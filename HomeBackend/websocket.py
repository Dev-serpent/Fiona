"""WebSocket handler for real-time device event streaming."""
from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web, WSMsgType

logger = logging.getLogger(__name__)

# ── Connected clients ─────────────────────────────────────────────────────────

_ws_clients: set[web.WebSocketResponse] = set()
"""Set of all currently-connected WebSocket peers."""


# ── Handler ───────────────────────────────────────────────────────────────────


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle an incoming WebSocket connection.

    Supports the following incoming JSON messages:

    - ``{"type": "ping"}`` → responds with ``{"type": "pong"}``
    - ``{"type": "subscribe", "device_id": "..."}`` — reserved for future use
    """
    ws = web.WebSocketResponse(heartbeat=30.0)
    await ws.prepare(request)
    _ws_clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_ws_clients))

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await ws.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    # Reserved for future use — acknowledge the subscription
                    device_id = data.get("device_id", "")
                    await ws.send_json({
                        "type": "subscribed",
                        "device_id": device_id,
                    })
                else:
                    await ws.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

            elif msg.type == WSMsgType.ERROR:
                logger.error("WebSocket error: %s", ws.exception())
    finally:
        _ws_clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(_ws_clients))

    return ws


# ── Broadcast ─────────────────────────────────────────────────────────────────


async def broadcast_event(event_data: dict[str, Any]) -> None:
    """Broadcast a device event to all connected WebSocket clients.

    Each client receives: ``{"type": "event", "data": {event_data}}``

    Disconnected clients are automatically pruned.
    """
    if not _ws_clients:
        return

    message = json.dumps({"type": "event", "data": event_data})
    disconnected: list[web.WebSocketResponse] = []

    for ws in _ws_clients:
        try:
            await ws.send_str(message)
        except (ConnectionError, ValueError, OSError):
            disconnected.append(ws)

    for ws in disconnected:
        _ws_clients.discard(ws)
        logger.debug("Pruned disconnected WebSocket client")
