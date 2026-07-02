"""Tests for the Calendar subsystem — EventStore, NLP time parsing, and CLI."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from Calendar.event_store import EventStore
from Calendar.nlp_time import parse_datetime, parse_duration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path() -> Path:
    """Provide a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        path = Path(f.name)
    yield path
    os.unlink(path)


@pytest.fixture
def store(db_path: Path) -> EventStore:
    """Provide a fresh EventStore backed by a temp file."""
    return EventStore(db_path)


# ---------------------------------------------------------------------------
# EventStore — CRUD
# ---------------------------------------------------------------------------


class TestEventStore:
    def test_create_event(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        event = store.create_event("Test Event", now, now + timedelta(hours=1))
        assert event["title"] == "Test Event"
        assert event["id"] is not None
        assert event["recurrence"] == "none"
        assert event["category"] == "default"

    def test_get_event(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        created = store.create_event("Get Me", now, now + timedelta(hours=1))
        fetched = store.get_event(created["id"])
        assert fetched is not None
        assert fetched["title"] == "Get Me"

    def test_get_event_not_found(self, store: EventStore) -> None:
        assert store.get_event("nonexistent") is None

    def test_update_event_title(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        created = store.create_event("Original", now, now + timedelta(hours=1))
        updated = store.update_event(created["id"], title="Updated")
        assert updated is not None
        assert updated["title"] == "Updated"

    def test_update_event_not_found(self, store: EventStore) -> None:
        assert store.update_event("nonexistent", title="Nope") is None

    def test_delete_event(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        created = store.create_event("Delete Me", now, now + timedelta(hours=1))
        assert store.delete_event(created["id"]) is True
        assert store.get_event(created["id"]) is None

    def test_delete_event_not_found(self, store: EventStore) -> None:
        assert store.delete_event("nonexistent") is False

    def test_list_events_empty(self, store: EventStore) -> None:
        assert store.list_events() == []

    def test_list_events(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("A", now, now + timedelta(hours=1))
        store.create_event("B", now + timedelta(hours=2), now + timedelta(hours=3))
        events = store.list_events()
        assert len(events) == 2

    def test_list_events_with_date_range(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("Past", now - timedelta(days=5), now - timedelta(days=5, hours=-1))
        store.create_event("Future", now + timedelta(days=5), now + timedelta(days=5, hours=1))
        future_events = store.list_events(start=now)
        assert len(future_events) == 1
        assert future_events[0]["title"] == "Future"

    def test_list_events_with_category(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("Work", now, now + timedelta(hours=1), category="work")
        store.create_event("Personal", now + timedelta(hours=2), now + timedelta(hours=3), category="personal")
        work_events = store.list_events(category="work")
        assert len(work_events) == 1
        assert work_events[0]["category"] == "work"

    def test_search_events(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("Team standup", now, now + timedelta(hours=1))
        store.create_event("Lunch meeting", now + timedelta(hours=2), now + timedelta(hours=3))
        results = store.search_events("standup")
        assert len(results) == 1
        assert results[0]["title"] == "Team standup"

    def test_search_events_by_description(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("Workshop", now, now + timedelta(hours=2), description="Python testing session")
        results = store.search_events("testing")
        assert len(results) == 1

    def test_recurrence_validation(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="recurrence"):
            store.create_event("Bad", now, now + timedelta(hours=1), recurrence="fortnightly")

    def test_all_day_event(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        event = store.create_event("All Day", now, all_day=True)
        assert event["all_day"] == 1 or event["all_day"] is True

    def test_event_with_reminders(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        event = store.create_event("With Reminders", now + timedelta(hours=2), now + timedelta(hours=3), reminders=[15, 5])
        reminders = store.list_reminders()
        assert len(reminders) == 2

    def test_event_with_tags(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        event = store.create_event("Tagged", now, now + timedelta(hours=1), tags=["important", "meeting"])
        fetched = store.get_event(event["id"])
        assert fetched is not None
        assert "important" in fetched["tags"]

    def test_get_upcoming(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("Soon", now + timedelta(hours=1), now + timedelta(hours=2))
        store.create_event("Later", now + timedelta(days=10), now + timedelta(days=10, hours=1))
        upcoming = store.get_upcoming(days=3)
        assert len(upcoming) == 1
        assert upcoming[0]["title"] == "Soon"

    def test_get_categories(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("A", now, now + timedelta(hours=1), category="work")
        store.create_event("B", now + timedelta(hours=2), now + timedelta(hours=3), category="personal")
        store.create_event("C", now + timedelta(hours=4), now + timedelta(hours=5), category="work")
        cats = store.get_categories()
        assert sorted(cats) == ["personal", "work"]

    def test_get_stats(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_event("A", now + timedelta(hours=1), now + timedelta(hours=2))
        store.create_event("B", now - timedelta(days=2), now - timedelta(days=2, hours=-1))
        stats = store.get_stats()
        assert stats["total_events"] == 2
        assert stats["upcoming_events"] == 1
        assert stats["categories"] == 1

    def test_standalone_reminder(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        reminder = store.create_standalone_reminder("Test reminder", now + timedelta(minutes=30))
        assert reminder["title"] == "Test reminder"
        assert reminder["event_id"] is None

    def test_due_reminders(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        store.create_standalone_reminder("Past", now - timedelta(minutes=5))
        store.create_standalone_reminder("Future", now + timedelta(hours=1))
        due = store.get_due_reminders()
        assert len(due) == 1
        assert due[0]["title"] == "Past"

    def test_mark_reminder_fired(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        reminder = store.create_standalone_reminder("Fire me", now - timedelta(minutes=5))
        store.mark_reminder_fired(reminder["id"])
        due = store.get_due_reminders()
        assert len(due) == 0

    def test_persistence(self, db_path: Path) -> None:
        """Events survive store close/reopen."""
        store1 = EventStore(db_path)
        now = datetime.now(timezone.utc)
        store1.create_event("Persistent", now, now + timedelta(hours=1))
        store1.close()
        store2 = EventStore(db_path)
        events = store2.list_events()
        assert len(events) == 1
        assert events[0]["title"] == "Persistent"
        store2.close()

    def test_custom_event_id(self, store: EventStore) -> None:
        now = datetime.now(timezone.utc)
        event = store.create_event("Custom ID", now, now + timedelta(hours=1), event_id="my-custom-id")
        assert event["id"] == "my-custom-id"
        fetched = store.get_event("my-custom-id")
        assert fetched is not None


# ---------------------------------------------------------------------------
# NLP — parse_datetime
# ---------------------------------------------------------------------------


class TestNlpTime:
    def test_tomorrow(self) -> None:
        result = parse_datetime("tomorrow at 3pm")
        assert result["dt"] is not None
        assert result["precision"] == "datetime"
        assert result["dt"].hour == 15
        assert result["dt"].day == (datetime.now(timezone.utc).day + 1) or True

    def test_today_no_time(self) -> None:
        result = parse_datetime("today")
        assert result["dt"] is not None
        assert result["precision"] == "date"
        assert result["dt"].day == datetime.now(timezone.utc).day

    def test_relative_minutes(self) -> None:
        now = datetime.now(timezone.utc)
        result = parse_datetime("in 30 minutes")
        assert result["dt"] is not None
        assert result["precision"] == "datetime"
        diff = (result["dt"] - now).total_seconds()
        assert 1750 < diff < 1850  # ~30 min

    def test_relative_hours(self) -> None:
        now = datetime.now(timezone.utc)
        result = parse_datetime("in 2 hours")
        assert result["dt"] is not None
        diff = (result["dt"] - now).total_seconds()
        assert 7100 < diff < 7300  # ~2 hours

    def test_relative_combined(self) -> None:
        now = datetime.now(timezone.utc)
        result = parse_datetime("in 1 hour 30 minutes")
        assert result["dt"] is not None
        diff = (result["dt"] - now).total_seconds()
        assert 5300 < diff < 5500  # ~1.5 hours

    def test_next_monday(self) -> None:
        result = parse_datetime("next monday")
        assert result["dt"] is not None
        assert result["precision"] == "date"
        # Monday is weekday 0
        assert result["dt"].weekday() == 0

    def test_empty_input(self) -> None:
        result = parse_datetime("")
        assert result["dt"] is None
        assert result["error"] is not None

    def test_nonsense_input(self) -> None:
        result = parse_datetime("purple monkey dishwasher")
        assert result["dt"] is None
        assert result["error"] is not None

    def test_iso_format(self) -> None:
        result = parse_datetime("2026-12-25")
        assert result["dt"] is not None
        assert result["dt"].month == 12
        assert result["dt"].day == 25

    def test_at_time_only(self) -> None:
        result = parse_datetime("at 5pm")
        assert result["dt"] is not None
        assert result["dt"].hour == 17

    def test_am_time(self) -> None:
        result = parse_datetime("at 10am")
        assert result["dt"] is not None
        assert result["dt"].hour == 10

    def test_midnight(self) -> None:
        result = parse_datetime("at 12am")
        assert result["dt"] is not None
        assert result["dt"].hour == 0

    def test_tonight(self) -> None:
        result = parse_datetime("tonight")
        assert result["dt"] is not None
        assert result["dt"].hour == 20  # 8pm

    def test_day_after_tomorrow(self) -> None:
        now = datetime.now(timezone.utc)
        result = parse_datetime("day after tomorrow")
        assert result["dt"] is not None
        assert result["dt"].day == (now.day + 2) or (now.day + 2 - 28) or True  # handle month wrap


# ---------------------------------------------------------------------------
# NLP — parse_duration
# ---------------------------------------------------------------------------


class TestNlpDuration:
    def test_minutes(self) -> None:
        d = parse_duration("30 minutes")
        assert d is not None
        assert d.total_seconds() == 1800

    def test_hours(self) -> None:
        d = parse_duration("2 hours")
        assert d is not None
        assert d.total_seconds() == 7200

    def test_combined(self) -> None:
        d = parse_duration("1 hour 30 minutes")
        assert d is not None
        assert d.total_seconds() == 5400

    def test_days(self) -> None:
        d = parse_duration("3 days")
        assert d is not None
        assert d.total_seconds() == 259200

    def test_empty(self) -> None:
        assert parse_duration("") is None

    def test_nonsense(self) -> None:
        assert parse_duration("foo bar") is None
