"""The canonical list of modules a tenant's CRM can be built from.

A template (see `template_schema.py`) picks which of these are enabled and what
they are called for that tenant — this is how the same codebase presents
"Contacts" to a general CRM and "Customers" to an insurance agent.

`key` is stable and is what code, permissions and routes use. `label` is only ever
a display string, so renaming a module for one client changes nothing else.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDef:
    key: str
    label: str          # default display name
    order: int
    route: str          # frontend path
    icon: str           # lucide-react icon name
    permission: str | None  # permission gating visibility; None = always visible
    locked: bool = False    # cannot be disabled by a template or tenant admin


MODULE_CATALOG: list[ModuleDef] = [
    ModuleDef("dashboard",  "Dashboard",  1,  "/",           "LayoutDashboard", None,               locked=True),
    ModuleDef("companies",  "Companies",  2,  "/companies",  "Building2",       "companies:read"),
    ModuleDef("contacts",   "Contacts",   3,  "/contacts",   "UsersRound",      "contacts:read"),
    ModuleDef("leads",      "Leads",      4,  "/leads",      "Target",          "leads:read"),
    ModuleDef("deals",      "Deals",      5,  "/deals",      "Handshake",       "deals:read"),
    ModuleDef("policies",   "Policies",   6,  "/policies",   "ShieldCheck",     "policies:read"),
    ModuleDef("pipeline",   "Pipeline",   7,  "/pipeline",   "SquareKanban",    "deals:read"),
    ModuleDef("calendar",   "Calendar",   8,  "/calendar",   "Calendar",        "calendar:read"),
    ModuleDef("tasks",      "Tasks",      9,  "/tasks",      "ListTodo",        "tasks:read"),
    ModuleDef("projects",   "Projects",   10,  "/projects",   "FolderKanban",    "projects:read"),
    ModuleDef("products",   "Products",   11, "/products",   "Package",         "products:read"),
    ModuleDef("quotations", "Quotations", 12, "/quotations", "FileText",        "quotations:read"),
    ModuleDef("invoices",   "Invoices",   13, "/invoices",   "Receipt",         "invoices:read"),
    ModuleDef("support",    "Support",    14, "/support",    "LifeBuoy",        "support:read"),
    ModuleDef("reports",    "Reports",    15, "/reports",    "ChartColumnBig",  "reports:read"),
    ModuleDef("settings",   "Settings",   16, "/settings",   "Settings",        "settings:read", locked=True),
]

MODULES_BY_KEY = {m.key: m for m in MODULE_CATALOG}
MODULE_KEYS = [m.key for m in MODULE_CATALOG]


def module_or_none(key: str) -> ModuleDef | None:
    return MODULES_BY_KEY.get(key)
