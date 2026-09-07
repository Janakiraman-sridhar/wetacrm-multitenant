from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel

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
