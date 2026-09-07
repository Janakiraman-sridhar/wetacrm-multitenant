from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel, TenantScoped


class Role(TenantScoped, BaseModel):
    __tablename__ = "roles"

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(TenantScoped, BaseModel):
    """A login.

    Email stays globally unique across the platform: one login belongs to exactly
    one tenant, which keeps the sign-in screen free of a tenant picker.

    A platform Super Admin is the one user kind with no tenant — `tenant_id` and
    `role_id` are both null and `is_platform_admin` is true. They authenticate into
    the platform console, and reach tenant data only by impersonating a tenant user
    (which is audited).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str | None] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    theme: Mapped[str] = mapped_column(String(10), default="light")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    role: Mapped[Role | None] = relationship(back_populates="users", lazy="joined")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
