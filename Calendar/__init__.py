"""Calendar — events, reminders, and scheduling subsystem.

Provides:
- SQLite-backed event and reminder persistence (``EventStore``)
- Natural language date/time parsing (``parse_datetime``)
- Background reminder engine with pluggable notification callbacks
- CLI via ``fiona calendar``

Quick start::

    from Calendar.event_store import EventStore
    store = EventStore()
    store.create_event("Team standup", start_time=..., reminders=[15])
"""

from __future__ import annotations

from Calendar.event_store import EventStore, get_store
from Calendar.nlp_time import parse_datetime, parse_duration
from Calendar.reminder_engine import ReminderEngine, get_engine, start_engine, stop_engine

__version__ = "0.1.0"

__all__ = [
    "EventStore",
    "get_store",
    "ReminderEngine",
    "get_engine",
    "start_engine",
    "stop_engine",
    "parse_datetime",
    "parse_duration",
]
