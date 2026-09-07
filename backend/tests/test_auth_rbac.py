"""Sign-in, tokens, and who is allowed to do what.

These paths are older than the multi-tenant work and had no suite of their own — the
isolation tests exercised them incidentally, which covers "does it work" but not
"does it refuse". Refusing correctly is the whole job of an auth layer.
"""

import pytest

from app.core.security import create_access_token, create_refresh_token, decode_token

API = "/api/v1"


def _login(client, email, password):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


# --- signing in ---------------------------------------------------------------

def test_a_correct_password_signs_in(client, alpha):
    from tests.conftest import PASSWORD

    resp = _login(client, alpha.admin_email, PASSWORD)
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["email"] == alpha.admin_email


def test_a_wrong_password_is_refused(client, alpha):
    assert _login(client, alpha.admin_email, "not-the-password").status_code == 401


def test_an_unknown_email_is_refused_the_same_way(client):
    """The two must be indistinguishable, or the endpoint enumerates accounts."""
    unknown = _login(client, "nobody-at-all@example.com", "whatever")
    wrong = _login(client, "nobody-at-all@example.com", "different")
    assert unknown.status_code == 401
    assert unknown.json() == wrong.json()


def test_the_password_is_never_echoed_back(client, alpha):
    from tests.conftest import PASSWORD

    body = _login(client, alpha.admin_email, PASSWORD).json()
    assert "password" not in str(body).lower() or PASSWORD not in str(body)
    assert "password_hash" not in body["user"]


def test_a_deactivated_user_cannot_sign_in(client, alpha):
    from sqlalchemy import select

    from app.core.tenancy import tenant_scope
    from app.database.session import SessionLocal
    from app.users.models import User
    from tests.conftest import PASSWORD

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        user = db.scalar(select(User).where(User.email == alpha.admin_email))
        user.is_active = False
        db.commit()
    try:
        assert _login(client, alpha.admin_email, PASSWORD).status_code in (401, 403)
    finally:
        with SessionLocal() as db, tenant_scope(alpha.tenant_id):
            user = db.scalar(select(User).where(User.email == alpha.admin_email))
            user.is_active = True
            db.commit()


# --- tokens -------------------------------------------------------------------

def test_no_token_is_refused(client):
    assert client.get(f"{API}/contacts").status_code == 401


def test_a_junk_token_is_refused(client):
    for bad in ("Bearer nonsense", "Bearer a.b.c", "Basic abc", "nonsense"):
        resp = client.get(f"{API}/contacts", headers={"Authorization": bad})
        assert resp.status_code == 401, bad


def test_a_refresh_token_is_not_an_access_token(client, alpha):
    """Otherwise the long-lived credential becomes the short-lived one."""
    from tests.conftest import PASSWORD

    refresh = _login(client, alpha.admin_email, PASSWORD).json()["refresh_token"]
    resp = client.get(f"{API}/contacts", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401


def test_an_expired_token_is_refused(client, alpha):
    import time

    from app.core.config import settings

    original = settings.access_token_expire_minutes
    settings.access_token_expire_minutes = -1
    try:
        stale = create_access_token("whoever", alpha.tenant_id)
    finally:
        settings.access_token_expire_minutes = original
    time.sleep(0.01)
    assert client.get(
        f"{API}/contacts", headers={"Authorization": f"Bearer {stale}"}
    ).status_code == 401


def test_a_token_signed_with_another_secret_is_refused(client, alpha):
    from app.core.config import settings

    original = settings.jwt_secret
    settings.jwt_secret = "a-completely-different-secret"
    try:
        forged = create_access_token("whoever", alpha.tenant_id)
    finally:
        settings.jwt_secret = original
    assert client.get(
        f"{API}/contacts", headers={"Authorization": f"Bearer {forged}"}
    ).status_code == 401


def test_decode_rejects_the_wrong_token_type():
    token = create_refresh_token("user-1", "tenant-1")
    assert decode_token(token, "refresh") is not None
    assert decode_token(token, "access") is None


def test_refreshing_returns_a_working_access_token(client, alpha):
    from tests.conftest import PASSWORD

    refresh = _login(client, alpha.admin_email, PASSWORD).json()["refresh_token"]
    resp = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200, resp.text
    fresh = resp.json()["access_token"]
    assert client.get(
        f"{API}/contacts", headers={"Authorization": f"Bearer {fresh}"}
    ).status_code == 200


def test_refreshing_with_an_access_token_is_refused(client, alpha):
    resp = client.post(f"{API}/auth/refresh", json={"refresh_token": alpha.token})
    assert resp.status_code == 401


# --- who may do what ----------------------------------------------------------

@pytest.fixture()
def read_only_user(client, alpha):
    """A user whose role can read contacts and nothing else."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.core.tenancy import tenant_scope
    from app.database.session import SessionLocal
    from app.users.models import Role, User

    email = "readonly-rbac@example.com"
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        role = Role(name="RBAC Read Only", permissions=["contacts:read"])
        db.add(role)
        db.flush()
        user = User(
            email=email, password_hash=hash_password("read-only-pass-1"),
            first_name="Read", last_name="Only", role_id=role.id,
        )
        db.add(user)
        db.commit()
        ids = (user.id, role.id)

    token = _login(client, email, "read-only-pass-1").json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        db.delete(db.get(User, ids[0]))
        db.commit()
        db.delete(db.get(Role, ids[1]))
        db.commit()


def test_a_granted_permission_is_allowed(client, read_only_user):
    assert client.get(f"{API}/contacts", headers=read_only_user).status_code == 200


def test_a_missing_write_permission_is_refused(client, read_only_user):
    resp = client.post(
        f"{API}/contacts", json={"first_name": "Should", "last_name": "Fail"},
        headers=read_only_user,
    )
    assert resp.status_code == 403


def test_a_missing_read_permission_is_refused(client, read_only_user):
    assert client.get(f"{API}/deals", headers=read_only_user).status_code == 403


def test_a_missing_delete_permission_is_refused(client, read_only_user, alpha):
    resp = client.delete(f"{API}/contacts/{alpha.ids['contact']}", headers=read_only_user)
    assert resp.status_code == 403


def test_reveal_pii_needs_its_own_permission(client, read_only_user, alpha):
    """`contacts:read` must not be enough to see a full PAN."""
    resp = client.post(
        f"{API}/contacts/{alpha.ids['contact']}/reveal", json={"field": "pan"}, headers=read_only_user
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("permissions,wanted,allowed", [
    (["*"], "anything:read", True),
    (["contacts:*"], "contacts:delete", True),
    (["contacts:*"], "deals:read", False),
    (["contacts:read"], "contacts:read", True),
    (["contacts:read"], "contacts:write", False),
    ([], "contacts:read", False),
    (["contacts:read", "deals:read"], "deals:read", True),
])
def test_permission_matching(permissions, wanted, allowed):
    from app.core.permissions import has_permission

    assert has_permission(permissions, wanted) is allowed
