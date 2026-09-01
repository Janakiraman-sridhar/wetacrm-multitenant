from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.companies.models import Company
from app.companies.schemas import CompanyCreate, CompanyOut, CompanyUpdate
from app.core.crud import apply_updates, get_or_404
from app.core.deps import get_current_user, require_perm
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, Page
from app.database.session import get_db
from app.services import search_sync
from app.users.models import User

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=Page[CompanyOut], dependencies=[Depends(require_perm("companies:read"))])
def list_companies(params: PageParams = Depends(page_params), db: Session = Depends(get_db)):
    stmt = select(Company)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Company.name.ilike(q), Company.industry.ilike(q), Company.city.ilike(q), Company.email.ilike(q)))
    stmt = apply_sort(stmt, Company, params.sort)
    return paginate(db, stmt, params)


@router.get("/{company_id}", response_model=CompanyOut, dependencies=[Depends(require_perm("companies:read"))])
def get_company(company_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Company, company_id, "Company")


@router.post("", response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("companies:write"))):
    company = Company(**payload.model_dump())
    db.add(company)
    db.flush()
    log_activity(db, "company", company.id, "system", "Company created", user_id=user.id)
    audit(db, user.id, "create", "company", company.id, {"name": company.name})
    db.commit()
    search_sync.sync_company(company)
    return company


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(company_id: str, payload: CompanyUpdate, db: Session = Depends(get_db), user: User = Depends(require_perm("companies:write"))):
    company = get_or_404(db, Company, company_id, "Company")
    changes = apply_updates(company, payload.model_dump(exclude_unset=True))
    if changes:
        audit(db, user.id, "update", "company", company.id, changes)
    db.commit()
    search_sync.sync_company(company)
    return company


@router.delete("/{company_id}", response_model=Message)
def delete_company(company_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("companies:delete"))):
    company = get_or_404(db, Company, company_id, "Company")
    name = company.name
    db.delete(company)
    audit(db, user.id, "delete", "company", company_id, {"name": name})
    db.commit()
    search_sync.remove("companies", company_id)
    return {"detail": "Company deleted"}
