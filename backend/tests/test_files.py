"""Signed download links, and not trusting an uploader's word about a file's type.

The link route is the only one in the product that serves stored bytes without a
bearer token, so it carries the weight of two questions: can a link be edited into
someone else's file, and can a file be served as something that runs.
"""

import io
import time

import pytest

from app.services import downloads, mime

API = "/api/v1"


def _upload(client, world, content: bytes, filename: str, content_type: str):
    return client.post(
        f"{API}/documents",
        files={"file": (filename, io.BytesIO(content), content_type)},
        headers=world.auth(),
    )


@pytest.fixture()
def document(client, alpha):
    resp = _upload(client, alpha, b"%PDF-1.4 a real enough pdf", "policy.pdf", "application/pdf")
    assert resp.status_code == 200, resp.text
    row = resp.json()
    yield row
    client.delete(f"{API}/documents/{row['id']}", headers=alpha.auth())


# --- the token ----------------------------------------------------------------

def test_a_token_round_trips():
    token = downloads.sign("tenants/abc/x/file.pdf", "abc", filename="file.pdf")
    payload = downloads.verify(token)
    assert payload["k"] == "tenants/abc/x/file.pdf"
    assert payload["t"] == "abc"


def test_a_tampered_token_is_refused():
    token = downloads.sign("tenants/abc/x/file.pdf", "abc")
    body, signature = token.split(".", 1)
    # Re-point the link at another tenant's key and keep the signature.
    forged = downloads.sign("tenants/victim/x/file.pdf", "victim").split(".", 1)[0]
    with pytest.raises(downloads.InvalidDownloadToken):
        downloads.verify(f"{forged}.{signature}")


def test_an_expired_token_is_refused():
    token = downloads.sign("tenants/abc/x/file.pdf", "abc", ttl=-1)
    with pytest.raises(downloads.InvalidDownloadToken):
        downloads.verify(token)


def test_garbage_is_refused():
    for bad in ("", "nonsense", "a.b", "...."):
        with pytest.raises(downloads.InvalidDownloadToken):
            downloads.verify(bad)


def test_a_session_token_is_not_a_download_token(client, alpha):
    """Domain separation: the two are signed with different keys on purpose."""
    with pytest.raises(downloads.InvalidDownloadToken):
        downloads.verify(alpha.token)


# --- the route ----------------------------------------------------------------

def test_a_signed_link_serves_the_file_without_a_bearer_token(client, alpha, document):
    link = client.get(f"{API}/documents/{document['id']}/link", headers=alpha.auth())
    assert link.status_code == 200, link.text
    url = link.json()["url"]

    # No Authorization header — that is the whole point.
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


def test_a_served_file_cannot_be_told_to_run(client, alpha, document):
    url = client.get(f"{API}/documents/{document['id']}/link", headers=alpha.auth()).json()["url"]
    resp = client.get(url)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]
    assert resp.headers["cache-control"].startswith("private")


def test_an_expired_link_stops_working(client, alpha, document):
    from app.services import downloads as dl

    doc_key = client.get(
        f"{API}/documents", params={"page_size": 50}, headers=alpha.auth()
    ).json()
    token = dl.sign("tenants/x/y.pdf", alpha.tenant_id, ttl=-1)
    assert client.get(f"{API}/files/{token}").status_code == 404
    assert doc_key is not None


def test_a_link_for_another_tenants_key_is_refused(client, alpha, bravo):
    """Signed by us, pointing where it should not: the scope check catches it."""
    resp = _upload(client, bravo, b"%PDF-1.4 bravo's file", "bravo.pdf", "application/pdf")
    assert resp.status_code == 200
    bravo_doc = resp.json()

    with_bravo_key = client.get(
        f"{API}/documents/{bravo_doc['id']}/link", headers=bravo.auth()
    ).json()["url"]
    key = downloads.verify(with_bravo_key.rsplit("/", 1)[1])["k"]

    # A token minted for alpha's tenant but naming bravo's key — the shape an
    # attacker would forge if they could sign. `read_file` refuses it.
    crossed = downloads.sign(key, alpha.tenant_id)
    assert client.get(f"{API}/files/{crossed}").status_code == 404

    client.delete(f"{API}/documents/{bravo_doc['id']}", headers=bravo.auth())


def test_a_missing_file_and_a_bad_signature_look_the_same(client, alpha):
    """Otherwise the endpoint tells an attacker which keys exist."""
    missing = downloads.sign("tenants/%s/nope/gone.pdf" % alpha.tenant_id, alpha.tenant_id)
    assert client.get(f"{API}/files/{missing}").status_code == 404
    assert client.get(f"{API}/files/not-a-real-token").status_code == 404


# --- what a file is -----------------------------------------------------------

def test_html_uploaded_as_a_pdf_is_not_stored_as_a_pdf(client, alpha):
    """The stored type decides how it is served later, so it must come from the bytes."""
    resp = _upload(
        client, alpha,
        b"<!doctype html><script>alert(document.cookie)</script>",
        "invoice.pdf", "application/pdf",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["mime_type"] == "application/octet-stream"
    client.delete(f"{API}/documents/{resp.json()['id']}", headers=alpha.auth())


def test_an_html_upload_is_refused_outright(client, alpha):
    resp = _upload(client, alpha, b"<html><body>hi</body></html>", "page.html", "text/html")
    assert resp.status_code == 400
    assert "script" in resp.json()["detail"]


def test_an_svg_upload_is_refused(client, alpha):
    """An SVG is a document that can run script wearing an image's clothes."""
    resp = _upload(client, alpha, b"<svg xmlns='http://www.w3.org/2000/svg'/>",
                   "logo.svg", "image/svg+xml")
    assert resp.status_code == 400


def test_an_empty_upload_is_refused(client, alpha):
    resp = _upload(client, alpha, b"", "nothing.pdf", "application/pdf")
    assert resp.status_code == 400


def test_a_real_png_keeps_its_type(client, alpha):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
    resp = _upload(client, alpha, png, "photo.bin", "application/octet-stream")
    assert resp.status_code == 200
    assert resp.json()["mime_type"] == "image/png"
    client.delete(f"{API}/documents/{resp.json()['id']}", headers=alpha.auth())


def test_an_oversized_upload_is_refused(client, alpha):
    from app.documents.router import MAX_UPLOAD_BYTES

    resp = _upload(client, alpha, b"x" * (MAX_UPLOAD_BYTES + 1), "big.bin", "application/pdf")
    assert resp.status_code == 413


# --- the sniffer itself -------------------------------------------------------

@pytest.mark.parametrize("data,expected", [
    (b"%PDF-1.7 ...", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n rest", "image/png"),
    (b"\xff\xd8\xff\xe0 jfif", "image/jpeg"),
    (b"GIF89a....", "image/gif"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    (b"plain notes about a customer", "text/plain"),
    (b"<!DOCTYPE html><p>hi", "application/octet-stream"),
    (b"<svg xmlns='x'>", "application/octet-stream"),
    (b"\x00\x01\x02\x03\xfe", "application/octet-stream"),
])
def test_sniffing(data, expected):
    assert mime.sniff(data) == expected


def test_an_office_document_keeps_its_claimed_flavour():
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert mime.sniff(b"PK\x03\x04 rest", docx) == docx
    assert mime.sniff(b"PK\x03\x04 rest", "application/zip") == "application/zip"
    # A zip claiming to be HTML is still just a zip.
    assert mime.sniff(b"PK\x03\x04 rest", "text/html") == "application/zip"


def test_only_known_safe_types_render_inline():
    assert mime.is_inline_safe("application/pdf")
    assert mime.is_inline_safe("image/png")
    assert not mime.is_inline_safe("image/svg+xml")
    assert not mime.is_inline_safe("text/html")
    assert not mime.is_inline_safe("application/octet-stream")
    assert not mime.is_inline_safe(None)
