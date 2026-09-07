from datetime import date, datetime

from pydantic import Field, computed_field

from app.core.schemas import CompanyBrief, ORMModel, UserBrief


class NomineeIn(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    relation: str | None = None
    date_of_birth: date | None = None
    age: int | None = Field(default=None, ge=0, le=120)
    share_percent: int = Field(default=100, ge=1, le=100)
    appointee_name: str | None = None
    appointee_relation: str | None = None


class NomineeOut(NomineeIn):
    id: str
    position: int = 0

    @computed_field
    @property
    def is_minor(self) -> bool:
        return self.age is not None and self.age < 18


class CustomerNoteIn(ORMModel):
    body: str = Field(min_length=1)
    is_pinned: bool = False


class CustomerNoteOut(ORMModel):
    id: str
    body: str
    is_pinned: bool
    created_at: datetime
    author: UserBrief | None = None


class CustomerFieldsIn(ORMModel):
    """Insurance customer fields. All optional — a general CRM tenant sends none."""

    date_of_birth: date | None = None
    gender: str | None = None
    marital_status: str | None = None
    occupation: str | None = None
    annual_income: int | None = None

    mobile: str | None = None
    alt_mobile: str | None = None
    alt_email: str | None = None

    address_line: str | None = None
    pincode: str | None = None
    city: str | None = None
    state: str | None = None

    stage: str | None = None
    referred_by_type: str | None = None
    referred_by_contact_id: str | None = None
    referred_by_name: str | None = None
    referred_on: date | None = None
    products_of_interest: list[str] = []


class ContactBase(ORMModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = ""
    position: str | None = None
    company_id: str | None = None
    emails: list[str] = []
    phones: list[str] = []
    social_links: dict[str, str] = {}
    notes: str | None = None
    tags: list[str] = []
    owner_id: str | None = None
    #: Values for this tenant's custom fields. Validated on flush against the
    #: tenant's own field definitions; undeclared keys are dropped.
    custom: dict = {}


class ContactCreate(ContactBase, CustomerFieldsIn):
    #: Write-only. Validated, encrypted and indexed by `contacts.service`; never
    #: echoed back — responses carry only the masked form.
    pan: str | None = None
    aadhaar: str | None = None
    nominees: list[NomineeIn] | None = None


class ContactUpdate(CustomerFieldsIn):
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None
    company_id: str | None = None
    emails: list[str] | None = None
    phones: list[str] | None = None
    social_links: dict[str, str] | None = None
    notes: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None
    custom: dict | None = None
    products_of_interest: list[str] | None = None

    pan: str | None = None
    aadhaar: str | None = None
    nominees: list[NomineeIn] | None = None


class ContactOut(ContactBase):
    id: str
    created_at: datetime
    updated_at: datetime
    company: CompanyBrief | None = None
    owner: UserBrief | None = None

    # Insurance fields, null for a general CRM tenant.
    date_of_birth: date | None = None
    gender: str | None = None
    marital_status: str | None = None
    occupation: str | None = None
    annual_income: int | None = None
    mobile: str | None = None
    alt_mobile: str | None = None
    alt_email: str | None = None
    address_line: str | None = None
    pincode: str | None = None
    city: str | None = None
    state: str | None = None
    stage: str | None = None
    referred_by_type: str | None = None
    referred_by_contact_id: str | None = None
    referred_by_name: str | None = None
    referred_on: date | None = None
    products_of_interest: list[str] = []
    nominees: list[NomineeOut] = []

    # Identity is never returned in full. `pan_masked` and `aadhaar_masked` are
    # populated by the router from `contacts.service.masked_identity`; the plaintext
    # comes only from the audited reveal endpoint.
    pan_masked: str | None = None
    aadhaar_masked: str | None = None
    has_pan: bool = False
    has_aadhaar: bool = False
    aadhaar_full_stored: bool = False

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @computed_field
    @property
    def primary_phone(self) -> str | None:
        """The number to call or message — shown wherever the customer appears."""
        return self.mobile or (self.phones[0] if self.phones else None)

    @computed_field
    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class RevealIn(ORMModel):
    field: str = Field(pattern="^(pan|aadhaar)$")


class RevealOut(ORMModel):
    field: str
    value: str
    #: Restated in the response so the UI can tell the user their view was recorded.
    audited: bool = True


class BirthdayOut(ORMModel):
    id: str
    full_name: str
    date_of_birth: date
    turning: int
    days_away: int
    primary_phone: str | None = None
    email: str | None = None
    owner: UserBrief | None = None


class IdentityLookupOut(ORMModel):
    found: bool
    contact_id: str | None = None
    full_name: str | None = None
