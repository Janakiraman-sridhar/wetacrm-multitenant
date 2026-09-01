from datetime import date, datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ContactBrief, ORMModel, UserBrief


class ItemIn(ORMModel):
    product_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    quantity: float = Field(1, gt=0)
    unit_price: float = Field(0, ge=0)
    tax_rate: float = Field(0, ge=0, le=100)


class ItemOut(ItemIn):
    id: str
    line_total: float
    position: int


class QuotationCreate(ORMModel):
    company_id: str | None = None
    contact_id: str | None = None
    deal_id: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    currency: str = "INR"
    discount: float = Field(0, ge=0)
    notes: str | None = None
    terms: str | None = None
    items: list[ItemIn] = []


class QuotationUpdate(ORMModel):
    company_id: str | None = None
    contact_id: str | None = None
    deal_id: str | None = None
    status: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    currency: str | None = None
    discount: float | None = Field(None, ge=0)
    notes: str | None = None
    terms: str | None = None
    items: list[ItemIn] | None = None


class QuotationOut(ORMModel):
    id: str
    number: str
    status: str
    company_id: str | None = None
    contact_id: str | None = None
    deal_id: str | None = None
    issue_date: date | None = None
    valid_until: date | None = None
    currency: str
    subtotal: float
    tax_total: float
    discount: float
    total: float
    notes: str | None = None
    terms: str | None = None
    created_at: datetime
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    created_by: UserBrief | None = None
    items: list[ItemOut] = []


class SendQuotationIn(ORMModel):
    to_email: str | None = None  # defaults to the contact's first email
    message: str | None = None
