# WeTa CRM — Multi-Tenant Platform & Insurance Agent Vertical

**Product Requirements / User Requirements Specification**

| | |
|---|---|
| Version | 0.1 (draft for review) |
| Date | 2026-09-07 |
| Base system | WeTa CRM v1.0 (FastAPI modular monolith + React/TS, see `PROJECT_PLAN.md`, `CLAUDE.md`) |
| Status | Awaiting sign-off on §2 open decisions before Phase 0 starts |

---

## 1. Purpose and scope

Today WeTa CRM is a single-organisation, general-purpose CRM. This document specifies two changes that
ship together:

1. **A multi-tenant platform layer.** A platform Super Admin creates client accounts (a company or an
   individual agent), picks a **template** (General CRM or Insurance Agent), and the new tenant gets a
   fully configured CRM of its own. Fields, modules and labels can then be customised per client.
2. **An Insurance Agent vertical.** A template that reshapes the CRM for an insurance agent or agency:
   Policies, Customers, renewals, PII handling, WhatsApp outreach, poster studio and insurance reporting.

The existing general CRM continues to work — it becomes the "General CRM" template rather than a
separate product.

### Out of scope for this document

Claims management workflow, agent-hierarchy commission splits (sub-agents / POSP downlines), customer
self-service portal, mobile apps, IRDAI regulatory filings, accounting/GST return integration. These are
noted in §12 as candidates for later.

---

## 2. Decisions still open

The four questions below materially change the build. I have assumed a default for each so this
document is complete and actionable — **correct any that are wrong and I will revise before Phase 0.**

| # | Question | Assumed answer | Why it matters |
|---|---|---|---|
| D1 | How does the insurance version relate to the current codebase? | **One codebase, multi-tenant, template-driven.** Your later message ("multi tenant software... keep these as a general crm template and insurance template") settles this — no fork, no separate repo. | Determines the whole architecture. Now assumed settled. |
| D2 | WhatsApp capability | **Phase 1: click-to-chat (`wa.me`) only** — free, no approvals, works immediately. **Phase 5: Meta WhatsApp Cloud API** behind a provider interface so a BSP (AiSensy/Interakt/Twilio) can be swapped in. | Automated/bulk sending needs a Meta Business account, business verification, a dedicated number and pre-approved templates. Click-to-chat needs none of that, so requirement C6 ships in week one. |
| D3 | Insurance lines covered | **Motor, Health and Life as first-class** (each with its own field set), **General/non-motor as a light generic set.** Motor is assumed primary — the Vahan button implies it. | Drives how many product-specific field groups the Policies module needs. Dropping a line is cheap; adding one later is a schema change. |
| D4 | What pincode does | **Serviceability + address autofill.** Capture pincode → auto-fill city/state → filter the insurer/product list to those available in that area. **Motor RTO zone-based premium maths is deferred** to a later phase. | Zone pricing needs a maintained pincode→zone reference table and real premium formulas per insurer. Serviceability only needs a mapping table you control. |

**One compliance flag before you sign off** — see §9.3. Storing full Aadhaar numbers by a private entity
is restricted under the Aadhaar Act (s.29) and UIDAI regulations; the normal practice for insurance
intermediaries is to store **only the last 4 digits** plus an offline e-KYC reference, not the full
12-digit number. The design below supports full-Aadhaar storage (encrypted, masked, audited) because you
asked for it, but it is **off by default** and must be switched on per tenant with an explicit
acknowledgement. Please confirm you want it available at all.

---

## 3. Personas

| Persona | Scope | Typical needs |
|---|---|---|
| **Platform Super Admin** (you) | Tenant *configuration* only, never tenant data | Create/suspend/delete clients, choose and edit templates, customise their fields and modules, see platform health |
| **Tenant Admin** (agency owner) | One tenant | Manage own users/roles, branding, own custom fields, insurers/products masters, see whole book |
| **Agent / Sales Executive** | Own + assigned records | Daily work: customers, policies, renewals, quotes, tasks, WhatsApp outreach |
| **Ops / Back office** | Tenant-wide | Policy data entry, document collection, renewal chasing, reconciliation |
| **Viewer / Accountant** | Read-only | Premium and commission reports |

---

# PART A — Multi-tenant platform

## 4. Tenancy model

### 4.1 Isolation strategy

**Shared database, shared schema, `tenant_id` discriminator on every business table**, enforced centrally.

Rejected alternatives: schema-per-tenant (Postgres schema sprawl, painful migrations at scale) and
database-per-tenant (operationally heavy for a VPS deployment). The shared-schema approach fits the
existing SQLAlchemy setup and the current Docker Compose footprint.

**The isolation must be enforced in one place, not in every router.** A single missed `WHERE tenant_id`
is a cross-client data leak. Implementation:

- A `TenantScoped` mixin adds `tenant_id: Mapped[str]` (indexed FK to `tenants.id`) to every business model.
- A request-scoped `ContextVar` holds the current tenant, set by the auth dependency from the JWT `tid` claim.
- A global SQLAlchemy `do_orm_execute` event injects `with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == current_tenant_id())` into **every** ORM query, including relationship loads.
- Inserts get `tenant_id` from the same context via a `before_flush` hook, so routers never set it by hand.
- A guard raises loudly if a tenant-scoped query runs with no tenant in context (except for explicitly marked platform-level queries).

This is the single most security-critical piece of the build. It gets its own test suite in Phase 0
(§11) before any feature work lands on top of it.

### 4.2 Schema consequences

Every currently-global unique constraint becomes **composite with `tenant_id`**:

| Table | Today | Becomes |
|---|---|---|
| `settings` | `key` unique | `UNIQUE(tenant_id, key)` |
| `email_templates` | `name` unique | `UNIQUE(tenant_id, name)` |
| `deal_stages` | `name` unique | `UNIQUE(tenant_id, name)` |
| `tags` | `name` unique | `UNIQUE(tenant_id, name)` |
| `lead_sources` | `name` unique | `UNIQUE(tenant_id, name)` |
| `users` | `email` unique | stays globally unique (see §4.4) |
| `quotations` / `invoices` | number unique | `UNIQUE(tenant_id, number)` |

Document numbering (`app/services/numbering.py`) already reads its counter from the `settings` table, so
once settings are tenant-scoped, `QT-2026-0001` restarts per tenant automatically — no code change beyond
the scoping.

### 4.3 Stop using `create_all` — cut over to Alembic now

The current schema is managed by `Base.metadata.create_all()` plus the additive-column hack in
`app/database/ensure_schema.py`. Adding `tenant_id` to ~25 tables, changing unique constraints and
backfilling existing rows is exactly the kind of change that hack cannot do.

**Phase 0 generates a baseline Alembic migration** (`migrations/versions/` is currently empty) and all
later schema work goes through Alembic. `ensure_schema.py` is retired.

### 4.4 Authentication and tenant resolution

- `users.email` stays **globally unique**; one login belongs to exactly one tenant. Simplest correct model, and avoids a tenant-picker on the login screen.
- `users.tenant_id` is nullable; `NULL` + `is_platform_admin = true` identifies a platform Super Admin.
- JWT gains a `tid` claim. `get_current_user` sets the tenant context from it.
- Platform admins authenticate into the **platform console** (`/platform`), a different shell from the tenant app.
- **No impersonation.** A platform admin cannot open a client's workspace. This was built and then deliberately removed: a support session that can read every customer's PAN and Aadhaar is a standing breach waiting for one compromised admin account, and the audit trail only tells you afterwards. The console manages a workspace from the outside — modules, template, status, owner and record counts — which covers what support actually needs. Where a person genuinely must see a client's data, the client adds them as a user of their own workspace, which is visible to the client and revocable by them.

### 4.5 Infrastructure scoping

| Service | Change |
|---|---|
| Meilisearch | One index per entity (unchanged), with `tenant_id` added as a **filterable attribute**; every query is filtered. Simpler than index-per-tenant and stays within Meilisearch limits. |
| MinIO / local uploads | Object keys prefixed `tenants/<tenant_id>/…`. Download endpoints verify the key prefix matches the caller's tenant before streaming. |
| Socket.IO | Rooms become `tenant:<tid>:user:<uid>`. |
| Celery beat jobs | Every scheduled job (renewal reminders, birthdays, daily summary, reindex) iterates active tenants and runs inside each tenant's context. |
| Rate limiting | Keyed by `tenant_id + IP` rather than IP alone. |

---

## 5. Super Admin console

A separate React shell at `/platform`, accessible only to `is_platform_admin` users.

### 5.1 Tenants

| Screen | Contents |
|---|---|
| Tenant list | Name, type (Company / Individual), template, plan, users, status (Active / Trial / Suspended), created, last activity. Search + filter. |
| Create tenant | Name, type, slug, owner first/last name, owner email, owner mobile, **template selection**, plan, timezone, currency, locale. On save: provision (§6.3), create the owner as Tenant Admin, email credentials. |
| Tenant detail | Overview + tabs: Users, Modules, Fields, Branding, Usage, Audit. Actions: Impersonate, Suspend, Reactivate, Delete. |
| Suspend | Blocks all logins for that tenant; data retained; reversible. |
| Delete | Two-step confirmation with the tenant name typed to confirm; soft-delete for 30 days, then a purge job removes rows and storage objects. |

### 5.2 Template manager

- View the two system templates (General CRM, Insurance Agent) — read-only, versioned.
- **Clone** a system template into a custom template, then edit it and use it for new tenants.
- Template diff view: what a template changes relative to the base CRM.
- Templates are **cloned into a tenant at provisioning time**, never referenced live. Editing a template afterwards does not silently mutate existing tenants — a deliberate "apply template update to tenant X" action does, with a preview of what changes.

### 5.3 Per-tenant customisation

The Super Admin can, for any tenant: enable/disable modules, rename module and field labels, add/edit/remove
custom fields (§7), set required/optional, reorder fields and sections, and configure pipeline stages and
customer stages. The Tenant Admin gets the same screens scoped to their own tenant, minus the ability to
disable modules their plan includes.

### 5.4 Platform dashboard

Tenant count by status and template, new tenants this month, active users (7/30-day), storage used per
tenant, WhatsApp message volume and cost per tenant, failed background jobs, recent platform audit events.

---

## 6. Templates

### 6.1 What a template defines

A template is a versioned JSON document, seeded from `app/platform/templates/*.json`:

```jsonc
{
  "key": "insurance_agent",
  "name": "Insurance Agent",
  "version": 1,
  "modules": [
    { "key": "dashboard",  "enabled": true,  "label": "Dashboard",  "order": 1 },
    { "key": "customers",  "enabled": true,  "label": "Customers",  "order": 2, "base": "contacts" },
    { "key": "policies",   "enabled": true,  "label": "Policies",   "order": 3 },
    { "key": "pipeline",   "enabled": true,  "label": "Pipeline",   "order": 4 },
    { "key": "quotations", "enabled": true,  "label": "Quotations", "order": 5 },
    { "key": "poster",     "enabled": true,  "label": "Poster Studio", "order": 6 },
    { "key": "loans",      "enabled": true,  "label": "Loans",      "order": 7 },
    { "key": "tasks",      "enabled": true,  "label": "Tasks",      "order": 8 },
    { "key": "reports",    "enabled": true,  "label": "Reports",    "order": 9 },
    { "key": "companies",  "enabled": false },
    { "key": "invoices",   "enabled": false },
    { "key": "projects",   "enabled": false },
    { "key": "support",    "enabled": false }
  ],
  "fields":   { "customers": [ /* field defs, see §7 */ ] },
  "stages":   { "pipeline": [...], "customer": [...] },
  "roles":    [ /* role name → permission list */ ],
  "masters":  { "insurers": [...], "product_types": [...], "banks": [...], "relations": [...] },
  "settings": { "branding": {...}, "features": { "whatsapp": true, "aadhaar_full": false } },
  "email_templates": [...],
  "poster_templates": [...]
}
```

### 6.2 The two system templates

**General CRM** — today's module set exactly as it ships now (Companies, Contacts, Leads, Deals, Pipeline,
Calendar, Tasks, Projects, Products, Quotations, Invoices, Support, Reports, Settings). This is the
regression baseline: a tenant created from it must behave identically to the current single-tenant app.

**Insurance Agent** — module set per §6.1 above. Contacts is relabelled **Customers** and extended with
insurance fields; Deals/Pipeline is relabelled to an enquiry pipeline; Companies, Invoices, Projects and
Support are off by default (a tenant admin can switch Support back on for service requests).

### 6.3 Provisioning a tenant

1. Create the `tenants` row (status `provisioning`).
2. Generate and store the tenant's data-encryption key (§9.2).
3. Copy the template config into tenant-owned rows: roles + permissions, module config, custom field definitions, pipeline and customer stages, masters (insurers, product types, banks, relations), settings, email templates, poster templates.
4. Create the owner user as Tenant Admin with a random password.
5. Create the search index filter and the storage prefix.
6. Set status `active`; send the welcome email with a password-set link.

The whole step runs in one transaction and is idempotent — a failed provision can be retried. This
replaces today's global `app/database/seed.py`, which becomes `provision_tenant(db, tenant, template)`.

---

## 7. Custom fields engine

This is what makes "customize the fields as per client requirements" real.

### 7.1 Storage

- `custom_field_defs` — `tenant_id`, `module`, `key`, `label`, `field_type`, `options` (JSON), `required`, `section`, `order`, `default_value`, `help_text`, `show_in_table`, `filterable`, `is_pii`, `is_active`.
- Each entity table gains a `custom` JSON column. Values live there; no per-tenant DDL, ever.
- On Postgres the column is `JSONB` with a GIN index so custom-field filtering stays fast.

Field types: `text`, `textarea`, `number`, `decimal`, `date`, `datetime`, `select`, `multiselect`,
`checkbox`, `email`, `phone`, `url`, `currency`, `file`, `lookup` (reference another record).

### 7.2 How it reaches the UI

The frontend already treats list pages as configuration — `components/CrudPage.tsx` consumes a
`FieldDef[]`, `columns`, `allColumns` and `filterFields`. **That existing design is why this is
tractable:** instead of those arrays being hardcoded in `pages/Companies.tsx` and friends, a new endpoint

```
GET /api/v1/schema/{module}
```

returns the merged **base fields + tenant custom fields + labels + stages** for the current tenant, and
`CrudPage` renders from it. Hardcoded page configs become the fallback/base definition that the API merges
over.

Server-side, the same definitions build a dynamic Pydantic validator per module per tenant (cached), so
custom fields are validated as strictly as base ones. `app/filtering.py` gains a dynamic layer that maps a
filterable custom field to a JSON-path expression, and the CSV `IOSpec` registry gains custom columns so
import/export stays in step.

### 7.3 Guard rails

- Base fields required by business logic (e.g. policy expiry date, customer mobile) are marked **locked** — a tenant can relabel and reorder them but cannot delete or make them optional.
- Deleting a custom field soft-deletes the definition and retains the data for 30 days.
- Changing a field's type is blocked once data exists; the user is directed to create a new field instead.

---

# PART B — Insurance Agent vertical

## 8. Modules

### 8.1 Dashboard

**Top KPI strip** (the four you named, plus four more that fall out of the same data):

| KPI | Definition |
|---|---|
| Customers | Active customer count for the tenant (scoped to own records for an agent, tenant-wide for admin) |
| Active policies | Policies with status `active` and expiry ≥ today |
| Book premium | Σ gross premium of active policies (the in-force book) |
| Renewals in 60 days | Policies expiring within 60 days, not yet renewed |
| Renewals in 7 / 30 days | Same, tighter windows — the actual daily work queue |
| New business MTD | Policies issued this month, count + premium |
| Lapsed | Expired > 0 days and not renewed |
| Birthdays this week | Feeds the wish workflow (§10.1) |

**Privacy toggle (requirement).** A single eye icon in the KPI strip header hides/shows *all* numeric
values at once — counts and amounts blur to `••••`. Useful when the agent is screen-sharing or sitting
with a customer. State persists per user (server-side user preference, mirrored to `localStorage` so
there is no flash of visible values on load). Default: **visible**.

**Charts** (Recharts, already a dependency): premium by month split new vs renewal; policies by insurer;
policies by product type; renewal funnel (due → contacted → quoted → renewed → lapsed); enquiry-to-policy
conversion; top 5 products by premium.

**Panels:** renewals due this week with one-click call/WhatsApp, today's tasks, today's and this week's
birthdays, recent activity, quotes awaiting response.

Every KPI and chart segment is **click-through** to a filtered list — the existing
`/reports/dashboard/drilldown` endpoint and `DrilldownModal.tsx` component already do this and get extended.

### 8.2 Policies

The core new module. `GET/POST/PATCH/DELETE /api/v1/policies` following the router conventions in
`CLAUDE.md` (get_or_404 → apply_updates → log_activity + audit → notify → commit → search_sync).

**Common fields (all lines):** policy number, insurer, product type, plan name, customer, proposer (if
different), sourcing channel, **bank** (bancassurance source — you asked for a bank filter), branch,
issue date, risk start date, expiry date, premium (net / GST / gross), payment mode, payment frequency,
status, renewal-of link, renewed-to link, agent/owner, commission %, commission amount, remarks,
attachments, nominee block (§10.5).

**Status model:** `draft → active → expiring (auto, within 60 days) → renewed | lapsed | cancelled`.
A nightly job moves policies between `active`, `expiring` and `lapsed`. Renewal creates a **new** policy
row linked to the previous one, preserving history — never an in-place edit.

**Line-specific field groups** (rendered conditionally on product type, and extendable per tenant via §7):

| Line | Fields |
|---|---|
| Motor | Registration no., make, model, variant, fuel, CC, seating, mfg year, RTO, chassis no., engine no., IDV, NCB %, OD premium, TP premium, previous insurer, previous policy no., claim taken (Y/N), PUC expiry |
| Health | Sum insured, policy type (individual/floater/top-up), members covered (name, DOB, relation), pre-existing diseases, waiting period, room-rent limit, co-pay %, portability from |
| Life | Sum assured, policy term, premium paying term, maturity date, riders, bonus type, next due date |
| General | Risk location, coverage type, sum insured, peril set |

**Filters (requirement):** insurer, **bank**, product type, status, expiry-date range, issue-date range,
agent, branch, sourcing channel, premium range, city/pincode, renewal-due window, claim taken. All wired
through the existing whitelist registry in `app/filtering.py`, so CSV export automatically matches the
on-screen filter.

**List views:** the saved-views mechanism already in `CrudPage` gives per-agent column sets for free
(e.g. a "Renewal desk" view showing customer, mobile, insurer, expiry, premium).

### 8.3 Customers

Contacts, relabelled and extended. Full field list in §10; the behaviours that make it a *customer* record
rather than a contact record:

- **Lifecycle stage** on the record (§10.11), configurable per tenant.
- **360° detail view** with tabs: Overview, Policies (all policies incl. history and renewals), Quotations, Loans, Notes, Attachments, Tasks, **Timeline / Audit log**.
- Family / dependent linking, so a floater health policy or a household's motor policies group together.
- Cross-sell surface: "has motor, no health" style prompts derived from the customer's product mix.

### 8.4 Pipeline (enquiries)

The existing Kanban, retargeted. Default insurance stages (tenant-editable):
`New enquiry → Contacted → Quote shared → Negotiation → Documents collected → Payment pending → Policy issued | Lost`.

Cards show **name + mobile + WhatsApp icon** (requirement C4/C6), product type, expected premium and
expiry/target date. Won ("Policy issued") prompts to create the Policy record from the enquiry, carrying
over customer, product and premium — the same pattern as today's lead→deal conversion in
`app/leads/router.py`.

### 8.5 Quotations

Keeps the existing engine (line items, tax maths in `app/services/billing.py`, sequential `QT-` numbering,
ReportLab PDF, email send, convert). Insurance changes:

- Quote lines become **plan options** — compare 2–4 insurer quotes side by side on one PDF (insurer, plan, sum insured/IDV, premium breakup, key inclusions/exclusions).
- Merge fields for insurance data; branded per tenant.
- "Convert to Policy" replaces "Convert to Invoice" for insurance tenants.
- Send via email **and** WhatsApp (PDF as document message, or link).

### 8.6 Poster Studio

Design and send branded creatives — the module with the most new UI.

- **Template gallery:** birthday, policy renewal reminder, policy issued / thank-you, festival greetings, product promo, claim-assistance. Seeded per tenant from the template (§6.1) and extendable.
- **Editor:** canvas-based (fabric.js), drag/resize/rotate text and image layers, tenant brand colours and fonts, agent photo and contact strip, background image upload or stock pick, layer ordering, undo/redo. Deliberately similar in spirit to the existing document-template studio in `app/settings/router.py` (`/document-preview/{kind}`) so the UX rhymes.
- **Merge fields:** `{customer_name}`, `{policy_number}`, `{insurer}`, `{expiry_date}`, `{days_to_expiry}`, `{premium}`, `{vehicle_no}`, `{agent_name}`, `{agent_mobile}`, `{agency_name}`.
- **Personalised batch generation:** pick an audience (today's birthdays, renewals in N days, a saved policy filter, or a manual selection) → the studio renders one personalised PNG per recipient → preview grid → send.
- **Sending:** Phase 4 = per-customer click-to-chat, image downloaded and attached by the agent, or shared via the Web Share API on mobile. Phase 5 = direct send through the WhatsApp API (§10.11), queued via Celery with per-tenant rate limiting and delivery status.
- **Output:** PNG (1080×1080 and 1080×1920 story) plus PDF; stored under the tenant's storage prefix with a 90-day retention for generated batches.

### 8.7 Loans

Cross-sell tracking, on by default in the insurance template.

Fields: customer, loan type (home, personal, vehicle, business, loan-against-property, education), amount
requested, tenure, lender/bank, status (`enquiry → documents → logged in → sanctioned → disbursed |
rejected`), sanctioned amount, ROI, payout %, expected payout, actual payout, disbursement date, remarks,
attachments. Simple Kanban + list, and a payout report.

Customers also carry a **products of interest** multi-select (motor, health, life, general, and each loan
type) so an agent can flag interest without creating a record — this covers the lighter reading of
"an option for selecting loans".

### 8.8 Tasks and Calendar

Existing modules, with insurance task types: renewal call, document collection, birthday wish, payment
follow-up, claim assistance, policy delivery. Tasks link to a customer **and optionally a policy**. Task
rows show name + mobile + WhatsApp icon. Renewal tasks are auto-created by the nightly job at 60/30/15/7/1
days before expiry (thresholds configurable per tenant).

### 8.9 Reports

Renewal register (due in range, with contact status), production/premium report (by month, insurer,
product, bank, agent), commission report (earned, received, pending), lapse and retention analysis,
customer growth, birthday list, cross-sell opportunity list, loan payout report, agent performance
leaderboard. All exportable to CSV/Excel through the existing `/io` engine, and to PDF.

---

## 9. Security, PII and compliance

### 9.1 What counts as sensitive here

PAN, Aadhaar, date of birth, mobile numbers, address, bank details, health declarations, income. PAN and
Aadhaar get the strongest treatment (encryption + masking + reveal audit); the rest are protected by
tenant isolation, RBAC and transport security.

### 9.2 Encryption at rest (requirement C13)

- Envelope encryption. A platform master key (`PII_MASTER_KEY`, 32 bytes, base64, from env — never in the repo) encrypts a **per-tenant data-encryption key** stored in `tenants.dek_encrypted`.
- Field encryption is **AES-256-GCM** via the `cryptography` package (new dependency), wrapped in a SQLAlchemy `TypeDecorator` (`EncryptedString`) so models declare `pan: Mapped[str] = mapped_column(EncryptedString(...))` and encryption is transparent.
- **Searchability:** an encrypted column cannot be searched with `LIKE`. Each encrypted field gets a companion **blind index** column — `HMAC-SHA256(tenant_key, normalise(value))` — which supports exact-match lookup ("find the customer with this PAN") without exposing plaintext.
- Encrypted values are **never** sent to Meilisearch and never appear in logs, exports (unless explicitly permitted), or error messages.
- Key rotation: a documented re-encryption job; master key rotation re-wraps tenant DEKs without touching row data.

### 9.3 Masking and reveal (requirement)

- API responses return **masked values by default**: PAN as `ABCDE••••F`, Aadhaar as `•••• •••• 1234`.
- Full value requires a dedicated call — `POST /api/v1/customers/{id}/reveal` with `{"field": "pan"}` — gated by a new permission `customers:reveal_pii`, rate-limited per user, and **written to the audit log every time** (who, what field, which customer, when, from which IP).
- The UI shows a masked value with an eye icon; clicking calls the reveal endpoint, shows the value for 30 seconds, then re-masks. A tooltip states that the view is logged.
- Reveal events are visible to the Tenant Admin in a "PII access" report.

### 9.4 Aadhaar — read this before sign-off

Under the Aadhaar Act s.29 and UIDAI regulations, a private entity that is not an authorised
KYC user generally **should not store the full 12-digit Aadhaar number**. The accepted practice for
insurance intermediaries is to store the **last 4 digits** and, where identity proof is needed, an
**offline e-KYC reference** or a masked Aadhaar image.

The design therefore:

- **Default:** the Aadhaar field stores last-4 only, plus an optional masked-Aadhaar document attachment.
- **Optional:** a per-tenant feature flag `aadhaar_full` enables full-number capture (encrypted, masked, reveal-audited as above). Enabling it requires the Tenant Admin to accept an on-screen acknowledgement of their legal basis, which is recorded with a timestamp.
- PAN has no equivalent restriction and is stored in full (encrypted) by default.

I have built this in because you asked for full Aadhaar capture; please confirm you want the flag to exist,
and consider taking your compliance advisor's view before enabling it for a live tenant.

### 9.5 Other hardening in scope

Tenant-scoped rate limiting; the current in-memory limiter in `app/core/rate_limit.py` moves to Redis so
it survives multiple workers. Attachment upload validation (MIME sniffing, size caps, extension allowlist).
Signed, expiring URLs for document downloads. Audit retention policy per tenant.

---

## 10. Cross-cutting requirements (your numbered list)

| # | Requirement | Specification |
|---|---|---|
| C1 | Birthdays shown in the customer section | A "Birthdays" panel in Customers and on the Dashboard: Today / Tomorrow / This week / This month tabs, each row showing name, age turning, mobile, WhatsApp button and "Send birthday poster". Backed by a day-and-month index on DOB so the query is fast. A daily job creates birthday tasks and (Phase 5) can auto-send. |
| C2 | Capture pincode; policy selection based on it | Pincode field with 6-digit validation and **auto-fill of city/state** from a bundled India pincode dataset (offline, no API dependency). A tenant-maintained `insurer_serviceability` mapping (insurer × product × pincode/state) filters the insurer and product dropdowns when creating a policy or quote. Zone-based premium maths deferred (D4). |
| C3 | PAN and Aadhaar mandatory | Both marked required on the customer form, enforced server-side. PAN validated against `[A-Z]{5}[0-9]{4}[A-Z]` and uppercased. Aadhaar validated as 12 digits with the **Verhoeff checksum** (catches typos). Per §9.4 the stored Aadhaar is last-4 unless the tenant enables full capture. A tenant setting can relax "mandatory" to "mandatory before policy issue" so an early-stage enquiry is not blocked. |
| C4 | Name + phone visible everywhere | One shared `<CustomerChip>` component — avatar, name, primary mobile, WhatsApp icon, click-through to the customer — reused in pipeline cards, task rows, policy rows, quotation rows, loan rows, calendar entries, notification items and global search results. Table `allColumns` for every module includes mobile so it can be added to any saved view. |
| C5 | Nominee name, age, relation | A nominee block on both the customer (default nominee) and the policy (policy-specific, pre-filled from the customer and overridable). Fields: name, **age**, **relation** (from a tenant-editable master), DOB, share %, and appointee name/relation when the nominee is a minor. Multiple nominees per policy with shares validated to total 100%. |
| C6 | Mobile + alternative mobile with WhatsApp icon | Both fields on the customer. Each renders a WhatsApp icon that opens `https://wa.me/<E.164>?text=<prefilled>` in a new tab — works with WhatsApp Web on desktop and the app on mobile, no integration needed. Numbers are normalised to E.164 on save (default country code per tenant). Prefilled text comes from a per-context message template (renewal, birthday, quote follow-up). |
| C7 | Multiple notes + attachments when adding/editing a customer | A repeatable notes section inside the customer form (not only on the detail page) — each note carries body, author, timestamp, optional pin, and is editable/deletable by its author or an admin. Attachments: multi-file drag-and-drop with a category (PAN, Aadhaar, RC, previous policy, photo, other), stored via the existing `app/services/storage.py`, virus/MIME checked, listed with preview and download. Both persist as part of the create/edit transaction. |
| C8 | Audit history shown as logs on the record | A Timeline tab on the customer (and policy) merging the existing `activities` and `audit_logs` tables: field-level changes rendered as "Mobile changed from X to Y by Priya · 12 Mar 2026 14:20", plus system events, notes, calls, WhatsApp sends, PII reveals, document uploads. Filterable by event type and date. The backend already records all of this via `log_activity` and `audit` — this is mostly a read/render surface. |
| C9 | Referred by | On the customer: `referred_by_type` (existing customer / staff / external / campaign), a lookup to the referring customer when applicable, free-text name otherwise, and referral date. Enables a referral report and a "referrals given" count on the referrer's profile. |
| C10 | Option for selecting loans | Two levels: a **products of interest** multi-select on the customer that includes each loan type (light touch), and the full **Loans module** (§8.7) for tracking an actual loan case to payout. |
| C11 | WhatsApp integration | Phase 1: click-to-chat everywhere (C6). Phase 5: a `WhatsAppProvider` interface with a Meta Cloud API implementation — send text, template and media (poster/PDF) messages; store message id and delivery status; queue through Celery with per-tenant throttling; handle the 24-hour session window by using approved templates for the first contact. Tenant settings hold the phone number id, token and template mapping. Because a BSP swap is likely, no provider specifics leak past the interface. |
| C12 | Global search | The existing global search (`app/search/router.py`, Meilisearch with SQL fallback) extended to index **customers, policies, quotations and loans**, tenant-filtered (§4.5). Searchable by name, mobile, policy number, vehicle registration number and PAN **via blind index only** (exact match, never substring — see §9.2). Results grouped by type with the customer chip; `Ctrl/Cmd+K` to open. |
| C13 | PAN and Aadhaar encrypted in the database | §9.2. |
| C14 | Vahan portal button | A button in the top bar (insurance template only) opening `https://vahan.parivahan.gov.in/nrservices/faces/user/searchstatus.xhtml` in a new tab, with `rel="noopener noreferrer"`. If a vehicle registration number is in context (viewing a motor policy), it is copied to the clipboard with a toast — the portal does not accept a registration number as a URL parameter, so pre-filling is not possible. The button's URL is a tenant setting so it can be repointed. |
| C15 | Stages in customer details | A configurable customer lifecycle stage, separate from the enquiry pipeline. Default set: `Prospect → Contacted → Documents pending → Policy issued → Active → Renewal due → Lapsed → Dormant`. Shown as a stepper at the top of the customer detail view, changeable inline, every change written to the timeline. Stages, colours and order are per-tenant (template-seeded, admin-editable). |

---

# PART C — Delivery

## 11. Phase plan

Each phase ends in a state you can run locally and click through. "Verify locally" lists what to check
before moving on.

### Phase 0 — Multi-tenant foundation *(largest risk, do it first)*

- Baseline Alembic migration from the current schema; retire `ensure_schema.py`.
- `tenants` table; `TenantScoped` mixin and `tenant_id` on all business tables; composite unique constraints (§4.2).
- Tenant context var, JWT `tid` claim, global `do_orm_execute` filter, insert hook, missing-context guard.
- Platform admin flag, `/platform` auth, impersonation with audit.
- Migrate existing data into a single "Default" tenant so nothing is lost.
- Scope storage keys, search filter, socket rooms, rate limiter, Celery jobs.
- **Isolation test suite** (this is the deliverable that matters): two tenants, overlapping data, and a test per module asserting that tenant A's token can never read, update, delete, export, search or download tenant B's rows — including via relationship loads, drilldowns, CSV export and file download endpoints.

*Verify locally:* create two tenants, log in as each, confirm complete separation; confirm the existing app still behaves identically for the Default tenant.

### Phase 1 — Templates, provisioning and Super Admin console

- Template JSON schema; seed General CRM and Insurance Agent templates.
- `provision_tenant()` replacing global seeding.
- Super Admin console: tenant list, create, detail, suspend, impersonate, template manager.
- Module enable/disable and label overrides driving the sidebar and routes.

*Verify locally:* create a tenant from each template; confirm the General CRM tenant matches today's app and the Insurance tenant shows the insurance module set with renamed labels.

### Phase 2 — Custom fields engine

- `custom_field_defs`, `custom` JSON columns, `GET /schema/{module}`.
- `CrudPage` driven by API-supplied field definitions; dynamic server-side validation.
- Field editor UI (Super Admin + Tenant Admin); dynamic filtering and CSV import/export.

*Verify locally:* add a custom field to Customers for one tenant, confirm it appears in the form, table views, filters and CSV export — and does **not** appear for the other tenant.

### Phase 3 — Customers and PII

- Customer model: all fields per §10, nominee block, referred-by, stages, products of interest.
- Encryption service, `EncryptedString`, blind indexes, masking, reveal endpoint + permission + audit.
- Pincode dataset with city/state autofill; PAN and Aadhaar validation.
- Notes and attachments in the create/edit form; timeline/audit tab; `<CustomerChip>` rolled out everywhere.
- Birthday panel and query.

*Verify locally:* create a customer with PAN and Aadhaar; inspect the database and confirm ciphertext, not plaintext; confirm masking, reveal, and that the reveal is in the audit log.

### Phase 4 — Policies and renewals

- Policy model with common + line-specific field groups; full CRUD, filters (incl. bank), saved views.
- Status lifecycle job; renewal-as-new-record with history chain.
- Renewal task automation at 60/30/15/7/1 days.
- Insurance Dashboard: KPI strip with privacy toggle, charts, renewal and birthday panels, drill-through.
- Enquiry pipeline stages and "Policy issued → create policy".

*Verify locally:* create policies across motor/health/life, set expiry dates near today, run the job, confirm status transitions, renewal tasks, and correct KPI numbers with the toggle hiding them.

### Phase 5 — WhatsApp and Poster Studio

- Click-to-chat completed everywhere with per-context message templates.
- Poster Studio: template gallery, canvas editor, merge fields, batch personalised generation, download/share.
- `WhatsAppProvider` interface + Meta Cloud API implementation; template management; Celery send queue with delivery status; per-tenant settings and throttling.

*Verify locally:* generate a birthday poster batch for this week's birthdays and send one via click-to-chat; if API credentials are configured, send one through the API and confirm delivery status.

### Phase 6 — Quotations, Loans and Reports

- Insurance quotation (multi-insurer comparison PDF, WhatsApp send, convert to policy).
- Loans module and payout report.
- Full insurance report suite with CSV/PDF export.
- Global search extended to customers, policies, quotations, loans.

### Phase 7 — Hardening and deployment

- Security review of tenant isolation and PII paths; Redis-backed rate limiting; signed download URLs.
- Performance: indexes for renewal/birthday/expiry queries, JSONB GIN indexes, query profiling at 10k+ policies per tenant.
- Backup/restore and per-tenant export; tenant deletion purge job.
- **Automated test suite** — the repo currently has none (see `CLAUDE.md`); Phase 0's isolation tests are the seed, and this phase brings coverage to the critical paths: auth, RBAC, tenant isolation, encryption, billing maths, renewal transitions.
- Docker Compose and Nginx updates; runbook.

### Sequencing note

Phases 0–2 are platform work with no visible insurance features. That is deliberate — retrofitting tenant
isolation and dynamic fields **after** building the insurance modules would mean touching every new file a
second time. Phase 3 is where the insurance product starts to look real.

---

## 12. Later candidates

Claims tracking and settlement follow-up; sub-agent/POSP hierarchy with commission splits; customer
self-service portal (policy documents, renewal payment); payment gateway for renewal collection; insurer
API integrations for real-time quotes; motor RTO zone premium calculation (D4); OCR extraction from
uploaded RC/policy PDFs; IRDAI-format reporting; mobile app; per-tenant subdomains and custom domains;
usage-based billing for the platform itself.

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Tenant | One client account — an agency or an individual agent — with its own isolated data |
| Template | A versioned configuration bundle that shapes a new tenant's CRM |
| Book premium | Total gross premium of all in-force policies |
| IDV | Insured Declared Value — the sum insured for a motor own-damage cover |
| NCB | No Claim Bonus — renewal discount for a claim-free year |
| OD / TP | Own Damage / Third Party — the two components of a motor premium |
| POSP | Point of Sales Person — a registered sub-agent |
| Blind index | A keyed hash of a value, stored alongside its ciphertext to allow exact-match search without decryption |
| Bancassurance | Insurance sourced through a bank channel |
