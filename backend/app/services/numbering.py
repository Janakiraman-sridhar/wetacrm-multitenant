from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.settings.models import Setting

PREFIXES = {"quotation": "QT", "invoice": "INV", "ticket": "TKT"}


def next_number(db: Session, kind: str) -> str:
    """Sequential document numbers like QT-2026-0042, backed by the settings counters.

    The prefix can be overridden per document type via the <kind>_template setting.
    """
    prefix = PREFIXES.get(kind, kind.upper())
    template_row = db.scalar(select(Setting).where(Setting.key == f"{kind}_template"))
    if template_row and (template_row.value or {}).get("number_prefix"):
        prefix = str(template_row.value["number_prefix"]).strip() or prefix

    row = db.scalar(select(Setting).where(Setting.key == "counters").with_for_update())
    if row is None:
        row = Setting(key="counters", value={})
        db.add(row)
        db.flush()
    counters = dict(row.value or {})
    counters[kind] = int(counters.get(kind, 0)) + 1
    row.value = counters
    db.flush()
    return f"{prefix}-{date.today().year}-{counters[kind]:04d}"
