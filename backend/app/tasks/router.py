from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.notifications.service import notify
from app.services import search_sync
from app.tasks.models import TASK_PRIORITIES, TASK_STATUSES, Task
from app.tasks.schemas import TaskCreate, TaskOut, TaskUpdate
from app.users.models import User

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _validate(data: dict) -> None:
    if data.get("priority") and data["priority"] not in TASK_PRIORITIES:
        raise AppError(f"Invalid priority. Expected one of {TASK_PRIORITIES}")
    if data.get("status") and data["status"] not in TASK_STATUSES:
        raise AppError(f"Invalid status. Expected one of {TASK_STATUSES}")


@router.get("", response_model=Page[TaskOut], dependencies=[Depends(require_perm("tasks:read"))])
def list_tasks(
    status: str | None = None,
    priority: str | None = None,
    assigned_to_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Task)
    if status:
        stmt = stmt.where(Task.status == status)
    if priority:
        stmt = stmt.where(Task.priority == priority)
    if assigned_to_id:
        stmt = stmt.where(Task.assigned_to_id == assigned_to_id)
    if entity_type:
        stmt = stmt.where(Task.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(Task.entity_id == entity_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Task.title.ilike(q), Task.description.ilike(q)))
    stmt = apply_sort(stmt, Task, params.sort)
    return paginate(db, stmt, params)


@router.get("/{task_id}", response_model=TaskOut, dependencies=[Depends(require_perm("tasks:read"))])
def get_task(task_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Task, task_id, "Task")


@router.post("", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("tasks:write"))):
    data = payload.model_dump()
    _validate(data)
    task = Task(**data, created_by_id=user.id)
    db.add(task)
    db.flush()
    audit(db, user.id, "create", "task", task.id, {"title": task.title})
    if task.assigned_to_id and task.assigned_to_id != user.id:
        notify(db, task.assigned_to_id, "task_assigned", f"Task assigned: {task.title}",
               f"Assigned by {user.full_name}", "/tasks")
    db.commit()
    search_sync.sync_task(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("tasks:write"))):
    task = get_or_404(db, Task, task_id, "Task")
    data = payload.model_dump(exclude_unset=True)
    _validate(data)
    previous_assignee = task.assigned_to_id
    changes = apply_updates(task, data)
    if changes:
        audit(db, user.id, "update", "task", task.id, changes)
    if "assigned_to_id" in changes and task.assigned_to_id and task.assigned_to_id != previous_assignee and task.assigned_to_id != user.id:
        notify(db, task.assigned_to_id, "task_assigned", f"Task assigned: {task.title}",
               f"Assigned by {user.full_name}", "/tasks")
    db.commit()
    search_sync.sync_task(task)
    return task


@router.delete("/{task_id}", response_model=Message)
def delete_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("tasks:delete"))):
    task = get_or_404(db, Task, task_id, "Task")
    title = task.title
    db.delete(task)
    audit(db, user.id, "delete", "task", task_id, {"title": title})
    db.commit()
    search_sync.remove("tasks", task_id)
    return {"detail": "Task deleted"}
