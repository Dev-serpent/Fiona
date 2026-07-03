"""REST API endpoints for device CRUD and state management."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from aiohttp import web

from SmartHome.errors import DeviceNotFoundError
from SmartHome.models import (
    DeviceEvent,
    DeviceInfo,
    DeviceProperties,
    DeviceState,
    DeviceStatus,
    DeviceType,
)

from HomeBackend.database import DB_APP_KEY, Database

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def _get_db(request: web.Request) -> Database:
    """Shortcut to retrieve the database instance from the app."""
    db: Optional[Database] = request.app.get(DB_APP_KEY)
    if db is None:
        raise web.HTTPInternalServerError(text="Database not initialised")
    return db


def _new_uuid() -> str:
    """Generate a fresh hex UUID string."""
    from uuid import uuid4
    return uuid4().hex


def _parse_device_info(body: dict[str, Any]) -> DeviceInfo:
    """Parse a JSON body into a ``DeviceInfo``, raising 400 on invalid data."""
    device_type_str = body.get("device_type", "switch")
    try:
        device_type = DeviceType(device_type_str)
    except ValueError:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": f"Invalid device_type: {device_type_str}"}),
            content_type="application/json",
        )

    props_data = body.get("properties", {})
    properties = DeviceProperties(
        name=props_data.get("name", ""),
        room=props_data.get("room", "default"),
        location=props_data.get("location", ""),
        manufacturer=props_data.get("manufacturer", "Fiona IoT"),
        model=props_data.get("model", "v1"),
        firmware_version=props_data.get("firmware_version", "1.0.0"),
        poll_interval=props_data.get("poll_interval", 60),
    )

    state_data = body.get("state", {})
    state = DeviceState(
        power=state_data.get("power"),
        brightness=state_data.get("brightness"),
        color_temp=state_data.get("color_temp"),
        color=state_data.get("color"),
        temperature=state_data.get("temperature"),
        humidity=state_data.get("humidity"),
        motion_detected=state_data.get("motion_detected"),
        door_open=state_data.get("door_open"),
        target_temperature=state_data.get("target_temperature"),
        hvac_mode=state_data.get("hvac_mode"),
    )

    tags = body.get("tags", [])

    status_str = body.get("status", "offline")
    try:
        status = DeviceStatus(status_str)
    except ValueError:
        status = DeviceStatus.OFFLINE

    # Generate a device_id if none was provided (avoid empty-string PK collisions)
    raw_id = body.get("device_id")
    device_id = raw_id if raw_id else _new_uuid()

    return DeviceInfo(
        device_id=device_id,
        device_type=device_type,
        status=status,
        properties=properties,
        state=state,
        tags=tags,
    )


def _serialize_device(info: DeviceInfo) -> dict[str, Any]:
    """Convert a ``DeviceInfo`` to a JSON-serialisable dict."""
    return {
        "device_id": info.device_id,
        "device_type": info.device_type.value,
        "status": info.status.value,
        "properties": {
            "name": info.properties.name,
            "room": info.properties.room,
            "location": info.properties.location,
            "manufacturer": info.properties.manufacturer,
            "model": info.properties.model,
            "firmware_version": info.properties.firmware_version,
            "poll_interval": info.properties.poll_interval,
        },
        "state": {
            "power": info.state.power,
            "brightness": info.state.brightness,
            "color_temp": info.state.color_temp,
            "color": info.state.color,
            "temperature": info.state.temperature,
            "humidity": info.state.humidity,
            "motion_detected": info.state.motion_detected,
            "door_open": info.state.door_open,
            "target_temperature": info.state.target_temperature,
            "hvac_mode": info.state.hvac_mode,
        },
        "last_seen": info.last_seen.isoformat() if info.last_seen else None,
        "created_at": info.created_at.isoformat() if info.created_at else None,
        "tags": info.tags,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@routes.get("/api/devices")
async def list_devices(request: web.Request) -> web.Response:
    """List all devices, optionally filtered by ``?type=...&room=...``."""
    db = _get_db(request)
    device_type = request.query.get("type")
    room = request.query.get("room")
    devices = db.list_devices(device_type=device_type, room=room)
    return web.json_response(
        {"devices": [_serialize_device(d) for d in devices], "count": len(devices)},
    )


@routes.post("/api/devices")
async def create_device(request: web.Request) -> web.Response:
    """Register a new device.

    Request body (JSON):
        - ``device_type`` (required): one of the ``DeviceType`` values.
        - ``properties`` (optional): device metadata.
        - ``state`` (optional): initial device state.
        - ``tags`` (optional): list of string tags.
    """
    db = _get_db(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    if not body:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Empty request body"}), content_type="application/json")

    info = _parse_device_info(body)
    stored = db.create_device(info)
    logger.info("Device created via API: %s", stored.device_id)
    return web.json_response(_serialize_device(stored), status=201)


@routes.get("/api/devices/{device_id}")
async def get_device(request: web.Request) -> web.Response:
    """Get detailed information about a specific device."""
    db = _get_db(request)
    device_id = request.match_info["device_id"]
    device = db.get_device(device_id)
    if device is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )
    return web.json_response(_serialize_device(device))


@routes.put("/api/devices/{device_id}")
async def update_device(request: web.Request) -> web.Response:
    """Update a device's properties and/or status.

    Request body (JSON): partial fields to update.
    """
    db = _get_db(request)
    device_id = request.match_info["device_id"]

    existing = db.get_device(device_id)
    if existing is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    # Build updated values
    if "status" in body:
        try:
            new_status = DeviceStatus(body["status"])
            db.update_device(device_id, status=new_status.value)
        except ValueError:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": f"Invalid status: {body['status']}"}),
                content_type="application/json",
            )

    if "properties" in body:
        props = body["properties"]
        existing.properties.name = props.get("name", existing.properties.name)
        existing.properties.room = props.get("room", existing.properties.room)
        existing.properties.location = props.get("location", existing.properties.location)
        existing.properties.manufacturer = props.get("manufacturer", existing.properties.manufacturer)
        existing.properties.model = props.get("model", existing.properties.model)
        existing.properties.firmware_version = props.get("firmware_version", existing.properties.firmware_version)
        existing.properties.poll_interval = props.get("poll_interval", existing.properties.poll_interval)
        db.update_device(device_id, properties=json.dumps({
            "name": existing.properties.name,
            "room": existing.properties.room,
            "location": existing.properties.location,
            "manufacturer": existing.properties.manufacturer,
            "model": existing.properties.model,
            "firmware_version": existing.properties.firmware_version,
            "poll_interval": existing.properties.poll_interval,
        }))

    if "tags" in body:
        db.update_device(device_id, tags=json.dumps(body["tags"]))

    updated = db.get_device(device_id)
    assert updated is not None  # we just verified existence
    return web.json_response(_serialize_device(updated))


@routes.delete("/api/devices/{device_id}")
async def delete_device(request: web.Request) -> web.Response:
    """Remove a device from the registry."""
    db = _get_db(request)
    device_id = request.match_info["device_id"]
    if not db.delete_device(device_id):
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )
    logger.info("Device deleted via API: %s", device_id)
    return web.json_response({"status": "deleted", "device_id": device_id})


@routes.get("/api/devices/{device_id}/state")
async def get_device_state(request: web.Request) -> web.Response:
    """Get the current state of a device."""
    db = _get_db(request)
    device_id = request.match_info["device_id"]
    device = db.get_device(device_id)
    if device is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )
    return web.json_response(_serialize_device(device)["state"])


@routes.put("/api/devices/{device_id}/state")
async def update_device_state(request: web.Request) -> web.Response:
    """Update a device's state (e.g. turn on/off, set brightness)."""
    db = _get_db(request)
    device_id = request.match_info["device_id"]

    existing = db.get_device(device_id)
    if existing is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Device not found: {device_id}"}),
            content_type="application/json",
        )

    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    # Merge incoming state with existing state
    current_state = existing.state
    new_state = DeviceState(
        power=body.get("power", current_state.power),
        brightness=body.get("brightness", current_state.brightness),
        color_temp=body.get("color_temp", current_state.color_temp),
        color=body.get("color", current_state.color),
        temperature=body.get("temperature", current_state.temperature),
        humidity=body.get("humidity", current_state.humidity),
        motion_detected=body.get("motion_detected", current_state.motion_detected),
        door_open=body.get("door_open", current_state.door_open),
        target_temperature=body.get("target_temperature", current_state.target_temperature),
        hvac_mode=body.get("hvac_mode", current_state.hvac_mode),
    )

    db.update_device_state(device_id, new_state)

    # Update last_seen
    db.update_device(device_id, last_seen=datetime.now(timezone.utc).isoformat())

    updated = db.get_device(device_id)
    assert updated is not None
    logger.info("Device state updated via API: %s", device_id)
    return web.json_response(_serialize_device(updated)["state"])
