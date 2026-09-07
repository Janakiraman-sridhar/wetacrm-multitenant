from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from app.core.permissions import has_permission
from app.database.session import get_db
from app.filtering import apply_filters_for
from app.platform.schema_service import active_custom_fields
from app.io.registry import SPECS
from app.io.spec import IOColumn, ImportOptions, build_csv, build_template_csv, parse_csv
from app.users.models import User

router = APIRouter(prefix="/io", tags=["import-export"])

MAX_IMPORT_BYTES = 5 * 1024 * 1024


def _spec(entity: str):
    spec = SPECS.get(entity)
    if not spec:
        raise NotFoundError("Import/export entity")
    return spec


def _require(user: User, module: str, action: str) -> None:
    perms = user.role.permissions if user.role else []
    if not has_permission(perms, f"{module}:{action}"):
        raise PermissionDeniedError()


def _csv_response(text: str, filename: str) -> Response:
    # BOM so Excel opens UTF-8 correctly
    return Response(
        content="﻿" + text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/entities")
def list_entities(user: User = Depends(get_current_user)):
    """Which entities the current user can import/export."""
    perms = user.role.permissions if user.role else []
    return [
        {"entity": key, "label": spec.label, "module": spec.module,
         "can_read": has_permission(perms, f"{spec.module}:read"),
         "can_write": has_permission(perms, f"{spec.module}:write")}
        for key, spec in SPECS.items()
    ]


@router.get("/{entity}/export")
def export_entity(
    entity: str,
    filters: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    spec = _spec(entity)
    _require(user, spec.module, "read")
    stmt = apply_filters_for(db, spec.base_select(), spec.filter_key, filters)
    objs = db.scalars(stmt).all()
    rows = spec.expand(objs) if spec.expand else objs
    # A tenant's own fields belong in their export as much as the built-in ones.
    extra = custom_columns_for(db, spec.filter_key)
    return _csv_response(build_csv(spec, rows, extra_columns=extra), f"{spec.filename}.csv")


@router.get("/{entity}/template")
def template_entity(entity: str, user: User = Depends(get_current_user)):
    spec = _spec(entity)
    _require(user, spec.module, "read")
    return _csv_response(build_template_csv(spec), f"{spec.filename}_import_template.csv")


@router.post("/{entity}/import")
async def import_entity(
    entity: str,
    file: UploadFile,
    send_emails: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    spec = _spec(entity)
    _require(user, spec.module, "write")
    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:
        raise AppError("File exceeds the 5 MB import limit", 413)
    if not raw.strip():
        raise AppError("The uploaded file is empty", 400)
    rows = parse_csv(raw, spec)
    if not rows:
        raise AppError("No data rows found — the file needs a header row and at least one record", 400)
    result = spec.import_rows(db, user, rows, ImportOptions(send_emails=send_emails))
    return result.as_dict()


def custom_columns_for(db, module: str) -> list[IOColumn]:
    """Export columns for this tenant's custom fields, if the module has any."""
    from app.schema_registry import CUSTOMISABLE_MODULES

    if module not in CUSTOMISABLE_MODULES:
        return []
    columns = []
    for definition in active_custom_fields(db, module):
        key = definition.key

        def read(obj, _key=key):
            values = getattr(obj, "custom", None) or {}
            value = values.get(_key)
            if isinstance(value, list):
                return ", ".join(str(v) for v in value)
            return "" if value is None else value

        columns.append(IOColumn(key=f"custom.{key}", label=definition.label, value=read))
    return columns
