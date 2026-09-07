from sqlalchemy import JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped


class Setting(TenantScoped, BaseModel):
    """Key/value application settings (company profile, branding, counters, ...)."""

    __tablename__ = "settings"

    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_settings_tenant_key"),)

    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class EmailTemplate(TenantScoped, BaseModel):
    __tablename__ = "email_templates"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_email_templates_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_html: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(500))


class Tag(TenantScoped, BaseModel):
    __tablename__ = "tags"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    color: Mapped[str] = mapped_column(String(20), default="#4F46E5")
