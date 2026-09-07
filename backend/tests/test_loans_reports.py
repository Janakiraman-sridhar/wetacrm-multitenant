"""Loan cases and the insurance report suite.

What matters here is that the numbers are right and mean what they say: payout
follows the sanctioned amount, retention counts only cover that has actually
expired, and nothing sums across tenants.
"""

from datetime import date, timedelta

import pytest

API = "/api/v1"


@pytest.fixture()
def lender(client, alpha):
    resp = client.post(
        f"{API}/masters", json={"type": "bank", "name": "Loan Test Bank"}, headers=alpha.auth()
    )
    if resp.status_code == 409:
        rows = client.get(
            f"{API}/masters", params={"type": "bank", "active_only": False}, headers=alpha.auth()
        ).json()
        return next(m for m in rows if m["name"] == "Loan Test Bank")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture()
def borrower(client, alpha):
    row = client.post(
        f"{API}/contacts",
        json={"first_name": "Loan", "last_name": "Borrower", "mobile": "9700000001"},
        headers=alpha.auth(),
    ).json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


def make_loan(client, world, borrower, lender, **overrides):
    payload = {
        "customer_id": borrower["id"],
        "loan_type": "Home Loan",
        "lender_id": lender["id"],
        "amount_requested": "5000000",
        "tenure_months": 240,
        "applied_on": str(date.today()),
    }
    payload.update(overrides)
    resp = client.post(f"{API}/loans", json=payload, headers=world.auth())
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- loans --------------------------------------------------------------------

def test_a_loan_case_is_created_and_defaults_to_enquiry(client, alpha, borrower, lender):
    loan = make_loan(client, alpha, borrower, lender)
    try:
        assert loan["status"] == "enquiry"
        assert loan["is_open"] is True
        assert loan["customer"]["full_name"] == "Loan Borrower"
        assert loan["lender"]["name"] == "Loan Test Bank"
        # Unowned work goes nowhere, so it lands on whoever created it.
        assert loan["owner_id"]
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_payout_is_derived_from_the_sanctioned_amount(client, alpha, borrower, lender):
    """Lenders pay on what they sanction, not on what was asked for."""
    loan = make_loan(
        client, alpha, borrower, lender,
        amount_requested="5000000", amount_sanctioned="4000000", payout_percent="0.75",
    )
    try:
        # 0.75% of 40,00,000 = 30,000 — not of the 50,00,000 requested.
        assert str(loan["expected_payout"]) == "30000.00"
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_payout_is_recomputed_when_either_input_changes(client, alpha, borrower, lender):
    """A stale payout beside fresh numbers is how a report goes quietly wrong."""
    loan = make_loan(
        client, alpha, borrower, lender, amount_sanctioned="1000000", payout_percent="1"
    )
    try:
        assert str(loan["expected_payout"]) == "10000.00"
        raised = client.patch(
            f"{API}/loans/{loan['id']}", json={"amount_sanctioned": "2000000"}, headers=alpha.auth()
        ).json()
        assert str(raised["expected_payout"]) == "20000.00"
        retuned = client.patch(
            f"{API}/loans/{loan['id']}", json={"payout_percent": "0.5"}, headers=alpha.auth()
        ).json()
        assert str(retuned["expected_payout"]) == "10000.00"
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_moving_to_a_stage_stamps_its_date(client, alpha, borrower, lender):
    loan = make_loan(client, alpha, borrower, lender)
    try:
        sanctioned = client.patch(
            f"{API}/loans/{loan['id']}",
            json={"status": "sanctioned", "amount_sanctioned": "3000000", "payout_percent": "1"},
            headers=alpha.auth(),
        ).json()
        assert sanctioned["sanctioned_on"] == str(date.today())

        disbursed = client.patch(
            f"{API}/loans/{loan['id']}", json={"status": "disbursed"}, headers=alpha.auth()
        ).json()
        assert disbursed["disbursed_on"] == str(date.today())
        assert disbursed["is_open"] is False
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_an_explicit_date_is_not_overwritten(client, alpha, borrower, lender):
    loan = make_loan(client, alpha, borrower, lender)
    backdated = str(date.today() - timedelta(days=10))
    try:
        updated = client.patch(
            f"{API}/loans/{loan['id']}",
            json={"status": "disbursed", "disbursed_on": backdated},
            headers=alpha.auth(),
        ).json()
        assert updated["disbursed_on"] == backdated
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_an_unknown_status_is_rejected(client, alpha, borrower, lender):
    resp = client.post(
        f"{API}/loans",
        json={"customer_id": borrower["id"], "loan_type": "Home Loan", "status": "approved"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


def test_the_board_groups_only_open_cases(client, alpha, borrower, lender):
    open_case = make_loan(client, alpha, borrower, lender, status="documents")
    closed = make_loan(client, alpha, borrower, lender, loan_type="Personal Loan", status="disbursed")
    try:
        board = client.get(f"{API}/loans/board", headers=alpha.auth()).json()
        columns = {c["status"]: [l["id"] for l in c["loans"]] for c in board}
        assert open_case["id"] in columns["documents"]
        assert all(closed["id"] not in ids for ids in columns.values())
    finally:
        for row in (open_case, closed):
            client.delete(f"{API}/loans/{row['id']}", headers=alpha.auth())


def test_loan_stats_track_what_is_owed(client, alpha, borrower, lender):
    loan = make_loan(
        client, alpha, borrower, lender,
        status="disbursed", amount_sanctioned="2000000", payout_percent="1", actual_payout="8000",
    )
    try:
        stats = client.get(f"{API}/loans/stats", headers=alpha.auth()).json()
        assert float(stats["expected_payout"]) >= 20000
        assert float(stats["received_payout"]) >= 8000
        assert float(stats["outstanding_payout"]) >= 12000
        assert stats["by_status"]["disbursed"] >= 1
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_loans_do_not_cross_tenants(client, alpha, bravo, borrower, lender):
    loan = make_loan(client, alpha, borrower, lender)
    try:
        assert client.get(f"{API}/loans/{loan['id']}", headers=bravo.auth()).status_code == 404
        assert client.get(f"{API}/loans", headers=bravo.auth()).json()["total"] == 0
        theirs = client.get(f"{API}/loans/stats", headers=bravo.auth()).json()
        assert theirs["open_cases"] == 0
        assert float(theirs["expected_payout"]) == 0
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


# --- reports ------------------------------------------------------------------

@pytest.fixture()
def book(client, alpha, borrower):
    """A small book: one renewing, one expired-and-lapsed, one renewed."""
    insurer = client.post(
        f"{API}/masters", json={"type": "insurer", "name": "Report Insurer"}, headers=alpha.auth()
    )
    if insurer.status_code == 409:
        rows = client.get(
            f"{API}/masters", params={"type": "insurer", "active_only": False}, headers=alpha.auth()
        ).json()
        insurer = next(m for m in rows if m["name"] == "Report Insurer")
    else:
        insurer = insurer.json()

    today = date.today()
    made = []

    def add(**kwargs):
        payload = {
            "product_line": "motor", "customer_id": borrower["id"], "insurer_id": insurer["id"],
            "issue_date": str(today), "premium_net": "10000", "premium_gst": "1800",
            "commission_percent": "15",
        }
        payload.update(kwargs)
        resp = client.post(f"{API}/policies", json=payload, headers=alpha.auth())
        assert resp.status_code == 200, resp.text
        made.append(resp.json())
        return made[-1]

    expiring = add(policy_number="RPT-EXPIRING", expiry_date=str(today + timedelta(days=20)),
                   commission_amount="1770")
    lapsed = add(policy_number="RPT-LAPSED", expiry_date=str(today - timedelta(days=30)))
    to_renew = add(policy_number="RPT-RENEWED", expiry_date=str(today - timedelta(days=10)))

    start = today + timedelta(days=1)
    renewal = client.post(
        f"{API}/policies/{to_renew['id']}/renew",
        json={"policy_number": "RPT-RENEWED-2", "start_date": str(start),
              "expiry_date": str(start + timedelta(days=364)), "premium_gross": "12500"},
        headers=alpha.auth(),
    ).json()
    made.append(renewal)

    yield {"insurer": insurer, "expiring": expiring, "lapsed": lapsed,
           "renewed": to_renew, "renewal": renewal}

    for row in reversed(made):
        client.delete(f"{API}/policies/{row['id']}", headers=alpha.auth())


def test_the_renewal_register_carries_the_phone_number(client, alpha, book):
    """It is the day's call list, so it must not need a record opened per row."""
    rows = client.get(
        f"{API}/reports/insurance/renewals", params={"within_days": 60}, headers=alpha.auth()
    ).json()
    entry = next((r for r in rows if r["policy_number"] == "RPT-EXPIRING"), None)
    assert entry is not None
    assert entry["mobile"] == "+919700000001"
    assert entry["customer"] == "Loan Borrower"
    assert entry["days_to_expiry"] == 20


def test_production_splits_new_from_renewal(client, alpha, book):
    """An agency that cannot tell them apart cannot tell growth from retention."""
    report = client.get(f"{API}/reports/insurance/production", headers=alpha.auth()).json()
    assert report["total_policies"] >= 4
    month = f"{date.today().year}-{date.today().month:02d}"
    row = next(r for r in report["by_month"] if r["month"] == month)
    assert row["new"] > 0
    assert row["renewal"] > 0, "the renewal was counted as new business"
    assert any(r["name"] == "Report Insurer" for r in report["by_insurer"])


def test_retention_only_counts_cover_that_has_expired(client, alpha, book):
    """Counting unexpired policies as not-renewed would report a healthy book as collapsing."""
    report = client.get(f"{API}/reports/insurance/retention", headers=alpha.auth()).json()
    assert report["due"] >= 2
    assert report["renewed"] >= 1
    assert report["lapsed"] >= 1
    assert 0 <= report["retention_rate"] <= 100
    # The policy expiring in 20 days is not counted as lost.
    assert all(p["policy_number"] != "RPT-EXPIRING" for p in report["lapsed_policies"])


def test_commission_separates_booked_from_unbilled(client, alpha, book):
    """A percentage with no amount is money owed, not money worth nothing."""
    report = client.get(f"{API}/reports/insurance/commission", headers=alpha.auth()).json()
    assert report["policy_commission"] >= 1770
    missing = {p["policy_number"] for p in report["policies_missing_commission"]}
    assert "RPT-LAPSED" in missing, "a policy with a rate but no amount was silently ignored"


def test_cross_sell_names_the_gap(client, alpha, book):
    report = client.get(f"{API}/reports/insurance/cross-sell", headers=alpha.auth()).json()
    entry = next(
        (r for r in report["single_line_customers"] if r["customer"] == "Loan Borrower"), None
    )
    assert entry is not None
    assert entry["holds"] == ["motor"]
    assert set(entry["missing"]) == {"health", "life"}


def test_the_leaderboard_ranks_on_premium(client, alpha, book):
    rows = client.get(f"{API}/reports/insurance/leaderboard", headers=alpha.auth()).json()
    assert rows
    assert rows[0]["premium"] >= rows[-1]["premium"]
    assert sum(r["policies"] for r in rows) >= 4


def test_loan_payout_report_lists_what_is_still_owed(client, alpha, borrower, lender):
    loan = make_loan(
        client, alpha, borrower, lender,
        status="disbursed", amount_sanctioned="1000000", payout_percent="2", actual_payout="5000",
    )
    try:
        report = client.get(f"{API}/reports/insurance/loan-payouts", headers=alpha.auth()).json()
        entry = next((r for r in report["awaiting_payout"] if r["loan_id"] == loan["id"]), None)
        assert entry is not None, "a part-paid case was not listed as awaiting payout"
        assert entry["outstanding"] == 15000.0
        assert any(r["lender"] == "Loan Test Bank" for r in report["by_lender"])
    finally:
        client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_reports_do_not_sum_across_tenants(client, alpha, bravo, book):
    theirs = client.get(f"{API}/reports/insurance/production", headers=bravo.auth()).json()
    assert theirs["total_policies"] == 0
    assert theirs["total_premium"] == 0
    assert client.get(f"{API}/reports/insurance/renewals", headers=bravo.auth()).json() == []


# --- export -------------------------------------------------------------------

def test_the_renewal_register_exports_as_csv(client, alpha, book):
    resp = client.get(f"{API}/reports/insurance/renewals/export", headers=alpha.auth())
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "RPT-EXPIRING" in resp.text
    assert "policy_number" in resp.text


@pytest.mark.parametrize("report", ["renewals", "lapsed", "birthdays", "cross-sell", "loan-payouts"])
def test_every_advertised_export_works(client, alpha, report):
    resp = client.get(f"{API}/reports/insurance/{report}/export", headers=alpha.auth())
    assert resp.status_code == 200, resp.text


def test_an_unknown_export_says_what_is_available(client, alpha):
    resp = client.get(f"{API}/reports/insurance/nonsense/export", headers=alpha.auth())
    assert resp.status_code == 404
    assert "renewals" in resp.json()["detail"]


def test_a_case_entered_as_disbursed_gets_its_dates(client, alpha, borrower, lender):
    """Agencies enter existing cases at the stage they are already at."""
    loan = make_loan(client, alpha, borrower, lender,
                     status="disbursed", amount_sanctioned="1000000", payout_percent="1")
    assert loan["disbursed_on"] == str(date.today())
    assert loan["sanctioned_on"] == str(date.today())
    client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_a_date_supplied_on_create_is_kept(client, alpha, borrower, lender):
    when = str(date.today() - timedelta(days=45))
    loan = make_loan(client, alpha, borrower, lender, status="disbursed", disbursed_on=when)
    assert loan["disbursed_on"] == when
    client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())


def test_an_enquiry_gets_no_stage_dates(client, alpha, borrower, lender):
    loan = make_loan(client, alpha, borrower, lender)
    assert loan["sanctioned_on"] is None and loan["disbursed_on"] is None
    client.delete(f"{API}/loans/{loan['id']}", headers=alpha.auth())
