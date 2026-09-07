"""Purging a deleted tenant.

Irreversible work, so the tests are mostly about what it *refuses* to do. The one
that matters most is `test_purging_one_tenant_leaves_the_other_untouched`: a purge
that reaches past its own tenant is the worst bug this codebase could have, and it
would look exactly like success.
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.tenancy import platform_scope
from app.database.base import utcnow
from app.database.session import SessionLocal
from app.platform import purge
from app.platform.models import Tenant

API = "/api/v1"


def _tenant(db, tenant_id) -> Tenant:
    with platform_scope():
        return db.get(Tenant, tenant_id)


@pytest.fixture()
def doomed(client, admin_headers):
    """A workspace with data in it, created and deleted through the console."""
    created = client.post(
        f"{API}/platform/tenants",
        json={"name": "Purge Me", "owner_email": "owner-purge@example.com",
              "owner_password": "purge-pass-12", "template_key": "insurance_agent"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    tenant = created.json()

    token = client.post(
        f"{API}/auth/login",
        json={"email": "owner-purge@example.com", "password": "purge-pass-12"},
    ).json()["access_token"]
    own = {"Authorization": f"Bearer {token}"}
    customer = client.post(
        f"{API}/contacts",
        json={"first_name": "Doomed", "last_name": "Customer", "mobile": "9700000900"},
        headers=own,
    )
    assert customer.status_code == 200, customer.text

    yield tenant

    # Purge rather than deleting the tenant row: deleting it alone would orphan the
    # users, and `users.email` is globally unique, so the next test could not reuse
    # the address. Which is the same shape as the production bug this suite guards.
    with SessionLocal() as db:
        row = _tenant(db, tenant["id"])
        if row is not None:
            with platform_scope():
                row.deleted_at = row.deleted_at or utcnow()
                db.commit()
            purge.purge_tenant(db, _tenant(db, tenant["id"]))


def _delete_and_backdate(client, admin_headers, tenant_id, days):
    """Delete through the API, then age it as if the window had passed."""
    assert client.delete(
        f"{API}/platform/tenants/{tenant_id}", headers=admin_headers
    ).status_code == 200
    with SessionLocal() as db:
        with platform_scope():
            row = db.get(Tenant, tenant_id)
            row.deleted_at = utcnow() - timedelta(days=days)
            db.commit()


# --- what is due --------------------------------------------------------------

def test_a_live_tenant_is_never_due(client, admin_headers, doomed):
    with SessionLocal() as db:
        due = {t.id for t in purge.tenants_due_for_purge(db)}
    assert doomed["id"] not in due


def test_a_tenant_inside_the_window_is_not_due(client, admin_headers, doomed):
    _delete_and_backdate(client, admin_headers, doomed["id"], days=5)
    with SessionLocal() as db:
        due = {t.id for t in purge.tenants_due_for_purge(db)}
    assert doomed["id"] not in due, "deletion must stay undoable for the whole window"


def test_a_tenant_past_the_window_is_due(client, admin_headers, doomed):
    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    with SessionLocal() as db:
        due = {t.id for t in purge.tenants_due_for_purge(db)}
    assert doomed["id"] in due


def test_the_default_workspace_is_never_due(client, admin_headers):
    with SessionLocal() as db:
        due = purge.tenants_due_for_purge(db, retention_days=1)
    assert all(t.slug != "default" for t in due)


def test_a_zero_day_window_is_refused():
    """It would purge a workspace the instant it was deleted, undoing nothing."""
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            purge.tenants_due_for_purge(db, retention_days=0)


# --- what it removes ----------------------------------------------------------

def test_a_dry_run_reports_without_removing(client, admin_headers, doomed):
    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    with SessionLocal() as db:
        summary = purge.purge_tenant(db, _tenant(db, doomed["id"]), dry_run=True)
        assert summary["rows"]["contacts"] >= 1
        assert summary["rows"]["users"] >= 1
        assert _tenant(db, doomed["id"]) is not None, "a dry run must change nothing"


def test_purging_removes_the_tenant_and_its_rows(client, admin_headers, doomed):
    from app.contacts.models import Contact

    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    with SessionLocal() as db:
        summary = purge.purge_tenant(db, _tenant(db, doomed["id"]))
        assert summary["rows"]["contacts"] >= 1

        assert _tenant(db, doomed["id"]) is None
        with platform_scope():
            left = db.scalar(
                select(func.count()).select_from(Contact.__table__)
                .where(Contact.__table__.c.tenant_id == doomed["id"])
            )
        assert left == 0, "rows survived a purge that reported success"


def test_purging_removes_every_scoped_table(client, admin_headers, doomed):
    """Not just the obvious ones — settings, roles and modules go too."""
    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    with SessionLocal() as db:
        purge.purge_tenant(db, _tenant(db, doomed["id"]))
        with platform_scope():
            for table in purge._tenant_tables():
                remaining = db.scalar(
                    select(func.count()).select_from(table)
                    .where(table.c.tenant_id == doomed["id"])
                )
                assert remaining == 0, f"{table.name} still holds purged rows"


def test_purging_one_tenant_leaves_the_other_untouched(client, admin_headers, doomed, alpha):
    """The bug that would look exactly like success."""
    from app.contacts.models import Contact

    with SessionLocal() as db:
        with platform_scope():
            before = db.scalar(
                select(func.count()).select_from(Contact.__table__)
                .where(Contact.__table__.c.tenant_id == alpha.tenant_id)
            )

    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    with SessionLocal() as db:
        purge.purge_tenant(db, _tenant(db, doomed["id"]))
        with platform_scope():
            after = db.scalar(
                select(func.count()).select_from(Contact.__table__)
                .where(Contact.__table__.c.tenant_id == alpha.tenant_id)
            )
    assert after == before and before > 0

    # And the untouched tenant still works end to end.
    assert client.get(f"{API}/contacts", headers=alpha.auth()).status_code == 200


def test_a_live_tenant_cannot_be_purged(client, admin_headers, doomed):
    with SessionLocal() as db:
        with pytest.raises(ValueError):
            purge.purge_tenant(db, _tenant(db, doomed["id"]))


# --- the scheduled job --------------------------------------------------------

def test_the_scheduled_job_purges_what_is_due(client, admin_headers, doomed):
    from app.automation.tasks import purge_deleted_tenants

    _delete_and_backdate(client, admin_headers, doomed["id"], days=31)
    assert purge_deleted_tenants() >= 1
    with SessionLocal() as db:
        assert _tenant(db, doomed["id"]) is None


def test_the_scheduled_job_leaves_the_window_alone(client, admin_headers, doomed):
    from app.automation.tasks import purge_deleted_tenants

    _delete_and_backdate(client, admin_headers, doomed["id"], days=2)
    purge_deleted_tenants()
    with SessionLocal() as db:
        assert _tenant(db, doomed["id"]) is not None


# --- the console ---------------------------------------------------------------

def test_the_console_lists_what_is_awaiting_purge(client, admin_headers, doomed):
    _delete_and_backdate(client, admin_headers, doomed["id"], days=10)
    rows = client.get(f"{API}/platform/deleted-tenants", headers=admin_headers).json()
    row = next(r for r in rows if r["id"] == doomed["id"])
    assert row["days_until_purge"] == 20
    assert row["retention_days"] == 30


def test_purging_now_needs_the_slug_typed(client, admin_headers, doomed):
    slug = doomed["slug"]
    assert client.delete(
        f"{API}/platform/tenants/{doomed['id']}", headers=admin_headers
    ).status_code == 200

    wrong = client.post(
        f"{API}/platform/tenants/{doomed['id']}/purge",
        params={"confirm": "not-the-slug"}, headers=admin_headers,
    )
    assert wrong.status_code == 400
    assert slug in wrong.json()["detail"]

    right = client.post(
        f"{API}/platform/tenants/{doomed['id']}/purge",
        params={"confirm": slug}, headers=admin_headers,
    )
    assert right.status_code == 200, right.text
    with SessionLocal() as db:
        assert _tenant(db, doomed["id"]) is None


def test_purging_a_live_workspace_through_the_api_is_refused(client, admin_headers, doomed):
    resp = client.post(
        f"{API}/platform/tenants/{doomed['id']}/purge",
        params={"confirm": doomed["slug"]}, headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "Delete the workspace first" in resp.json()["detail"]


def test_a_tenant_user_cannot_reach_the_purge_endpoints(client, alpha, doomed):
    assert client.get(
        f"{API}/platform/deleted-tenants", headers=alpha.auth()
    ).status_code in (401, 403)
    assert client.post(
        f"{API}/platform/tenants/{doomed['id']}/purge",
        params={"confirm": doomed["slug"]}, headers=alpha.auth(),
    ).status_code in (401, 403)
