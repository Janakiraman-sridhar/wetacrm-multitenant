import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select

from app.automation.celery_app import celery_app
from app.core.tenancy import platform_scope, tenant_scope
from app.database.base import utcnow
from app.database.session import SessionLocal
from app.services import email as email_service

log = logging.getLogger("weta.tasks")


def active_tenant_ids(db) -> list[str]:
    """Tenants a scheduled job should run for."""
    from app.platform.models import Tenant

    with platform_scope():
        return list(
            db.scalars(
                select(Tenant.id).where(
                    Tenant.status.in_(["active", "trial"]), Tenant.deleted_at.is_(None)
                )
            ).all()
        )


def for_each_tenant(fn):
    """Run `fn(db)` once per active tenant, inside that tenant's scope.

    Scheduled jobs are the one place with no request to carry a tenant, so every
    one of them has to opt in explicitly. Returns the summed result.
    """
    total = 0
    with SessionLocal() as db:
        for tenant_id in active_tenant_ids(db):
            with tenant_scope(tenant_id):
                try:
                    total += fn(db) or 0
                except Exception:
                    log.exception("Scheduled job failed for tenant %s", tenant_id)
                    db.rollback()
    return total


@celery_app.task
def send_email_task(to: str | list[str], subject: str, body_html: str) -> bool:
    return email_service.send_email(to, subject, body_html)


@celery_app.task
def send_meeting_reminders() -> int:
    """Notify organizer + participants for meetings starting within 15 minutes."""
    return for_each_tenant(_send_meeting_reminders_for_tenant)


def _send_meeting_reminders_for_tenant(db) -> int:
    from app.activities.models import Activity
    from app.meetings.models import Meeting
    from app.notifications.service import notify

    sent = 0
    now = utcnow()
    upcoming = db.scalars(
        select(Meeting).where(and_(Meeting.starts_at >= now, Meeting.starts_at <= now + timedelta(minutes=15)))
    ).all()
    for meeting in upcoming:
        already = db.scalar(
            select(Activity).where(
                and_(
                    Activity.entity_type == "meeting",
                    Activity.entity_id == meeting.id,
                    Activity.type == "system",
                    Activity.title == "Reminder sent",
                )
            )
        )
        if already:
            continue
        user_ids = {meeting.organizer_id, *(meeting.participant_ids or [])} - {None}
        for uid in user_ids:
            notify(db, uid, "meeting_reminder", f"Meeting soon: {meeting.title}",
                   f"Starts at {meeting.starts_at:%H:%M} UTC", "/calendar")
        db.add(Activity(entity_type="meeting", entity_id=meeting.id, type="system", title="Reminder sent"))
        sent += 1
    db.commit()
    return sent


@celery_app.task
def mark_overdue_invoices() -> int:
    return for_each_tenant(_mark_overdue_invoices_for_tenant)


def _mark_overdue_invoices_for_tenant(db) -> int:
    from app.invoices.models import Invoice

    rows = db.scalars(
        select(Invoice).where(and_(Invoice.status.in_(["sent", "partial"]), Invoice.due_date < date.today()))
    ).all()
    for inv in rows:
        inv.status = "overdue"
    db.commit()
    return len(rows)


def _admin_emails(db) -> list[str]:
    from app.users.models import Role, User

    stmt = select(User.email).join(Role).where(Role.name.in_(["Super Admin", "Admin"]), User.is_active.is_(True))
    return list(db.scalars(stmt).all())


def _summary_since(db, since) -> str:
    from app.deals.models import Deal
    from app.leads.models import Lead
    from app.tasks.models import Task

    new_leads = db.scalar(select(func.count()).select_from(Lead).where(Lead.created_at >= since)) or 0
    won = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "won", Deal.closed_at >= since)) or 0
    open_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.status.in_(["todo", "in_progress"]))) or 0
    return (
        f"<p>New leads: <b>{new_leads}</b><br/>"
        f"Deals won: <b>{won}</b><br/>"
        f"Open tasks: <b>{open_tasks}</b></p>"
    )


def _send_summary(db, since, label: str) -> int:
    body = _summary_since(db, since)
    admins = _admin_emails(db)
    if not admins:
        return 0
    email_service.send_email(admins, f"WeTa CRM — {label}", body)
    return 1


@celery_app.task
def send_daily_summary() -> int:
    return for_each_tenant(lambda db: _send_summary(db, utcnow() - timedelta(days=1), "Daily summary"))


@celery_app.task
def send_weekly_summary() -> int:
    return for_each_tenant(lambda db: _send_summary(db, utcnow() - timedelta(days=7), "Weekly summary"))


@celery_app.task
def reindex_search() -> int:
    return for_each_tenant(_reindex_for_tenant)


def _reindex_for_tenant(db) -> int:
    from app.companies.models import Company
    from app.contacts.models import Contact
    from app.deals.models import Deal
    from app.leads.models import Lead
    from app.projects.models import Project
    from app.services import search_sync
    from app.tasks.models import Task

    count = 0
    for model, sync in [
        (Company, search_sync.sync_company), (Contact, search_sync.sync_contact),
        (Lead, search_sync.sync_lead), (Deal, search_sync.sync_deal),
        (Task, search_sync.sync_task), (Project, search_sync.sync_project),
    ]:
        for row in db.scalars(select(model)).all():
            sync(row)
            count += 1
    return count


@celery_app.task
def refresh_policy_statuses() -> int:
    """Move policies between active, expiring and lapsed as dates pass.

    Status being derived rather than typed is what makes "renewals due in 60 days"
    a number worth acting on — it cannot drift because someone forgot to change a
    dropdown.
    """
    return for_each_tenant(_refresh_policy_statuses_for_tenant)


def _refresh_policy_statuses_for_tenant(db) -> int:
    from app.policies import service as policy_service

    return policy_service.refresh_statuses(db)


@celery_app.task
def create_renewal_tasks() -> int:
    """Raise a renewal task at each threshold before expiry.

    De-duplicated on the policy and threshold, so a restart or a second run in the
    same day does not bury the agent in copies of the same reminder.
    """
    return for_each_tenant(_create_renewal_tasks_for_tenant)


def _create_renewal_tasks_for_tenant(db) -> int:
    from app.policies.models import RENEWAL_WINDOWS
    from app.policies import service as policy_service
    from app.notifications.service import notify
    from app.tasks.models import Task

    created = 0
    today = date.today()
    for policy in policy_service.renewals_due(db, within_days=max(RENEWAL_WINDOWS)):
        days = (policy.expiry_date - today).days
        threshold = next((w for w in sorted(RENEWAL_WINDOWS) if days <= w), None)
        if threshold is None:
            continue

        title = f"Renewal due in {threshold} days: {policy.policy_number}"
        already = db.scalar(
            select(Task).where(
                Task.entity_type == "policy",
                Task.entity_id == policy.id,
                Task.title == title,
            )
        )
        if already:
            continue

        customer = policy.customer.full_name if policy.customer else "customer"
        db.add(
            Task(
                title=title,
                description=(
                    f"{customer}'s {policy.product_line} policy "
                    f"{policy.policy_number} expires on {policy.expiry_date:%d %b %Y}."
                ),
                priority="high" if threshold <= 7 else "medium",
                due_date=datetime.combine(policy.expiry_date, datetime.min.time()),
                assigned_to_id=policy.owner_id,
                entity_type="policy",
                entity_id=policy.id,
            )
        )
        if policy.owner_id:
            notify(db, policy.owner_id, "renewal_due", title,
                   f"Expires {policy.expiry_date:%d %b %Y}", f"/policies?id={policy.id}")
        created += 1

    if created:
        db.commit()
    return created


@celery_app.task
def purge_deleted_tenants() -> int:
    """Remove workspaces whose retention window has passed. Irreversible.

    The console promises a deleted workspace is kept for 30 days and then removed.
    This is what makes the second half of that true.

    Each tenant is purged independently: one failing (storage unreachable, say)
    must not stop the rest, and a tenant that fails part-way is left soft-deleted
    so the next run picks it up again.
    """
    from app.platform import purge

    purged = 0
    with SessionLocal() as db:
        try:
            due = purge.tenants_due_for_purge(db)
        except ValueError:
            log.exception("Retention window is misconfigured; purging nothing")
            return 0

        for tenant in due:
            try:
                summary = purge.purge_tenant(db, tenant)
                log.warning(
                    "Purged %s after retention: %s rows, %s files",
                    summary["slug"], sum(summary["rows"].values()), summary["files_removed"],
                )
                purged += 1
            except Exception:
                log.exception("Could not purge tenant %s; it stays for the next run", tenant.slug)
                db.rollback()
    return purged
