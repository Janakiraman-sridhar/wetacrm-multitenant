from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped


class Setting(TenantScoped, BaseModel):
    """Key/value application settings (company profile, branding, counters, ...)."""

    __tablename__ = "settings"

    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_settings_tenant_key"),)

    key: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class EmailTemplate(TenantScoped, BaseModel):
    """A template, and the moment it fires.

    The trigger lives here rather than at the call site because that is what makes
    the wording and the workflow one thing a tenant configures. See
    `app/settings/workflows.py` for the catalog of triggers and why.
    """

    __tablename__ = "email_templates"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_email_templates_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_html: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(500))

    #: Which event sends it. None means the template exists but nothing fires it.
    trigger: Mapped[str | None] = mapped_column(String(50), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    #: Trigger-specific settings, e.g. how many days before expiry to send.
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class SentEmail(TenantScoped, BaseModel):
    """One row per automated email, so a daily job cannot send the same one twice.

    A renewal reminder job that runs every day would otherwise email the customer
    every day for the whole window. The dedupe key carries what makes the send
    unique — usually the policy and the threshold it crossed.

    It doubles as the answer to "did we email this customer?", which an agency asks
    far more often than it asks anything about job scheduling.
    """

    __tablename__ = "sent_emails"

    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_sent_emails_tenant_key"),
    )

    trigger: Mapped[str] = mapped_column(String(50), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), index=True)
    recipient: Mapped[str] = mapped_column(String(255), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(32), index=True)
    subject: Mapped[str | None] = mapped_column(String(255))
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


class Tag(TenantScoped, BaseModel):
    __tablename__ = "tags"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    color: Mapped[str] = mapped_column(String(20), default="#4F46E5")
