from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

#: Which family of cover this is. Drives which extra fields the form shows and how
#: the policy is reported on — deliberately a short fixed list, while the specific
#: plan name is free text and the insurer comes from the tenant's own masters.
PRODUCT_LINES = ["motor", "health", "life", "general"]

#: `expiring` and `lapsed` are set by the nightly job, never by hand — that is what
#: makes "renewals due" trustworthy. Renewal creates a *new* policy and marks the
#: old one `renewed`, so history is never overwritten.
POLICY_STATUSES = ["draft", "active", "expiring", "renewed", "lapsed", "cancelled"]

SOURCING_CHANNELS = ["direct", "bank", "online", "referral", "renewal", "agent"]

PAYMENT_MODES = ["cash", "cheque", "online", "upi", "card", "netbanking", "auto_debit"]

PAYMENT_FREQUENCIES = ["single", "annual", "half_yearly", "quarterly", "monthly"]

#: Days before expiry that renewal work should start. Also the thresholds the
#: reminder job uses.
RENEWAL_WINDOWS = [60, 30, 15, 7, 1]

MASTER_TYPES = [
    "insurer", "broker", "bank", "branch", "product_type", "relation", "loan_type",
]


class Master(TenantScoped, BaseModel):
    """A tenant's reference lists: insurers, banks, branches, relations.

    A table rather than a settings blob because policies point at these rows, and an
    agency renames or retires an insurer without wanting every old policy to change
    with it.
    """

    __tablename__ = "masters"

    __table_args__ = (
        UniqueConstraint("tenant_id", "type", "name", name="uq_masters_tenant_type_name"),
    )

    type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    code: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)


class Policy(TenantScoped, BaseModel):
    """One issued policy.

    Fields common to every line are real columns; the line-specific ones live in
    `details`. The exceptions are promoted to columns because they are filtered,
    sorted and reported on constantly — a JSON path is the wrong place for
    "everything expiring next month" or "find this registration number".
    """

    __tablename__ = "policies"

    __table_args__ = (
        UniqueConstraint("tenant_id", "policy_number", name="uq_policies_tenant_number"),
    )

    policy_number: Mapped[str] = mapped_column(String(80), index=True)
    product_line: Mapped[str] = mapped_column(String(20), index=True)
    plan_name: Mapped[str | None] = mapped_column(String(200))

    insurer_id: Mapped[str | None] = mapped_column(ForeignKey("masters.id"), index=True)
    #: The intermediary the business was placed through, where it was not placed
    #: direct. Distinct from `insurer_id`: one underwrites the risk, the other
    #: carries the agency code the commission is paid against, and an agency
    #: reconciles by both.
    broker_id: Mapped[str | None] = mapped_column(ForeignKey("masters.id"), index=True)
    #: Bancassurance source — the bank that introduced the business. Filterable
    #: because commission and reconciliation are organised by it.
    bank_id: Mapped[str | None] = mapped_column(ForeignKey("masters.id"), index=True)
    branch: Mapped[str | None] = mapped_column(String(150))
    sourcing_channel: Mapped[str | None] = mapped_column(String(20), index=True)

    customer_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    #: Set only when the person paying is not the person covered.
    proposer_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)

    issue_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)

    premium_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    premium_gst: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    #: What the customer actually paid — the number the book premium sums.
    premium_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, index=True)
    sum_insured: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")

    payment_mode: Mapped[str | None] = mapped_column(String(20))
    payment_frequency: Mapped[str | None] = mapped_column(String(20), default="annual")

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)

    #: Renewal chain. A renewal is a new row pointing back at the one it replaced, so
    #: the history of a customer's cover is never overwritten by an edit.
    renewal_of_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"), index=True)
    renewed_to_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"))

    commission_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    #: Motor registration number, promoted out of `details` because it is how an
    #: agent looks a motor policy up and what the Vahan lookup needs.
    registration_no: Mapped[str | None] = mapped_column(String(20), index=True)

    remarks: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    #: Line-specific fields — vehicle details, members covered, riders. Validated
    #: against the product line rather than free-form.
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    #: This tenant's custom fields (Phase 2).
    custom: Mapped[dict] = mapped_column(JSON, default=dict)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    insurer = relationship("Master", foreign_keys=[insurer_id], lazy="joined")
    broker = relationship("Master", foreign_keys=[broker_id], lazy="joined")
    bank = relationship("Master", foreign_keys=[bank_id], lazy="joined")
    customer = relationship("Contact", foreign_keys=[customer_id], lazy="joined")
    owner = relationship("User", lazy="joined")
    renewal_of = relationship("Policy", remote_side="Policy.id", foreign_keys=[renewal_of_id])

    @property
    def days_to_expiry(self) -> int | None:
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @property
    def is_in_force(self) -> bool:
        return self.status in ("active", "expiring")
