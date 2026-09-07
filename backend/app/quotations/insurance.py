"""Insurance quotations: several insurers quoted side by side, one of them chosen.

The one rule that shapes this module: **an insurance quotation's total is the
selected option, never the sum of the options.** A standard quotation's items are
things the customer buys together, so summing them is the total. Insurance options
are competing quotes for the *same* cover — three insurers quoting ₹12k, ₹14k and
₹16k is a ₹12k–₹16k decision, not a ₹42k sale. Summing them would put a number on
the PDF that no customer will ever pay.

Which is why the options live in their own JSON column rather than in
`quotation_items`: the billing engine's job is to add items up, and these must not
be added up.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.exceptions import AppError
from app.policies.service import compute_premium

#: Whitelisted keys on an option — same reasoning as `LINE_FIELDS` on a policy: a
#: free-form JSON blob becomes a dumping ground nobody can report on. A tenant that
#: needs another attribute adds a custom field.
OPTION_FIELDS = [
    "insurer_id", "insurer_name", "plan_name", "sum_insured", "premium_net",
    "premium_gst", "premium_gross", "idv", "ncb_percent", "add_ons", "features",
    "exclusions", "room_rent_limit", "co_pay_percent", "waiting_period_months",
    "policy_term_years", "claim_settlement_ratio", "network_hospitals",
    "recommended", "selected", "remarks",
]

#: Attributes the comparison PDF prints as rows, in the order an agent talks through
#: them. Only those present on at least one option are rendered.
COMPARISON_ROWS = [
    ("plan_name", "Plan"),
    ("sum_insured", "Sum insured"),
    ("idv", "IDV"),
    ("ncb_percent", "No-claim bonus"),
    ("premium_net", "Net premium"),
    ("premium_gst", "GST"),
    ("premium_gross", "Premium payable"),
    ("policy_term_years", "Term (years)"),
    ("room_rent_limit", "Room rent"),
    ("co_pay_percent", "Co-pay %"),
    ("waiting_period_months", "Waiting period (months)"),
    ("claim_settlement_ratio", "Claim settlement ratio"),
    ("network_hospitals", "Network hospitals"),
    ("add_ons", "Add-ons"),
    ("features", "Highlights"),
    ("exclusions", "Not covered"),
]

MONEY_FIELDS = {"sum_insured", "premium_net", "premium_gst", "premium_gross", "idv"}

#: Keys carried on the quotation alongside the options — the risk being quoted.
RISK_FIELDS = [
    "product_line", "sum_insured", "registration_no", "make", "model",
    "manufacture_year", "members", "age_band", "existing_policy_no",
    "existing_insurer", "expiry_date", "remarks",
]


def _money(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalise_options(options: list[dict] | None) -> list[dict]:
    """Clean the options and settle which one is selected.

    Premiums go through the same `compute_premium` a policy does, so an option
    quoted net-plus-GST and the policy it becomes cannot disagree about the gross.
    """
    cleaned: list[dict] = []
    for raw in options or []:
        option = {key: raw[key] for key in OPTION_FIELDS if key in raw}
        if not (option.get("insurer_name") or option.get("insurer_id")):
            raise AppError("Every option needs an insurer")
        net, gst, gross = compute_premium(
            option.get("premium_net"), option.get("premium_gst"), option.get("premium_gross")
        )
        option["premium_net"] = float(net)
        option["premium_gst"] = float(gst)
        option["premium_gross"] = float(gross)
        for key in ("sum_insured", "idv"):
            if option.get(key) not in (None, ""):
                option[key] = float(_money(option[key]))
        option["recommended"] = bool(option.get("recommended"))
        option["selected"] = bool(option.get("selected"))
        cleaned.append(option)

    if not cleaned:
        return cleaned

    # Exactly one selection. Two selected options means two totals, and the customer
    # would be shown whichever the code happened to reach first.
    selected = [o for o in cleaned if o["selected"]]
    if len(selected) > 1:
        raise AppError("Only one option can be selected")
    if not selected:
        # Fall back to the recommendation, then to the cheapest — an agent comparing
        # quotes has a total in mind before they have ticked anything.
        default = next((o for o in cleaned if o["recommended"]), None)
        if default is None:
            default = min(cleaned, key=lambda o: o["premium_gross"])
        default["selected"] = True
    return cleaned


def selected_option(insurance: dict | None) -> dict | None:
    return next((o for o in (insurance or {}).get("options", []) if o.get("selected")), None)


def clean_risk(insurance: dict | None) -> dict:
    """Strip the risk block to known keys, options normalised."""
    data = insurance or {}
    risk = {key: data[key] for key in RISK_FIELDS if key in data}
    risk["options"] = normalise_options(data.get("options"))
    return risk


def totals(insurance: dict | None) -> tuple[Decimal, Decimal, Decimal]:
    """(subtotal, tax, total) for an insurance quotation — the selected option only."""
    option = selected_option(insurance)
    if option is None:
        return Decimal(0), Decimal(0), Decimal(0)
    return (
        _money(option.get("premium_net")) or Decimal(0),
        _money(option.get("premium_gst")) or Decimal(0),
        _money(option.get("premium_gross")) or Decimal(0),
    )


def comparison_rows(insurance: dict | None) -> list[tuple[str, list]]:
    """Rows for the comparison table: only attributes some option actually carries."""
    options = (insurance or {}).get("options", [])
    rows = []
    for key, label in COMPARISON_ROWS:
        values = [option.get(key) for option in options]
        if all(value in (None, "", [], 0) for value in values):
            continue
        rows.append((label, values))
    return rows
