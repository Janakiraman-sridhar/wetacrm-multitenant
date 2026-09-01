from sqlalchemy.orm import Session

from app.activities.models import Activity, AuditLog


def log_activity(
    db: Session,
    entity_type: str,
    entity_id: str,
    type: str,
    title: str,
    user_id: str | None = None,
    body: str | None = None,
    meta: dict | None = None,
) -> Activity:
    """Add a timeline entry for an entity. Caller commits."""
    a = Activity(
        entity_type=entity_type,
        entity_id=entity_id,
        type=type,
        title=title,
        body=body,
        user_id=user_id,
        meta=meta or {},
    )
    db.add(a)
    return a


def audit(
    db: Session,
    user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    changes: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Record an audit-log row. Caller commits."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes or {},
            ip_address=ip_address,
        )
    )
