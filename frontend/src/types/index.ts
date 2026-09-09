export interface Role {
  id: string;
  name: string;
  description?: string | null;
  permissions: string[];
  is_system: boolean;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  theme: string;
  last_login_at?: string | null;
  created_at: string;
  /** Null for a platform Super Admin, who has no tenant role. */
  role: Role | null;
  /** Platform Super Admins get the console at /platform, not the CRM. */
  is_platform_admin: boolean;
}

export interface UserBrief {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url?: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Company {
  id: string;
  name: string;
  industry?: string | null;
  website?: string | null;
  gst_number?: string | null;
  phone?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  postal_code?: string | null;
  notes?: string | null;
  tags: string[];
  owner_id?: string | null;
  owner?: UserBrief | null;
  created_at: string;
}

export interface Contact {
  id: string;
  first_name: string;
  last_name: string;
  position?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  emails: string[];
  phones: string[];
  social_links: Record<string, string>;
  notes?: string | null;
  tags: string[];
  owner?: UserBrief | null;
  created_at: string;
  // Insurance customer fields — null for a general CRM tenant.
  date_of_birth?: string | null;
  gender?: string | null;
  marital_status?: string | null;
  occupation?: string | null;
  annual_income?: number | null;
  mobile?: string | null;
  alt_mobile?: string | null;
  alt_email?: string | null;
  address_line?: string | null;
  pincode?: string | null;
  city?: string | null;
  state?: string | null;
  stage?: string | null;
  referred_by_type?: string | null;
  referred_by_contact_id?: string | null;
  referred_by_name?: string | null;
  referred_on?: string | null;
  products_of_interest?: string[];
  nominees?: Nominee[];
  /** Identity numbers only ever arrive masked; the full value needs an audited reveal. */
  pan_masked?: string | null;
  aadhaar_masked?: string | null;
  has_pan?: boolean;
  has_aadhaar?: boolean;
  aadhaar_full_stored?: boolean;
  full_name?: string;
  primary_phone?: string | null;
  age?: number | null;
}

export interface LeadSource {
  id: string;
  name: string;
}

export interface Lead {
  id: string;
  title: string;
  contact_name?: string | null;
  email?: string | null;
  phone?: string | null;
  company_name?: string | null;
  source_id?: string | null;
  source?: LeadSource | null;
  status: string;
  score: number;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  notes?: string | null;
  follow_up_at?: string | null;
  converted_deal_id?: string | null;
  tags?: string[];
  created_at: string;
}

export interface Tag {
  id: string;
  name: string;
  color: string;
}

export interface DealStage {
  id: string;
  name: string;
  order: number;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  deal_count?: number;
}

export interface Deal {
  id: string;
  title: string;
  value: number;
  currency: string;
  probability: number;
  expected_close_date?: string | null;
  stage_id: string;
  stage?: DealStage | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  contact?: { id: string; first_name: string; last_name: string } | null;
  owner_id?: string | null;
  owner?: UserBrief | null;
  competitors?: string | null;
  notes?: string | null;
  status: string;
  tags?: string[];
  created_at: string;
}

export interface PipelineColumn {
  stage: DealStage;
  deals: Deal[];
  total_value: number;
}

export interface Task {
  id: string;
  title: string;
  description?: string | null;
  priority: string;
  status: string;
  due_date?: string | null;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  created_by?: UserBrief | null;
  entity_type?: string | null;
  entity_id?: string | null;
  created_at: string;
}

export interface Meeting {
  id: string;
  title: string;
  agenda?: string | null;
  starts_at: string;
  ends_at?: string | null;
  location?: string | null;
  participant_ids: string[];
  external_participants: string[];
  notes?: string | null;
  organizer?: UserBrief | null;
  created_at: string;
}

export interface CalendarItem {
  id: string;
  kind: string;
  title: string;
  type: string;
  starts_at: string;
  ends_at?: string | null;
  location?: string | null;
}

export interface Product {
  id: string;
  name: string;
  sku?: string | null;
  description?: string | null;
  category?: string | null;
  unit_price: number;
  currency: string;
  tax_rate: number;
  stock_qty?: number | null;
  is_active: boolean;
  created_at: string;
}

export interface LineItem {
  id?: string;
  product_id?: string | null;
  name: string;
  description?: string | null;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  line_total?: number;
}

export interface Quotation {
  id: string;
  number: string;
  status: string;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  contact?: { id: string; first_name: string; last_name: string } | null;
  deal_id?: string | null;
  issue_date?: string | null;
  valid_until?: string | null;
  currency: string;
  subtotal: number;
  tax_total: number;
  discount: number;
  total: number;
  notes?: string | null;
  terms?: string | null;
  items: LineItem[];
  created_at: string;
  /** "standard" sums its items; "insurance" quotes competing insurers and takes one. */
  kind?: "standard" | "insurance";
  insurance?: InsuranceQuoteRisk | null;
  policy_id?: string | null;
}

export interface InsuranceQuoteOption {
  insurer_id?: string | null;
  insurer_name?: string | null;
  plan_name?: string | null;
  sum_insured?: number | null;
  idv?: number | null;
  premium_net?: number | null;
  premium_gst?: number | null;
  premium_gross?: number | null;
  add_ons?: string[];
  features?: string[];
  claim_settlement_ratio?: string | null;
  recommended?: boolean;
  /** Exactly one option carries this — it is what the quotation total comes from. */
  selected?: boolean;
}

export interface InsuranceQuoteRisk {
  product_line?: string;
  registration_no?: string | null;
  existing_insurer?: string | null;
  sum_insured?: number | string | null;
  options?: InsuranceQuoteOption[];
}

export interface Invoice {
  id: string;
  number: string;
  quotation_id?: string | null;
  status: string;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  issue_date?: string | null;
  due_date?: string | null;
  currency: string;
  subtotal: number;
  tax_total: number;
  discount: number;
  total: number;
  amount_paid: number;
  notes?: string | null;
  items: LineItem[];
  created_at: string;
}

export interface ProjectTask {
  id: string;
  title: string;
  is_milestone: boolean;
  status: string;
  due_date?: string | null;
  assigned_to?: UserBrief | null;
  position: number;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  budget?: number | null;
  owner?: UserBrief | null;
  team_ids: string[];
  tasks: ProjectTask[];
  created_at: string;
}

export interface Ticket {
  id: string;
  number: string;
  subject: string;
  description?: string | null;
  company_id?: string | null;
  company?: { id: string; name: string } | null;
  contact_id?: string | null;
  priority: string;
  status: string;
  assigned_to_id?: string | null;
  assigned_to?: UserBrief | null;
  resolution?: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body?: string | null;
  link?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AppSetting {
  key: string;
  value: Record<string, any>;
}

export interface TemplateVariable {
  key: string;
  label: string;
  sample: string;
}

export interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body_html: string;
  description?: string | null;
  updated_at: string;
  variables?: TemplateVariable[];

  /** What fires it. null means the template exists and nothing sends it. */
  trigger?: string | null;
  enabled: boolean;
  config: Record<string, any>;
  trigger_label?: string | null;
  trigger_description?: string | null;
  /** "event" fires inside a request; "scheduled" fires from a daily job. */
  trigger_kind?: "event" | "scheduled" | null;
  audience?: string | null;
  locked: boolean;
  locked_reason: string;
  customer_facing: boolean;
  config_schema: Record<string, EmailConfigField>;
  sent_count: number;
  last_sent_at?: string | null;
}

export interface EmailConfigField {
  label: string;
  type: "multiselect";
  options: number[];
  default?: number[];
  help?: string;
}

export interface EmailWorkflowTrigger {
  key: string;
  label: string;
  description: string;
  kind: "event" | "scheduled";
  audience: string;
  merge_fields: string[];
  locked: boolean;
  locked_reason: string;
  customer_facing: boolean;
  config_schema: Record<string, EmailConfigField>;
  template_id?: string | null;
  template_name?: string | null;
  enabled: boolean;
}


// --- platform / multi-tenancy -------------------------------------------------

/** One module in the current workspace's sidebar, as configured for this tenant. */
export interface TenantModule {
  id: string;
  module_key: string;
  /** What this tenant calls it — "Contacts" or "Customers" for the same module. */
  label: string;
  enabled: boolean;
  order: number;
  route: string;
  icon: string;
  permission: string | null;
  locked: boolean;
}

export type TenantStatus = "provisioning" | "trial" | "active" | "suspended" | "deleted";

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  type: "company" | "individual";
  status: TenantStatus;
  template_key: string;
  plan: string;
  timezone: string;
  currency: string;
  locale: string;
  owner_user_id?: string | null;
  created_at: string;
  suspended_at?: string | null;
}

export interface TenantUser {
  id: string;
  email: string;
  full_name: string;
  role?: string | null;
  is_active: boolean;
  last_login_at?: string | null;
  is_owner: boolean;
}

export interface TenantDetail extends Tenant {
  user_count: number;
  settings: Record<string, unknown>;
  owner_email?: string | null;
  owner_name?: string | null;
  module_count: number;
  enabled_module_count: number;
  /** Row counts, keyed by entity — only for modules this workspace has. */
  record_counts: Record<string, number>;
  users: TenantUser[];
}

export interface CrmTemplate {
  id: string;
  key: string;
  name: string;
  description?: string | null;
  version: number;
  is_system: boolean;
  module_count: number;
  enabled_module_count: number;
  role_count: number;
  stage_count: number;
}

export interface CrmTemplateDetail extends CrmTemplate {
  config: Record<string, any>;
}

export interface PlatformStats {
  tenants_total: number;
  tenants_active: number;
  tenants_suspended: number;
  users_total: number;
  by_template: Record<string, number>;
}


export interface Nominee {
  id: string;
  name: string;
  relation?: string | null;
  date_of_birth?: string | null;
  age?: number | null;
  share_percent: number;
  appointee_name?: string | null;
  appointee_relation?: string | null;
  position: number;
  is_minor: boolean;
}

export interface CustomerNote {
  id: string;
  body: string;
  is_pinned: boolean;
  created_at: string;
  author?: UserBrief | null;
}

// --- policies -----------------------------------------------------------------

export interface Master {
  id: string;
  type: string;
  name: string;
  code?: string | null;
  is_active: boolean;
  order: number;
}

export type ProductLine = "motor" | "health" | "life" | "general";

export type PolicyStatus =
  | "draft" | "active" | "expiring" | "renewed" | "lapsed" | "cancelled";

export interface Policy {
  id: string;
  policy_number: string;
  product_line: ProductLine;
  plan_name?: string | null;
  insurer_id?: string | null;
  /** The intermediary the policy was placed through, where it was not placed direct. */
  broker_id?: string | null;
  bank_id?: string | null;
  branch?: string | null;
  sourcing_channel?: string | null;
  customer_id: string;
  owner_id?: string | null;
  issue_date?: string | null;
  start_date?: string | null;
  expiry_date?: string | null;
  premium_net: string | number;
  premium_gst: string | number;
  premium_gross: string | number;
  sum_insured?: string | number | null;
  currency: string;
  payment_mode?: string | null;
  payment_frequency?: string | null;
  status: PolicyStatus;
  renewal_of_id?: string | null;
  renewed_to_id?: string | null;
  commission_percent?: string | number | null;
  commission_amount?: string | number | null;
  registration_no?: string | null;
  remarks?: string | null;
  tags: string[];
  /** Line-specific fields — vehicle, members covered, riders. */
  details: Record<string, any>;
  custom: Record<string, any>;
  created_at: string;
  updated_at: string;
  insurer?: Master | null;
  broker?: Master | null;
  bank?: Master | null;
  customer?: { id: string; first_name: string; last_name: string; full_name: string; mobile?: string | null } | null;
  owner?: UserBrief | null;
  days_to_expiry?: number | null;
  is_in_force?: boolean;
}

export interface RenewalDue {
  id: string;
  policy_number: string;
  product_line: ProductLine;
  expiry_date: string;
  days_to_expiry: number;
  premium_gross: string | number;
  status: PolicyStatus;
  customer?: Policy["customer"];
  insurer?: Master | null;
  owner?: UserBrief | null;
}

export interface PolicyStats {
  customers: number;
  active_policies: number;
  book_premium: string | number;
  renewals_60d: number;
  renewals_30d: number;
  renewals_7d: number;
  lapsed: number;
  new_business_mtd_count: number;
  new_business_mtd_premium: string | number;
  birthdays_this_week: number;
  commission_mtd: string | number;
}

export interface PolicyCharts {
  premium_by_month: { month: string; new: number; renewal: number }[];
  by_insurer: { name: string; count: number; premium: number }[];
  by_product_line: { name: string; count: number; premium: number }[];
  by_status: { name: string; count: number }[];
}

// --- loans --------------------------------------------------------------------

export type LoanStatus =
  | "enquiry" | "documents" | "logged_in" | "sanctioned" | "disbursed" | "rejected";

export interface Loan {
  id: string;
  customer_id: string;
  loan_type: string;
  lender_id?: string | null;
  owner_id?: string | null;
  status: LoanStatus;
  amount_requested?: string | number | null;
  amount_sanctioned?: string | number | null;
  tenure_months?: number | null;
  interest_rate?: string | number | null;
  payout_percent?: string | number | null;
  /** Derived server-side from the sanctioned amount — never sent on write. */
  expected_payout?: string | number | null;
  actual_payout?: string | number | null;
  applied_on?: string | null;
  sanctioned_on?: string | null;
  disbursed_on?: string | null;
  rejected_reason?: string | null;
  remarks?: string | null;
  tags: string[];
  custom: Record<string, any>;
  customer?: Policy["customer"];
  lender?: Master | null;
  owner?: UserBrief | null;
  is_open?: boolean;
}

export interface LoanStats {
  open_cases: number;
  sanctioned_value: string | number;
  disbursed_value: string | number;
  expected_payout: string | number;
  received_payout: string | number;
  outstanding_payout: string | number;
  by_status: Record<string, number>;
}

export interface LoanBoardColumn {
  status: LoanStatus;
  label: string;
  loans: Loan[];
  value: string | number;
}
