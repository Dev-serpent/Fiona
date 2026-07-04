"""Tests for the ApiCatalog facade, especially README parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fiona.apicatalog.catalog import ApiCatalog

_SAMPLE_README = """# Public APIs

## Weather
| API | Description | Auth | HTTPS | CORS | Link |
|---|---|---|---|---|---|
| OpenWeatherMap | Current weather data | apiKey | Yes | unknown | https://api.openweathermap.org |
| WeatherAPI | Weather forecasts | apiKey | Yes | yes | https://www.weatherapi.com |

## Books
| API | Description | Auth | HTTPS | CORS | Link |
|---|---|---|---|---|---|
| Open Library | Books and authors | No | Yes | yes | https://openlibrary.org |

## Cryptocurrency
| API | Description | Auth | HTTPS | CORS | Link |
|---|---|---|---|---|---|
| CoinDesk | Bitcoin price index | No | Yes | unknown | https://www.coindesk.com/price/ |
"""


class TestCatalogReadmeParser(unittest.TestCase):
    """ApiCatalog._parse_readme with sample README content."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        self.tmp.write(_SAMPLE_README)
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self.catalog = ApiCatalog()

    def tearDown(self) -> None:
        self.path.unlink(missing_ok=True)

    def test_parse_readme(self) -> None:
        entries = self.catalog._parse_readme(self.path)
        self.assertEqual(len(entries), 4)

    def test_parse_category(self) -> None:
        entries = self.catalog._parse_readme(self.path)
        weather = [e for e in entries if e.name == "OpenWeatherMap"]
        self.assertEqual(len(weather), 1)
        self.assertEqual(weather[0].category, "Weather")
        self.assertEqual(weather[0].auth, "apiKey")
        self.assertTrue(weather[0].https)

    def test_parse_no_auth(self) -> None:
        entries = self.catalog._parse_readme(self.path)
        library = [e for e in entries if e.name == "Open Library"]
        self.assertEqual(len(library), 1)
        self.assertIsNone(library[0].auth)

    def test_parse_no_entries_for_empty_file(self) -> None:
        empty = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        empty.write("# Empty\n")
        empty.close()
        empty_path = Path(empty.name)
        try:
            entries = self.catalog._parse_readme(empty_path)
            self.assertEqual(len(entries), 0)
        finally:
            empty_path.unlink(missing_ok=True)

    def test_parse_missing_file(self) -> None:
        entries = self.catalog._parse_readme(Path("/nonexistent/README.md"))
        self.assertEqual(len(entries), 0)

    def test_parse_https_no(self) -> None:
        readme = """# Test
| API | Description | Auth | HTTPS | CORS | Link |
|---|---|---|---|---|---|
| InsecureAPI | No encryption | No | No | yes | http://insecure.com |
"""
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        tmp.write(readme)
        tmp.close()
        path = Path(tmp.name)
        try:
            entries = self.catalog._parse_readme(path)
            self.assertEqual(len(entries), 1)
            self.assertFalse(entries[0].https)
            self.assertEqual(entries[0].url, "http://insecure.com")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
