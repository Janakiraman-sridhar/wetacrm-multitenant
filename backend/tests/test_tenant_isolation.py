"""Tenant isolation: the tests Phase 0 exists to pass.

Each test signs in as tenant *alpha* and tries to reach something owned by tenant
*bravo*. Nothing may come back. The cases are grouped by the route a leak could
take, because they fail independently: a list endpoint, a detail lookup, a write,
a delete, an aggregate count, a CSV export, a file download, search, and following
a foreign key.
"""

import pytest

API = "/api/v1"

# (module path, id key in TenantWorld.ids, the field whose value identifies the row)
MODULES = [
    ("/companies", "company", "name"),
    ("/contacts", "contact", "first_name"),
    ("/leads", "lead", "title"),
    ("/deals", "deal", "title"),
    ("/tasks", "task", "title"),
    ("/products", "product", "name"),
    ("/projects", "project", "name"),
    ("/tickets", "ticket", "subject"),
    ("/quotations", "quotation", "number"),
    ("/invoices", "invoice", "number"),
    ("/documents", "document", "name"),
]


def _ids(payload) -> set[str]:
    items = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
    return {row["id"] for row in items if isinstance(row, dict) and "id" in row}


# --- lists -------------------------------------------------------------------

@pytest.mark.parametrize("path,key,_field", MODULES)
def test_list_shows_only_own_rows(client, alpha, bravo, path, key, _field):
    resp = client.get(f"{API}{path}", params={"page_size": 200}, headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    returned = _ids(resp.json())
    assert alpha.ids[key] in returned, f"{path}: tenant cannot see its own row"
    assert bravo.ids[key] not in returned, f"{path}: LEAK — other tenant's row is listed"


@pytest.mark.parametrize("path,key,_field", MODULES)
def test_list_total_counts_only_own_rows(client, alpha, bravo, path, key, _field):
    """The page total is a separate query from the rows — and a separate leak."""
    resp = client.get(f"{API}{path}", params={"page_size": 200}, headers=alpha.auth())
    body = resp.json()
    assert body["total"] == len(body["items"]), (
        f"{path}: total ({body['total']}) counts rows the tenant cannot see "
        f"({len(body['items'])} returned)"
    )


# --- detail, update, delete ---------------------------------------------------

@pytest.mark.parametrize("path,key,_field", MODULES)
def test_detail_of_other_tenant_row_is_not_found(client, alpha, bravo, path, key, _field):
    resp = client.get(f"{API}{path}/{bravo.ids[key]}", headers=alpha.auth())
    assert resp.status_code in (404, 405), f"{path}: LEAK — status {resp.status_code}"


@pytest.mark.parametrize("path,key,field", MODULES)
def test_update_of_other_tenant_row_is_rejected(client, alpha, bravo, path, key, field):
    resp = client.patch(f"{API}{path}/{bravo.ids[key]}", json={field: "hijacked"}, headers=alpha.auth())
    assert resp.status_code in (404, 405, 422), f"{path}: LEAK — status {resp.status_code}"


@pytest.mark.parametrize("path,key,_field", MODULES)
def test_delete_of_other_tenant_row_is_rejected(client, alpha, bravo, path, key, _field):
    resp = client.delete(f"{API}{path}/{bravo.ids[key]}", headers=alpha.auth())
    assert resp.status_code in (404, 405), f"{path}: LEAK — status {resp.status_code}"


# --- users, roles and reference data ------------------------------------------

def test_user_list_is_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/users", params={"page_size": 200}, headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    returned = _ids(resp.json())
    assert alpha.ids["user"] in returned
    assert bravo.ids["user"] not in returned


def test_users_all_is_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/users/all", headers=alpha.auth())
    assert resp.status_code == 200
    returned = {u["id"] for u in resp.json()}
    assert bravo.ids["user"] not in returned


def test_roles_are_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/roles", headers=alpha.auth())
    assert resp.status_code == 200
    returned = {r["id"] for r in resp.json()}
    assert alpha.ids["role"] in returned
    assert bravo.ids["role"] not in returned


def test_deal_stages_are_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/deals/stages", headers=alpha.auth())
    assert resp.status_code == 200
    returned = {s["id"] for s in resp.json()}
    assert bravo.ids["stage"] not in returned


def test_lead_sources_are_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/leads/sources", headers=alpha.auth())
    assert resp.status_code == 200
    returned = {s["id"] for s in resp.json()}
    assert bravo.ids["source"] not in returned


def test_tags_are_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/settings/tags", headers=alpha.auth())
    assert resp.status_code == 200
    returned = {t["id"] for t in resp.json()}
    assert bravo.ids["tag"] not in returned


def test_settings_are_tenant_scoped(client, alpha, bravo):
    """Two tenants hold the same settings key with different values."""
    resp = client.get(f"{API}/settings", headers=alpha.auth())
    assert resp.status_code == 200
    branding = [s for s in resp.json() if s["key"] == "branding"]
    assert branding, "tenant cannot read its own settings"
    assert branding[0]["value"]["app_name"] == "ALPHA CRM"
    assert len(branding) == 1, "LEAK — another tenant's settings row is visible"


def test_notifications_are_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/notifications", params={"page_size": 200}, headers=alpha.auth())
    assert resp.status_code == 200
    assert bravo.ids["notification"] not in _ids(resp.json())


# --- aggregates, pipeline, calendar, activities -------------------------------

def test_pipeline_columns_hold_only_own_deals(client, alpha, bravo):
    resp = client.get(f"{API}/deals/pipeline", headers=alpha.auth())
    assert resp.status_code == 200
    deal_ids = {d["id"] for column in resp.json() for d in column.get("deals", [])}
    assert bravo.ids["deal"] not in deal_ids


def test_calendar_is_tenant_scoped(client, alpha, bravo):
    resp = client.get(
        f"{API}/calendar", params={"start": "2026-01-01", "end": "2026-12-31"}, headers=alpha.auth()
    )
    assert resp.status_code == 200
    ids = {item.get("id") for item in resp.json()}
    assert bravo.ids["meeting"] not in ids
    assert bravo.ids["calendar_event"] not in ids


def test_dashboard_counts_exclude_other_tenants(client, alpha, bravo):
    resp = client.get(f"{API}/reports/dashboard", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    kpis = body.get("kpis", body)
    # Each tenant seeded exactly one deal, one lead and one company.
    for field, expected in (("open_deals", 1), ("active_leads", 1)):
        if field in kpis:
            assert kpis[field] <= expected, f"{field} counts other tenants' rows"


def test_audit_log_is_tenant_scoped(client, alpha, bravo):
    resp = client.get(f"{API}/audit-logs", params={"page_size": 200}, headers=alpha.auth())
    assert resp.status_code == 200
    for row in resp.json()["items"]:
        assert row.get("user_id") != bravo.ids["user"]


# --- search -------------------------------------------------------------------

def test_search_does_not_cross_tenants(client, alpha, bravo):
    resp = client.get(f"{API}/search", params={"q": "bravo"}, headers=alpha.auth())
    assert resp.status_code == 200
    hits = [hit for group in resp.json()["results"].values() for hit in group]
    assert not hits, f"LEAK — search returned another tenant's records: {hits}"

    own = client.get(f"{API}/search", params={"q": "alpha"}, headers=alpha.auth())
    assert any(
        hit for group in own.json()["results"].values() for hit in group
    ), "search returns nothing for the tenant's own data"


# --- CSV export and import ----------------------------------------------------

@pytest.mark.parametrize("entity,needle", [
    ("companies", "bravo-corp"),
    ("leads", "bravo-lead"),
    ("deals", "bravo-deal"),
    ("contacts", "bravo"),
])
def test_csv_export_excludes_other_tenants(client, alpha, entity, needle):
    resp = client.get(f"{API}/io/{entity}/export", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    assert needle not in resp.text, f"LEAK — {entity} export contains {needle}"


# --- file download ------------------------------------------------------------

def test_document_download_of_other_tenant_is_refused(client, alpha, bravo):
    resp = client.get(f"{API}/documents/{bravo.ids['document']}/download", headers=alpha.auth())
    assert resp.status_code in (403, 404), f"LEAK — status {resp.status_code}"


# --- token and tenant integrity ----------------------------------------------

def test_no_token_is_rejected(client, bravo):
    assert client.get(f"{API}/companies").status_code == 401


def test_token_cannot_be_reused_against_another_tenants_row(client, alpha, bravo):
    """The core promise: a valid token plus a known id from elsewhere yields nothing."""
    resp = client.get(f"{API}/companies/{bravo.ids['company']}", headers=alpha.auth())
    assert resp.status_code == 404


def test_suspended_tenant_cannot_sign_in(client, worlds, platform_admin_token):
    from tests.conftest import PASSWORD

    bravo = worlds["bravo"]
    admin_headers = {"Authorization": f"Bearer {platform_admin_token}"}
    suspend = client.post(
        f"{API}/platform/tenants/{bravo.tenant_id}/suspend", headers=admin_headers
    )
    assert suspend.status_code == 200, suspend.text
    try:
        blocked = client.post(
            f"{API}/auth/login", json={"email": bravo.admin_email, "password": PASSWORD}
        )
        assert blocked.status_code == 403
    finally:
        client.post(f"{API}/platform/tenants/{bravo.tenant_id}/reactivate", headers=admin_headers)


# --- platform console ---------------------------------------------------------

def test_tenant_user_cannot_reach_platform_api(client, alpha):
    assert client.get(f"{API}/platform/tenants", headers=alpha.auth()).status_code == 403


def test_platform_admin_sees_all_tenants(client, platform_admin_token):
    resp = client.get(
        f"{API}/platform/tenants", headers={"Authorization": f"Bearer {platform_admin_token}"}
    )
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()}
    assert {"alpha", "bravo"} <= slugs


def test_platform_admin_cannot_use_tenant_endpoints_without_impersonating(client, platform_admin_token):
    resp = client.get(
        f"{API}/companies", headers={"Authorization": f"Bearer {platform_admin_token}"}
    )
    assert resp.status_code in (401, 403)


def test_impersonation_grants_exactly_one_tenant(client, platform_admin_token, alpha, bravo):
    resp = client.post(
        f"{API}/platform/tenants/{alpha.tenant_id}/impersonate",
        json={},
        headers={"Authorization": f"Bearer {platform_admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    seen = _ids(client.get(f"{API}/companies", params={"page_size": 200}, headers=headers).json())
    assert alpha.ids["company"] in seen
    assert bravo.ids["company"] not in seen


# --- provisioning a tenant through the platform API ---------------------------

def test_provisioned_tenant_is_seeded_and_isolated(client, platform_admin_token, alpha):
    """End-to-end: create a tenant the way the console will, then use it.

    Covers the case the fixtures cannot — `provision_tenant` running for real —
    which is where a per-tenant seed that creates a globally-unique user breaks.
    """
    headers = {"Authorization": f"Bearer {platform_admin_token}"}
    created = client.post(
        f"{API}/platform/tenants",
        json={
            "name": "Charlie Agency",
            "type": "individual",
            "owner_email": "owner-charlie@example.com",
            "owner_password": "charlie-password-1",
            "owner_first_name": "Charlie",
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["slug"] == "charlie-agency"
    assert body["user_count"] == 1

    signed_in = client.post(
        f"{API}/auth/login",
        json={"email": "owner-charlie@example.com", "password": "charlie-password-1"},
    )
    assert signed_in.status_code == 200, signed_in.text
    own = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}

    # Seeded reference data is present…
    stages = client.get(f"{API}/deals/stages", headers=own)
    assert {s["name"] for s in stages.json()} >= {"New", "Won", "Lost"}
    roles = client.get(f"{API}/roles", headers=own)
    assert "Super Admin" in {r["name"] for r in roles.json()}

    # …and the new tenant starts empty, seeing nothing from anyone else.
    for path in ("/companies", "/leads", "/deals", "/contacts"):
        listing = client.get(f"{API}{path}", headers=own).json()
        assert listing["total"] == 0, f"{path}: new tenant is not empty"

    assert client.get(f"{API}/companies/{alpha.ids['company']}", headers=own).status_code == 404


def test_duplicate_owner_email_is_rejected(client, platform_admin_token, alpha):
    resp = client.post(
        f"{API}/platform/tenants",
        json={"name": "Clash Agency", "owner_email": alpha.admin_email, "owner_password": "another-pass-1"},
        headers={"Authorization": f"Bearer {platform_admin_token}"},
    )
    assert resp.status_code == 409
