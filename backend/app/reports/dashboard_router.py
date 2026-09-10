"""Which cards a workspace's dashboard is built from.

`GET /api/v1/dashboard-widgets` is to the dashboard what `GET /modules` is to the
sidebar: the page renders the list it is given rather than a sequence written into
the component. That is what makes a new vertical a template decision instead of
another `if` in `Dashboard.tsx`.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError
from app.core.schemas import Message
from app.database.session import get_db
from app.platform.models import TenantModule
from app.reports import widgets
from app.reports.widgets import DASHBOARD_SETTING
from app.settings.models import Setting
from app.users.models import User

router = APIRouter(tags=["dashboard"])


class WidgetIn(BaseModel):
    key: str
    enabled: bool = True
    order: int | None = None


def _enabled_modules(db: Session) -> set[str]:
    return {
        row.module_key
        for row in db.scalars(select(TenantModule).where(TenantModule.enabled.is_(True))).all()
    }


def _stored(db: Session) -> list[dict] | None:
    """This workspace's saved layout, whichever shape it was written in.

    The first version stored a bare list; it is now an object, because
    `SettingOut.value` is typed `dict` and a list breaks `GET /settings` for every
    other row. A workspace whose layout was saved in between holds the old shape,
    and a reader that knows only the new one crashes the whole dashboard with an
    AttributeError. Both are read; the next save writes the current shape.
    """
    row = db.scalar(select(Setting).where(Setting.key == DASHBOARD_SETTING))
    if row is None:
        return None
    if isinstance(row.value, list):
        return row.value
    stored = (row.value or {}).get(widgets.DASHBOARD_KEY)
    return stored if isinstance(stored, list) else None


@router.get("/dashboard-widgets")
def my_dashboard(
    all_widgets: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """This workspace's dashboard, in order.

    `all_widgets=true` includes the ones switched off, which is what the editor
    needs — everyone else wants only what is on screen.
    """
    resolved = widgets.resolve(_stored(db), _enabled_modules(db), selective=False)
    return resolved if all_widgets else [w for w in resolved if w["enabled"]]


@router.put("/dashboard-widgets", response_model=Message)
def save_dashboard(
    payload: list[WidgetIn],
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:write")),
):
    """Replace the layout.

    Stored complete, in the order given, so a later read never has to guess: a
    partial save would leave the unnamed widgets to a default that changes the day
    a new card ships.
    """
    known = set(widgets.WIDGETS_BY_KEY)
    unknown = [w.key for w in payload if w.key not in known]
    if unknown:
        raise AppError(f"Not a dashboard card: {', '.join(sorted(unknown))}", 400)

    stored = [
        {"key": w.key, "enabled": True if widgets.WIDGETS_BY_KEY[w.key].locked else w.enabled,
         "order": index + 1}
        for index, w in enumerate(payload)
    ]
    # Anything the caller left out keeps whatever it had, so a stale editor cannot
    # silently switch off a card it had never heard of.
    named = {w["key"] for w in stored}
    for previous in _stored(db) or []:
        if previous.get("key") in known and previous["key"] not in named:
            stored.append({**previous, "order": len(stored) + 1})

    row = db.scalar(select(Setting).where(Setting.key == DASHBOARD_SETTING))
    if row is None:
        db.add(Setting(key=DASHBOARD_SETTING, value={widgets.DASHBOARD_KEY: stored}))
    else:
        # A row still in the old bare-list shape is normalised by this write.
        existing = row.value if isinstance(row.value, dict) else {}
        row.value = {**existing, widgets.DASHBOARD_KEY: stored}
    audit(db, user.id, "update", "setting", DASHBOARD_SETTING,
          {"enabled": [w["key"] for w in stored if w["enabled"]]})
    db.commit()
    return {"detail": "Dashboard updated"}


@router.get("/dashboard-widgets/catalog")
def catalog(user: User = Depends(get_current_user)):
    """Every card that exists, whatever this workspace has switched on.

    The template editor in the platform console needs this: it is choosing for a
    workspace that does not exist yet, so it cannot ask one what its modules are.
    """
    return [
        {
            "key": w.key, "label": w.label, "description": w.description,
            "order": w.order, "requires": w.requires, "width": w.width,
            "locked": w.locked,
        }
        for w in widgets.WIDGET_CATALOG
    ]
