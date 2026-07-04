"""Action handlers for the API catalog — registered with ActionRegistry.

These handlers are the public interface between the agent and the catalog.
They are deliberately limited to **discovery and metadata retrieval**.
Actual HTTP invocation of discovered APIs is deferred to a future
``HttpTool`` / ``ApiGateway`` component.
"""

from __future__ import annotations

from typing import Any

from fiona.actions import ActionHandler
from fiona.apicatalog.catalog import ApiCatalog


class ApiSearchHandler(ActionHandler):
    """Search the public-API catalog by keyword."""

    @property
    def name(self) -> str:
        return "api_search"

    def execute(self, params: dict[str, Any]) -> str:
        query = (params.get("query") or params.get("q") or "").strip()
        if not query:
            return "Error: 'query' parameter is required."

        top_k = int(params.get("top_k", 10))
        category = params.get("category")

        catalog = self._get_catalog()
        results = catalog.search(query, top_k=top_k)

        if not results:
            return f"No APIs found for '{query}'. Try a different search term."

        lines = [f"Found {len(results)} API{'' if len(results) == 1 else 's'} matching '{query}':"]
        for i, r in enumerate(results, 1):
            entry = r.entry
            desc_short = (entry.description[:120] + "…") if len(entry.description) > 120 else entry.description
            lines.append(
                f"\n{i}. {entry.name}  [{entry.category}]\n"
                f"   {desc_short}\n"
                f"   Auth: {entry.auth or 'None'}  |  HTTPS: {'Yes' if entry.https else 'No'}"
                f"  |  CORS: {entry.cors}\n"
                f"   {entry.url}"
            )

        return "\n".join(lines)

    def to_tool_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "api_search",
                "description": (
                    "Search the public-API catalog for APIs matching a "
                    "natural-language query (e.g. 'weather', 'translate text')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query — describes what the API should do",
                        },
                        "category": {
                            "type": "string",
                            "description": (
                                "Optional category filter (e.g. 'Weather', "
                                "'Finance', 'Science & Math')"
                            ),
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    @staticmethod
    def _get_catalog() -> ApiCatalog:
        return ApiCatalog()


class ApiInfoHandler(ActionHandler):
    """Return full metadata for a named API."""

    @property
    def name(self) -> str:
        return "api_info"

    def execute(self, params: dict[str, Any]) -> str:
        name = (params.get("name") or "").strip()
        if not name:
            return "Error: 'name' parameter is required."

        catalog = self._get_catalog()
        entry = catalog.get_by_name(name)
        if entry is None:
            return f"API '{name}' not found in catalog."

        return (
            f"API: {entry.name}\n"
            f"Category: {entry.category}\n"
            f"Description: {entry.description}\n"
            f"Authentication: {entry.auth or 'None (public)'}\n"
            f"HTTPS: {'Yes' if entry.https else 'No'}\n"
            f"CORS: {entry.cors}\n"
            f"URL: {entry.url}"
        )

    def to_tool_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "api_info",
                "description": "Get full metadata for a specific API by name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Exact name of the API as returned by api_search",
                        },
                    },
                    "required": ["name"],
                },
            },
        }

    @staticmethod
    def _get_catalog() -> ApiCatalog:
        return ApiCatalog()


class ApiListCategoriesHandler(ActionHandler):
    """List all API categories with their entry counts."""

    @property
    def name(self) -> str:
        return "api_categories"

    def execute(self, params: dict[str, Any]) -> str:
        catalog = self._get_catalog()
        categories = catalog.list_categories()

        if not categories:
            return "No categories found. Try running a search first."

        lines = ["API Categories:\n"]
        for cat in categories:
            lines.append(f"  • {cat.name} ({cat.count} API{'' if cat.count == 1 else 's'})")

        return "\n".join(lines)

    def to_tool_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "api_categories",
                "description": "List all API categories available in the catalog",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    @staticmethod
    def _get_catalog() -> ApiCatalog:
        return ApiCatalog()
