from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Domain error carrying an HTTP status; raised from services."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class NotFoundError(AppError):
    def __init__(self, entity: str = "Resource"):
        super().__init__(f"{entity} not found", 404)


class PermissionDeniedError(AppError):
    def __init__(self, detail: str = "You do not have permission to perform this action"):
        super().__init__(detail, 403)


def register_exception_handlers(app: FastAPI) -> None:
    from app.core.tenancy import TenantContextMissing

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(TenantContextMissing)
    async def missing_tenant_handler(request: Request, exc: TenantContextMissing):
        """A tenant-scoped query with no tenant in context is a refusal, not a crash.

        It reaches here when a platform admin hits an endpoint that reads tenant data:
        they have no workspace, so the query correctly refuses to run rather than
        returning everyone's rows. Answering 500 hid that behind "something broke".
        """
        return JSONResponse(
            status_code=403,
            content={"detail": "This endpoint needs a workspace. Platform administrators have none."},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Never leak stack traces to clients.
        import logging

        logging.getLogger("weta").exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
