from datetime import datetime

from pydantic import Field

from app.core.schemas import ORMModel


class SettingOut(ORMModel):
    key: str
    value: dict


class SettingUpdate(ORMModel):
    value: dict


class TemplateVariable(ORMModel):
    key: str
    label: str
    sample: str


class EmailTemplateOut(ORMModel):
    id: str
    name: str
    subject: str
    body_html: str
    description: str | None = None
    updated_at: datetime
    variables: list[TemplateVariable] = []


class EmailTemplateUpdate(ORMModel):
    subject: str | None = None
    body_html: str | None = None
    description: str | None = None


class TagOut(ORMModel):
    id: str
    name: str
    color: str


class TagCreate(ORMModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = "#4F46E5"


class TagUpdate(ORMModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = None
