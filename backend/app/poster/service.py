"""Building the merge values and the audience a batch is generated for."""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contacts.models import Contact
from app.policies.models import Policy
from app.poster.presets import MERGE_FIELDS, PRESETS
from app.poster.models import PosterTemplate
from app.services import storage
from app.settings.models import Setting

log = logging.getLogger("weta.poster")


def seed_presets(db: Session) -> int:
    """Give a workspace something to send on day one instead of a blank canvas."""
    existing = {t.name for t in db.scalars(select(PosterTemplate)).all()}
    created = 0
    for preset in PRESETS:
        if preset["name"] in existing:
            continue
        db.add(PosterTemplate(is_system=False, is_active=True, **preset))
        created += 1
    return created


def agency_values(db: Session, user=None) -> dict:
    """The parts of a poster that are about the agency, not the customer."""
    profile = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    branding = db.scalar(select(Setting).where(Setting.key == "branding"))
    agency = (profile.value or {}) if profile else {}
    brand = (branding.value or {}) if branding else {}
    return {
        "agency_name": agency.get("name") or brand.get("app_name") or "",
        "agent_name": f"{user.first_name} {user.last_name}".strip() if user else "",
        # The agent's own number if they have one, else the agency switchboard.
        "agent_mobile": (user.phone if user and user.phone else agency.get("phone")) or "",
    }


def customer_values(contact: Contact) -> dict:
    return {
        "customer_name": contact.full_name,
        "first_name": contact.first_name,
    }


def policy_values(policy: Policy) -> dict:
    days = policy.days_to_expiry
    return {
        "policy_number": policy.policy_number,
        "insurer": policy.insurer.name if policy.insurer else "",
        "expiry_date": policy.expiry_date.strftime("%d %b %Y") if policy.expiry_date else "",
        "days_to_expiry": str(days) if days is not None else "",
        "premium": f"₹{policy.premium_gross:,.0f}" if policy.premium_gross else "",
        "vehicle_no": policy.registration_no or "",
        "product_line": (policy.product_line or "").title(),
    }


def sample_values(db: Session, user=None) -> dict:
    """Placeholder values for the editor preview — real agency details, fake customer."""
    return {**MERGE_FIELDS, **agency_values(db, user)}


def load_assets(db: Session, template: dict) -> dict:
    """Fetch the images a template refers to.

    Only the logo for now; an uploaded background or agent photo resolves through
    the same map once the asset library lands.
    """
    assets: dict[str, bytes] = {}
    needs_logo = (template.get("background") or {}).get("image") == "logo" or any(
        layer.get("source") == "logo" for layer in template.get("layers") or []
    )
    if not needs_logo:
        return assets

    profile = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    logo_key = (profile.value or {}).get("logo_key") if profile else None
    if logo_key:
        try:
            assets["logo"] = storage.read_file(logo_key)
        except Exception:
            log.warning("Could not load the workspace logo for a poster")
    return assets


# --- audiences ----------------------------------------------------------------

def audience_birthdays(db: Session, within_days: int = 7) -> list[dict]:
    """Customers with a birthday coming up, each with their own merge values."""
    today = date.today()
    keys = [
        f"{(today + timedelta(days=offset)).month:02d}{(today + timedelta(days=offset)).day:02d}"
        for offset in range(within_days + 1)
    ]
    rows = db.scalars(
        select(Contact).where(Contact.birthday_key.in_(keys), Contact.date_of_birth.isnot(None))
    ).all()
    return [
        {
            "contact_id": contact.id,
            "name": contact.full_name,
            "phone": contact.primary_phone,
            "values": customer_values(contact),
        }
        for contact in rows
    ]


def audience_renewals(db: Session, within_days: int = 30) -> list[dict]:
    """Policies coming up for renewal, with both customer and policy merge values."""
    from app.policies import service as policy_service

    out = []
    for policy in policy_service.renewals_due(db, within_days):
        contact = policy.customer
        if not contact:
            continue
        out.append({
            "contact_id": contact.id,
            "policy_id": policy.id,
            "name": contact.full_name,
            "phone": contact.primary_phone,
            "values": {**customer_values(contact), **policy_values(policy)},
        })
    return out


def audience_selection(db: Session, contact_ids: list[str]) -> list[dict]:
    rows = db.scalars(select(Contact).where(Contact.id.in_(contact_ids))).all()
    return [
        {
            "contact_id": contact.id,
            "name": contact.full_name,
            "phone": contact.primary_phone,
            "values": customer_values(contact),
        }
        for contact in rows
    ]


def resolve_audience(db: Session, kind: str, params: dict) -> list[dict]:
    if kind == "birthdays":
        return audience_birthdays(db, int(params.get("within_days", 7)))
    if kind == "renewals":
        return audience_renewals(db, int(params.get("within_days", 30)))
    if kind == "selection":
        return audience_selection(db, params.get("contact_ids") or [])
    return []
