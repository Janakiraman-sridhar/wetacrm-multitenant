"""Insurance reports, and CSV export for the ones an agency works from.

The renewal register and the lapsed list are worked offline — an agent takes them
into a day of calls — so those export. The rest are read on screen.
"""

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.deps import require_perm
from app.core.exceptions import AppError
from app.database.session import get_db
from app.reports import insurance

router = APIRouter(prefix="/reports/insurance", tags=["reports"])

READ = Depends(require_perm("reports:read"))


@router.get("/renewals", dependencies=[READ])
def renewals(within_days: int = Query(60, ge=1, le=365), include_lapsed: bool = False,
             db: Session = Depends(get_db)):
    return insurance.renewal_register(db, within_days, include_lapsed)


@router.get("/production", dependencies=[READ])
def production(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db)):
    return insurance.production(db, months)


@router.get("/commission", dependencies=[READ])
def commission(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db)):
    return insurance.commission(db, months)


@router.get("/retention", dependencies=[READ])
def retention(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db)):
    return insurance.retention(db, months)


@router.get("/cross-sell", dependencies=[READ])
def cross_sell(db: Session = Depends(get_db)):
    return insurance.cross_sell(db)


@router.get("/leaderboard", dependencies=[READ])
def leaderboard(months: int = Query(3, ge=1, le=24), db: Session = Depends(get_db)):
    return insurance.agent_leaderboard(db, months)


@router.get("/loan-payouts", dependencies=[READ])
def loan_payouts(db: Session = Depends(get_db)):
    return insurance.loan_payouts(db)


@router.get("/birthdays", dependencies=[READ])
def birthdays(within_days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    return insurance.birthday_list(db, within_days)


@router.get("/customer-growth", dependencies=[READ])
def customer_growth(months: int = Query(12, ge=1, le=36), db: Session = Depends(get_db)):
    return insurance.customer_growth(db, months)


def _csv(rows: list[dict], filename: str) -> Response:
    if not rows:
        return Response(content="", media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    # BOM so Excel opens it as UTF-8 rather than mangling names.
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report}/export", dependencies=[READ])
def export(
    report: str,
    within_days: int = Query(60, ge=1, le=365),
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
):
    """Export the reports an agency works offline."""
    if report == "renewals":
        return _csv(insurance.renewal_register(db, within_days), "renewal_register.csv")
    if report == "lapsed":
        return _csv(insurance.retention(db, months)["lapsed_policies"], "lapsed_policies.csv")
    if report == "birthdays":
        return _csv(insurance.birthday_list(db, within_days), "birthdays.csv")
    if report == "cross-sell":
        rows = [
            {**row, "holds": ", ".join(row["holds"]), "missing": ", ".join(row["missing"])}
            for row in insurance.cross_sell(db)["single_line_customers"]
        ]
        return _csv(rows, "cross_sell.csv")
    if report == "loan-payouts":
        return _csv(insurance.loan_payouts(db)["awaiting_payout"], "loan_payouts.csv")
    raise AppError(
        "That report cannot be exported. Available: renewals, lapsed, birthdays, "
        "cross-sell, loan-payouts",
        404,
    )
