"""REST API endpoints for room management."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from aiohttp import web

from SmartHome.models import Room

from HomeBackend.database import DB_APP_KEY, Database

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def _get_db(request: web.Request) -> Database:
    db: Optional[Database] = request.app.get(DB_APP_KEY)
    if db is None:
        raise web.HTTPInternalServerError(text="Database not initialised")
    return db


def _serialize_room(room: Room) -> dict[str, Any]:
    return {
        "room_id": room.room_id,
        "name": room.name,
        "floor": room.floor,
        "device_ids": room.device_ids,
    }


@routes.get("/api/rooms")
async def list_rooms(request: web.Request) -> web.Response:
    """List all rooms."""
    db = _get_db(request)
    rooms = db.list_rooms()
    return web.json_response(
        {"rooms": [_serialize_room(r) for r in rooms], "count": len(rooms)},
    )


@routes.post("/api/rooms")
async def create_room(request: web.Request) -> web.Response:
    """Create a new room.

    Request body (JSON):
        - ``name`` (required): Room name.
        - ``floor`` (optional, default ``"1"``): Floor identifier.
    """
    db = _get_db(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    name = body.get("name", "").strip()
    if not name:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Room name is required"}),
            content_type="application/json",
        )

    room = Room(name=name, floor=body.get("floor", "1"))
    stored = db.create_room(room)
    logger.info("Room created via API: %s (%s)", stored.room_id, stored.name)
    return web.json_response(_serialize_room(stored), status=201)


@routes.get("/api/rooms/{room_id}")
async def get_room(request: web.Request) -> web.Response:
    """Get details about a specific room, including its device list."""
    db = _get_db(request)
    room_id = request.match_info["room_id"]
    room = db.get_room(room_id)
    if room is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Room not found: {room_id}"}),
            content_type="application/json",
        )

    # Enrich with device details
    devices = [db.get_device(did) for did in room.device_ids]
    device_summaries = []
    for d in devices:
        if d is not None:
            device_summaries.append({
                "device_id": d.device_id,
                "device_type": d.device_type.value,
                "status": d.status.value,
                "name": d.properties.name,
            })

    result = _serialize_room(room)
    result["devices"] = device_summaries
    return web.json_response(result)


@routes.put("/api/rooms/{room_id}")
async def update_room(request: web.Request) -> web.Response:
    """Update a room's name and/or floor.

    Request body (JSON): partial fields to update.
    """
    db = _get_db(request)
    room_id = request.match_info["room_id"]

    existing = db.get_room(room_id)
    if existing is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Room not found: {room_id}"}),
            content_type="application/json",
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    name = body.get("name", existing.name)
    floor = body.get("floor", existing.floor)

    # We delete and re-insert since room_id is the PK
    updated_room = Room(room_id=room_id, name=name, floor=floor, device_ids=existing.device_ids)
    db.delete_room(room_id)
    db.create_room(updated_room)
    logger.info("Room updated via API: %s", room_id)
    return web.json_response(_serialize_room(updated_room))


@routes.delete("/api/rooms/{room_id}")
async def delete_room(request: web.Request) -> web.Response:
    """Delete a room."""
    db = _get_db(request)
    room_id = request.match_info["room_id"]
    if not db.delete_room(room_id):
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Room not found: {room_id}"}),
            content_type="application/json",
        )
    logger.info("Room deleted via API: %s", room_id)
    return web.json_response({"status": "deleted", "room_id": room_id})


@routes.post("/api/rooms/{room_id}/devices/{device_id}")
async def assign_device_to_room(request: web.Request) -> web.Response:
    """Assign a device to a room."""
    db = _get_db(request)
    room_id = request.match_info["room_id"]
    device_id = request.match_info["device_id"]

    # Verify both exist
    room = db.get_room(room_id)
    if room is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Room not found: {room_id}"}),
            content_type="application/json",
        )
    device = db.get_device(device_id)
    if device is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )

    db.assign_device_to_room(device_id, room_id)
    logger.info("Device %s assigned to room %s", device_id, room_id)
    return web.json_response({"status": "assigned", "room_id": room_id, "device_id": device_id})
