"""High-level facade for the public-APIs catalog."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Sequence

from fiona.apicatalog.cache import ApiCache
from fiona.apicatalog.models import ApiCategory, ApiEntry, SearchResult
from fiona.apicatalog.repository import PublicApisRepo
from fiona.apicatalog.search import ApiSearcher

logger = logging.getLogger(__name__)

# Regex for section headings in the public-apis README
# Matches ## and ### (categories are ### under ## Index)
_HEADING_RE = re.compile(r"^#{2,3}\s+(.+)$")
# Regex to detect table separator rows (|---|---|---|...)
_SEPARATOR_RE = re.compile(r"^\|[\s\-:]+\|")
# Regex to extract a markdown link: [text](url)
_MD_LINK_RE = re.compile(r"^\[(.+?)\]\((.+?)\)\s*$")


class ApiCatalog:
    """Facade that ties together repository management, caching, and search.

    Typical usage::

        catalog = ApiCatalog()
        catalog.refresh()           # clone/pull + parse + cache
        results = catalog.search("weather")   # ranked results
        entry = catalog.get_by_name("OpenWeatherMap")
    """

    def __init__(
        self,
        repo: PublicApisRepo | None = None,
        cache: ApiCache | None = None,
    ) -> None:
        self._repo = repo or PublicApisRepo()
        self._cache = cache or ApiCache()
        self._searcher = ApiSearcher(self._cache)

    # ------------------------------------------------------------------
    # Refresh / sync
    # ------------------------------------------------------------------

    def refresh(self) -> int:
        """Clone or pull the repository, parse the README, populate the cache.

        Returns the number of entries that were stored.
        """
        repo_path = self._repo.ensure()
        entries = self._parse_readme(repo_path / "README.md")
        if not entries:
            logger.warning("No API entries parsed from README.md")
            return 0
        self._cache.open()
        count = self._cache.store_entries(entries)
        logger.info("Cached %d API entries from public-apis", count)
        return count

    def refresh_if_stale(self, max_age_hours: int = 24) -> int | None:
        """Refresh the cache if it is empty or older than *max_age_hours*.

        Returns the number of entries stored, or ``None`` if the cache
        was already fresh.
        """
        self._cache.open()
        if self._cache.count() == 0:
            return self.refresh()

        last = self._repo.last_refreshed()
        if last is not None:
            elapsed = (__import__("datetime").datetime.now() - last).total_seconds()
            if elapsed < max_age_hours * 3600:
                return None  # still fresh

        return self.refresh()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 10,
        category: str | None = None,
    ) -> list[SearchResult]:
        """Search the catalog, returning ranked results.

        If the cache is empty it will be populated automatically.
        """
        self._cache.open()
        if self._cache.count() == 0:
            self.refresh()
        return self._searcher.search(query, top_k=top_k)

    def get_by_name(self, name: str) -> ApiEntry | None:
        """Look up a single API by its exact name."""
        self._cache.open()
        if self._cache.count() == 0:
            self.refresh()
        return self._searcher.get_by_name(name)

    def get_by_category(self, category: str) -> list[ApiEntry]:
        """Return all entries under a given category."""
        self._cache.open()
        if self._cache.count() == 0:
            self.refresh()
        return self._searcher.get_by_category(category)

    def list_categories(self) -> list[ApiCategory]:
        """Return all known categories with their entry counts."""
        self._cache.open()
        if self._cache.count() == 0:
            self.refresh()
        return self._searcher.list_categories()

    # ------------------------------------------------------------------
    # Internal: README parsing
    # ------------------------------------------------------------------

    def _parse_readme(self, path: Path) -> list[ApiEntry]:
        """Parse the public-apis ``README.md`` table format.

        Handles two formats:

        **Legacy 6-column** (old README)::

            ## Category Name
            | API | Description | Auth | HTTPS | CORS | Link |
            |---|---|---|---|---|---|
            | Name | Desc | apiKey | Yes | Yes | https://... |

        **New 5-column** (current README, URL embedded in name)::

            ## Category Name
            | API | Description | Auth | HTTPS | CORS |
            |---|---|---|---|---|
            | [Name](https://...) | Desc | apiKey | Yes | Yes |
        """
        if not path.exists():
            logger.warning("README.md not found at %s", path)
            return []

        entries: list[ApiEntry] = []
        current_category = "Uncategorized"

        with open(path, encoding="utf-8") as f:
            for line in f:
                # Section header (## or ### — # is the document title)
                m = _HEADING_RE.match(line)
                if m:
                    heading = m.group(1).strip()
                    # Skip non-API section containers
                    if heading not in ("Index", "APILayer APIs", "Learn more about Public APIs", "License"):
                        current_category = heading
                    continue

                # Skip separator rows (|---|---|---|...)
                if _SEPARATOR_RE.match(line):
                    continue

                # Table row: must start with '|' and have at least 5 pipe chars
                if not line.startswith("|"):
                    continue
                if line.count("|") < 5:
                    continue

                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) < 5:
                    continue

                # Skip header rows (first cell is a column label, not an API name)
                first = cells[0].lower()
                if first in ("api", "name", "api name", "resource", "endpoint"):
                    continue

                # ---- Extract name + url ----
                # New format: name is a markdown link [Name](url) in column 0
                md_match = _MD_LINK_RE.match(cells[0])
                if md_match:
                    name = md_match.group(1)
                    url = md_match.group(2)
                else:
                    name = cells[0]
                    # Legacy format: URL is in column 5 (index 5 out of 6)
                    url = cells[5] if len(cells) > 5 else ""

                if not name or not url:
                    continue

                description = cells[1]
                auth_raw = cells[2] if len(cells) > 2 and cells[2] else None
                https_raw = cells[3].lower() if len(cells) > 3 else "no"
                cors_raw = cells[4].lower() if len(cells) > 4 else "unknown"

                # Normalise auth — treat "No" / empty as None
                auth: str | None = auth_raw
                if auth and auth.lower() in ("no", "none", ""):
                    auth = None

                entries.append(
                    ApiEntry(
                        name=name,
                        description=description,
                        auth=auth,
                        https=https_raw == "yes",
                        cors=cors_raw,
                        category=current_category,
                        url=url,
                    )
                )

        return entries
