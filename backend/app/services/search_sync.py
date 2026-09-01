"""Builds compact search documents and pushes them to Meilisearch (no-op without it)."""

from app.services.search_client import delete_document, index_document


def _doc(entity, type_: str, title: str, subtitle: str = "", extra: str = "") -> dict:
    return {
        "id": entity.id,
        "type": type_,
        "title": title or "",
        "subtitle": subtitle or "",
        "extra": extra or "",
        "created_at": entity.created_at.isoformat() if entity.created_at else None,
    }


def sync_company(c) -> None:
    index_document("companies", _doc(c, "company", c.name, c.industry or "", c.city or ""))


def sync_contact(c) -> None:
    name = f"{c.first_name} {c.last_name}".strip()
    emails = ", ".join(c.emails or [])
    index_document("contacts", _doc(c, "contact", name, c.position or "", emails))


def sync_lead(l) -> None:
    index_document("leads", _doc(l, "lead", l.title, l.company_name or "", l.email or ""))


def sync_deal(d) -> None:
    index_document("deals", _doc(d, "deal", d.title, d.company.name if d.company else "", str(d.value or "")))


def sync_task(t) -> None:
    index_document("tasks", _doc(t, "task", t.title, t.status or "", t.priority or ""))


def sync_project(p) -> None:
    index_document("projects", _doc(p, "project", p.name, p.status or "", ""))


def remove(index: str, entity_id: str) -> None:
    delete_document(index, entity_id)
