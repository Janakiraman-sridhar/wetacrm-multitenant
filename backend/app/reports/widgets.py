"""The canonical list of cards a dashboard can be built from.

The mirror of `app/platform/catalog.py`, for the same reason: the dashboard was a
hardcoded sequence in one React file, so an insurance workspace opened on six deal
figures reading zero, and a new vertical could only be served by adding another
`if` to that file. A vertical is a data decision here, not a code change — the
sidebar has worked that way since the module catalog landed and the dashboard was
the last screen still ignoring it.

`key` is stable and is what a template, a stored row and the frontend all use.
`requires` names the module a widget needs; a workspace without that module never
sees the widget, which reuses the gating already in place rather than inventing a
second rule for the dashboard.
"""

from dataclasses import dataclass

#: Settings row holding a workspace's own layout. A settings row rather than a
#: table because nothing points at a widget — unlike `tenant_modules`, which
#: permissions and routes join to.
DASHBOARD_SETTING = "dashboard_widgets"

#: The layout lives under this key inside that row. Settings values are objects
#: everywhere else and `SettingOut.value` is typed as one, so a bare list would
#: break `GET /settings` for every other row in the workspace.
DASHBOARD_KEY = "widgets"


@dataclass(frozen=True)
class WidgetDef:
    key: str
    label: str
    #: What it tells you, shown in the editor. An admin choosing between fourteen
    #: cards needs more than a name to choose with.
    description: str
    order: int
    #: Module key this widget reports on, or None for one that always applies.
    #: A widget whose module is switched off is not offered and not rendered.
    requires: str | None = None
    #: Two column widths: a strip of figures spans the row, a chart takes half.
    width: str = "half"
    #: Cannot be switched off — a dashboard with nothing on it is not a choice
    #: anyone means to make.
    locked: bool = False


WIDGET_CATALOG: list[WidgetDef] = [
    WidgetDef(
        "insurance_book", "Your book",
        "Customers, active policies, book premium, renewals due, new business, "
        "commission and birthdays — the figures an agent opens the day on.",
        1, requires="policies", width="full",
    ),
    WidgetDef(
        "renewals_due", "Renewals due",
        "Policies expiring in the next 7, 30 or 60 days, soonest first.",
        2, requires="policies",
    ),
    WidgetDef(
        "birthdays", "Birthdays",
        "Customers with a birthday today, this week or this month.",
        3, requires="contacts",
    ),
    WidgetDef(
        "deal_kpis", "Sales figures",
        "Revenue won, active leads, open and won deals, tasks due and meetings "
        "in the period.",
        4, requires="deals", width="full",
    ),
    WidgetDef(
        "revenue_series", "Revenue over time",
        "Won deal value by month across the selected period.",
        5, requires="deals",
    ),
    WidgetDef(
        "lead_conversion", "Lead conversion",
        "Leads created against leads converted, over time.",
        6, requires="leads",
    ),
    WidgetDef(
        "pipeline_by_stage", "Open pipeline by stage",
        "Where open deal value is sitting right now.",
        7, requires="deals",
    ),
    WidgetDef(
        "lead_sources", "Lead sources",
        "Which sources the period's leads came from.",
        8, requires="leads",
    ),
    WidgetDef(
        "win_rate", "Win rate",
        "Won against lost, for deals closed in the period.",
        9, requires="deals",
    ),
    WidgetDef(
        "tasks_overview", "Tasks overview",
        "Tasks by status for the period.",
        10, requires="tasks",
    ),
    WidgetDef(
        "upcoming_meetings", "Upcoming meetings",
        "What is in the calendar for the period.",
        11, requires="calendar",
    ),
    WidgetDef(
        "recent_activity", "Recent activity",
        "The latest entries from the activity timeline across the workspace.",
        12,
    ),
    WidgetDef(
        "team_performance", "Top performers",
        "Deals won by owner, for the period.",
        13, requires="deals",
    ),
]

WIDGETS_BY_KEY: dict[str, WidgetDef] = {w.key: w for w in WIDGET_CATALOG}


def widget_map(configured: list[dict] | None) -> dict[str, dict]:
    """Index a template's or tenant's widget list by key."""
    return {w["key"]: w for w in (configured or []) if w.get("key")}


def resolve(
    configured: list[dict] | None,
    enabled_modules: set[str],
    *,
    selective: bool,
) -> list[dict]:
    """The dashboard a workspace should see, in order.

    `selective` is the difference between the two moments this is read at, and
    getting it wrong is silent both ways:

    * **A template** is written by hand and may name four cards. Naming any is
      treated as naming all — anything left out is off, exactly as `_apply_modules`
      reads a template's module list. Listing four and getting thirteen is not what
      anyone means. Pass `selective=True`.
    * **A workspace's stored layout** is written by the editor and always names every
      widget. So a key it does not mention is one shipped *after* it was saved, and
      that gets the catalog default — the equivalent of `backfill_new_modules()`,
      without which a new card would arrive switched off for every workspace that
      already exists and nobody would ever see it. Pass `selective=False`.

    A widget whose module is switched off is dropped whatever the configuration says,
    reusing the rule that makes a disabled module gone rather than hidden.
    """
    overrides = widget_map(configured)
    # "Naming any names all" only bites when something *is* named. A template that
    # says nothing about the dashboard is unconfigured, not a request for a blank
    # one — the same reading `_apply_modules` gives an absent module list.
    selective = selective and bool(overrides)

    out = []
    for definition in WIDGET_CATALOG:
        if definition.requires and definition.requires not in enabled_modules:
            continue
        override = overrides.get(definition.key)
        if override is not None:
            enabled = bool(override.get("enabled", True))
        else:
            enabled = not selective
        if definition.locked:
            enabled = True
        out.append({
            "key": definition.key,
            "label": (override or {}).get("label") or definition.label,
            "description": definition.description,
            "enabled": enabled,
            "order": (override or {}).get("order") or definition.order,
            "width": (override or {}).get("width") or definition.width,
            "requires": definition.requires,
            "locked": definition.locked,
        })
    return sorted(out, key=lambda w: w["order"])


def materialise(template_config: list[dict] | None) -> list[dict]:
    """Turn a template's widget list into the complete layout a workspace stores.

    Every catalog key is named, so the stored row is a full picture and the tenant
    read path never has to re-apply template semantics. Module gating is deliberately
    *not* applied here: a workspace that switches Policies on later should get its
    book back without anyone re-provisioning it.
    """
    overrides = widget_map(template_config)
    selective = bool(overrides)
    rows = []
    for definition in WIDGET_CATALOG:
        override = overrides.get(definition.key)
        enabled = bool(override.get("enabled", True)) if override else not selective
        rows.append({
            "key": definition.key,
            "enabled": True if definition.locked else enabled,
            "order": (override or {}).get("order") or definition.order,
        })
    return sorted(rows, key=lambda w: w["order"])
