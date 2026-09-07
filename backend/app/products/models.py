from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped


class Product(TenantScoped, BaseModel):
    __tablename__ = "products"

    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),)

    name: Mapped[str] = mapped_column(String(255), index=True)
    sku: Mapped[str | None] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)  # percent
    stock_qty: Mapped[int | None] = mapped_column(Integer)  # optional stock tracking
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
