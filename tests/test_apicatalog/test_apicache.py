"""Tests for the SQLite-backed ApiCache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fiona.apicatalog.cache import ApiCache
from fiona.apicatalog.models import ApiEntry


class TestApiCache(unittest.TestCase):
    """ApiCache CRUD, search, and lifecycle."""

    def setUp(self) -> None:
        self.db_path = Path(tempfile.mktemp(suffix=".db"))
        self.cache = ApiCache(db_path=self.db_path)

    def tearDown(self) -> None:
        self.cache.close()
        self.db_path.unlink(missing_ok=True)

    def _sample_entries(self) -> list[ApiEntry]:
        return [
            ApiEntry(
                name="OpenWeatherMap",
                description="Current weather data for cities worldwide",
                auth="apiKey",
                https=True,
                cors="unknown",
                category="Weather",
                url="https://api.openweathermap.org",
            ),
            ApiEntry(
                name="WeatherAPI",
                description="Weather forecasts and historical data",
                auth="apiKey",
                https=True,
                cors="yes",
                category="Weather",
                url="https://www.weatherapi.com",
            ),
            ApiEntry(
                name="CoinDesk",
                description="Bitcoin price index",
                auth=None,
                https=True,
                cors="unknown",
                category="Cryptocurrency",
                url="https://www.coindesk.com/price/",
            ),
            ApiEntry(
                name="Open Library",
                description="Books, authors, and covers",
                auth=None,
                https=True,
                cors="yes",
                category="Books",
                url="https://openlibrary.org",
            ),
        ]

    def test_open_creates_db(self) -> None:
        self.assertFalse(self.db_path.exists())
        self.cache.open()
        self.assertTrue(self.db_path.exists())

    def test_store_and_count(self) -> None:
        entries = self._sample_entries()
        self.cache.open()
        count = self.cache.store_entries(entries)
        self.assertEqual(count, len(entries))
        self.assertEqual(self.cache.count(), len(entries))

    def test_store_duplicate_replaces(self) -> None:
        self.cache.open()
        entries = self._sample_entries()[:1]
        self.cache.store_entries(entries)
        self.assertEqual(self.cache.count(), 1)

        # Store same name with different description
        dup = [
            ApiEntry(
                name="OpenWeatherMap",
                description="Updated description",
                auth="OAuth",
                https=False,
                cors="no",
                category="Changed",
                url="https://new.url",
            )
        ]
        self.cache.store_entries(dup)
        self.assertEqual(self.cache.count(), 1)
        entry = self.cache.get_by_name("OpenWeatherMap")
        assert entry is not None
        self.assertEqual(entry.description, "Updated description")

    def test_search_by_keyword(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())

        results = self.cache.search("weather")
        self.assertGreaterEqual(len(results), 2)

        names = {r.name for r in results}
        self.assertIn("OpenWeatherMap", names)
        self.assertIn("WeatherAPI", names)

    def test_search_by_category(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())

        results = self.cache.search("weather", category="Weather")
        self.assertGreaterEqual(len(results), 2)

    def test_search_nonexistent(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        results = self.cache.search("xyznonexistent")
        self.assertEqual(len(results), 0)

    def test_get_by_name(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        entry = self.cache.get_by_name("CoinDesk")
        assert entry is not None
        self.assertEqual(entry.category, "Cryptocurrency")

    def test_get_by_name_missing(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        self.assertIsNone(self.cache.get_by_name("NonExistent"))

    def test_get_by_category(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        entries = self.cache.get_by_category("Books")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "Open Library")

    def test_list_categories(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        cats = self.cache.list_categories()
        cat_names = {c[0] for c in cats}
        self.assertIn("Weather", cat_names)
        self.assertIn("Books", cat_names)
        self.assertIn("Cryptocurrency", cat_names)

    def test_clear(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        self.assertGreater(self.cache.count(), 0)
        self.cache.clear()
        self.assertEqual(self.cache.count(), 0)

    def test_auto_open_on_search(self) -> None:
        """Search should auto-open the cache."""
        self.cache.store_entries(self._sample_entries())  # no explicit open
        self.assertGreater(self.cache.count(), 0)

    def test_search_with_multiple_tokens(self) -> None:
        self.cache.open()
        self.cache.store_entries(self._sample_entries())
        results = self.cache.search("weather data")
        # Should match entries with either "weather" OR "data"
        self.assertGreaterEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
