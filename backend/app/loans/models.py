from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

#: An agent's loan case moves through these in order, except that `rejected` can
#: happen at any point. Terminal states are `disbursed` and `rejected`.
LOAN_STATUSES = ["enquiry", "documents", "logged_in", "sanctioned", "disbursed", "rejected"]

#: The stages that still need work, in the order an agent works them. Used by the
#: board and by the "open cases" figure.
OPEN_LOAN_STATUSES = ["enquiry", "documents", "logged_in", "sanctioned"]

LOAN_TYPES = [
    "Home Loan", "Personal Loan", "Vehicle Loan", "Business Loan",
    "Loan Against Property", "Education Loan",
]


class Loan(TenantScoped, BaseModel):
    """A loan case an agent is cross-selling, tracked to payout.

    Deliberately thinner than a policy: an agent introduces the customer to a lender
    and is paid a percentage of what is disbursed. The lender owns the underwriting,
    so what matters here is whose case it is, where it has got to, and what it earns.

    `payout_percent` is applied to the **sanctioned** amount, which is what lenders
    actually pay on, and `expected_payout` is derived rather than typed so it cannot
    drift from the numbers beside it.
    """

    __tablename__ = "loans"

    customer_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    loan_type: Mapped[str] = mapped_column(String(60), index=True)
    #: The lender, from the tenant's `bank` masters. Free text is not offered: a
    #: payout report grouped by lender is only useful if the names are consistent.
    lender_id: Mapped[str | None] = mapped_column(ForeignKey("masters.id"), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)

    status: Mapped[str] = mapped_column(String(20), default="enquiry", index=True)

    amount_requested: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_sanctioned: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    payout_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    #: Derived from the sanctioned amount and the payout percentage.
    expected_payout: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    #: What was actually received, which is often not what was expected.
    actual_payout: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    applied_on: Mapped[date | None] = mapped_column(Date)
    sanctioned_on: Mapped[date | None] = mapped_column(Date)
    disbursed_on: Mapped[date | None] = mapped_column(Date, index=True)
    rejected_reason: Mapped[str | None] = mapped_column(String(300))

    remarks: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    custom: Mapped[dict] = mapped_column(JSON, default=dict)

    customer = relationship("Contact", lazy="joined")
    lender = relationship("Master", lazy="joined")
    owner = relationship("User", lazy="joined")

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_LOAN_STATUSES

    @property
    def payout_outstanding(self) -> Decimal | None:
        """What is still owed on a disbursed case."""
        if self.status != "disbursed" or self.expected_payout is None:
            return None
        return self.expected_payout - (self.actual_payout or Decimal(0))
