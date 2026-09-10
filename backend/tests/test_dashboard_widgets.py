"""The dashboard as data.

The claim worth testing: which cards a workspace opens on is decided by its
template and its own settings, not by a sequence written into a React file — and
the two moments that configuration is read at do not mean the same thing.
"""

import pytest

from app.reports import widgets

API = "/api/v1"

ALL_MODULES = {"policies", "contacts", "deals", "leads", "tasks", "calendar"}


def test_a_template_naming_any_card_is_naming_all_of_them():
    """The same rule `_apply_modules` reads a template's module list with.

    Listing the four cards a vertical should open on and silently getting the other
    nine is not what anyone means.
    """
    resolved = widgets.resolve(
        [{"key": "insurance_book"}, {"key": "birthdays"}], ALL_MODULES, selective=True
    )
    assert [w["key"] for w in resolved if w["enabled"]] == ["insurance_book", "birthdays"]


def test_a_workspace_layout_gains_cards_shipped_after_it_was_saved():
    """The equivalent of `backfill_new_modules()`.

    A stored layout always names every card it knew about, so a key it does not
    mention is one that shipped later. Read selectively, a new card would arrive
    switched off for every workspace that already exists and nobody would see it.
    """
    stored = [{"key": "insurance_book", "enabled": True, "order": 1}]
    resolved = widgets.resolve(stored, ALL_MODULES, selective=False)
    enabled = {w["key"] for w in resolved if w["enabled"]}

    assert "insurance_book" in enabled
    assert "birthdays" in enabled, "a card the stored layout predates was hidden"
    assert len(enabled) == len(resolved)


def test_switching_a_card_off_is_respected_either_way():
    for selective in (True, False):
        resolved = widgets.resolve(
            [{"key": "win_rate", "enabled": False}], ALL_MODULES, selective=selective
        )
        assert "win_rate" not in {w["key"] for w in resolved if w["enabled"]}


def test_a_card_whose_module_is_off_is_not_served_at_all():
    """Not merely hidden — the same rule that makes a disabled module gone."""
    resolved = widgets.resolve(
        [{"key": "insurance_book", "enabled": True}], {"contacts", "deals"}, selective=False
    )
    keys = {w["key"] for w in resolved}
    assert "insurance_book" not in keys
    assert "renewals_due" not in keys
    assert "birthdays" in keys, "a card whose module is on went missing with the others"


def test_materialise_writes_the_whole_picture():
    """What provisioning stores: every key, so no later read has to guess."""
    rows = widgets.materialise([{"key": "insurance_book", "enabled": True, "order": 1}])
    assert len(rows) == len(widgets.WIDGET_CATALOG)
    assert [r["key"] for r in rows if r["enabled"]] == ["insurance_book"]


def test_an_unconfigured_template_still_gets_everything():
    assert all(r["enabled"] for r in widgets.materialise(None))
    assert all(w["enabled"] for w in widgets.resolve(None, ALL_MODULES, selective=True))


# --- over HTTP ----------------------------------------------------------------

def test_a_workspace_serves_its_layout(client, alpha):
    resp = client.get(f"{API}/dashboard-widgets", headers=alpha.auth())
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, "no dashboard at all"
    assert all(w["enabled"] for w in rows), "a switched-off card was served to the page"
    assert all(w["description"] for w in rows), "a card with nothing to choose it by"


def test_the_editor_asks_for_the_hidden_ones_too(client, alpha):
    on_screen = client.get(f"{API}/dashboard-widgets", headers=alpha.auth()).json()
    everything = client.get(
        f"{API}/dashboard-widgets", params={"all_widgets": True}, headers=alpha.auth()
    ).json()
    assert len(everything) >= len(on_screen)


def test_saving_a_layout_changes_what_the_page_gets(client, alpha):
    everything = client.get(
        f"{API}/dashboard-widgets", params={"all_widgets": True}, headers=alpha.auth()
    ).json()
    original = [{"key": w["key"], "enabled": w["enabled"], "order": w["order"]} for w in everything]
    try:
        client.put(
            f"{API}/dashboard-widgets",
            json=[{"key": w["key"], "enabled": w["key"] != "tasks_overview", "order": i + 1}
                  for i, w in enumerate(everything)],
            headers=alpha.auth(),
        )
        after = client.get(f"{API}/dashboard-widgets", headers=alpha.auth()).json()
        assert "tasks_overview" not in [w["key"] for w in after]
        assert len(after) == len([w for w in everything if w["enabled"]]) - 1
    finally:
        client.put(f"{API}/dashboard-widgets", json=original, headers=alpha.auth())


def test_the_saved_order_is_the_order_served(client, alpha):
    everything = client.get(
        f"{API}/dashboard-widgets", params={"all_widgets": True}, headers=alpha.auth()
    ).json()
    original = [{"key": w["key"], "enabled": w["enabled"], "order": w["order"]} for w in everything]
    reversed_keys = [w["key"] for w in reversed(everything)]
    try:
        client.put(
            f"{API}/dashboard-widgets",
            json=[{"key": k, "enabled": True, "order": i + 1} for i, k in enumerate(reversed_keys)],
            headers=alpha.auth(),
        )
        after = client.get(f"{API}/dashboard-widgets", headers=alpha.auth()).json()
        assert [w["key"] for w in after] == reversed_keys
    finally:
        client.put(f"{API}/dashboard-widgets", json=original, headers=alpha.auth())


def test_a_layout_saved_in_the_first_shape_still_reads(client, alpha):
    """The stored shape changed from a bare list to an object under a `widgets` key.

    A workspace whose layout was saved before that change holds the old shape, and a
    reader that knows only the new one raises `AttributeError` and takes the whole
    dashboard down with a 500 — which is exactly what happened, on a real workspace,
    the moment the two shapes met. Both are read; a save normalises.
    """
    from sqlalchemy import select

    from app.database.session import SessionLocal
    from app.core.tenancy import tenant_scope
    from app.reports.widgets import DASHBOARD_SETTING
    from app.settings.models import Setting

    legacy = [{"key": "recent_activity", "enabled": True, "order": 1},
              {"key": "birthdays", "enabled": False, "order": 2}]
    with SessionLocal() as db, tenant_scope(alpha.tenant_id):
        row = db.scalar(select(Setting).where(Setting.key == DASHBOARD_SETTING))
        original = row.value if row else None
        if row is None:
            row = Setting(key=DASHBOARD_SETTING, value=legacy)
            db.add(row)
        else:
            row.value = legacy          # the bare list, as the first version wrote it
        db.commit()

    try:
        resp = client.get(f"{API}/dashboard-widgets", headers=alpha.auth())
        assert resp.status_code == 200, resp.text
        keys = [w["key"] for w in resp.json()]
        assert "recent_activity" in keys
        assert "birthdays" not in keys, "the old shape was read but its choices ignored"
    finally:
        with SessionLocal() as db, tenant_scope(alpha.tenant_id):
            row = db.scalar(select(Setting).where(Setting.key == DASHBOARD_SETTING))
            if row is not None:
                if original is None:
                    db.delete(row)
                else:
                    row.value = original
                db.commit()


def test_an_unknown_card_is_refused_by_name(client, alpha):
    resp = client.put(
        f"{API}/dashboard-widgets",
        json=[{"key": "moon_phase", "enabled": True}],
        headers=alpha.auth(),
    )
    assert resp.status_code == 400
    assert "moon_phase" in resp.json()["detail"]


def test_a_layout_does_not_cross_tenants(client, alpha, bravo):
    """Two workspaces on the same template still get their own dashboard."""
    everything = client.get(
        f"{API}/dashboard-widgets", params={"all_widgets": True}, headers=alpha.auth()
    ).json()
    original = [{"key": w["key"], "enabled": w["enabled"], "order": w["order"]} for w in everything]
    try:
        client.put(
            f"{API}/dashboard-widgets",
            json=[{"key": w["key"], "enabled": w["key"] == "recent_activity", "order": i + 1}
                  for i, w in enumerate(everything)],
            headers=alpha.auth(),
        )
        mine = client.get(f"{API}/dashboard-widgets", headers=alpha.auth()).json()
        theirs = client.get(f"{API}/dashboard-widgets", headers=bravo.auth()).json()
        assert [w["key"] for w in mine] == ["recent_activity"]
        assert len(theirs) > 1, "one workspace's dashboard reached another"
    finally:
        client.put(f"{API}/dashboard-widgets", json=original, headers=alpha.auth())


@pytest.mark.parametrize("definition", widgets.WIDGET_CATALOG, ids=lambda d: d.key)
def test_every_card_names_a_real_module(definition):
    """A typo in `requires` would silently hide a card from every workspace."""
    from app.platform.catalog import MODULES_BY_KEY

    if definition.requires:
        assert definition.requires in MODULES_BY_KEY, definition.requires
