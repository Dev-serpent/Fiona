"""Tests for the ApiSearcher scoring and ranking."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fiona.apicatalog.cache import ApiCache
from fiona.apicatalog.models import ApiEntry
from fiona.apicatalog.search import ApiSearcher


class TestApiSearcher(unittest.TestCase):
    """ApiSearcher multi-strategy ranking."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.tmp.name)
        self.tmp.close()
        self.cache = ApiCache(db_path=self.db_path)
        self.cache.open()
        self._seed_data()
        self.searcher = ApiSearcher(self.cache)

    def tearDown(self) -> None:
        self.cache.close()
        self.db_path.unlink(missing_ok=True)

    def _seed_data(self) -> None:
        entries = [
            ApiEntry(
                name="OpenWeatherMap",
                description="Current weather data for cities worldwide. "
                            "Includes temperature, humidity, wind speed.",
                auth="apiKey",
                https=True,
                cors="unknown",
                category="Weather",
                url="https://api.openweathermap.org",
            ),
            ApiEntry(
                name="WeatherAPI",
                description="Weather forecasts, historical data, and astronomy.",
                auth="apiKey",
                https=True,
                cors="yes",
                category="Weather",
                url="https://www.weatherapi.com",
            ),
            ApiEntry(
                name="CoinGecko",
                description="Cryptocurrency market data and prices.",
                auth="apiKey",
                https=True,
                cors="yes",
                category="Cryptocurrency",
                url="https://www.coingecko.com",
            ),
            ApiEntry(
                name="Open Library",
                description="Books, authors, and covers. Search and catalog.",
                auth=None,
                https=True,
                cors="yes",
                category="Books",
                url="https://openlibrary.org",
            ),
            ApiEntry(
                name="NASA",
                description="NASA data about space, astronomy, and Earth science.",
                auth=None,
                https=True,
                cors="no",
                category="Science & Math",
                url="https://api.nasa.gov",
            ),
        ]
        self.cache.store_entries(entries)

    def test_search_by_category_name(self) -> None:
        """Category match should rank highest."""
        results = self.searcher.search("weather", top_k=5)
        self.assertGreater(len(results), 0)
        # Both weather APIs should be in results
        names = {r.entry.name for r in results}
        self.assertIn("OpenWeatherMap", names)
        self.assertIn("WeatherAPI", names)

    def test_search_by_name(self) -> None:
        results = self.searcher.search("CoinGecko", top_k=5)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].entry.name, "CoinGecko")

    def test_search_by_description_keyword(self) -> None:
        results = self.searcher.search("books authors", top_k=5)
        self.assertGreater(len(results), 0)
        names = {r.entry.name for r in results}
        self.assertIn("Open Library", names)

    def test_search_no_results(self) -> None:
        results = self.searcher.search("xyznonexistentqwerty", top_k=5)
        self.assertEqual(len(results), 0)

    def test_search_top_k(self) -> None:
        results = self.searcher.search("api", top_k=2)
        self.assertLessEqual(len(results), 2)

    def test_search_scoring_order(self) -> None:
        """Results should be in descending score order."""
        results = self.searcher.search("weather", top_k=5)
        for i in range(len(results) - 1):
            self.assertGreaterEqual(results[i].score, results[i + 1].score)

    def test_get_by_name(self) -> None:
        entry = self.searcher.get_by_name("NASA")
        assert entry is not None
        self.assertEqual(entry.category, "Science & Math")

    def test_get_by_name_missing(self) -> None:
        self.assertIsNone(self.searcher.get_by_name("NonExistent"))

    def test_get_by_category(self) -> None:
        entries = self.searcher.get_by_category("Books")
        self.assertEqual(len(entries), 1)

    def test_list_categories(self) -> None:
        cats = self.searcher.list_categories()
        cat_names = {c.name for c in cats}
        self.assertIn("Weather", cat_names)
        self.assertIn("Books", cat_names)

    def test_multiple_tokens(self) -> None:
        """Multiple tokens should still find matches."""
        results = self.searcher.search("space data", top_k=5)
        self.assertGreater(len(results), 0)


if __name__ == "__main__":
    unittest.main()
