from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel, UserBrief


class SourceOut(ORMModel):
    id: str
    name: str


class LeadBase(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    source_id: str | None = None
    status: str = "new"
    score: int = Field(0, ge=0, le=100)
    assigned_to_id: str | None = None
    notes: str | None = None
    follow_up_at: datetime | None = None
    tags: list[str] = []
    #: Values for this tenant's custom fields. Validated on flush against the
    #: tenant's own field definitions; undeclared keys are dropped.
    custom: dict = {}


class LeadCreate(LeadBase):
    pass


class LeadUpdate(ORMModel):
    title: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    source_id: str | None = None
    status: str | None = None
    score: int | None = Field(None, ge=0, le=100)
    assigned_to_id: str | None = None
    notes: str | None = None
    follow_up_at: datetime | None = None
    tags: list[str] | None = None
    custom: dict | None = None


class LeadOut(LeadBase):
    id: str
    created_at: datetime
    updated_at: datetime
    converted_deal_id: str | None = None
    source: SourceOut | None = None
    assigned_to: UserBrief | None = None


class LeadConvertIn(ORMModel):
    deal_title: str | None = None
    value: float = 0
    company_id: str | None = None
    contact_id: str | None = None
    create_company: bool = True
    create_contact: bool = True
