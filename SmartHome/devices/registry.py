"""In-memory device registry with optional database persistence.

Implements :class:`SmartHome.interfaces.IDeviceRegistry`.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from typing import Any, Optional

from SmartHome.interfaces import EventHandler, IDeviceRegistry
from SmartHome.models import DeviceInfo, DeviceProperties, DeviceType

logger = logging.getLogger(__name__)


class DeviceRegistry(IDeviceRegistry):
    """Thread-safe in-memory device registry.

    Stores :class:`DeviceInfo` objects in a dict keyed by ``device_id``.
    All public mutating methods are serialised through an :class:`asyncio.Lock`
    to prevent race conditions between concurrent coroutines.

    Optionally attaches a synchronous ``Database`` instance for persistence.
    When attached, every register / unregister / update call is also applied
    to the database.

    Usage::

        registry = DeviceRegistry()
        device_id = await registry.register(DeviceInfo(...))
        info = await registry.get(device_id)
        await registry.unregister(device_id)
    """

    def __init__(self, database: Any = None) -> None:
        self._devices: dict[str, DeviceInfo] = {}
        self._lock = asyncio.Lock()
        self._database = database

        # Event callback lists (mutable — callers can append / remove)
        self._on_device_registered: list[EventHandler] = []
        self._on_device_removed: list[EventHandler] = []

    # ── Callback lists (interface properties) ────────────────────────────

    @property
    def on_device_registered(self) -> list[EventHandler]:
        """List of callbacks invoked when a new device is registered.

        Each handler receives the :class:`DeviceInfo` of the newly-registered
        device as its sole positional argument.
        """
        return self._on_device_registered

    @property
    def on_device_removed(self) -> list[EventHandler]:
        """List of callbacks invoked when a device is removed.

        Each handler receives the ``device_id`` string of the removed device
        as its sole positional argument.
        """
        return self._on_device_removed

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def register(self, device_info: DeviceInfo) -> str:
        """Register a device in the registry.

        Args:
            device_info: The :class:`DeviceInfo` describing the device.

        Returns:
            The ``device_id`` assigned to the device.

        Raises:
            ValueError: If a device with the same ``device_id`` is already
                registered.
        """
        async with self._lock:
            if device_info.device_id in self._devices:
                raise ValueError(
                    f"Device already registered: {device_info.device_id}"
                )
            self._devices[device_info.device_id] = device_info
            did = device_info.device_id

        # Persist to database (outside lock to avoid blocking).
        await self._persist_device(device_info)

        # Fire callbacks (outside lock to avoid deadlocks).
        await self._fire_callbacks(self._on_device_registered, device_info)

        logger.info("Device registered: %s (%s)", did, device_info.device_type)
        return did

    async def unregister(self, device_id: str) -> bool:
        """Remove a device from the registry.

        Returns:
            ``True`` if the device was found and removed, ``False`` otherwise.
        """
        async with self._lock:
            info = self._devices.pop(device_id, None)
            if info is None:
                return False

        # Remove from database (outside lock).
        await self._remove_persisted(device_id)

        # Fire callbacks (outside lock).
        await self._fire_callbacks(self._on_device_removed, device_id)

        logger.info("Device unregistered: %s", device_id)
        return True

    async def get(self, device_id: str) -> Optional[DeviceInfo]:
        """Look up a device by its *device_id*.

        Returns:
            The :class:`DeviceInfo` or ``None`` if not found.
        """
        return self._devices.get(device_id)

    async def list(
        self,
        device_type: Optional[DeviceType] = None,
        room: Optional[str] = None,
    ) -> list[DeviceInfo]:
        """List registered devices, optionally filtered by type and/or room.

        When both filters are given, only devices matching **both** criteria
        are returned (logical AND).
        """
        result: list[DeviceInfo] = []
        for info in self._devices.values():
            if device_type is not None and info.device_type != device_type:
                continue
            if room is not None and info.properties.room != room:
                continue
            result.append(info)
        return result

    async def update(
        self,
        device_id: str,
        properties: DeviceProperties,
    ) -> Optional[DeviceInfo]:
        """Update the configurable properties of a registered device.

        Args:
            device_id: The device to update.
            properties: New :class:`DeviceProperties` to apply.

        Returns:
            The updated :class:`DeviceInfo` or ``None`` if the device does
            not exist.
        """
        async with self._lock:
            info = self._devices.get(device_id)
            if info is None:
                return None
            info.properties = copy.copy(properties)

        # Persist update to database (outside lock).
        await self._persist_device(info)

        return info

    # ── Bulk load ────────────────────────────────────────────────────────

    async def load_from_database(self) -> int:
        """Populate the in-memory store from the attached database.

        Returns:
            The number of devices loaded.

        Calling this method is safe even if the registry already contains
        devices — in-memory devices take precedence (no overwrite).
        """
        if self._database is None:
            return 0

        db_devices: list[DeviceInfo] = await asyncio.to_thread(
            self._database.list_devices
        )
        loaded = 0
        for info in db_devices:
            if info.device_id not in self._devices:
                self._devices[info.device_id] = info
                loaded += 1
        logger.info("Loaded %d devices from database", loaded)
        return loaded

    # ── Private helpers ──────────────────────────────────────────────────

    async def _persist_device(self, device_info: DeviceInfo) -> None:
        """Write *device_info* to the database (if attached)."""
        if self._database is None:
            return
        try:
            await asyncio.to_thread(
                self._database.create_device, device_info
            )
        except Exception:
            logger.warning(
                "Failed to persist device %s to database",
                device_info.device_id,
                exc_info=True,
            )

    async def _remove_persisted(self, device_id: str) -> None:
        """Remove *device_id* from the database (if attached)."""
        if self._database is None:
            return
        try:
            await asyncio.to_thread(self._database.delete_device, device_id)
        except Exception:
            logger.warning(
                "Failed to remove device %s from database",
                device_id,
                exc_info=True,
            )

    async def _fire_callbacks(
        self,
        handlers: list[EventHandler],
        *args: Any,
    ) -> None:
        """Invoke each handler in *handlers* with *args*.

        Exceptions from individual handlers are logged and swallowed so
        that one failing callback does not break subsequent callbacks or
        the calling operation.
        """
        for handler in list(handlers):
            try:
                await handler(*args)
            except Exception:
                logger.exception(
                    "DeviceRegistry callback %r raised an error", handler
                )


__all__ = ["DeviceRegistry"]
