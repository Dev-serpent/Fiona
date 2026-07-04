"""Tests for catalog action handlers (ApiSearchHandler, ApiInfoHandler, etc.)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fiona.apicatalog.actions import (
    ApiInfoHandler,
    ApiListCategoriesHandler,
    ApiSearchHandler,
)
from fiona.apicatalog.cache import ApiCache
from fiona.apicatalog.models import ApiEntry


class _SeededMixin:
    """Mixin that provides a pre-seeded ApiCache via mock."""

    SEED_DATA = [
        ApiEntry(
            name="OpenWeatherMap",
            description="Current weather data",
            auth="apiKey",
            https=True,
            cors="unknown",
            category="Weather",
            url="https://api.openweathermap.org",
        ),
        ApiEntry(
            name="CoinGecko",
            description="Cryptocurrency prices",
            auth="apiKey",
            https=True,
            cors="yes",
            category="Cryptocurrency",
            url="https://www.coingecko.com",
        ),
        ApiEntry(
            name="Open Library",
            description="Books and authors",
            auth=None,
            https=True,
            cors="yes",
            category="Books",
            url="https://openlibrary.org",
        ),
    ]

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.tmp.name)
        self.tmp.close()
        self.cache = ApiCache(db_path=self.db_path)
        self.cache.open()
        self.cache.store_entries(self.SEED_DATA)
        self.cache.close()  # close so ApiCatalog re-opens it

        patcher = patch(
            "fiona.apicatalog.catalog.ApiCache",
            return_value=ApiCache(db_path=self.db_path),
        )
        self.mock_cache = patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.db_path.unlink(missing_ok=True)


class TestApiSearchHandler(unittest.TestCase):
    """ApiSearchHandler formatting and validation."""

    def test_missing_query_returns_error(self) -> None:
        handler = ApiSearchHandler()
        result = handler.execute({})
        self.assertTrue(result.startswith("Error:"))

    def test_empty_query_returns_error(self) -> None:
        handler = ApiSearchHandler()
        result = handler.execute({"query": ""})
        self.assertTrue(result.startswith("Error:"))

    def test_to_tool_spec_has_required_fields(self) -> None:
        handler = ApiSearchHandler()
        spec = handler.to_tool_spec()
        self.assertEqual(spec["function"]["name"], "api_search")
        self.assertIn("query", spec["function"]["parameters"]["required"])


class TestApiInfoHandler(_SeededMixin, unittest.TestCase):
    """ApiInfoHandler metadata retrieval."""

    def test_missing_name_returns_error(self) -> None:
        handler = ApiInfoHandler()
        result = handler.execute({})
        self.assertTrue(result.startswith("Error:"))

    def test_unknown_api_returns_not_found(self) -> None:
        handler = ApiInfoHandler()
        result = handler.execute({"name": "NonExistentAPI"})
        self.assertIn("not found", result.lower())

    def test_to_tool_spec(self) -> None:
        handler = ApiInfoHandler()
        spec = handler.to_tool_spec()
        self.assertEqual(spec["function"]["name"], "api_info")
        self.assertIn("name", spec["function"]["parameters"]["required"])


class TestApiListCategoriesHandler(_SeededMixin, unittest.TestCase):
    """ApiListCategoriesHandler category listing."""

    def test_list_categories(self) -> None:
        handler = ApiListCategoriesHandler()
        result = handler.execute({})
        self.assertIn("Weather", result)
        self.assertIn("Books", result)
        self.assertIn("Cryptocurrency", result)

    def test_to_tool_spec(self) -> None:
        handler = ApiListCategoriesHandler()
        spec = handler.to_tool_spec()
        self.assertEqual(spec["function"]["name"], "api_categories")


if __name__ == "__main__":
    unittest.main()
