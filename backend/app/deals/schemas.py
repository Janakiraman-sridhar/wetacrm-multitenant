from datetime import date, datetime

from pydantic import Field

from app.core.schemas import CompanyBrief, ContactBrief, ORMModel, UserBrief


class StageOut(ORMModel):
    id: str
    name: str
    order: int
    probability: int
    is_won: bool
    is_lost: bool
    deal_count: int = 0


class StageCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    order: int = 0
    probability: int = Field(0, ge=0, le=100)


class ReorderStagesIn(ORMModel):
    stage_ids: list[str] = Field(min_length=1)


class StageUpdate(ORMModel):
    name: str | None = None
    order: int | None = None
    probability: int | None = Field(None, ge=0, le=100)


class DealBase(ORMModel):
    title: str = Field(min_length=1, max_length=255)
    value: float = 0
    currency: str = "INR"
    probability: int = Field(10, ge=0, le=100)
    expected_close_date: date | None = None
    stage_id: str | None = None
    company_id: str | None = None
    contact_id: str | None = None
    owner_id: str | None = None
    competitors: str | None = None
    notes: str | None = None


class DealCreate(DealBase):
    pass


class DealUpdate(ORMModel):
    title: str | None = None
    value: float | None = None
    currency: str | None = None
    probability: int | None = Field(None, ge=0, le=100)
    expected_close_date: date | None = None
    stage_id: str | None = None
    company_id: str | None = None
    contact_id: str | None = None
    owner_id: str | None = None
    competitors: str | None = None
    notes: str | None = None


class DealOut(DealBase):
    id: str
    status: str
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    stage: StageOut | None = None
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    owner: UserBrief | None = None


class MoveStageIn(ORMModel):
    stage_id: str


class PipelineColumn(ORMModel):
    stage: StageOut
    deals: list[DealOut]
    total_value: float
