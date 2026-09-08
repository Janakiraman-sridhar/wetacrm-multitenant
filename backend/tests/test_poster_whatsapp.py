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


# --- design controls, checked in pixels ---------------------------------------
#
# These read the rendered image rather than comparing byte lengths, because the
# bugs this section exists to catch were all of one kind: a control that changed
# the spec, changed nothing on the poster, and reported success. An agent then
# drags a slider, sees no difference, and concludes the studio is broken.

def _pixels(spec, values=None):
    from io import BytesIO

    from PIL import Image

    return Image.open(BytesIO(render(spec, values or {}))).convert("RGB")


def _on_black(layer):
    return {"size": "square", "background": {"color": "#000000"}, "layers": [layer]}


def _colours(image):
    """Every pixel as an (r, g, b) tuple. `getdata()` is on its way out of Pillow."""
    raw = image.tobytes()
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]


def test_text_opacity_blends_instead_of_being_thrown_away():
    """Half-opacity white text over black must land mid-grey.

    `draw.text` on an RGBA canvas *replaces* the pixel instead of blending it, and
    the final `convert("RGB")` then discards the alpha — so text drawn straight onto
    the canvas came out fully opaque however low the opacity was set.
    """
    layer = {"type": "text", "x": 0, "y": 100, "w": 1080, "text": "OPACITY",
             "size": 200, "color": "#FFFFFF", "align": "center", "bold": True}
    solid = _pixels(_on_black(layer))
    faded = _pixels(_on_black({**layer, "opacity": 0.5}))

    brightest_solid = max(_colours(solid), key=sum)
    brightest_faded = max(_colours(faded), key=sum)
    assert brightest_solid == (255, 255, 255)
    assert 100 < brightest_faded[0] < 180, brightest_faded


def test_a_rounded_shape_keeps_the_opacity_it_was_given():
    """Rounding the corners must not make a translucent panel solid.

    `_rounded` applied its mask with `putalpha`, which *replaces* the alpha channel
    — so any shape with both a radius and an opacity rendered fully opaque, and the
    frosted panel every one of these designs uses came out as a white slab.
    """
    panel = {"type": "rect", "x": 100, "y": 100, "w": 880, "h": 400,
             "fill": "#FFFFFF", "opacity": 0.2}
    square = _pixels(_on_black(panel)).getpixel((540, 300))
    rounded = _pixels(_on_black({**panel, "radius": 40})).getpixel((540, 300))

    assert square == rounded, "the corner radius changed the fill's opacity"
    assert square[0] < 90, f"20% white over black should stay dark, got {square}"


def test_a_gradient_background_changes_down_the_canvas():
    spec = {"size": "square", "layers": [],
            "background": {"color": "#000000", "gradient": {"to": "#FFFFFF"}}}
    image = _pixels(spec)
    assert image.getpixel((540, 5))[0] < 20
    assert image.getpixel((540, 1075))[0] > 235
    # Horizontal runs the other way; the top row is then a full sweep, not flat.
    across = _pixels({**spec, "background": {**spec["background"],
                                             "gradient": {"to": "#FFFFFF", "angle": "horizontal"}}})
    assert across.getpixel((5, 540))[0] < 20
    assert across.getpixel((1075, 540))[0] > 235


def test_a_line_layer_draws_where_it_is_told():
    spec = _on_black({"type": "line", "x": 200, "y": 500, "w": 600, "h": 10,
                      "fill": "#FF0000"})
    image = _pixels(spec)
    assert image.getpixel((500, 505)) == (255, 0, 0)
    assert image.getpixel((100, 505)) == (0, 0, 0), "the line leaked left of its x"
    assert image.getpixel((500, 400)) == (0, 0, 0), "the line leaked above its y"


def test_letter_spacing_widens_the_line():
    from app.poster.render import _line_width, load_font
    from PIL import Image, ImageDraw

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = load_font(40)
    assert _line_width(draw, "SPACED", font, 12) > _line_width(draw, "SPACED", font, 0)


def test_an_unknown_font_family_falls_back_rather_than_failing():
    """A family that resolves to nothing must not drop to Pillow's bitmap default."""
    from app.poster.render import load_font

    assert load_font(40, family="not-a-real-family").getname() == load_font(40).getname()
    # Italic is unavailable in some containers; the upright of the family is the
    # right answer there, not a different family.
    assert load_font(40, italic=True) is not None


def test_uppercase_is_applied_to_the_rendered_text_not_just_stored():
    lower = _on_black({"type": "text", "x": 0, "y": 100, "w": 1080, "text": "quiet",
                       "size": 160, "color": "#FFFFFF"})
    upper = {**lower, "layers": [{**lower["layers"][0], "uppercase": True}]}
    assert _pixels(lower).tobytes() != _pixels(upper).tobytes()


def test_an_outline_puts_its_own_colour_around_the_glyphs():
    spec = _on_black({"type": "text", "x": 0, "y": 100, "w": 1080, "text": "RING",
                      "size": 200, "color": "#FFFFFF", "align": "center", "bold": True,
                      "outline": {"color": "#FF0000", "width": 6}})
    colours = set(_colours(_pixels(spec)))
    assert any(r > 180 and g < 80 and b < 80 for r, g, b in colours), "no outline drawn"


def test_a_nonsense_opacity_is_treated_as_opaque_rather_than_crashing():
    from app.poster.render import _opacity_factor

    assert _opacity_factor(None) == 1.0
    assert _opacity_factor("nonsense") == 1.0
    assert _opacity_factor(5) == 1.0
    assert _opacity_factor(-2) == 0.0
    assert _opacity_factor(0.25) == 0.25


# --- the image library --------------------------------------------------------
#
# The point of these: an agent should be able to put their own picture on a poster,
# and the picture should not be able to put anything on the agent. So what a design
# can draw and what an upload can be are tested together.

def _png(size=(60, 40), colour=(220, 80, 40)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()


def _open(png: bytes):
    from io import BytesIO

    from PIL import Image

    return Image.open(BytesIO(png)).convert("RGB")


def _upload(client, world, data: bytes, name="picture.png", claimed="image/png"):
    return client.post(
        f"{API}/poster/assets",
        files={"file": (name, data, claimed)},
        headers=world.auth(),
    )


@pytest.fixture()
def asset(client, alpha):
    resp = _upload(client, alpha, _png((600, 400)))
    assert resp.status_code == 200, resp.text
    row = resp.json()
    yield row
    client.delete(f"{API}/poster/assets/{row['id']}", headers=alpha.auth())


def test_an_uploaded_picture_records_what_it_actually_is(asset):
    """Dimensions come from the file, not from the form."""
    assert (asset["width"], asset["height"]) == (600, 400)
    assert asset["mime_type"] == "image/png"
    assert asset["size_bytes"] > 0


def test_the_stored_type_comes_from_the_bytes_not_the_header(client, alpha):
    """A PNG announced as a JPEG is stored as what it is.

    Whatever is recorded here is the `Content-Type` the file is later served with,
    so believing the uploader would let them choose it.
    """
    resp = _upload(client, alpha, _png(), name="lie.jpg", claimed="image/jpeg")
    assert resp.status_code == 200, resp.text
    assert resp.json()["mime_type"] == "image/png"
    client.delete(f"{API}/poster/assets/{resp.json()['id']}", headers=alpha.auth())


@pytest.mark.parametrize(
    "name,data,claimed",
    [
        ("doc.pdf", b"%PDF-1.4\ncontent", "application/pdf"),
        ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
         "image/svg+xml"),
        ("page.html", b"<!doctype html><script>alert(1)</script>", "text/html"),
        ("empty.png", b"", "image/png"),
        # PNG magic then rubbish: passes the sniff, fails to decode. Accepting it
        # would mean a picture that uploads fine and then silently never draws.
        ("broken.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png"),
    ],
)
def test_what_a_poster_will_not_take(client, alpha, name, data, claimed):
    resp = _upload(client, alpha, data, name=name, claimed=claimed)
    assert resp.status_code == 400, f"{name} was accepted: {resp.text}"


def test_the_refusal_says_what_the_file_actually_was(client, alpha):
    """"Upload failed" tells an agent nothing about what to do next."""
    resp = _upload(client, alpha, b"%PDF-1.4\nx", name="scan.pdf", claimed="application/pdf")
    assert "application/pdf" in resp.json()["detail"]


def test_a_picture_is_served_as_the_type_it_passed_as(client, alpha, asset):
    resp = client.get(f"{API}/poster/assets/{asset['id']}/file", headers=alpha.auth())
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_a_picture_does_not_cross_tenants(client, alpha, bravo, asset):
    """The row and the bytes are both refused, not just the listing."""
    assert not [
        a for a in client.get(f"{API}/poster/assets", headers=bravo.auth()).json()
        if a["id"] == asset["id"]
    ]
    assert client.get(f"{API}/poster/assets/{asset['id']}/file",
                      headers=bravo.auth()).status_code == 404
    assert client.delete(f"{API}/poster/assets/{asset['id']}",
                         headers=bravo.auth()).status_code == 404


def test_a_design_can_draw_an_uploaded_picture(client, alpha, asset):
    spec = {
        "size": "square",
        "background": {"color": "#000000"},
        "layers": [{"type": "image", "x": 100, "y": 100, "w": 400, "h": 400,
                    "source": asset["id"], "fit": "cover"}],
    }
    drawn = client.post(f"{API}/poster/preview", json=spec, headers=alpha.auth())
    assert drawn.status_code == 200, drawn.text
    image = _open(drawn.content)
    assert image.getpixel((300, 300)) == (220, 80, 40), "the picture was not drawn"
    assert image.getpixel((900, 900)) == (0, 0, 0), "it drew outside its box"


def test_a_picture_can_be_the_background_and_the_scrim_darkens_it(client, alpha, asset):
    """The scrim is what keeps white text readable over a photo of unknown brightness."""
    plain = {"size": "square", "background": {"image": asset["id"]}, "layers": []}
    dark = {"size": "square",
            "background": {"image": asset["id"], "overlay": "#00000073"}, "layers": []}
    a = _open(client.post(f"{API}/poster/preview", json=plain, headers=alpha.auth()).content)
    b = _open(client.post(f"{API}/poster/preview", json=dark, headers=alpha.auth()).content)
    assert sum(a.getpixel((540, 540))) > sum(b.getpixel((540, 540)))


def test_a_deleted_picture_costs_its_layer_not_the_poster(client, alpha):
    """Someone will delete a picture a design still uses. It must not 500."""
    created = _upload(client, alpha, _png()).json()
    spec = {
        "size": "square",
        "background": {"color": "#000000"},
        "layers": [
            {"type": "image", "x": 100, "y": 100, "w": 400, "h": 400, "source": created["id"]},
            {"type": "text", "x": 0, "y": 700, "w": 1080, "text": "Still here",
             "size": 60, "color": "#FFFFFF", "align": "center"},
        ],
    }
    assert client.delete(f"{API}/poster/assets/{created['id']}",
                         headers=alpha.auth()).status_code == 200

    after = client.post(f"{API}/poster/preview", json=spec, headers=alpha.auth())
    assert after.status_code == 200, after.text
    image = _open(after.content)
    assert image.getpixel((300, 300)) == (0, 0, 0), "a deleted picture still drew"
    # The rest of the design survives — that is the whole point.
    assert any(px == (255, 255, 255) for px in _colours(image))


def test_only_the_pictures_a_design_names_are_fetched():
    """A workspace with forty pictures should not load thirty-nine per keystroke."""
    from app.poster.service import _sources

    spec = {
        "background": {"color": "#fff", "image": "bg-asset"},
        "layers": [
            {"type": "image", "source": "one"},
            {"type": "image", "asset_key": "two"},
            {"type": "text", "text": "hello", "source": "not-an-image-layer"},
            {"type": "image"},  # nothing chosen yet
            {"type": "rect", "fill": "#000"},
        ],
    }
    assert _sources(spec) == {"bg-asset", "one", "two"}
    assert _sources({"layers": [], "background": {}}) == set()


def test_an_empty_design_still_renders(client, alpha):
    """A new design starts blank; a studio that cannot preview one is unusable."""
    resp = client.post(f"{API}/poster/preview",
                       json={"size": "square", "layers": [], "background": {"color": "#FFFFFF"}},
                       headers=alpha.auth())
    assert resp.status_code == 200
    assert resp.content[:8] == PNG_MAGIC
