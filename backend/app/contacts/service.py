"""Customer PII: writing it, masking it, and revealing it under audit.

The rule this file exists to enforce: **a full PAN or Aadhaar never leaves the API
by accident.** Serialisation returns the masked form; the plaintext is reachable only
through `reveal_field`, which requires its own permission and writes an audit row
every single time.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.exceptions import AppError, PermissionDeniedError
from app.core.permissions import has_permission
from app.core.tenancy import require_tenant_id
from app.core.validators import (
    mask_pan, normalise_aadhaar, normalise_pan, normalise_phone, normalise_pincode,
)
from app.services import crypto
from app.settings.models import Setting

log = logging.getLogger("weta.customers")

REVEAL_PERMISSION = "contacts:reveal_pii"


# --- tenant policy ------------------------------------------------------------

def tenant_features(db: Session) -> dict:
    row = db.scalar(select(Setting).where(Setting.key == "features"))
    return dict(row.value or {}) if row else {}


def aadhaar_full_capture_enabled(db: Session) -> bool:
    """Whether this tenant may store the whole Aadhaar number.

    Off unless a tenant deliberately turns it on. A private entity storing full
    Aadhaar is restricted under the Aadhaar Act; last-4 is the normal practice for
    an intermediary. See PRD 9.4.
    """
    return bool(tenant_features(db).get("aadhaar_full_capture", False))


# --- writing ------------------------------------------------------------------

def apply_identity(db: Session, contact, pan: str | None, aadhaar: str | None) -> None:
    """Validate, encrypt and index PAN and Aadhaar onto a contact.

    Passing `None` leaves the stored value alone, so a PATCH that does not mention
    PAN does not wipe it. Passing an empty string clears it.
    """
    tenant_id = require_tenant_id()

    if pan is not None:
        if pan == "":
            contact.pan_encrypted = None
            contact.pan_index = None
        else:
            cleaned = normalise_pan(pan)
            contact.pan_encrypted = crypto.encrypt_for_tenant(tenant_id, cleaned)
            contact.pan_index = crypto.blind_index(tenant_id, cleaned)

    if aadhaar is not None:
        if aadhaar == "":
            contact.aadhaar_encrypted = None
            contact.aadhaar_index = None
            contact.aadhaar_last4 = None
        else:
            cleaned = normalise_aadhaar(aadhaar)
            # Last-4 is always kept; the full number only where the tenant opted in.
            contact.aadhaar_last4 = cleaned[-4:]
            if aadhaar_full_capture_enabled(db):
                contact.aadhaar_encrypted = crypto.encrypt_for_tenant(tenant_id, cleaned)
                contact.aadhaar_index = crypto.blind_index(tenant_id, cleaned)
            else:
                contact.aadhaar_encrypted = None
                contact.aadhaar_index = None


def normalise_customer_fields(db: Session, data: dict) -> dict:
    """Clean the contact payload fields that have a canonical form."""
    country_code = "+91"
    profile = db.scalar(select(Setting).where(Setting.key == "company_profile"))
    if profile and (profile.value or {}).get("country_code"):
        country_code = profile.value["country_code"]

    for field in ("mobile", "alt_mobile"):
        if data.get(field):
            data[field] = normalise_phone(data[field], country_code)
    if data.get("phones"):
        data["phones"] = [normalise_phone(p, country_code) for p in data["phones"] if p]
    if "pincode" in data and data["pincode"]:
        data["pincode"] = normalise_pincode(data["pincode"])
    if data.get("date_of_birth"):
        from app.contacts.customer_fields import birthday_key_for

        value = data["date_of_birth"]
        data["birthday_key"] = birthday_key_for(value)
    return data


def find_by_identity(db: Session, pan: str | None = None, aadhaar: str | None = None):
    """Look a customer up by PAN or Aadhaar, without decrypting anything.

    This is what the blind index is for: the lookup hashes the search term the same
    way the stored value was hashed and compares hashes.
    """
    from app.contacts.models import Contact

    tenant_id = require_tenant_id()
    if pan:
        index = crypto.blind_index(tenant_id, normalise_pan(pan))
        return db.scalar(select(Contact).where(Contact.pan_index == index)) if index else None
    if aadhaar:
        index = crypto.blind_index(tenant_id, normalise_aadhaar(aadhaar))
        return db.scalar(select(Contact).where(Contact.aadhaar_index == index)) if index else None
    return None


# --- reading ------------------------------------------------------------------

def masked_identity(contact) -> dict:
    """What the API returns by default: enough to recognise, not enough to use."""
    pan_plain = None
    if contact.pan_encrypted:
        pan_plain = crypto.decrypt_for_tenant(contact.tenant_id, contact.pan_encrypted)
    return {
        "pan_masked": mask_pan(pan_plain) if pan_plain else None,
        "has_pan": bool(contact.pan_encrypted),
        "aadhaar_masked": f"XXXX XXXX {contact.aadhaar_last4}" if contact.aadhaar_last4 else None,
        "has_aadhaar": bool(contact.aadhaar_last4),
        "aadhaar_full_stored": bool(contact.aadhaar_encrypted),
    }


def reveal_field(db: Session, contact, field: str, user, ip: str | None = None) -> str:
    """Return a full PAN or Aadhaar, and record who looked.

    Every reveal is audited — that record is what makes storing this data
    defensible, and it is what a tenant admin reviews in the PII access report.
    """
    if not has_permission(user.role.permissions if user.role else [], REVEAL_PERMISSION):
        raise PermissionDeniedError("You do not have permission to view full identity numbers")

    if field == "pan":
        stored = contact.pan_encrypted
    elif field == "aadhaar":
        stored = contact.aadhaar_encrypted
        if not stored and contact.aadhaar_last4:
            raise AppError(
                "Only the last 4 digits of this Aadhaar are stored. "
                "Full capture is switched off for this workspace.",
                400,
            )
    else:
        raise AppError(f"'{field}' is not a revealable field")

    if not stored:
        raise AppError(f"No {field.upper()} is stored for this customer", 404)

    value = crypto.decrypt_for_tenant(contact.tenant_id, stored)
    if value is None:
        raise AppError("Stored value could not be read", 500)

    audit(
        db, user.id, "reveal_pii", "contact", contact.id,
        {"field": field, "customer": contact.full_name}, ip_address=ip,
    )
    db.commit()
    log.info("PII revealed: %s on contact %s by user %s", field, contact.id, user.id)
    return value
