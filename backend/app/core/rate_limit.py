import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.exceptions import AppError
from app.core.tenancy import current_tenant_id

_hits: dict[str, deque] = defaultdict(deque)


def rate_limiter(name: str, limit: int, window_seconds: int = 60):
    """Simple in-memory sliding-window limiter, keyed by client IP.

    Suitable for a single-process deployment; swap for a Redis-backed limiter
    when scaling horizontally.
    """

    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Keyed by tenant as well as IP so one busy tenant cannot exhaust another's budget.
        key = f"{current_tenant_id() or '-'}:{name}:{client_ip}"
        now = time.monotonic()
        bucket = _hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise AppError("Too many requests, please try again shortly", 429)
        bucket.append(now)

    return dependency
