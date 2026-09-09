"""Policies, renewals and the numbers the dashboard reports.

The two things worth proving: status follows the expiry date rather than whatever
someone last typed, and a renewal preserves the history instead of overwriting it.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

API = "/api/v1"


@pytest.fixture()
def masters(client, alpha):
    """An insurer and a bank for this tenant to write policies against.

    Reuses an existing entry rather than insisting on creating one: a master that
    policies point at is deactivated rather than deleted, so it survives teardown.
    """
    made = {}
    for kind, name in (("insurer", "Test General Insurance"), ("bank", "Test Bank")):
        resp = client.post(
            f"{API}/masters", json={"type": kind, "name": name}, headers=alpha.auth()
        )
        if resp.status_code == 409:
            existing = client.get(
                f"{API}/masters", params={"type": kind, "active_only": False}, headers=alpha.auth()
            ).json()
            row = next(m for m in existing if m["name"] == name)
            client.patch(f"{API}/masters/{row['id']}", json={"is_active": True}, headers=alpha.auth())
            made[kind] = row
            continue
        assert resp.status_code == 200, resp.text
        made[kind] = resp.json()
    return made


@pytest.fixture()
def customer(client, alpha):
    row = client.post(
        f"{API}/contacts",
        json={"first_name": "Policy", "last_name": "Holder", "mobile": "9800000001"},
        headers=alpha.auth(),
    ).json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def make_policy(client, world, customer, masters, **overrides):
    today = date.today()
    payload = {
        "policy_number": f"POL-{overrides.pop('suffix', '0001')}",
        "product_line": "motor",
        "plan_name": "Private Car Package",
        "customer_id": customer["id"],
        "insurer_id": masters["insurer"]["id"],
        "bank_id": masters["bank"]["id"],
        "sourcing_channel": "bank",
        "issue_date": str(today),
        "start_date": str(today),
        "expiry_date": str(today + timedelta(days=300)),
        "premium_net": "10000.00",
        "premium_gst": "1800.00",
        "sum_insured": "500000.00",
        "registration_no": "TN01AB1234",
        "details": {"make": "Maruti", "model": "Swift", "idv": 500000, "ncb_percent": 20},
    }
    payload.update(overrides)
    resp = client.post(f"{API}/policies", json=payload, headers=world.auth())
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- masters ------------------------------------------------------------------

def test_masters_are_created_and_listed(client, alpha, masters):
    insurers = client.get(f"{API}/masters", params={"type": "insurer"}, headers=alpha.auth()).json()
    assert any(m["name"] == "Test General Insurance" for m in insurers)


def test_duplicate_master_is_rejected(client, alpha, masters):
    resp = client.post(
        f"{API}/masters", json={"type": "insurer", "name": "Test General Insurance"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 409


def test_masters_do_not_cross_tenants(client, alpha, bravo, masters):
    theirs = client.get(f"{API}/masters", params={"type": "insurer"}, headers=bravo.auth()).json()
    assert not any(m["name"] == "Test General Insurance" for m in theirs)


def test_master_in_use_is_deactivated_not_deleted(client, alpha, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="INUSE")
    try:
        resp = client.delete(f"{API}/masters/{masters['insurer']['id']}", headers=alpha.auth())
        assert resp.status_code == 200
        assert "deactivated" in resp.json()["detail"]
        # The policy keeps the insurer it was actually written with.
        assert client.get(f"{API}/policies/{policy['id']}", headers=alpha.auth()).json()["insurer_id"]
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


# --- creating -----------------------------------------------------------------

def test_policy_is_created_with_derived_premium(client, alpha, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="PREM")
    try:
        # Gross was not supplied, so it is derived from net + GST.
        assert Decimal(policy["premium_gross"]) == Decimal("11800.00")
        assert policy["status"] == "active"
        assert policy["customer"]["full_name"] == "Policy Holder"
        assert policy["details"]["make"] == "Maruti"
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_details_outside_the_product_line_are_dropped(client, alpha, customer, masters):
    """`details` is not a dumping ground — a tenant that needs more adds a custom field."""
    policy = make_policy(
        client, alpha, customer, masters, suffix="DETAIL",
        details={"make": "Honda", "room_rent_limit": 5000, "nonsense": "x"},
    )
    try:
        assert policy["details"]["make"] == "Honda"
        # room_rent_limit belongs to health, not motor.
        assert "room_rent_limit" not in policy["details"]
        assert "nonsense" not in policy["details"]
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_duplicate_policy_number_is_rejected(client, alpha, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="DUP")
    try:
        resp = client.post(
            f"{API}/policies",
            json={
                "policy_number": "POL-DUP", "product_line": "motor",
                "customer_id": customer["id"], "expiry_date": str(date.today() + timedelta(days=100)),
            },
            headers=alpha.auth(),
        )
        assert resp.status_code == 409
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_unknown_product_line_is_rejected(client, alpha, customer, masters):
    resp = client.post(
        f"{API}/policies",
        json={"policy_number": "POL-BAD", "product_line": "spaceship", "customer_id": customer["id"]},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


# --- status is derived, not typed ---------------------------------------------

def test_status_follows_the_expiry_date_on_create(client, alpha, customer, masters):
    """A back-dated policy lands as lapsed rather than sitting in the book as active."""
    expired = make_policy(
        client, alpha, customer, masters, suffix="OLD",
        expiry_date=str(date.today() - timedelta(days=5)), status="active",
    )
    expiring = make_policy(
        client, alpha, customer, masters, suffix="SOON",
        expiry_date=str(date.today() + timedelta(days=20)),
    )
    try:
        assert expired["status"] == "lapsed"
        assert expiring["status"] == "expiring"
    finally:
        for row in (expired, expiring):
            client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_refresh_moves_statuses_as_dates_pass(client, alpha, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="REFRESH")
    try:
        assert policy["status"] == "active"
        client.patch(
            f"{API}/policies/{policy['id']}",
            json={"expiry_date": str(date.today() + timedelta(days=10))},
            headers=alpha.auth(),
        )
        refreshed = client.post(f"{API}/policies/refresh-statuses", headers=alpha.auth())
        assert refreshed.status_code == 200
        after = client.get(f"{API}/policies/{policy['id']}", headers=alpha.auth()).json()
        assert after["status"] == "expiring"
        assert after["days_to_expiry"] == 10
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


# --- renewal ------------------------------------------------------------------

def test_renewal_creates_a_new_policy_and_keeps_the_old_one(client, alpha, customer, masters):
    original = make_policy(
        client, alpha, customer, masters, suffix="RENEW",
        expiry_date=str(date.today() + timedelta(days=10)),
    )
    new_start = date.today() + timedelta(days=11)
    resp = client.post(
        f"{API}/policies/{original['id']}/renew",
        json={
            "policy_number": "POL-RENEW-2", "start_date": str(new_start),
            "expiry_date": str(new_start + timedelta(days=364)), "premium_gross": "13000.00",
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    renewal = resp.json()
    try:
        assert renewal["renewal_of_id"] == original["id"]
        assert renewal["sourcing_channel"] == "renewal"
        # Details carry over — nobody retypes a chassis number to renew.
        assert renewal["details"]["make"] == "Maruti"
        assert renewal["registration_no"] == "TN01AB1234"

        previous = client.get(f"{API}/policies/{original['id']}", headers=alpha.auth()).json()
        assert previous["status"] == "renewed"
        assert previous["renewed_to_id"] == renewal["id"]

        chain = client.get(f"{API}/policies/{renewal['id']}/history", headers=alpha.auth()).json()
        assert [p["policy_number"] for p in chain] == ["POL-RENEW", "POL-RENEW-2"]
    finally:
        client.delete(f"{API}/policies/{renewal['id']}", headers=alpha.auth())
        client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth())


def test_a_policy_cannot_be_renewed_twice(client, alpha, customer, masters):
    original = make_policy(client, alpha, customer, masters, suffix="ONCE")
    start = date.today() + timedelta(days=1)
    first = client.post(
        f"{API}/policies/{original['id']}/renew",
        json={"policy_number": "POL-ONCE-2", "start_date": str(start),
              "expiry_date": str(start + timedelta(days=364))},
        headers=alpha.auth(),
    ).json()
    try:
        again = client.post(
            f"{API}/policies/{original['id']}/renew",
            json={"policy_number": "POL-ONCE-3", "start_date": str(start),
                  "expiry_date": str(start + timedelta(days=364))},
            headers=alpha.auth(),
        )
        assert again.status_code == 409
    finally:
        client.delete(f"{API}/policies/{first['id']}", headers=alpha.auth())
        client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth())


def test_a_renewed_policy_cannot_be_deleted_first(client, alpha, customer, masters):
    original = make_policy(client, alpha, customer, masters, suffix="CHAIN")
    start = date.today() + timedelta(days=1)
    renewal = client.post(
        f"{API}/policies/{original['id']}/renew",
        json={"policy_number": "POL-CHAIN-2", "start_date": str(start),
              "expiry_date": str(start + timedelta(days=364))},
        headers=alpha.auth(),
    ).json()
    try:
        assert client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth()).status_code == 409
    finally:
        client.delete(f"{API}/policies/{renewal['id']}", headers=alpha.auth())
        client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth())


# --- the renewal desk ---------------------------------------------------------

def test_renewals_lists_what_is_expiring_soonest_first(client, alpha, customer, masters):
    near = make_policy(client, alpha, customer, masters, suffix="NEAR",
                       expiry_date=str(date.today() + timedelta(days=5)))
    far = make_policy(client, alpha, customer, masters, suffix="FAR",
                      expiry_date=str(date.today() + timedelta(days=50)))
    outside = make_policy(client, alpha, customer, masters, suffix="OUT",
                          expiry_date=str(date.today() + timedelta(days=300)))
    try:
        due = client.get(f"{API}/policies/renewals", params={"within_days": 60}, headers=alpha.auth()).json()
        numbers = [p["policy_number"] for p in due]
        assert numbers.index("POL-NEAR") < numbers.index("POL-FAR")
        assert "POL-OUT" not in numbers
        assert due[0]["customer"]["full_name"] == "Policy Holder"
    finally:
        for row in (near, far, outside):
            client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_a_renewed_policy_drops_off_the_renewal_desk(client, alpha, customer, masters):
    original = make_policy(client, alpha, customer, masters, suffix="DESK",
                           expiry_date=str(date.today() + timedelta(days=5)))
    start = date.today() + timedelta(days=6)
    renewal = client.post(
        f"{API}/policies/{original['id']}/renew",
        json={"policy_number": "POL-DESK-2", "start_date": str(start),
              "expiry_date": str(start + timedelta(days=364))},
        headers=alpha.auth(),
    ).json()
    try:
        due = client.get(f"{API}/policies/renewals", headers=alpha.auth()).json()
        assert "POL-DESK" not in [p["policy_number"] for p in due]
    finally:
        client.delete(f"{API}/policies/{renewal['id']}", headers=alpha.auth())
        client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth())


# --- dashboard numbers --------------------------------------------------------

def test_stats_report_the_book(client, alpha, customer, masters):
    active = make_policy(client, alpha, customer, masters, suffix="S1")
    soon = make_policy(client, alpha, customer, masters, suffix="S2",
                       expiry_date=str(date.today() + timedelta(days=20)))
    try:
        stats = client.get(f"{API}/policies/stats", headers=alpha.auth()).json()
        assert stats["active_policies"] >= 2
        assert Decimal(stats["book_premium"]) >= Decimal("23600.00")
        assert stats["renewals_60d"] >= 1
        assert stats["renewals_30d"] >= 1
        assert stats["new_business_mtd_count"] >= 2
    finally:
        for row in (active, soon):
            client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_stats_do_not_count_another_tenants_policies(client, alpha, bravo, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="ISO")
    try:
        theirs = client.get(f"{API}/policies/stats", headers=bravo.auth()).json()
        assert theirs["active_policies"] == 0
        assert Decimal(theirs["book_premium"]) == Decimal(0)
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_charts_group_the_book(client, alpha, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="CHART")
    try:
        charts = client.get(f"{API}/policies/charts", headers=alpha.auth()).json()
        assert any(row["name"] == "Test General Insurance" for row in charts["by_insurer"])
        assert any(row["name"] == "Motor" for row in charts["by_product_line"])
        assert charts["premium_by_month"], "premium series is empty"
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


# --- isolation ----------------------------------------------------------------

def test_policies_do_not_cross_tenants(client, alpha, bravo, customer, masters):
    policy = make_policy(client, alpha, customer, masters, suffix="LEAK")
    try:
        assert client.get(f"{API}/policies/{policy['id']}", headers=bravo.auth()).status_code == 404
        listing = client.get(f"{API}/policies", params={"page_size": 200}, headers=bravo.auth()).json()
        assert listing["total"] == 0
        assert client.get(f"{API}/policies/renewals", headers=bravo.auth()).json() == []
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_policy_filters_work(client, alpha, customer, masters):
    motor = make_policy(client, alpha, customer, masters, suffix="FM")
    health = make_policy(
        client, alpha, customer, masters, suffix="FH", product_line="health",
        details={"policy_type": "family_floater", "room_rent_limit": 5000},
    )
    try:
        by_line = client.get(
            f"{API}/policies", params={"product_line": "health", "page_size": 100}, headers=alpha.auth()
        ).json()
        numbers = {p["policy_number"] for p in by_line["items"]}
        assert "POL-FH" in numbers and "POL-FM" not in numbers

        by_bank = client.get(
            f"{API}/policies",
            params={"filters": f'[{{"key":"bank_id","type":"select","value":["{masters["bank"]["id"]}"]}}]',
                    "page_size": 100},
            headers=alpha.auth(),
        ).json()
        assert by_bank["total"] >= 2
    finally:
        for row in (motor, health):
            client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_policies_support_custom_fields(client, alpha, customer, masters):
    """Phase 2's engine covers the new module too."""
    client.post(
        f"{API}/schema/policies/fields",
        json={"key": "endorsement_no", "label": "Endorsement no", "field_type": "text"},
        headers=alpha.auth(),
    )
    policy = make_policy(
        client, alpha, customer, masters, suffix="CF", custom={"endorsement_no": "END-77"}
    )
    try:
        assert policy["custom"]["endorsement_no"] == "END-77"
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())
        client.delete(f"{API}/schema/policies/fields/endorsement_no", headers=alpha.auth())


def test_created_premium_matches_what_a_later_read_returns(client, alpha, customer, masters):
    """The create response and a subsequent GET must agree.

    Derived premiums used to come back unquantised ("5900") on create and
    column-normalised ("5900.00") on read — the same number, two shapes, which a
    client formatting currency notices.
    """
    policy = make_policy(
        client, alpha, customer, masters, suffix="QUANT",
        premium_net="5000", premium_gst="900", premium_gross=None,
    )
    try:
        fetched = client.get(f"{API}/policies/{policy['id']}", headers=alpha.auth()).json()
        for field in ("premium_net", "premium_gst", "premium_gross"):
            assert str(policy[field]) == str(fetched[field]), (
                f"{field}: create returned {policy[field]!r}, read returned {fetched[field]!r}"
            )
        assert str(policy["premium_gross"]) == "5900.00"
    finally:
        client.delete(f"{API}/policies/{policy['id']}", headers=alpha.auth())


def test_deleting_a_renewal_unlinks_the_policy_it_replaced(client, alpha, customer, masters):
    """Otherwise the previous policy points at a row that no longer exists.

    It is then stuck: `renewed` forever, un-deletable because `renewed_to_id` is set,
    and un-renewable for the same reason.
    """
    original = make_policy(
        client, alpha, customer, masters, suffix="UNLINK",
        expiry_date=str(date.today() + timedelta(days=20)),
    )
    start = date.today() + timedelta(days=21)
    renewal = client.post(
        f"{API}/policies/{original['id']}/renew",
        json={"policy_number": "POL-UNLINK-2", "start_date": str(start),
              "expiry_date": str(start + timedelta(days=364))},
        headers=alpha.auth(),
    ).json()

    assert client.delete(f"{API}/policies/{renewal['id']}", headers=alpha.auth()).status_code == 200

    after = client.get(f"{API}/policies/{original['id']}", headers=alpha.auth()).json()
    assert after["renewed_to_id"] is None, "previous policy still points at the deleted renewal"
    # Its status is re-derived, so it returns to the renewal desk rather than
    # sitting as `renewed` with nothing to show for it.
    assert after["status"] == "expiring"

    due = client.get(f"{API}/policies/renewals", headers=alpha.auth()).json()
    assert "POL-UNLINK" in {p["policy_number"] for p in due}

    # And it can now be deleted, which it could not before.
    assert client.delete(f"{API}/policies/{original['id']}", headers=alpha.auth()).status_code == 200


# --- the insurance company a policy was placed through ------------------------
#
# Two different companies, both named on the policy: the insurer underwrites the
# risk, the intermediary carries the agency code the commission is paid against.
# An agency reconciles by each of them separately, which is the whole reason this
# is not one field.

@pytest.fixture()
def broker(client, alpha):
    resp = client.post(
        f"{API}/masters", json={"type": "broker", "name": "Test Insurance Broking"},
        headers=alpha.auth(),
    )
    if resp.status_code == 409:
        existing = client.get(
            f"{API}/masters", params={"type": "broker", "active_only": False}, headers=alpha.auth()
        ).json()
        return next(m for m in existing if m["name"] == "Test Insurance Broking")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_broker_is_its_own_list_not_mixed_into_insurers(client, alpha, broker, masters):
    insurers = client.get(f"{API}/masters", params={"type": "insurer"}, headers=alpha.auth()).json()
    brokers = client.get(f"{API}/masters", params={"type": "broker"}, headers=alpha.auth()).json()

    assert broker["id"] in [m["id"] for m in brokers]
    assert broker["id"] not in [m["id"] for m in insurers], "the broker leaked into the insurer list"
    assert masters["insurer"]["id"] not in [m["id"] for m in brokers]


def test_a_policy_names_the_insurer_and_the_intermediary_separately(
    client, alpha, customer, masters, broker
):
    created = make_policy(
        client, alpha, customer, masters, suffix="BRK1", broker_id=broker["id"],
    )
    fetched = client.get(f"{API}/policies/{created['id']}", headers=alpha.auth()).json()

    assert fetched["insurer"]["name"] == masters["insurer"]["name"]
    assert fetched["broker"]["name"] == "Test Insurance Broking"
    assert fetched["insurer_id"] != fetched["broker_id"]

    client.delete(f"{API}/policies/{created['id']}", headers=alpha.auth())


def test_the_book_can_be_read_by_intermediary(client, alpha, customer, masters, broker):
    """The reason it is a column and not a note: an agency reconciles by it."""
    placed = make_policy(client, alpha, customer, masters, suffix="BRK2", broker_id=broker["id"])
    direct = make_policy(client, alpha, customer, masters, suffix="BRK3")

    page = client.get(
        f"{API}/policies", params={"broker_id": broker["id"]}, headers=alpha.auth()
    ).json()
    ids = [p["id"] for p in page["items"]]
    assert placed["id"] in ids
    assert direct["id"] not in ids, "a policy placed direct came back under the intermediary"

    for row in (placed, direct):
        client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_the_intermediary_can_be_cleared(client, alpha, customer, masters, broker):
    """A policy moved to direct business must actually lose it.

    Checked by re-reading rather than by trusting the update's own response: the
    relationship is still loaded on that session, so a clear that did nothing would
    look like a clear that worked.
    """
    created = make_policy(client, alpha, customer, masters, suffix="BRK4", broker_id=broker["id"])
    client.patch(f"{API}/policies/{created['id']}", json={"broker_id": None}, headers=alpha.auth())

    fetched = client.get(f"{API}/policies/{created['id']}", headers=alpha.auth()).json()
    assert fetched["broker_id"] is None
    assert fetched["broker"] is None

    client.delete(f"{API}/policies/{created['id']}", headers=alpha.auth())


def test_it_is_called_what_an_agency_calls_it(client, alpha):
    """The label is served, not hardcoded in the page, so every screen agrees."""
    schema = client.get(f"{API}/schema/policies", headers=alpha.auth()).json()
    labels = {f["key"]: f["label"] for f in schema["fields"]}
    assert labels["broker_id"] == "Insurance company"
    assert labels["insurer_id"] == "Insurer"
