from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

QUOTATION_STATUSES = ["draft", "sent", "accepted", "declined", "converted"]

#: "standard" quotes line items that add up; "insurance" quotes competing insurers,
#: of which the customer takes one. See `app/quotations/insurance.py`.
QUOTATION_KINDS = ["standard", "insurance"]


class Quotation(TenantScoped, BaseModel):
    __tablename__ = "quotations"

    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_quotations_tenant_number"),)

    number: Mapped[str] = mapped_column(String(50), index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    kind: Mapped[str] = mapped_column(String(20), default="standard", index=True)
    issue_date: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    #: The risk quoted plus the competing insurer options — insurance quotations only.
    insurance: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Set when this quotation was converted into a policy.
    policy_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"), index=True)

    company = relationship("Company", lazy="joined")
    contact = relationship("Contact", lazy="joined")
    created_by = relationship("User", lazy="joined")
    items: Mapped[list["QuotationItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", lazy="selectin", order_by="QuotationItem.position"
    )


class QuotationItem(TenantScoped, BaseModel):
    __tablename__ = "quotation_items"

    quotation_id: Mapped[str] = mapped_column(ForeignKey("quotations.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)

    quotation: Mapped[Quotation] = relationship(back_populates="items")
