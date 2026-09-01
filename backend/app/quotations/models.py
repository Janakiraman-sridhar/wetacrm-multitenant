from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel

QUOTATION_STATUSES = ["draft", "sent", "accepted", "declined", "converted"]


class Quotation(BaseModel):
    __tablename__ = "quotations"

    number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
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

    company = relationship("Company", lazy="joined")
    contact = relationship("Contact", lazy="joined")
    created_by = relationship("User", lazy="joined")
    items: Mapped[list["QuotationItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", lazy="selectin", order_by="QuotationItem.position"
    )


class QuotationItem(BaseModel):
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
