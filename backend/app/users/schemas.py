from datetime import datetime

from pydantic import EmailStr, Field

from app.core.schemas import ORMModel


class RoleOut(ORMModel):
    id: str
    name: str
    description: str | None = None
    permissions: list[str]
    is_system: bool


class RoleCreate(ORMModel):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = None
    permissions: list[str] = []


class RoleUpdate(ORMModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


class UserOut(ORMModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    avatar_url: str | None = None
    is_active: bool
    # Lets the frontend route a platform admin to the console instead of the CRM.
    is_platform_admin: bool = False
    theme: str
    last_login_at: datetime | None = None
    created_at: datetime
    # Null for a platform Super Admin, who has no tenant role.
    role: RoleOut | None = None


class UserCreate(ORMModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1)
    last_name: str = ""
    phone: str | None = None
    role_id: str
    send_welcome_email: bool = True


class UserUpdate(ORMModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role_id: str | None = None
    is_active: bool | None = None
