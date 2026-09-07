"""Policy lifecycle: what each product line carries, when a status changes, and renewal.

Two rules shape everything here:

* **Status is derived, not typed.** `expiring` and `lapsed` come from the expiry date
  via a nightly job, never from a user picking them. That is what makes "renewals due
  in 60 days" a number you can act on rather than one that depends on someone
  remembering to update a dropdown.
* **A renewal is a new row.** The expiring policy is marked `renewed` and linked
  forward, so a customer's cover history survives — editing the old policy in place
  would destroy the record of what they were covered for last year.
"""

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.policies.models import PRODUCT_LINES, RENEWAL_WINDOWS, Policy

log = logging.getLogger("weta.policies")

#: Fields each product line carries beyond the common ones. Anything not listed is
#: dropped, so `details` cannot become a dumping ground — a tenant that needs more
#: adds a custom field (Phase 2) instead.
LINE_FIELDS: dict[str, list[str]] = {
    "motor": [
        "make", "model", "variant", "fuel_type", "cubic_capacity", "seating_capacity",
        "manufacture_year", "rto", "chassis_no", "engine_no", "idv", "ncb_percent",
        "od_premium", "tp_premium", "previous_insurer", "previous_policy_no",
        "claim_taken", "puc_expiry", "vehicle_type",
    ],
    "health": [
        "policy_type", "members", "pre_existing_diseases", "waiting_period_months",
        "room_rent_limit", "co_pay_percent", "portability_from", "top_up_deductible",
    ],
    "life": [
        "sum_assured", "policy_term_years", "premium_paying_term_years", "maturity_date",
        "riders", "bonus_type", "next_due_date", "plan_type",
    ],
    "general": [
        "risk_location", "coverage_type", "perils", "occupancy", "building_value",
        "contents_value",
    ],
}


def validate_details(product_line: str, details: dict | None) -> dict:
    """Keep only the fields that belong to this product line."""
    if product_line not in PRODUCT_LINES:
        raise AppError(f"Product line must be one of: {', '.join(PRODUCT_LINES)}")
    allowed = set(LINE_FIELDS.get(product_line, []))
    return {key: value for key, value in (details or {}).items() if key in allowed}


def compute_premium(net: Decimal | None, gst: Decimal | None, gross: Decimal | None) -> tuple:
    """Fill in whichever of net / GST / gross was left out.

    Agents have the gross from the receipt and the net from the insurer, rarely both
    plus the tax. Deriving the missing one keeps the book premium honest without
    making anyone do arithmetic.
    """
    net = Decimal(str(net)) if net is not None else None
    gst = Decimal(str(gst)) if gst is not None else None
    gross = Decimal(str(gross)) if gross is not None else None

    if gross is None and net is not None:
        gross = net + (gst or Decimal(0))
    elif net is None and gross is not None:
        net = gross - (gst or Decimal(0))
    if gst is None and net is not None and gross is not None:
        gst = gross - net

    # Quantised to match the Numeric(14, 2) columns, so the create response carries
    # the same value a later read does — otherwise a client formatting currency sees
    # "5900" on save and "5900.00" on reload.
    return tuple(_money(value) for value in (net, gst, gross))


def _money(value: Decimal | None) -> Decimal:
    return (value or Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --- status -------------------------------------------------------------------

def derive_status(policy: Policy, today: date | None = None) -> str:
    """What a policy's status should be, given its expiry date.

    Terminal states are left alone: a renewed, cancelled or draft policy is where
    someone deliberately put it.
    """
    if policy.status in ("renewed", "cancelled", "draft"):
        return policy.status
    if not policy.expiry_date:
        return policy.status

    today = today or date.today()
    days = (policy.expiry_date - today).days
    if days < 0:
        return "lapsed"
    if days <= max(RENEWAL_WINDOWS):
        return "expiring"
    return "active"


def refresh_statuses(db: Session, today: date | None = None) -> int:
    """Move policies between active, expiring and lapsed. Idempotent."""
    changed = 0
    for policy in db.scalars(
        select(Policy).where(Policy.status.in_(["active", "expiring", "lapsed"]))
    ).all():
        target = derive_status(policy, today)
        if target != policy.status:
            policy.status = target
            changed += 1
    if changed:
        db.commit()
    return changed


# --- renewal ------------------------------------------------------------------

def renewals_due(db: Session, within_days: int = 60, include_lapsed: bool = False):
    """Policies needing renewal work, soonest first."""
    today = date.today()
    cutoff = today + timedelta(days=within_days)
    statuses = ["active", "expiring"] + (["lapsed"] if include_lapsed else [])
    stmt = (
        select(Policy)
        .where(
            Policy.status.in_(statuses),
            Policy.expiry_date.isnot(None),
            Policy.expiry_date <= cutoff,
            Policy.renewed_to_id.is_(None),
        )
        .order_by(Policy.expiry_date)
    )
    if not include_lapsed:
        stmt = stmt.where(Policy.expiry_date >= today)
    return list(db.scalars(stmt).all())


def build_renewal(db: Session, previous: Policy, payload) -> Policy:
    """Create the replacement policy and link the two together.

    Everything not supplied is carried over — an agent renewing a motor policy
    should not have to retype the chassis number.
    """
    if previous.renewed_to_id:
        raise AppError("This policy has already been renewed", 409)
    if previous.status == "cancelled":
        raise AppError("A cancelled policy cannot be renewed", 400)

    net, gst, gross = compute_premium(
        payload.premium_net if payload.premium_net is not None else previous.premium_net,
        payload.premium_gst if payload.premium_gst is not None else previous.premium_gst,
        payload.premium_gross,
    )

    renewal = Policy(
        policy_number=payload.policy_number,
        product_line=previous.product_line,
        plan_name=payload.plan_name or previous.plan_name,
        insurer_id=payload.insurer_id or previous.insurer_id,
        bank_id=previous.bank_id,
        branch=previous.branch,
        sourcing_channel="renewal",
        customer_id=previous.customer_id,
        proposer_id=previous.proposer_id,
        owner_id=previous.owner_id,
        issue_date=date.today(),
        start_date=payload.start_date,
        expiry_date=payload.expiry_date,
        premium_net=net,
        premium_gst=gst,
        premium_gross=gross,
        sum_insured=payload.sum_insured if payload.sum_insured is not None else previous.sum_insured,
        currency=previous.currency,
        payment_frequency=previous.payment_frequency,
        commission_percent=previous.commission_percent,
        registration_no=previous.registration_no,
        remarks=payload.remarks,
        tags=list(previous.tags or []),
        details=dict(previous.details or {}),
        custom=dict(previous.custom or {}),
        renewal_of_id=previous.id,
        status="active",
    )
    db.add(renewal)
    db.flush()

    previous.renewed_to_id = renewal.id
    previous.status = "renewed"
    return renewal


def renewal_chain(db: Session, policy: Policy) -> list[Policy]:
    """The full history of this cover, oldest first."""
    chain: list[Policy] = []
    cursor = policy
    seen = set()
    while cursor and cursor.renewal_of_id and cursor.id not in seen:
        seen.add(cursor.id)
        previous = db.get(Policy, cursor.renewal_of_id)
        if not previous:
            break
        chain.insert(0, previous)
        cursor = previous

    chain.append(policy)

    cursor = policy
    seen = {policy.id}
    while cursor and cursor.renewed_to_id and cursor.renewed_to_id not in seen:
        nxt = db.get(Policy, cursor.renewed_to_id)
        if not nxt:
            break
        chain.append(nxt)
        seen.add(nxt.id)
        cursor = nxt
    return chain
