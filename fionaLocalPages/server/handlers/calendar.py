"""REST API handler for the Calendar subsystem.

Wraps ``Calendar.event_store.EventStore`` and related utilities for
CRUD operations on events and reminders via HTTP.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from aiohttp.web import Request, Response, json_response

from fionaLocalPages.server.middleware import ApiError

logger = logging.getLogger("fiona.handlers.calendar")

# ---------------------------------------------------------------------------
# Lazy import — the Calendar module may not be installed / importable in
# minimal environments.  We defer importing until first use.
# ---------------------------------------------------------------------------
_store = None


def _get_store():
    global _store
    if _store is None:
        from Calendar import get_store
        _store = get_store()
    return _store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_body(request: Request) -> dict[str, Any]:
    """Safely extract JSON body from request."""
    try:
        return request.json()
    except AttributeError:
        # For sync callers (e.g. flask action handlers via mock)
        raise ApiError(400, "Request must have a JSON body")
    except Exception:
        raise ApiError(400, "Invalid JSON body")


def _bool_or_default(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes")
    if isinstance(val, int):
        return val == 1
    return default


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def list_events(request: Request) -> Response:
    """GET /api/v1/calendar/events

    Query params:
        upcoming (int) — get upcoming N days of events
        category (str) — filter by category
        start_date (str) — ISO date to start from
        end_date (str) — ISO date to end at
    """
    store = _get_store()
    query = request.query

    if "upcoming" in query:
        try:
            days = int(query.get("upcoming", 7))
        except (ValueError, TypeError):
            raise ApiError(400, "upcoming must be an integer")
        events = store.get_upcoming(days)
    elif "category" in query:
        events = store.list_events(category=query.get("category"))
    elif "start_date" in query or "end_date" in query:
        start = query.get("start_date")
        end = query.get("end_date")
        events = store.list_events(start_date=start, end_date=end)
    else:
        events = store.list_events()

    return json_response({
        "ok": True,
        "data": {
            "events": events,
            "total": len(events),
        },
    })


async def create_event(request: Request) -> Response:
    """POST /api/v1/calendar/events"""
    body = await _json_body(request)
    store = _get_store()

    title = (body.get("title") or "").strip()
    if not title:
        raise ApiError(400, "title is required")

    start_time_str = (body.get("start_time") or "").strip()
    if not start_time_str:
        raise ApiError(400, "start_time is required")

    # Parse start_time using natural language if possible
    from Calendar import parse_datetime
    parsed = parse_datetime(start_time_str)
    if parsed and parsed.get("dt"):
        start_dt = parsed["dt"]
    else:
        # Try ISO format
        try:
            start_dt = datetime.fromisoformat(start_time_str)
        except (ValueError, TypeError):
            raise ApiError(400, f"Cannot parse start_time: {start_time_str}")

    # Parse duration if provided
    duration = body.get("duration")
    if duration:
        from Calendar import parse_duration
        dur = parse_duration(str(duration))
        if dur:
            duration = int(dur.total_seconds()) // 60  # convert to minutes
        else:
            try:
                duration = int(duration)
            except (ValueError, TypeError):
                duration = None

    event = store.create_event(
        title=title,
        start_time=start_dt,
        end_time=body.get("end_time"),
        all_day=_bool_or_default(body.get("all_day"), False),
        category=body.get("category"),
        color=body.get("color"),
        tags=body.get("tags"),
        description=body.get("description"),
        recurrence=body.get("recurrence"),
        duration_minutes=duration,
        reminders=body.get("reminders"),
    )
    return json_response({"ok": True, "data": event}, status=201)


async def get_event(request: Request) -> Response:
    """GET /api/v1/calendar/events/{id}"""
    event_id = request.match_info.get("id", "")
    store = _get_store()
    event = store.get_event(event_id)
    if event is None:
        raise ApiError(404, f"Event not found: {event_id}")
    return json_response({"ok": True, "data": event})


async def update_event(request: Request) -> Response:
    """PUT /api/v1/calendar/events/{id}"""
    event_id = request.match_info.get("id", "")
    body = await _json_body(request)
    store = _get_store()

    # Parse start_time if provided
    start_time_str = body.get("start_time")
    if start_time_str:
        from Calendar import parse_datetime
        parsed = parse_datetime(start_time_str)
        if parsed and parsed.get("dt"):
            body["start_time"] = parsed["dt"]

    # Parse duration if provided
    duration = body.get("duration")
    if duration:
        from Calendar import parse_duration
        dur = parse_duration(str(duration))
        if dur:
            body["duration_minutes"] = int(dur.total_seconds()) // 60
        elif isinstance(duration, (int, float)):
            body["duration_minutes"] = int(duration)

    updated = store.update_event(event_id, **body)
    if updated is None:
        raise ApiError(404, f"Event not found: {event_id}")
    return json_response({"ok": True, "data": updated})


async def delete_event(request: Request) -> Response:
    """DELETE /api/v1/calendar/events/{id}"""
    event_id = request.match_info.get("id", "")
    store = _get_store()

    try:
        store.delete_event(event_id)
    except ValueError as e:
        raise ApiError(404, str(e))

    return json_response({"ok": True})


async def search_events(request: Request) -> Response:
    """GET /api/v1/calendar/events/search?q=..."""
    query = (request.query.get("q") or "").strip()
    if not query:
        raise ApiError(400, "query parameter 'q' is required")

    store = _get_store()
    results = store.search_events(query)
    return json_response({
        "ok": True,
        "data": {"events": results, "total": len(results)},
    })


async def get_stats(request: Request) -> Response:
    """GET /api/v1/calendar/stats"""
    store = _get_store()
    stats = store.get_stats()
    return json_response({"ok": True, "data": stats})


async def create_reminder(request: Request) -> Response:
    """POST /api/v1/calendar/reminders

    Body:
        title (str) — reminder title
        remind_at (str) — natural language or ISO datetime
        event_id (str, optional) — link to existing event
    """
    body = await _json_body(request)
    store = _get_store()

    title = (body.get("title") or "").strip()
    if not title:
        raise ApiError(400, "title is required")

    remind_at_str = (body.get("remind_at") or "").strip()
    if not remind_at_str:
        raise ApiError(400, "remind_at is required")

    from Calendar import parse_datetime
    parsed = parse_datetime(remind_at_str)
    if parsed and parsed.get("dt"):
        remind_dt = parsed["dt"]
    else:
        try:
            remind_dt = datetime.fromisoformat(remind_at_str)
        except (ValueError, TypeError):
            raise ApiError(400, f"Cannot parse remind_at: {remind_at_str}")

    event_id = body.get("event_id")
    reminder = store.create_reminder(
        event_id=event_id,
        reminder_minutes=-1,  # absolute time reminder
        remind_at=remind_dt,
        title=title,
    )
    return json_response({"ok": True, "data": reminder}, status=201)


async def get_due_reminders(request: Request) -> Response:
    """GET /api/v1/calendar/reminders/due"""
    store = _get_store()
    due = store.get_due_reminders()
    return json_response({
        "ok": True,
        "data": {"reminders": due, "total": len(due)},
    })


async def mark_reminder_fired(request: Request) -> Response:
    """POST /api/v1/calendar/reminders/{id}/mark-fired"""
    reminder_id = request.match_info.get("id", "")
    store = _get_store()

    try:
        store.mark_reminder_fired(reminder_id)
    except ValueError as e:
        raise ApiError(404, str(e))

    return json_response({"ok": True})
