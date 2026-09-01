from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel


class Setting(BaseModel):
    """Key/value application settings (company profile, branding, counters, ...)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class EmailTemplate(BaseModel):
    __tablename__ = "email_templates"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_html: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(500))


class Tag(BaseModel):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(20), default="#4F46E5")
