from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel, UserBrief


class ActivityCreate(ORMModel):
    entity_type: str
    entity_id: str
    type: str = "note"
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None


class ActivityOut(ORMModel):
    id: str
    type: str
    title: str
    body: str | None = None
    entity_type: str
    entity_id: str
    meta: dict
    created_at: datetime
    user: UserBrief | None = None


class AuditLogOut(ORMModel):
    id: str
    action: str
    entity_type: str
    entity_id: str | None = None
    changes: dict
    ip_address: str | None = None
    created_at: datetime
    user: UserBrief | None = None


class CommentCreate(ORMModel):
    entity_type: str
    entity_id: str
    body: str = Field(min_length=1)


class CommentOut(ORMModel):
    id: str
    body: str
    entity_type: str
    entity_id: str
    created_at: datetime
    user: UserBrief | None = None
