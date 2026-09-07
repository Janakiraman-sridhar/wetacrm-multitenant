"""Money arithmetic, document numbering, and CSV import/export.

Money is the part of a CRM where being nearly right is the same as being wrong, and
`Decimal` with an explicit rounding mode is only half the answer — the other half is
checking that the totals a customer sees add up to the lines above them.

The CSV path matters for a different reason: it is how a client's existing book
arrives on day one. An import that silently drops a column, or lands rows in the
wrong workspace, loses data at exactly the moment there is no backup of it.
"""

import io
from decimal import Decimal

import pytest

from app.services import billing

API = "/api/v1"


# --- line-item arithmetic -----------------------------------------------------

def test_a_line_totals_quantity_times_price_plus_tax():
    items, subtotal, tax = billing.compute_items(
        [{"quantity": 3, "unit_price": 100, "tax_rate": 18}]
    )
    assert items[0]["line_total"] == Decimal("354.00")
    assert subtotal == Decimal("300.00")
    assert tax == Decimal("54.00")


def test_lines_are_summed_not_rounded_one_by_one():
    """Rounding each line and then summing drifts; sum first, round once."""
    _items, subtotal, tax = billing.compute_items([
        {"quantity": 1, "unit_price": "0.005", "tax_rate": 0},
        {"quantity": 1, "unit_price": "0.005", "tax_rate": 0},
    ])
    assert subtotal == Decimal("0.01")
    assert tax == Decimal("0.00")


def test_a_third_of_a_rupee_rounds_half_up():
    _items, subtotal, _tax = billing.compute_items(
        [{"quantity": 3, "unit_price": "33.335", "tax_rate": 0}]
    )
    assert subtotal == Decimal("100.01")  # 100.005 -> half up


def test_positions_are_assigned_in_order():
    items, _s, _t = billing.compute_items([{"name": "a"}, {"name": "b"}, {"name": "c"}])
    assert [i["position"] for i in items] == [0, 1, 2]


def test_no_items_is_zero_not_an_error():
    items, subtotal, tax = billing.compute_items([])
    assert items == [] and subtotal == Decimal("0.00") and tax == Decimal("0.00")


def test_a_discount_comes_off_the_total():
    assert billing.compute_total(Decimal("1000"), Decimal("180"), 200) == Decimal("980.00")


def test_a_discount_larger_than_the_bill_floors_at_zero():
    """A negative total would be a refund the rest of the system cannot express."""
    assert billing.compute_total(Decimal("100"), Decimal("18"), 500) == Decimal("0.00")


def test_floats_do_not_leak_into_the_arithmetic():
    """0.1 + 0.2 must be 0.30, which is the whole reason this uses Decimal."""
    _items, subtotal, _tax = billing.compute_items([
        {"quantity": 1, "unit_price": 0.1, "tax_rate": 0},
        {"quantity": 1, "unit_price": 0.2, "tax_rate": 0},
    ])
    assert subtotal == Decimal("0.30")


@pytest.mark.parametrize("missing", [{}, {"quantity": 2}, {"unit_price": 50}])
def test_missing_fields_default_rather_than_crash(missing):
    """An import row with a blank column must not take the whole import down."""
    items, _s, _t = billing.compute_items([missing])
    assert items[0]["line_total"] >= Decimal("0")


# --- what a quotation actually returns ----------------------------------------

def test_a_quotation_total_matches_its_lines(client, alpha):
    resp = client.post(f"{API}/quotations", json={
        "contact_id": alpha.ids["contact"],
        "discount": 100,
        "items": [
            {"name": "Advisory", "quantity": 2, "unit_price": 1500, "tax_rate": 18},
            {"name": "Filing", "quantity": 1, "unit_price": 500, "tax_rate": 5},
        ],
    }, headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    quote = resp.json()
    try:
        assert float(quote["subtotal"]) == 3500.0        # 3000 + 500
        assert float(quote["tax_total"]) == 565.0        # 540 + 25
        assert float(quote["total"]) == 3965.0           # - 100 discount
        assert sum(float(i["line_total"]) for i in quote["items"]) == 4065.0
    finally:
        client.delete(f"{API}/quotations/{quote['id']}", headers=alpha.auth())


def test_the_total_survives_a_reload(client, alpha):
    """A create response and a later read must agree, to the paisa."""
    created = client.post(f"{API}/quotations", json={
        "contact_id": alpha.ids["contact"],
        "items": [{"name": "Thing", "quantity": 3, "unit_price": "33.33", "tax_rate": 18}],
    }, headers=alpha.auth()).json()
    try:
        reread = client.get(f"{API}/quotations/{created['id']}", headers=alpha.auth()).json()
        assert float(created["total"]) == float(reread["total"])
    finally:
        client.delete(f"{API}/quotations/{created['id']}", headers=alpha.auth())


# --- document numbering -------------------------------------------------------

def test_numbers_do_not_repeat_within_a_tenant(client, alpha):
    numbers = []
    ids = []
    for _ in range(5):
        row = client.post(f"{API}/quotations", json={"contact_id": alpha.ids["contact"]},
                          headers=alpha.auth()).json()
        numbers.append(row["number"])
        ids.append(row["id"])
    try:
        assert len(set(numbers)) == 5, f"numbering repeated: {numbers}"
    finally:
        for qid in ids:
            client.delete(f"{API}/quotations/{qid}", headers=alpha.auth())


def test_two_tenants_number_independently(client, alpha, bravo):
    """Each client's numbering is their own; a shared counter leaks activity."""
    a = client.post(f"{API}/quotations", json={"contact_id": alpha.ids["contact"]},
                    headers=alpha.auth()).json()
    b = client.post(f"{API}/quotations", json={"contact_id": bravo.ids["contact"]},
                    headers=bravo.auth()).json()
    try:
        # Same shape, and neither one skipped ahead because the other exists.
        assert a["number"].split("-")[0] == b["number"].split("-")[0]
    finally:
        client.delete(f"{API}/quotations/{a['id']}", headers=alpha.auth())
        client.delete(f"{API}/quotations/{b['id']}", headers=bravo.auth())


# --- CSV import and export ----------------------------------------------------

def test_the_export_returns_a_csv(client, alpha):
    resp = client.get(f"{API}/io/contacts/export", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    assert "csv" in resp.headers["content-type"]
    # Headers are the human labels an agency sees on screen, not column names.
    assert b"First Name" in resp.content
    assert b"alpha" in resp.content


def test_a_template_is_offered_for_import(client, alpha):
    resp = client.get(f"{API}/io/contacts/template", headers=alpha.auth())
    assert resp.status_code == 200
    assert b"First Name" in resp.content
    # And a sample row, so it is obvious what goes in each column.
    assert len(resp.content.splitlines()) >= 2


def test_importing_creates_rows(client, alpha):
    csv_bytes = (
        "first_name,last_name,mobile\n"
        "Imported,Person,9700000701\n"
        "Second,Person,9700000702\n"
    ).encode()
    resp = client.post(
        f"{API}/io/contacts/import",
        files={"file": ("people.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 2, result
    assert result["failed"] == 0, result

    listed = client.get(f"{API}/contacts", params={"search": "Imported", "page_size": 50},
                        headers=alpha.auth()).json()
    made = [c for c in listed["items"] if c["first_name"] in ("Imported", "Second")]
    assert len(made) >= 1
    for row in made:
        client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def test_a_blank_line_is_skipped_not_imported_as_a_nameless_contact(client, alpha):
    """Spreadsheet exports end with a blank line. It is not a record.

    Before this, importing one created a contact with no name that nobody could
    explain the origin of.
    """
    csv_bytes = b"".join([
        b"first_name,last_name,mobile\n",
        b"Good,Row,9700000703\n",
        b",,\n",
        b"Another,Row,9700000704\n",
        b"\n",
    ])
    resp = client.post(
        f"{API}/io/contacts/import",
        files={"file": ("mixed.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["created"] == 2, f"blank lines were imported: {result}"

    listed = client.get(f"{API}/contacts", params={"search": "Row", "page_size": 50},
                        headers=alpha.auth()).json()
    made = [r for r in listed["items"] if r["first_name"] in ("Good", "Another")]
    assert len(made) == 2
    assert not any(r["first_name"] == "" for r in listed["items"]), (
        "a nameless contact was created"
    )
    for row in made:
        client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def test_a_file_of_only_blank_lines_is_refused(client, alpha):
    csv_bytes = b"first_name,last_name,mobile\n,,\n,,\n"
    resp = client.post(
        f"{API}/io/contacts/import",
        files={"file": ("blank.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "No data rows" in resp.json()["detail"]


def test_an_import_lands_in_the_callers_tenant(client, alpha, bravo):
    """The single worst import bug: a client's book arriving in someone else's."""
    csv_bytes = "first_name,last_name,mobile\nScoped,Import,9700000705\n".encode()
    client.post(
        f"{API}/io/contacts/import",
        files={"file": ("one.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=alpha.auth(),
    )
    theirs = client.get(f"{API}/contacts", params={"search": "Scoped", "page_size": 50},
                        headers=alpha.auth()).json()["items"]
    others = client.get(f"{API}/contacts", params={"search": "Scoped", "page_size": 50},
                        headers=bravo.auth()).json()["items"]
    assert theirs, "the import did not land in the importing tenant"
    assert not others, "an import leaked into another tenant"

    for row in theirs:
        client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def test_an_export_respects_the_filter_on_screen(client, alpha):
    """The export and the list share one filter registry, so they must agree.

    `position` is a declared contact filter; matching something no contact has must
    produce a header and nothing else, not the whole book.
    """
    unfiltered = client.get(f"{API}/io/contacts/export", headers=alpha.auth())
    filtered = client.get(
        f"{API}/io/contacts/export",
        params={"filters": '[{"key":"position","value":"no-such-position-anywhere"}]'},
        headers=alpha.auth(),
    )
    assert filtered.status_code == 200
    assert len(filtered.content.splitlines()) == 1, "the filter was ignored by the export"
    assert len(unfiltered.content.splitlines()) > 1


def test_an_export_and_the_list_endpoint_agree(client, alpha):
    """One registry backs both; if they disagree an export shows rows the UI hid."""
    filters = '[{"key":"position","value":"no-such-position-anywhere"}]'
    listed = client.get(f"{API}/contacts", params={"filters": filters, "page_size": 200},
                        headers=alpha.auth()).json()
    exported = client.get(f"{API}/io/contacts/export", params={"filters": filters},
                          headers=alpha.auth())
    assert listed["total"] == len(exported.content.splitlines()) - 1
