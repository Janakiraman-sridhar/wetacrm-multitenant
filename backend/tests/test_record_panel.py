"""Notes, attachments and the trails a record leaves.

All four have been written to the database since these modules were built and none
had a screen. These test the claims the new screens make: a note is dated and
attributed, a file belongs to one record, and the audit log says what changed.
"""

API = "/api/v1"


def _customer(client, world, name="Panel"):
    return client.post(
        f"{API}/contacts",
        json={"first_name": name, "last_name": "Subject", "mobile": "9800000009"},
        headers=world.auth(),
    ).json()


def _pdf() -> bytes:
    return b"%PDF-1.4\nprobe\n"


# --- dated notes ---------------------------------------------------------------

def test_a_note_is_dated_and_attributed(client, alpha):
    """The difference from the single notes box on the record."""
    customer = _customer(client, alpha, "Noted")
    try:
        made = client.post(
            f"{API}/contacts/{customer['id']}/notes",
            json={"body": "Called about the renewal.", "is_pinned": False},
            headers=alpha.auth(),
        )
        assert made.status_code == 200, made.text

        rows = client.get(f"{API}/contacts/{customer['id']}/notes", headers=alpha.auth()).json()
        assert len(rows) == 1
        assert rows[0]["author"] is not None, "a note nobody can be asked about"
        assert rows[0]["created_at"]
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_a_pinned_note_comes_first(client, alpha):
    customer = _customer(client, alpha, "Pinned")
    try:
        for body in ("older", "newer"):
            client.post(f"{API}/contacts/{customer['id']}/notes",
                        json={"body": body, "is_pinned": False}, headers=alpha.auth())
        rows = client.get(f"{API}/contacts/{customer['id']}/notes", headers=alpha.auth()).json()
        oldest = next(r for r in rows if r["body"] == "older")

        client.patch(
            f"{API}/contacts/{customer['id']}/notes/{oldest['id']}",
            json={"body": "older", "is_pinned": True}, headers=alpha.auth(),
        )
        after = client.get(f"{API}/contacts/{customer['id']}/notes", headers=alpha.auth()).json()
        assert after[0]["body"] == "older", "pinning did not lift it above the newer note"
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_writing_a_note_shows_up_on_the_timeline(client, alpha):
    """The panel's two tabs are fed by one action; the History tab must see it."""
    customer = _customer(client, alpha, "Trailed")
    try:
        client.post(f"{API}/contacts/{customer['id']}/notes",
                    json={"body": "Spoke to them.", "is_pinned": False}, headers=alpha.auth())
        timeline = client.get(
            f"{API}/activities",
            params={"entity_type": "contact", "entity_id": customer["id"]},
            headers=alpha.auth(),
        ).json()
        assert any("Note" in a["title"] for a in timeline["items"]), timeline["items"]
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_a_note_belongs_to_the_customer_it_was_written_on(client, alpha):
    """The path is checked, not just the id — otherwise any note id would do."""
    one = _customer(client, alpha, "Owner")
    two = _customer(client, alpha, "Stranger")
    try:
        note = client.post(f"{API}/contacts/{one['id']}/notes",
                           json={"body": "private", "is_pinned": False},
                           headers=alpha.auth()).json()
        resp = client.delete(f"{API}/contacts/{two['id']}/notes/{note['id']}", headers=alpha.auth())
        assert resp.status_code == 404
    finally:
        for row in (one, two):
            client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


# --- attachments ---------------------------------------------------------------

def test_a_file_attaches_to_one_record_only(client, alpha):
    customer = _customer(client, alpha, "Filed")
    try:
        made = client.post(
            f"{API}/documents",
            params={"entity_type": "contact", "entity_id": customer["id"]},
            files={"file": ("kyc.pdf", _pdf(), "application/pdf")},
            headers=alpha.auth(),
        )
        assert made.status_code == 200, made.text
        doc = made.json()
        assert doc["mime_type"] == "application/pdf"

        mine = client.get(f"{API}/documents",
                          params={"entity_type": "contact", "entity_id": customer["id"]},
                          headers=alpha.auth()).json()
        assert doc["id"] in [d["id"] for d in mine["items"]]

        elsewhere = client.get(f"{API}/documents",
                               params={"entity_type": "policy", "entity_id": customer["id"]},
                               headers=alpha.auth()).json()
        assert doc["id"] not in [d["id"] for d in elsewhere["items"]], "it showed up on another record"

        client.delete(f"{API}/documents/{doc['id']}", headers=alpha.auth())
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_the_panel_link_serves_the_file_without_a_bearer_token(client, alpha):
    """An `img src` or a new tab cannot send one, so the signature is the credential."""
    customer = _customer(client, alpha, "Linked")
    try:
        doc = client.post(
            f"{API}/documents",
            params={"entity_type": "contact", "entity_id": customer["id"]},
            files={"file": ("schedule.pdf", _pdf(), "application/pdf")},
            headers=alpha.auth(),
        ).json()
        link = client.get(f"{API}/documents/{doc['id']}/link", headers=alpha.auth()).json()
        assert link["url"].startswith("/api/v1/files/")

        served = client.get(link["url"])  # deliberately no auth header
        assert served.status_code == 200
        assert served.content.startswith(b"%PDF")
        assert served.headers["x-content-type-options"] == "nosniff"

        client.delete(f"{API}/documents/{doc['id']}", headers=alpha.auth())
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_a_file_does_not_cross_tenants(client, alpha, bravo):
    customer = _customer(client, alpha, "Sealed")
    try:
        doc = client.post(
            f"{API}/documents",
            params={"entity_type": "contact", "entity_id": customer["id"]},
            files={"file": ("private.pdf", _pdf(), "application/pdf")},
            headers=alpha.auth(),
        ).json()
        listed = client.get(f"{API}/documents",
                            params={"entity_type": "contact", "entity_id": customer["id"]},
                            headers=bravo.auth()).json()
        assert doc["id"] not in [d["id"] for d in listed["items"]]
        assert client.get(f"{API}/documents/{doc['id']}/link",
                          headers=bravo.auth()).status_code == 404

        client.delete(f"{API}/documents/{doc['id']}", headers=alpha.auth())
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


# --- the audit log -------------------------------------------------------------

def test_an_edit_is_recorded_with_its_before_and_after(client, alpha):
    """What the audit screen exists to show, and what makes it worth reading."""
    customer = _customer(client, alpha, "Audited")
    try:
        client.patch(f"{API}/contacts/{customer['id']}",
                     json={"occupation": "Engineer"}, headers=alpha.auth())

        log = client.get(f"{API}/audit-logs",
                         params={"entity_type": "contact", "entity_id": customer["id"]},
                         headers=alpha.auth()).json()
        updates = [r for r in log["items"] if r["action"] == "update"]
        assert updates, [r["action"] for r in log["items"]]

        change = updates[0]["changes"].get("occupation")
        assert isinstance(change, list) and len(change) == 2, updates[0]["changes"]
        assert change[1] == "Engineer"
        assert updates[0]["user"] is not None, "an entry with nobody attached proves nothing"
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_viewing_an_identity_number_shows_up_on_that_customer(client, alpha):
    """The reveal audit is the reason storing a PAN is defensible at all.

    It lands in the same table against the same record as an ordinary edit, which
    is what lets one panel on the customer answer both "what changed" and "who
    looked" — the question a tenant admin actually has.
    """
    customer = client.post(
        f"{API}/contacts",
        json={"first_name": "Revealed", "last_name": "Subject", "pan": "ABCDE1234F"},
        headers=alpha.auth(),
    ).json()
    try:
        shown = client.post(f"{API}/contacts/{customer['id']}/reveal",
                            json={"field": "pan"}, headers=alpha.auth())
        assert shown.status_code == 200, shown.text

        log = client.get(f"{API}/audit-logs",
                         params={"entity_type": "contact", "entity_id": customer["id"]},
                         headers=alpha.auth()).json()
        reveals = [r for r in log["items"] if r["action"] == "reveal_pii"]
        assert reveals, [r["action"] for r in log["items"]]
        assert reveals[0]["changes"]["field"] == "pan"
        assert reveals[0]["user"] is not None, "a reveal nobody can be pinned to"

        # And it is scoped to this customer, not the whole workspace.
        other = client.post(f"{API}/contacts", json={"first_name": "Untouched"},
                            headers=alpha.auth()).json()
        theirs = client.get(f"{API}/audit-logs",
                            params={"entity_type": "contact", "entity_id": other["id"]},
                            headers=alpha.auth()).json()
        assert not [r for r in theirs["items"] if r["action"] == "reveal_pii"]
        client.delete(f"{API}/contacts/{other['id']}", headers=alpha.auth())
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_the_audit_log_does_not_cross_tenants(client, alpha, bravo):
    customer = _customer(client, alpha, "Ours")
    try:
        client.patch(f"{API}/contacts/{customer['id']}",
                     json={"occupation": "Doctor"}, headers=alpha.auth())
        theirs = client.get(f"{API}/audit-logs",
                            params={"entity_type": "contact", "entity_id": customer["id"]},
                            headers=bravo.auth()).json()
        assert theirs["items"] == [], "one workspace could read another's audit trail"
    finally:
        client.delete(f"{API}/contacts/{customer['id']}", headers=alpha.auth())


def test_the_audit_log_is_read_only_over_http(client, alpha):
    """Nothing offers a way to delete an entry, and nothing should."""
    log = client.get(f"{API}/audit-logs", headers=alpha.auth()).json()
    if not log["items"]:
        return
    entry = log["items"][0]["id"]
    assert client.delete(f"{API}/audit-logs/{entry}", headers=alpha.auth()).status_code in (404, 405)
