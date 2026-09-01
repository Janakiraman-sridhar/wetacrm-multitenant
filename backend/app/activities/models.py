from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel

ACTIVITY_TYPES = ["email", "call", "meeting", "note", "status_change", "assignment", "system"]


class Activity(BaseModel):
    """Timeline entry attached to any entity (lead, deal, company, ...)."""

    __tablename__ = "activities"

    type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    user = relationship("User", lazy="joined")


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))  # create|update|delete|login|...
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(32), index=True)
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(50))

    user = relationship("User", lazy="joined")
