"""REST API endpoints for device event history."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from aiohttp import web

from SmartHome.models import DeviceEvent

from HomeBackend.database import DB_APP_KEY, Database

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def _get_db(request: web.Request) -> Database:
    db: Optional[Database] = request.app.get(DB_APP_KEY)
    if db is None:
        raise web.HTTPInternalServerError(text="Database not initialised")
    return db


def _serialize_event(event: DeviceEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "device_id": event.device_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        "data": event.data,
    }


@routes.get("/api/events")
async def list_events(request: web.Request) -> web.Response:
    """List recent events.

    Query parameters:
        - ``device_id`` (optional): Filter by device.
        - ``limit`` (optional, default 100): Maximum number of events.
    """
    db = _get_db(request)
    device_id = request.query.get("device_id")
    try:
        limit = int(request.query.get("limit", "100"))
    except ValueError:
        limit = 100
    if limit < 1:
        limit = 100
    if limit > 1000:
        limit = 1000

    events = db.list_events(device_id=device_id, limit=limit)
    return web.json_response({
        "events": [_serialize_event(e) for e in events],
        "count": len(events),
    })


@routes.delete("/api/events")
async def clear_events(request: web.Request) -> web.Response:
    """Clear all stored events."""
    db = _get_db(request)
    count = db.clear_events()
    logger.info("Events cleared via API (%d deleted)", count)
    return web.json_response({"status": "cleared", "deleted": count})
