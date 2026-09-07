from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit
from app.core.crud import apply_updates, get_or_404
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.permissions import ALL_PERMISSIONS, MODULES
from app.core.schemas import Message, Page
from app.core.security import hash_password
from app.core.tenancy import platform_scope
from app.database.session import get_db
from app.services.email import send_welcome
from app.users.models import Role, User
from app.users.schemas import RoleCreate, RoleOut, RoleUpdate, UserCreate, UserOut, UserUpdate

router = APIRouter(tags=["users"])


# --- Users ---

@router.get("/users", response_model=Page[UserOut], dependencies=[Depends(require_perm("users:read"))])
def list_users(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(User)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(User.email.ilike(q), User.first_name.ilike(q), User.last_name.ilike(q)))
    stmt = apply_sort(stmt, User, params.sort)
    return paginate(db, stmt, params)


@router.get("/users/all", response_model=list[UserOut])
def list_all_active_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Lightweight list for assignee pickers — any authenticated user."""
    return db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.first_name)).all()


@router.post("/users", response_model=UserOut, dependencies=[Depends(require_perm("users:write"))])
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.scalar(select(User).where(User.email == payload.email)):
        raise AppError("A user with this email already exists", 409)
    get_or_404(db, Role, payload.role_id, "Role")
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        role_id=payload.role_id,
    )
    db.add(user)
    db.flush()
    audit(db, actor.id, "create", "user", user.id, {"email": payload.email})
    db.commit()
    if payload.send_welcome_email:
        send_welcome(db, user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_perm("users:write"))])
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    user = get_or_404(db, User, user_id, "User")
    data = payload.model_dump(exclude_unset=True)
    if "role_id" in data:
        get_or_404(db, Role, data["role_id"], "Role")
    if data.get("email") and data["email"] != user.email:
        # One login belongs to one workspace, so the address has to be free
        # platform-wide — not just inside this tenant.
        with platform_scope():
            taken = db.scalar(select(User).where(User.email == data["email"]))
        if taken:
            raise AppError("That email address is already in use", 409)
    changes = apply_updates(user, data)
    if changes:
        audit(db, actor.id, "update", "user", user.id, changes)
    db.commit()
    return user


@router.delete("/users/{user_id}", response_model=Message, dependencies=[Depends(require_perm("users:delete"))])
def deactivate_user(user_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if user_id == actor.id:
        raise AppError("You cannot deactivate your own account", 400)
    user = get_or_404(db, User, user_id, "User")
    user.is_active = False
    audit(db, actor.id, "deactivate", "user", user.id)
    db.commit()
    return {"detail": "User deactivated"}


# --- Roles & permissions ---

@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(require_perm("roles:read"))])
def list_roles(db: Session = Depends(get_db)):
    return db.scalars(select(Role).order_by(Role.created_at)).all()


@router.get("/permissions")
def list_permissions(_: User = Depends(get_current_user)):
    return {"modules": MODULES, "permissions": ALL_PERMISSIONS}


@router.post("/roles", response_model=RoleOut, dependencies=[Depends(require_perm("roles:write"))])
def create_role(payload: RoleCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if db.scalar(select(Role).where(Role.name == payload.name)):
        raise AppError("A role with this name already exists", 409)
    role = Role(name=payload.name, description=payload.description, permissions=payload.permissions, is_system=False)
    db.add(role)
    db.flush()
    audit(db, actor.id, "create", "role", role.id, {"name": role.name})
    db.commit()
    return role


@router.patch("/roles/{role_id}", response_model=RoleOut, dependencies=[Depends(require_perm("roles:write"))])
def update_role(role_id: str, payload: RoleUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    role = get_or_404(db, Role, role_id, "Role")
    if role.is_system and payload.permissions is not None and role.name == "Super Admin":
        raise AppError("The Super Admin role cannot be modified", 400)
    changes = apply_updates(role, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, actor.id, "update", "role", role.id, changes)
    db.commit()
    return role


@router.delete("/roles/{role_id}", response_model=Message, dependencies=[Depends(require_perm("roles:delete"))])
def delete_role(role_id: str, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    role = get_or_404(db, Role, role_id, "Role")
    if role.is_system:
        raise AppError("System roles cannot be deleted", 400)
    if db.scalar(select(User).where(User.role_id == role.id).limit(1)):
        raise AppError("Role is assigned to users and cannot be deleted", 400)
    db.delete(role)
    audit(db, actor.id, "delete", "role", role_id, {"name": role.name})
    db.commit()
    return {"detail": "Role deleted"}
