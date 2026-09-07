"""File storage: MinIO when configured, local ./uploads directory otherwise.

Object keys are prefixed `tenants/<tenant_id>/`, and reads and deletes verify that
prefix against the caller's tenant. Without that check a leaked or guessed key
would be enough to pull another tenant's document, since object storage has no
row-level filter of its own.
"""

import io
import logging
import os
import re
import uuid

from app.core.config import settings
from app.core.tenancy import current_tenant_id, is_platform_scope

log = logging.getLogger("weta.storage")

_minio_client = None


def _get_minio():
    global _minio_client
    if not settings.minio_endpoint or not settings.minio_access_key:
        return None
    if _minio_client is None:
        from minio import Minio

        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not _minio_client.bucket_exists(settings.minio_bucket):
            _minio_client.make_bucket(settings.minio_bucket)
    return _minio_client


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[-120:]


class StorageAccessDenied(Exception):
    """A storage key was accessed from outside the tenant that owns it."""


def tenant_prefix(tenant_id: str | None = None) -> str:
    tid = tenant_id or current_tenant_id()
    return f"tenants/{tid}/" if tid else "shared/"


def assert_key_readable(key: str) -> None:
    """Refuse a key that does not belong to the caller's tenant."""
    if is_platform_scope():
        return
    tid = current_tenant_id()
    if not tid:
        raise StorageAccessDenied("No tenant in context")
    # Legacy keys (pre-multi-tenant) have no prefix and belong to the default tenant;
    # the migration rewrites them, so anything unprefixed here is suspect.
    if not key.startswith(f"tenants/{tid}/"):
        raise StorageAccessDenied("Storage key does not belong to this tenant")


def save_file(data: bytes, filename: str, content_type: str | None = None) -> str:
    """Store bytes under the current tenant's prefix; returns the storage key."""
    key = f"{tenant_prefix()}{uuid.uuid4().hex}/{_safe_name(filename)}"
    client = _get_minio()
    if client:
        client.put_object(
            settings.minio_bucket, key, io.BytesIO(data), length=len(data),
            content_type=content_type or "application/octet-stream",
        )
    else:
        path = os.path.join(settings.upload_dir, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return key


def read_file(key: str) -> bytes:
    assert_key_readable(key)
    client = _get_minio()
    if client:
        resp = client.get_object(settings.minio_bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
    path = os.path.join(settings.upload_dir, key.replace("/", os.sep))
    with open(path, "rb") as f:
        return f.read()


def delete_file(key: str) -> None:
    assert_key_readable(key)
    client = _get_minio()
    try:
        if client:
            client.remove_object(settings.minio_bucket, key)
        else:
            path = os.path.join(settings.upload_dir, key.replace("/", os.sep))
            if os.path.exists(path):
                os.remove(path)
    except Exception:
        log.exception("Failed to delete stored file %s", key)
