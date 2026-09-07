"""Templates, provisioning and per-tenant module configuration.

The question these answer: does creating a tenant from a template actually produce a
*different* CRM, and does the general template still reproduce the original one?
"""

import pytest

API = "/api/v1"


@pytest.fixture()
def admin_headers(platform_admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {platform_admin_token}"}


def _make_tenant(client, admin_headers, name, email, template_key):
    resp = client.post(
        f"{API}/platform/tenants",
        json={
            "name": name,
            "owner_email": email,
            "owner_password": "provision-pass-1",
            "template_key": template_key,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    signed_in = client.post(
        f"{API}/auth/login", json={"email": email, "password": "provision-pass-1"}
    )
    assert signed_in.status_code == 200, signed_in.text
    return resp.json(), {"Authorization": f"Bearer {signed_in.json()['access_token']}"}


# --- the templates themselves -------------------------------------------------

def test_system_templates_are_loaded(client, admin_headers):
    resp = client.get(f"{API}/platform/templates", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    by_key = {t["key"]: t for t in resp.json()}
    assert {"general_crm", "insurance_agent"} <= set(by_key)
    assert all(by_key[k]["is_system"] for k in ("general_crm", "insurance_agent"))
    # Each template switches off what its vertical does not use: the insurance one
    # drops Companies/Invoices/Projects/Support, the general one drops Policies.
    for key in ("insurance_agent", "general_crm"):
        assert by_key[key]["enabled_module_count"] < by_key[key]["module_count"]


def test_template_detail_carries_its_config(client, admin_headers):
    resp = client.get(f"{API}/platform/templates/insurance_agent", headers=admin_headers)
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config["key"] == "insurance_agent"
    labels = {m["key"]: m["label"] for m in config["modules"]}
    assert labels["contacts"] == "Customers"
    assert {"insurers", "banks", "relations"} <= set(config["masters"])


def test_tenant_user_cannot_read_templates(client, alpha):
    assert client.get(f"{API}/platform/templates", headers=alpha.auth()).status_code == 403


# --- what provisioning actually produces --------------------------------------

def test_insurance_tenant_gets_a_renamed_reshaped_crm(client, admin_headers):
    _, own = _make_tenant(
        client, admin_headers, "Sunrise Agency", "owner-sunrise@example.com", "insurance_agent"
    )

    modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()
    by_key = {m["module_key"]: m for m in modules}

    # Renamed, not reimplemented — the module key is unchanged.
    assert by_key["contacts"]["label"] == "Customers"
    assert by_key["leads"]["label"] == "Enquiries"
    assert by_key["products"]["label"] == "Plans"

    # Trimmed for an agent.
    assert by_key["invoices"]["enabled"] is False
    assert by_key["projects"]["enabled"] is False
    assert by_key["contacts"]["enabled"] is True

    # Insurance pipeline, not the generic sales one.
    stages = [s["name"] for s in client.get(f"{API}/deals/stages", headers=own).json()]
    assert "New enquiry" in stages and "Policy issued" in stages
    assert "Qualified" not in stages

    # Insurance roles and sources.
    roles = {r["name"] for r in client.get(f"{API}/roles", headers=own).json()}
    assert {"Agent", "Back Office", "Accounts"} <= roles
    sources = {s["name"] for s in client.get(f"{API}/leads/sources", headers=own).json()}
    assert {"Bank channel", "Renewal due"} <= sources


def test_general_tenant_still_matches_the_original_crm(client, admin_headers):
    """The regression guard: general_crm must reproduce the pre-template behaviour."""
    _, own = _make_tenant(
        client, admin_headers, "Plain Co", "owner-plain@example.com", "general_crm"
    )

    modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()
    enabled = {m["module_key"] for m in modules if m["enabled"]}
    # Every module the product shipped with before the insurance work.
    assert enabled == {
        "dashboard", "companies", "contacts", "leads", "deals", "pipeline", "calendar",
        "tasks", "projects", "products", "quotations", "invoices", "support", "reports", "settings",
    }
    # Policies is insurance-only and must not appear for a general CRM tenant.
    assert "policies" not in enabled
    by_key = {m["module_key"]: m["label"] for m in modules}
    assert by_key["contacts"] == "Contacts"

    stages = [s["name"] for s in client.get(f"{API}/deals/stages", headers=own).json()]
    assert stages[:3] == ["New", "Contacted", "Qualified"]

    roles = {r["name"] for r in client.get(f"{API}/roles", headers=own).json()}
    assert {"Super Admin", "Sales Manager", "Sales Executive", "Viewer"} <= roles

    templates = {t["name"] for t in client.get(f"{API}/settings/email-templates", headers=own).json()}
    assert {"welcome", "password_reset", "lead_assigned", "quotation"} <= templates


def test_insurance_masters_land_in_settings(client, admin_headers):
    _, own = _make_tenant(
        client, admin_headers, "Masters Agency", "owner-masters@example.com", "insurance_agent"
    )
    settings = {s["key"]: s["value"] for s in client.get(f"{API}/settings", headers=own).json()}
    assert "HDFC ERGO" in settings["masters"]["insurers"]
    # Full Aadhaar capture must be off unless a tenant deliberately opts in (PRD 9.4).
    assert settings["features"]["aadhaar_full_capture"] is False


def test_two_templates_produce_different_workspaces(client, admin_headers):
    _, insurance = _make_tenant(
        client, admin_headers, "Compare Agency", "owner-cmp-a@example.com", "insurance_agent"
    )
    _, general = _make_tenant(
        client, admin_headers, "Compare Co", "owner-cmp-b@example.com", "general_crm"
    )
    a = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=insurance).json()}
    b = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=general).json()}
    assert a != b
    assert a["contacts"] == "Customers" and b["contacts"] == "Contacts"


# --- module configuration -----------------------------------------------------

def test_module_list_defaults_to_enabled_only(client, alpha):
    enabled = client.get(f"{API}/modules", headers=alpha.auth()).json()
    everything = client.get(f"{API}/modules", params={"enabled_only": False}, headers=alpha.auth()).json()
    assert len(enabled) <= len(everything)
    assert all(m["enabled"] for m in enabled)
    # The catalog metadata the sidebar needs comes with it.
    assert all(m["route"] and m["icon"] for m in everything)


def test_tenant_admin_can_rename_a_module(client, alpha):
    modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=alpha.auth()).json()
    contacts = next(m for m in modules if m["module_key"] == "contacts")
    try:
        resp = client.patch(
            f"{API}/modules/{contacts['id']}", json={"label": "Policyholders"}, headers=alpha.auth()
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "Policyholders"
        again = client.get(f"{API}/modules", headers=alpha.auth()).json()
        assert any(m["label"] == "Policyholders" for m in again)
    finally:
        client.patch(f"{API}/modules/{contacts['id']}", json={"label": "Contacts"}, headers=alpha.auth())


def test_locked_modules_cannot_be_switched_off(client, alpha):
    modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=alpha.auth()).json()
    settings_module = next(m for m in modules if m["module_key"] == "settings")
    assert settings_module["locked"] is True
    resp = client.patch(
        f"{API}/modules/{settings_module['id']}", json={"enabled": False}, headers=alpha.auth()
    )
    assert resp.status_code == 400


def test_module_config_does_not_leak_between_tenants(client, alpha, bravo):
    alpha_modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=alpha.auth()).json()
    bravo_ids = {
        m["id"]
        for m in client.get(f"{API}/modules", params={"enabled_only": False}, headers=bravo.auth()).json()
    }
    assert not ({m["id"] for m in alpha_modules} & bravo_ids)

    target = next(m for m in alpha_modules if m["module_key"] == "leads")
    resp = client.patch(f"{API}/modules/{target['id']}", json={"label": "Stolen"}, headers=bravo.auth())
    assert resp.status_code == 404


def test_platform_admin_can_reconfigure_a_tenants_modules(client, admin_headers):
    created, own = _make_tenant(
        client, admin_headers, "Reconfig Co", "owner-reconfig@example.com", "general_crm"
    )
    tenant_id = created["id"]

    resp = client.patch(
        f"{API}/platform/tenants/{tenant_id}/modules",
        json=[
            {"module_key": "contacts", "label": "Members"},
            {"module_key": "projects", "enabled": False},
        ],
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    seen = {m["module_key"]: m for m in client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()}
    assert seen["contacts"]["label"] == "Members"
    assert seen["projects"]["enabled"] is False
    assert "projects" not in {m["module_key"] for m in client.get(f"{API}/modules", headers=own).json()}


# --- cloning and deleting templates -------------------------------------------

def test_clone_then_use_then_delete(client, admin_headers):
    clone = client.post(
        f"{API}/platform/templates/insurance_agent/clone",
        json={"key": "agency_lite", "name": "Agency Lite", "description": "Trimmed agency setup"},
        headers=admin_headers,
    )
    assert clone.status_code == 200, clone.text
    assert clone.json()["is_system"] is False
    assert clone.json()["config"]["key"] == "agency_lite"

    _, own = _make_tenant(
        client, admin_headers, "Lite Agency", "owner-lite@example.com", "agency_lite"
    )
    labels = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=own).json()}
    assert labels["contacts"] == "Customers"

    # In use, so it cannot be removed yet.
    assert client.delete(f"{API}/platform/templates/agency_lite", headers=admin_headers).status_code == 409


def test_duplicate_clone_key_is_rejected(client, admin_headers):
    first = client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "dupe_check", "name": "Dupe Check"},
        headers=admin_headers,
    )
    assert first.status_code == 200
    second = client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "dupe_check", "name": "Dupe Check Again"},
        headers=admin_headers,
    )
    assert second.status_code == 409


def test_system_templates_cannot_be_deleted(client, admin_headers):
    resp = client.delete(f"{API}/platform/templates/general_crm", headers=admin_headers)
    assert resp.status_code == 400


def test_unused_custom_template_can_be_deleted(client, admin_headers):
    client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "throwaway", "name": "Throwaway"},
        headers=admin_headers,
    )
    assert client.delete(f"{API}/platform/templates/throwaway", headers=admin_headers).status_code == 200
    assert client.get(f"{API}/platform/templates/throwaway", headers=admin_headers).status_code == 404


# --- re-applying a template to a live tenant ----------------------------------

def test_apply_template_is_additive_and_keeps_customisations(client, admin_headers):
    created, own = _make_tenant(
        client, admin_headers, "Switcher Co", "owner-switcher@example.com", "general_crm"
    )
    tenant_id = created["id"]

    modules = client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()
    contacts = next(m for m in modules if m["module_key"] == "contacts")
    client.patch(f"{API}/modules/{contacts['id']}", json={"label": "My Own Name"}, headers=own)

    resp = client.post(
        f"{API}/platform/tenants/{tenant_id}/apply-template",
        params={"template_key": "insurance_agent"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    after = {m["module_key"]: m for m in client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()}
    # The tenant's own rename survives — apply is additive, never destructive.
    assert after["contacts"]["label"] == "My Own Name"
    # …but new material from the template arrives.
    sources = {s["name"] for s in client.get(f"{API}/leads/sources", headers=own).json()}
    assert "Bank channel" in sources
    roles = {r["name"] for r in client.get(f"{API}/roles", headers=own).json()}
    assert "Back Office" in roles
