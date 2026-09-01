from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel, UserBrief


class TaskBase(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: str = "medium"
    status: str = "todo"
    due_date: datetime | None = None
    assigned_to_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(ORMModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    assigned_to_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None


class TaskOut(TaskBase):
    id: str
    created_at: datetime
    updated_at: datetime
    assigned_to: UserBrief | None = None
    created_by: UserBrief | None = None
