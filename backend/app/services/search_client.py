"""Meilisearch integration with graceful degradation.

When MEILI_URL is unset (or the server is unreachable) indexing becomes a no-op
and the /search endpoint falls back to SQL ILIKE queries.
"""

import logging

from app.core.config import settings
from app.core.tenancy import current_tenant_id

log = logging.getLogger("weta.search")

_client = None
_available: bool | None = None

INDEXES = ["leads", "companies", "contacts", "deals", "tasks", "projects"]


def get_client():
    global _client, _available
    if not settings.meili_url:
        return None
    if _available is False:
        return None
    if _client is None:
        try:
            import meilisearch

            _client = meilisearch.Client(settings.meili_url, settings.meili_master_key or None)
            _client.health()
            _available = True
            _ensure_tenant_filterable(_client)
        except Exception:
            log.warning("Meilisearch unavailable at %s — falling back to SQL search", settings.meili_url)
            _client = None
            _available = False
    return _client


def _ensure_tenant_filterable(client) -> None:
    """Make `tenant_id` filterable so searches can be constrained to one tenant.

    Meilisearch rejects a filter on an attribute that is not declared filterable,
    so this must succeed before any tenant-scoped search runs. Applied once per
    process, on the first client build.
    """
    for index in INDEXES:
        try:
            client.index(index).update_filterable_attributes(["tenant_id", "type"])
        except Exception:
            log.warning("Could not set filterable attributes on index %s", index)


def index_document(index: str, doc: dict) -> None:
    client = get_client()
    if not client:
        return
    tenant_id = doc.get("tenant_id")
    if not tenant_id:
        log.error("Refusing to index a document without tenant_id in %s", index)
        return
    try:
        client.index(index).add_documents([doc], primary_key="id")
    except Exception:
        log.exception("Failed to index document in %s", index)


def delete_document(index: str, doc_id: str) -> None:
    client = get_client()
    if not client:
        return
    try:
        client.index(index).delete_document(doc_id)
    except Exception:
        log.exception("Failed to delete document from %s", index)


def search_all(query: str, limit: int = 5) -> dict[str, list[dict]] | None:
    """Search every index within the current tenant.

    Returns None when Meilisearch is unavailable so the caller can fall back to
    SQL. Also returns None when there is no tenant in context: an unfiltered
    Meilisearch query would return every tenant's documents, so refusing to search
    is the only safe answer.
    """
    tenant_id = current_tenant_id()
    if not tenant_id:
        log.error("Refusing to run a global search with no tenant in context")
        return None

    client = get_client()
    if not client:
        return None

    results: dict[str, list[dict]] = {}
    try:
        for index in INDEXES:
            try:
                hits = client.index(index).search(
                    query, {"limit": limit, "filter": f'tenant_id = "{tenant_id}"'}
                )["hits"]
            except Exception:
                hits = []
            results[index] = hits
        return results
    except Exception:
        return None


def remove_tenant(tenant_id: str) -> None:
    """Drop every document belonging to one tenant, across every index.

    Called when a tenant is purged. Without it their names and titles would keep
    turning up in the index long after the rows were gone — and Meilisearch is the
    one store that is not covered by deleting database rows.
    """
    client = get_client()
    if not client:
        return
    for index in INDEXES:
        try:
            client.index(index).delete_documents(filter=f'tenant_id = "{tenant_id}"')
        except Exception:
            log.exception("Could not clear %s for tenant %s", index, tenant_id)
