"""Sliding-window rate limiting, shared across workers when Redis is available.

The in-memory limiter this replaced counted per process, which meant two things:
the budget reset whenever the container restarted, and four Gunicorn workers gave an
attacker four times the allowance. Neither is visible in testing — the limiter looks
like it works — and both matter on the endpoints it guards: sign-in, password reset,
and revealing a customer's PAN.

Redis makes the window shared and durable. Without `REDIS_URL` it falls back to the
in-memory counter, consistent with how every other optional service degrades here —
and loudly, once, so nobody assumes they have protection they do not have.

**Failing open is deliberate.** If Redis is unreachable mid-request, the limiter lets
the request through rather than refusing it. A rate limiter that takes the whole
product down when its cache blinks has caused a worse outage than the abuse it was
guarding against; the fallback still applies a per-process limit.
"""

import logging
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenancy import current_tenant_id

log = logging.getLogger("weta.rate_limit")

_hits: dict[str, deque] = defaultdict(deque)
_redis = None
_redis_failed = False
_warned_no_redis = False


def _get_redis():
    """The shared counter, or None to fall back to the in-memory one."""
    global _redis, _redis_failed, _warned_no_redis

    if not settings.redis_url:
        if not _warned_no_redis:
            _warned_no_redis = True
            log.warning(
                "REDIS_URL is not set — rate limits are per-process and reset on restart. "
                "Set it before running more than one worker."
            )
        return None
    if _redis_failed:
        return None
    if _redis is None:
        try:
            import redis

            _redis = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
            _redis.ping()
        except Exception:
            # Once, not per request: a dead Redis should not also fill the log.
            _redis_failed = True
            _redis = None
            log.exception("Redis is unreachable — falling back to per-process rate limits")
    return _redis


def _allow_in_memory(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _allow_redis(client, key: str, limit: int, window_seconds: int) -> bool:
    """A sliding window over a sorted set, trimmed to the window on every call.

    Sorted set rather than a counter with an expiry, because a plain counter resets
    on a fixed boundary — letting through a full budget at 11:59 and another at
    12:00, which is twice the limit in two seconds.
    """
    now = time.time()
    cutoff = now - window_seconds
    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        # A unique member per hit; the score is what the window is measured on.
        pipe.zadd(key, {f"{now}:{time.monotonic_ns()}": now})
        pipe.expire(key, window_seconds + 1)
        _, used, _, _ = pipe.execute()
    except Exception:
        log.exception("Rate limit check failed; allowing the request")
        return True
    return used < limit


def rate_limiter(name: str, limit: int, window_seconds: int = 60):
    """Dependency allowing `limit` requests per `window_seconds`, per tenant and IP."""

    def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Keyed by tenant as well as IP so one busy tenant cannot exhaust another's
        # budget, and one IP behind a shared NAT cannot lock out a whole office.
        key = f"ratelimit:{current_tenant_id() or '-'}:{name}:{client_ip}"

        redis_client = _get_redis()
        allowed = (
            _allow_redis(redis_client, key, limit, window_seconds)
            if redis_client is not None
            else _allow_in_memory(key, limit, window_seconds)
        )
        if not allowed:
            raise AppError("Too many requests, please try again shortly", 429)

    return dependency


def reset() -> None:
    """Clear every counter. For tests — the process-local window outlives them."""
    global _redis_failed
    _hits.clear()
    _redis_failed = False
    client = _get_redis()
    if client is not None:
        try:
            keys = list(client.scan_iter("ratelimit:*"))
            if keys:
                client.delete(*keys)
        except Exception:
            log.exception("Could not clear Redis rate limit keys")
