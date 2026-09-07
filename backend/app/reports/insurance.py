"""The reports an insurance agency actually runs.

Each one answers a question an agent or owner asks out loud — what is expiring, what
did we write this month, who owes us commission, who is drifting away, who has only
one product. Anything that could not be phrased that way is not here.

Every figure is tenant-scoped by the global filter, so nothing in this file has to
remember to say so.
"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contacts.models import Contact
from app.loans.models import Loan
from app.policies.models import Master, Policy
from app.users.models import User


def _money(value) -> float:
    return float(value or 0)


def renewal_register(db: Session, within_days: int = 60, include_lapsed: bool = False) -> list[dict]:
    """What is expiring, with the contact details needed to chase it.

    The single most-used report in an agency: it *is* the day's call list, so it
    carries the phone number rather than making someone open each record.
    """
    from app.policies import service as policy_service

    return [
        {
            "policy_id": p.id,
            "policy_number": p.policy_number,
            "product_line": p.product_line,
            "customer": p.customer.full_name if p.customer else "",
            "mobile": p.customer.primary_phone if p.customer else None,
            "insurer": p.insurer.name if p.insurer else "",
            "expiry_date": p.expiry_date,
            "days_to_expiry": p.days_to_expiry,
            "premium": _money(p.premium_gross),
            "status": p.status,
            "agent": p.owner.full_name if p.owner else "",
        }
        for p in policy_service.renewals_due(db, within_days, include_lapsed)
    ]


def production(db: Session, months: int = 12) -> dict:
    """What was written, sliced the ways an agency reviews it.

    Counted by issue date, and split new vs renewal — an agency that cannot tell the
    two apart cannot tell growth from retention.
    """
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    policies = db.scalars(
        select(Policy).where(Policy.issue_date.isnot(None), Policy.issue_date >= start)
    ).all()

    by_month: dict[str, dict] = {}
    by_insurer: dict[str, dict] = {}
    by_line: dict[str, dict] = {}
    by_bank: dict[str, dict] = {}
    by_agent: dict[str, dict] = {}

    insurers = {m.id: m.name for m in db.scalars(select(Master).where(Master.type == "insurer")).all()}
    banks = {m.id: m.name for m in db.scalars(select(Master).where(Master.type == "bank")).all()}

    def add(bucket: dict, key: str, policy: Policy) -> None:
        row = bucket.setdefault(key, {"name": key, "count": 0, "premium": 0.0, "commission": 0.0})
        row["count"] += 1
        row["premium"] += _money(policy.premium_gross)
        row["commission"] += _money(policy.commission_amount)

    for policy in policies:
        month = f"{policy.issue_date.year}-{policy.issue_date.month:02d}"
        row = by_month.setdefault(month, {"month": month, "new": 0.0, "renewal": 0.0, "count": 0})
        row["renewal" if policy.renewal_of_id else "new"] += _money(policy.premium_gross)
        row["count"] += 1

        add(by_insurer, insurers.get(policy.insurer_id, "Unassigned"), policy)
        add(by_line, (policy.product_line or "other").title(), policy)
        add(by_bank, banks.get(policy.bank_id, "Direct"), policy)
        add(by_agent, policy.owner.full_name if policy.owner else "Unassigned", policy)

    ranked = lambda bucket: sorted(bucket.values(), key=lambda r: r["premium"], reverse=True)
    return {
        "period_months": months,
        "total_policies": len(policies),
        "total_premium": sum(_money(p.premium_gross) for p in policies),
        "total_commission": sum(_money(p.commission_amount) for p in policies),
        "by_month": sorted(by_month.values(), key=lambda r: r["month"]),
        "by_insurer": ranked(by_insurer),
        "by_product_line": ranked(by_line),
        "by_bank": ranked(by_bank),
        "by_agent": ranked(by_agent),
    }


def commission(db: Session, months: int = 12) -> dict:
    """Earned against received, and what that leaves outstanding.

    A policy with a commission percentage but no amount is treated as unbilled
    rather than zero — silently counting it as nothing is how an agency loses track
    of money it is owed.
    """
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    policies = db.scalars(
        select(Policy).where(Policy.issue_date.isnot(None), Policy.issue_date >= start)
    ).all()

    booked = sum(_money(p.commission_amount) for p in policies)
    unbilled = [p for p in policies if p.commission_percent and not p.commission_amount]

    loans = db.scalars(select(Loan).where(Loan.status == "disbursed")).all()
    loan_expected = sum(_money(l.expected_payout) for l in loans)
    loan_received = sum(_money(l.actual_payout) for l in loans)

    return {
        "policy_commission": booked,
        "policies_missing_commission": [
            {
                "policy_id": p.id, "policy_number": p.policy_number,
                "premium": _money(p.premium_gross), "percent": _money(p.commission_percent),
            }
            for p in unbilled
        ],
        "loan_payout_expected": loan_expected,
        "loan_payout_received": loan_received,
        "loan_payout_outstanding": loan_expected - loan_received,
        "total_earned": booked + loan_expected,
    }


def retention(db: Session, months: int = 12) -> dict:
    """How much of the book renewed, and how much walked.

    Measured on policies that have *reached* their expiry — counting cover that has
    not expired yet as "not renewed" would report a healthy book as collapsing.
    """
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    expired = db.scalars(
        select(Policy).where(
            Policy.expiry_date.isnot(None),
            Policy.expiry_date >= start,
            Policy.expiry_date < today,
        )
    ).all()

    renewed = [p for p in expired if p.renewed_to_id]
    lapsed = [p for p in expired if not p.renewed_to_id]
    total = len(expired)

    return {
        "period_months": months,
        "due": total,
        "renewed": len(renewed),
        "lapsed": len(lapsed),
        "retention_rate": round(len(renewed) / total * 100, 1) if total else None,
        "premium_retained": sum(_money(p.premium_gross) for p in renewed),
        "premium_lost": sum(_money(p.premium_gross) for p in lapsed),
        "lapsed_policies": [
            {
                "policy_id": p.id, "policy_number": p.policy_number,
                "customer": p.customer.full_name if p.customer else "",
                "mobile": p.customer.primary_phone if p.customer else None,
                "expired_on": p.expiry_date,
                "premium": _money(p.premium_gross),
            }
            for p in sorted(lapsed, key=lambda x: x.expiry_date, reverse=True)[:100]
        ],
    }


def cross_sell(db: Session) -> dict:
    """Customers holding one product line, and which they are missing.

    The cheapest business in an agency is the customer already on the books, so the
    report names the specific gap rather than just flagging "only one product".
    """
    policies = db.scalars(
        select(Policy).where(Policy.status.in_(["active", "expiring"]))
    ).all()

    lines_by_customer: dict[str, set] = {}
    for policy in policies:
        lines_by_customer.setdefault(policy.customer_id, set()).add(policy.product_line)

    all_lines = {"motor", "health", "life"}
    contacts = {c.id: c for c in db.scalars(select(Contact)).all()}

    opportunities = []
    for customer_id, lines in lines_by_customer.items():
        missing = sorted(all_lines - lines)
        if not missing:
            continue
        contact = contacts.get(customer_id)
        if not contact:
            continue
        opportunities.append({
            "contact_id": customer_id,
            "customer": contact.full_name,
            "mobile": contact.primary_phone,
            "holds": sorted(lines),
            "missing": missing,
        })

    without_any = [
        {"contact_id": c.id, "customer": c.full_name, "mobile": c.primary_phone}
        for c in contacts.values()
        if c.id not in lines_by_customer
    ]

    return {
        "single_line_customers": sorted(opportunities, key=lambda r: len(r["missing"]), reverse=True),
        "customers_with_no_policy": without_any[:200],
        "counts": {
            "with_gaps": len(opportunities),
            "with_no_policy": len(without_any),
        },
    }


def agent_leaderboard(db: Session, months: int = 3) -> list[dict]:
    """Who wrote what. Ranked on premium, because that is what the agency is paid on."""
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    policies = db.scalars(
        select(Policy).where(Policy.issue_date.isnot(None), Policy.issue_date >= start)
    ).all()
    loans = db.scalars(
        select(Loan).where(Loan.disbursed_on.isnot(None), Loan.disbursed_on >= start)
    ).all()

    rows: dict[str, dict] = {}

    def row_for(user: User | None) -> dict:
        name = user.full_name if user else "Unassigned"
        return rows.setdefault(name, {
            "agent": name, "policies": 0, "premium": 0.0,
            "commission": 0.0, "loans": 0, "loan_payout": 0.0,
        })

    for policy in policies:
        row = row_for(policy.owner)
        row["policies"] += 1
        row["premium"] += _money(policy.premium_gross)
        row["commission"] += _money(policy.commission_amount)

    for loan in loans:
        row = row_for(loan.owner)
        row["loans"] += 1
        row["loan_payout"] += _money(loan.expected_payout)

    return sorted(rows.values(), key=lambda r: r["premium"], reverse=True)


def loan_payouts(db: Session) -> dict:
    """Loan cases by lender, and what is still owed on the disbursed ones."""
    loans = db.scalars(select(Loan)).all()
    lenders = {m.id: m.name for m in db.scalars(select(Master).where(Master.type == "bank")).all()}

    by_lender: dict[str, dict] = {}
    for loan in loans:
        name = lenders.get(loan.lender_id, "Unassigned")
        row = by_lender.setdefault(name, {
            "lender": name, "cases": 0, "sanctioned": 0.0,
            "expected": 0.0, "received": 0.0,
        })
        row["cases"] += 1
        row["sanctioned"] += _money(loan.amount_sanctioned)
        if loan.status == "disbursed":
            row["expected"] += _money(loan.expected_payout)
            row["received"] += _money(loan.actual_payout)

    for row in by_lender.values():
        row["outstanding"] = row["expected"] - row["received"]

    return {
        "by_lender": sorted(by_lender.values(), key=lambda r: r["expected"], reverse=True),
        "awaiting_payout": [
            {
                "loan_id": l.id,
                "customer": l.customer.full_name if l.customer else "",
                "loan_type": l.loan_type,
                "lender": lenders.get(l.lender_id, ""),
                "disbursed_on": l.disbursed_on,
                "expected": _money(l.expected_payout),
                "received": _money(l.actual_payout),
                "outstanding": _money(l.payout_outstanding),
            }
            for l in loans
            if l.status == "disbursed" and (l.payout_outstanding or Decimal(0)) > 0
        ],
    }


def birthday_list(db: Session, within_days: int = 30) -> list[dict]:
    today = date.today()
    keys = [
        f"{(today + timedelta(days=offset)).month:02d}{(today + timedelta(days=offset)).day:02d}"
        for offset in range(within_days + 1)
    ]
    rows = db.scalars(
        select(Contact).where(Contact.birthday_key.in_(keys), Contact.date_of_birth.isnot(None))
    ).all()

    out = []
    for contact in rows:
        dob = contact.date_of_birth
        this_year = date(today.year, dob.month, dob.day)
        if this_year < today:
            this_year = date(today.year + 1, dob.month, dob.day)
        out.append({
            "contact_id": contact.id,
            "customer": contact.full_name,
            "mobile": contact.primary_phone,
            "date_of_birth": dob,
            "turning": this_year.year - dob.year,
            "days_away": (this_year - today).days,
        })
    return sorted(out, key=lambda r: r["days_away"])


def customer_growth(db: Session, months: int = 12) -> list[dict]:
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    rows = db.execute(
        select(Contact.created_at).where(Contact.created_at >= start)
    ).all()

    by_month: dict[str, int] = {}
    for (created,) in rows:
        key = f"{created.year}-{created.month:02d}"
        by_month[key] = by_month.get(key, 0) + 1

    running = db.scalar(
        select(func.count()).select_from(Contact).where(Contact.created_at < start)
    ) or 0
    out = []
    for month in sorted(by_month):
        running += by_month[month]
        out.append({"month": month, "added": by_month[month], "total": running})
    return out
