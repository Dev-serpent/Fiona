"""Tests for API catalog data models."""

from __future__ import annotations

import unittest

from fiona.apicatalog.models import ApiCategory, ApiEntry, SearchResult


class TestApiEntry(unittest.TestCase):
    """ApiEntry dataclass construction and immutability."""

    def test_create_minimal(self) -> None:
        entry = ApiEntry(
            name="TestAPI",
            description="A test API",
            auth="apiKey",
            https=True,
            cors="yes",
            category="Testing",
            url="https://test.api.example.com",
        )
        self.assertEqual(entry.name, "TestAPI")
        self.assertEqual(entry.auth, "apiKey")
        self.assertTrue(entry.https)
        self.assertEqual(entry.cors, "yes")
        self.assertEqual(entry.category, "Testing")
        self.assertEqual(entry.url, "https://test.api.example.com")
        self.assertEqual(entry.source_rank, 0)

    def test_create_with_auth_none(self) -> None:
        entry = ApiEntry(
            name="NoAuthAPI",
            description="No auth required",
            auth=None,
            https=False,
            cors="no",
            category="Testing",
            url="http://example.com",
        )
        self.assertIsNone(entry.auth)
        self.assertFalse(entry.https)

    def test_create_with_source_rank(self) -> None:
        entry = ApiEntry(
            name="PopularAPI",
            description="A popular API",
            auth="OAuth",
            https=True,
            cors="unknown",
            category="Popular",
            url="https://popular.api.com",
            source_rank=42,
        )
        self.assertEqual(entry.source_rank, 42)

    def test_frozen_immutable(self) -> None:
        entry = ApiEntry(
            name="Frozen",
            description="Should be immutable",
            auth=None,
            https=True,
            cors="yes",
            category="Test",
            url="https://example.com",
        )
        with self.assertRaises(AttributeError):
            entry.name = "Changed"  # type: ignore[misc]

    def test_entry_hashable(self) -> None:
        entry = ApiEntry(
            name="Hashable",
            description="Can be used in sets",
            auth=None,
            https=True,
            cors="yes",
            category="Test",
            url="https://example.com",
        )
        s = {entry}
        self.assertIn(entry, s)


class TestSearchResult(unittest.TestCase):
    """SearchResult dataclass."""

    def setUp(self) -> None:
        self.entry = ApiEntry(
            name="WeatherAPI",
            description="Weather data",
            auth="apiKey",
            https=True,
            cors="yes",
            category="Weather",
            url="https://weather.api",
        )

    def test_create(self) -> None:
        result = SearchResult(entry=self.entry, score=0.85, matched_on="category")
        self.assertIs(result.entry, self.entry)
        self.assertEqual(result.score, 0.85)
        self.assertEqual(result.matched_on, "category")

    def test_score_range(self) -> None:
        result = SearchResult(entry=self.entry, score=1.0, matched_on="name")
        self.assertEqual(result.score, 1.0)


class TestApiCategory(unittest.TestCase):
    """ApiCategory dataclass."""

    def test_create(self) -> None:
        cat = ApiCategory(name="Weather", count=15)
        self.assertEqual(cat.name, "Weather")
        self.assertEqual(cat.count, 15)

    def test_zero_count(self) -> None:
        cat = ApiCategory(name="Empty", count=0)
        self.assertEqual(cat.count, 0)


if __name__ == "__main__":
    unittest.main()
