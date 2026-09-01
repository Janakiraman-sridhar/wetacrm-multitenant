"""Central permission registry. A permission is "<module>:<action>".

A role's `permissions` column stores a JSON list of these strings; "*" grants everything.
"""

MODULES = [
    "users", "roles", "companies", "contacts", "leads", "deals", "activities",
    "tasks", "calendar", "products", "quotations", "invoices", "projects",
    "support", "documents", "reports", "settings",
]

ACTIONS = ["read", "write", "delete"]

ALL_PERMISSIONS = [f"{m}:{a}" for m in MODULES for a in ACTIONS]


def _grant(modules: list[str], actions: list[str] | None = None) -> list[str]:
    return [f"{m}:{a}" for m in modules for a in (actions or ACTIONS)]


SALES_MODULES = ["companies", "contacts", "leads", "deals", "activities", "tasks",
                 "calendar", "products", "quotations", "documents", "reports"]

# Default (system) roles seeded on first boot.
DEFAULT_ROLES: dict[str, dict] = {
    "Super Admin": {"description": "Full access to everything", "permissions": ["*"]},
    "Admin": {
        "description": "Administers the CRM, users and settings",
        "permissions": ALL_PERMISSIONS,
    },
    "Sales Manager": {
        "description": "Manages the sales team and full sales cycle",
        "permissions": _grant(SALES_MODULES + ["invoices", "projects", "support"]) + ["users:read"],
    },
    "Sales Executive": {
        "description": "Works leads, deals and daily sales activities",
        "permissions": _grant(SALES_MODULES, ["read", "write"]),
    },
    "Marketing": {
        "description": "Manages leads, campaigns and contacts",
        "permissions": _grant(["leads", "contacts", "companies", "activities", "tasks", "calendar", "reports"], ["read", "write"]),
    },
    "Support": {
        "description": "Handles support tickets and customer communication",
        "permissions": _grant(["support", "tasks", "activities", "calendar"], ["read", "write"])
        + ["companies:read", "contacts:read", "documents:read"],
    },
    "Finance": {
        "description": "Manages quotations, invoices and revenue reports",
        "permissions": _grant(["quotations", "invoices", "products", "reports"])
        + ["companies:read", "contacts:read", "deals:read", "documents:read"],
    },
    "HR": {
        "description": "Manages users and internal tasks",
        "permissions": ["users:read", "users:write"] + _grant(["tasks", "calendar"], ["read", "write"]),
    },
    "Viewer": {
        "description": "Read-only access",
        "permissions": [f"{m}:read" for m in MODULES],
    },
}


def has_permission(role_permissions: list[str] | None, permission: str) -> bool:
    perms = role_permissions or []
    if "*" in perms:
        return True
    if permission in perms:
        return True
    # "<module>:*" wildcard support for custom roles
    module = permission.split(":")[0]
    return f"{module}:*" in perms
