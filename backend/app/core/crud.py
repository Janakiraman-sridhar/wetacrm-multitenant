from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError


def get_or_404(db: Session, model, id: str, entity_name: str | None = None):
    obj = db.get(model, id)
    if obj is None:
        raise NotFoundError(entity_name or model.__name__)
    return obj


def apply_updates(obj, data: dict) -> dict:
    """Set changed fields on an ORM object; returns {field: [old, new]} for auditing."""
    changes: dict = {}
    for field, value in data.items():
        old = getattr(obj, field, None)
        if old != value:
            changes[field] = [_plain(old), _plain(value)]
            setattr(obj, field, value)
    return changes


def _plain(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (list, dict, str, int, float, bool)) or v is None:
        return v
    return str(v)
