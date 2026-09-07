from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped

TENANT_TYPES = ["company", "individual"]
TENANT_STATUSES = ["provisioning", "trial", "active", "suspended", "deleted"]


class Tenant(BaseModel):
    """One client account — an agency or an individual agent — with isolated data.

    Every business row in the database carries this row's id. See
    `app.core.tenancy` for how that isolation is enforced.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="company")
    status: Mapped[str] = mapped_column(String(20), default="provisioning", index=True)
    template_key: Mapped[str] = mapped_column(String(50), default="general_crm")
    plan: Mapped[str] = mapped_column(String(50), default="standard")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    locale: Mapped[str] = mapped_column(String(10), default="en-IN")
    default_country_code: Mapped[str] = mapped_column(String(5), default="+91")

    # Wrapped per-tenant data-encryption key for PII (Phase 3). Generated at
    # provisioning; encrypted with the platform master key, never stored in clear.
    dek_encrypted: Mapped[str | None] = mapped_column(Text)

    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    owner_user_id: Mapped[str | None] = mapped_column(String(32))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def is_usable(self) -> bool:
        return self.status in ("active", "trial")


class PlatformAuditLog(BaseModel):
    """Audit trail for platform-level actions, kept separate from tenant audit logs.

    Impersonation in particular is recorded here against the *real* platform admin,
    so actions taken while impersonating are always attributable.
    """

    __tablename__ = "platform_audit_logs"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50), index=True)
    tenant_id_ref: Mapped[str | None] = mapped_column(String(32), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(50))


class CrmTemplate(BaseModel):
    """A stored CRM template — the recipe a tenant is provisioned from.

    System templates are loaded from `app/platform/templates/*.json` on startup and
    refreshed when their version increases; a platform admin can clone one to make a
    custom template. Config is held as a whole JSON document rather than normalised
    tables because it is read as a unit, versioned as a unit, and its shape will keep
    growing as later phases add sections.
    """

    __tablename__ = "crm_templates"

    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class TenantModule(TenantScoped, BaseModel):
    """Which modules a tenant has, what they are called, and in what order.

    Copied from the template at provisioning and editable afterwards, which is what
    makes "Contacts" appear as "Customers" for an insurance tenant without any
    branching in the module's own code.
    """

    __tablename__ = "tenant_modules"

    __table_args__ = (UniqueConstraint("tenant_id", "module_key", name="uq_tenant_modules_tenant_key"),)

    module_key: Mapped[str] = mapped_column(String(50), index=True)
    label: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
