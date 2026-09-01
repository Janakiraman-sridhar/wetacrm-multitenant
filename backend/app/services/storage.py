"""File storage: MinIO when configured, local ./uploads directory otherwise."""

import io
import logging
import os
import re
import uuid

from app.core.config import settings

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


def save_file(data: bytes, filename: str, content_type: str | None = None) -> str:
    """Store bytes; returns the storage key."""
    key = f"{uuid.uuid4().hex}/{_safe_name(filename)}"
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
