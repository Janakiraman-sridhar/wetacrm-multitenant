"""Loan cases: the cross-sell an insurance agent tracks alongside policies."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import Field, computed_field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.activities.service import audit, log_activity
from app.contacts.models import Contact
from app.core.crud import apply_updates, get_or_404
from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.core.pagination import PageParams, apply_sort, page_params, paginate
from app.core.schemas import Message, ORMModel, Page, UserBrief
from app.database.session import get_db
from app.filtering import apply_filters_for
from app.loans.models import LOAN_STATUSES, OPEN_LOAN_STATUSES, Loan
from app.policies.schemas import CustomerBrief, MasterOut
from app.users.models import User

router = APIRouter(prefix="/loans", tags=["loans"])


class LoanBase(ORMModel):
    customer_id: str
    loan_type: str = Field(min_length=1, max_length=60)
    lender_id: str | None = None
    owner_id: str | None = None
    status: str = "enquiry"
    amount_requested: Decimal | None = None
    amount_sanctioned: Decimal | None = None
    tenure_months: int | None = None
    interest_rate: Decimal | None = None
    payout_percent: Decimal | None = None
    actual_payout: Decimal | None = None
    applied_on: date | None = None
    sanctioned_on: date | None = None
    disbursed_on: date | None = None
    rejected_reason: str | None = None
    remarks: str | None = None
    tags: list[str] = []
    custom: dict = {}


class LoanCreate(LoanBase):
    pass


class LoanUpdate(ORMModel):
    customer_id: str | None = None
    loan_type: str | None = None
    lender_id: str | None = None
    owner_id: str | None = None
    status: str | None = None
    amount_requested: Decimal | None = None
    amount_sanctioned: Decimal | None = None
    tenure_months: int | None = None
    interest_rate: Decimal | None = None
    payout_percent: Decimal | None = None
    actual_payout: Decimal | None = None
    applied_on: date | None = None
    sanctioned_on: date | None = None
    disbursed_on: date | None = None
    rejected_reason: str | None = None
    remarks: str | None = None
    tags: list[str] | None = None
    custom: dict | None = None


class LoanOut(LoanBase):
    id: str
    expected_payout: Decimal | None = None
    customer: CustomerBrief | None = None
    lender: MasterOut | None = None
    owner: UserBrief | None = None

    @computed_field
    @property
    def is_open(self) -> bool:
        return self.status in OPEN_LOAN_STATUSES


class LoanStatsOut(ORMModel):
    open_cases: int
    sanctioned_value: Decimal
    disbursed_value: Decimal
    expected_payout: Decimal
    received_payout: Decimal
    #: Expected minus received on disbursed cases — the number an agent chases.
    outstanding_payout: Decimal
    by_status: dict[str, int]


def _money(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def derive_expected_payout(sanctioned, percent) -> Decimal | None:
    """Payout follows the sanctioned amount, not the requested one.

    Derived rather than typed so it cannot sit stale beside the numbers it comes
    from — the commonest way a payout report goes quietly wrong.
    """
    if sanctioned is None or percent is None:
        return None
    return _money(Decimal(str(sanctioned)) * Decimal(str(percent)) / Decimal(100))


@router.get("", response_model=Page[LoanOut], dependencies=[Depends(require_perm("loans:read"))])
def list_loans(
    filters: str | None = Query(None),
    status: str | None = None,
    loan_type: str | None = None,
    lender_id: str | None = None,
    customer_id: str | None = None,
    owner_id: str | None = None,
    open_only: bool = False,
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
):
    stmt = select(Loan)
    if status:
        stmt = stmt.where(Loan.status == status)
    if open_only:
        stmt = stmt.where(Loan.status.in_(OPEN_LOAN_STATUSES))
    if loan_type:
        stmt = stmt.where(Loan.loan_type == loan_type)
    if lender_id:
        stmt = stmt.where(Loan.lender_id == lender_id)
    if customer_id:
        stmt = stmt.where(Loan.customer_id == customer_id)
    if owner_id:
        stmt = stmt.where(Loan.owner_id == owner_id)
    if params.search:
        q = f"%{params.search}%"
        stmt = stmt.where(or_(Loan.loan_type.ilike(q), Loan.remarks.ilike(q)))
    stmt = apply_sort(stmt, Loan, params.sort)
    stmt = apply_filters_for(db, stmt, "loans", filters)
    return paginate(db, stmt, params)


@router.get("/board", dependencies=[Depends(require_perm("loans:read"))])
def board(db: Session = Depends(get_db)):
    """Open cases grouped by stage, for the pipeline view."""
    loans = db.scalars(
        select(Loan).where(Loan.status.in_(OPEN_LOAN_STATUSES)).order_by(Loan.created_at.desc())
    ).all()
    columns = {status: [] for status in OPEN_LOAN_STATUSES}
    for loan in loans:
        columns[loan.status].append(LoanOut.model_validate(loan).model_dump())
    return [
        {
            "status": status,
            "label": status.replace("_", " ").title(),
            "loans": columns[status],
            "value": sum(Decimal(str(l["amount_requested"] or 0)) for l in columns[status]),
        }
        for status in OPEN_LOAN_STATUSES
    ]


@router.get("/stats", response_model=LoanStatsOut, dependencies=[Depends(require_perm("loans:read"))])
def stats(db: Session = Depends(get_db)):
    loans = db.scalars(select(Loan)).all()
    disbursed = [l for l in loans if l.status == "disbursed"]
    expected = sum((l.expected_payout or Decimal(0)) for l in disbursed) or Decimal(0)
    received = sum((l.actual_payout or Decimal(0)) for l in disbursed) or Decimal(0)

    by_status: dict[str, int] = {status: 0 for status in LOAN_STATUSES}
    for loan in loans:
        by_status[loan.status] = by_status.get(loan.status, 0) + 1

    return {
        "open_cases": sum(1 for l in loans if l.is_open),
        "sanctioned_value": sum((l.amount_sanctioned or Decimal(0)) for l in loans) or Decimal(0),
        "disbursed_value": sum((l.amount_sanctioned or Decimal(0)) for l in disbursed) or Decimal(0),
        "expected_payout": expected,
        "received_payout": received,
        "outstanding_payout": expected - received,
        "by_status": by_status,
    }


@router.get("/{loan_id}", response_model=LoanOut, dependencies=[Depends(require_perm("loans:read"))])
def get_loan(loan_id: str, db: Session = Depends(get_db)):
    return get_or_404(db, Loan, loan_id, "Loan")


@router.post("", response_model=LoanOut)
def create_loan(
    payload: LoanCreate, db: Session = Depends(get_db), user: User = Depends(require_perm("loans:write"))
):
    data = payload.model_dump()
    if data["status"] not in LOAN_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(LOAN_STATUSES)}")
    get_or_404(db, Contact, data["customer_id"], "Customer")
    data["expected_payout"] = derive_expected_payout(
        data.get("amount_sanctioned"), data.get("payout_percent")
    )
    data["owner_id"] = data.get("owner_id") or user.id

    # Stamp the dates a stage implies, exactly as moving into that stage would. A
    # case entered late — already sanctioned, already disbursed — must not land in
    # the payout report with a blank date the update path would have filled in.
    if data["status"] in ("sanctioned", "disbursed") and not data.get("sanctioned_on"):
        data["sanctioned_on"] = date.today()
    if data["status"] == "disbursed" and not data.get("disbursed_on"):
        data["disbursed_on"] = date.today()

    loan = Loan(**data)
    db.add(loan)
    db.flush()
    log_activity(db, "contact", loan.customer_id, "system",
                 f"{loan.loan_type} enquiry created", user_id=user.id)
    audit(db, user.id, "create", "loan", loan.id, {"type": loan.loan_type})
    db.commit()
    return loan


@router.patch("/{loan_id}", response_model=LoanOut)
def update_loan(
    loan_id: str,
    payload: LoanUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("loans:write")),
):
    loan = get_or_404(db, Loan, loan_id, "Loan")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in LOAN_STATUSES:
        raise AppError(f"Status must be one of: {', '.join(LOAN_STATUSES)}")

    previous_status = loan.status
    changes = apply_updates(loan, data)

    # Recompute whenever either input moved, so the payout never lags the numbers
    # it is calculated from.
    if {"amount_sanctioned", "payout_percent"} & changes.keys():
        loan.expected_payout = derive_expected_payout(loan.amount_sanctioned, loan.payout_percent)

    # Stamp the dates a stage implies, unless the user set them explicitly.
    if "status" in changes and loan.status != previous_status:
        if loan.status == "sanctioned" and not loan.sanctioned_on and "sanctioned_on" not in data:
            loan.sanctioned_on = date.today()
        if loan.status == "disbursed" and not loan.disbursed_on and "disbursed_on" not in data:
            loan.disbursed_on = date.today()
        log_activity(db, "contact", loan.customer_id, "status_change",
                     f"{loan.loan_type} moved to {loan.status}", user_id=user.id)

    if changes:
        audit(db, user.id, "update", "loan", loan.id, changes)
    db.commit()
    return loan


@router.delete("/{loan_id}", response_model=Message)
def delete_loan(
    loan_id: str, db: Session = Depends(get_db), user: User = Depends(require_perm("loans:delete"))
):
    loan = get_or_404(db, Loan, loan_id, "Loan")
    label = loan.loan_type
    db.delete(loan)
    audit(db, user.id, "delete", "loan", loan_id, {"type": label})
    db.commit()
    return {"detail": "Loan deleted"}
