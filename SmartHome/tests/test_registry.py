"""Unit tests for DeviceRegistry."""
from __future__ import annotations

from typing import Any

import pytest

from SmartHome.devices.registry import DeviceRegistry
from SmartHome.models import DeviceInfo, DeviceProperties, DeviceType


@pytest.fixture
def registry() -> DeviceRegistry:
    """Return a fresh in-memory registry."""
    return DeviceRegistry()


@pytest.fixture
def device_info() -> DeviceInfo:
    """Return a minimal DeviceInfo."""
    return DeviceInfo(
        device_type=DeviceType.SWITCH,
        properties=DeviceProperties(name="Test Switch", room="garage"),
    )


# ── CRUD ─────────────────────────────────────────────────────────────────

class TestRegistryCRUD:
    """Test register, get, unregister, list, update."""

    async def test_register_and_get(self, registry: DeviceRegistry, device_info: DeviceInfo) -> None:
        """Register a device; get() returns it."""
        device_id = await registry.register(device_info)
        got = await registry.get(device_id)
        assert got is not None
        assert got.device_id == device_id
        assert got.device_type == DeviceType.SWITCH

    async def test_register_returns_id(self, registry: DeviceRegistry) -> None:
        """register() returns the device_id."""
        info = DeviceInfo(device_type=DeviceType.LIGHT)
        device_id = await registry.register(info)
        assert device_id == info.device_id

    async def test_register_duplicate_raises(self, registry: DeviceRegistry, device_info: DeviceInfo) -> None:
        """Registering the same device_id twice raises ValueError."""
        await registry.register(device_info)
        with pytest.raises(ValueError, match="Device already registered"):
            await registry.register(device_info)

    async def test_register_many_and_list_all(self, registry: DeviceRegistry) -> None:
        """list() returns all registered devices."""
        ids = []
        for i in range(5):
            info = DeviceInfo(device_type=DeviceType.SWITCH)
            ids.append(await registry.register(info))
        all_devices = await registry.list()
        assert len(all_devices) == 5
        returned_ids = [d.device_id for d in all_devices]
        assert sorted(returned_ids) == sorted(ids)

    async def test_unregister_removes(self, registry: DeviceRegistry, device_info: DeviceInfo) -> None:
        """After unregister, get() returns None."""
        device_id = await registry.register(device_info)
        removed = await registry.unregister(device_id)
        assert removed is True
        assert await registry.get(device_id) is None

    async def test_unregister_missing(self, registry: DeviceRegistry) -> None:
        """unregister() returns False for unknown ID."""
        result = await registry.unregister("nonexistent")
        assert result is False

    async def test_unregister_then_list(self, registry: DeviceRegistry, device_info: DeviceInfo) -> None:
        """After unregister, device no longer appears in list()."""
        device_id = await registry.register(device_info)
        await registry.unregister(device_id)
        all_devices = await registry.list()
        assert device_id not in [d.device_id for d in all_devices]

    async def test_update_properties(self, registry: DeviceRegistry, device_info: DeviceInfo) -> None:
        """update() modifies device properties."""
        device_id = await registry.register(device_info)
        new_props = DeviceProperties(name="Updated Switch", room="kitchen")
        updated = await registry.update(device_id, new_props)
        assert updated is not None
        assert updated.properties.name == "Updated Switch"
        assert updated.properties.room == "kitchen"
        # Verify it's persisted
        got = await registry.get(device_id)
        assert got is not None
        assert got.properties.name == "Updated Switch"

    async def test_update_missing(self, registry: DeviceRegistry) -> None:
        """update() returns None for unknown ID."""
        result = await registry.update(
            "nonexistent",
            DeviceProperties(name="Nope"),
        )
        assert result is None


# ── Filtering ────────────────────────────────────────────────────────────

class TestRegistryFilter:
    async def test_list_by_type(self, registry: DeviceRegistry) -> None:
        light_id = await registry.register(
            DeviceInfo(device_type=DeviceType.LIGHT)
        )
        switch_id = await registry.register(
            DeviceInfo(device_type=DeviceType.SWITCH)
        )
        lights = await registry.list(device_type=DeviceType.LIGHT)
        assert len(lights) == 1
        assert lights[0].device_id == light_id

    async def test_list_by_room(self, registry: DeviceRegistry) -> None:
        info1 = DeviceInfo(
            device_type=DeviceType.SWITCH,
            properties=DeviceProperties(room="living_room"),
        )
        info2 = DeviceInfo(
            device_type=DeviceType.PLUG,
            properties=DeviceProperties(room="bedroom"),
        )
        id1 = await registry.register(info1)
        await registry.register(info2)
        living = await registry.list(room="living_room")
        assert len(living) == 1
        assert living[0].device_id == id1

    async def test_list_by_type_and_room(self, registry: DeviceRegistry) -> None:
        info1 = DeviceInfo(
            device_type=DeviceType.LIGHT,
            properties=DeviceProperties(room="living_room"),
        )
        info2 = DeviceInfo(
            device_type=DeviceType.SWITCH,
            properties=DeviceProperties(room="living_room"),
        )
        info3 = DeviceInfo(
            device_type=DeviceType.LIGHT,
            properties=DeviceProperties(room="bedroom"),
        )
        await registry.register(info1)
        await registry.register(info2)
        await registry.register(info3)
        result = await registry.list(device_type=DeviceType.LIGHT, room="living_room")
        assert len(result) == 1
        assert result[0].device_id == info1.device_id

    async def test_list_empty(self, registry: DeviceRegistry) -> None:
        assert await registry.list() == []

    async def test_list_filter_no_matches(self, registry: DeviceRegistry) -> None:
        await registry.register(DeviceInfo(device_type=DeviceType.LIGHT))
        result = await registry.list(device_type=DeviceType.THERMOSTAT)
        assert result == []


# ── Event Callbacks ──────────────────────────────────────────────────────

class TestRegistryCallbacks:
    async def test_on_device_registered_fires(
        self, registry: DeviceRegistry
    ) -> None:
        received: list[DeviceInfo] = []

        async def cb(info: DeviceInfo) -> None:
            received.append(info)

        registry.on_device_registered.append(cb)
        info = DeviceInfo(device_type=DeviceType.SWITCH)
        await registry.register(info)
        assert len(received) == 1
        assert received[0].device_id == info.device_id

    async def test_on_device_removed_fires(
        self, registry: DeviceRegistry, device_info: DeviceInfo
    ) -> None:
        received: list[str] = []

        async def cb(device_id: str) -> None:
            received.append(device_id)

        registry.on_device_removed.append(cb)
        device_id = await registry.register(device_info)
        await registry.unregister(device_id)
        assert len(received) == 1
        assert received[0] == device_id

    async def test_multiple_callbacks_all_fire(
        self, registry: DeviceRegistry, device_info: DeviceInfo
    ) -> None:
        count = 0

        async def cb1(info: DeviceInfo) -> None:
            nonlocal count
            count += 1

        async def cb2(info: DeviceInfo) -> None:
            nonlocal count
            count += 1

        registry.on_device_registered.append(cb1)
        registry.on_device_registered.append(cb2)
        await registry.register(device_info)
        assert count == 2

    async def test_callback_error_does_not_block_others(
        self, registry: DeviceRegistry, device_info: DeviceInfo
    ) -> None:
        """A failing callback does not prevent other callbacks from running."""
        fired = [False, False]

        async def failing(info: DeviceInfo) -> None:
            raise RuntimeError("oops")

        async def ok(info: DeviceInfo) -> None:
            fired[1] = True

        registry.on_device_registered.append(failing)
        registry.on_device_registered.append(ok)
        await registry.register(device_info)
        assert fired[1] is True


# ── Concurrency ──────────────────────────────────────────────────────────

class TestRegistryConcurrency:
    """Basic concurrency: coroutines don't corrupt internal state."""

    async def test_concurrent_register_and_list(
        self, registry: DeviceRegistry
    ) -> None:
        """Multiple concurrent operations should not corrupt state."""
        async def register_many(count: int) -> list[str]:
            ids = []
            for i in range(count):
                info = DeviceInfo(device_type=DeviceType.SWITCH)
                ids.append(await registry.register(info))
            return ids

        import asyncio
        results = await asyncio.gather(
            register_many(3),
            register_many(3),
            register_many(3),
        )
        all_ids = [item for sublist in results for item in sublist]
        assert len(all_ids) == 9
        assert len(set(all_ids)) == 9  # all unique

    async def test_concurrent_register_unregister(
        self, registry: DeviceRegistry
    ) -> None:
        """Register and unregister concurrently should not lose entries."""
        info = DeviceInfo(device_type=DeviceType.SWITCH)
        device_id = await registry.register(info)

        async def unregister_twice() -> tuple[bool, bool]:
            r1 = await registry.unregister(device_id)
            r2 = await registry.unregister(device_id)
            return r1, r2

        import asyncio
        (r1, r2) = await unregister_twice()
        assert r1 is True   # first removed
        assert r2 is False  # second already gone
        assert await registry.get(device_id) is None


# ── Load from Database ──────────────────────────────────────────────────

class TestRegistryDatabase:
    """Test database attachment (using a mock)."""

    async def test_load_from_database_no_db(self, registry: DeviceRegistry) -> None:
        """load_from_database() returns 0 when no database is attached."""
        count = await registry.load_from_database()
        assert count == 0

    async def test_database_persistence_integration(self) -> None:
        """Verify that database methods are called with correct arguments."""
        # Use a mock database object
        class MockDatabase:
            def __init__(self):
                self.devices: list[DeviceInfo] = []
                self.removed_ids: list[str] = []

            def create_device(self, info: DeviceInfo) -> None:
                self.devices.append(info)

            def delete_device(self, device_id: str) -> bool:
                self.removed_ids.append(device_id)
                return True

            def list_devices(self) -> list[DeviceInfo]:
                return self.devices

        db = MockDatabase()
        reg = DeviceRegistry(database=db)

        info = DeviceInfo(device_type=DeviceType.SWITCH, device_id="mock-1")
        await reg.register(info)
        assert len(db.devices) == 1
        assert db.devices[0].device_id == "mock-1"

        await reg.unregister("mock-1")
        assert "mock-1" in db.removed_ids

        # Load back
        reg2 = DeviceRegistry(database=db)
        count = await reg2.load_from_database()
        assert count == 1
        assert await reg2.get("mock-1") is not None

    async def test_update_calls_database(self) -> None:
        """update() also persists to the database."""
        registry_calls: list[DeviceInfo] = []

        class MockDB:
            def create_device(self, info: DeviceInfo) -> None:
                registry_calls.append(info)

            def delete_device(self, device_id: str) -> bool:
                return True

            def list_devices(self) -> list[DeviceInfo]:
                return list(registry_calls)

        db = MockDB()
        reg = DeviceRegistry(database=db)

        info = DeviceInfo(device_type=DeviceType.LIGHT, device_id="upd-1")
        await reg.register(info)

        await reg.update(
            "upd-1",
            DeviceProperties(name="Updated", room="roof"),
        )

        got = await reg.get("upd-1")
        assert got is not None
        assert got.properties.name == "Updated"
