from datetime import datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ORMModel, UserBrief


class ContactBase(ORMModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = ""
    position: str | None = None
    company_id: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    social_links: dict[str, str] = {}
    notes: str | None = None
    tags: list[str] = []
    owner_id: str | None = None
    #: Values for this tenant's custom fields. Validated on flush against the
    #: tenant's own field definitions; undeclared keys are dropped.
    custom: dict = {}


class ContactCreate(ContactBase):
    pass


class ContactUpdate(ORMModel):
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None
    company_id: str | None = None
    emails: list[str] | None = None
    phones: list[str] | None = None
    social_links: dict[str, str] | None = None
    notes: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None
    custom: dict | None = None


class ContactOut(ContactBase):
    id: str
    created_at: datetime
    updated_at: datetime
    company: CompanyBrief | None = None
    owner: UserBrief | None = None
