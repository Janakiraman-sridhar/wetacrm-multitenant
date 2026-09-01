from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import BaseModel

PROJECT_STATUSES = ["planned", "active", "on_hold", "completed", "cancelled"]


class Project(BaseModel):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"))
    status: Mapped[str] = mapped_column(String(20), default="planned", index=True)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    team_ids: Mapped[list] = mapped_column(JSON, default=list)

    company = relationship("Company", lazy="joined")
    owner = relationship("User", lazy="joined")
    tasks: Mapped[list["ProjectTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin", order_by="ProjectTask.position"
    )


class ProjectTask(BaseModel):
    """Project milestones and work items."""

    __tablename__ = "project_tasks"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="todo")  # todo|in_progress|done
    due_date: Mapped[date | None] = mapped_column(Date)
    assigned_to_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="tasks")
    assigned_to = relationship("User", lazy="joined")
