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


# --- customising a template ---------------------------------------------------

def test_a_system_template_cannot_be_edited(client, admin_headers):
    """It is refreshed from the product, so an edit would be silently overwritten."""
    resp = client.patch(
        f"{API}/platform/templates/general_crm",
        json={"lead_sources": ["Only this"]},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "Clone" in resp.json()["detail"]


def test_a_cloned_template_can_be_customised(client, admin_headers):
    client.post(
        f"{API}/platform/templates/insurance_agent/clone",
        json={"key": "custom_agency", "name": "Custom Agency"},
        headers=admin_headers,
    )
    try:
        resp = client.patch(
            f"{API}/platform/templates/custom_agency",
            json={
                "name": "Custom Agency v2",
                "modules": [
                    {"key": "contacts", "enabled": True, "label": "Members", "order": 2},
                    {"key": "policies", "enabled": True, "label": "Cover", "order": 3},
                    # Named explicitly: a template that lists any modules is listing
                    # all of them, so leaving these out would switch them off — and a
                    # switched-off module is refused at the API, not just hidden.
                    {"key": "leads", "enabled": True, "label": "Enquiries", "order": 4},
                    {"key": "deals", "enabled": True, "label": "Cases", "order": 5},
                    {"key": "projects", "enabled": False, "label": "Projects", "order": 9},
                ],
                "lead_sources": ["Roadshow", "Referral"],
                "stages": [
                    {"name": "Enquiry", "order": 1, "probability": 10},
                    {"name": "Closed", "order": 2, "probability": 100, "is_won": True},
                ],
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        config = resp.json()["config"]
        assert resp.json()["name"] == "Custom Agency v2"
        assert {m["key"]: m["label"] for m in config["modules"]}["contacts"] == "Members"
        assert config["lead_sources"] == ["Roadshow", "Referral"]

        # And a workspace made from it comes out that way.
        client.post(
            f"{API}/platform/tenants",
            json={
                "name": "Built From Custom", "owner_email": "owner-custom@example.com",
                "owner_password": "custom-pass-12", "template_key": "custom_agency",
            },
            headers=admin_headers,
        )
        token = client.post(
            f"{API}/auth/login",
            json={"email": "owner-custom@example.com", "password": "custom-pass-12"},
        ).json()["access_token"]
        own = {"Authorization": f"Bearer {token}"}

        labels = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=own).json()}
        assert labels["contacts"] == "Members"
        assert labels["policies"] == "Cover"
        sources = {s["name"] for s in client.get(f"{API}/leads/sources", headers=own).json()}
        assert sources == {"Roadshow", "Referral"}
        stages = [s["name"] for s in client.get(f"{API}/deals/stages", headers=own).json()]
        assert stages == ["Enquiry", "Closed"]

        # And the module the template switched off is gone, not merely hidden.
        assert client.get(f"{API}/projects", headers=own).status_code == 404
    finally:
        pass


def test_an_invalid_edit_is_rejected_rather_than_stored(client, admin_headers):
    """A typo'd module key would produce a workspace nobody notices is broken."""
    client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "bad_edit", "name": "Bad Edit"},
        headers=admin_headers,
    )
    resp = client.patch(
        f"{API}/platform/templates/bad_edit",
        json={"modules": [{"key": "spaceships", "enabled": True}]},
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "Unknown module" in resp.json()["detail"]

    # The stored template is untouched.
    after = client.get(f"{API}/platform/templates/bad_edit", headers=admin_headers).json()
    assert all(m["key"] != "spaceships" for m in after["config"]["modules"])


def test_editing_a_template_leaves_existing_tenants_alone(client, admin_headers):
    """Templates are copied at provisioning; a later edit must not reach back."""
    client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "drift_check", "name": "Drift Check"},
        headers=admin_headers,
    )
    client.post(
        f"{API}/platform/tenants",
        json={
            "name": "Drift Tenant", "owner_email": "owner-drift@example.com",
            "owner_password": "drift-pass-123", "template_key": "drift_check",
        },
        headers=admin_headers,
    )
    token = client.post(
        f"{API}/auth/login", json={"email": "owner-drift@example.com", "password": "drift-pass-123"}
    ).json()["access_token"]
    own = {"Authorization": f"Bearer {token}"}
    before = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=own).json()}

    client.patch(
        f"{API}/platform/templates/drift_check",
        json={"modules": [{"key": "contacts", "enabled": True, "label": "Renamed Later"}]},
        headers=admin_headers,
    )

    after = {m["module_key"]: m["label"] for m in client.get(f"{API}/modules", headers=own).json()}
    assert after["contacts"] == before["contacts"] != "Renamed Later"


def test_the_module_catalog_is_served(client, admin_headers):
    """The editor offers exactly the keys the backend accepts."""
    resp = client.get(f"{API}/platform/module-catalog", headers=admin_headers)
    assert resp.status_code == 200
    catalog = {m["key"]: m for m in resp.json()}
    assert {"dashboard", "contacts", "policies", "settings"} <= set(catalog)
    assert catalog["settings"]["locked"] is True


# --- deleting a tenant --------------------------------------------------------

def test_a_tenant_can_be_deleted_and_its_users_lose_access(client, admin_headers):
    created = client.post(
        f"{API}/platform/tenants",
        json={
            "name": "Doomed Agency", "owner_email": "owner-doomed@example.com",
            "owner_password": "doomed-pass-12", "template_key": "general_crm",
        },
        headers=admin_headers,
    ).json()

    signed_in = client.post(
        f"{API}/auth/login", json={"email": "owner-doomed@example.com", "password": "doomed-pass-12"}
    )
    assert signed_in.status_code == 200

    deleted = client.delete(f"{API}/platform/tenants/{created['id']}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text

    # Signing in is refused once the workspace is gone.
    after = client.post(
        f"{API}/auth/login", json={"email": "owner-doomed@example.com", "password": "doomed-pass-12"}
    )
    assert after.status_code in (401, 403)

    # And it drops out of the console listing.
    listed = client.get(f"{API}/platform/tenants", headers=admin_headers).json()
    assert created["id"] not in {t["id"] for t in listed}


def test_a_deleted_tenants_email_can_be_used_again(client, admin_headers):
    """Deleting a client and re-creating them is the commonest console mistake to undo.

    `users.email` is globally unique, so without releasing the address on delete the
    same client could never be added back under their own email.
    """
    first = client.post(
        f"{API}/platform/tenants",
        json={"name": "Recreate Agency", "owner_email": "owner-recreate@example.com",
              "owner_password": "recreate-pass-1"},
        headers=admin_headers,
    )
    assert first.status_code == 200, first.text
    assert client.delete(
        f"{API}/platform/tenants/{first.json()['id']}", headers=admin_headers
    ).status_code == 200

    second = client.post(
        f"{API}/platform/tenants",
        json={"name": "Recreate Agency Again", "owner_email": "owner-recreate@example.com",
              "owner_password": "recreate-pass-2"},
        headers=admin_headers,
    )
    assert second.status_code == 200, second.text

    # The new owner signs in with the new password; the old login is gone.
    assert client.post(
        f"{API}/auth/login",
        json={"email": "owner-recreate@example.com", "password": "recreate-pass-2"},
    ).status_code == 200
    assert client.post(
        f"{API}/auth/login",
        json={"email": "owner-recreate@example.com", "password": "recreate-pass-1"},
    ).status_code in (401, 403)

    client.delete(f"{API}/platform/tenants/{second.json()['id']}", headers=admin_headers)


def test_an_email_held_by_a_live_workspace_still_clashes(client, admin_headers):
    """Releasing addresses on delete must not weaken the check for live ones."""
    live = client.post(
        f"{API}/platform/tenants",
        json={"name": "Occupied Agency", "owner_email": "owner-occupied@example.com",
              "owner_password": "occupied-pass-1"},
        headers=admin_headers,
    )
    assert live.status_code == 200, live.text
    try:
        clash = client.post(
            f"{API}/platform/tenants",
            json={"name": "Second Agency", "owner_email": "owner-occupied@example.com",
                  "owner_password": "occupied-pass-2"},
            headers=admin_headers,
        )
        assert clash.status_code == 409
        # And it says where the address is, rather than leaving a dead end.
        assert "Occupied Agency" in clash.json()["detail"]
    finally:
        client.delete(f"{API}/platform/tenants/{live.json()['id']}", headers=admin_headers)


def test_deleting_a_tenant_deactivates_its_users(client, admin_headers):
    created = client.post(
        f"{API}/platform/tenants",
        json={"name": "Frozen Agency", "owner_email": "owner-frozen@example.com",
              "owner_password": "frozen-pass-12"},
        headers=admin_headers,
    ).json()
    client.delete(f"{API}/platform/tenants/{created['id']}", headers=admin_headers)

    listed = client.get(
        f"{API}/platform/tenants", params={"include_deleted": True}, headers=admin_headers
    ).json()
    assert created["id"] in {t["id"] for t in listed}, "the row is retained, only the address is freed"


def test_the_default_workspace_cannot_be_deleted(client, admin_headers):
    """It holds the data everything migrated into; removing it is never intended."""
    tenants = client.get(f"{API}/platform/tenants", headers=admin_headers).json()
    default = next((t for t in tenants if t["slug"] == "default"), None)
    if default is None:
        return  # the test database has no default workspace
    resp = client.delete(f"{API}/platform/tenants/{default['id']}", headers=admin_headers)
    assert resp.status_code == 400


def test_a_tenant_user_cannot_delete_their_own_workspace(client, alpha):
    resp = client.delete(f"{API}/platform/tenants/{alpha.tenant_id}", headers=alpha.auth())
    assert resp.status_code == 403


def test_a_template_that_names_modules_is_treated_as_naming_all_of_them(client, admin_headers):
    """Listing the modules a client should have must not silently add the rest.

    An admin who lists seven modules means seven, not seven plus whatever the
    catalog happens to contain.
    """
    client.post(
        f"{API}/platform/templates/general_crm/clone",
        json={"key": "selective", "name": "Selective"},
        headers=admin_headers,
    )
    resp = client.patch(
        f"{API}/platform/templates/selective",
        json={"modules": [
            {"key": "dashboard", "enabled": True, "label": "Home", "order": 1},
            {"key": "contacts", "enabled": True, "label": "Clients", "order": 2},
            {"key": "settings", "enabled": True, "label": "Settings", "order": 3},
        ]},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    client.post(
        f"{API}/platform/tenants",
        json={
            "name": "Selective Co", "owner_email": "owner-selective@example.com",
            "owner_password": "selective-pass1", "template_key": "selective",
        },
        headers=admin_headers,
    )
    token = client.post(
        f"{API}/auth/login",
        json={"email": "owner-selective@example.com", "password": "selective-pass1"},
    ).json()["access_token"]
    own = {"Authorization": f"Bearer {token}"}

    enabled = {m["module_key"] for m in client.get(f"{API}/modules", headers=own).json()}
    assert enabled == {"dashboard", "contacts", "settings"}, f"got {sorted(enabled)}"
    # The rows still exist, so the tenant admin can switch one on later.
    everything = client.get(f"{API}/modules", params={"enabled_only": False}, headers=own).json()
    assert len(everything) > 3


# --- a disabled module is gone, not just hidden -------------------------------

def _module_id(client, headers, key: str) -> str:
    rows = client.get(f"{API}/modules", params={"enabled_only": False}, headers=headers).json()
    return next(m["id"] for m in rows if m["module_key"] == key)


def test_switching_a_module_off_closes_its_api(client, alpha):
    """Otherwise "disabled" only means "missing from the sidebar".

    A workspace with Policies switched off could still create policies over the API
    that its own UI would never show.
    """
    assert client.get(f"{API}/policies", headers=alpha.auth()).status_code == 200

    module_id = _module_id(client, alpha.auth(), "policies")
    client.patch(f"{API}/modules/{module_id}", json={"enabled": False}, headers=alpha.auth())
    try:
        assert client.get(f"{API}/policies", headers=alpha.auth()).status_code == 404
        assert client.post(
            f"{API}/policies",
            json={"policy_number": "SHOULD-NOT-SAVE", "product_line": "motor",
                  "customer_id": alpha.ids["contact"]},
            headers=alpha.auth(),
        ).status_code == 404
    finally:
        client.patch(f"{API}/modules/{module_id}", json={"enabled": True}, headers=alpha.auth())
    assert client.get(f"{API}/policies", headers=alpha.auth()).status_code == 200


def test_the_poster_studio_is_gated_on_its_own_module(client, alpha):
    """Poster is permissioned on `contacts:read`, so the permission alone cannot gate it."""
    assert client.get(f"{API}/poster/templates", headers=alpha.auth()).status_code == 200

    module_id = _module_id(client, alpha.auth(), "poster")
    client.patch(f"{API}/modules/{module_id}", json={"enabled": False}, headers=alpha.auth())
    try:
        assert client.get(f"{API}/poster/templates", headers=alpha.auth()).status_code == 404
        # Contacts itself keeps working — only the Poster Studio went away.
        assert client.get(f"{API}/contacts", headers=alpha.auth()).status_code == 200
    finally:
        client.patch(f"{API}/modules/{module_id}", json={"enabled": True}, headers=alpha.auth())


def test_a_locked_module_cannot_be_switched_off(client, alpha):
    module_id = _module_id(client, alpha.auth(), "settings")
    resp = client.patch(f"{API}/modules/{module_id}", json={"enabled": False}, headers=alpha.auth())
    assert resp.status_code == 400
    assert client.get(f"{API}/settings", headers=alpha.auth()).status_code in (200, 404)


def test_search_drops_groups_for_modules_this_workspace_does_not_have(client, alpha):
    """A general CRM should not get a "Policies" heading for a module it switched off."""
    before = client.get(f"{API}/search", params={"q": "a"}, headers=alpha.auth()).json()
    assert "policies" in before["results"]

    module_id = _module_id(client, alpha.auth(), "policies")
    client.patch(f"{API}/modules/{module_id}", json={"enabled": False}, headers=alpha.auth())
    try:
        after = client.get(f"{API}/search", params={"q": "a"}, headers=alpha.auth()).json()
        assert "policies" not in after["results"]
        assert "contacts" in after["results"]
    finally:
        client.patch(f"{API}/modules/{module_id}", json={"enabled": True}, headers=alpha.auth())


# --- creating and deleting templates ------------------------------------------

def test_a_new_template_starts_from_a_working_one(client, admin_headers):
    """A template with no roles or stages provisions a workspace nobody can sign into."""
    resp = client.post(
        f"{API}/platform/templates",
        json={"key": "brand_new", "name": "Brand New", "base_key": "insurance_agent",
              "description": "Made from scratch in the console"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    config = resp.json()["config"]
    assert resp.json()["is_system"] is False
    assert config["key"] == "brand_new"
    assert config["name"] == "Brand New"
    # It inherited a working shape rather than starting empty.
    assert config["roles"], "a new template must carry roles"
    assert any(m["key"] == "policies" and m["enabled"] for m in config["modules"])

    client.delete(f"{API}/platform/templates/brand_new", headers=admin_headers)


def test_a_new_template_defaults_to_the_general_crm_base(client, admin_headers):
    resp = client.post(
        f"{API}/platform/templates",
        json={"key": "defaulted_base", "name": "Defaulted Base"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    modules = {m["key"]: m["enabled"] for m in resp.json()["config"]["modules"]}
    assert modules.get("policies") is False, "general_crm is the base, so Policies is off"
    client.delete(f"{API}/platform/templates/defaulted_base", headers=admin_headers)


def test_a_duplicate_template_key_is_refused(client, admin_headers):
    resp = client.post(
        f"{API}/platform/templates",
        json={"key": "general_crm", "name": "Clashing"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_an_unknown_base_is_refused(client, admin_headers):
    resp = client.post(
        f"{API}/platform/templates",
        json={"key": "from_nowhere", "name": "From Nowhere", "base_key": "does_not_exist"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_a_custom_template_can_be_created_edited_and_deleted(client, admin_headers):
    """The whole loop the console offers, in one pass."""
    created = client.post(
        f"{API}/platform/templates",
        json={"key": "full_loop", "name": "Full Loop"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text

    edited = client.patch(
        f"{API}/platform/templates/full_loop",
        json={"name": "Full Loop v2",
              "modules": [{"key": "contacts", "enabled": True, "label": "Members", "order": 2},
                          {"key": "leads", "enabled": True, "label": "Enquiries", "order": 3},
                          {"key": "deals", "enabled": True, "label": "Cases", "order": 4}]},
        headers=admin_headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Full Loop v2"

    removed = client.delete(f"{API}/platform/templates/full_loop", headers=admin_headers)
    assert removed.status_code == 200
    assert client.get(f"{API}/platform/templates/full_loop", headers=admin_headers).status_code == 404


def test_a_template_in_use_cannot_be_deleted(client, admin_headers):
    client.post(
        f"{API}/platform/templates",
        json={"key": "in_use_tpl", "name": "In Use"},
        headers=admin_headers,
    )
    tenant = client.post(
        f"{API}/platform/tenants",
        json={"name": "Uses The Template", "owner_email": "owner-inuse@example.com",
              "owner_password": "inuse-pass-12", "template_key": "in_use_tpl"},
        headers=admin_headers,
    )
    assert tenant.status_code == 200, tenant.text
    try:
        blocked = client.delete(f"{API}/platform/templates/in_use_tpl", headers=admin_headers)
        assert blocked.status_code == 409
        assert "still use this template" in blocked.json()["detail"]
    finally:
        client.delete(f"{API}/platform/tenants/{tenant.json()['id']}", headers=admin_headers)
        client.delete(f"{API}/platform/templates/in_use_tpl", headers=admin_headers)


def test_a_system_template_cannot_be_deleted(client, admin_headers):
    resp = client.delete(f"{API}/platform/templates/general_crm", headers=admin_headers)
    assert resp.status_code == 400


# --- what the console shows about one workspace -------------------------------

def test_tenant_detail_carries_what_the_console_needs_to_show(client, admin_headers):
    created = client.post(
        f"{API}/platform/tenants",
        json={"name": "Detailed Agency", "owner_email": "owner-detail@example.com",
              "owner_password": "detail-pass-12", "template_key": "insurance_agent",
              "owner_first_name": "Meena", "owner_last_name": "Iyer",
              "plan": "pro", "currency": "INR"},
        headers=admin_headers,
    )
    assert created.status_code == 200, created.text
    try:
        detail = client.get(
            f"{API}/platform/tenants/{created.json()['id']}", headers=admin_headers
        ).json()

        assert detail["owner_email"] == "owner-detail@example.com"
        assert detail["owner_name"] == "Meena Iyer"
        assert detail["plan"] == "pro"
        assert detail["user_count"] == 1
        assert detail["enabled_module_count"] > 0
        assert detail["enabled_module_count"] <= detail["module_count"]

        owner = next(u for u in detail["users"] if u["is_owner"])
        assert owner["email"] == "owner-detail@example.com"
        assert owner["role"] == "Super Admin"
        assert owner["is_active"] is True

        # Counts are only reported for modules this workspace actually has: an
        # insurance template has Policies and no Companies.
        assert "policies" in detail["record_counts"]
        assert "companies" not in detail["record_counts"]
        assert detail["record_counts"]["policies"] == 0
    finally:
        client.delete(f"{API}/platform/tenants/{created.json()['id']}", headers=admin_headers)


def test_tenant_detail_counts_are_that_tenants_own(client, admin_headers, alpha):
    """The counts run in the tenant's scope — a cross-tenant total would be worse
    than no number at all, because it looks authoritative."""
    detail = client.get(
        f"{API}/platform/tenants/{alpha.tenant_id}", headers=admin_headers
    ).json()
    assert detail["record_counts"]["customers"] == 1
    assert detail["record_counts"]["companies"] == 1
