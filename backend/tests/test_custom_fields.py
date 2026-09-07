"""Per-tenant custom fields.

The two questions worth answering: does a field one tenant adds actually work
everywhere (form, record, table, filter, export), and is it genuinely invisible to
every other tenant?
"""

import pytest

API = "/api/v1"


def _add_field(client, world, module, **kwargs):
    payload = {"key": "policy_number", "label": "Policy number", "field_type": "text", **kwargs}
    resp = client.post(f"{API}/schema/{module}/fields", json=payload, headers=world.auth())
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def alpha_field(client, alpha):
    """A custom text field on alpha's Companies, removed again afterwards."""
    _add_field(client, alpha, "companies", show_in_table=True, filterable=True)
    yield "policy_number"
    client.delete(f"{API}/schema/companies/fields/policy_number", headers=alpha.auth())


# --- the schema endpoint ------------------------------------------------------

def test_schema_lists_base_fields_derived_from_the_model(client, alpha):
    resp = client.get(f"{API}/schema/companies", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    fields = {f["key"]: f for f in resp.json()["fields"]}
    assert {"name", "industry", "website", "city", "owner_id"} <= set(fields)
    # Plumbing columns are not fields anyone should configure.
    assert not ({"id", "created_at", "updated_at", "tenant_id", "custom"} & set(fields))
    # Types are inferred from the column.
    assert fields["notes"]["type"] == "textarea"
    assert fields["owner_id"]["type"] == "select"
    assert fields["email"]["type"] == "email"


def test_name_is_locked_on_companies(client, alpha):
    fields = {f["key"]: f for f in client.get(f"{API}/schema/companies", headers=alpha.auth()).json()["fields"]}
    assert fields["name"]["locked"] is True
    resp = client.patch(
        f"{API}/schema/companies/fields/name", json={"is_active": False}, headers=alpha.auth()
    )
    assert resp.status_code == 400


def test_unknown_module_is_rejected(client, alpha):
    assert client.get(f"{API}/schema/unicorns", headers=alpha.auth()).status_code == 404


# --- adding a field -----------------------------------------------------------

def test_added_field_appears_in_the_schema(client, alpha, alpha_field):
    fields = {f["key"]: f for f in client.get(f"{API}/schema/companies", headers=alpha.auth()).json()["fields"]}
    assert fields["policy_number"]["is_custom"] is True
    assert fields["policy_number"]["label"] == "Policy number"


def test_field_key_cannot_collide_with_a_base_field(client, alpha):
    resp = client.post(
        f"{API}/schema/companies/fields",
        json={"key": "industry", "label": "Industry", "field_type": "text"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "built-in" in resp.json()["detail"]


def test_duplicate_key_is_rejected(client, alpha, alpha_field):
    resp = client.post(
        f"{API}/schema/companies/fields",
        json={"key": "policy_number", "label": "Again", "field_type": "text"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 409


def test_dropdown_needs_options(client, alpha):
    resp = client.post(
        f"{API}/schema/companies/fields",
        json={"key": "no_options", "label": "No options", "field_type": "select", "options": []},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


def test_invalid_key_is_rejected(client, alpha):
    resp = client.post(
        f"{API}/schema/companies/fields",
        json={"key": "Bad Key!", "label": "Bad", "field_type": "text"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


# --- storing and reading values -----------------------------------------------

def test_value_round_trips_through_create_and_edit(client, alpha, alpha_field):
    created = client.post(
        f"{API}/companies",
        json={"name": "Custom Co", "custom": {"policy_number": "POL-123"}},
        headers=alpha.auth(),
    )
    assert created.status_code == 200, created.text
    company_id = created.json()["id"]
    try:
        fetched = client.get(f"{API}/companies/{company_id}", headers=alpha.auth()).json()
        assert fetched["custom"]["policy_number"] == "POL-123"

        updated = client.patch(
            f"{API}/companies/{company_id}",
            json={"custom": {"policy_number": "POL-999"}},
            headers=alpha.auth(),
        )
        assert updated.status_code == 200
        assert updated.json()["custom"]["policy_number"] == "POL-999"
    finally:
        client.delete(f"{API}/companies/{company_id}", headers=alpha.auth())


def test_undeclared_keys_are_dropped_not_stored(client, alpha, alpha_field):
    """A stale form should not block a save, nor smuggle in undeclared data."""
    created = client.post(
        f"{API}/companies",
        json={"name": "Dropper Co", "custom": {"policy_number": "P-1", "not_a_field": "junk"}},
        headers=alpha.auth(),
    )
    assert created.status_code == 200, created.text
    try:
        stored = created.json()["custom"]
        assert stored["policy_number"] == "P-1"
        assert "not_a_field" not in stored
    finally:
        client.delete(f"{API}/companies/{created.json()['id']}", headers=alpha.auth())


def test_typed_field_rejects_a_bad_value(client, alpha):
    client.post(
        f"{API}/schema/companies/fields",
        json={"key": "premium", "label": "Premium", "field_type": "number"},
        headers=alpha.auth(),
    )
    try:
        resp = client.post(
            f"{API}/companies",
            json={"name": "Bad Number Co", "custom": {"premium": "not-a-number"}},
            headers=alpha.auth(),
        )
        assert resp.status_code == 400
        assert "Premium" in resp.json()["detail"]
    finally:
        client.delete(f"{API}/schema/companies/fields/premium", headers=alpha.auth())


def test_dropdown_rejects_a_value_outside_its_options(client, alpha):
    client.post(
        f"{API}/schema/companies/fields",
        json={
            "key": "segment", "label": "Segment", "field_type": "select",
            "options": [{"value": "smb", "label": "SMB"}, {"value": "ent", "label": "Enterprise"}],
        },
        headers=alpha.auth(),
    )
    try:
        bad = client.post(
            f"{API}/companies",
            json={"name": "Bad Segment Co", "custom": {"segment": "wholesale"}},
            headers=alpha.auth(),
        )
        assert bad.status_code == 400

        good = client.post(
            f"{API}/companies",
            json={"name": "Good Segment Co", "custom": {"segment": "ent"}},
            headers=alpha.auth(),
        )
        assert good.status_code == 200
        client.delete(f"{API}/companies/{good.json()['id']}", headers=alpha.auth())
    finally:
        client.delete(f"{API}/schema/companies/fields/segment", headers=alpha.auth())


def test_required_custom_field_is_enforced(client, alpha):
    client.post(
        f"{API}/schema/companies/fields",
        json={"key": "must_have", "label": "Must have", "field_type": "text", "required": True},
        headers=alpha.auth(),
    )
    try:
        resp = client.post(f"{API}/companies", json={"name": "Missing Co"}, headers=alpha.auth())
        assert resp.status_code == 400
        assert "Must have" in resp.json()["detail"]
    finally:
        client.delete(f"{API}/schema/companies/fields/must_have", headers=alpha.auth())


# --- isolation: the point of the whole design ---------------------------------

def test_a_field_added_by_one_tenant_is_invisible_to_another(client, alpha, bravo, alpha_field):
    alpha_keys = {f["key"] for f in client.get(f"{API}/schema/companies", headers=alpha.auth()).json()["fields"]}
    bravo_keys = {f["key"] for f in client.get(f"{API}/schema/companies", headers=bravo.auth()).json()["fields"]}
    assert "policy_number" in alpha_keys
    assert "policy_number" not in bravo_keys, "LEAK — another tenant sees this field"


def test_another_tenant_cannot_edit_or_delete_the_field(client, alpha, bravo, alpha_field):
    assert client.patch(
        f"{API}/schema/companies/fields/policy_number", json={"label": "Hijacked"}, headers=bravo.auth()
    ).status_code in (400, 404)
    assert client.delete(
        f"{API}/schema/companies/fields/policy_number", headers=bravo.auth()
    ).status_code == 404
    # Still alpha's, still named the same.
    fields = {f["key"]: f for f in client.get(f"{API}/schema/companies", headers=alpha.auth()).json()["fields"]}
    assert fields["policy_number"]["label"] == "Policy number"


def test_values_do_not_cross_tenants(client, alpha, bravo, alpha_field):
    created = client.post(
        f"{API}/companies",
        json={"name": "Alpha Custom Co", "custom": {"policy_number": "SECRET-1"}},
        headers=alpha.auth(),
    )
    company_id = created.json()["id"]
    try:
        assert client.get(f"{API}/companies/{company_id}", headers=bravo.auth()).status_code == 404
        export = client.get(f"{API}/io/companies/export", headers=bravo.auth())
        assert "SECRET-1" not in export.text
    finally:
        client.delete(f"{API}/companies/{company_id}", headers=alpha.auth())


# --- renaming and hiding built-in fields --------------------------------------

def test_base_field_can_be_relabelled_and_hidden(client, alpha):
    try:
        renamed = client.patch(
            f"{API}/schema/companies/fields/industry",
            json={"label": "Line of business"},
            headers=alpha.auth(),
        )
        assert renamed.status_code == 200, renamed.text
        fields = {f["key"]: f for f in renamed.json()["fields"]}
        assert fields["industry"]["label"] == "Line of business"
        assert fields["industry"]["is_custom"] is False

        hidden = client.patch(
            f"{API}/schema/companies/fields/industry", json={"is_active": False}, headers=alpha.auth()
        )
        assert {f["key"]: f for f in hidden.json()["fields"]}["industry"]["is_active"] is False
    finally:
        client.patch(
            f"{API}/schema/companies/fields/industry",
            json={"label": "Industry", "is_active": True},
            headers=alpha.auth(),
        )


def test_relabelling_does_not_affect_another_tenant(client, alpha, bravo):
    try:
        client.patch(
            f"{API}/schema/companies/fields/city", json={"label": "Branch city"}, headers=alpha.auth()
        )
        bravo_fields = {f["key"]: f for f in client.get(f"{API}/schema/companies", headers=bravo.auth()).json()["fields"]}
        assert bravo_fields["city"]["label"] == "City"
    finally:
        client.patch(f"{API}/schema/companies/fields/city", json={"label": "City"}, headers=alpha.auth())


def test_builtin_field_cannot_be_deleted(client, alpha):
    resp = client.delete(f"{API}/schema/companies/fields/industry", headers=alpha.auth())
    assert resp.status_code in (400, 404)


# --- filtering and export -----------------------------------------------------

def test_custom_field_can_be_filtered_on(client, alpha, alpha_field):
    match = client.post(
        f"{API}/companies", json={"name": "Filter Hit", "custom": {"policy_number": "FIND-ME"}},
        headers=alpha.auth(),
    ).json()
    miss = client.post(
        f"{API}/companies", json={"name": "Filter Miss", "custom": {"policy_number": "OTHER"}},
        headers=alpha.auth(),
    ).json()
    try:
        filters = '[{"key":"custom.policy_number","type":"text","value":"FIND-ME"}]'
        resp = client.get(
            f"{API}/companies", params={"filters": filters, "page_size": 100}, headers=alpha.auth()
        )
        assert resp.status_code == 200, resp.text
        names = {row["name"] for row in resp.json()["items"]}
        assert "Filter Hit" in names
        assert "Filter Miss" not in names
    finally:
        for row in (match, miss):
            client.delete(f"{API}/companies/{row['id']}", headers=alpha.auth())


def test_custom_field_is_included_in_csv_export(client, alpha, alpha_field):
    created = client.post(
        f"{API}/companies", json={"name": "Export Co", "custom": {"policy_number": "EXP-1"}},
        headers=alpha.auth(),
    ).json()
    try:
        export = client.get(f"{API}/io/companies/export", headers=alpha.auth())
        assert export.status_code == 200
        assert "Policy number" in export.text, "custom column header missing from export"
        assert "EXP-1" in export.text, "custom value missing from export"
    finally:
        client.delete(f"{API}/companies/{created['id']}", headers=alpha.auth())


# --- deletion keeps the data --------------------------------------------------

def test_deleting_a_field_keeps_stored_values(client, alpha):
    client.post(
        f"{API}/schema/companies/fields",
        json={"key": "temp_note", "label": "Temp note", "field_type": "text"},
        headers=alpha.auth(),
    )
    created = client.post(
        f"{API}/companies", json={"name": "Recover Co", "custom": {"temp_note": "kept"}},
        headers=alpha.auth(),
    ).json()
    try:
        assert client.delete(f"{API}/schema/companies/fields/temp_note", headers=alpha.auth()).status_code == 200
        # Recreating the field with the same key brings the values back.
        client.post(
            f"{API}/schema/companies/fields",
            json={"key": "temp_note", "label": "Temp note", "field_type": "text"},
            headers=alpha.auth(),
        )
        again = client.get(f"{API}/companies/{created['id']}", headers=alpha.auth()).json()
        assert again["custom"]["temp_note"] == "kept"
    finally:
        client.delete(f"{API}/schema/companies/fields/temp_note", headers=alpha.auth())
        client.delete(f"{API}/companies/{created['id']}", headers=alpha.auth())


# --- other modules ------------------------------------------------------------

@pytest.mark.parametrize("module", ["contacts", "leads", "deals", "tasks", "products", "projects", "support"])
def test_every_customisable_module_serves_a_schema(client, alpha, module):
    resp = client.get(f"{API}/schema/{module}", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["fields"]) > 0


def test_dropdown_and_number_filters_match_exactly(client, alpha):
    """Exact-match filters are the ones a text CAST silently breaks.

    `cast(custom['k'], String)` leaves the JSON quoting in place, so `= 'motor'`
    and `IN ('motor')` never match — while a substring `ILIKE` matches straight
    through the quotes and hides the bug.
    """
    client.post(
        f"{API}/schema/companies/fields",
        json={
            "key": "segment", "label": "Segment", "field_type": "select", "filterable": True,
            "options": [{"value": "motor", "label": "Motor"}, {"value": "health", "label": "Health"}],
        },
        headers=alpha.auth(),
    )
    client.post(
        f"{API}/schema/companies/fields",
        json={"key": "premium", "label": "Premium", "field_type": "number", "filterable": True},
        headers=alpha.auth(),
    )
    motor = client.post(
        f"{API}/companies",
        json={"name": "Motor Co", "custom": {"segment": "motor", "premium": 5000}},
        headers=alpha.auth(),
    ).json()
    health = client.post(
        f"{API}/companies",
        json={"name": "Health Co", "custom": {"segment": "health", "premium": 200}},
        headers=alpha.auth(),
    ).json()
    try:
        by_select = client.get(
            f"{API}/companies",
            params={"filters": '[{"key":"custom.segment","type":"select","value":["motor"]}]',
                    "page_size": 100},
            headers=alpha.auth(),
        ).json()
        names = {row["name"] for row in by_select["items"]}
        assert "Motor Co" in names, "dropdown filter matched nothing"
        assert "Health Co" not in names

        by_number = client.get(
            f"{API}/companies",
            params={"filters": '[{"key":"custom.premium","type":"number","op":"gte","value":1000}]',
                    "page_size": 100},
            headers=alpha.auth(),
        ).json()
        names = {row["name"] for row in by_number["items"]}
        assert "Motor Co" in names
        assert "Health Co" not in names, "number filter compared as text"
    finally:
        for row in (motor, health):
            client.delete(f"{API}/companies/{row['id']}", headers=alpha.auth())
        for key in ("segment", "premium"):
            client.delete(f"{API}/schema/companies/fields/{key}", headers=alpha.auth())
