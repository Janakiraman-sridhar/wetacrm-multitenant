from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel

TASK_PRIORITIES = ["low", "medium", "high", "urgent"]
TASK_STATUSES = ["todo", "in_progress", "done", "cancelled"]


class Task(BaseModel):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(20), default="todo", index=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str | None] = mapped_column(String(50))  # optional link: lead|deal|company|...
    entity_id: Mapped[str | None] = mapped_column(String(32))

    assigned_to = relationship("User", foreign_keys=[assigned_to_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id], lazy="joined")


class Comment(BaseModel):
    __tablename__ = "comments"

    body: Mapped[str] = mapped_column(Text)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)

    user = relationship("User", lazy="joined")
