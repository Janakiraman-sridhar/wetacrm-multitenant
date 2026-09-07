"""Per-tenant data export.

Two things must hold at once: the client gets everything of theirs, and the zip does
not become the easiest way to walk off with every customer's identity numbers.
"""

import csv
import io
import json
import zipfile

import pytest

API = "/api/v1"


@pytest.fixture()
def archive(client, admin_headers, alpha):
    resp = client.get(f"{API}/platform/tenants/{alpha.tenant_id}/export", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(resp.content))


def _rows(archive, table):
    with archive.open(f"data/{table}.csv") as handle:
        text = handle.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_the_export_contains_the_tenants_records(archive, alpha):
    contacts = _rows(archive, "contacts")
    assert any(row["id"] == alpha.ids["contact"] for row in contacts)

    companies = _rows(archive, "companies")
    assert any(row["id"] == alpha.ids["company"] for row in companies)


def test_it_contains_only_that_tenants_records(archive, alpha, bravo):
    """The export runs in the tenant's scope; a leak here hands over another client."""
    for name in archive.namelist():
        if not name.startswith("data/"):
            continue
        table = name[len("data/"):-len(".csv")]
        for row in _rows(archive, table):
            if "tenant_id" in row and row["tenant_id"]:
                assert row["tenant_id"] == alpha.tenant_id, f"{table} leaked another tenant"


def test_it_carries_a_manifest_and_a_readme(archive, alpha):
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["slug"] == "alpha"
    assert manifest["total_rows"] == sum(manifest["tables"].values())
    assert manifest["tables"]["contacts"] >= 1

    readme = archive.read("README.txt").decode("utf-8")
    assert "PAN and Aadhaar" in readme
    assert "contacts" in readme


def test_password_hashes_are_never_exported(archive):
    """Not the client's data to take, and an offline cracking target if it leaves."""
    users = _rows(archive, "users")
    assert users, "the export should contain the workspace's users"
    assert "password_hash" not in users[0]


def test_identity_numbers_are_exported_encrypted_not_plaintext(client, alpha, admin_headers):
    """The zip must not be a shortcut past the reveal endpoint's permission and audit."""
    created = client.post(
        f"{API}/contacts",
        json={"first_name": "Export", "last_name": "Check", "mobile": "9700000811",
              "pan": "ABCDE1234F"},
        headers=alpha.auth(),
    )
    assert created.status_code == 200, created.text
    try:
        resp = client.get(
            f"{API}/platform/tenants/{alpha.tenant_id}/export", headers=admin_headers
        )
        blob = resp.content
        # The plaintext PAN appears nowhere in the archive, in any file.
        assert b"ABCDE1234F" not in blob

        rows = _rows(zipfile.ZipFile(io.BytesIO(blob)), "contacts")
        row = next(r for r in rows if r["id"] == created.json()["id"])
        assert row["pan_encrypted"], "the ciphertext should still be there"
        assert row["pan_masked"] == "ABCDE****F", "and the masked form is readable"
    finally:
        client.delete(f"{API}/contacts/{created.json()['id']}", headers=alpha.auth())


def test_json_columns_survive_as_json(archive):
    contacts = _rows(archive, "contacts")
    row = contacts[0]
    # Written as JSON text inside the cell, so it can be read back rather than
    # arriving as a Python repr nobody can parse.
    assert json.loads(row["emails"]) is not None
    assert isinstance(json.loads(row["custom"]), dict)


def test_empty_tables_are_omitted_unless_asked_for(client, admin_headers, alpha):
    lean = zipfile.ZipFile(io.BytesIO(client.get(
        f"{API}/platform/tenants/{alpha.tenant_id}/export", headers=admin_headers
    ).content))
    full = zipfile.ZipFile(io.BytesIO(client.get(
        f"{API}/platform/tenants/{alpha.tenant_id}/export",
        params={"include_empty": True}, headers=admin_headers,
    ).content))
    assert len(full.namelist()) > len(lean.namelist())


def test_a_tenant_user_cannot_export(client, alpha):
    resp = client.get(f"{API}/platform/tenants/{alpha.tenant_id}/export", headers=alpha.auth())
    assert resp.status_code in (401, 403)


def test_exporting_an_unknown_tenant_is_a_404(client, admin_headers):
    resp = client.get(f"{API}/platform/tenants/does-not-exist/export", headers=admin_headers)
    assert resp.status_code == 404


def test_the_export_is_audited(client, admin_headers, alpha, bravo):
    """An admin taking a whole workspace should leave a trace."""
    from sqlalchemy import select

    from app.core.tenancy import platform_scope
    from app.database.session import SessionLocal
    from app.platform.models import PlatformAuditLog

    client.get(f"{API}/platform/tenants/{alpha.tenant_id}/export", headers=admin_headers)
    with SessionLocal() as db, platform_scope():
        actions = db.scalars(
            select(PlatformAuditLog.action).where(PlatformAuditLog.action == "tenant.export")
        ).all()
    assert actions, "an export left no audit row"
