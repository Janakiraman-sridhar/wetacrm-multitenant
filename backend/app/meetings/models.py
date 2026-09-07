from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped

EVENT_TYPES = ["meeting", "call", "follow_up", "reminder"]


class Meeting(TenantScoped, BaseModel):
    __tablename__ = "meetings"

    title: Mapped[str] = mapped_column(String(255))
    agenda: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String(255))  # room or meet link
    organizer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    participant_ids: Mapped[list] = mapped_column(JSON, default=list)   # internal user ids
    external_participants: Mapped[list] = mapped_column(JSON, default=list)  # emails
    notes: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(32))

    organizer = relationship("User", lazy="joined")


class CalendarEvent(TenantScoped, BaseModel):
    """Lightweight calendar items (calls, follow-ups, reminders).

    Meetings surface on the calendar too; the calendar API merges both.
    """

    __tablename__ = "calendar_events"

    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(20), default="reminder", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(32))

    user = relationship("User", lazy="joined")
