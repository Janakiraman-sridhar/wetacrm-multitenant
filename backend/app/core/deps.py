from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError, PermissionDeniedError
from app.core.permissions import has_permission
from app.core.security import decode_token
from app.core.tenancy import current_tenant_id, platform_scope
from app.database.session import get_db
from app.platform.catalog import MODULES_BY_KEY
from app.platform.models import Tenant, TenantModule
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

        if user.is_platform_admin and not token_tenant:
            return user  # platform console session; no tenant context

        if not token_tenant:
            raise AppError("Invalid or expired token", 401)

        # The token's tenant must be the user's own. There is no exception: platform
        # admins have no way to obtain a token for someone else's workspace.
        if user.tenant_id != token_tenant:
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


def module_enabled(db: Session, key: str) -> bool:
    """Whether this tenant has the module switched on.

    A tenant provisioned before the module existed has no row at all; that counts as
    enabled, because the alternative is an upgrade silently switching things off.
    """
    row = db.scalar(select(TenantModule).where(TenantModule.module_key == key))
    return True if row is None else row.enabled


def require_module(key: str):
    """Refuse a request for a module this workspace has switched off.

    Used where the endpoint's permission does not name its own module — the Poster
    Studio is gated by `contacts:read`, so without this, turning Poster off would
    hide it from the sidebar while leaving the API wide open.
    """

    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if not module_enabled(db, key):
            label = MODULES_BY_KEY[key].label if key in MODULES_BY_KEY else key
            raise NotFoundError(label)
        return user

    return dependency


def require_perm(permission: str):
    module_key = permission.split(":", 1)[0]
    #: Only permissions whose prefix *is* a catalog module can be module-gated.
    #: `users:read` and `activities:read` are cross-cutting and have no module to
    #: switch off, so they are never gated.
    gated = module_key in MODULES_BY_KEY and not MODULES_BY_KEY[module_key].locked

    def dependency(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.is_platform_admin and user.tenant_id is None:
            # A platform admin has no tenant data to act on, and cannot borrow a
            # tenant's session. Console work happens under /platform/*.
            raise PermissionDeniedError(
                "Platform administrators cannot use tenant endpoints"
            )
        if not has_permission(user.role.permissions if user.role else [], permission):
            raise PermissionDeniedError()
        # A module the tenant switched off is *gone*, not merely hidden. Without this
        # a workspace with Policies disabled could still create policies over the API
        # that its own UI would never show.
        if gated and not module_enabled(db, module_key):
            raise NotFoundError(MODULES_BY_KEY[module_key].label)
        return user

    return dependency
