from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

INVOICE_STATUSES = ["draft", "sent", "partial", "paid", "overdue", "cancelled"]


class Invoice(TenantScoped, BaseModel):
    __tablename__ = "invoices"

    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_invoices_tenant_number"),)

    number: Mapped[str] = mapped_column(String(50), index=True)
    quotation_id: Mapped[str | None] = mapped_column(ForeignKey("quotations.id"))
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    company = relationship("Company", lazy="joined")
    contact = relationship("Contact", lazy="joined")
    created_by = relationship("User", lazy="joined")
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", lazy="selectin", order_by="InvoiceItem.position"
    )


class InvoiceItem(TenantScoped, BaseModel):
    __tablename__ = "invoice_items"

    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)

    invoice: Mapped[Invoice] = relationship(back_populates="items")
