"""REST API handlers for the public-API catalog (apicatalog)."""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import web

from fiona.apicatalog import ApiCatalog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singleton — ApiCatalog is created once on first request.
# ---------------------------------------------------------------------------
_catalog: ApiCatalog | None = None


def _get_catalog() -> ApiCatalog:
    global _catalog
    if _catalog is None:
        _catalog = ApiCatalog()
    return _catalog


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_search(request: web.Request) -> web.Response:
    """GET /api/v1/apicatalog/search

    Query params:
        q           — search query (required)
        category    — optional category filter
        top_k       — max results (default 10)

    Returns ranked API entries as JSON.
    """
    query = (request.query.get("q") or "").strip()
    if not query:
        return web.json_response(
            {"error": "Missing required query parameter 'q'"},
            status=400,
        )

    category = request.query.get("category")
    top_k_str = request.query.get("top_k", "10")
    try:
        top_k = max(1, int(top_k_str))
    except (ValueError, TypeError):
        top_k = 10

    catalog = _get_catalog()
    try:
        results = catalog.search(query, top_k=top_k, category=category)
    except Exception:
        logger.exception("API catalog search failed")
        return web.json_response(
            {"error": "Search failed. Is the catalog cloned? Try again."},
            status=502,
        )

    return web.json_response({
        "ok": True,
        "query": query,
        "category": category,
        "count": len(results),
        "results": [_result_to_dict(r) for r in results],
    })


async def handle_info(request: web.Request) -> web.Response:
    """GET /api/v1/apicatalog/info

    Query params:
        name — exact API name (required)

    Returns full metadata for a single API.
    """
    name = (request.query.get("name") or "").strip()
    if not name:
        return web.json_response(
            {"error": "Missing required query parameter 'name'"},
            status=400,
        )

    catalog = _get_catalog()
    entry = catalog.get_by_name(name)
    if entry is None:
        return web.json_response(
            {"error": f"API '{name}' not found in catalog"},
            status=404,
        )

    return web.json_response({
        "ok": True,
        "entry": {
            "name": entry.name,
            "description": entry.description,
            "auth": entry.auth,
            "https": entry.https,
            "cors": entry.cors,
            "category": entry.category,
            "url": entry.url,
        },
    })


async def handle_categories(request: web.Request) -> web.Response:
    """GET /api/v1/apicatalog/categories

    Returns all categories with their API counts.
    """
    catalog = _get_catalog()
    try:
        categories = catalog.list_categories()
    except Exception:
        logger.exception("Failed to list categories")
        return web.json_response(
            {"error": "Failed to list categories"},
            status=502,
        )

    return web.json_response({
        "ok": True,
        "count": len(categories),
        "categories": [
            {"name": c.name, "count": c.count} for c in categories
        ],
    })


async def handle_refresh(request: web.Request) -> web.Response:
    """POST /api/v1/apicatalog/refresh

    Force a git pull + re-parse + re-cache of the public-apis repository.
    """
    catalog = _get_catalog()
    try:
        count = catalog.refresh()
    except Exception:
        logger.exception("Catalog refresh failed")
        return web.json_response(
            {"error": "Refresh failed. Is git installed? Check logs."},
            status=502,
        )

    return web.json_response({
        "ok": True,
        "entries_cached": count,
        "message": f"Cached {count} API entries from public-apis.",
    })


async def handle_status(request: web.Request) -> web.Response:
    """GET /api/v1/apicatalog/status

    Returns catalog status: entry count, last refreshed, cache location.
    """
    catalog = _get_catalog()
    try:
        from fiona.apicatalog.cache import ApiCache
        from fiona.apicatalog.repository import PublicApisRepo

        cache = ApiCache()
        cache.open()
        entry_count = cache.count()
        cache.close()

        repo = PublicApisRepo()
        last_refreshed = repo.last_refreshed()

        return web.json_response({
            "ok": True,
            "entry_count": entry_count,
            "last_refreshed": last_refreshed.isoformat() if last_refreshed else None,
            "cache_path": str(ApiCache.DEFAULT_DB_PATH),
            "repo_path": str(PublicApisRepo.DEFAULT_CACHE_DIR),
        })
    except Exception:
        logger.exception("Failed to get catalog status")
        return web.json_response({
            "ok": False,
            "entry_count": 0,
            "error": "Catalog not initialized",
        })


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _result_to_dict(r: Any) -> dict:
    """Convert a SearchResult to a JSON-safe dict."""
    entry = r.entry
    return {
        "name": entry.name,
        "description": entry.description,
        "auth": entry.auth,
        "https": entry.https,
        "cors": entry.cors,
        "category": entry.category,
        "url": entry.url,
        "score": round(r.score, 4),
        "matched_on": r.matched_on,
    }
