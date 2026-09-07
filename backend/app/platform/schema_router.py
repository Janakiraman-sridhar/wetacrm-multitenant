"""Field configuration API.

`GET /schema/{module}` is read by every signed-in user — it is what the form and
table render from. The write endpoints are the field editor, and need
`settings:write`, because adding a field changes the workspace for everyone in it.
"""

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError, NotFoundError
from app.core.schemas import Message
from app.database.session import get_db
from app.platform.fields import FieldDef
from app.platform.schema_service import merged_schema, validate_new_field
from app.schema_registry import CUSTOMISABLE_MODULES, FIELD_TYPES, base_fields
from app.users.models import User

router = APIRouter(tags=["schema"])

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class FieldOption(BaseModel):
    value: str
    label: str


class FieldCreate(BaseModel):
    key: str = Field(min_length=2, max_length=42)
    label: str = Field(min_length=1, max_length=120)
    field_type: str = "text"
    options: list[FieldOption] = []
    required: bool = False
    section: str | None = None
    order: int = 999
    help_text: str | None = None
    placeholder: str | None = None
    default_value: str | None = None
    show_in_table: bool = False
    filterable: bool = False
    is_pii: bool = False


class FieldUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    options: list[FieldOption] | None = None
    required: bool | None = None
    section: str | None = None
    order: int | None = None
    help_text: str | None = None
    placeholder: str | None = None
    default_value: str | None = None
    is_active: bool | None = None
    show_in_table: bool | None = None
    filterable: bool | None = None
    is_pii: bool | None = None


@router.get("/schema/modules")
def customisable_modules(user: User = Depends(get_current_user)):
    """Which modules accept custom fields, and what types are available."""
    return {"modules": CUSTOMISABLE_MODULES, "field_types": FIELD_TYPES}


@router.get("/schema/{module}")
def module_schema(
    module: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """The merged field schema for a module, as this tenant has configured it."""
    return {"module": module, "fields": merged_schema(db, module)}


@router.post("/schema/{module}/fields")
def create_field(
    module: str,
    payload: FieldCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:write")),
):
    """Add a field to a module for this tenant only."""
    key = payload.key.strip().lower()
    if not KEY_PATTERN.match(key):
        raise AppError("Key must start with a letter and use only lowercase letters, numbers and underscores")
    validate_new_field(module, key, payload.field_type)

    if db.scalar(select(FieldDef).where(FieldDef.module == module, FieldDef.key == key)):
        raise AppError(f"A field with key '{key}' already exists on this module", 409)
    if payload.field_type in ("select", "multiselect") and not payload.options:
        raise AppError(f"A {payload.field_type} field needs at least one option")

    definition = FieldDef(
        module=module,
        key=key,
        label=payload.label,
        field_type=payload.field_type,
        options=[o.model_dump() for o in payload.options],
        required=payload.required,
        section=payload.section,
        order=payload.order,
        help_text=payload.help_text,
        placeholder=payload.placeholder,
        default_value=payload.default_value,
        is_custom=True,
        show_in_table=payload.show_in_table,
        filterable=payload.filterable,
        is_pii=payload.is_pii,
    )
    db.add(definition)
    db.flush()
    audit(db, user.id, "create", "field", definition.id, {"module": module, "key": key})
    db.commit()
    return {"module": module, "fields": merged_schema(db, module)}


@router.patch("/schema/{module}/fields/{key}")
def update_field(
    module: str,
    key: str,
    payload: FieldUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:write")),
):
    """Change a field — a custom one, or an override on a base one.

    Overriding a base field creates its row on first edit, so the table only holds
    the differences from the shipped defaults rather than a copy of everything.
    """
    if module not in CUSTOMISABLE_MODULES:
        raise NotFoundError("Module")

    definition = db.scalar(select(FieldDef).where(FieldDef.module == module, FieldDef.key == key))
    base = {f.key: f for f in base_fields(module)}.get(key)

    if definition is None:
        if base is None:
            raise NotFoundError("Field")
        definition = FieldDef(
            module=module, key=key, label=base.label, field_type=base.type,
            is_custom=False, order=0,
        )
        db.add(definition)
        db.flush()

    data = payload.model_dump(exclude_unset=True)
    if base and base.locked:
        if data.get("is_active") is False:
            raise AppError(f"{base.label} cannot be hidden", 400)
        if data.get("required") is False:
            raise AppError(f"{base.label} cannot be made optional", 400)

    changes = {}
    for field, value in data.items():
        if field == "options" and value is not None:
            value = [o if isinstance(o, dict) else o.model_dump() for o in value]
        if getattr(definition, field) != value:
            changes[field] = [getattr(definition, field), value]
            setattr(definition, field, value)
    if changes:
        audit(db, user.id, "update", "field", definition.id, {"module": module, "key": key, **changes})
    db.commit()
    return {"module": module, "fields": merged_schema(db, module)}


@router.delete("/schema/{module}/fields/{key}", response_model=Message)
def delete_field(
    module: str,
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:delete")),
):
    """Remove a custom field.

    The definition goes; the values stay in each record's `custom` JSON. That is
    deliberate — a field deleted by mistake can be recreated with the same key and
    the data reappears, and nothing rewrites every row of a large table.
    """
    definition = db.scalar(select(FieldDef).where(FieldDef.module == module, FieldDef.key == key))
    if definition is None:
        raise NotFoundError("Field")
    if not definition.is_custom:
        raise AppError("Built-in fields cannot be deleted — hide it instead", 400)

    db.delete(definition)
    audit(db, user.id, "delete", "field", definition.id, {"module": module, "key": key})
    db.commit()
    return {"detail": f"Field '{key}' deleted. Existing values are retained."}
