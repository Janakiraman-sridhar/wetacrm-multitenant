import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


def new_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    """Common columns for every business table.

    UUIDs are stored as 32-char hex strings so the schema is portable between
    PostgreSQL (production) and SQLite (zero-setup local dev).
    """

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TenantScoped:
    """Marks a model as belonging to exactly one tenant.

    Inheriting this is the *only* thing a model has to do to become tenant-safe:
    `app.core.tenancy` stamps `tenant_id` on insert and filters every SELECT that
    touches the model. Routers must never filter by `tenant_id` themselves — a
    hand-written filter that gets forgotten is a cross-tenant data leak, which is
    exactly what the central enforcement exists to prevent.

    `tenant_id` is nullable at the column level because platform-level rows
    (a Super Admin user, and their role-less account) legitimately have none.
    For every business table it is populated on insert and never null in practice.
    """

    @declared_attr
    def tenant_id(cls) -> Mapped[str | None]:
        return mapped_column(
            String(32),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            index=True,
            nullable=True,
        )
