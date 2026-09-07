"""The customer record's insurance fields, and the rules that keep them clean.

These live on `contacts` rather than a new table: an insurance tenant's "Customer"
*is* the CRM's contact, relabelled by its template. A separate table would fork every
relationship, filter, export and search path for no gain.

Every column here is nullable and the general CRM template leaves them hidden, so a
non-insurance tenant is unaffected.
"""

from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

# A customer's position in the agency's own lifecycle, distinct from the enquiry
# pipeline. Seeded per tenant so an agency can rename or reorder them.
DEFAULT_CUSTOMER_STAGES = [
    "Prospect", "Contacted", "Documents pending", "Policy issued",
    "Active", "Renewal due", "Lapsed", "Dormant",
]

REFERRAL_TYPES = ["customer", "staff", "external", "campaign", "walk_in"]

GENDERS = ["male", "female", "other", "prefer_not_to_say"]

MARITAL_STATUSES = ["single", "married", "widowed", "divorced"]


class CustomerFieldsMixin:
    """Insurance customer columns, mixed into `Contact`."""

    # --- personal -------------------------------------------------------------
    date_of_birth: Mapped[date | None] = mapped_column(Date, index=True)
    #: Day-of-year as MMDD, indexed, so "whose birthday is this week" is one range
    #: scan instead of a function call on every row.
    birthday_key: Mapped[str | None] = mapped_column(String(4), index=True)
    gender: Mapped[str | None] = mapped_column(String(20))
    marital_status: Mapped[str | None] = mapped_column(String(20))
    occupation: Mapped[str | None] = mapped_column(String(150))
    annual_income: Mapped[int | None] = mapped_column(Integer)

    # --- contact --------------------------------------------------------------
    mobile: Mapped[str | None] = mapped_column(String(20), index=True)
    alt_mobile: Mapped[str | None] = mapped_column(String(20))
    alt_email: Mapped[str | None] = mapped_column(String(255))

    # --- address --------------------------------------------------------------
    address_line: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(String(6), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))

    # --- identity (encrypted; see app/services/crypto.py) ---------------------
    #: Ciphertext. Never returned by the API — the schema serialises the masked
    #: form, and the full value only through the audited reveal endpoint.
    pan_encrypted: Mapped[str | None] = mapped_column(Text)
    #: Keyed hash of the PAN, for exact-match lookup without decrypting.
    pan_index: Mapped[str | None] = mapped_column(String(64), index=True)
    aadhaar_encrypted: Mapped[str | None] = mapped_column(Text)
    aadhaar_index: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Always stored, even when full capture is off — it is what masking shows and
    #: what an agency is normally allowed to keep. See PRD 9.4.
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4))

    # --- relationship ---------------------------------------------------------
    stage: Mapped[str | None] = mapped_column(String(50), index=True)
    referred_by_type: Mapped[str | None] = mapped_column(String(20))
    referred_by_contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    referred_by_name: Mapped[str | None] = mapped_column(String(200))
    referred_on: Mapped[date | None] = mapped_column(Date)
    #: Product lines the customer is interested in, loans included — the light-touch
    #: alternative to opening a record for every cross-sell idea.
    products_of_interest: Mapped[list] = mapped_column(JSON, default=list)


def birthday_key_for(value: date | None) -> str | None:
    """MMDD, so a date range covers "this week" without touching every row."""
    return f"{value.month:02d}{value.day:02d}" if value else None
