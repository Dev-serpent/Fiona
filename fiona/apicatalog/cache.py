"""SQLite-backed persistent cache for parsed API entries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fiona.apicatalog.models import ApiEntry


class ApiCache:
    """Persistent cache of parsed API entries.

    Stores entries in a local SQLite database at ``~/.cache/fiona/apis.db``.
    Provides indexed search by category and full-text search across names
    and descriptions.
    """

    DEFAULT_DB_PATH = Path.home() / ".cache" / "fiona" / "apis.db"

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or self.DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and ensure the schema exists."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS api_entries (
                name        TEXT PRIMARY KEY,
                description TEXT,
                auth        TEXT,
                https       INTEGER,
                cors        TEXT,
                category    TEXT,
                url         TEXT,
                source_rank INTEGER DEFAULT 0,
                updated_at  TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_category
            ON api_entries(category)
        """)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------

    def store_entries(self, entries: list[ApiEntry]) -> int:
        """Bulk upsert *entries* using ``INSERT OR REPLACE``.

        Returns the number of rows affected.
        """
        self._ensure_open()
        count = 0
        rows = [
            (
                e.name,
                e.description,
                e.auth,
                int(e.https),
                e.cors if e.cors else "unknown",
                e.category,
                e.url,
            )
            for e in entries
        ]
        with self._conn:  # auto-commit on success
            count = self._conn.executemany(
                """INSERT OR REPLACE INTO api_entries
                   (name, description, auth, https, cors, category, url)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            ).rowcount
        return count

    def count(self) -> int:
        """Return the total number of cached entries."""
        self._ensure_open()
        row = self._conn.execute("SELECT COUNT(*) AS cnt FROM api_entries").fetchone()
        return row["cnt"] if row else 0

    def search(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[ApiEntry]:
        """Search entries by keyword.

        Performs a broad ``LIKE``-based pre-filter across ``name`` and
        ``description`` columns using ``OR`` between tokens.  This is
        intentionally broad — the caller (``ApiSearcher``) applies
        fine-grained scoring and ranking on the result set.

        Results are ordered by category then name.
        """
        self._ensure_open()
        name_conditions: list[str] = []
        name_params: list[Any] = []

        # Tokenise and skip very short fragments
        tokens = [t for t in query.strip().lower().split() if len(t) > 1]
        for token in tokens:
            like = f"%{token}%"
            name_conditions.append(
                "(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
            )
            name_params.extend([like, like])

        where_parts: list[str] = []
        params: list[Any] = []

        if name_conditions:
            # OR between tokens so the pre-filter is broad
            where_parts.append("(" + " OR ".join(name_conditions) + ")")
            params.extend(name_params)

        if category:
            where_parts.append("LOWER(category) = ?")
            params.append(category.lower())

        where_clause = " AND ".join(where_parts) if where_parts else "1=1"
        sql = (
            f"SELECT * FROM api_entries WHERE {where_clause}"
            f" ORDER BY category, name LIMIT ?"
        )
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def get_by_name(self, name: str) -> ApiEntry | None:
        """Return a single entry by exact name match, or ``None``."""
        self._ensure_open()
        row = self._conn.execute(
            "SELECT * FROM api_entries WHERE name = ?", (name,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def get_by_category(self, category: str) -> list[ApiEntry]:
        """Return all entries under *category*."""
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT * FROM api_entries WHERE LOWER(category) = LOWER(?)"
            " ORDER BY name",
            (category,),
        ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def list_categories(self) -> list[tuple[str, int]]:
        """Return ``[(category_name, count), ...]`` sorted by count descending."""
        self._ensure_open()
        rows = self._conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM api_entries"
            " GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        return [(r["category"], r["cnt"]) for r in rows]

    def clear(self) -> None:
        """Delete all entries from the cache."""
        self._ensure_open()
        with self._conn:
            self._conn.execute("DELETE FROM api_entries")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._conn is None:
            self.open()


def _row_to_entry(row: sqlite3.Row) -> ApiEntry:
    return ApiEntry(
        name=row["name"],
        description=row["description"],
        auth=row["auth"],
        https=bool(row["https"]),
        cors=row["cors"],
        category=row["category"],
        url=row["url"],
        source_rank=row["source_rank"] if "source_rank" in row.keys() else 0,
    )
