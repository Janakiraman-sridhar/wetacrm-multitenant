from datetime import datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ContactBrief, ORMModel, UserBrief


class TicketBase(ORMModel):
    subject: str = Field(min_length=1, max_length=255)
    description: str | None = None
    company_id: str | None = None
    contact_id: str | None = None
    priority: str = "medium"
    status: str = "open"
    assigned_to_id: str | None = None
    resolution: str | None = None
    #: Values for this tenant's custom fields. Validated on flush against the
    #: tenant's own field definitions; undeclared keys are dropped.
    custom: dict = {}


class TicketCreate(TicketBase):
    pass


class TicketUpdate(ORMModel):
    subject: str | None = None
    description: str | None = None
    company_id: str | None = None
    contact_id: str | None = None
    priority: str | None = None
    status: str | None = None
    assigned_to_id: str | None = None
    resolution: str | None = None
    custom: dict | None = None


class TicketOut(TicketBase):
    id: str
    number: str
    created_at: datetime
    updated_at: datetime
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    assigned_to: UserBrief | None = None
