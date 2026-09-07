from datetime import date, datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ORMModel, UserBrief


class ProjectTaskIn(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    is_milestone: bool = False
    status: str = "todo"
    due_date: date | None = None
    assigned_to_id: str | None = None


class ProjectTaskOut(ProjectTaskIn):
    id: str
    position: int
    assigned_to: UserBrief | None = None


class ProjectBase(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    company_id: str | None = None
    status: str = "planned"
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = None
    owner_id: str | None = None
    team_ids: list[str] = []
    #: Values for this tenant's custom fields. Validated on flush against the
    #: tenant's own field definitions; undeclared keys are dropped.
    custom: dict = {}


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ORMModel):
    name: str | None = None
    description: str | None = None
    company_id: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = None
    owner_id: str | None = None
    team_ids: list[str] | None = None
    custom: dict | None = None


class ProjectOut(ProjectBase):
    id: str
    created_at: datetime
    updated_at: datetime
    company: CompanyBrief | None = None
    owner: UserBrief | None = None
    tasks: list[ProjectTaskOut] = []


class ProjectTaskUpdate(ORMModel):
    title: str | None = None
    is_milestone: bool | None = None
    status: str | None = None
    due_date: date | None = None
    assigned_to_id: str | None = None
    position: int | None = None
