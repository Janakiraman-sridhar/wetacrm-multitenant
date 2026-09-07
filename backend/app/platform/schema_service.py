"""The merged field schema for a module, and validation of the values it describes.

`GET /api/v1/schema/{module}` is what the frontend form and table are built from:
the product's base fields with this tenant's relabels and hides applied, plus any
fields the tenant added. One request, one source of truth, so a client can be given
a field without a deploy.

Validation lives here too, and is enforced through a session hook rather than in
each router — the same reasoning as tenant isolation. A check that every router has
to remember is a check that will eventually be forgotten.
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.platform.fields import FieldDef
from app.schema_registry import (
    CUSTOMISABLE_MODULES, FIELD_TYPES, BaseField, base_fields, base_field_keys,
)

log = logging.getLogger("weta.schema")

MAX_TEXT = 5000


def merged_schema(db: Session, module: str) -> list[dict]:
    """Base fields + tenant overrides + tenant custom fields, in display order."""
    if module not in CUSTOMISABLE_MODULES:
        raise AppError(f"Module '{module}' does not support custom fields", 404)

    defs = {
        (d.module, d.key): d
        for d in db.scalars(select(FieldDef).where(FieldDef.module == module)).all()
    }

    out: list[dict] = []
    for index, base in enumerate(base_fields(module)):
        override = defs.get((module, base.key))
        out.append(_render_base(base, override, index))

    for definition in defs.values():
        if definition.is_custom:
            out.append(_render_custom(definition))

    out.sort(key=lambda f: (f["order"], f["label"]))
    return out


def _render_base(base: BaseField, override: FieldDef | None, index: int) -> dict:
    return {
        "key": base.key,
        "label": override.label if override and override.label else base.label,
        "type": base.type,               # a base field's type is fixed by its column
        "required": base.required or bool(override and override.required),
        "options": (override.options if override and override.options else base.options) or [],
        "section": override.section if override else None,
        "order": override.order if override and override.order else index,
        "help_text": override.help_text if override else None,
        "placeholder": override.placeholder if override else None,
        "is_custom": False,
        "locked": base.locked,
        # A locked field cannot be hidden however the override is set.
        "is_active": True if base.locked else (override.is_active if override else True),
        "show_in_table": bool(override.show_in_table) if override else False,
        "filterable": bool(override.filterable) if override else False,
        "is_pii": bool(override.is_pii) if override else False,
    }


def _render_custom(definition: FieldDef) -> dict:
    return {
        "key": definition.key,
        "label": definition.label,
        "type": definition.field_type,
        "required": definition.required,
        "options": definition.options or [],
        "section": definition.section,
        "order": definition.order or 999,
        "help_text": definition.help_text,
        "placeholder": definition.placeholder,
        "default_value": definition.default_value,
        "is_custom": True,
        "locked": False,
        "is_active": definition.is_active,
        "show_in_table": definition.show_in_table,
        "filterable": definition.filterable,
        "is_pii": definition.is_pii,
        "id": definition.id,
    }


def active_custom_fields(db: Session, module: str) -> list[FieldDef]:
    return list(
        db.scalars(
            select(FieldDef).where(
                FieldDef.module == module,
                FieldDef.is_custom.is_(True),
                FieldDef.is_active.is_(True),
            )
        ).all()
    )


# --- validation ---------------------------------------------------------------

def coerce_value(definition: FieldDef, value: Any) -> Any:
    """Coerce a submitted value to the field's type, or raise a user-facing error.

    Stored as JSON, so dates and decimals become strings and floats — the point is
    to reject nonsense at the boundary, not to preserve Python types.
    """
    label = definition.label
    if value is None or value == "":
        return None

    kind = definition.field_type
    try:
        if kind in ("text", "textarea", "email", "phone", "url"):
            text = str(value)
            if len(text) > MAX_TEXT:
                raise AppError(f"{label} is too long (max {MAX_TEXT} characters)")
            if kind == "email" and "@" not in text:
                raise AppError(f"{label} must be an email address")
            return text

        if kind == "number":
            return int(value)

        if kind in ("decimal", "currency"):
            return float(Decimal(str(value)))

        if kind == "checkbox":
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes", "on")

        if kind == "date":
            return date.fromisoformat(str(value)[:10]).isoformat()

        if kind == "datetime":
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()

        if kind == "select":
            allowed = {str(o.get("value")) for o in (definition.options or [])}
            text = str(value)
            if allowed and text not in allowed:
                raise AppError(f"{label} must be one of: {', '.join(sorted(allowed))}")
            return text

        if kind == "multiselect":
            if not isinstance(value, (list, tuple)):
                raise AppError(f"{label} must be a list")
            allowed = {str(o.get("value")) for o in (definition.options or [])}
            picked = [str(v) for v in value]
            if allowed:
                unknown = [v for v in picked if v not in allowed]
                if unknown:
                    raise AppError(f"{label} has invalid options: {', '.join(unknown)}")
            return picked
    except AppError:
        raise
    except (ValueError, TypeError, InvalidOperation):
        raise AppError(f"{label} is not a valid {kind}")

    return value


def validate_custom(db: Session, module: str, values: dict | None) -> dict:
    """Coerce and check a `custom` payload against this tenant's field definitions.

    Unknown keys are dropped rather than rejected: a stale form should not block a
    save, and silently storing values nobody declared would be worse.
    """
    definitions = {d.key: d for d in active_custom_fields(db, module)}
    submitted = values or {}
    cleaned: dict[str, Any] = {}

    for key, raw in submitted.items():
        definition = definitions.get(key)
        if definition is None:
            continue
        cleaned[key] = coerce_value(definition, raw)

    for key, definition in definitions.items():
        if definition.required and cleaned.get(key) in (None, "", []):
            raise AppError(f"{definition.label} is required")

    return cleaned


# --- field definition management ----------------------------------------------

RESERVED_KEYS = {"id", "created_at", "updated_at", "tenant_id", "custom"}


def validate_new_field(module: str, key: str, field_type: str) -> None:
    if module not in CUSTOMISABLE_MODULES:
        raise AppError(f"Module '{module}' does not support custom fields", 404)
    if field_type not in FIELD_TYPES:
        raise AppError(f"Unknown field type '{field_type}'")
    if key in RESERVED_KEYS:
        raise AppError(f"'{key}' is reserved")
    if key in base_field_keys(module):
        raise AppError(f"'{key}' is already a built-in field on this module")


# --- enforcement --------------------------------------------------------------

def _module_for_instance(obj) -> str | None:
    from app.schema_registry import CUSTOMISABLE_MODELS

    for module, model in CUSTOMISABLE_MODELS.items():
        if type(obj) is model:
            return module
    return None


def register_custom_field_validation() -> None:
    """Validate `custom` payloads on flush, for every module, once.

    Doing this in a session hook rather than in each router follows the same
    reasoning as tenant isolation: a check each of twenty routers has to remember
    is a check that will eventually be missed. `AppError` raised here surfaces as a
    normal 400 because the router's `db.commit()` is inside the request.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session as SessionClass

    @event.listens_for(SessionClass, "before_flush")
    def _validate_custom_on_flush(session, flush_context, instances):
        pending = [*session.new, *session.dirty]
        if not pending:
            return

        cache: dict[str, dict] = {}
        for obj in pending:
            if not hasattr(obj, "custom"):
                continue
            module = _module_for_instance(obj)
            if module is None:
                continue
            if module not in cache:
                cache[module] = {d.key: d for d in active_custom_fields(session, module)}

            definitions = cache[module]
            values = getattr(obj, "custom", None) or {}
            if not isinstance(values, dict):
                raise AppError("Custom field values must be an object")

            cleaned = {}
            for key, raw in values.items():
                definition = definitions.get(key)
                if definition is None:
                    continue  # dropped: a stale form should not block a save
                cleaned[key] = coerce_value(definition, raw)
            for key, definition in definitions.items():
                if definition.required and cleaned.get(key) in (None, "", []):
                    raise AppError(f"{definition.label} is required")
            if cleaned != values:
                obj.custom = cleaned
