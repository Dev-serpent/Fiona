"""REST API endpoints for scene management."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from aiohttp import web

from SmartHome.models import Scene

from HomeBackend.database import DB_APP_KEY, Database

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


def _get_db(request: web.Request) -> Database:
    db: Optional[Database] = request.app.get(DB_APP_KEY)
    if db is None:
        raise web.HTTPInternalServerError(text="Database not initialised")
    return db


def _serialize_scene(scene: Scene) -> dict[str, Any]:
    return {
        "scene_id": scene.scene_id,
        "name": scene.name,
        "states": scene.states,
        "created_at": scene.created_at.isoformat() if scene.created_at else None,
    }


@routes.get("/api/scenes")
async def list_scenes(request: web.Request) -> web.Response:
    """List all saved scenes."""
    db = _get_db(request)
    scenes = db.list_scenes()
    return web.json_response(
        {"scenes": [_serialize_scene(s) for s in scenes], "count": len(scenes)},
    )


@routes.post("/api/scenes")
async def create_scene(request: web.Request) -> web.Response:
    """Create a new scene.

    Request body (JSON):
        - ``name`` (required): Scene name.
        - ``states`` (optional): Dict of ``{device_id: {state_field: value}}``.
          If omitted, an empty state snapshot is stored.
    """
    db = _get_db(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "Invalid JSON body"}), content_type="application/json")

    name = body.get("name", "").strip()
    if not name:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "Scene name is required"}),
            content_type="application/json",
        )

    states = body.get("states", {})
    scene = Scene(name=name, states=states)
    stored = db.create_scene(scene)
    logger.info("Scene created via API: %s (%s)", stored.scene_id, stored.name)
    return web.json_response(_serialize_scene(stored), status=201)


@routes.get("/api/scenes/{scene_id}")
async def get_scene(request: web.Request) -> web.Response:
    """Get details of a specific scene."""
    db = _get_db(request)
    scene_id = request.match_info["scene_id"]
    scene = db.get_scene(scene_id)
    if scene is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Scene not found: {scene_id}"}),
            content_type="application/json",
        )
    return web.json_response(_serialize_scene(scene))


@routes.delete("/api/scenes/{scene_id}")
async def delete_scene(request: web.Request) -> web.Response:
    """Delete a scene."""
    db = _get_db(request)
    scene_id = request.match_info["scene_id"]
    if not db.delete_scene(scene_id):
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Scene not found: {scene_id}"}),
            content_type="application/json",
        )
    logger.info("Scene deleted via API: %s", scene_id)
    return web.json_response({"status": "deleted", "scene_id": scene_id})


@routes.post("/api/scenes/{scene_id}/activate")
async def activate_scene(request: web.Request) -> web.Response:
    """Activate a scene — apply all stored device states.

    For each device in the scene's state map, the device state is updated
    to the values captured when the scene was created.
    """
    db = _get_db(request)
    scene_id = request.match_info["scene_id"]
    scene = db.get_scene(scene_id)
    if scene is None:
        raise web.HTTPNotFound(
            text=json.dumps({"error": f"Scene not found: {scene_id}"}),
            content_type="application/json",
        )

    applied_devices = []
    errors: list[dict[str, Any]] = []

    for device_id, state_values in scene.states.items():
        device = db.get_device(device_id)
        if device is None:
            errors.append({"device_id": device_id, "error": "Device not found"})
            continue

        # Build a DeviceState from the stored values
        from SmartHome.models import DeviceState

        new_state = DeviceState(
            power=state_values.get("power", device.state.power),
            brightness=state_values.get("brightness", device.state.brightness),
            color_temp=state_values.get("color_temp", device.state.color_temp),
            color=state_values.get("color", device.state.color),
            temperature=state_values.get("temperature", device.state.temperature),
            humidity=state_values.get("humidity", device.state.humidity),
            motion_detected=state_values.get("motion_detected", device.state.motion_detected),
            door_open=state_values.get("door_open", device.state.door_open),
            target_temperature=state_values.get("target_temperature", device.state.target_temperature),
            hvac_mode=state_values.get("hvac_mode", device.state.hvac_mode),
        )
        db.update_device_state(device_id, new_state)
        applied_devices.append(device_id)

    logger.info(
        "Scene activated: %s (%d devices, %d errors)",
        scene_id,
        len(applied_devices),
        len(errors),
    )
    return web.json_response({
        "status": "activated",
        "scene_id": scene_id,
        "applied_devices": applied_devices,
        "errors": errors,
    })
