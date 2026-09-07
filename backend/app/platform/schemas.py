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


class TenantUserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str | None = None
    is_active: bool = True
    last_login_at: datetime | None = None
    is_owner: bool = False


class TenantDetailOut(TenantOut):
    user_count: int = 0
    settings: dict = {}
    owner_email: str | None = None
    owner_name: str | None = None
    module_count: int = 0
    enabled_module_count: int = 0
    #: Row counts for the modules this workspace actually has.
    record_counts: dict[str, int] = {}
    users: list[TenantUserOut] = []


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


class PlatformStatsOut(BaseModel):
    tenants_total: int
    tenants_active: int
    tenants_suspended: int
    users_total: int
    by_template: dict[str, int]


class TemplateOut(ORMModel):
    id: str
    key: str
    name: str
    description: str | None = None
    version: int
    is_system: bool
    module_count: int = 0
    enabled_module_count: int = 0
    role_count: int = 0
    stage_count: int = 0


class TemplateDetailOut(TemplateOut):
    config: dict = {}


class TemplateClone(BaseModel):
    key: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None


class TemplateCreate(TemplateClone):
    """A new template always starts from an existing one.

    A template with no roles and no pipeline stages would provision a workspace whose
    owner has no Super Admin role to be given — broken in a way nobody would notice
    until they tried to sign in. So "new" means "copy of a working one, yours to
    change", and the base is explicit rather than assumed.
    """

    base_key: str = "general_crm"


class TenantModuleUpdate(BaseModel):
    module_key: str
    label: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    order: int | None = None


class TemplateUpdate(BaseModel):
    """Edit a custom template.

    Only the sections a platform admin realistically changes — modules and their
    labels, pipeline stages, lead sources, tags. Roles and settings are left to the
    JSON so a mis-edit cannot lock a workspace out of its own permissions.
    """

    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    modules: list[dict] | None = None
    stages: list[dict] | None = None
    lead_sources: list[str] | None = None
    tags: list[dict] | None = None
    settings: dict | None = None
