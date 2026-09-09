"""Customer identity data: encrypted at rest, masked by default, audited on reveal.

The claim being tested is the one that matters if this ever goes wrong: a full PAN
or Aadhaar is not in the database in readable form, is not in an API response, and
cannot be looked at without leaving a record of who looked.
"""

import sqlite3

import pytest

from app.core.validators import (
    mask_pan, normalise_aadhaar, normalise_pan, normalise_phone, verhoeff_valid,
)

API = "/api/v1"

# Valid PAN format, and an Aadhaar with a correct Verhoeff check digit.
PAN = "ABCDE1234F"
AADHAAR = "234123412346"


@pytest.fixture()
def customer(client, alpha):
    resp = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Meera", "last_name": "Iyer",
            "mobile": "9876543210", "pan": PAN, "aadhaar": AADHAAR,
            "date_of_birth": "1990-06-15", "pincode": "600001",
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


# --- validators ---------------------------------------------------------------

def test_verhoeff_catches_a_single_digit_typo():
    assert verhoeff_valid(AADHAAR)
    broken = AADHAAR[:5] + str((int(AADHAAR[5]) + 1) % 10) + AADHAAR[6:]
    assert not verhoeff_valid(broken)


def test_verhoeff_catches_a_transposition():
    swapped = list(AADHAAR)
    swapped[3], swapped[4] = swapped[4], swapped[3]
    if "".join(swapped) != AADHAAR:
        assert not verhoeff_valid("".join(swapped))


def test_pan_is_uppercased_and_format_checked():
    assert normalise_pan(" abcde1234f ") == PAN
    with pytest.raises(Exception):
        normalise_pan("ABC123")


def test_aadhaar_strips_formatting():
    assert normalise_aadhaar("2341 2341 2346") == AADHAAR


def test_phone_becomes_e164():
    assert normalise_phone("9876543210") == "+919876543210"
    assert normalise_phone("+91 98765 43210") == "+919876543210"
    assert normalise_phone("09876543210") == "+919876543210"


def test_masking_keeps_only_the_recognisable_part():
    assert mask_pan(PAN) == "ABCDE****F"


# --- storage ------------------------------------------------------------------

def test_identity_is_ciphertext_in_the_database(customer):
    """The claim that matters: the raw number is not sitting in the table."""
    from tests.conftest import _DB_PATH

    conn = sqlite3.connect(_DB_PATH)
    row = conn.execute(
        "SELECT pan_encrypted, pan_index, aadhaar_last4, aadhaar_encrypted FROM contacts WHERE id = ?",
        (customer["id"],),
    ).fetchone()
    conn.close()
    pan_encrypted, pan_index, aadhaar_last4, aadhaar_encrypted = row

    assert pan_encrypted and PAN not in pan_encrypted, "PAN is stored in the clear"
    assert pan_encrypted.startswith("v1:"), "ciphertext is missing its version prefix"
    assert pan_index and PAN not in pan_index, "the blind index leaks the value"
    # Full capture is off by default, so only the last 4 of the Aadhaar is kept.
    assert aadhaar_last4 == AADHAAR[-4:]
    assert aadhaar_encrypted is None


def test_full_aadhaar_is_not_stored_unless_the_tenant_opts_in(customer):
    assert customer["has_aadhaar"] is True
    assert customer["aadhaar_full_stored"] is False


def test_two_encryptions_of_the_same_value_differ(client, alpha):
    """Randomised nonces, so ciphertext cannot be used to compare records."""
    from tests.conftest import _DB_PATH

    ids = []
    for name in ("One", "Two"):
        ids.append(
            client.post(
                f"{API}/contacts", json={"first_name": name, "pan": PAN}, headers=alpha.auth()
            ).json()["id"]
        )
    try:
        conn = sqlite3.connect(_DB_PATH)
        rows = conn.execute(
            f"SELECT pan_encrypted, pan_index FROM contacts WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        ).fetchall()
        conn.close()
        assert rows[0][0] != rows[1][0], "identical plaintexts produced identical ciphertext"
        # …but the blind index is deterministic, which is what makes lookup work.
        assert rows[0][1] == rows[1][1]
    finally:
        for contact_id in ids:
            client.delete(f"{API}/contacts/{contact_id}", headers=alpha.auth())


# --- masking ------------------------------------------------------------------

def test_api_returns_only_masked_values(client, alpha, customer):
    body = client.get(f"{API}/contacts/{customer['id']}", headers=alpha.auth()).json()
    assert body["pan_masked"] == "ABCDE****F"
    assert body["aadhaar_masked"] == f"XXXX XXXX {AADHAAR[-4:]}"
    serialised = str(body)
    assert PAN not in serialised, "the full PAN came back in the response"
    assert AADHAAR not in serialised, "the full Aadhaar came back in the response"


def test_list_endpoint_does_not_leak_identity(client, alpha, customer):
    body = client.get(f"{API}/contacts", params={"page_size": 200}, headers=alpha.auth()).json()
    assert PAN not in str(body)
    assert any(row["id"] == customer["id"] for row in body["items"])


# --- reveal -------------------------------------------------------------------

def test_reveal_returns_the_value_and_records_who_looked(client, alpha, customer):
    resp = client.post(
        f"{API}/contacts/{customer['id']}/reveal", json={"field": "pan"}, headers=alpha.auth()
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["value"] == PAN

    log = client.get(f"{API}/contacts/{customer['id']}/pii-access", headers=alpha.auth())
    assert log.status_code == 200
    entries = log.json()
    assert entries, "the reveal was not recorded"
    assert entries[0]["field"] == "pan"
    assert entries[0]["user"]["name"]


def test_reveal_needs_its_own_permission(client, alpha, customer):
    """Editing customers is not the same right as reading their raw identity."""
    roles = client.get(f"{API}/roles", headers=alpha.auth()).json()
    admin_role = next(r for r in roles if r["name"] == "Super Admin")
    limited = client.post(
        f"{API}/roles",
        json={
            "name": "No Reveal", "description": "Can edit customers, cannot see raw PAN",
            "permissions": ["contacts:read", "contacts:write"],
        },
        headers=alpha.auth(),
    ).json()
    user = client.post(
        f"{API}/users",
        json={
            "email": "noreveal@example.com", "password": "no-reveal-pass-1",
            "first_name": "No", "last_name": "Reveal", "role_id": limited["id"],
            "send_welcome_email": False,
        },
        headers=alpha.auth(),
    ).json()
    token = client.post(
        f"{API}/auth/login", json={"email": "noreveal@example.com", "password": "no-reveal-pass-1"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # They can read the customer…
        assert client.get(f"{API}/contacts/{customer['id']}", headers=headers).status_code == 200
        # …but not the raw number.
        denied = client.post(
            f"{API}/contacts/{customer['id']}/reveal", json={"field": "pan"}, headers=headers
        )
        assert denied.status_code == 403
    finally:
        client.delete(f"{API}/users/{user['id']}", headers=alpha.auth())
        client.delete(f"{API}/roles/{limited['id']}", headers=alpha.auth())
        assert admin_role


def test_revealing_aadhaar_explains_why_it_is_unavailable(client, alpha, customer):
    resp = client.post(
        f"{API}/contacts/{customer['id']}/reveal", json={"field": "aadhaar"}, headers=alpha.auth()
    )
    assert resp.status_code == 400
    assert "last 4" in resp.json()["detail"]


def test_reveal_across_tenants_is_not_found(client, bravo, customer):
    resp = client.post(
        f"{API}/contacts/{customer['id']}/reveal", json={"field": "pan"}, headers=bravo.auth()
    )
    assert resp.status_code == 404


# --- blind index lookup -------------------------------------------------------

def test_lookup_finds_a_customer_by_pan_without_decrypting(client, alpha, customer):
    resp = client.get(f"{API}/contacts/lookup", params={"pan": PAN}, headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    assert resp.json()["found"] is True
    assert resp.json()["contact_id"] == customer["id"]


def test_lookup_is_tenant_scoped(client, bravo, customer):
    resp = client.get(f"{API}/contacts/lookup", params={"pan": PAN}, headers=bravo.auth())
    assert resp.status_code == 200
    assert resp.json()["found"] is False, "LEAK — found another tenant's customer by PAN"


# --- validation at the API boundary -------------------------------------------

@pytest.mark.parametrize("field,value,fragment", [
    ("pan", "NOTAPAN", "ABCDE1234F"),
    ("aadhaar", "1234", "12 digits"),
    ("aadhaar", "234123412340", "typo"),
    ("aadhaar", "034123412346", "0 or 1"),
])
def test_invalid_identity_is_rejected(client, alpha, field, value, fragment):
    resp = client.post(
        f"{API}/contacts", json={"first_name": "Invalid", field: value}, headers=alpha.auth()
    )
    assert resp.status_code == 400, resp.text
    assert fragment in resp.json()["detail"]


def test_bad_pincode_is_rejected(client, alpha):
    resp = client.post(
        f"{API}/contacts", json={"first_name": "Pin", "pincode": "12"}, headers=alpha.auth()
    )
    assert resp.status_code == 400


# --- nominees -----------------------------------------------------------------

def test_nominee_shares_must_total_100(client, alpha):
    resp = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Nominee Test",
            "nominees": [
                {"name": "A", "relation": "Spouse", "age": 40, "share_percent": 60},
                {"name": "B", "relation": "Son", "age": 20, "share_percent": 30},
            ],
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "100%" in resp.json()["detail"]


def test_minor_nominee_needs_an_appointee(client, alpha):
    resp = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Minor Test",
            "nominees": [{"name": "Child", "relation": "Son", "age": 10, "share_percent": 100}],
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "appointee" in resp.json()["detail"]


def test_valid_nominees_are_saved(client, alpha):
    created = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Nominees OK",
            "nominees": [
                {"name": "Priya", "relation": "Spouse", "age": 38, "share_percent": 60},
                {"name": "Arjun", "relation": "Son", "age": 10, "share_percent": 40,
                 "appointee_name": "Priya", "appointee_relation": "Mother"},
            ],
        },
        headers=alpha.auth(),
    )
    assert created.status_code == 200, created.text
    try:
        nominees = created.json()["nominees"]
        assert len(nominees) == 2
        assert sum(n["share_percent"] for n in nominees) == 100
        assert next(n for n in nominees if n["name"] == "Arjun")["is_minor"] is True
    finally:
        client.delete(f"{API}/contacts/{created.json()['id']}", headers=alpha.auth())


def test_editing_a_customer_keeps_the_nominees_it_was_not_asked_about(client, alpha):
    """Omitting them leaves them alone; sending an empty list clears them.

    The customer form now sends the whole list on every save, so the difference
    matters: a page that edits an address and omits `nominees` must not wipe them,
    and one that removes the last nominee must actually remove it.
    """
    created = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Nominee Keeper",
            "nominees": [{"name": "Priya", "relation": "Spouse", "age": 38, "share_percent": 100}],
        },
        headers=alpha.auth(),
    ).json()
    try:
        client.patch(f"{API}/contacts/{created['id']}", json={"city": "Chennai"},
                     headers=alpha.auth())
        kept = client.get(f"{API}/contacts/{created['id']}", headers=alpha.auth()).json()
        assert [n["name"] for n in kept["nominees"]] == ["Priya"], "an unrelated edit wiped them"

        replaced = client.patch(
            f"{API}/contacts/{created['id']}",
            json={"nominees": [
                {"name": "Ravi", "relation": "Father", "age": 66, "share_percent": 100},
            ]},
            headers=alpha.auth(),
        )
        assert replaced.status_code == 200, replaced.text
        after = client.get(f"{API}/contacts/{created['id']}", headers=alpha.auth()).json()
        assert [n["name"] for n in after["nominees"]] == ["Ravi"]

        client.patch(f"{API}/contacts/{created['id']}", json={"nominees": []}, headers=alpha.auth())
        emptied = client.get(f"{API}/contacts/{created['id']}", headers=alpha.auth()).json()
        assert emptied["nominees"] == []
    finally:
        client.delete(f"{API}/contacts/{created['id']}", headers=alpha.auth())


# --- birthdays ----------------------------------------------------------------

def test_birthdays_lists_customers_whose_birthday_is_near(client, alpha):
    from datetime import date, timedelta

    soon = date.today() + timedelta(days=3)
    created = client.post(
        f"{API}/contacts",
        json={"first_name": "Birthday", "last_name": "Soon",
              "date_of_birth": f"1985-{soon.month:02d}-{soon.day:02d}", "mobile": "9000000001"},
        headers=alpha.auth(),
    ).json()
    try:
        resp = client.get(f"{API}/contacts/birthdays", params={"within_days": 7}, headers=alpha.auth())
        assert resp.status_code == 200, resp.text
        entry = next((b for b in resp.json() if b["id"] == created["id"]), None)
        assert entry is not None, "customer with a birthday in 3 days was not listed"
        assert entry["days_away"] == 3
        assert entry["turning"] == soon.year - 1985
        assert entry["primary_phone"] == "+919000000001"
    finally:
        client.delete(f"{API}/contacts/{created['id']}", headers=alpha.auth())


def test_birthdays_do_not_cross_tenants(client, alpha, bravo):
    from datetime import date, timedelta

    soon = date.today() + timedelta(days=2)
    created = client.post(
        f"{API}/contacts",
        json={"first_name": "Alpha", "last_name": "Birthday",
              "date_of_birth": f"1980-{soon.month:02d}-{soon.day:02d}"},
        headers=alpha.auth(),
    ).json()
    try:
        theirs = client.get(f"{API}/contacts/birthdays", params={"within_days": 7}, headers=bravo.auth())
        assert created["id"] not in {b["id"] for b in theirs.json()}
    finally:
        client.delete(f"{API}/contacts/{created['id']}", headers=alpha.auth())


# --- notes --------------------------------------------------------------------

def test_notes_are_added_listed_and_attributed(client, alpha, customer):
    added = client.post(
        f"{API}/contacts/{customer['id']}/notes",
        json={"body": "Prefers a call after 6pm.", "is_pinned": True},
        headers=alpha.auth(),
    )
    assert added.status_code == 200, added.text
    assert added.json()["author"]["first_name"]

    listed = client.get(f"{API}/contacts/{customer['id']}/notes", headers=alpha.auth()).json()
    assert len(listed) == 1
    assert listed[0]["is_pinned"] is True


def test_notes_do_not_cross_tenants(client, alpha, bravo, customer):
    client.post(
        f"{API}/contacts/{customer['id']}/notes", json={"body": "private"}, headers=alpha.auth()
    )
    assert client.get(
        f"{API}/contacts/{customer['id']}/notes", headers=bravo.auth()
    ).status_code == 404


# --- the general CRM tenant is unaffected -------------------------------------

def test_a_contact_without_insurance_fields_still_works(client, alpha):
    """The general CRM path: no PII, no nominees, nothing required."""
    created = client.post(
        f"{API}/contacts",
        json={"first_name": "Plain", "last_name": "Contact", "emails": ["plain@example.com"]},
        headers=alpha.auth(),
    )
    assert created.status_code == 200, created.text
    try:
        body = created.json()
        assert body["has_pan"] is False
        assert body["pan_masked"] is None
        assert body["nominees"] == []
        assert body["full_name"] == "Plain Contact"
    finally:
        client.delete(f"{API}/contacts/{created.json()['id']}", headers=alpha.auth())
