"""Keyword-based search and ranking over the API catalog."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Sequence

from fiona.apicatalog.cache import ApiCache
from fiona.apicatalog.models import ApiCategory, ApiEntry, SearchResult

# ---------------------------------------------------------------------------
# Stop words filtered out during keyword extraction
# ---------------------------------------------------------------------------
_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "for", "and", "or", "of", "to", "in", "is",
    "it", "on", "at", "by", "with", "from", "as", "be", "are", "was",
    "can", "do", "does", "has", "have", "had", "not", "no", "but",
})


class ApiSearcher:
    """Search and rank API entries using multi-strategy matching.

    Combines three strategies with weighted scoring:

    1. **Category match** (weight 3.0) — exact category name match.
    2. **Name fuzzy match** (weight 2.0) — ``SequenceMatcher`` ratio.
    3. **Description keyword match** (weight 1.0) — token overlap.
    """

    # Strategy weights
    CATEGORY_WEIGHT = 3.0
    NAME_WEIGHT = 2.0
    DESCRIPTION_WEIGHT = 1.0

    def __init__(self, cache: ApiCache) -> None:
        self._cache = cache

    def search(self, query: str, top_k: int = 10) -> list[SearchResult]:
        """Return the *top_k* most relevant ``SearchResult`` entries.

        Matching is entirely local — no LLM calls are made.
        """
        # 1.  Get candidates from SQLite full-text search
        candidates = self._cache.search(query, limit=top_k * 3)

        if not candidates:
            return []

        # 2.  Score each candidate
        query_lower = query.lower().strip()
        query_tokens = _tokenize(query_lower)

        scored: list[tuple[float, ApiEntry, str]] = []
        for entry in candidates:
            score, reason = self._score_entry(entry, query_lower, query_tokens)
            if score > 0.0:
                scored.append((score, entry, reason))

        # 3.  Sort descending by score, break ties alphabetically
        scored.sort(key=lambda t: (-t[0], t[1].name.lower()))

        return [
            SearchResult(entry=e, score=s, matched_on=r)
            for s, e, r in scored[:top_k]
        ]

    def _score_entry(
        self,
        entry: ApiEntry,
        query_lower: str,
        query_tokens: set[str],
    ) -> tuple[float, str]:
        """Score a single entry and return ``(score, match_reason)``."""
        scores: list[tuple[float, str]] = []

        # Strategy 1 — category match
        cat_lower = entry.category.lower()
        if query_lower == cat_lower or query_lower in cat_lower or cat_lower in query_lower:
            scores.append((self.CATEGORY_WEIGHT, "category"))

        # Strategy 2 — name fuzzy match
        name_lower = entry.name.lower()
        name_ratio = SequenceMatcher(None, query_lower, name_lower).ratio()
        if name_ratio > 0.4:
            scores.append((name_ratio * self.NAME_WEIGHT, "name"))
        # Also check if any query token appears in the name
        if any(token in name_lower for token in query_tokens):
            scores.append((0.5 * self.NAME_WEIGHT, "name"))

        # Strategy 3 — description keyword match
        desc_lower = entry.description.lower()
        desc_tokens = _tokenize(desc_lower)
        common = query_tokens & desc_tokens
        if common:
            keyword_score = (len(common) / max(len(query_tokens), 1)) * self.DESCRIPTION_WEIGHT
            scores.append((keyword_score, "keyword"))

        if not scores:
            return (0.0, "none")

        total = sum(s for s, _ in scores)
        best_reason = max(scores, key=lambda t: t[0])[1]
        return (total, best_reason)

    # ------------------------------------------------------------------
    # Convenience queries
    # ------------------------------------------------------------------

    def get_by_name(self, name: str) -> ApiEntry | None:
        """Return a single entry by exact name."""
        return self._cache.get_by_name(name)

    def get_by_category(self, category: str) -> list[ApiEntry]:
        """Return all entries in a category."""
        return self._cache.get_by_category(category)

    def list_categories(self) -> list[ApiCategory]:
        """Return all categories with entry counts."""
        raw = self._cache.list_categories()
        return [ApiCategory(name=n, count=c) for n, c in raw]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Split *text* into lower-cased tokens, removing stop-words."""
    words = text.split()
    return {w for w in words if w not in _STOP_WORDS and len(w) > 1}
