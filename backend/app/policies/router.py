"""Policies, the tenant's reference masters, and the renewal desk."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.contacts.models import Contact
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.filtering import apply_filters_for
from app.notifications.service import notify
from app.policies import service
from app.policies.models import MASTER_TYPES, POLICY_STATUSES, PRODUCT_LINES, Master, Policy
from app.policies.schemas import (
    MasterIn, MasterOut, MasterUpdate, PolicyCreate, PolicyOut, PolicyStatsOut, PolicyUpdate,
    RenewalDueOut, RenewIn,
)
from app.users.models import User

router = APIRouter(tags=["policies"])


# --- masters ------------------------------------------------------------------

@router.get("/masters", response_model=list[MasterOut], dependencies=[Depends(require_perm("policies:read"))])
def list_masters(type: str | None = None, active_only: bool = True, db: Session = Depends(get_db)):
    stmt = select(Master).order_by(Master.type, Master.order, Master.name)
    if type:
        stmt = stmt.where(Master.type == type)
    if active_only:
        stmt = stmt.where(Master.is_active.is_(True))
    return db.scalars(stmt).all()


@router.post("/masters", response_model=MasterOut)
def create_master(
    payload: MasterIn, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))
):
    if payload.type not in MASTER_TYPES:
        raise AppError(f"Type must be one of: {', '.join(MASTER_TYPES)}")
    if db.scalar(select(Master).where(Master.type == payload.type, Master.name == payload.name)):
        raise AppError(f"'{payload.name}' already exists in {payload.type}", 409)
    row = Master(**payload.model_dump())
    db.add(row)
    db.commit()
    return row


@router.patch("/masters/{master_id}", response_model=MasterOut)
def update_master(
    master_id: str,
    payload: MasterUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("settings:write")),
):
    row = get_or_404(db, Master, master_id, "Master")
    apply_updates(row, payload.model_dump(exclude_unset=True))
    db.commit()
    return row


@router.delete("/masters/{master_id}", response_model=Message)
def delete_master(
    master_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))
):
    """Retire a master entry.

    Deactivated rather than deleted when policies point at it, so historical records
    keep the insurer or bank they were actually written with.
    """
    row = get_or_404(db, Master, master_id, "Master")
    in_use = db.scalar(
        select(func.count()).select_from(Policy).where(
            or_(Policy.insurer_id == master_id, Policy.bank_id == master_id)
        )
    ) or 0
    if in_use:
        row.is_active = False
        db.commit()
        return {"detail": f"Used by {in_use} policy(s), so it was deactivated rather than deleted"}
    db.delete(row)
    db.commit()
    return {"detail": "Deleted"}


# --- policies -----------------------------------------------------------------

@router.get("/policies", response_model=Page[PolicyOut], dependencies=[Depends(require_perm("policies:read"))])
def list_policies(
    filters: str | None = Query(None),
    status: str | None = None,
    product_line: str | None = None,
    insurer_id: str | None = None,
    bank_id: str | None = None,
    customer_id: str | None = None,
    owner_id: str | None = None,
    expiring_within: int | None = Query(None, ge=0, le=730),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Policy)
    if status:
        stmt = stmt.where(Policy.status == status)
    if product_line:
        stmt = stmt.where(Policy.product_line == product_line)
    if insurer_id:
        stmt = stmt.where(Policy.insurer_id == insurer_id)
    if bank_id:
        stmt = stmt.where(Policy.bank_id == bank_id)
    if customer_id:
        stmt = stmt.where(Policy.customer_id == customer_id)
    if owner_id:
        stmt = stmt.where(Policy.owner_id == owner_id)
    if expiring_within is not None:
        today = date.today()
        stmt = stmt.where(
            Policy.expiry_date.isnot(None),
            Policy.expiry_date >= today,
            Policy.expiry_date <= today + timedelta(days=expiring_within),
        )
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(
            or_(Policy.policy_number.ilike(q), Policy.registration_no.ilike(q), Policy.plan_name.ilike(q))
        )
    stmt = apply_sort(stmt, Policy, params.sort)
    stmt = apply_filters_for(db, stmt, "policies", filters)
    return paginate(db, stmt, params)


@router.get("/policies/renewals", response_model=list[RenewalDueOut],
            dependencies=[Depends(require_perm("policies:read"))])
def renewals(
    within_days: int = Query(60, ge=1, le=365),
    include_lapsed: bool = False,
    db: Session = Depends(get_db),
):
    """The renewal desk: what needs chasing, soonest first."""
    return [
        {
            "id": p.id, "policy_number": p.policy_number, "product_line": p.product_line,
            "expiry_date": p.expiry_date, "days_to_expiry": p.days_to_expiry,
            "premium_gross": p.premium_gross, "status": p.status,
            "customer": p.customer, "insurer": p.insurer, "owner": p.owner,
        }
        for p in service.renewals_due(db, within_days, include_lapsed)
    ]


@router.get("/policies/stats", response_model=PolicyStatsOut,
            dependencies=[Depends(require_perm("policies:read"))])
def stats(db: Session = Depends(get_db)):
    """The KPI strip on the insurance dashboard."""
    today = date.today()
    month_start = today.replace(day=1)

    def renewals_within(days: int) -> int:
        return db.scalar(
            select(func.count()).select_from(Policy).where(
                Policy.status.in_(["active", "expiring"]),
                Policy.renewed_to_id.is_(None),
                Policy.expiry_date.isnot(None),
                Policy.expiry_date >= today,
                Policy.expiry_date <= today + timedelta(days=days),
            )
        ) or 0

    in_force = [Policy.status.in_(["active", "expiring"])]
    book_premium = db.scalar(
        select(func.coalesce(func.sum(Policy.premium_gross), 0)).where(*in_force)
    ) or Decimal(0)

    new_business = db.scalars(
        select(Policy).where(Policy.issue_date.isnot(None), Policy.issue_date >= month_start)
    ).all()

    birthday_keys = [
        f"{(today + timedelta(days=offset)).month:02d}{(today + timedelta(days=offset)).day:02d}"
        for offset in range(8)
    ]

    return {
        "customers": db.scalar(select(func.count()).select_from(Contact)) or 0,
        "active_policies": db.scalar(select(func.count()).select_from(Policy).where(*in_force)) or 0,
        "book_premium": book_premium,
        "renewals_60d": renewals_within(60),
        "renewals_30d": renewals_within(30),
        "renewals_7d": renewals_within(7),
        "lapsed": db.scalar(
            select(func.count()).select_from(Policy).where(Policy.status == "lapsed")
        ) or 0,
        "new_business_mtd_count": len(new_business),
        "new_business_mtd_premium": sum((p.premium_gross or Decimal(0)) for p in new_business) or Decimal(0),
        "birthdays_this_week": db.scalar(
            select(func.count()).select_from(Contact).where(Contact.birthday_key.in_(birthday_keys))
        ) or 0,
        "commission_mtd": sum((p.commission_amount or Decimal(0)) for p in new_business) or Decimal(0),
    }


@router.get("/policies/charts", dependencies=[Depends(require_perm("policies:read"))])
def charts(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db)):
    """Series for the dashboard: premium by month, and the book by insurer and line."""
    today = date.today()
    start = (today.replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)

    by_month: dict[str, dict] = {}
    cursor = start
    while cursor <= today:
        by_month[f"{cursor.year}-{cursor.month:02d}"] = {"month": f"{cursor.year}-{cursor.month:02d}",
                                                         "new": 0.0, "renewal": 0.0}
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    for policy in db.scalars(
        select(Policy).where(Policy.issue_date.isnot(None), Policy.issue_date >= start)
    ).all():
        key = f"{policy.issue_date.year}-{policy.issue_date.month:02d}"
        if key not in by_month:
            continue
        bucket = "renewal" if policy.renewal_of_id else "new"
        by_month[key][bucket] += float(policy.premium_gross or 0)

    def grouped(column, label_of):
        rows = db.execute(
            select(column, func.count(), func.coalesce(func.sum(Policy.premium_gross), 0))
            .where(Policy.status.in_(["active", "expiring"]))
            .group_by(column)
        ).all()
        return [
            {"name": label_of(key), "count": count, "premium": float(premium)}
            for key, count, premium in rows
            if key is not None
        ]

    insurers = {m.id: m.name for m in db.scalars(select(Master).where(Master.type == "insurer")).all()}
    return {
        "premium_by_month": list(by_month.values()),
        "by_insurer": sorted(
            grouped(Policy.insurer_id, lambda k: insurers.get(k, "Unknown")),
            key=lambda r: r["premium"], reverse=True,
        )[:10],
        "by_product_line": grouped(Policy.product_line, lambda k: k.title()),
        "by_status": [
            {"name": status, "count": count}
            for status, count in db.execute(
                select(Policy.status, func.count()).group_by(Policy.status)
            ).all()
        ],
    }


@router.get("/policies/{policy_id}", response_model=PolicyOut,
            dependencies=[Depends(require_perm("policies:read"))])
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Policy, policy_id, "Policy")


@router.get("/policies/{policy_id}/history", response_model=list[PolicyOut],
            dependencies=[Depends(require_perm("policies:read"))])
def history(policy_id: str, db: Session = Depends(get_db)):
    """Every policy in this renewal chain, oldest first."""
    policy = get_or_404(db, Policy, policy_id, "Policy")
    return service.renewal_chain(db, policy)


@router.post("/policies", response_model=PolicyOut)
def create_policy(
    payload: PolicyCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("policies:write"))
):
    data = payload.model_dump()
    if data["product_line"] not in PRODUCT_LINES:
        raise AppError(f"Product line must be one of: {', '.join(PRODUCT_LINES)}")
    if data.get("status") not in POLICY_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(POLICY_STATUSES)}")
    if db.scalar(select(Policy).where(Policy.policy_number == data["policy_number"])):
        raise AppError(f"Policy number {data['policy_number']} already exists", 409)

    get_or_404(db, Contact, data["customer_id"], "Customer")
    data["details"] = service.validate_details(data["product_line"], data.get("details"))
    data["premium_net"], data["premium_gst"], data["premium_gross"] = service.compute_premium(
        data.get("premium_net"), data.get("premium_gst"), data.get("premium_gross")
    )
    data.setdefault("owner_id", None)
    if not data["owner_id"]:
        data["owner_id"] = user.id

    policy = Policy(**data)
    # Status follows the expiry date, so a policy entered with a past date lands as
    # lapsed rather than sitting in the book as active.
    policy.status = service.derive_status(policy)
    db.add(policy)
    db.flush()

    log_activity(db, "policy", policy.id, "system", f"Policy {policy.policy_number} created", user_id=user.id)
    log_activity(db, "contact", policy.customer_id, "system",
                 f"Policy {policy.policy_number} issued", user_id=user.id)
    audit(db, user.id, "create", "policy", policy.id,
          {"number": policy.policy_number, "premium": str(policy.premium_gross)})
    db.commit()
    return policy


@router.patch("/policies/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("policies:write")),
):
    policy = get_or_404(db, Policy, policy_id, "Policy")
    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] not in POLICY_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(POLICY_STATUSES)}")
    if "details" in data:
        data["details"] = service.validate_details(data.get("product_line") or policy.product_line,
                                                   data["details"])
    if {"premium_net", "premium_gst", "premium_gross"} & data.keys():
        data["premium_net"], data["premium_gst"], data["premium_gross"] = service.compute_premium(
            data.get("premium_net", policy.premium_net),
            data.get("premium_gst", policy.premium_gst),
            data.get("premium_gross"),
        )

    changes = apply_updates(policy, data)
    if "expiry_date" in changes and policy.status not in ("renewed", "cancelled"):
        policy.status = service.derive_status(policy)
    if changes:
        audit(db, user.id, "update", "policy", policy.id, changes)
    db.commit()
    return policy


@router.post("/policies/{policy_id}/renew", response_model=PolicyOut)
def renew_policy(
    policy_id: str,
    payload: RenewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("policies:write")),
):
    """Create the replacement policy and mark this one renewed.

    A new row rather than an edit, so what the customer was covered for last year
    remains on record.
    """
    previous = get_or_404(db, Policy, policy_id, "Policy")
    if db.scalar(select(Policy).where(Policy.policy_number == payload.policy_number)):
        raise AppError(f"Policy number {payload.policy_number} already exists", 409)

    renewal = service.build_renewal(db, previous, payload)
    log_activity(db, "policy", previous.id, "status_change",
                 f"Renewed as {renewal.policy_number}", user_id=user.id)
    log_activity(db, "contact", renewal.customer_id, "system",
                 f"Policy renewed: {previous.policy_number} → {renewal.policy_number}", user_id=user.id)
    audit(db, user.id, "renew", "policy", previous.id,
          {"renewed_to": renewal.policy_number, "premium": str(renewal.premium_gross)})
    if renewal.owner_id and renewal.owner_id != user.id:
        notify(db, renewal.owner_id, "policy_renewed",
               f"Policy renewed: {renewal.policy_number}",
               f"Renewed by {user.full_name}", f"/policies?id={renewal.id}")
    db.commit()
    return renewal


@router.delete("/policies/{policy_id}", response_model=Message)
def delete_policy(
    policy_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("policies:delete"))
):
    policy = get_or_404(db, Policy, policy_id, "Policy")
    number = policy.policy_number
    if policy.renewed_to_id:
        raise AppError("This policy has been renewed; delete the renewal first", 409)
    db.delete(policy)
    audit(db, user.id, "delete", "policy", policy_id, {"number": number})
    db.commit()
    return {"detail": "Policy deleted"}


@router.post("/policies/refresh-statuses", response_model=Message)
def refresh_statuses(db: Session = Depends(get_db), user: User = Depends(require_perm("policies:write"))):
    """Re-derive every policy's status from its expiry date.

    The nightly job does this automatically; the endpoint exists so it can be
    triggered by hand after a bulk import.
    """
    changed = service.refresh_statuses(db)
    return {"detail": f"{changed} policy status(es) updated"}
