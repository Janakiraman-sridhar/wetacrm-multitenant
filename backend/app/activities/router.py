from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activities.models import ACTIVITY_TYPES, Activity, AuditLog
from app.activities.schemas import ActivityCreate, ActivityOut, AuditLogOut, CommentCreate, CommentOut
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, page_params, paginate
from app.core.schemas import Page
from app.database.session import get_db
from app.tasks.models import Comment
from app.users.models import User

router = APIRouter(tags=["activities"])


@router.get("/activities", response_model=Page[ActivityOut], dependencies=[Depends(require_perm("activities:read"))])
def list_activities(
    entity_type: str | None = None,
    entity_id: str | None = None,
    type: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Activity).order_by(Activity.created_at.desc())
    if entity_type:
        stmt = stmt.where(Activity.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Activity.entity_id == entity_id)
    if type:
        stmt = stmt.where(Activity.type == type)
    return paginate(db, stmt, params)


@router.post("/activities", response_model=ActivityOut)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("activities:write"))):
    if payload.type not in ACTIVITY_TYPES:
        raise AppError(f"Invalid activity type. Expected one of {ACTIVITY_TYPES}")
    activity = Activity(**payload.model_dump(), user_id=user.id)
    db.add(activity)
    db.commit()
    return activity


@router.get("/audit-logs", response_model=Page[AuditLogOut], dependencies=[Depends(require_perm("settings:read"))])
def list_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return paginate(db, stmt, params)


@router.get("/comments", response_model=Page[CommentOut])
def list_comments(
    entity_type: str,
    entity_id: str,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = (
        select(Comment)
        .where(Comment.entity_type == entity_type, Comment.entity_id == entity_id)
        .order_by(Comment.created_at.asc())
    )
    return paginate(db, stmt, params)


@router.post("/comments", response_model=CommentOut)
def create_comment(payload: CommentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    comment = Comment(**payload.model_dump(), user_id=user.id)
    db.add(comment)
    db.commit()
    return comment
