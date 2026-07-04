"""Data models for the API catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiEntry:
    """Single entry from the public-apis catalog.

    All fields map directly to the columns in the public-apis README table.
    Frozen so entries can be safely cached and shared across threads.
    """

    name: str
    description: str
    auth: str | None  # "apiKey", "OAuth", None, "X-Mashape-Key", etc.
    https: bool
    cors: str  # "yes" | "no" | "unknown"
    category: str
    url: str  # API base URL or documentation URL
    source_rank: int = 0  # popularity / quality signal


@dataclass(frozen=True)
class SearchResult:
    """A single search hit with relevance scoring."""

    entry: ApiEntry
    score: float  # 0.0 – 1.0 relevance
    matched_on: str  # "name" | "description" | "category" | "keyword"


@dataclass(frozen=True)
class ApiCategory:
    """A category with its API count."""

    name: str
    count: int
