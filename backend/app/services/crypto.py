"""Field-level encryption for personal data.

**Envelope encryption.** A platform master key encrypts a per-tenant data key (DEK);
the DEK encrypts the values. One tenant's data cannot be read with another's key, and
rotating the master key re-wraps the DEKs without touching a single row.

**AES-256-GCM**, so every value is authenticated as well as encrypted — a tampered
ciphertext fails to decrypt rather than returning plausible garbage. Each value gets
a fresh 96-bit nonce, stored alongside it.

**Blind indexes.** An encrypted column cannot be searched: two encryptions of the
same PAN differ. Each searchable encrypted field therefore has a companion column
holding `HMAC-SHA256(tenant_key, normalised_value)`, which supports exact-match
lookup ("find the customer with this PAN") without storing anything reversible.

Ciphertext is stored as ``v1:<base64 nonce>:<base64 ciphertext>``. The version prefix
is what makes a future algorithm change a migration rather than a rewrite.
"""

import base64
import hashlib
import hmac
import logging
import os
import threading

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

log = logging.getLogger("weta.crypto")

VERSION = "v1"
NONCE_BYTES = 12
KEY_BYTES = 32

_dek_cache: dict[str, bytes] = {}
_lock = threading.Lock()


class DecryptionError(RuntimeError):
    """A stored value could not be decrypted — wrong key, or tampered data."""


# --- keys ---------------------------------------------------------------------

def master_key() -> bytes:
    """The platform key that wraps every tenant DEK.

    In production this must come from `PII_MASTER_KEY`. Without it, a key is derived
    from the JWT secret so local development still runs with no setup — consistent
    with how every other optional service degrades — but it is logged loudly,
    because a derived key means PII is only as strong as the JWT secret.
    """
    raw = (settings.pii_master_key or "").strip()
    if raw:
        try:
            key = base64.urlsafe_b64decode(raw)
            if len(key) == KEY_BYTES:
                return key
        except Exception:
            pass
        return hashlib.sha256(raw.encode()).digest()

    if settings.environment == "production":
        raise RuntimeError(
            "PII_MASTER_KEY must be set in production. Generate one with: "
            "python -c \"import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        )
    log.warning(
        "PII_MASTER_KEY is not set — deriving a development key from JWT_SECRET. "
        "Set a real key before storing anyone's actual PAN or Aadhaar."
    )
    return hashlib.sha256(f"weta-pii-dev:{settings.jwt_secret}".encode()).digest()


def generate_dek() -> bytes:
    return os.urandom(KEY_BYTES)


def wrap_dek(dek: bytes) -> str:
    """Encrypt a tenant DEK with the master key, for storage on the tenant row."""
    return encrypt_with_key(master_key(), dek.hex())


def unwrap_dek(wrapped: str) -> bytes:
    return bytes.fromhex(decrypt_with_key(master_key(), wrapped))


def cache_dek(tenant_id: str, wrapped: str | None) -> bytes | None:
    """Unwrap and remember a tenant's DEK for this process."""
    if not wrapped:
        return None
    with _lock:
        cached = _dek_cache.get(tenant_id)
        if cached is not None:
            return cached
        try:
            dek = unwrap_dek(wrapped)
        except Exception:
            log.exception("Could not unwrap the data key for tenant %s", tenant_id)
            return None
        _dek_cache[tenant_id] = dek
        return dek


def forget_dek(tenant_id: str) -> None:
    with _lock:
        _dek_cache.pop(tenant_id, None)


def tenant_dek(tenant_id: str) -> bytes | None:
    """The cached DEK, loading it from the tenant row on a miss.

    The miss path opens its own short session because this is reached from inside a
    flush, where reusing the caller's session would reenter it.
    """
    with _lock:
        cached = _dek_cache.get(tenant_id)
    if cached is not None:
        return cached

    from app.database.session import SessionLocal
    from app.platform.models import Tenant

    with SessionLocal() as db:
        from app.core.tenancy import platform_scope

        with platform_scope():
            tenant = db.get(Tenant, tenant_id)
            wrapped = tenant.dek_encrypted if tenant else None
    return cache_dek(tenant_id, wrapped)


# --- primitives ---------------------------------------------------------------

def encrypt_with_key(key: bytes, plaintext: str) -> str:
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{VERSION}:{base64.b64encode(nonce).decode()}:{base64.b64encode(ciphertext).decode()}"


def decrypt_with_key(key: bytes, stored: str) -> str:
    try:
        version, nonce_b64, ciphertext_b64 = stored.split(":", 2)
    except ValueError:
        raise DecryptionError("Stored value is not in the expected format")
    if version != VERSION:
        raise DecryptionError(f"Unsupported ciphertext version '{version}'")
    try:
        plaintext = AESGCM(key).decrypt(
            base64.b64decode(nonce_b64), base64.b64decode(ciphertext_b64), None
        )
    except (InvalidTag, ValueError) as exc:
        raise DecryptionError("Value could not be decrypted") from exc
    return plaintext.decode("utf-8")


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(f"{VERSION}:")


# --- tenant-scoped helpers ----------------------------------------------------

def encrypt_for_tenant(tenant_id: str, plaintext: str | None) -> str | None:
    if plaintext in (None, ""):
        return None
    dek = tenant_dek(tenant_id)
    if dek is None:
        raise RuntimeError(f"Tenant {tenant_id} has no data key; cannot store personal data")
    return encrypt_with_key(dek, str(plaintext))


def decrypt_for_tenant(tenant_id: str, stored: str | None) -> str | None:
    if not stored:
        return None
    if not is_encrypted(stored):
        return stored  # written before encryption was switched on
    dek = tenant_dek(tenant_id)
    if dek is None:
        return None
    try:
        return decrypt_with_key(dek, stored)
    except DecryptionError:
        log.warning("Could not decrypt a stored value for tenant %s", tenant_id)
        return None


def blind_index(tenant_id: str, value: str | None) -> str | None:
    """A keyed hash for exact-match lookup of an encrypted value.

    Keyed per tenant and domain-separated from encryption, so the index cannot be
    brute-forced across tenants and leaks nothing beyond "these two rows hold the
    same value".
    """
    if value in (None, ""):
        return None
    dek = tenant_dek(tenant_id)
    if dek is None:
        return None
    normalised = str(value).strip().upper().replace(" ", "").replace("-", "")
    key = hashlib.sha256(b"weta-blind-index:" + dek).digest()
    return hmac.new(key, normalised.encode("utf-8"), hashlib.sha256).hexdigest()
