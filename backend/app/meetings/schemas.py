from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel, UserBrief


class MeetingBase(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    agenda: str | None = None
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = None
    participant_ids: list[str] = []
    external_participants: list[str] = []
    notes: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class MeetingCreate(MeetingBase):
    pass


class MeetingUpdate(ORMModel):
    title: str | None = None
    agenda: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    participant_ids: list[str] | None = None
    external_participants: list[str] | None = None
    notes: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class MeetingOut(MeetingBase):
    id: str
    created_at: datetime
    organizer: UserBrief | None = None


class EventBase(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    type: str = "reminder"
    starts_at: datetime
    ends_at: datetime | None = None
    notes: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class EventCreate(EventBase):
    user_id: str | None = None  # defaults to current user


class EventUpdate(ORMModel):
    title: str | None = None
    type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None


class EventOut(EventBase):
    id: str
    created_at: datetime
    user: UserBrief | None = None


class CalendarItem(ORMModel):
    """Unified calendar feed item (meetings + events)."""

    id: str
    kind: str  # "meeting" | "event"
    title: str
    type: str
    starts_at: datetime
    ends_at: datetime | None = None
    location: str | None = None
