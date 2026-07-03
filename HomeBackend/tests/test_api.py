"""Integration tests for the HomeBackend REST API."""
from __future__ import annotations

import os
import tempfile
from typing import Any

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from HomeBackend.config import DatabaseConfig, ServerConfig
from HomeBackend.server import HomeBackendServer


class HomeBackendAPITests(AioHTTPTestCase):
    """Integration test suite using aiohttp test utilities.

    Each test gets a fresh server with a temporary database file.
    """

    async def get_application(self):
        """Set up a fresh HomeBackendServer with a temporary database."""
        self._db_fd, self._db_path = tempfile.mkstemp(suffix=".db", prefix="hb_test_")
        os.close(self._db_fd)  # we only need the path

        config = ServerConfig(
            database=DatabaseConfig(db_path=self._db_path),
        )
        self._backend = HomeBackendServer(config)
        self._backend.db.connect()
        return self._backend.app

    async def tearDownAsync(self):
        """Clean up the temporary database."""
        if hasattr(self, "_backend"):
            self._backend.db.close()
        if hasattr(self, "_db_path"):
            for ext in ("", "-wal", "-shm"):
                try:
                    os.remove(self._db_path + ext)
                except FileNotFoundError:
                    pass

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _create_device(
        self,
        device_type: str = "switch",
        **extra: Any,
    ) -> dict[str, Any]:
        payload = {"device_type": device_type, **extra}
        resp = await self.client.post("/api/devices", json=payload)
        assert resp.status == 201, await resp.text()
        return await resp.json()

    async def _get_db(self):
        """Access the database instance for direct operations in tests."""
        return self._backend.db

    # ── Health ─────────────────────────────────────────────────────────────

    async def test_health(self):
        """Liveness probe should return 200."""
        resp = await self.client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "homebackend"

    async def test_readiness(self):
        """Readiness probe should return 200 when DB is connected."""
        resp = await self.client.get("/api/health/ready")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ready"

    # ── Device CRUD ────────────────────────────────────────────────────────

    async def test_create_device(self):
        """A device can be created and returns the full descriptor."""
        data = await self._create_device("light", properties={"name": "Living Room Light"})
        assert data["device_id"] is not None
        assert data["device_type"] == "light"
        assert data["properties"]["name"] == "Living Room Light"
        assert data["status"] == "offline"

    async def test_get_device(self):
        """A device can be retrieved by its device_id."""
        created = await self._create_device("motion_sensor")
        device_id = created["device_id"]

        resp = await self.client.get(f"/api/devices/{device_id}")
        assert resp.status == 200
        data = await resp.json()
        assert data["device_id"] == device_id

    async def test_list_devices(self):
        """Listing devices returns all registered devices."""
        await self._create_device("light")
        await self._create_device("switch")
        resp = await self.client.get("/api/devices")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 2

    async def test_list_devices_filtered(self):
        """Listing devices with type filter returns matching devices only."""
        await self._create_device("light")
        await self._create_device("switch")
        resp = await self.client.get("/api/devices?type=light")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 1
        assert data["devices"][0]["device_type"] == "light"

    async def test_update_device(self):
        """A device's properties can be updated."""
        created = await self._create_device("switch", properties={"name": "Old Name"})
        device_id = created["device_id"]

        resp = await self.client.put(
            f"/api/devices/{device_id}",
            json={"properties": {"name": "New Name"}},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["properties"]["name"] == "New Name"

    async def test_delete_device(self):
        """A device can be deleted."""
        created = await self._create_device("plug")
        device_id = created["device_id"]

        resp = await self.client.delete(f"/api/devices/{device_id}")
        assert resp.status == 200

        # Verify it's gone
        resp = await self.client.get(f"/api/devices/{device_id}")
        assert resp.status == 404

    async def test_device_state(self):
        """Device state can be read and updated."""
        created = await self._create_device("light")
        device_id = created["device_id"]

        # Read initial state
        resp = await self.client.get(f"/api/devices/{device_id}/state")
        assert resp.status == 200
        state = await resp.json()
        assert state["power"] is None

        # Update state
        resp = await self.client.put(
            f"/api/devices/{device_id}/state",
            json={"power": True, "brightness": 75},
        )
        assert resp.status == 200
        state = await resp.json()
        assert state["power"] is True
        assert state["brightness"] == 75

    # ── 404 Handling ───────────────────────────────────────────────────────

    async def test_404_device(self):
        """Requesting a nonexistent device returns 404."""
        resp = await self.client.get("/api/devices/nonexistent")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    async def test_404_room(self):
        """Requesting a nonexistent room returns 404."""
        resp = await self.client.get("/api/rooms/nonexistent")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    async def test_404_scene(self):
        """Requesting a nonexistent scene returns 404."""
        resp = await self.client.get("/api/scenes/nonexistent")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    # ── 400 Handling ───────────────────────────────────────────────────────

    async def test_400_invalid_device_type(self):
        """Creating a device with an invalid type returns 400."""
        resp = await self.client.post("/api/devices", json={"device_type": "invalid_type"})
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    async def test_400_empty_body(self):
        """Creating a device with an empty body returns 400."""
        resp = await self.client.post("/api/devices", json={})
        assert resp.status == 400

    # ── Rooms ──────────────────────────────────────────────────────────────

    async def test_create_room(self):
        """A room can be created."""
        resp = await self.client.post("/api/rooms", json={"name": "Living Room", "floor": "1"})
        assert resp.status == 201
        data = await resp.json()
        assert data["name"] == "Living Room"
        assert data["floor"] == "1"

    async def test_list_rooms(self):
        """Listing rooms returns all rooms."""
        await self.client.post("/api/rooms", json={"name": "Kitchen"})
        await self.client.post("/api/rooms", json={"name": "Bedroom"})
        resp = await self.client.get("/api/rooms")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 2

    async def test_get_room_with_devices(self):
        """Getting a room returns its device details."""
        # Create a room
        room_resp = await self.client.post("/api/rooms", json={"name": "Office"})
        room = await room_resp.json()
        room_id = room["room_id"]

        # Create a device and assign it
        device = await self._create_device("switch")
        device_id = device["device_id"]

        await self.client.post(f"/api/rooms/{room_id}/devices/{device_id}")

        # Get room details
        resp = await self.client.get(f"/api/rooms/{room_id}")
        assert resp.status == 200
        data = await resp.json()
        assert device_id in data["device_ids"]
        assert len(data["devices"]) == 1
        assert data["devices"][0]["device_id"] == device_id

    async def test_delete_room(self):
        """A room can be deleted."""
        resp = await self.client.post("/api/rooms", json={"name": "Delete Me"})
        room = await resp.json()
        room_id = room["room_id"]

        resp = await self.client.delete(f"/api/rooms/{room_id}")
        assert resp.status == 200

        resp = await self.client.get(f"/api/rooms/{room_id}")
        assert resp.status == 404

    async def test_update_room(self):
        """A room can be renamed."""
        resp = await self.client.post("/api/rooms", json={"name": "Old Name", "floor": "1"})
        room = await resp.json()
        room_id = room["room_id"]

        resp = await self.client.put(
            f"/api/rooms/{room_id}",
            json={"name": "New Name", "floor": "2"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["name"] == "New Name"
        assert data["floor"] == "2"

    # ── Scenes ─────────────────────────────────────────────────────────────

    async def test_create_scene(self):
        """A scene can be created."""
        device1 = await self._create_device("light")
        device2 = await self._create_device("switch")

        states = {
            device1["device_id"]: {"power": True, "brightness": 80},
            device2["device_id"]: {"power": False},
        }

        resp = await self.client.post("/api/scenes", json={"name": "Evening", "states": states})
        assert resp.status == 201
        data = await resp.json()
        assert data["name"] == "Evening"
        assert data["states"] == states

    async def test_activate_scene(self):
        """Activating a scene applies stored states to devices."""
        device = await self._create_device("light")
        device_id = device["device_id"]

        # Create a scene with desired states
        states = {device_id: {"power": True, "brightness": 100}}
        scene_resp = await self.client.post("/api/scenes", json={"name": "Full Bright", "states": states})
        scene = await scene_resp.json()
        scene_id = scene["scene_id"]

        # Activate the scene
        resp = await self.client.post(f"/api/scenes/{scene_id}/activate")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "activated"
        assert device_id in data["applied_devices"]

        # Verify device state was updated
        state_resp = await self.client.get(f"/api/devices/{device_id}/state")
        state = await state_resp.json()
        assert state["power"] is True
        assert state["brightness"] == 100

    async def test_delete_scene(self):
        """A scene can be deleted."""
        resp = await self.client.post("/api/scenes", json={"name": "Temp Scene"})
        scene = await resp.json()
        scene_id = scene["scene_id"]

        resp = await self.client.delete(f"/api/scenes/{scene_id}")
        assert resp.status == 200

        resp = await self.client.get(f"/api/scenes/{scene_id}")
        assert resp.status == 404

    # ── Events ─────────────────────────────────────────────────────────────

    async def test_list_events(self):
        """Events can be listed after being stored."""
        from SmartHome.models import DeviceEvent

        db = await self._get_db()
        event = DeviceEvent(device_id="test-device", event_type="state_changed", data={"power": True})
        db.store_event(event)

        resp = await self.client.get("/api/events")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 1
        assert data["events"][0]["device_id"] == "test-device"
        assert data["events"][0]["event_type"] == "state_changed"

    async def test_list_events_filtered(self):
        """Events can be filtered by device_id."""
        from SmartHome.models import DeviceEvent

        db = await self._get_db()
        db.store_event(DeviceEvent(device_id="device-a", event_type="state_changed"))
        db.store_event(DeviceEvent(device_id="device-b", event_type="state_changed"))

        resp = await self.client.get("/api/events?device_id=device-a")
        assert resp.status == 200
        data = await resp.json()
        assert data["count"] == 1
        assert data["events"][0]["device_id"] == "device-a"

    async def test_clear_events(self):
        """Events can be cleared."""
        from SmartHome.models import DeviceEvent

        db = await self._get_db()
        db.store_event(DeviceEvent(device_id="test", event_type="test"))
        db.store_event(DeviceEvent(device_id="test2", event_type="test"))

        resp = await self.client.delete("/api/events")
        assert resp.status == 200
        data = await resp.json()
        assert data["deleted"] == 2

        resp = await self.client.get("/api/events")
        data = await resp.json()
        assert data["count"] == 0
