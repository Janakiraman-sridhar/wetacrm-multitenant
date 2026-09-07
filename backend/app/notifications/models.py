from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import BaseModel, TenantScoped


class Notification(TenantScoped, BaseModel):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # lead_assigned|deal_updated|task_assigned|meeting_reminder|mention|system
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))  # frontend route, e.g. /leads/<id>
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
