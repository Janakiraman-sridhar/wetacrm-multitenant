from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activities.models import Activity
from app.companies.models import Company
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.database.base import utcnow
from app.database.session import get_db
from app.deals.models import Deal, DealStage
from app.invoices.models import Invoice
from app.leads.models import Lead, LeadSource
from app.meetings.models import Meeting
from app.quotations.models import Quotation
from app.tasks.models import Task
from app.users.models import User

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_perm("reports:read"))])

ACTIVE_LEAD_STATUSES = ["new", "contacted", "qualified"]
DRILLDOWN_ROW_CAP = 500


# --- date-range helpers ---------------------------------------------------

def _range(start: date | None, end: date | None) -> tuple[datetime, datetime]:
    """Resolve optional query params to a [start, end] datetime window.

    Defaults to the last 12 months ending today.
    """
    end_d = end or date.today()
    start_d = start or (end_d - timedelta(days=365))
    if start_d > end_d:
        raise AppError("start must be on or before end", 400)
    return datetime.combine(start_d, time.min), datetime.combine(end_d, time.max)


def _bucket_keys(start_dt: datetime, end_dt: datetime) -> tuple[str, list[str]]:
    """Time-series buckets: daily for spans up to 45 days, monthly otherwise."""
    span_days = (end_dt - start_dt).days
    if span_days <= 45:
        keys, day = [], start_dt.date()
        while day <= end_dt.date():
            keys.append(day.isoformat())
            day += timedelta(days=1)
        return "day", keys
    keys = []
    year, month = start_dt.year, start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        keys.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return "month", keys


def _key_of(dt: datetime, granularity: str) -> str:
    return dt.date().isoformat() if granularity == "day" else f"{dt.year:04d}-{dt.month:02d}"


# --- scoped queries shared by dashboard and drilldown ---------------------

def _won_deals(db: Session, s: datetime, e: datetime) -> list[Deal]:
    return db.scalars(
        select(Deal).where(Deal.status == "won", Deal.closed_at >= s, Deal.closed_at <= e).order_by(Deal.closed_at.desc())
    ).all()


def _closed_deals(db: Session, s: datetime, e: datetime) -> list[Deal]:
    return db.scalars(
        select(Deal).where(Deal.status.in_(["won", "lost"]), Deal.closed_at >= s, Deal.closed_at <= e)
        .order_by(Deal.closed_at.desc())
    ).all()


def _open_deals(db: Session, s: datetime, e: datetime) -> list[Deal]:
    return db.scalars(
        select(Deal).where(Deal.status == "open", Deal.created_at >= s, Deal.created_at <= e)
        .order_by(Deal.created_at.desc())
    ).all()


def _leads_created(db: Session, s: datetime, e: datetime) -> list[Lead]:
    return db.scalars(
        select(Lead).where(Lead.created_at >= s, Lead.created_at <= e).order_by(Lead.created_at.desc())
    ).all()


def _tasks_due(db: Session, s: datetime, e: datetime) -> list[Task]:
    return db.scalars(
        select(Task).where(
            Task.status.in_(["todo", "in_progress"]), Task.due_date >= s, Task.due_date <= e
        ).order_by(Task.due_date.asc())
    ).all()


def _tasks_created(db: Session, s: datetime, e: datetime) -> list[Task]:
    return db.scalars(
        select(Task).where(Task.created_at >= s, Task.created_at <= e).order_by(Task.created_at.desc())
    ).all()


def _meetings_in(db: Session, s: datetime, e: datetime) -> list[Meeting]:
    return db.scalars(
        select(Meeting).where(Meeting.starts_at >= s, Meeting.starts_at <= e).order_by(Meeting.starts_at.asc())
    ).all()


def _invoices_in(db: Session, s: datetime, e: datetime) -> list[Invoice]:
    return db.scalars(
        select(Invoice).where(Invoice.created_at >= s, Invoice.created_at <= e).order_by(Invoice.created_at.desc())
    ).all()


def _quotations_in(db: Session, s: datetime, e: datetime) -> list[Quotation]:
    return db.scalars(
        select(Quotation).where(Quotation.created_at >= s, Quotation.created_at <= e).order_by(Quotation.created_at.desc())
    ).all()


def _activities_in(db: Session, s: datetime, e: datetime, limit: int) -> list[Activity]:
    return db.scalars(
        select(Activity).where(Activity.created_at >= s, Activity.created_at <= e)
        .order_by(Activity.created_at.desc()).limit(limit)
    ).all()


# --- dashboard ------------------------------------------------------------

@router.get("/dashboard")
def dashboard(
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
):
    s, e = _range(start, end)
    granularity, keys = _bucket_keys(s, e)

    won = _won_deals(db, s, e)
    closed = _closed_deals(db, s, e)
    open_deals = _open_deals(db, s, e)
    leads = _leads_created(db, s, e)
    tasks_due = _tasks_due(db, s, e)
    meetings = _meetings_in(db, s, e)

    revenue = sum(float(d.value or 0) for d in won)
    lost_count = len(closed) - len(won)

    # Revenue over time
    rev_buckets = {k: 0.0 for k in keys}
    for deal in won:
        key = _key_of(deal.closed_at, granularity)
        if key in rev_buckets:
            rev_buckets[key] += float(deal.value or 0)
    revenue_series = [{"period": k, "revenue": rev_buckets[k]} for k in keys]

    # Lead creation vs conversion over time
    lead_buckets: dict[str, dict] = {k: {"created": 0, "converted": 0} for k in keys}
    for lead in leads:
        key = _key_of(lead.created_at, granularity)
        if key in lead_buckets:
            lead_buckets[key]["created"] += 1
            if lead.status == "converted":
                lead_buckets[key]["converted"] += 1
    lead_conversion = [{"period": k, **lead_buckets[k]} for k in keys]

    # Open pipeline by stage (deals created in range, non-terminal stages)
    stages = db.scalars(select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order)).all()
    by_stage = defaultdict(lambda: {"count": 0, "value": 0.0})
    for deal in open_deals:
        by_stage[deal.stage_id]["count"] += 1
        by_stage[deal.stage_id]["value"] += float(deal.value or 0)
    pipeline_by_stage = [
        {"stage": st.name, "count": by_stage[st.id]["count"], "value": by_stage[st.id]["value"]}
        for st in stages
    ]

    # Lead sources
    source_names = {src.id: src.name for src in db.scalars(select(LeadSource))}
    src_counts: dict[str, int] = defaultdict(int)
    for lead in leads:
        src_counts[source_names.get(lead.source_id, "Unknown")] += 1
    lead_sources = sorted(
        [{"source": name, "count": count} for name, count in src_counts.items()],
        key=lambda r: r["count"], reverse=True,
    )

    # Win rate (deals closed in range)
    win_rate = {
        "won": len(won),
        "lost": lost_count,
        "win_rate": round(len(won) / len(closed) * 100, 1) if closed else 0,
    }

    # Tasks overview (tasks created in range, by status)
    task_counts: dict[str, int] = defaultdict(int)
    for task in _tasks_created(db, s, e):
        task_counts[task.status] += 1
    tasks_overview = [
        {"status": status, "count": task_counts.get(status, 0)}
        for status in ["todo", "in_progress", "done", "cancelled"]
    ]

    # Team performance (won in range / open created in range, per owner)
    perf = defaultdict(lambda: {"won_value": 0.0, "won_count": 0, "open_count": 0})
    for deal in won:
        if deal.owner_id:
            perf[deal.owner_id]["won_value"] += float(deal.value or 0)
            perf[deal.owner_id]["won_count"] += 1
    for deal in open_deals:
        if deal.owner_id:
            perf[deal.owner_id]["open_count"] += 1
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    team_performance = sorted(
        [{"user_id": uid, "name": users.get(uid, "Unknown"), **stats} for uid, stats in perf.items()],
        key=lambda r: r["won_value"], reverse=True,
    )[:8]

    upcoming = [m for m in meetings if m.starts_at >= utcnow()][:5] or meetings[:5]

    return {
        "start": s.date().isoformat(),
        "end": e.date().isoformat(),
        "granularity": granularity,
        "kpis": {
            "revenue": revenue,
            "won_deals": len(won),
            "active_leads": sum(1 for l in leads if l.status in ACTIVE_LEAD_STATUSES),
            "open_deals": len(open_deals),
            "open_deals_value": sum(float(d.value or 0) for d in open_deals),
            "tasks_due": len(tasks_due),
            "meetings": len(meetings),
        },
        "revenue_series": revenue_series,
        "lead_conversion": lead_conversion,
        "pipeline_by_stage": pipeline_by_stage,
        "lead_sources": lead_sources,
        "win_rate": win_rate,
        "tasks_overview": tasks_overview,
        "team_performance": team_performance,
        "upcoming_meetings": [
            {"id": m.id, "title": m.title, "starts_at": m.starts_at.isoformat(), "location": m.location}
            for m in upcoming
        ],
        "recent_activities": [
            {
                "id": a.id, "type": a.type, "title": a.title, "entity_type": a.entity_type,
                "created_at": a.created_at.isoformat(),
                "user": a.user.full_name if a.user else None,
            }
            for a in _activities_in(db, s, e, 8)
        ],
    }


# --- predefined report templates ------------------------------------------

REPORT_TEMPLATES = {
    "sales_performance": "Sales Performance",
    "pipeline_health": "Pipeline Health",
    "lead_generation": "Lead Generation",
    "team_performance": "Team Performance",
    "revenue_collections": "Revenue & Collections",
}


@router.get("/templates/{template_key}")
def report_template(
    template_key: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
):
    if template_key not in REPORT_TEMPLATES:
        raise AppError(f"Unknown report template '{template_key}'", 404)
    s, e = _range(start, end)
    granularity, keys = _bucket_keys(s, e)
    base = {
        "template": template_key,
        "title": REPORT_TEMPLATES[template_key],
        "start": s.date().isoformat(),
        "end": e.date().isoformat(),
        "granularity": granularity,
    }
    users = {u.id: u.full_name for u in db.scalars(select(User))}

    if template_key == "sales_performance":
        won = _won_deals(db, s, e)
        closed = _closed_deals(db, s, e)
        open_deals = _open_deals(db, s, e)
        revenue = sum(float(d.value or 0) for d in won)
        buckets = {k: 0.0 for k in keys}
        for d in won:
            key = _key_of(d.closed_at, granularity)
            if key in buckets:
                buckets[key] += float(d.value or 0)
        stages = db.scalars(select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order)).all()
        by_stage = defaultdict(lambda: {"count": 0, "value": 0.0})
        for d in open_deals:
            by_stage[d.stage_id]["count"] += 1
            by_stage[d.stage_id]["value"] += float(d.value or 0)
        perf = defaultdict(lambda: {"won_value": 0.0, "won_count": 0})
        for d in won:
            if d.owner_id:
                perf[d.owner_id]["won_value"] += float(d.value or 0)
                perf[d.owner_id]["won_count"] += 1
        return {
            **base,
            "kpis": {
                "revenue": revenue,
                "won_deals": len(won),
                "lost_deals": len(closed) - len(won),
                "win_rate": round(len(won) / len(closed) * 100, 1) if closed else 0,
                "avg_deal_size": round(revenue / len(won), 2) if won else 0,
                "open_pipeline_value": sum(float(d.value or 0) for d in open_deals),
            },
            "revenue_series": [{"period": k, "revenue": buckets[k]} for k in keys],
            "pipeline_by_stage": [
                {"stage": st.name, "count": by_stage[st.id]["count"], "value": by_stage[st.id]["value"]} for st in stages
            ],
            "top_performers": sorted(
                [{"name": users.get(uid, "Unknown"), **v} for uid, v in perf.items()],
                key=lambda r: r["won_value"], reverse=True,
            )[:8],
        }

    if template_key == "pipeline_health":
        open_deals = _open_deals(db, s, e)
        open_value = sum(float(d.value or 0) for d in open_deals)
        weighted = sum(float(d.value or 0) * (d.probability or 0) / 100 for d in open_deals)
        stages = db.scalars(select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order)).all()
        by_stage = defaultdict(lambda: {"count": 0, "value": 0.0, "weighted": 0.0})
        for d in open_deals:
            by_stage[d.stage_id]["count"] += 1
            by_stage[d.stage_id]["value"] += float(d.value or 0)
            by_stage[d.stage_id]["weighted"] += float(d.value or 0) * (d.probability or 0) / 100
        closes: dict[str, float] = defaultdict(float)
        for d in open_deals:
            if d.expected_close_date:
                closes[f"{d.expected_close_date.year:04d}-{d.expected_close_date.month:02d}"] += float(d.value or 0)
        return {
            **base,
            "kpis": {
                "open_deals": len(open_deals),
                "open_value": open_value,
                "weighted_forecast": round(weighted, 2),
                "avg_probability": round(sum(d.probability or 0 for d in open_deals) / len(open_deals), 1) if open_deals else 0,
                "no_close_date": sum(1 for d in open_deals if not d.expected_close_date),
            },
            "pipeline_by_stage": [
                {"stage": st.name, **{k: round(v, 2) if isinstance(v, float) else v for k, v in by_stage[st.id].items()}}
                for st in stages
            ],
            "expected_closes": [{"month": m, "value": round(v, 2)} for m, v in sorted(closes.items())],
            "top_open_deals": [
                {
                    "title": d.title, "company": d.company.name if d.company else "",
                    "stage": d.stage.name if d.stage else "", "value": float(d.value or 0),
                    "probability": d.probability, "owner": users.get(d.owner_id, ""),
                    "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else "",
                }
                for d in sorted(open_deals, key=lambda x: float(x.value or 0), reverse=True)[:10]
            ],
        }

    if template_key == "lead_generation":
        leads = _leads_created(db, s, e)
        converted = [l for l in leads if l.status == "converted"]
        buckets = {k: {"created": 0, "converted": 0} for k in keys}
        for l in leads:
            key = _key_of(l.created_at, granularity)
            if key in buckets:
                buckets[key]["created"] += 1
                if l.status == "converted":
                    buckets[key]["converted"] += 1
        source_names = {src.id: src.name for src in db.scalars(select(LeadSource))}
        src_counts: dict[str, int] = defaultdict(int)
        for l in leads:
            src_counts[source_names.get(l.source_id, "Unknown")] += 1
        status_counts: dict[str, int] = defaultdict(int)
        for l in leads:
            status_counts[l.status] += 1
        return {
            **base,
            "kpis": {
                "leads_created": len(leads),
                "converted": len(converted),
                "conversion_rate": round(len(converted) / len(leads) * 100, 1) if leads else 0,
                "avg_score": round(sum(l.score for l in leads) / len(leads), 1) if leads else 0,
                "unassigned": sum(1 for l in leads if not l.assigned_to_id),
            },
            "lead_series": [{"period": k, **buckets[k]} for k in keys],
            "lead_sources": sorted(
                [{"source": name, "count": c} for name, c in src_counts.items()], key=lambda r: r["count"], reverse=True
            ),
            "status_breakdown": [
                {"status": st, "count": status_counts.get(st, 0)}
                for st in ["new", "contacted", "qualified", "unqualified", "converted"]
            ],
        }

    if template_key == "team_performance":
        won = _won_deals(db, s, e)
        closed = _closed_deals(db, s, e)
        open_deals = _open_deals(db, s, e)
        rows: dict[str, dict] = defaultdict(lambda: {"won_value": 0.0, "won_count": 0, "lost_count": 0, "open_count": 0, "open_value": 0.0})
        for d in won:
            if d.owner_id:
                rows[d.owner_id]["won_value"] += float(d.value or 0)
                rows[d.owner_id]["won_count"] += 1
        for d in closed:
            if d.owner_id and d.status == "lost":
                rows[d.owner_id]["lost_count"] += 1
        for d in open_deals:
            if d.owner_id:
                rows[d.owner_id]["open_count"] += 1
                rows[d.owner_id]["open_value"] += float(d.value or 0)
        members = []
        for uid, r in rows.items():
            total_closed = r["won_count"] + r["lost_count"]
            members.append({
                "name": users.get(uid, "Unknown"),
                **{k: round(v, 2) if isinstance(v, float) else v for k, v in r.items()},
                "win_rate": round(r["won_count"] / total_closed * 100, 1) if total_closed else 0,
            })
        members.sort(key=lambda r: r["won_value"], reverse=True)
        return {
            **base,
            "kpis": {
                "active_members": len(members),
                "total_won_value": round(sum(m["won_value"] for m in members), 2),
                "total_won_deals": sum(m["won_count"] for m in members),
                "best_performer": members[0]["name"] if members else "—",
            },
            "members": members,
        }

    # revenue_collections
    invoices = _invoices_in(db, s, e)
    quotes = _quotations_in(db, s, e)
    invoiced = sum(float(i.total or 0) for i in invoices)
    collected = sum(float(i.amount_paid or 0) for i in invoices)
    inv_by_status = defaultdict(lambda: {"count": 0, "value": 0.0})
    for i in invoices:
        inv_by_status[i.status]["count"] += 1
        inv_by_status[i.status]["value"] += float(i.total or 0)
    inv_buckets = {k: 0.0 for k in keys}
    for i in invoices:
        key = _key_of(i.created_at, granularity)
        if key in inv_buckets:
            inv_buckets[key] += float(i.total or 0)
    decided = [q for q in quotes if q.status in ("accepted", "declined", "converted")]
    accepted = [q for q in decided if q.status in ("accepted", "converted")]
    return {
        **base,
        "kpis": {
            "invoiced_total": round(invoiced, 2),
            "collected_total": round(collected, 2),
            "outstanding": round(invoiced - collected, 2),
            "overdue_invoices": sum(1 for i in invoices if i.status == "overdue"),
            "quotations_issued": len(quotes),
            "quote_acceptance_rate": round(len(accepted) / len(decided) * 100, 1) if decided else 0,
        },
        "invoiced_series": [{"period": k, "value": round(inv_buckets[k], 2)} for k in keys],
        "invoices_by_status": [
            {"status": st, "count": v["count"], "value": round(v["value"], 2)} for st, v in sorted(inv_by_status.items())
        ],
        "quotes_by_status": [
            {"status": st, "count": sum(1 for q in quotes if q.status == st)}
            for st in ["draft", "sent", "accepted", "declined", "converted"]
        ],
    }


# --- drilldown: underlying rows for every KPI / chart ---------------------

def _deal_rows(deals: list[Deal]) -> tuple[list[dict], list[dict]]:
    columns = [
        {"key": "title", "label": "Deal", "type": "text"},
        {"key": "company", "label": "Company", "type": "text"},
        {"key": "stage", "label": "Stage", "type": "badge"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "value", "label": "Value", "type": "money"},
        {"key": "probability", "label": "Prob. %", "type": "number"},
        {"key": "owner", "label": "Owner", "type": "text"},
        {"key": "expected_close_date", "label": "Expected close", "type": "date"},
        {"key": "closed_at", "label": "Closed at", "type": "datetime"},
        {"key": "created_at", "label": "Created", "type": "datetime"},
    ]
    rows = [
        {
            "title": d.title,
            "company": d.company.name if d.company else "",
            "stage": d.stage.name if d.stage else "",
            "status": d.status,
            "value": float(d.value or 0),
            "currency": d.currency,
            "probability": d.probability,
            "owner": d.owner.full_name if d.owner else "",
            "expected_close_date": d.expected_close_date.isoformat() if d.expected_close_date else "",
            "closed_at": d.closed_at.isoformat(sep=" ", timespec="minutes") if d.closed_at else "",
            "created_at": d.created_at.isoformat(sep=" ", timespec="minutes"),
        }
        for d in deals
    ]
    return columns, rows


def _lead_rows(leads: list[Lead], source_names: dict) -> tuple[list[dict], list[dict]]:
    columns = [
        {"key": "title", "label": "Lead", "type": "text"},
        {"key": "company_name", "label": "Company", "type": "text"},
        {"key": "contact_name", "label": "Contact", "type": "text"},
        {"key": "email", "label": "Email", "type": "text"},
        {"key": "source", "label": "Source", "type": "text"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "score", "label": "Score", "type": "number"},
        {"key": "assigned_to", "label": "Assigned to", "type": "text"},
        {"key": "created_at", "label": "Created", "type": "datetime"},
    ]
    rows = [
        {
            "title": l.title,
            "company_name": l.company_name or "",
            "contact_name": l.contact_name or "",
            "email": l.email or "",
            "source": source_names.get(l.source_id, ""),
            "status": l.status,
            "score": l.score,
            "assigned_to": l.assigned_to.full_name if l.assigned_to else "",
            "created_at": l.created_at.isoformat(sep=" ", timespec="minutes"),
        }
        for l in leads
    ]
    return columns, rows


def _task_rows(tasks: list[Task]) -> tuple[list[dict], list[dict]]:
    columns = [
        {"key": "title", "label": "Task", "type": "text"},
        {"key": "priority", "label": "Priority", "type": "badge"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "due_date", "label": "Due", "type": "datetime"},
        {"key": "assigned_to", "label": "Assigned to", "type": "text"},
        {"key": "created_by", "label": "Created by", "type": "text"},
        {"key": "created_at", "label": "Created", "type": "datetime"},
    ]
    rows = [
        {
            "title": t.title,
            "priority": t.priority,
            "status": t.status,
            "due_date": t.due_date.isoformat(sep=" ", timespec="minutes") if t.due_date else "",
            "assigned_to": t.assigned_to.full_name if t.assigned_to else "",
            "created_by": t.created_by.full_name if t.created_by else "",
            "created_at": t.created_at.isoformat(sep=" ", timespec="minutes"),
        }
        for t in tasks
    ]
    return columns, rows


@router.get("/dashboard/drilldown")
def dashboard_drilldown(
    metric: str = Query(min_length=1, max_length=50),
    start: date | None = Query(None),
    end: date | None = Query(None),
    db: Session = Depends(get_db),
):
    s, e = _range(start, end)
    source_names = {src.id: src.name for src in db.scalars(select(LeadSource))}

    if metric in ("revenue", "won_deals", "revenue_series"):
        columns, rows = _deal_rows(_won_deals(db, s, e))
        title = "Won deals"
    elif metric == "open_deals" or metric == "pipeline_by_stage":
        columns, rows = _deal_rows(_open_deals(db, s, e))
        title = "Open deals"
    elif metric == "win_rate":
        columns, rows = _deal_rows(_closed_deals(db, s, e))
        title = "Closed deals (won + lost)"
    elif metric == "team_performance":
        deals = _won_deals(db, s, e) + _open_deals(db, s, e)
        columns, rows = _deal_rows(deals)
        title = "Deals by owner"
    elif metric == "active_leads":
        leads = [l for l in _leads_created(db, s, e) if l.status in ACTIVE_LEAD_STATUSES]
        columns, rows = _lead_rows(leads, source_names)
        title = "Active leads"
    elif metric in ("lead_conversion", "lead_sources"):
        columns, rows = _lead_rows(_leads_created(db, s, e), source_names)
        title = "Leads created"
    elif metric == "tasks_due":
        columns, rows = _task_rows(_tasks_due(db, s, e))
        title = "Tasks due"
    elif metric == "tasks_overview":
        columns, rows = _task_rows(_tasks_created(db, s, e))
        title = "Tasks created"
    elif metric in ("meetings", "upcoming_meetings"):
        columns = [
            {"key": "title", "label": "Meeting", "type": "text"},
            {"key": "starts_at", "label": "Starts", "type": "datetime"},
            {"key": "ends_at", "label": "Ends", "type": "datetime"},
            {"key": "location", "label": "Location", "type": "text"},
            {"key": "organizer", "label": "Organizer", "type": "text"},
        ]
        rows = [
            {
                "title": m.title,
                "starts_at": m.starts_at.isoformat(sep=" ", timespec="minutes"),
                "ends_at": m.ends_at.isoformat(sep=" ", timespec="minutes") if m.ends_at else "",
                "location": m.location or "",
                "organizer": m.organizer.full_name if m.organizer else "",
            }
            for m in _meetings_in(db, s, e)
        ]
        title = "Meetings"
    elif metric == "invoices":
        columns = [
            {"key": "number", "label": "Invoice", "type": "text"},
            {"key": "company", "label": "Company", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge"},
            {"key": "issue_date", "label": "Issued", "type": "date"},
            {"key": "due_date", "label": "Due", "type": "date"},
            {"key": "total", "label": "Total", "type": "money"},
            {"key": "amount_paid", "label": "Paid", "type": "money"},
            {"key": "created_by", "label": "Created by", "type": "text"},
        ]
        rows = [
            {
                "number": i.number,
                "company": i.company.name if i.company else "",
                "status": i.status,
                "issue_date": i.issue_date.isoformat() if i.issue_date else "",
                "due_date": i.due_date.isoformat() if i.due_date else "",
                "total": float(i.total or 0),
                "amount_paid": float(i.amount_paid or 0),
                "currency": i.currency,
                "created_by": i.created_by.full_name if i.created_by else "",
            }
            for i in _invoices_in(db, s, e)
        ]
        title = "Invoices"
    elif metric == "quotations":
        columns = [
            {"key": "number", "label": "Quotation", "type": "text"},
            {"key": "company", "label": "Company", "type": "text"},
            {"key": "status", "label": "Status", "type": "badge"},
            {"key": "issue_date", "label": "Issued", "type": "date"},
            {"key": "valid_until", "label": "Valid until", "type": "date"},
            {"key": "total", "label": "Total", "type": "money"},
            {"key": "created_by", "label": "Created by", "type": "text"},
        ]
        rows = [
            {
                "number": q.number,
                "company": q.company.name if q.company else "",
                "status": q.status,
                "issue_date": q.issue_date.isoformat() if q.issue_date else "",
                "valid_until": q.valid_until.isoformat() if q.valid_until else "",
                "total": float(q.total or 0),
                "currency": q.currency,
                "created_by": q.created_by.full_name if q.created_by else "",
            }
            for q in _quotations_in(db, s, e)
        ]
        title = "Quotations"
    elif metric == "recent_activities":
        columns = [
            {"key": "title", "label": "Activity", "type": "text"},
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "entity_type", "label": "Related to", "type": "text"},
            {"key": "user", "label": "By", "type": "text"},
            {"key": "created_at", "label": "When", "type": "datetime"},
        ]
        rows = [
            {
                "title": a.title,
                "type": a.type,
                "entity_type": a.entity_type,
                "user": a.user.full_name if a.user else "",
                "created_at": a.created_at.isoformat(sep=" ", timespec="minutes"),
            }
            for a in _activities_in(db, s, e, DRILLDOWN_ROW_CAP)
        ]
        title = "Activities"
    else:
        raise AppError(f"Unknown drilldown metric '{metric}'", 400)

    truncated = len(rows) > DRILLDOWN_ROW_CAP
    return {
        "metric": metric,
        "title": title,
        "start": s.date().isoformat(),
        "end": e.date().isoformat(),
        "columns": columns,
        "rows": rows[:DRILLDOWN_ROW_CAP],
        "total": len(rows),
        "truncated": truncated,
    }


# --- standalone reports (Reports page) ------------------------------------

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


@router.get("/funnel")
def sales_funnel(db: Session = Depends(get_db)):
    stages = db.scalars(select(DealStage).order_by(DealStage.order)).all()
    counts = dict(db.execute(select(Deal.stage_id, func.count()).group_by(Deal.stage_id)).all())
    values = dict(db.execute(select(Deal.stage_id, func.coalesce(func.sum(Deal.value), 0)).group_by(Deal.stage_id)).all())
    return [
        {"stage": st.name, "count": counts.get(st.id, 0), "value": float(values.get(st.id, 0))}
        for st in stages
    ]


@router.get("/lead-sources")
def lead_sources_report(db: Session = Depends(get_db)):
    rows = db.execute(select(Lead.source_id, func.count()).group_by(Lead.source_id)).all()
    sources = {src.id: src.name for src in db.scalars(select(LeadSource))}
    return [{"source": sources.get(sid, "Unknown"), "count": count} for sid, count in rows]


@router.get("/win-rate")
def win_rate_report(db: Session = Depends(get_db)):
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
