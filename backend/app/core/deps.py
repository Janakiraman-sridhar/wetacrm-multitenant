from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, PermissionDeniedError
from app.core.permissions import has_permission
from app.core.security import decode_token
from app.database.session import get_db
from app.users.models import User


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("Not authenticated", 401)
    payload = decode_token(authorization.split(" ", 1)[1], "access")
    if not payload:
        raise AppError("Invalid or expired token", 401)
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise AppError("Invalid or expired token", 401)
    return user


def require_perm(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user.role.permissions if user.role else [], permission):
            raise PermissionDeniedError()
        return user

    return dependency
