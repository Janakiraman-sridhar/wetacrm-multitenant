"""The one route that serves a stored file without a bearer token.

It is unauthenticated on purpose: a signed link is the whole point, so that a
document can be opened in a tab, put in an `<img src>`, or handed to something that
will not send an Authorization header. What replaces the bearer token is the
signature — and because the token names the tenant, serving it re-enters that
tenant's scope rather than trusting the key's shape.

Everything served here is served defensively:

- `X-Content-Type-Options: nosniff`, so a browser cannot decide a file is HTML
  because its bytes look like it.
- `Content-Disposition: attachment` for anything outside a short inline-safe list.
  A PDF or a PNG may render in place; an unrecognised blob is downloaded.
- `Content-Security-Policy: sandbox`, which neuters script in anything that does
  render, belt-and-braces with the type check above.
- `Cache-Control: private`, so a shared proxy does not keep one workspace's document
  where another's request might find it.
"""

import logging

from fastapi import APIRouter, Response

from app.core.exceptions import NotFoundError
from app.core.tenancy import tenant_scope
from app.services import downloads, mime, storage

log = logging.getLogger("weta.files")

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{token}")
def signed_download(token: str):
    """Serve the file a signed link points at."""
    try:
        payload = downloads.verify(token)
    except downloads.InvalidDownloadToken as exc:
        # 404 rather than 401: a wrong signature and a missing file should be
        # indistinguishable, or the endpoint becomes an oracle for valid keys.
        log.info("Refused a download link: %s", exc)
        raise NotFoundError("File")

    key, tenant_id = payload["k"], payload["t"]
    with tenant_scope(tenant_id):
        try:
            data = storage.read_file(key)
        except (storage.StorageAccessDenied, FileNotFoundError, OSError):
            raise NotFoundError("File")

    # The stored type is re-derived from the bytes, not taken from the link, so a
    # token cannot ask for a file to be served as something it is not.
    content_type = mime.sniff(data, payload.get("m"))
    inline = bool(payload.get("i")) and mime.is_inline_safe(content_type)
    filename = payload.get("n") or "download"

    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Cache-Control": "private, max-age=60",
        },
    )
