from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel


class ProductBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit_price: float = 0
    currency: str = "INR"
    tax_rate: float = Field(0, ge=0, le=100)
    stock_qty: int | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ORMModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit_price: float | None = None
    currency: str | None = None
    tax_rate: float | None = Field(None, ge=0, le=100)
    stock_qty: int | None = None
    is_active: bool | None = None


class ProductOut(ProductBase):
    id: str
    created_at: datetime
    updated_at: datetime
