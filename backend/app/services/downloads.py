"""Signed, expiring links to stored files.

Every file route requires a bearer token, which is safe but means a file cannot be
put in an `<img src>`, opened in a new tab, or handed to anything that will not send
an Authorization header. The workaround — fetching blobs and holding object URLs —
works but makes a poster gallery load every image through JavaScript and makes
"send this document to the customer" impossible.

A signed link solves that without weakening anything, provided three things hold:

**The token names the tenant, and reading it re-enters that tenant's scope.** The key
alone is not enough: `tenants/<id>/...` is guessable in shape, so a token that only
carried a key would let one workspace's link be edited into another's.

**It expires.** Minutes, not days. A link that leaks from a browser history or a chat
message stops working on its own.

**It is signed with a key that is not the session key.** Domain-separated from
`JWT_SECRET`, so a download token can never be replayed as a session and a bug in one
path cannot mint credentials for the other.
"""

import base64
import hashlib
import hmac
import json
import logging
import time

from app.core.config import settings

log = logging.getLogger("weta.downloads")

#: Long enough to open a file or load a gallery, short enough that a link pasted
#: somewhere it should not be is dead before anyone finds it.
DEFAULT_TTL_SECONDS = 300


class InvalidDownloadToken(Exception):
    """The token is malformed, tampered with, or past its expiry."""


def _signing_key() -> bytes:
    return hashlib.sha256(f"weta-download-v1:{settings.jwt_secret}".encode()).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign(
    key: str,
    tenant_id: str,
    *,
    filename: str | None = None,
    content_type: str | None = None,
    inline: bool = False,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> str:
    """Mint a token granting read access to one storage key, for a short while."""
    payload = {
        "k": key,
        "t": tenant_id,
        "e": int(time.time()) + ttl,
        "n": filename,
        "m": content_type,
        "i": inline,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def verify(token: str) -> dict:
    """Return the payload, or raise. Never returns something half-checked."""
    try:
        body, signature = token.split(".", 1)
    except ValueError:
        raise InvalidDownloadToken("Malformed link")

    expected = hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest()
    try:
        supplied = _unb64(signature)
    except Exception:
        # Junk that is not even base64. This route is unauthenticated, so anything
        # that escapes as an unhandled exception is a 500 anyone can trigger.
        raise InvalidDownloadToken("Malformed link")

    # Constant-time: a timing oracle on the signature is how forged tokens get made.
    if not hmac.compare_digest(supplied, expected):
        raise InvalidDownloadToken("Link signature does not match")

    try:
        payload = json.loads(_unb64(body))
    except Exception:
        raise InvalidDownloadToken("Malformed link")
    if not isinstance(payload, dict):
        raise InvalidDownloadToken("Malformed link")

    if payload.get("e", 0) < time.time():
        raise InvalidDownloadToken("This link has expired")
    if not payload.get("k") or not payload.get("t"):
        raise InvalidDownloadToken("Malformed link")
    return payload
