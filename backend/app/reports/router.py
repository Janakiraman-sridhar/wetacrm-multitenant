from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activities.models import Activity
from app.companies.models import Company
from app.core.deps import require_perm
from app.database.base import utcnow
from app.database.session import get_db
from app.deals.models import Deal, DealStage
from app.leads.models import Lead, LeadSource
from app.meetings.models import Meeting
from app.tasks.models import Task
from app.users.models import User

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_perm("reports:read"))])


def _month_key(dt) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _last_12_months() -> list[str]:
    now = utcnow()
    months = []
    year, month = now.year, now.month
    for _ in range(12):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    revenue = db.scalar(select(func.coalesce(func.sum(Deal.value), 0)).where(Deal.status == "won")) or 0
    revenue_this_month = db.scalar(
        select(func.coalesce(func.sum(Deal.value), 0)).where(Deal.status == "won", Deal.closed_at >= month_start)
    ) or 0
    active_leads = db.scalar(select(func.count()).select_from(Lead).where(Lead.status.in_(["new", "contacted", "qualified"]))) or 0
    open_deals = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "open")) or 0
    open_deals_value = db.scalar(select(func.coalesce(func.sum(Deal.value), 0)).where(Deal.status == "open")) or 0
    won_deals = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "won")) or 0
    tasks_due_today = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.status.in_(["todo", "in_progress"]), Task.due_date >= today_start, Task.due_date < today_end
        )
    ) or 0

    upcoming_meetings = [
        {"id": m.id, "title": m.title, "starts_at": m.starts_at.isoformat(), "location": m.location}
        for m in db.scalars(select(Meeting).where(Meeting.starts_at >= now).order_by(Meeting.starts_at).limit(5))
    ]
    recent_activities = [
        {
            "id": a.id, "type": a.type, "title": a.title, "entity_type": a.entity_type,
            "created_at": a.created_at.isoformat(),
            "user": a.user.full_name if a.user else None,
        }
        for a in db.scalars(select(Activity).order_by(Activity.created_at.desc()).limit(8))
    ]

    # Monthly won revenue, grouped in Python for SQLite/Postgres portability
    months = _last_12_months()
    monthly = {m: 0.0 for m in months}
    year_ago = now - timedelta(days=370)
    for deal in db.scalars(select(Deal).where(Deal.status == "won", Deal.closed_at >= year_ago)):
        key = _month_key(deal.closed_at)
        if key in monthly:
            monthly[key] += float(deal.value or 0)
    monthly_sales = [{"month": m, "revenue": monthly[m]} for m in months]

    # Lead conversion per month (created vs converted)
    lead_monthly: dict[str, dict] = {m: {"created": 0, "converted": 0} for m in months}
    for lead in db.scalars(select(Lead).where(Lead.created_at >= year_ago)):
        key = _month_key(lead.created_at)
        if key in lead_monthly:
            lead_monthly[key]["created"] += 1
            if lead.status == "converted":
                lead_monthly[key]["converted"] += 1
    lead_conversion = [{"month": m, **lead_monthly[m]} for m in months]

    # Team performance: won value per owner
    perf = defaultdict(lambda: {"won_value": 0.0, "won_count": 0, "open_count": 0})
    for deal in db.scalars(select(Deal)):
        if not deal.owner_id:
            continue
        if deal.status == "won":
            perf[deal.owner_id]["won_value"] += float(deal.value or 0)
            perf[deal.owner_id]["won_count"] += 1
        elif deal.status == "open":
            perf[deal.owner_id]["open_count"] += 1
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    team_performance = sorted(
        [{"user_id": uid, "name": users.get(uid, "Unknown"), **stats} for uid, stats in perf.items()],
        key=lambda r: r["won_value"], reverse=True,
    )[:8]

    return {
        "kpis": {
            "revenue": float(revenue),
            "revenue_this_month": float(revenue_this_month),
            "active_leads": active_leads,
            "open_deals": open_deals,
            "open_deals_value": float(open_deals_value),
            "won_deals": won_deals,
            "tasks_due_today": tasks_due_today,
        },
        "upcoming_meetings": upcoming_meetings,
        "recent_activities": recent_activities,
        "monthly_sales": monthly_sales,
        "lead_conversion": lead_conversion,
        "team_performance": team_performance,
    }


@router.get("/funnel")
def sales_funnel(db: Session = Depends(get_db)):
    stages = db.scalars(select(DealStage).order_by(DealStage.order)).all()
    counts = dict(db.execute(select(Deal.stage_id, func.count()).group_by(Deal.stage_id)).all())
    values = dict(db.execute(select(Deal.stage_id, func.coalesce(func.sum(Deal.value), 0)).group_by(Deal.stage_id)).all())
    return [
        {"stage": s.name, "count": counts.get(s.id, 0), "value": float(values.get(s.id, 0))}
        for s in stages
    ]


@router.get("/lead-sources")
def lead_sources_report(db: Session = Depends(get_db)):
    rows = db.execute(select(Lead.source_id, func.count()).group_by(Lead.source_id)).all()
    sources = {s.id: s.name for s in db.scalars(select(LeadSource))}
    return [{"source": sources.get(sid, "Unknown"), "count": count} for sid, count in rows]


@router.get("/win-rate")
def win_rate(db: Session = Depends(get_db)):
    won = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "won")) or 0
    lost = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "lost")) or 0
    open_ = db.scalar(select(func.count()).select_from(Deal).where(Deal.status == "open")) or 0
    closed = won + lost
    return {"won": won, "lost": lost, "open": open_, "win_rate": round(won / closed * 100, 1) if closed else 0}


@router.get("/customer-growth")
def customer_growth(db: Session = Depends(get_db)):
    months = _last_12_months()
    counts = {m: 0 for m in months}
    year_ago = utcnow() - timedelta(days=370)
    for company in db.scalars(select(Company).where(Company.created_at >= year_ago)):
        key = _month_key(company.created_at)
        if key in counts:
            counts[key] += 1
    return [{"month": m, "count": counts[m]} for m in months]


@router.get("/activity")
def activity_report(days: int = 30, db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=min(days, 365))
    rows = db.execute(
        select(Activity.type, func.count()).where(Activity.created_at >= since).group_by(Activity.type)
    ).all()
    return [{"type": t, "count": c} for t, c in rows]
