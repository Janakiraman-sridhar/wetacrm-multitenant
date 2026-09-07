"""What a file actually is, rather than what it was uploaded as.

`UploadFile.content_type` is whatever the client typed in a header. Storing it and
then echoing it back on download means an attacker chooses the `Content-Type` their
file is served with — which is one browser quirk away from stored XSS on a CRM full
of other people's customer data.

So: sniff the bytes, and where the sniff disagrees with the claim, trust the bytes.
Where nothing recognisable is found, fall back to `application/octet-stream` rather
than to the client's word for it.

This is a short allow-list, not a full format detector. It does not need to identify
everything — it needs to be certain about the handful of types that are safe to serve
inline, and unbothered about the rest, which are served as downloads regardless.
"""

#: (offset, magic bytes, mime type). Ordered most-specific first.
_SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"%PDF-", "application/pdf"),
    (0, b"\x89PNG\r\n\x1a\n", "image/png"),
    (0, b"\xff\xd8\xff", "image/jpeg"),
    (0, b"GIF87a", "image/gif"),
    (0, b"GIF89a", "image/gif"),
    (0, b"BM", "image/bmp"),
    (0, b"II*\x00", "image/tiff"),
    (0, b"MM\x00*", "image/tiff"),
    (0, b"OggS", "application/ogg"),
    (0, b"\x1f\x8b", "application/gzip"),
    (0, b"Rar!\x1a\x07", "application/vnd.rar"),
    (0, b"7z\xbc\xaf\x27\x1c", "application/x-7z-compressed"),
    (0, b"\xd0\xcf\x11\xe0", "application/vnd.ms-office"),  # legacy .doc/.xls
    (4, b"ftyp", "video/mp4"),
]

#: Types a browser may render in place. Everything else is sent as an attachment.
#: Deliberately excludes SVG — it is a document that can run script, so an SVG
#: rendered inline from user upload is an XSS vector wearing an image's clothes.
INLINE_SAFE = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "text/plain",
}

#: Never served with the client's claimed type, whatever it says.
_NEVER_TRUST = {
    "text/html", "application/xhtml+xml", "image/svg+xml",
    "application/xml", "text/xml", "application/javascript", "text/javascript",
}


def _zip_flavour(data: bytes, claimed: str | None) -> str:
    """A .docx, .xlsx and .zip are all PK archives; the claim decides between them."""
    office = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.oasis.opendocument.spreadsheet",
    }
    return claimed if claimed in office else "application/zip"


def sniff(data: bytes, claimed: str | None = None) -> str:
    """The content type to store and serve. Never the client's word alone."""
    head = data[:64]

    for offset, magic, mime in _SIGNATURES:
        if head[offset:offset + len(magic)] == magic:
            return mime

    if head[:4] == b"PK\x03\x04":
        return _zip_flavour(data, claimed)

    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"

    # Text that decodes cleanly and holds no markup is safe to call text/plain.
    # Anything with a tag in it is not, whatever extension it arrived under.
    try:
        text = data[:2048].decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"

    lowered = text.lstrip()[:256].lower()
    if lowered.startswith(("<!doctype html", "<html", "<?xml", "<svg", "<script")):
        return "application/octet-stream"
    if data and all(ch >= " " or ch in "\r\n\t" for ch in text):
        return "text/plain"
    return "application/octet-stream"


def is_inline_safe(content_type: str | None) -> bool:
    return bool(content_type) and content_type in INLINE_SAFE


def rejected_reason(content_type: str) -> str | None:
    """Why an upload is refused, or None if it is fine to store.

    Only the actively dangerous ones are refused. A CRM holds odd files and
    refusing anything unrecognised would make it useless — the defence is in how
    they are served, not in guessing which are harmless.
    """
    if content_type in _NEVER_TRUST:
        return f"{content_type} files cannot be uploaded — they can run script when opened"
    return None
