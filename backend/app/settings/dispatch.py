"""Sending the scheduled emails, once each.

The renewal reminder and the birthday greeting are the two triggers a daily job
fires rather than a request. Both need the same protection: the job runs every day,
and a policy is "due in 30 days" only once but "inside the renewal window" for two
months. Without a record of what has already gone out, an agency's customers get the
same reminder every morning for a month, which is the kind of bug that loses the
agency their customer rather than losing us a test.

The record is a `sent_emails` row with a unique dedupe key, and the uniqueness is
enforced by the database — not by reading first and writing second, which two workers
can both get through.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.settings import workflows
from app.settings.models import EmailTemplate, SentEmail, Setting

log = logging.getLogger("weta.dispatch")


def _company(db: Session) -> dict:
    row = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    return row.value or {} if row else {}


def _already_sent(db: Session, dedupe_key: str) -> bool:
    return db.scalar(
        select(SentEmail.id).where(SentEmail.dedupe_key == dedupe_key)
    ) is not None


def send_once(
    db: Session,
    trigger: str,
    to: str,
    context: dict,
    *,
    dedupe_key: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> bool:
    """Send, unless this exact thing has already been sent. Returns True if it went.

    The row is written *before* the send and committed, so a crash mid-send fails
    towards not sending again rather than towards sending twice. For a renewal
    reminder that is the right way round: a customer who misses one email gets the
    next threshold, a customer who gets five is being harassed by software.
    """
    if not to or "@" not in to:
        return False
    if _already_sent(db, dedupe_key):
        return False

    template = workflows.template_for(db, trigger)
    if template is None:
        return False

    record = SentEmail(
        trigger=trigger, dedupe_key=dedupe_key, recipient=to,
        entity_type=entity_type, entity_id=entity_id,
        subject=template.subject, sent_at=utcnow(), delivered=False,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # Another worker claimed this send between the check and the insert. That is
        # exactly what the unique constraint is for.
        db.rollback()
        return False

    delivered = workflows.fire(db, trigger, to, context)
    record.delivered = delivered
    db.commit()
    if not delivered:
        log.warning("Email for %s to %s was not delivered", trigger, to)
    return delivered


# --- renewal reminders --------------------------------------------------------

def send_renewal_emails(db: Session) -> int:
    """One email per policy at each configured threshold before expiry."""
    from app.policies import service as policy_service

    template = workflows.template_for(db, "policy_renewal_due")
    if template is None:
        return 0

    thresholds = sorted(
        (template.config or {}).get("days_before")
        or workflows.default_config("policy_renewal_due")["days_before"],
        reverse=True,
    )
    if not thresholds:
        return 0

    company = _company(db)
    today = date.today()
    sent = 0

    for policy in policy_service.renewals_due(db, within_days=max(thresholds)):
        customer = policy.customer
        if not customer:
            continue
        to = (customer.emails or [None])[0]
        if not to:
            continue

        days = (policy.expiry_date - today).days
        # The threshold this policy has just crossed, not every one below it — a
        # policy at 6 days should get the 7-day email once, not 7, 15, 30 and 60.
        threshold = next((t for t in sorted(thresholds) if days <= t), None)
        if threshold is None:
            continue

        if send_once(
            db, "policy_renewal_due", to,
            {
                "customer_name": customer.full_name,
                "policy_number": policy.policy_number,
                "insurer": policy.insurer.name if policy.insurer else "",
                "expiry_date": policy.expiry_date.strftime("%d %b %Y"),
                "days_to_expiry": days,
                "premium": f"{policy.currency} {policy.premium_gross:,.2f}",
                "agent_name": policy.owner.full_name if policy.owner else "",
                "company_name": company.get("name", ""),
            },
            dedupe_key=f"renewal:{policy.id}:{threshold}",
            entity_type="policy", entity_id=policy.id,
        ):
            sent += 1
    return sent


# --- birthday greetings -------------------------------------------------------

def send_birthday_emails(db: Session) -> int:
    from app.contacts.models import Contact

    template = workflows.template_for(db, "customer_birthday")
    if template is None:
        return 0

    offsets = (template.config or {}).get("days_before")
    if offsets is None:
        offsets = workflows.default_config("customer_birthday")["days_before"]
    if not offsets:
        return 0

    company = _company(db)
    today = date.today()
    sent = 0

    for offset in offsets:
        target = today + timedelta(days=offset)
        key = f"{target.month:02d}{target.day:02d}"
        for contact in db.scalars(
            select(Contact).where(Contact.birthday_key == key)
        ).all():
            to = (contact.emails or [None])[0]
            if not to:
                continue
            if send_once(
                db, "customer_birthday", to,
                {
                    "customer_name": contact.full_name,
                    "agent_name": contact.owner.full_name if contact.owner else "",
                    "company_name": company.get("name", ""),
                },
                # Keyed by the year so it sends again next year, and by the offset so
                # "day before" and "on the day" are distinct sends.
                dedupe_key=f"birthday:{contact.id}:{target.year}:{offset}",
                entity_type="contact", entity_id=contact.id,
            ):
                sent += 1
    return sent
