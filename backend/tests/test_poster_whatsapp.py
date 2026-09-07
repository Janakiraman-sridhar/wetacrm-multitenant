"""Poster Studio and WhatsApp.

The claims worth testing: a design renders to a real image with merge fields
resolved, a batch produces one personalised poster per recipient, and the API path
refuses clearly rather than pretending to send when it is not configured.
"""

from datetime import date, timedelta

import pytest

from app.poster.render import apply_merge, render
from app.services import whatsapp

API = "/api/v1"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture()
def poster_customer(client, alpha):
    soon = date.today() + timedelta(days=3)
    row = client.post(
        f"{API}/contacts",
        json={
            "first_name": "Poster", "last_name": "Recipient", "mobile": "9876500001",
            "date_of_birth": f"1990-{soon.month:02d}-{soon.day:02d}",
        },
        headers=alpha.auth(),
    ).json()
    yield row
    client.delete(f"{API}/contacts/{row['id']}", headers=alpha.auth())


@pytest.fixture()
def template(client, alpha):
    resp = client.post(
        f"{API}/poster/templates",
        json={
            "name": "Test Poster", "category": "birthday", "size": "square",
            "background": {"color": "#4F46E5"},
            "layers": [
                {"type": "rect", "x": 40, "y": 40, "w": 1000, "h": 1000,
                 "fill": "#FFFFFF", "radius": 32},
                {"type": "text", "x": 100, "y": 300, "w": 880, "text": "Happy birthday {customer_name}",
                 "size": 64, "bold": True, "color": "#1E293B", "align": "center"},
                {"type": "text", "x": 100, "y": 500, "w": 880, "text": "from {agent_name}",
                 "size": 36, "color": "#64748B", "align": "center"},
            ],
        },
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()
    yield row
    client.delete(f"{API}/poster/templates/{row['id']}", headers=alpha.auth())


# --- the renderer -------------------------------------------------------------

def test_merge_replaces_known_fields_and_empties_unknown_ones():
    """A visible `{oops}` on a customer's poster is worse than a gap."""
    assert apply_merge("Hi {customer_name}", {"customer_name": "Meera"}) == "Hi Meera"
    assert apply_merge("Hi {nonexistent}!", {}) == "Hi !"


def test_render_produces_a_real_png():
    spec = {
        "size": "square",
        "background": {"color": "#FFFFFF"},
        "layers": [{"type": "text", "x": 40, "y": 40, "w": 1000, "text": "Hello {customer_name}",
                    "size": 48, "color": "#000000"}],
    }
    png = render(spec, {"customer_name": "Test"})
    assert png[:8] == PNG_MAGIC
    assert len(png) > 1000


def test_a_broken_layer_does_not_break_the_poster():
    """One bad layer must not cost the agent the whole design."""
    spec = {
        "size": "square",
        "layers": [
            {"type": "text", "x": 40, "y": 40, "w": 900, "text": "Fine", "size": 40},
            {"type": "image", "source": "missing-asset", "x": 0, "y": 0, "w": 100, "h": 100},
            {"type": "nonsense"},
        ],
    }
    assert render(spec, {})[:8] == PNG_MAGIC


def test_long_text_wraps_and_truncates_rather_than_overflowing():
    spec = {
        "size": "square",
        "layers": [{"type": "text", "x": 40, "y": 40, "w": 400, "size": 40, "max_lines": 2,
                    "text": "word " * 200}],
    }
    assert render(spec, {})[:8] == PNG_MAGIC


def test_both_canvas_sizes_render():
    for size, expected in (("square", 1080), ("story", 1920)):
        from io import BytesIO

        from PIL import Image

        png = render({"size": size, "layers": []}, {})
        image = Image.open(BytesIO(png))
        assert image.size[1] == expected, f"{size} rendered {image.size}"


# --- templates ----------------------------------------------------------------

def test_presets_are_seeded_only_where_the_studio_is_switched_on(client, alpha, platform_admin_token):
    """A general CRM workspace has the studio off, so seeding designs there is clutter."""
    admin = {"Authorization": f"Bearer {platform_admin_token}"}
    created = client.post(
        f"{API}/platform/tenants",
        json={
            "name": "Poster Agency", "owner_email": "owner-poster@example.com",
            "owner_password": "poster-pass-12", "template_key": "insurance_agent",
        },
        headers=admin,
    )
    assert created.status_code == 200, created.text
    token = client.post(
        f"{API}/auth/login",
        json={"email": "owner-poster@example.com", "password": "poster-pass-12"},
    ).json()["access_token"]

    theirs = client.get(f"{API}/poster/templates", headers={"Authorization": f"Bearer {token}"})
    assert theirs.status_code == 200, theirs.text
    assert {"Birthday wishes", "Renewal reminder"} <= {t["name"] for t in theirs.json()}

    # The general CRM tenant gets none — its template has the studio off.
    general = client.get(f"{API}/poster/templates", headers=alpha.auth()).json()
    assert not any(t["name"] == "Birthday wishes" for t in general)


def test_presets_can_be_added_on_demand(client, alpha):
    """A workspace that wants the studio later is not left with a blank canvas."""
    added = client.post(f"{API}/poster/seed-presets", headers=alpha.auth())
    assert added.status_code == 200, added.text
    names = {t["name"] for t in client.get(f"{API}/poster/templates", headers=alpha.auth()).json()}
    assert {"Birthday wishes", "Renewal reminder"} <= names


def test_merge_fields_are_advertised(client, alpha):
    body = client.get(f"{API}/poster/merge-fields", headers=alpha.auth()).json()
    assert "customer_name" in body["fields"]
    assert "policy_number" in body["fields"]
    assert body["sizes"]["square"] == {"width": 1080, "height": 1080}


def test_templates_do_not_cross_tenants(client, alpha, bravo, template):
    theirs = client.get(f"{API}/poster/templates", headers=bravo.auth()).json()
    assert template["id"] not in {t["id"] for t in theirs}
    assert client.patch(
        f"{API}/poster/templates/{template['id']}", json={"name": "Hijacked"}, headers=bravo.auth()
    ).status_code == 404


# --- preview ------------------------------------------------------------------

def test_preview_renders_an_unsaved_design(client, alpha):
    """The editor previews through the same renderer that produces the final file."""
    resp = client.post(
        f"{API}/poster/preview",
        json={"size": "square", "background": {"color": "#000000"},
              "layers": [{"type": "text", "x": 40, "y": 40, "w": 900,
                          "text": "{customer_name}", "size": 60, "color": "#FFFFFF"}]},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == PNG_MAGIC


def test_preview_uses_a_real_customer_when_asked(client, alpha, poster_customer):
    resp = client.post(
        f"{API}/poster/preview",
        json={"size": "square", "contact_id": poster_customer["id"],
              "layers": [{"type": "text", "x": 40, "y": 40, "w": 900,
                          "text": "{customer_name}", "size": 60}]},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200
    assert resp.content[:8] == PNG_MAGIC


def test_saved_template_preview(client, alpha, template):
    resp = client.get(f"{API}/poster/templates/{template['id']}/preview", headers=alpha.auth())
    assert resp.status_code == 200
    assert resp.content[:8] == PNG_MAGIC


# --- batches ------------------------------------------------------------------

def test_audience_lists_who_a_batch_would_go_to(client, alpha, poster_customer):
    people = client.get(
        f"{API}/poster/audience", params={"kind": "birthdays", "within_days": 7}, headers=alpha.auth()
    ).json()
    assert any(p["contact_id"] == poster_customer["id"] for p in people)


def test_batch_makes_one_personalised_poster_per_recipient(client, alpha, template, poster_customer):
    resp = client.post(
        f"{API}/poster/batches",
        json={"template_id": template["id"], "audience": "birthdays", "within_days": 7},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    batch = resp.json()
    entry = next((i for i in batch["items"] if i["contact_id"] == poster_customer["id"]), None)
    assert entry is not None, "the recipient was not in the batch"
    assert entry.get("file_key"), "no poster was produced for the recipient"
    assert entry["phone"] == "+919876500001"

    # Each file is a real, fetchable image.
    fetched = client.get(f"{API}/poster/file", params={"key": entry["file_key"]}, headers=alpha.auth())
    assert fetched.status_code == 200
    assert fetched.content[:8] == PNG_MAGIC


def test_batch_of_a_manual_selection(client, alpha, template, poster_customer):
    resp = client.post(
        f"{API}/poster/batches",
        json={"template_id": template["id"], "audience": "selection",
              "contact_ids": [poster_customer["id"]], "name": "Hand-picked"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1


def test_an_empty_audience_is_refused(client, alpha, template):
    resp = client.post(
        f"{API}/poster/batches",
        json={"template_id": template["id"], "audience": "selection", "contact_ids": []},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400


def test_a_generated_poster_cannot_be_fetched_by_another_tenant(
    client, alpha, bravo, template, poster_customer
):
    batch = client.post(
        f"{API}/poster/batches",
        json={"template_id": template["id"], "audience": "selection",
              "contact_ids": [poster_customer["id"]]},
        headers=alpha.auth(),
    ).json()
    key = batch["items"][0]["file_key"]
    resp = client.get(f"{API}/poster/file", params={"key": key}, headers=bravo.auth())
    assert resp.status_code == 404, "LEAK — another tenant fetched a generated poster"


def test_batches_are_listed_and_readable(client, alpha, template, poster_customer):
    created = client.post(
        f"{API}/poster/batches",
        json={"template_id": template["id"], "audience": "selection",
              "contact_ids": [poster_customer["id"]], "name": "Listed batch"},
        headers=alpha.auth(),
    ).json()
    listed = client.get(f"{API}/poster/batches", headers=alpha.auth()).json()
    assert any(b["id"] == created["id"] for b in listed)
    detail = client.get(f"{API}/poster/batches/{created['id']}", headers=alpha.auth()).json()
    assert detail["name"] == "Listed batch"


# --- whatsapp -----------------------------------------------------------------

def test_number_normalisation():
    assert whatsapp.normalise_number("9876543210") == "919876543210"
    assert whatsapp.normalise_number("+91 98765 43210") == "919876543210"
    assert whatsapp.normalise_number("12345") is None


def test_click_to_chat_link_carries_the_message():
    link = whatsapp.click_to_chat_link("9876543210", "Hello there")
    assert link.startswith("https://wa.me/919876543210?text=")
    assert "Hello%20there" in link or "Hello+there" in link


def test_status_reports_click_to_chat_when_the_api_is_not_configured(client, alpha):
    body = client.get(f"{API}/whatsapp/status", headers=alpha.auth()).json()
    assert body["provider"] == "click_to_chat"
    assert body["can_send_from_server"] is False
    assert body["click_to_chat"] is True


def test_link_endpoint_returns_a_link_and_records_it(client, alpha, poster_customer):
    resp = client.post(
        f"{API}/whatsapp/link",
        json={"contact_id": poster_customer["id"], "message": "Happy birthday!"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["link"].startswith("https://wa.me/919876500001")

    # Recorded, so a second agent can see the customer was already messaged.
    log = client.get(
        f"{API}/whatsapp/messages", params={"contact_id": poster_customer["id"]}, headers=alpha.auth()
    ).json()
    assert log and log[0]["channel"] == "click_to_chat"
    assert log[0]["status"] == "opened"


def test_a_customer_without_a_number_is_refused(client, alpha):
    no_phone = client.post(
        f"{API}/contacts", json={"first_name": "No", "last_name": "Phone"}, headers=alpha.auth()
    ).json()
    try:
        resp = client.post(
            f"{API}/whatsapp/link", json={"contact_id": no_phone["id"], "message": "hi"},
            headers=alpha.auth(),
        )
        assert resp.status_code == 400
    finally:
        client.delete(f"{API}/contacts/{no_phone['id']}", headers=alpha.auth())


def test_server_send_refuses_clearly_when_the_api_is_not_configured(client, alpha, poster_customer):
    """Never report a message as sent when nothing left the building."""
    resp = client.post(
        f"{API}/whatsapp/send",
        json={"contact_id": poster_customer["id"], "message": "Test"},
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "not set up" in resp.json()["detail"]

    # The attempt is still recorded, as failed rather than sent.
    log = client.get(
        f"{API}/whatsapp/messages", params={"contact_id": poster_customer["id"]}, headers=alpha.auth()
    ).json()
    assert any(m["status"] == "failed" for m in log)


def test_the_null_provider_never_claims_success():
    provider = whatsapp.NullProvider()
    assert provider.can_send is False
    for result in (
        provider.send_text("919876543210", "hi"),
        provider.send_media("919876543210", b"", "x.png", None),
        provider.send_template("919876543210", "tpl", []),
    ):
        assert result.ok is False
        assert result.error


def test_message_log_does_not_cross_tenants(client, alpha, bravo, poster_customer):
    client.post(
        f"{API}/whatsapp/link", json={"contact_id": poster_customer["id"], "message": "private"},
        headers=alpha.auth(),
    )
    theirs = client.get(f"{API}/whatsapp/messages", headers=bravo.auth()).json()
    assert not any(m.get("body") == "private" for m in theirs)


def test_a_layer_whose_fields_are_all_empty_is_dropped():
    """"Call {agent_mobile}" with no number renders a button reading just "Call".

    Worse than no button. A layer whose placeholders all came back empty is left
    out — but ordinary copy, and text where any field resolved, is untouched.
    """
    from app.poster.render import is_hollow

    assert is_hollow("Call {agent_mobile}", {"agent_mobile": ""}) is True
    assert is_hollow("Call {agent_mobile}", {}) is True
    assert is_hollow("Call {agent_mobile}", {"agent_mobile": "+91 98765 43210"}) is False
    # No placeholders at all — always keep it.
    assert is_hollow("Renewal due", {}) is False
    # One of two resolved — keep it; the sentence still says something.
    assert is_hollow("{agent_name} · {agent_mobile}", {"agent_name": "Priya"}) is False


def test_hollow_layers_do_not_reach_the_rendered_poster():
    spec = {
        "size": "square",
        "layers": [
            {"type": "text", "x": 40, "y": 40, "w": 900, "text": "Renewal due", "size": 48},
            {"type": "text", "x": 40, "y": 200, "w": 900, "text": "Call {agent_mobile}", "size": 40},
        ],
    }
    with_number = render(spec, {"agent_mobile": "+919876543210"})
    without = render(spec, {"agent_mobile": ""})
    assert with_number[:8] == PNG_MAGIC and without[:8] == PNG_MAGIC
    # Dropping a line of text means fewer pixels drawn, so a smaller PNG.
    assert len(without) < len(with_number), "the hollow layer was still drawn"


def test_a_layer_can_depend_on_data_it_does_not_display():
    """A button's background must vanish with its label, not linger as an empty pill.

    Dropping only the text left the coloured rect behind, which looks broken. A
    layer therefore declares what it needs, even when it shows none of it itself.
    """
    from app.poster.render import has_required

    assert has_required({"requires": "agent_mobile"}, {"agent_mobile": "+91999"}) is True
    assert has_required({"requires": "agent_mobile"}, {"agent_mobile": ""}) is False
    assert has_required({"requires": ["a", "b"]}, {"a": "x", "b": ""}) is False
    # No dependency declared — always drawn.
    assert has_required({"type": "rect"}, {}) is True


def test_the_whole_call_to_action_disappears_without_a_number():
    button = [
        {"type": "rect", "x": 240, "y": 700, "w": 600, "h": 96, "fill": "#F59E0B",
         "radius": 48, "requires": "agent_mobile"},
        {"type": "text", "x": 240, "y": 728, "w": 600, "text": "Call {agent_mobile}",
         "size": 38, "requires": "agent_mobile"},
    ]
    spec = {"size": "square", "background": {"color": "#0F172A"}, "layers": button}
    with_number = render(spec, {"agent_mobile": "+919876543210"})
    without = render(spec, {"agent_mobile": ""})
    assert len(without) < len(with_number), "the empty button was still drawn"
