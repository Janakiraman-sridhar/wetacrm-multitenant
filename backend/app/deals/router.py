from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
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
    DealCreate, DealOut, DealUpdate, MoveStageIn, PipelineColumn, StageCreate, StageOut, StageUpdate,
)
from app.notifications.service import notify
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/deals", tags=["deals"])


# --- Stages / pipeline ---

@router.get("/stages", response_model=list[StageOut], dependencies=[Depends(require_perm("deals:read"))])
def list_stages(db: Session = Depends(get_db)):
    return db.scalars(select(DealStage).order_by(DealStage.order)).all()


@router.post("/stages", response_model=StageOut)
def create_stage(payload: StageCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stage = DealStage(**payload.model_dump())
    db.add(stage)
    audit(db, user.id, "create", "deal_stage", changes={"name": payload.name})
    db.commit()
    return stage


@router.patch("/stages/{stage_id}", response_model=StageOut)
def update_stage(stage_id: str, payload: StageUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stage = get_or_404(db, DealStage, stage_id, "Stage")
    changes = apply_updates(stage, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, user.id, "update", "deal_stage", stage.id, changes)
    db.commit()
    return stage


@router.delete("/stages/{stage_id}", response_model=Message)
def delete_stage(stage_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("settings:write"))):
    stage = get_or_404(db, DealStage, stage_id, "Stage")
    if stage.is_won or stage.is_lost:
        raise AppError("Won/Lost stages cannot be deleted", 400)
    if db.scalar(select(Deal).where(Deal.stage_id == stage.id).limit(1)):
        raise AppError("Stage has deals and cannot be deleted", 400)
    db.delete(stage)
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
