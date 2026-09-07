# CRM templates

Each JSON file here is a **system template** — the recipe a tenant's CRM is built
from. `app/platform/provisioning.py` loads them at startup into the `crm_templates`
table, and copies one into a tenant when it is provisioned.

| File | What it makes |
|---|---|
| `general_crm.json` | The full-purpose CRM the product shipped with. This is the regression baseline: a tenant created from it must behave exactly like the pre-template app. |
| `insurance_agent.json` | An insurance agency workspace — Contacts renamed to Customers, an enquiry-to-policy pipeline, insurer/bank/relation masters, renewal and birthday email templates. |

## Editing

- Bump `version` when you change a file. `sync_system_templates()` only refreshes a stored system template when the file's version is **higher** than the stored one.
- Templates are **copied into a tenant at provisioning**, never referenced live. Editing a file therefore does not change any existing tenant — that needs a deliberate re-apply.
- `parse_template()` validates on load: every `modules[].key` must exist in `app/platform/catalog.py`, and every role permission must exist in `app/core/permissions.py`. A typo fails fast rather than producing a subtly broken tenant.
- Modules marked `locked` in the catalog (dashboard, settings) stay enabled whatever the template says.

## Adding a vertical

Add a JSON file, add its key to `SYSTEM_TEMPLATE_KEYS` in `provisioning.py`. No other
code changes — that is the point of the templates.

`general_crm.json` was generated from the original seed constants rather than written
by hand, so it matches the old behaviour exactly.
