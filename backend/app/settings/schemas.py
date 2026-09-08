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

    #: What fires it, and whether it does. See `app/settings/workflows.py`.
    trigger: str | None = None
    enabled: bool = True
    config: dict = {}
    #: Denormalised from the trigger catalog so the settings screen can describe the
    #: workflow without a second request.
    trigger_label: str | None = None
    trigger_description: str | None = None
    trigger_kind: str | None = None
    audience: str | None = None
    locked: bool = False
    locked_reason: str = ""
    customer_facing: bool = False
    config_schema: dict = {}
    #: Sends recorded for this trigger, so the screen can say it is actually working.
    sent_count: int = 0
    last_sent_at: datetime | None = None


class EmailTemplateUpdate(ORMModel):
    subject: str | None = None
    body_html: str | None = None
    description: str | None = None
    trigger: str | None = None
    enabled: bool | None = None
    config: dict | None = None


class WorkflowTriggerOut(ORMModel):
    key: str
    label: str
    description: str
    kind: str
    audience: str
    merge_fields: list[str] = []
    locked: bool = False
    locked_reason: str = ""
    customer_facing: bool = False
    config_schema: dict = {}
    #: The template currently bound to it, if any.
    template_id: str | None = None
    template_name: str | None = None
    enabled: bool = False


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
