"""Request middleware that puts the caller's tenant into context.

This is deliberately a *pure ASGI* middleware rather than a Starlette
``BaseHTTPMiddleware``: pure ASGI middleware runs in the same asyncio task as the
endpoint, so a ``ContextVar`` set here is visible to the route handler and to the
sync dependencies FastAPI runs in a threadpool (which inherit a copy of the
current context). ``BaseHTTPMiddleware`` runs the downstream app in a separate
task and cannot be relied on to propagate context.

The tenant id is read from the signed JWT's ``tid`` claim, so it cannot be forged.
`app.core.deps.get_current_user` still re-validates that the user really belongs
to that tenant before any handler runs.
"""

import logging

from app.core.security import decode_token
from app.core.tenancy import reset_request_tenant, set_request_tenant

log = logging.getLogger("weta.tenancy")


class TenantContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        tenant_id = _tenant_from_headers(scope.get("headers") or [])
        token = set_request_tenant(tenant_id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_tenant(token)


def _tenant_from_headers(headers) -> str | None:
    for key, value in headers:
        if key.lower() != b"authorization":
            continue
        try:
            raw = value.decode("latin-1")
        except Exception:
            return None
        if not raw.lower().startswith("bearer "):
            return None
        payload = decode_token(raw.split(" ", 1)[1], "access")
        return payload.get("tid") if payload else None
    return None
