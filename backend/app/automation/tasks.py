import logging
from datetime import date, timedelta

from sqlalchemy import and_, func, select

from app.automation.celery_app import celery_app
from app.database.base import utcnow
from app.database.session import SessionLocal
from app.services import email as email_service

log = logging.getLogger("weta.tasks")


@celery_app.task
def send_email_task(to: str | list[str], subject: str, body_html: str) -> bool:
    return email_service.send_email(to, subject, body_html)


@celery_app.task
def send_meeting_reminders() -> int:
    """Notify organizer + participants for meetings starting within 15 minutes."""
    from app.activities.models import Activity
    from app.meetings.models import Meeting
    from app.notifications.service import notify

    sent = 0
    with SessionLocal() as db:
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
    from app.invoices.models import Invoice

    with SessionLocal() as db:
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


@celery_app.task
def send_daily_summary() -> bool:
    with SessionLocal() as db:
        body = _summary_since(db, utcnow() - timedelta(days=1))
        admins = _admin_emails(db)
    return email_service.send_email(admins, "WeTa CRM — Daily summary", body) if admins else False


@celery_app.task
def send_weekly_summary() -> bool:
    with SessionLocal() as db:
        body = _summary_since(db, utcnow() - timedelta(days=7))
        admins = _admin_emails(db)
    return email_service.send_email(admins, "WeTa CRM — Weekly summary", body) if admins else False


@celery_app.task
def reindex_search() -> int:
    from app.companies.models import Company
    from app.contacts.models import Contact
    from app.deals.models import Deal
    from app.leads.models import Lead
    from app.projects.models import Project
    from app.services import search_sync
    from app.tasks.models import Task

    count = 0
    with SessionLocal() as db:
        for model, sync in [
            (Company, search_sync.sync_company), (Contact, search_sync.sync_contact),
            (Lead, search_sync.sync_lead), (Deal, search_sync.sync_deal),
            (Task, search_sync.sync_task), (Project, search_sync.sync_project),
        ]:
            for row in db.scalars(select(model)).all():
                sync(row)
                count += 1
    return count
