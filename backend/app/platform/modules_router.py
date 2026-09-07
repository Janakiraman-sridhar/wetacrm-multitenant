"""The tenant-facing view of its own module configuration.

`GET /api/v1/modules` is what the frontend sidebar is built from: which modules this
workspace has, what they are called here, and in what order. It is the reason
renaming "Contacts" to "Customers" for one client needs no code change.

The write endpoints are for a tenant admin adjusting their own workspace; a platform
admin does the same thing for any tenant through `/platform/tenants/{id}/modules`.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError, NotFoundError
from app.core.schemas import ORMModel
from app.database.session import get_db
from app.platform.catalog import MODULES_BY_KEY
from app.platform.models import TenantModule
from app.users.models import User

router = APIRouter(tags=["modules"])


class ModuleOut(ORMModel):
    id: str
    module_key: str
    label: str
    enabled: bool
    order: int
    # From the catalog, so the frontend does not need its own copy.
    route: str = ""
    icon: str = ""
    permission: str | None = None
    locked: bool = False


class ModuleUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    order: int | None = None


def _decorate(row: TenantModule) -> dict:
    definition = MODULES_BY_KEY.get(row.module_key)
    data = {
        "id": row.id,
        "module_key": row.module_key,
        "label": row.label,
        "enabled": row.enabled,
        "order": row.order,
        "route": definition.route if definition else "",
        "icon": definition.icon if definition else "",
        "permission": definition.permission if definition else None,
        "locked": definition.locked if definition else False,
    }
    return data


def list_tenant_modules(db: Session, enabled_only: bool = False) -> list[dict]:
    stmt = select(TenantModule).order_by(TenantModule.order)
    if enabled_only:
        stmt = stmt.where(TenantModule.enabled.is_(True))
    return [_decorate(row) for row in db.scalars(stmt).all()]


@router.get("/modules", response_model=list[ModuleOut])
def my_modules(
    enabled_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The current workspace's modules. Drives the sidebar, so every signed-in user reads it."""
    return list_tenant_modules(db, enabled_only=enabled_only)


@router.patch("/modules/{module_id}", response_model=ModuleOut)
def update_module(
    module_id: str,
    payload: ModuleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:write")),
):
    row = db.get(TenantModule, module_id)
    if row is None:
        raise NotFoundError("Module")

    definition = MODULES_BY_KEY.get(row.module_key)
    data = payload.model_dump(exclude_unset=True)
    if definition and definition.locked and data.get("enabled") is False:
        raise AppError(f"{definition.label} cannot be switched off", 400)

    changes = {}
    for field, value in data.items():
        if getattr(row, field) != value:
            changes[field] = [getattr(row, field), value]
            setattr(row, field, value)
    if changes:
        audit(db, user.id, "update", "module", row.id, changes)
    db.commit()
    return _decorate(row)
