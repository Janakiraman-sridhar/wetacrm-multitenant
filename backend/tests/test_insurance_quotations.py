"""Insurance quotations: competing options, one selection, one policy.

The rule under test throughout: an insurance quotation's total is the *selected*
option, never the sum of the options. Three insurers quoting for the same cover is
a choice, not a basket.
"""

from datetime import date, timedelta

import pytest

API = "/api/v1"


@pytest.fixture()
def insurer(client, alpha):
    resp = client.post(
        f"{API}/masters", json={"type": "insurer", "name": "Quote Test Insurer"}, headers=alpha.auth()
    )
    if resp.status_code == 409:
        rows = client.get(
            f"{API}/masters", params={"type": "insurer", "active_only": False}, headers=alpha.auth()
        ).json()
        return next(m for m in rows if m["name"] == "Quote Test Insurer")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def customer(client, alpha):
    row = client.post(
        f"{API}/contacts",
        json={"first_name": "Quote", "last_name": "Customer", "mobile": "9700000101"},
        headers=alpha.auth(),
    ).json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def options(**overrides):
    base = [
        {"insurer_name": "Cheap General", "plan_name": "Basic", "premium_gross": "12000",
         "premium_gst": "1830", "sum_insured": "500000", "idv": "480000"},
        {"insurer_name": "Mid General", "plan_name": "Comprehensive", "premium_gross": "14000",
         "premium_gst": "2135", "sum_insured": "500000", "idv": "500000"},
        {"insurer_name": "Premium General", "plan_name": "Zero Dep", "premium_gross": "16500",
         "premium_gst": "2516", "sum_insured": "500000", "idv": "520000"},
    ]
    for index, patch in overrides.items():
        base[int(index)].update(patch)
    return base


def make_quotation(client, world, customer, **overrides):
    payload = {
        "kind": "insurance",
        "contact_id": customer["id"],
        "insurance": {
            "product_line": "motor",
            "registration_no": "TN01AB1234",
            "options": options(),
        },
    }
    payload.update(overrides)
    resp = client.post(f"{API}/quotations", json=payload, headers=world.auth())
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- totals -------------------------------------------------------------------

def test_total_is_the_selected_option_not_the_sum(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    # 12000 + 14000 + 16500 = 42500 — the number this must never produce.
    assert float(quote["total"]) == 12000.0
    assert float(quote["subtotal"]) == 12000.0 - 1830.0
    assert float(quote["tax_total"]) == 1830.0


def test_cheapest_is_selected_when_nothing_is_marked(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    chosen = [o for o in quote["insurance"]["options"] if o["selected"]]
    assert len(chosen) == 1
    assert chosen[0]["insurer_name"] == "Cheap General"


def test_recommendation_beats_cheapest(client, alpha, customer):
    quote = make_quotation(
        client, alpha, customer,
        insurance={"product_line": "motor", "options": options(**{"2": {"recommended": True}})},
    )
    chosen = next(o for o in quote["insurance"]["options"] if o["selected"])
    assert chosen["insurer_name"] == "Premium General"
    assert float(quote["total"]) == 16500.0


def test_explicit_selection_wins(client, alpha, customer):
    quote = make_quotation(
        client, alpha, customer,
        insurance={"product_line": "motor",
                   "options": options(**{"0": {"recommended": True}, "1": {"selected": True}})},
    )
    chosen = next(o for o in quote["insurance"]["options"] if o["selected"])
    assert chosen["insurer_name"] == "Mid General"
    assert float(quote["total"]) == 14000.0


def test_two_selections_are_refused(client, alpha, customer):
    resp = client.post(
        f"{API}/quotations",
        json={
            "kind": "insurance", "contact_id": customer["id"],
            "insurance": {"options": options(**{"0": {"selected": True}, "1": {"selected": True}})},
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "one option" in resp.json()["detail"].lower()


def test_option_without_an_insurer_is_refused(client, alpha, customer):
    resp = client.post(
        f"{API}/quotations",
        json={"kind": "insurance", "contact_id": customer["id"],
              "insurance": {"options": [{"plan_name": "Mystery", "premium_gross": "9000"}]}},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


def test_net_is_derived_from_gross_and_gst(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    cheap = next(o for o in quote["insurance"]["options"] if o["insurer_name"] == "Cheap General")
    assert cheap["premium_net"] == 10170.0  # 12000 - 1830, not left as zero


def test_unknown_option_keys_are_dropped(client, alpha, customer):
    quote = make_quotation(
        client, alpha, customer,
        insurance={"options": options(**{"0": {"secret_margin": "9999"}})},
    )
    assert "secret_margin" not in quote["insurance"]["options"][0]


def test_switching_the_selection_moves_the_total(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    updated = client.patch(
        f"{API}/quotations/{quote['id']}",
        json={"insurance": {"product_line": "motor", "options": options(**{"2": {"selected": True}})}},
        headers=alpha.auth(),
    ).json()
    assert float(updated["total"]) == 16500.0


def test_a_standard_quotation_still_sums_its_items(client, alpha, customer):
    resp = client.post(
        f"{API}/quotations",
        json={
            "contact_id": customer["id"],
            "items": [
                {"name": "Consulting", "quantity": 2, "unit_price": 1000, "tax_rate": 18},
                {"name": "Support", "quantity": 1, "unit_price": 500, "tax_rate": 18},
            ],
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    quote = resp.json()
    assert quote["kind"] == "standard"
    assert float(quote["subtotal"]) == 2500.0
    assert float(quote["total"]) == 2950.0


# --- comparison PDF -----------------------------------------------------------

def test_comparison_pdf_renders(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    resp = client.get(f"{API}/quotations/{quote['id']}/comparison.pdf", headers=alpha.auth())
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
    assert len(resp.content) > 1000


def test_comparison_pdf_refused_for_a_standard_quotation(client, alpha, customer):
    quote = client.post(
        f"{API}/quotations", json={"contact_id": customer["id"], "items": []}, headers=alpha.auth()
    ).json()
    resp = client.get(f"{API}/quotations/{quote['id']}/comparison.pdf", headers=alpha.auth())
    assert resp.status_code == 400


def test_comparison_pdf_refused_with_no_options(client, alpha, customer):
    quote = client.post(
        f"{API}/quotations",
        json={"kind": "insurance", "contact_id": customer["id"], "insurance": {"options": []}},
        headers=alpha.auth(),
    ).json()
    resp = client.get(f"{API}/quotations/{quote['id']}/comparison.pdf", headers=alpha.auth())
    assert resp.status_code == 400


# --- convert to policy --------------------------------------------------------

def test_convert_creates_a_policy_from_the_selected_option(client, alpha, customer):
    quote = make_quotation(
        client, alpha, customer,
        insurance={"product_line": "motor", "registration_no": "TN01AB1234",
                   "options": options(**{"1": {"selected": True}})},
    )
    resp = client.post(
        f"{API}/quotations/{quote['id']}/convert-to-policy",
        json={
            "policy_number": "POL-FROM-QUOTE-1",
            "start_date": str(date.today()),
            "expiry_date": str(date.today() + timedelta(days=365)),
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    policy = resp.json()
    assert policy["policy_number"] == "POL-FROM-QUOTE-1"
    assert policy["plan_name"] == "Comprehensive"
    assert float(policy["premium_gross"]) == 14000.0
    assert policy["registration_no"] == "TN01AB1234"
    assert policy["status"] == "active"

    after = client.get(f"{API}/quotations/{quote['id']}", headers=alpha.auth()).json()
    assert after["status"] == "converted"
    assert after["policy_id"] == policy["id"]

    client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_convert_twice_is_refused(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    first = client.post(
        f"{API}/quotations/{quote['id']}/convert-to-policy",
        json={"policy_number": "POL-FROM-QUOTE-2"}, headers=alpha.auth(),
    )
    assert first.status_code == 200
    second = client.post(
        f"{API}/quotations/{quote['id']}/convert-to-policy",
        json={"policy_number": "POL-FROM-QUOTE-3"}, headers=alpha.auth(),
    )
    assert second.status_code == 409
    client.delete(f"{API}/policies/{first.json()['id']}", headers=alpha.auth())


def test_convert_needs_a_customer(client, alpha):
    quote = client.post(
        f"{API}/quotations",
        json={"kind": "insurance", "insurance": {"options": options()}},
        headers=alpha.auth(),
    ).json()
    resp = client.post(
        f"{API}/quotations/{quote['id']}/convert-to-policy",
        json={"policy_number": "POL-NO-CUSTOMER"}, headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "customer" in resp.json()["detail"].lower()


def test_insurance_quotation_does_not_convert_to_an_invoice(client, alpha, customer):
    quote = make_quotation(client, alpha, customer)
    resp = client.post(f"{API}/quotations/{quote['id']}/convert", headers=alpha.auth())
    assert resp.status_code == 400
    assert "policy" in resp.json()["detail"].lower()


def test_convert_expiry_drives_the_status(client, alpha, customer):
    """A back-dated conversion lands as lapsed, not as active."""
    quote = make_quotation(client, alpha, customer)
    resp = client.post(
        f"{API}/quotations/{quote['id']}/convert-to-policy",
        json={
            "policy_number": "POL-FROM-QUOTE-OLD",
            "expiry_date": str(date.today() - timedelta(days=10)),
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "lapsed"
    client.delete(f"{API}/policies/{resp.json()['id']}", headers=alpha.auth())


# --- tenancy ------------------------------------------------------------------

def test_one_tenants_insurance_quotation_is_invisible_to_another(client, alpha, bravo, customer):
    quote = make_quotation(client, alpha, customer)
    assert client.get(f"{API}/quotations/{quote['id']}", headers=bravo.auth()).status_code == 404
    assert client.get(
        f"{API}/quotations/{quote['id']}/comparison.pdf", headers=bravo.auth()
    ).status_code == 404


def test_a_duplicate_policy_number_is_refused_not_a_500(client, alpha, customer):
    """A mistyped number that already exists must come back as a conflict."""
    first = make_quotation(client, alpha, customer)
    resp = client.post(
        f"{API}/quotations/{first['id']}/convert-to-policy",
        json={"policy_number": "POL-DUPLICATE-1"}, headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text

    second = make_quotation(client, alpha, customer)
    clash = client.post(
        f"{API}/quotations/{second['id']}/convert-to-policy",
        json={"policy_number": "POL-DUPLICATE-1"}, headers=alpha.auth(),
    )
    assert clash.status_code == 409, clash.text
    assert "already exists" in clash.json()["detail"]

    # And the quotation is untouched, so it can be converted with the right number.
    after = client.get(f"{API}/quotations/{second['id']}", headers=alpha.auth()).json()
    assert after["status"] != "converted"
    assert after["policy_id"] is None

    client.delete(f"{API}/policies/{resp.json()['id']}", headers=alpha.auth())
