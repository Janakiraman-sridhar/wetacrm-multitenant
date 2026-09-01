from sqlalchemy.orm import Session

from app.notifications.models import Notification
from app.notifications.socket import emit_to_user


def notify(
    db: Session,
    user_id: str | None,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> None:
    """Persist a notification and push it over Socket.IO. Caller commits."""
    if not user_id:
        return
    n = Notification(user_id=user_id, type=type, title=title, body=body, link=link)
    db.add(n)
    db.flush()
    emit_to_user(
        user_id,
        "notification",
        {"id": n.id, "type": type, "title": title, "body": body, "link": link, "created_at": n.created_at.isoformat()},
    )
