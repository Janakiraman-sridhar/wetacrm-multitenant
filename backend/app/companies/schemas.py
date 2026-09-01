from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel, UserBrief


class CompanyBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    industry: str | None = None
    website: str | None = None
    gst_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    notes: str | None = None
    tags: list[str] = []
    owner_id: str | None = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(ORMModel):
    name: str | None = None
    industry: str | None = None
    website: str | None = None
    gst_number: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None


class CompanyOut(CompanyBase):
    id: str
    created_at: datetime
    updated_at: datetime
    owner: UserBrief | None = None
