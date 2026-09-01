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
from app.projects.models import PROJECT_STATUSES, Project, ProjectTask
from app.projects.schemas import (
    ProjectCreate, ProjectOut, ProjectTaskIn, ProjectTaskOut, ProjectTaskUpdate, ProjectUpdate,
)
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=Page[ProjectOut], dependencies=[Depends(require_perm("projects:read"))])
def list_projects(status: str | None = None, params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Project.name.ilike(q), Project.description.ilike(q)))
    stmt = apply_sort(stmt, Project, params.sort)
    return paginate(db, stmt, params)


@router.get("/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_perm("projects:read"))])
def get_project(project_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Project, project_id, "Project")


@router.post("", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("projects:write"))):
    if payload.status not in PROJECT_STATUSES:
        raise AppError(f"Invalid status. Expected one of {PROJECT_STATUSES}")
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    audit(db, user.id, "create", "project", project.id, {"name": project.name})
    for uid in set(project.team_ids or []) - {user.id}:
        notify(db, uid, "project_assigned", f"Added to project: {project.name}",
               f"Added by {user.full_name}", "/projects")
    db.commit()
    search_sync.sync_project(project)
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("projects:write"))):
    project = get_or_404(db, Project, project_id, "Project")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] not in PROJECT_STATUSES:
        raise AppError(f"Invalid status. Expected one of {PROJECT_STATUSES}")
    changes = apply_updates(project, data)
    if changes:
        audit(db, user.id, "update", "project", project.id, changes)
    db.commit()
    search_sync.sync_project(project)
    return project


@router.delete("/{project_id}", response_model=Message)
def delete_project(project_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("projects:delete"))):
    project = get_or_404(db, Project, project_id, "Project")
    name = project.name
    db.delete(project)
    audit(db, user.id, "delete", "project", project_id, {"name": name})
    db.commit()
    search_sync.remove("projects", project_id)
    return {"detail": "Project deleted"}


# --- Project tasks / milestones ---

@router.post("/{project_id}/tasks", response_model=ProjectTaskOut)
def add_project_task(project_id: str, payload: ProjectTaskIn, db: Session = Depends(get_db), user: User = Depends(require_perm("projects:write"))):
    project = get_or_404(db, Project, project_id, "Project")
    position = len(project.tasks)
    task = ProjectTask(**payload.model_dump(), project_id=project.id, position=position)
    db.add(task)
    if task.assigned_to_id and task.assigned_to_id != user.id:
        notify(db, task.assigned_to_id, "task_assigned", f"Project task: {task.title}",
               f"In project {project.name}", "/projects")
    db.commit()
    return task


@router.patch("/{project_id}/tasks/{task_id}", response_model=ProjectTaskOut)
def update_project_task(project_id: str, task_id: str, payload: ProjectTaskUpdate, db: Session = Depends(get_db), _: User = Depends(require_perm("projects:write"))):
    task = get_or_404(db, ProjectTask, task_id, "Project task")
    if task.project_id != project_id:
        raise AppError("Task does not belong to this project", 400)
    apply_updates(task, payload.model_dump(exclude_unset=True))
    db.commit()
    return task


@router.delete("/{project_id}/tasks/{task_id}", response_model=Message)
def delete_project_task(project_id: str, task_id: str, db: Session = Depends(get_db), _: User = Depends(require_perm("projects:write"))):
    task = get_or_404(db, ProjectTask, task_id, "Project task")
    if task.project_id != project_id:
        raise AppError("Task does not belong to this project", 400)
    db.delete(task)
    db.commit()
    return {"detail": "Project task deleted"}
