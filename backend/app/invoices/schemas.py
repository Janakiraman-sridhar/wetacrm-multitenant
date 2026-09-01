from datetime import date, datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ContactBrief, ORMModel, UserBrief
from app.quotations.schemas import ItemIn, ItemOut


class InvoiceCreate(ORMModel):
    company_id: str | None = None
    contact_id: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str = "INR"
    discount: float = Field(0, ge=0)
    notes: str | None = None
    items: list[ItemIn] = []


class InvoiceUpdate(ORMModel):
    company_id: str | None = None
    contact_id: str | None = None
    status: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    discount: float | None = Field(None, ge=0)
    notes: str | None = None
    items: list[ItemIn] | None = None


class InvoiceOut(ORMModel):
    id: str
    number: str
    quotation_id: str | None = None
    status: str
    company_id: str | None = None
    contact_id: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str
    subtotal: float
    tax_total: float
    discount: float
    total: float
    amount_paid: float
    notes: str | None = None
    created_at: datetime
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    created_by: UserBrief | None = None
    items: list[ItemOut] = []


class PaymentIn(ORMModel):
    amount: float = Field(gt=0)
