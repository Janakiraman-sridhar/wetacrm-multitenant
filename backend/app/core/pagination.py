from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@dataclass
class PageParams:
    page: int
    page_size: int
    search: str | None
    sort: str | None  # e.g. "name" or "-created_at"


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None),
    sort: str | None = Query(None),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, search=search, sort=sort)


def apply_sort(stmt, model, sort: str | None, default_col="created_at"):
    if sort:
        desc = sort.startswith("-")
        name = sort.lstrip("-")
        col = getattr(model, name, None)
        if col is not None:
            return stmt.order_by(col.desc() if desc else col.asc())
    col = getattr(model, default_col, None)
    return stmt.order_by(col.desc()) if col is not None else stmt


def paginate(db: Session, stmt, params: PageParams) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.offset((params.page - 1) * params.page_size).limit(params.page_size)).all()
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}
