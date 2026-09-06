"""Generic CSV import/export engine.

An `IOSpec` describes, per entity, how to serialize its rows to CSV, what the
importable columns are (for the sample template), and how to turn CSV rows back
into records. The registry (registry.py) defines one spec per module; the router
exposes /io/<entity>/export, /template and /import over them.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.users.models import User


@dataclass
class IOColumn:
    key: str                       # internal key used by importer row dicts
    label: str                     # CSV header shown to the user
    value: Callable[[Any], Any] | None = None  # export: obj -> cell (default getattr)


@dataclass
class ImportResult:
    created: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)  # {"row": int, "message": str}

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "failed": self.failed,
            "total": self.created + self.failed,
            "errors": self.errors[:100],  # cap payload
        }


@dataclass
class IOSpec:
    module: str                    # permission module, e.g. "companies"
    label: str                     # human label, e.g. "Companies"
    filename: str                  # base download filename
    columns: list[IOColumn]
    fetch: Callable[[Session], Iterable]
    import_rows: Callable[[Session, User, list[dict]], ImportResult]
    sample: dict                   # {column key: example string} for the template


# --- cell (de)serialization ------------------------------------------------

def cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def build_csv(spec: IOSpec, rows: Iterable) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.label for c in spec.columns])
    for obj in rows:
        w.writerow([cell(c.value(obj) if c.value else getattr(obj, c.key, None)) for c in spec.columns])
    return buf.getvalue()


def build_template_csv(spec: IOSpec) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.label for c in spec.columns])
    w.writerow([spec.sample.get(c.key, "") for c in spec.columns])
    return buf.getvalue()


def parse_csv(raw: bytes, spec: IOSpec) -> list[dict]:
    """Read the uploaded CSV into row dicts keyed by column.key.

    Accepts either the human labels or the raw keys as headers, tolerates a BOM,
    and trims whitespace.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    label_to_key = {c.label.strip().lower(): c.key for c in spec.columns}
    keys = {c.key for c in spec.columns}
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict] = []
    for raw_row in reader:
        row: dict[str, str] = {}
        for header, val in raw_row.items():
            if header is None:
                continue
            h = header.strip()
            key = label_to_key.get(h.lower()) or (h if h in keys else None)
            if key:
                row[key] = (val or "").strip()
        out.append(row)
    return out


# --- import helpers --------------------------------------------------------

def row_importer(create_fn: Callable[[Session, User, dict], None]):
    """Wrap a per-row create function into an import_rows runner.

    Each row is inserted inside its own SAVEPOINT, so a bad row fails on its own
    without discarding the rows before it.
    """

    def run(db: Session, user: User, rows: list[dict]) -> ImportResult:
        result = ImportResult()
        for i, row in enumerate(rows, start=2):  # row 1 is the header
            if not any(v for v in row.values()):
                continue  # skip blank lines
            try:
                with db.begin_nested():
                    create_fn(db, user, row)
                    db.flush()
                result.created += 1
            except AppError as e:
                result.failed += 1
                result.errors.append({"row": i, "message": e.detail})
            except Exception as e:  # noqa: BLE001
                result.failed += 1
                result.errors.append({"row": i, "message": str(e)[:200]})
        db.commit()
        return result

    return run


# --- value parsers (raise AppError with a friendly message on bad input) ----

def as_str(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def as_date(v: str | None, field_name: str = "date") -> date | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise AppError(f"Invalid {field_name} '{v}' — use YYYY-MM-DD")


def as_datetime(v: str | None, field_name: str = "date/time") -> datetime | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace(" ", "T"))
    except ValueError:
        raise AppError(f"Invalid {field_name} '{v}' — use YYYY-MM-DD or YYYY-MM-DD HH:MM")


def as_float(v: str | None, default: float = 0.0, field_name: str = "number") -> float:
    v = (v or "").strip().replace(",", "")
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        raise AppError(f"Invalid {field_name} '{v}'")


def as_int(v: str | None, default: int = 0, field_name: str = "number") -> int:
    v = (v or "").strip()
    if not v:
        return default
    try:
        return int(float(v))
    except ValueError:
        raise AppError(f"Invalid {field_name} '{v}'")


def as_list(v: str | None) -> list[str]:
    if not v:
        return []
    return [x.strip() for x in re.split(r"[;,]", v) if x.strip()]


def require(row: dict, key: str, label: str) -> str:
    val = (row.get(key) or "").strip()
    if not val:
        raise AppError(f"{label} is required")
    return val
