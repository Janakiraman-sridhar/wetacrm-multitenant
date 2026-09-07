# WeTa CRM — Phase-by-Phase Implementation Plan

Companion to [`INSURANCE_CRM_PRD.md`](INSURANCE_CRM_PRD.md). That document says *what* to build and *why*;
this one says *what to do, in what order, in which files*.

**Sizing.** `S` ≈ half a day, `M` ≈ 1–2 days, `L` ≈ 3–5 days, `XL` ≈ a week or more — for one developer
working with Claude Code, including local testing but **not** including review cycles or scope changes.
Phase totals assume tasks run in the listed order; several are parallelisable if more than one person works.

**Ordering.** Phases 0–2 are platform plumbing with no visible insurance features. This is deliberate:
retrofitting `tenant_id` and dynamic fields after the insurance modules exist means touching every new
file a second time. If you would rather demo something in week one, say so — the alternative is to build
Phase 3–4 single-tenant first and retrofit, which costs roughly 30–40% more total work but gives you
clickable insurance screens far sooner.

| Phase | Theme | Size |
|---|---|---|
| 0 | Multi-tenant foundation | XL (~8–10 days) |
| 1 | Templates, provisioning, Super Admin console | L (~5–6 days) |
| 2 | Custom fields engine | L (~5–6 days) |
| 3 | Customers and PII | L (~5–7 days) |
| 4 | Policies, renewals, insurance dashboard | XL (~7–9 days) |
| 5 | WhatsApp and Poster Studio | L (~5–7 days) |
| 6 | Quotations, Loans, Reports | M (~4–5 days) |
| 7 | Hardening, tests, deployment | M (~4–5 days) |

---

## Phase 0 — Multi-tenant foundation ✅ COMPLETE

*Delivered. 82 isolation tests pass; the Default workspace keeps its original data; new tenants can
be provisioned through `POST /api/v1/platform/tenants`. Two things came out differently from the
plan and are worth knowing:*

- *`with_loader_criteria` does not reach `select(func.count())`, so `paginate()` was returning the
  right rows with a cross-tenant total. Fixed in `scope_to_tenant()` plus `_augment_aggregate`.*
- *`seed.run()` created the default admin per tenant, which collides with the global-unique
  `users.email`. Owner creation moved to `provision_tenant()`.*

**Goal.** Two tenants can coexist in one database with provably zero data bleed, and the existing app
still works unchanged for the migrated "Default" tenant.

**Definition of done.** The isolation test suite (0.10) passes, and a manual pass through every module as
Tenant A shows none of Tenant B's data anywhere — lists, detail views, search, drilldowns, CSV export,
file downloads, notifications.

| # | Task | Files | Size |
|---|---|---|---|
| 0.1 | **Alembic baseline.** Generate the first migration from current models. Stop calling `Base.metadata.create_all()` and `ensure_columns()` in the lifespan; run `alembic upgrade head` at startup in Docker and document it for dev. Delete `ensure_schema.py`. | `migrations/versions/0001_baseline.py`, `app/main.py`, `app/database/ensure_schema.py` (delete), `backend/Dockerfile` | M |
| 0.2 | **Dev dependencies.** Add `pytest`, `pytest-asyncio`, `httpx` (TestClient needs it) and `cryptography` to a new `requirements-dev.txt` / extend `requirements.txt`. | `backend/requirements.txt`, `backend/requirements-dev.txt` | S |
| 0.3 | **Tenant model.** New `app/platform/` package. `Tenant`: id, name, slug (unique), type, status, template_key, plan, timezone, currency, locale, `dek_encrypted`, `settings` JSON, owner_user_id, created_at, deleted_at. Plus `PlatformAuditLog`. Register in `models_registry.py`. | `app/platform/{__init__,models,schemas}.py`, `app/models_registry.py` | M |
| 0.4 | **`TenantScoped` mixin** adding indexed `tenant_id` FK. Apply to every business model (companies, contacts, leads, deals, deal_stages, lead_sources, activities, audit_logs, comments, tasks, meetings, calendar_events, products, quotations, quotation_items, invoices, invoice_items, projects, project_tasks, documents, tickets, notifications, settings, email_templates, tags, users). | `app/database/base.py`, every `app/*/models.py` | M |
| 0.5 | **Schema migration.** Add `tenant_id` to all tables (nullable), create the Default tenant, backfill every row, set NOT NULL. Rewrite unique constraints as composite — see PRD §4.2 (`settings.key`, `email_templates.name`, `deal_stages.name`, `tags.name`, `lead_sources.name`, quotation/invoice numbers). | `migrations/versions/0002_multitenant.py` | L |
| 0.6 | **Tenant context.** `ContextVar` holding the active tenant; `current_tenant_id()`; `tenant_scope(tenant_id)` context manager for background jobs; an explicit `platform_scope()` escape hatch for cross-tenant queries. | `app/core/tenancy.py` (new) | M |
| 0.7 | **Global query filter.** A `do_orm_execute` event that injects `with_loader_criteria(TenantScoped, …)` into every ORM statement including relationship loads, and a `before_flush` hook that stamps `tenant_id` on new objects. Raise `TenantContextMissing` if a scoped query runs with no context outside `platform_scope()`. **This is the security boundary — no router should ever filter by tenant by hand.** | `app/core/tenancy.py`, `app/database/session.py` | L |
| 0.8 | **Auth.** `users.tenant_id` (nullable) and `users.is_platform_admin`. Add a `tid` claim in `_create_token`; set the tenant context in `get_current_user`; reject logins for suspended tenants. | `app/core/security.py`, `app/core/deps.py`, `app/auth/router.py`, `app/users/models.py` | M |
| 0.9 | **Infrastructure scoping.** Storage keys prefixed `tenants/<id>/` with prefix verification on download; `tenant_id` as a Meilisearch filterable attribute and applied to every query; Socket.IO rooms `tenant:<tid>:user:<uid>`; rate-limit key includes tenant; every Celery beat job iterates active tenants inside `tenant_scope()`. | `app/services/{storage,search_client,search_sync}.py`, `app/search/router.py`, `app/notifications/socket.py`, `app/core/rate_limit.py`, `app/automation/tasks.py` | L |
| 0.10 | **Isolation test suite.** pytest fixtures creating two tenants with overlapping data, then a parametrised test per module asserting Tenant A's token gets 404/403 — never data — for every list, detail, update, delete, export, template, import, search, drilldown and file-download endpoint. | `backend/tests/conftest.py`, `backend/tests/test_tenant_isolation.py` | L |
| 0.11 | **Platform auth.** Platform admin login and console session. *Impersonation was built here and later removed — see the Phase 6 notes; a platform admin has no route into tenant data.* | `app/platform/router.py`, `app/core/security.py` | M |

**Risks.** 0.7 is where a subtle miss becomes a data leak — budget time for it and do not shortcut 0.10.
0.5 is a destructive migration; take a database backup first and test the rollback path.

**Verify locally.** Run the migration against a copy of `backend/weta_crm_dev.db`; confirm all existing
data lands in the Default tenant and the app behaves exactly as it does today. Then create a second tenant
via a script, add records to both, and try to reach one from the other's session.

---

## Phase 1 — Templates, provisioning and Super Admin console ✅ COMPLETE

*Delivered. 99 tests pass. Creating a tenant from `insurance_agent` really does produce a
different CRM — sidebar reads Customers / Enquiries / Opportunities, pipeline runs New
enquiry → Policy issued — while a `general_crm` tenant is unchanged from the original app.
Notes:*

- *`general_crm.json` was generated from the original seed constants rather than written by
  hand, so it reproduces the old behaviour exactly. `app/database/seed.py` is now deleted.*
- *`Setting.value` is typed as a dict everywhere, so a bare string setting fails response
  validation — the Vahan URL had to be nested.*
- *Test fixtures now build tenants through `apply_template()` instead of hand-rolling roles
  and stages, so they exercise the real provisioning path.*

**Goal.** You can create a client from the platform console, pick General CRM or Insurance Agent, and they
get a working, correctly-configured CRM.

**Definition of done.** A tenant created from `general_crm` is indistinguishable from today's app; a tenant
created from `insurance_agent` shows the insurance sidebar with renamed modules.

| # | Task | Files | Size |
|---|---|---|---|
| 1.1 | **Template schema and loader.** Define and document the template JSON structure (PRD §6.1); loader with validation and versioning. | `app/platform/template_schema.py`, `app/platform/service.py` | M |
| 1.2 | **Seed the two system templates.** `general_crm.json` mirrors today's modules, roles, stages, sources and email templates exactly. `insurance_agent.json` per PRD §6.2 including insurer/bank/relation masters. | `app/platform/templates/{general_crm,insurance_agent}.json` | M |
| 1.3 | **`provision_tenant()`.** Replaces the global `seed.run()`: creates roles, module config, stages, masters, settings, email templates, poster templates and the owner user in one idempotent transaction. Refactor `app/database/seed.py` into it. | `app/platform/service.py`, `app/database/seed.py` | L |
| 1.4 | **Module config.** `tenant_modules` (tenant_id, module_key, enabled, label, order) driving what the tenant can see. API endpoint returning the current tenant's module config. | `app/platform/models.py`, `app/settings/router.py` | M |
| 1.5 | **Platform API.** Tenants list/create/detail/update/suspend/reactivate/soft-delete; template list and clone; platform dashboard metrics. All behind `is_platform_admin`. | `app/platform/router.py`, `app/main.py` | L |
| 1.6 | **Platform console UI.** A separate React shell at `/platform` with its own layout: tenant table, create-tenant wizard (details → template → owner → confirm), tenant detail page (owner, users, modules, record counts), template manager with create/edit/delete. | `frontend/src/platform/**` (new), `frontend/src/App.tsx` | L |
| 1.7 | **Tenant app respects module config.** `AppLayout`'s hardcoded `NAV` array becomes API-driven (labels and order included); routes 404 for disabled modules; `useAuth` exposes module config alongside permissions. | `frontend/src/layouts/AppLayout.tsx`, `frontend/src/App.tsx`, `frontend/src/context/AuthContext.tsx` | M |
| 1.8 | **Migrate the Default tenant** onto the `general_crm` template so it is a normal tenant like any other. | `migrations/versions/0003_default_tenant_template.py` | S |

**Verify locally.** Create one tenant of each template; log in to both; confirm sidebars, stages, roles and
email templates differ correctly and neither sees the other's data.

---

## Phase 2 — Custom fields engine ✅ COMPLETE

*Delivered. 129 tests pass. A tenant can add fields to eight modules, rename or hide the
built-in ones, and have all of it flow through form, record, table, filter and CSV export
— invisible to every other tenant. Notes:*

- *Base fields are derived from the models rather than hand-listed, so the field editor
  cannot drift out of step with the schema.*
- *`cast(custom['k'], String)` keeps the JSON quotes, so dropdown and number filters
  matched nothing while the text filter matched through the quotes and hid it. Only the
  live check caught it; `.as_string()` / `.as_float()` fixed it and there is now a test.*
- *Pydantic silently strips undeclared keys, so `custom` had to be added to the
  Create/Update/Out schemas of all eight modules.*
- *The plan's task 2.6 assumed replacing every page's hardcoded arrays. Layering the
  tenant's overrides on top of them instead achieves the same result and leaves the pages
  almost untouched.*

**Goal.** You can add, relabel, reorder and remove fields per client without touching code.

**Definition of done.** A custom field added to Customers for Tenant A appears in that tenant's form, table
views, filter panel and CSV export — and is invisible to Tenant B.

| # | Task | Files | Size |
|---|---|---|---|
| 2.1 | **`custom_field_defs` model** per PRD §7.1, plus migration. | `app/platform/models.py`, `migrations/versions/0004_custom_fields.py` | M |
| 2.2 | **`custom` JSON column** on every customisable entity; JSONB + GIN index on Postgres, plain JSON on SQLite. | every `app/*/models.py`, migration | M |
| 2.3 | **Base field catalog.** Declare server-side what each module's base fields are — today this only exists as hardcoded arrays inside the React pages. This becomes the thing custom fields merge over. | `app/schema_registry.py` (new) | L |
| 2.4 | **`GET /api/v1/schema/{module}`** returning merged base + custom fields, labels, sections, order, table columns, filterable fields and stages for the current tenant. Cached per tenant, invalidated on field edit. | `app/settings/router.py` or new `app/schema/router.py` | M |
| 2.5 | **Dynamic validation.** Build a Pydantic model per module per tenant from the merged definitions so custom fields validate as strictly as base ones; cache and invalidate with 2.4. | `app/core/dynamic_schema.py` (new) | L |
| 2.6 | **`CrudPage` consumes the schema endpoint.** `fields`, `columns`, `allColumns` and `filterFields` come from the API, with the current hardcoded page arrays kept as the base declaration. This is the highest-leverage frontend change in the project — the existing config-driven design means the pages themselves barely change. | `frontend/src/components/CrudPage.tsx`, `frontend/src/lib/schema.ts` (new), all `frontend/src/pages/*.tsx` | L |
| 2.7 | **Field editor UI.** Per-module field list with add/edit/reorder (drag), type picker, options editor, required and section settings, show-in-table and filterable toggles, locked-field indicators. Available to platform admin (any tenant) and tenant admin (own). | `frontend/src/platform/FieldEditor.tsx`, `frontend/src/pages/SettingsPage.tsx` | L |
| 2.8 | **Dynamic filtering and CSV I/O.** Extend `app/filtering.py` to map a filterable custom field to a JSON-path condition, and the `IOSpec` registry to include custom columns in export, template and import. | `app/filtering.py`, `app/io/{registry,spec}.py` | M |

**Risks.** 2.3 and 2.6 together are the biggest refactor in the project — every list page changes. Do one
module end-to-end (Companies) and prove it before converting the rest.

---

## Phase 3 — Customers and PII ✅ COMPLETE

*Delivered. 159 tests pass. PAN and Aadhaar are ciphertext in the database, masked in
every response, and revealable only with a separate permission and an audit row. Notes:*

- *Customer fields live on `contacts` rather than a new table — an insurance tenant's
  "Customer" is the CRM's contact, relabelled by its template. A separate table would
  fork every relationship, filter, export and search path.*
- *Aadhaar full capture is off by default (PRD 9.4); only last-4 is kept unless a
  workspace opts in. The reveal endpoint explains this rather than 404-ing.*
- *Test fixtures create tenants directly and so had no data key — provisioning mints
  one, and `ensure_tenant_keys()` backfills tenants created before this phase.*

**Goal.** The insurance customer record exists, complete, with PAN and Aadhaar encrypted, masked and
audit-logged on reveal.

**Definition of done.** Create a customer with PAN and Aadhaar; inspect the database directly and see
ciphertext; see masked values in the UI; reveal one and find the reveal in the audit log.

| # | Task | Files | Size |
|---|---|---|---|
| 3.1 | **Crypto service.** AES-256-GCM envelope encryption; platform master key from `PII_MASTER_KEY`; per-tenant DEK generated at provisioning and stored wrapped in `tenants.dek_encrypted`; `EncryptedString` SQLAlchemy `TypeDecorator`; HMAC-SHA256 blind-index helper. | `app/services/crypto.py` (new), `app/platform/service.py` | L |
| 3.2 | **Customer model.** Extend `contacts` with the insurance base fields (DOB, gender, marital status, alt mobile, alt email, pincode/city/state, occupation, annual income, PAN + `pan_bidx`, Aadhaar + `aadhaar_bidx`, `aadhaar_last4`, stage, referred-by block, products of interest). All nullable and hidden unless the template enables them, so the General CRM tenant is unaffected. | `app/contacts/{models,schemas,router}.py`, migration | L |
| 3.3 | **Nominee.** `nominees` table linked to customer and (Phase 4) policy: name, age, DOB, relation, share %, appointee name/relation. Share validation totalling 100%. | `app/contacts/models.py`, new `app/nominees/` or inline | M |
| 3.4 | **Notes and attachments in the form.** Repeatable notes (body, author, timestamp, pin) and multi-file upload with category, both saved inside the customer create/edit transaction. | `app/activities/models.py`, `app/documents/router.py`, `frontend/src/components/CrudPage.tsx`, `frontend/src/components/NotesField.tsx` (new), `AttachmentsField.tsx` (new) | L |
| 3.5 | **Masking and reveal.** Masked-by-default serialisation; `POST /customers/{id}/reveal`; new `customers:reveal_pii` permission; per-user rate limit; audit row per reveal; 30-second auto-remask in the UI; a "PII access" report for tenant admins. | `app/contacts/{schemas,router}.py`, `app/core/permissions.py`, `frontend/src/components/MaskedField.tsx` (new) | M |
| 3.6 | **Pincode dataset.** Bundle an offline India pincode → city/state dataset; lookup endpoint; auto-fill on the form. Plus the tenant-maintained `insurer_serviceability` table that filters insurer/product options by pincode. | `app/reference/pincodes.py` + data file, `app/platform/models.py` | M |
| 3.7 | **Validation.** PAN regex `[A-Z]{5}[0-9]{4}[A-Z]` with uppercasing; Aadhaar 12-digit **Verhoeff checksum**; E.164 mobile normalisation with a per-tenant default country code. | `app/core/validators.py` (new) | M |
| 3.8 | **Customer stages.** Per-tenant configurable lifecycle stages; stepper on the detail view; every change written to the timeline. | `app/platform/models.py`, `frontend/src/components/StageStepper.tsx` (new) | M |
| 3.9 | **Timeline tab.** Merge `activities` and `audit_logs` into one chronological feed with human-readable field-change rendering, filterable by type and date. | `app/activities/router.py`, `frontend/src/components/Timeline.tsx` (new) | M |
| 3.10 | **`<CustomerChip>`** — avatar, name, mobile, WhatsApp icon, click-through. Rolled out to pipeline cards, task rows, calendar items, notifications and search results. Mobile added to every module's `allColumns`. | `frontend/src/components/CustomerChip.tsx` (new), consuming pages | M |
| 3.11 | **Birthdays.** Day-and-month index on DOB; birthday query endpoint; Today / Tomorrow / This week / This month panel in Customers and on the Dashboard; daily job creating birthday tasks. | `app/contacts/router.py`, `app/automation/tasks.py`, `frontend/src/components/BirthdayPanel.tsx` (new) | M |

**Risks.** 3.1 must be right the first time — data encrypted with a broken scheme is hard to fix later.
Write the key-rotation and re-encryption procedure as part of this task, not afterwards.

---

## Phase 4 — Policies, renewals and the insurance dashboard ✅ COMPLETE

*Delivered. 180 tests pass. Verified live end to end: issue a motor and a health policy,
watch status derive from the expiry date, renew one and see the chain preserved and the
policy drop off the renewal desk. Notes:*

- *Premium schema fields default to `None`, not `0` — with a `0` default, `compute_premium`
  could not tell "gross not supplied" from "gross is zero" and never derived it.*
- *A master in use is deactivated rather than deleted, so historical policies keep the
  insurer they were written with. Test fixtures have to allow for that.*
- *Bumping a system template does not change existing tenants — that is the design. The
  live tenant was brought up to date with `POST /platform/tenants/{id}/apply-template`,
  which is exactly what that endpoint exists for.*

**Goal.** The book of business exists and drives daily work.

**Definition of done.** Policies across motor, health and life; expiry dates near today; the nightly job
transitions statuses and creates renewal tasks; the dashboard KPIs are correct and the privacy toggle hides
them.

| # | Task | Files | Size |
|---|---|---|---|
| 4.1 | **Masters.** Insurers, product types, plans, banks (bancassurance sources), branches, relations — tenant-scoped, template-seeded, admin-editable. | `app/platform/models.py`, `app/settings/router.py` | M |
| 4.2 | **Policy model.** Common columns per PRD §8.2, plus a `details` JSON for line-specific fields. Promote the high-value ones to real indexed columns because they are filtered and reported on constantly: `registration_no`, `sum_insured`, `idv`, `expiry_date`, `insurer_id`, `bank_id`, `product_type`, `status`. | `app/policies/{__init__,models,schemas}.py` (new), migration | L |
| 4.3 | **Policy router.** Full CRUD following the conventions in `CLAUDE.md`; conditional line-specific field groups; `FILTERS["policies"]` covering insurer, bank, product type, status, expiry range, issue range, agent, branch, channel, premium range, city/pincode, renewal window; `IOSpec` for CSV import/export. | `app/policies/router.py`, `app/filtering.py`, `app/io/registry.py`, `app/main.py` | L |
| 4.4 | **Status lifecycle job.** Nightly transition `active → expiring → lapsed`; renewal detection; idempotent and tenant-iterating. | `app/automation/tasks.py` | M |
| 4.5 | **Renewal flow.** "Renew" creates a **new** policy row linked to the previous via `renewal_of` / `renewed_to`, pre-filled and editable; the old policy becomes `renewed`. Renewal history visible on both. | `app/policies/router.py`, `frontend/src/pages/Policies.tsx` | M |
| 4.6 | **Renewal task automation** at 60/30/15/7/1 days before expiry, thresholds configurable per tenant, with de-duplication so a restart does not spam. | `app/automation/tasks.py` | M |
| 4.7 | **Insurance dashboard API.** KPIs (customers, active policies, book premium, renewals in 7/30/60 days, new business MTD, lapsed, birthdays this week) and chart series (premium by month new vs renewal, by insurer, by product, renewal funnel, conversion). Extend the existing drilldown endpoint for each. | `app/reports/router.py` | L |
| 4.8 | **Dashboard UI + privacy toggle.** KPI strip with a single eye icon blurring all values at once; state persisted as a user preference and mirrored to `localStorage` to avoid a flash of visible values on load; charts; renewal, task and birthday panels; click-through everywhere. | `frontend/src/pages/Dashboard.tsx`, `frontend/src/context/AuthContext.tsx` | L |
| 4.9 | **Enquiry pipeline.** Insurance stages seeded from the template; cards showing customer chip + product + expected premium + target date; "Policy issued" prompts to create the policy carrying enquiry data over — mirroring the existing lead→deal conversion in `app/leads/router.py`. | `app/deals/router.py`, `frontend/src/pages/Pipeline.tsx` | M |
| 4.10 | **Vahan button.** Top-bar button (insurance template only) opening the Vahan portal in a new tab; copies the registration number to the clipboard with a toast when a motor policy is in context; URL held in tenant settings. | `frontend/src/layouts/AppLayout.tsx` | S |

---

## Phase 5 — WhatsApp and Poster Studio ✅ COMPLETE

*Delivered. 212 tests pass. Verified by generating real posters and looking at them —
which is how both output bugs were found. Notes:*

- *Rendering is server-side (Pillow) rather than the planned client-side fabric.js, so
  one renderer serves the preview, the batch and the send. A client-side preview would
  drift from the file the customer receives.*
- *A merge field resolving to empty left a button reading just "Call". Fixed with
  `is_hollow()`; the empty background pill that remained needed `"requires"` on the
  layer as well. Neither showed up in a test — only in the rendered image.*
- *5.6–5.8 (Cloud API, message log, queue) are built and unit-tested behind the
  provider interface, but cannot be verified end to end without a verified Meta
  Business account. Click-to-chat needs none and is fully working.*

**Goal.** The agent can reach customers, with branded creatives.

| # | Task | Files | Size |
|---|---|---|---|
| 5.1 | **Click-to-chat everywhere.** `wa.me` helper with E.164 normalisation and per-context prefilled message templates (renewal, birthday, quote follow-up, document request), editable per tenant. Wired into `<CustomerChip>`, customer detail, policy rows, task rows, renewal panel. | `frontend/src/lib/whatsapp.ts` (new), consuming components | M |
| 5.2 | **Poster template model + gallery.** Tenant-scoped poster templates seeded from the tenant template; categories (birthday, renewal, issued, festival, promo). | `app/poster/{models,schemas,router}.py` (new) | M |
| 5.3 | **Canvas editor.** fabric.js editor: text and image layers, drag/resize/rotate, brand colours and fonts, agent photo and contact strip, background upload or pick, layer order, undo/redo. | `frontend/src/pages/PosterStudio.tsx` (new), `frontend/src/components/poster/**` | XL |
| 5.4 | **Merge fields.** `{customer_name}`, `{policy_number}`, `{insurer}`, `{expiry_date}`, `{days_to_expiry}`, `{premium}`, `{vehicle_no}`, `{agent_name}`, `{agent_mobile}`, `{agency_name}` — resolved server-side for batches, client-side for live preview. | `app/poster/service.py`, `frontend/src/components/poster/merge.ts` | M |
| 5.5 | **Batch generation.** Pick an audience (today's birthdays, renewals in N days, a saved policy filter, manual selection) → render one personalised PNG per recipient → preview grid → download or send. 1080×1080 and 1080×1920 outputs, stored under the tenant prefix with 90-day retention. | `app/poster/router.py`, `app/automation/tasks.py` | L |
| 5.6 | **`WhatsAppProvider` interface** with a Meta Cloud API implementation — text, template and media messages; tenant settings for phone number id, token and template mapping; nothing provider-specific leaks past the interface so a BSP can be swapped in. | `app/services/whatsapp/{base,meta_cloud}.py` (new) | L |
| 5.7 | **Message log + delivery status.** `whatsapp_messages` table (recipient, template, payload, provider message id, status, error); webhook endpoint for status callbacks; UI showing sent/delivered/read/failed. | `app/services/whatsapp/models.py`, `app/notifications/router.py` | M |
| 5.8 | **Send queue.** Celery tasks with per-tenant throttling, retry with backoff, and 24-hour session-window handling (approved templates for first contact). | `app/automation/tasks.py` | M |

**Dependency.** 5.6–5.8 need a verified Meta Business account, a dedicated number and approved templates.
Start that application at the beginning of Phase 4 — approval can take one to three weeks and it is the
most common thing to block a launch. 5.1–5.5 have no external dependency and ship regardless.

---

## Phase 6 — Quotations, Loans and Reports ✅ COMPLETE

| # | Task | Files | Size |
|---|---|---|---|
| 6.1 | **Insurance quotation.** Quote lines become plan options; side-by-side comparison of 2–4 insurer quotes on one branded PDF (insurer, plan, sum insured/IDV, premium breakup, key inclusions/exclusions). | `app/quotations/{models,schemas,router}.py`, `app/services/pdf.py` | L |
| 6.2 | **Convert to Policy** replacing convert-to-invoice for insurance tenants; send quote by email and WhatsApp. | `app/quotations/router.py` | M |
| 6.3 | **Loans module.** Model, CRUD, Kanban (`enquiry → documents → logged in → sanctioned → disbursed \| rejected`), payout tracking, filters, CSV I/O. | `app/loans/**` (new) | L |
| 6.4 | **Report suite.** Renewal register, production/premium by month-insurer-product-bank-agent, commission (earned/received/pending), lapse and retention, customer growth, birthday list, cross-sell opportunities, loan payouts, agent leaderboard. CSV and PDF export. | `app/reports/router.py`, `frontend/src/pages/Reports.tsx` | L |
| 6.5 | **Global search extended** to customers, policies, quotations and loans; tenant-filtered; PAN searchable by blind index (exact match only). | `app/search/router.py`, `app/services/search_sync.py` | M |

**What differed, and why.**

- **6.1** The plan said "quote lines become plan options". They did not: the options live in
  their own `insurance` JSON column, because `quotation_items` exist to be *summed* and
  competing insurer quotes must never be. An insurance quotation's total is the **selected**
  option — three insurers at ₹12k/₹14k/₹16.5k is a ₹12k–₹16.5k decision, not a ₹42.5k sale.
- **6.1** The comparison is a separate renderer (`app/quotations/comparison_pdf.py`), not a mode
  of `document_pdf`. One prints line items down the page and sums them; the other puts insurers
  across a landscape page and sums nothing. Bending one function into both would have meant a
  suppressed totals block and a transposed layout.
- **6.2** Convert-to-policy is an addition, not a replacement: `POST /quotations/{id}/convert`
  still makes an invoice for a standard quotation, and refuses an insurance one with an
  explanation. A tenant running both keeps both.
- **6.4** Insurance reports live beside the sales templates on the same Reports page, switched
  by a Sales/Insurance toggle that defaults to Insurance for any workspace with a policy book.
- **Unplanned, found while verifying.** A module a tenant had switched off was still reachable
  over the API — "disabled" meant *hidden from the sidebar*, nothing more. `require_perm` now
  refuses a permission whose module is off, `require_module` gates the Poster Studio (which is
  permissioned on `contacts:read` and so cannot be gated by its permission alone), search drops
  groups for modules a workspace does not have, and `backfill_new_modules()` gives existing
  tenants a row for modules added to the catalog after they were provisioned.
- **PDF/CSV** export shipped; PDF export of the *reports* did not — the two reports worth
  printing are call lists, and CSV is what an agency actually takes into a day of calls.
- **Not done:** 6.2's "send quote by WhatsApp" from the quotation row. The comparison sheet is a
  PDF, and click-to-chat cannot attach a file — it needs the Cloud API media send from 5.6.

**Console changes made after Phase 6, from testing the console itself.**

- **Impersonation removed.** A platform admin can no longer open a client's workspace: the
  endpoint is gone, `_create_token` cannot express an `imp` claim, and `get_current_user`
  refuses any token whose tenant is not the user's own. A support session that can read every
  customer's PAN and Aadhaar is a standing breach waiting for one compromised admin account,
  and an audit trail only tells you afterwards. The tenant page grew the details that made
  "go inside and look" tempting: owner, users, roles, last sign-in, module configuration and
  per-module record counts.
- **A platform admin now gets 403, not 500,** on endpoints guarded only by `get_current_user`.
  The tenant-scoped query was raising `TenantContextMissing`, which is correct behaviour
  surfacing as a crash.
- **Templates can be created and deleted from the console,** not only cloned. A new template
  always starts from an existing one, because an empty one provisions a workspace with no
  roles and no pipeline — broken in a way nobody notices until its owner cannot sign in.
  Deleting now asks first; it used to fire on a single click.
- **Deleting a tenant releases its email addresses.** `users.email` is globally unique, so a
  soft-deleted tenant held its owner's address for the entire retention window — meaning the
  commonest console mistake, deleting a client and adding them back, was impossible to undo.

---

## Phase 7 — Hardening, tests and deployment 🚧 IN PROGRESS

| # | Task | Files | Size |
|---|---|---|---|
| 7.1 | **Security review.** Re-audit every tenant-isolation path and every PII path; confirm no encrypted value reaches logs, search, exports or error messages. | — | M |
| 7.2 | **Redis rate limiting.** Replace the in-memory limiter so it survives multiple workers. | `app/core/rate_limit.py` | S |
| 7.3 | **Signed download URLs** with expiry for all attachments; MIME sniffing and size caps on upload. | `app/documents/router.py`, `app/services/storage.py` | M |
| 7.4 | **Performance.** Indexes for expiry, DOB day-month, renewal windows and JSONB custom fields; profile lists and dashboards at 10k+ policies per tenant; fix N+1 loads. | migrations, routers | M |
| 7.5 | **Test coverage** beyond Phase 0's isolation suite: auth and refresh, RBAC, encryption round-trip and masking, billing maths, renewal transitions, provisioning idempotency, CSV import/export. | `backend/tests/**` | L |
| 7.6 | ✅ **Purge and restore.** 30-day soft-delete purge (rows, files and search index), a console list of what is in the window, purge-now with the slug typed, and a documented backup/restore procedure. *Per-tenant data export still to do.* | `app/platform/purge.py`, `app/automation/tasks.py`, `docs/DEPLOY.md` | M |
| 7.7 | ✅ **Deployment.** `PII_MASTER_KEY` plumbed through both compose files; compose now *refuses to start* without it, `JWT_SECRET` or `ADMIN_PASSWORD` rather than falling back to a placeholder; `.env.example` ships blanks and generation instructions; runbook in `docs/DEPLOY.md`. | `docker-compose*.yml`, `docker/.env.example`, `docs/DEPLOY.md` | M |

**Done first, and why.** 7.7 and 7.6 were pulled to the front of the phase because they
were the two things actually blocking a deployment. `PII_MASTER_KEY` was enforced by the
application, passed by neither compose file and mentioned in no example — a fresh
`docker compose up` crashed at boot with nothing to explain why. And the delete screen
promised a 30-day purge that nothing performed, which is a promise made to whoever clicks
delete *and* to whoever asks what happens to their data.

---

## Cross-cutting notes

**Do not skip Phase 0.10.** Tenant isolation is the one defect class where a single missed filter exposes
one client's customer PII to another. It is also the one thing that is nearly impossible to retrofit
confidence into later.

**Keep the General CRM tenant green.** After every phase, run through a `general_crm` tenant and confirm
nothing regressed. It is the cheapest regression signal you have.

**Start the WhatsApp Business application early** (see Phase 5) — external approval is the most likely
cause of a slipped launch date.

**Reference data you need to source** before the phase that consumes it: India pincode → city/state
dataset (Phase 3.6), insurer and product master list for your actual panel (Phase 4.1), and later, if you
enable it, a pincode → RTO zone table.
