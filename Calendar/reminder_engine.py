"""Background reminder engine for the Calendar module.

Runs a daemon thread that periodically checks for due reminders
and fires desktop notifications.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from Calendar.event_store import EventStore, get_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_POLL_INTERVAL = 15.0  # seconds

# ---------------------------------------------------------------------------
# Notification callback type
# ---------------------------------------------------------------------------

OnReminderCallback = Callable[[dict[str, Any]], None]


def _default_notifier(reminder: dict[str, Any]) -> None:
    """Default reminder handler: log to console."""
    title = reminder.get("title", "Reminder")
    trigger = reminder.get("trigger_at", "?")
    logger.info("🔔 REMINDER: %s (triggered at %s)", title, trigger)


# ---------------------------------------------------------------------------
# ReminderEngine
# ---------------------------------------------------------------------------


class ReminderEngine:
    """Background thread that polls for due reminders and fires callbacks.

    Usage::

        engine = ReminderEngine()
        engine.on_reminder = lambda r: print(f"Reminder: {r['title']}")
        engine.start()
        ...
        engine.stop()
    """

    def __init__(
        self,
        store: EventStore | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._store = store or get_store()
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._fired_ids: set[str] = set()

        # Override this to route reminders somewhere useful
        self.on_reminder: OnReminderCallback = _default_notifier

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            logger.debug("ReminderEngine already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="reminder-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("ReminderEngine started (poll every %.1fs)", self._poll_interval)

    def stop(self) -> None:
        """Signal the polling thread to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            logger.info("ReminderEngine stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_reminders()
            except Exception:
                logger.exception("ReminderEngine poll error")
            self._stop_event.wait(self._poll_interval)

    def _check_reminders(self) -> None:
        due = self._store.get_due_reminders()
        for reminder in due:
            rid = reminder["id"]
            if rid in self._fired_ids:
                continue
            self._fired_ids.add(rid)
            try:
                self.on_reminder(reminder)
            except Exception:
                logger.exception("Reminder handler failed for %s", rid)
            try:
                self._store.mark_reminder_fired(rid)
            except Exception:
                logger.exception("Failed to mark reminder fired: %s", rid)

    def reset_fired_cache(self) -> None:
        """Clear the in-memory fired-reminder cache (e.g. after restart)."""
        self._fired_ids.clear()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: ReminderEngine | None = None


def get_engine(store: EventStore | None = None) -> ReminderEngine:
    """Get or create the module-level ReminderEngine singleton."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = ReminderEngine(store=store)
    elif store is not None:
        _engine._store = store  # noqa: SLF001
    return _engine


def start_engine(store: EventStore | None = None) -> ReminderEngine:
    """Get the engine singleton and start it."""
    eng = get_engine(store)
    eng.start()
    return eng


def stop_engine() -> None:
    """Stop the engine singleton if running."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        _engine.stop()
        _engine = None
