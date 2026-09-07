from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, PermissionDeniedError
from app.core.permissions import has_permission
from app.core.security import decode_token
from app.core.tenancy import current_tenant_id, platform_scope
from app.database.session import get_db
from app.platform.models import Tenant
from app.users.models import User


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve and validate the caller.

    The tenant is already in context by the time this runs — `TenantContextMiddleware`
    set it from the token's signed `tid` claim. This function's job is to prove the
    token's user actually belongs to that tenant, so a valid token for tenant A can
    never be paired with a `tid` for tenant B.

    The lookups run in `platform_scope()` because the user and tenant rows have to
    be readable before the caller's tenancy has been verified.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError("Not authenticated", 401)
    payload = decode_token(authorization.split(" ", 1)[1], "access")
    if not payload:
        raise AppError("Invalid or expired token", 401)

    with platform_scope():
        user = db.get(User, payload["sub"])
        if not user or not user.is_active:
            raise AppError("Invalid or expired token", 401)

        token_tenant = payload.get("tid")
        impersonator = payload.get("imp")

        if user.is_platform_admin and not token_tenant:
            return user  # platform console session; no tenant context

        if not token_tenant:
            raise AppError("Invalid or expired token", 401)

        # An impersonation token is minted by a platform admin for a specific tenant
        # user; otherwise the token's tenant must match the user's own.
        if not impersonator and user.tenant_id != token_tenant:
            raise AppError("Invalid or expired token", 401)
        if impersonator and user.tenant_id != token_tenant:
            raise AppError("Invalid or expired token", 401)

        tenant = db.get(Tenant, token_tenant)
        if not tenant or tenant.deleted_at is not None:
            raise AppError("Invalid or expired token", 401)
        if not tenant.is_usable:
            raise AppError("This account is suspended. Contact your administrator.", 403)

    if current_tenant_id() != token_tenant:
        # Middleware should have set this; refuse rather than run unscoped.
        raise AppError("Tenant context unavailable", 500)

    return user


def get_platform_admin(user: User = Depends(get_current_user)) -> User:
    """Guard for the Super Admin console. Platform admins bypass tenant RBAC entirely."""
    if not user.is_platform_admin:
        raise PermissionDeniedError("Platform administrator access required")
    return user


def require_perm(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.is_platform_admin and user.tenant_id is None:
            # A platform admin outside an impersonation session has no tenant data
            # to act on; they must impersonate to use tenant endpoints.
            raise PermissionDeniedError("Impersonate a tenant user to use this endpoint")
        if not has_permission(user.role.permissions if user.role else [], permission):
            raise PermissionDeniedError()
        return user

    return dependency
