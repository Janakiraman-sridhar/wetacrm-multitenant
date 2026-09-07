from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.schemas import ORMModel


class TenantOut(ORMModel):
    id: str
    name: str
    slug: str
    type: str
    status: str
    template_key: str
    plan: str
    timezone: str
    currency: str
    locale: str
    owner_user_id: str | None = None
    created_at: datetime
    suspended_at: datetime | None = None


class TenantDetailOut(TenantOut):
    user_count: int = 0
    settings: dict = {}


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    type: str = "company"
    template_key: str = "general_crm"
    slug: str | None = None
    owner_email: EmailStr
    owner_password: str | None = Field(default=None, min_length=8)
    owner_first_name: str = "Admin"
    owner_last_name: str = ""
    plan: str = "standard"
    timezone: str = "Asia/Kolkata"
    currency: str = "INR"


class TenantUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    timezone: str | None = None
    currency: str | None = None
    locale: str | None = None
    default_country_code: str | None = None


class ImpersonateIn(BaseModel):
    user_id: str | None = None  # defaults to the tenant's first Super Admin


class ImpersonateOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    tenant: TenantOut
    acting_as_email: str


class PlatformStatsOut(BaseModel):
    tenants_total: int
    tenants_active: int
    tenants_suspended: int
    users_total: int
    by_template: dict[str, int]
