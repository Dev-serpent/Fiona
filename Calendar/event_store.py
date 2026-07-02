"""SQLite-backed calendar event and reminder store.

Provides CRUD for events and reminders with recurrence support,
full-text search, and time-range queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_CALENDAR_DIR = Path.home() / ".config" / "fiona"
DEFAULT_CALENDAR_PATH = DEFAULT_CALENDAR_DIR / "calendar.sqlite"

# ---------------------------------------------------------------------------
# Event model helpers
# ---------------------------------------------------------------------------

_RECURRENCE_TYPES = ("none", "daily", "weekly", "weekdays", "monthly", "yearly")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row to an event dict."""
    event = dict(row)
    for col in ("start_time", "end_time", "created_at", "updated_at"):
        if isinstance(event.get(col), str):
            event[col] = event[col]
    if isinstance(event.get("reminders"), str):
        try:
            event["reminders"] = json.loads(event["reminders"])
        except (json.JSONDecodeError, TypeError):
            event["reminders"] = []
    if isinstance(event.get("tags"), str):
        try:
            event["tags"] = json.loads(event["tags"])
        except (json.JSONDecodeError, TypeError):
            event["tags"] = []
    if event.get("recurrence_end") is None:
        event["recurrence_end"] = None
    return event


# ---------------------------------------------------------------------------
# EventStore
# ---------------------------------------------------------------------------


class EventStore:
    """SQLite-backed event and reminder store.

    Thread-safe (uses check_same_thread=False + lock).
    """

    def __init__(self, db_path: str | Path = DEFAULT_CALENDAR_PATH) -> None:
        self._db_path = Path(db_path)
        _ensure_dir(self._db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock:
            cur = self._conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='events'")
            if cur.fetchone()[0] == 0:
                self._conn.executescript("""
                    CREATE TABLE events (
                        id              TEXT PRIMARY KEY,
                        title           TEXT NOT NULL,
                        description     TEXT DEFAULT '',
                        start_time      TEXT NOT NULL,       -- ISO 8601
                        end_time        TEXT NOT NULL,         -- ISO 8601
                        all_day         INTEGER DEFAULT 0,
                        location        TEXT DEFAULT '',
                        recurrence      TEXT DEFAULT 'none',  -- none|daily|weekly|weekdays|monthly|yearly
                        recurrence_end  TEXT DEFAULT NULL,    -- ISO 8601 or NULL
                        category        TEXT DEFAULT 'default',
                        color           TEXT DEFAULT '#4f8cff',
                        reminders       TEXT DEFAULT '[]',    -- JSON array of minutes-before
                        tags            TEXT DEFAULT '[]',    -- JSON array of strings
                        created_at      TEXT NOT NULL,
                        updated_at      TEXT NOT NULL
                    );

                    CREATE INDEX idx_events_start ON events(start_time);
                    CREATE INDEX idx_events_end   ON events(end_time);
                    CREATE INDEX idx_events_cat   ON events(category);

                    CREATE TABLE reminders (
                        id          TEXT PRIMARY KEY,
                        event_id    TEXT REFERENCES events(id) ON DELETE CASCADE,
                        title       TEXT NOT NULL,
                        trigger_at  TEXT NOT NULL,   -- ISO 8601
                        fired       INTEGER DEFAULT 0,
                        recurrence  TEXT DEFAULT 'none',
                        created_at  TEXT NOT NULL
                    );

                    CREATE INDEX idx_reminders_trigger ON reminders(trigger_at);
                    CREATE INDEX idx_reminders_fired   ON reminders(fired);
                """)
                self._conn.commit()
                logger.info("Calendar database created at %s", self._db_path)

    # ------------------------------------------------------------------
    # Events — CRUD
    # ------------------------------------------------------------------

    def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime | None = None,
        *,
        description: str = "",
        all_day: bool = False,
        location: str = "",
        recurrence: str = "none",
        recurrence_end: datetime | None = None,
        category: str = "default",
        color: str = "#4f8cff",
        reminders: list[int] | None = None,
        tags: list[str] | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new event. Returns the event dict."""
        if recurrence not in _RECURRENCE_TYPES:
            raise ValueError(f"recurrence must be one of {_RECURRENCE_TYPES}, got {recurrence!r}")
        if end_time is None:
            end_time = start_time + timedelta(hours=1)
        now = _now()
        eid = event_id or _uuid()
        with self._lock:
            self._conn.execute(
                """INSERT INTO events
                   (id, title, description, start_time, end_time, all_day,
                    location, recurrence, recurrence_end, category, color,
                    reminders, tags, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    eid,
                    title,
                    description,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    1 if all_day else 0,
                    location,
                    recurrence,
                    recurrence_end.isoformat() if recurrence_end else None,
                    category,
                    color,
                    json.dumps(reminders or []),
                    json.dumps(tags or []),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._conn.commit()
        event = self.get_event(eid)
        if event:
            self._sync_reminders(event)
        return event

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        """Fetch a single event by ID."""
        with self._lock:
            cur = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            row = cur.fetchone()
            return _row_to_event(row) if row else None

    def update_event(
        self,
        event_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        all_day: bool | None = None,
        location: str | None = None,
        recurrence: str | None = None,
        recurrence_end: datetime | None = None,
        category: str | None = None,
        color: str | None = None,
        reminders: list[int] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Update select fields on an event. Returns updated event or None."""
        existing = self.get_event(event_id)
        if not existing:
            return None

        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if description is not None:
            fields["description"] = description
        if start_time is not None:
            fields["start_time"] = start_time.isoformat()
        if end_time is not None:
            fields["end_time"] = end_time.isoformat()
        if all_day is not None:
            fields["all_day"] = 1 if all_day else 0
        if location is not None:
            fields["location"] = location
        if recurrence is not None:
            if recurrence not in _RECURRENCE_TYPES:
                raise ValueError(f"recurrence must be one of {_RECURRENCE_TYPES}, got {recurrence!r}")
            fields["recurrence"] = recurrence
        if recurrence_end is not None:
            fields["recurrence_end"] = recurrence_end.isoformat()
        if category is not None:
            fields["category"] = category
        if color is not None:
            fields["color"] = color
        if reminders is not None:
            fields["reminders"] = json.dumps(reminders)
        if tags is not None:
            fields["tags"] = json.dumps(tags)

        if not fields:
            return existing

        fields["updated_at"] = _now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [event_id]

        with self._lock:
            self._conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
            self._conn.commit()

        updated = self.get_event(event_id)
        if updated:
            self._sync_reminders(updated)
        return updated

    def delete_event(self, event_id: str) -> bool:
        """Delete an event and its reminders. Returns True if deleted."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List events with optional filters. Ordered by start_time ascending."""
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []

        if start:
            query += " AND end_time >= ?"
            params.append(start.isoformat())
        if end:
            query += " AND start_time <= ?"
            params.append(end.isoformat())
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY start_time ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._lock:
            cur = self._conn.execute(query, params)
            return [_row_to_event(row) for row in cur.fetchall()]

    def search_events(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Full-text search on event title and description."""
        pattern = f"%{query}%"
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM events WHERE title LIKE ? OR description LIKE ? ORDER BY start_time ASC LIMIT ?",
                (pattern, pattern, limit),
            )
            return [_row_to_event(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def _sync_reminders(self, event: dict[str, Any]) -> None:
        """Regenerate reminder entries for an event."""
        eid = event["id"]
        reminder_minutes: list[int] = event.get("reminders") or []
        start = datetime.fromisoformat(event["start_time"])

        # Delete existing reminders for this event
        self._conn.execute("DELETE FROM reminders WHERE event_id = ?", (eid,))

        for minutes_before in reminder_minutes:
            trigger_at = start - timedelta(minutes=minutes_before)
            if trigger_at > _now():
                rid = _uuid()
                self._conn.execute(
                    "INSERT INTO reminders (id, event_id, title, trigger_at, recurrence, created_at) VALUES (?,?,?,?,?,?)",
                    (rid, eid, event["title"], trigger_at.isoformat(), event.get("recurrence", "none"), _now().isoformat()),
                )
        self._conn.commit()

    def get_due_reminders(self) -> list[dict[str, Any]]:
        """Fetch all reminders that are due (trigger_at <= now) and not yet fired."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM reminders WHERE trigger_at <= ? AND fired = 0 ORDER BY trigger_at ASC",
                (_now().isoformat(),),
            )
            rows = [dict(row) for row in cur.fetchall()]
        return rows

    def mark_reminder_fired(self, reminder_id: str) -> None:
        """Mark a reminder as fired."""
        with self._lock:
            self._conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))
            self._conn.commit()

    def create_standalone_reminder(
        self,
        title: str,
        trigger_at: datetime,
        *,
        recurrence: str = "none",
    ) -> dict[str, Any]:
        """Create a reminder not tied to a specific event."""
        rid = _uuid()
        with self._lock:
            self._conn.execute(
                "INSERT INTO reminders (id, event_id, title, trigger_at, recurrence, created_at) VALUES (?,?,?,?,?,?)",
                (rid, None, title, trigger_at.isoformat(), recurrence, _now().isoformat()),
            )
            self._conn.commit()
        return self._get_reminder(rid)

    def _get_reminder(self, reminder_id: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_reminders(
        self,
        *,
        include_fired: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List reminders."""
        query = "SELECT * FROM reminders"
        params: list[Any] = []
        if not include_fired:
            query += " WHERE fired = 0"
        query += " ORDER BY trigger_at ASC LIMIT ?"
        params.append(limit)
        with self._lock:
            cur = self._conn.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get_upcoming(self, days: int = 7) -> list[dict[str, Any]]:
        """Get events starting within the next N days."""
        now = _now()
        end = now + timedelta(days=days)
        return self.list_events(start=now, end=end)

    def get_categories(self) -> list[str]:
        """List all unique event categories."""
        with self._lock:
            cur = self._conn.execute("SELECT DISTINCT category FROM events ORDER BY category")
            return [row[0] for row in cur.fetchall()]

    def get_stats(self) -> dict[str, Any]:
        """Return calendar statistics."""
        with self._lock:
            total = self._conn.execute("SELECT count(*) FROM events").fetchone()[0]
            upcoming = self._conn.execute(
                "SELECT count(*) FROM events WHERE start_time >= ?",
                (_now().isoformat(),),
            ).fetchone()[0]
            pending_reminders = self._conn.execute(
                "SELECT count(*) FROM reminders WHERE fired = 0 AND trigger_at <= ?",
                (_now().isoformat(),),
            ).fetchone()[0]
            cats = self._conn.execute("SELECT count(DISTINCT category) FROM events").fetchone()[0]
        return {
            "total_events": total,
            "upcoming_events": upcoming,
            "pending_reminders": pending_reminders,
            "categories": cats,
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_store: EventStore | None = None
_store_lock = threading.Lock()


def get_store(db_path: str | Path = DEFAULT_CALENDAR_PATH) -> EventStore:
    """Get or create the module-level EventStore singleton."""
    global _store  # noqa: PLW0603
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = EventStore(db_path)
    return _store
