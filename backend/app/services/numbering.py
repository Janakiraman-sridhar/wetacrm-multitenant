from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.settings.models import Setting

PREFIXES = {"quotation": "QT", "invoice": "INV", "ticket": "TKT"}


def next_number(db: Session, kind: str) -> str:
    """Sequential document numbers like QT-2026-0042, backed by the settings counters."""
    row = db.scalar(select(Setting).where(Setting.key == "counters").with_for_update())
    if row is None:
        row = Setting(key="counters", value={})
        db.add(row)
        db.flush()
    counters = dict(row.value or {})
    counters[kind] = int(counters.get(kind, 0)) + 1
    row.value = counters
    db.flush()
    return f"{PREFIXES.get(kind, kind.upper())}-{date.today().year}-{counters[kind]:04d}"
