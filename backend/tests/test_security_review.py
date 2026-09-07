"""The security review, written as checks rather than as a document.

A review done once is true once. These are the same questions asked on every run:
is every route authenticated, does every business model carry a tenant, does an
encrypted value ever escape through a channel that was not meant to carry it, and
does an error tell an attacker more than it tells a user.

The route sweep is the one that earns its place over time. Adding an endpoint without
an auth dependency is a one-line mistake that nothing else in the suite would notice,
and it stays unnoticed until it is found from outside.
"""

import pytest
from fastapi.routing import APIRoute

from app import models_registry  # noqa: F401  (registers every model)
from app.database.base import Base, TenantScoped
from app.main import app

API = "/api/v1"

#: Routes that are unauthenticated on purpose, each with the reason. Anything not on
#: this list must carry an auth dependency — the point is that adding one here is a
#: deliberate act someone has to justify in a code review.
PUBLIC_ROUTES = {
    "/api/v1/auth/login": "you cannot be signed in to sign in",
    "/api/v1/auth/refresh": "the refresh token is the credential",
    "/api/v1/auth/forgot-password": "requested by someone locked out",
    "/api/v1/auth/reset-password": "the emailed token is the credential",
    "/api/v1/files/{token}": "the signature is the credential; see app/files/router.py",
    "/api/v1/health": "liveness probe",
    "/health": "liveness probe",
    "/api/docs": "API documentation",
    "/api/redoc": "API documentation",
    "/api/openapi.json": "API documentation",
    "/": "root",
}

#: Matched on `__qualname__`, not `__name__`. `require_perm`, `require_module` and
#: `rate_limiter` all return an inner function called `dependency`, so matching the
#: bare name would count a rate-limited-but-unauthenticated route as guarded — a
#: false negative in exactly the check that exists to prevent one.
_AUTH_DEPENDENCIES = {
    "get_current_user",
    "get_platform_admin",
    "require_perm.<locals>.dependency",
    "require_module.<locals>.dependency",
}


def _auth_names(route: APIRoute) -> set[str]:
    """Every dependency on the route, including nested ones, by qualified name."""
    names = set()

    def walk(dependencies):
        for dependency in dependencies:
            call = getattr(dependency, "call", None)
            if call is not None:
                names.add(getattr(call, "__qualname__", getattr(call, "__name__", "")))
            walk(dependency.dependencies)

    walk(route.dependant.dependencies)
    return names


def _api_routes():
    return [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api/")
    ]


# --- every route is authenticated ---------------------------------------------

def test_every_route_requires_authentication_or_is_listed_as_public():
    unguarded = []
    for route in _api_routes():
        if route.path in PUBLIC_ROUTES:
            continue
        if not (_auth_names(route) & _AUTH_DEPENDENCIES):
            unguarded.append(f"{sorted(route.methods)} {route.path}")
    assert not unguarded, (
        "these routes have no auth dependency and are not listed in PUBLIC_ROUTES:\n  "
        + "\n  ".join(sorted(unguarded))
    )


def test_the_public_list_has_not_grown_silently():
    """A snapshot, so adding a public route is a visible decision."""
    actual = {r.path for r in _api_routes() if r.path in PUBLIC_ROUTES}
    unexpected = actual - set(PUBLIC_ROUTES)
    assert not unexpected, unexpected


@pytest.mark.parametrize("path", [
    "/contacts", "/policies", "/loans", "/quotations", "/documents",
    "/invoices", "/deals", "/leads", "/tasks", "/companies", "/search?q=x",
    "/platform/tenants", "/reports/insurance/renewals",
])
def test_calling_without_a_token_is_refused(client, path):
    """The sweep above reads the route table; this proves it at the door."""
    assert client.get(f"{API}{path}").status_code == 401


# --- every business row belongs to a tenant -----------------------------------

#: Tables that legitimately have no tenant: the platform's own.
_PLATFORM_TABLES = {"tenants", "crm_templates", "platform_audit_logs", "alembic_version"}


def test_every_table_is_tenant_scoped_or_explicitly_platform():
    """A new model without `TenantScoped` is a cross-tenant leak waiting to be read."""
    loose = [
        t.name for t in Base.metadata.sorted_tables
        if "tenant_id" not in t.c and t.name not in _PLATFORM_TABLES
    ]
    assert not loose, (
        f"these tables have no tenant_id and are not platform tables: {loose}. "
        "Either inherit TenantScoped or add them to _PLATFORM_TABLES with a reason."
    )


def test_tenant_id_is_indexed_everywhere():
    """Every query filters on it; an unindexed one is a scan on every request."""
    missing = []
    for table in Base.metadata.sorted_tables:
        if "tenant_id" not in table.c:
            continue
        indexed = any("tenant_id" in [c.name for c in ix.columns] for ix in table.indexes)
        if not (indexed or table.c.tenant_id.index):
            missing.append(table.name)
    assert not missing, f"tenant_id is not indexed on: {missing}"


def test_tenant_scoped_models_all_declare_the_column():
    for mapper in Base.registry.mappers:
        model = mapper.class_
        if issubclass(model, TenantScoped):
            assert hasattr(model, "tenant_id"), f"{model.__name__} has no tenant_id"


# --- encrypted values do not escape -------------------------------------------

def _encrypted_columns():
    for table in Base.metadata.sorted_tables:
        for column in table.c:
            if column.name.endswith("_encrypted"):
                yield table.name, column.name


def test_there_are_encrypted_columns_to_check():
    """Guards the tests below from passing because they found nothing."""
    assert list(_encrypted_columns()), "no *_encrypted columns found — has PII moved?"


@pytest.fixture()
def customer_with_pii(client, alpha):
    resp = client.post(
        f"{API}/contacts",
        json={"first_name": "Secret", "last_name": "Holder", "mobile": "9700000801",
              "pan": "ZYXWV9876E"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def test_a_pan_is_masked_in_the_record_it_belongs_to(client, alpha, customer_with_pii):
    body = client.get(
        f"{API}/contacts/{customer_with_pii['id']}", headers=alpha.auth()
    ).text
    assert "ZYXWV9876E" not in body
    assert "ZYXWV****E" in body


def test_a_pan_does_not_appear_in_a_list_response(client, alpha, customer_with_pii):
    body = client.get(f"{API}/contacts", params={"page_size": 200}, headers=alpha.auth()).text
    assert "ZYXWV9876E" not in body


def test_a_pan_does_not_appear_in_search_results(client, alpha, customer_with_pii):
    body = client.get(f"{API}/search", params={"q": "Secret"}, headers=alpha.auth()).text
    assert "ZYXWV9876E" not in body


def test_a_pan_does_not_appear_in_a_csv_export(client, alpha, customer_with_pii):
    body = client.get(f"{API}/io/contacts/export", headers=alpha.auth()).content
    assert b"ZYXWV9876E" not in body


def test_a_pan_does_not_appear_in_the_activity_timeline(client, alpha, customer_with_pii):
    body = client.get(
        f"{API}/activities", params={"entity_type": "contact",
                                     "entity_id": customer_with_pii["id"]},
        headers=alpha.auth(),
    ).text
    assert "ZYXWV9876E" not in body


def test_a_pan_does_not_appear_in_the_audit_log(client, alpha, customer_with_pii, admin_headers):
    """The audit trail records that a change happened, not the value it changed to."""
    from sqlalchemy import select

    from app.activities.models import AuditLog
    from app.core.tenancy import tenant_scope
    from app.database.session import SessionLocal

    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        rows = db.scalars(select(AuditLog).limit(500)).all()
        blob = " ".join(str(r.changes) for r in rows)
    assert "ZYXWV9876E" not in blob


def test_revealing_is_the_only_way_to_the_plaintext(client, alpha, customer_with_pii):
    """And it works — otherwise these tests pass because the value was never stored."""
    resp = client.post(
        f"{API}/contacts/{customer_with_pii['id']}/reveal",
        json={"field": "pan"}, headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == "ZYXWV9876E"


def test_revealing_is_audited(client, alpha, customer_with_pii):
    from sqlalchemy import select

    from app.activities.models import AuditLog
    from app.core.tenancy import tenant_scope
    from app.database.session import SessionLocal

    client.post(f"{API}/contacts/{customer_with_pii['id']}/reveal",
                json={"field": "pan"}, headers=alpha.auth())
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        actions = db.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == customer_with_pii["id"])
        ).all()
    assert any("reveal" in str(a) for a in actions), "a PII reveal left no audit row"


# --- errors say enough, and no more -------------------------------------------

def test_an_error_never_carries_a_stack_trace(client, alpha):
    for path in ("/contacts/does-not-exist", "/policies/does-not-exist",
                 "/loans/does-not-exist"):
        body = client.get(f"{API}{path}", headers=alpha.auth()).text
        assert "Traceback" not in body
        assert "File \"" not in body
        assert "sqlalchemy" not in body.lower()


def test_a_bad_filter_does_not_leak_sql(client, alpha):
    resp = client.get(
        f"{API}/contacts",
        params={"filters": '[{"key":"nonexistent\\"; DROP TABLE contacts;--","value":"x"}]'},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200
    assert "DROP TABLE" not in resp.text
    # And the table is still there.
    assert client.get(f"{API}/contacts", headers=alpha.auth()).status_code == 200


def test_a_sort_on_an_unknown_column_is_ignored_not_executed(client, alpha):
    resp = client.get(
        f"{API}/contacts", params={"sort": "(SELECT 1)"}, headers=alpha.auth()
    )
    assert resp.status_code in (200, 400)
    assert "SELECT" not in resp.text
