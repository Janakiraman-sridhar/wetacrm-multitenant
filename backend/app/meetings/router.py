from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.core.crud import apply_updates, get_or_404
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, page_params, paginate
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.meetings.models import EVENT_TYPES, CalendarEvent, Meeting
from app.meetings.schemas import (
    CalendarItem, EventCreate, EventOut, EventUpdate, MeetingCreate, MeetingOut, MeetingUpdate,
)
from app.notifications.service import notify
from app.users.models import User

router = APIRouter(tags=["calendar"])


# --- Meetings ---

@router.get("/meetings", response_model=Page[MeetingOut], dependencies=[Depends(require_perm("calendar:read"))])
def list_meetings(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Meeting).order_by(Meeting.starts_at.desc())
    if params.search:
        stmt = stmt.where(Meeting.title.ilike(f"%{params.search}%"))
    return paginate(db, stmt, params)


@router.post("/meetings", response_model=MeetingOut)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar:write"))):
    meeting = Meeting(**payload.model_dump(), organizer_id=user.id)
    db.add(meeting)
    db.flush()
    if meeting.entity_type and meeting.entity_id:
        log_activity(db, meeting.entity_type, meeting.entity_id, "meeting",
                     f"Meeting scheduled: {meeting.title}", user_id=user.id)
    audit(db, user.id, "create", "meeting", meeting.id, {"title": meeting.title})
    for uid in set(meeting.participant_ids or []) - {user.id}:
        notify(db, uid, "meeting_invite", f"Meeting: {meeting.title}",
               f"{meeting.starts_at:%d %b %Y %H:%M} — organized by {user.full_name}", "/calendar")
    db.commit()
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(meeting_id: str, payload: MeetingUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar:write"))):
    meeting = get_or_404(db, Meeting, meeting_id, "Meeting")
    changes = apply_updates(meeting, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, user.id, "update", "meeting", meeting.id, changes)
    db.commit()
    return meeting


@router.delete("/meetings/{meeting_id}", response_model=Message)
def delete_meeting(meeting_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar:delete"))):
    meeting = get_or_404(db, Meeting, meeting_id, "Meeting")
    db.delete(meeting)
    audit(db, user.id, "delete", "meeting", meeting_id, {"title": meeting.title})
    db.commit()
    return {"detail": "Meeting deleted"}


# --- Calendar events ---

@router.get("/calendar/events", response_model=Page[EventOut], dependencies=[Depends(require_perm("calendar:read"))])
def list_events(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(CalendarEvent).order_by(CalendarEvent.starts_at.desc())
    return paginate(db, stmt, params)


@router.post("/calendar/events", response_model=EventOut)
def create_event(payload: EventCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar:write"))):
    if payload.type not in EVENT_TYPES:
        raise AppError(f"Invalid event type. Expected one of {EVENT_TYPES}")
    data = payload.model_dump()
    data["user_id"] = data.get("user_id") or user.id
    event = CalendarEvent(**data)
    db.add(event)
    db.commit()
    return event


@router.patch("/calendar/events/{event_id}", response_model=EventOut)
def update_event(event_id: str, payload: EventUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("calendar:write"))):
    event = get_or_404(db, CalendarEvent, event_id, "Event")
    data = payload.model_dump(exclude_unset=True)
    if data.get("type") and data["type"] not in EVENT_TYPES:
        raise AppError(f"Invalid event type. Expected one of {EVENT_TYPES}")
    apply_updates(event, data)
    db.commit()
    return event


@router.delete("/calendar/events/{event_id}", response_model=Message)
def delete_event(event_id: str, db: Session = Depends(get_db), _: User = Depends(require_perm("calendar:delete"))):
    event = get_or_404(db, CalendarEvent, event_id, "Event")
    db.delete(event)
    db.commit()
    return {"detail": "Event deleted"}


@router.get("/calendar", response_model=list[CalendarItem], dependencies=[Depends(require_perm("calendar:read"))])
def calendar_feed(
    start: datetime,
    end: datetime,
    mine_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Unified feed of meetings + events for the calendar view."""
    meetings_stmt = select(Meeting).where(and_(Meeting.starts_at >= start, Meeting.starts_at <= end))
    events_stmt = select(CalendarEvent).where(and_(CalendarEvent.starts_at >= start, CalendarEvent.starts_at <= end))
    if mine_only:
        events_stmt = events_stmt.where(CalendarEvent.user_id == user.id)
    items: list[dict] = []
    for m in db.scalars(meetings_stmt).all():
        if mine_only and user.id != m.organizer_id and user.id not in (m.participant_ids or []):
            continue
        items.append({"id": m.id, "kind": "meeting", "title": m.title, "type": "meeting",
                      "starts_at": m.starts_at, "ends_at": m.ends_at, "location": m.location})
    for e in db.scalars(events_stmt).all():
        items.append({"id": e.id, "kind": "event", "title": e.title, "type": e.type,
                      "starts_at": e.starts_at, "ends_at": e.ends_at, "location": None})
    items.sort(key=lambda i: i["starts_at"])
    return items
