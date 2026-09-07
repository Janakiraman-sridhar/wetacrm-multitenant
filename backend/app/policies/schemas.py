from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, computed_field

from app.core.schemas import ORMModel, UserBrief


class MasterOut(ORMModel):
    id: str
    type: str
    name: str
    code: str | None = None
    is_active: bool = True
    order: int = 0


class MasterIn(ORMModel):
    type: str
    name: str = Field(min_length=1, max_length=150)
    code: str | None = None
    is_active: bool = True
    order: int = 0


class MasterUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    code: str | None = None
    is_active: bool | None = None
    order: int | None = None


class CustomerBrief(ORMModel):
    id: str
    first_name: str
    last_name: str
    mobile: str | None = None

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class PolicyBase(ORMModel):
    policy_number: str = Field(min_length=1, max_length=80)
    product_line: str
    plan_name: str | None = None

    insurer_id: str | None = None
    bank_id: str | None = None
    branch: str | None = None
    sourcing_channel: str | None = None

    customer_id: str
    proposer_id: str | None = None
    owner_id: str | None = None

    issue_date: date | None = None
    start_date: date | None = None
    expiry_date: date | None = None

    # None, not 0 — the service derives whichever of net/GST/gross was left out,
    # and a default of zero would make "not supplied" indistinguishable from "free".
    premium_net: Decimal | None = None
    premium_gst: Decimal | None = None
    premium_gross: Decimal | None = None
    sum_insured: Decimal | None = None
    currency: str = "INR"

    payment_mode: str | None = None
    payment_frequency: str | None = "annual"

    commission_percent: Decimal | None = None
    commission_amount: Decimal | None = None

    registration_no: str | None = None
    remarks: str | None = None
    tags: list[str] = []
    #: Line-specific fields — vehicle, members covered, riders. Validated against
    #: `product_line`; unknown keys are dropped.
    details: dict = {}
    custom: dict = {}


class PolicyCreate(PolicyBase):
    status: str = "active"


class PolicyUpdate(ORMModel):
    policy_number: str | None = None
    product_line: str | None = None
    plan_name: str | None = None
    insurer_id: str | None = None
    bank_id: str | None = None
    branch: str | None = None
    sourcing_channel: str | None = None
    customer_id: str | None = None
    proposer_id: str | None = None
    owner_id: str | None = None
    issue_date: date | None = None
    start_date: date | None = None
    expiry_date: date | None = None
    premium_net: Decimal | None = None
    premium_gst: Decimal | None = None
    premium_gross: Decimal | None = None
    sum_insured: Decimal | None = None
    payment_mode: str | None = None
    payment_frequency: str | None = None
    status: str | None = None
    commission_percent: Decimal | None = None
    commission_amount: Decimal | None = None
    registration_no: str | None = None
    remarks: str | None = None
    tags: list[str] | None = None
    details: dict | None = None
    custom: dict | None = None


class PolicyOut(PolicyBase):
    id: str
    status: str
    # Always populated on a stored policy, whatever was supplied on the way in.
    premium_net: Decimal = Decimal(0)
    premium_gst: Decimal = Decimal(0)
    premium_gross: Decimal = Decimal(0)
    created_at: datetime
    updated_at: datetime
    renewal_of_id: str | None = None
    renewed_to_id: str | None = None

    insurer: MasterOut | None = None
    bank: MasterOut | None = None
    customer: CustomerBrief | None = None
    owner: UserBrief | None = None

    @computed_field
    @property
    def days_to_expiry(self) -> int | None:
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

    @computed_field
    @property
    def is_in_force(self) -> bool:
        return self.status in ("active", "expiring")


class RenewIn(ORMModel):
    """What changes on renewal. Everything else is carried over from the old policy."""

    policy_number: str = Field(min_length=1, max_length=80)
    start_date: date
    expiry_date: date
    premium_net: Decimal | None = None
    premium_gst: Decimal | None = None
    premium_gross: Decimal | None = None
    sum_insured: Decimal | None = None
    insurer_id: str | None = None
    plan_name: str | None = None
    remarks: str | None = None


class RenewalDueOut(ORMModel):
    id: str
    policy_number: str
    product_line: str
    expiry_date: date
    days_to_expiry: int
    premium_gross: Decimal
    status: str
    customer: CustomerBrief | None = None
    insurer: MasterOut | None = None
    owner: UserBrief | None = None


class PolicyStatsOut(ORMModel):
    """The numbers on the insurance dashboard's KPI strip."""

    customers: int
    active_policies: int
    book_premium: Decimal
    renewals_60d: int
    renewals_30d: int
    renewals_7d: int
    lapsed: int
    new_business_mtd_count: int
    new_business_mtd_premium: Decimal
    birthdays_this_week: int
    commission_mtd: Decimal
