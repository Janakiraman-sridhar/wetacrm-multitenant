from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, Page
from app.database.base import utcnow
from app.database.session import get_db
from app.deals.models import Deal, DealStage
from app.deals.schemas import (
    DealCreate, DealOut, DealUpdate, MoveStageIn, PipelineColumn, ReorderStagesIn, StageCreate, StageOut, StageUpdate,
)
from app.notifications.service import notify
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/deals", tags=["deals"])


# --- Stages / pipeline ---

def _stage_counts(db: Session) -> dict:
    return dict(db.execute(select(Deal.stage_id, func.count()).group_by(Deal.stage_id)).all())


def _stage_out(stage: DealStage, counts: dict) -> dict:
    return {
        "id": stage.id, "name": stage.name, "order": stage.order, "probability": stage.probability,
        "is_won": stage.is_won, "is_lost": stage.is_lost, "deal_count": counts.get(stage.id, 0),
    }


def _normalize_orders(db: Session) -> None:
    """Keep open stages first (1..n) and the Won/Lost closing stages pinned at the end.

    Sorts on the in-memory `order` values (the session has autoflush disabled, so an
    SQL ORDER BY would see stale pre-update values and clobber a reorder).
    """
    stages = sorted(db.scalars(select(DealStage)).all(), key=lambda s: s.order)
    open_stages = [s for s in stages if not s.is_won and not s.is_lost]
    terminal = [s for s in stages if s.is_won] + [s for s in stages if s.is_lost]
    for i, stage in enumerate(open_stages + terminal, start=1):
        stage.order = i


@router.get("/stages", response_model=list[StageOut], dependencies=[Depends(require_perm("deals:read"))])
def list_stages(db: Session = Depends(get_db)):
    counts = _stage_counts(db)
    stages = db.scalars(select(DealStage).order_by(DealStage.order)).all()
    return [_stage_out(s, counts) for s in stages]


@router.post("/stages", response_model=StageOut)
def create_stage(payload: StageCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    name = payload.name.strip()
    if not name:
        raise AppError("Stage name is required")
    if db.scalar(select(DealStage).where(DealStage.name == name)):
        raise AppError("A stage with this name already exists", 409)
    open_max = db.scalar(
        select(func.coalesce(func.max(DealStage.order), 0)).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False))
    ) or 0
    stage = DealStage(name=name, probability=payload.probability, order=open_max + 1)
    db.add(stage)
    db.flush()
    _normalize_orders(db)
    audit(db, user.id, "create", "deal_stage", stage.id, {"name": name})
    db.commit()
    return _stage_out(stage, _stage_counts(db))


@router.post("/stages/reorder", response_model=list[StageOut])
def reorder_stages(payload: ReorderStagesIn, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stages = {s.id: s for s in db.scalars(select(DealStage)).all()}
    for stage_id in payload.stage_ids:
        stage = stages.get(stage_id)
        if not stage:
            raise AppError("Unknown stage in reorder list", 400)
        if stage.is_won or stage.is_lost:
            raise AppError("Closing stages (Won/Lost) always stay at the end", 400)
    for index, stage_id in enumerate(payload.stage_ids, start=1):
        stages[stage_id].order = index
    _normalize_orders(db)
    audit(db, user.id, "update", "deal_stage", changes={"reordered": payload.stage_ids})
    db.commit()
    counts = _stage_counts(db)
    return [_stage_out(s, counts) for s in db.scalars(select(DealStage).order_by(DealStage.order)).all()]


@router.patch("/stages/{stage_id}", response_model=StageOut)
def update_stage(stage_id: str, payload: StageUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stage = get_or_404(db, DealStage, stage_id, "Stage")
    data = payload.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise AppError("Stage name is required")
        clash = db.scalar(select(DealStage).where(DealStage.name == data["name"], DealStage.id != stage.id))
        if clash:
            raise AppError("A stage with this name already exists", 409)
    if (stage.is_won or stage.is_lost) and ("probability" in data or "order" in data):
        raise AppError("Only the name of a closing stage can be changed", 400)
    changes = apply_updates(stage, data)
    if changes:
        audit(db, user.id, "update", "deal_stage", stage.id, changes)
    db.commit()
    return _stage_out(stage, _stage_counts(db))


@router.delete("/stages/{stage_id}", response_model=Message)
def delete_stage(stage_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stage = get_or_404(db, DealStage, stage_id, "Stage")
    if stage.is_won or stage.is_lost:
        raise AppError("The Won and Lost closing stages cannot be deleted", 400)
    deal_count = db.scalar(select(func.count()).select_from(Deal).where(Deal.stage_id == stage.id)) or 0
    if deal_count:
        raise AppError(
            f"'{stage.name}' still contains {deal_count} deal{'s' if deal_count != 1 else ''}. "
            "Move or close them before deleting the stage.", 409,
        )
    open_count = db.scalar(
        select(func.count()).select_from(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False))
    ) or 0
    if open_count <= 1:
        raise AppError("The pipeline needs at least one open stage", 400)
    db.delete(stage)
    _normalize_orders(db)
    audit(db, user.id, "delete", "deal_stage", stage_id, {"name": stage.name})
    db.commit()
    return {"detail": "Stage deleted"}


@router.get("/pipeline", response_model=list[PipelineColumn], dependencies=[Depends(require_perm("deals:read"))])
def pipeline_board(owner_id: str | None = None, db: Session = Depends(get_db)):
    stages = db.scalars(select(DealStage).order_by(DealStage.order)).all()
    stmt = select(Deal).order_by(Deal.updated_at.desc())
    if owner_id:
        stmt = stmt.where(Deal.owner_id == owner_id)
    deals = db.scalars(stmt).all()
    by_stage: dict[str, list[Deal]] = {}
    for deal in deals:
        by_stage.setdefault(deal.stage_id, []).append(deal)
    return [
        {
            "stage": stage,
            "deals": by_stage.get(stage.id, []),
            "total_value": float(sum((d.value or 0) for d in by_stage.get(stage.id, []))),
        }
        for stage in stages
    ]


# --- Deals CRUD ---

@router.get("", response_model=Page[DealOut], dependencies=[Depends(require_perm("deals:read"))])
def list_deals(
    status: str | None = None,
    stage_id: str | None = None,
    owner_id: str | None = None,
    company_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Deal)
    if status:
        stmt = stmt.where(Deal.status == status)
    if stage_id:
        stmt = stmt.where(Deal.stage_id == stage_id)
    if owner_id:
        stmt = stmt.where(Deal.owner_id == owner_id)
    if company_id:
        stmt = stmt.where(Deal.company_id == company_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Deal.title.ilike(q), Deal.competitors.ilike(q)))
    stmt = apply_sort(stmt, Deal, params.sort)
    return paginate(db, stmt, params)


@router.get("/{deal_id}", response_model=DealOut, dependencies=[Depends(require_perm("deals:read"))])
def get_deal(deal_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Deal, deal_id, "Deal")


def _apply_stage(deal: Deal, stage: DealStage) -> None:
    deal.stage_id = stage.id
    deal.probability = stage.probability
    if stage.is_won:
        deal.status, deal.closed_at = "won", utcnow()
    elif stage.is_lost:
        deal.status, deal.closed_at = "lost", utcnow()
    else:
        deal.status, deal.closed_at = "open", None


@router.post("", response_model=DealOut)
def create_deal(payload: DealCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("deals:write"))):
    data = payload.model_dump()
    stage_id = data.pop("stage_id", None)
    if stage_id:
        stage = get_or_404(db, DealStage, stage_id, "Stage")
    else:
        stage = db.scalar(select(DealStage).where(DealStage.is_won.is_(False), DealStage.is_lost.is_(False)).order_by(DealStage.order))
        if not stage:
            raise AppError("No pipeline stages configured", 400)
    deal = Deal(**data, stage_id=stage.id)
    _apply_stage(deal, stage)
    db.add(deal)
    db.flush()
    log_activity(db, "deal", deal.id, "system", "Deal created", user_id=user.id)
    audit(db, user.id, "create", "deal", deal.id, {"title": deal.title})
    if deal.owner_id and deal.owner_id != user.id:
        notify(db, deal.owner_id, "deal_updated", f"Deal assigned: {deal.title}",
               f"Assigned by {user.full_name}", f"/deals?id={deal.id}")
    db.commit()
    search_sync.sync_deal(deal)
    return deal


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(deal_id: str, payload: DealUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("deals:write"))):
    deal = get_or_404(db, Deal, deal_id, "Deal")
    data = payload.model_dump(exclude_unset=True)
    new_stage_id = data.pop("stage_id", None)
    changes = apply_updates(deal, data)
    if new_stage_id and new_stage_id != deal.stage_id:
        stage = get_or_404(db, DealStage, new_stage_id, "Stage")
        changes["stage"] = [deal.stage.name if deal.stage else None, stage.name]
        _apply_stage(deal, stage)
        log_activity(db, "deal", deal.id, "status_change", f"Moved to stage {stage.name}", user_id=user.id)
    if changes:
        audit(db, user.id, "update", "deal", deal.id, changes)
        if deal.owner_id and deal.owner_id != user.id:
            notify(db, deal.owner_id, "deal_updated", f"Deal updated: {deal.title}",
                   f"Updated by {user.full_name}", f"/deals?id={deal.id}")
    db.commit()
    search_sync.sync_deal(deal)
    return deal


@router.post("/{deal_id}/move", response_model=DealOut)
def move_deal(deal_id: str, payload: MoveStageIn, db: Session = Depends(get_db), user: User = Depends(require_perm("deals:write"))):
    """Kanban drag & drop: move a deal to another stage."""
    deal = get_or_404(db, Deal, deal_id, "Deal")
    stage = get_or_404(db, DealStage, payload.stage_id, "Stage")
    if stage.id != deal.stage_id:
        old = deal.stage.name if deal.stage else None
        _apply_stage(deal, stage)
        log_activity(db, "deal", deal.id, "status_change", f"Moved to stage {stage.name}", user_id=user.id)
        audit(db, user.id, "update", "deal", deal.id, {"stage": [old, stage.name]})
        if deal.owner_id and deal.owner_id != user.id:
            notify(db, deal.owner_id, "deal_updated", f"Deal moved to {stage.name}: {deal.title}",
                   f"Moved by {user.full_name}", f"/pipeline")
        db.commit()
    return deal


@router.delete("/{deal_id}", response_model=Message)
def delete_deal(deal_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("deals:delete"))):
    deal = get_or_404(db, Deal, deal_id, "Deal")
    title = deal.title
    db.delete(deal)
    audit(db, user.id, "delete", "deal", deal_id, {"title": title})
    db.commit()
    search_sync.remove("deals", deal_id)
    return {"detail": "Deal deleted"}
