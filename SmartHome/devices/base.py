"""Abstract base device driver with common lifecycle management.

All concrete device drivers should inherit from :class:`BaseDeviceDriver`
to get standardised connect / disconnect / ping behaviour and built-in
event publishing.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from SmartHome.errors import DeviceTimeoutError
from SmartHome.events import EventBus
from SmartHome.interfaces import IDeviceDriver
from SmartHome.models import DeviceEvent, DeviceInfo, DeviceProperties, DeviceState, DeviceType


class BaseDeviceDriver(IDeviceDriver):
    """Base implementation for all device drivers.

    Provides:
    * Lifecycle tracking (``_connected`` flag)
    * An optional reference to the platform :class:`EventBus`
    * A convenience helper for publishing device events
    * Stub ``connect`` / ``disconnect`` / ``ping`` that subclasses override
    * Serialisation via :meth:`to_payload` / :meth:`from_payload`
    """

    DEVICE_TYPE: ClassVar[DeviceType] = DeviceType.SWITCH

    def __init__(self, device_info: DeviceInfo) -> None:
        self._device_info = device_info
        self._connected = False
        self._event_bus: Optional[EventBus] = None

    # ── IDeviceDriver properties ──────────────────────────────────────────

    @property
    def device_info(self) -> DeviceInfo:
        """Return the :class:`DeviceInfo` descriptor for this driver."""
        return self._device_info

    @property
    def is_connected(self) -> bool:
        """``True`` when the driver currently holds an active connection."""
        return self._connected

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Establish the connection to the device.

        Subclasses **must** override this method.  The default
        implementation always succeeds (used for testing / virtual devices).
        """
        self._connected = True
        return True

    async def disconnect(self) -> None:
        """Tear down the connection to the device.

        Subclasses should override to release resources.
        """
        self._connected = False

    async def ping(self) -> bool:
        """Health-check the device connection.

        The default returns the current value of :attr:`is_connected`.
        Subclasses may implement a more thorough check.
        """
        return self._connected

    # ── State ─────────────────────────────────────────────────────────────

    async def get_state(self) -> DeviceState:
        """Read the current device state.

        Subclasses **must** override this method.
        """
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Send a command / state update to the device.

        The base implementation:
        1. Calls :meth:`_validate_state` (subclasses may raise :exc:`ValueError`).
        2. Updates :attr:`_device_info.state` in-place with the provided dict.
        3. Publishes a ``state_changed`` event if an :class:`EventBus` is attached.
        4. Returns ``True``.

        Subclasses may send the delta to a physical device before updating
        the local copy.
        """
        self._validate_state(state)
        for key, value in state.items():
            if hasattr(self._device_info.state, key):
                setattr(self._device_info.state, key, value)
        await self._publish_event("state_changed", state)
        return True

    # ── Event helpers ─────────────────────────────────────────────────────

    def set_event_bus(self, bus: EventBus) -> None:
        """Attach an :class:`EventBus` so the driver can publish events."""
        self._event_bus = bus

    async def _publish_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Create a :class:`DeviceEvent` and publish it on the event bus.

        If no event bus has been attached via :meth:`set_event_bus`, this
        is a no-op.
        """
        if self._event_bus is None:
            return

        event = DeviceEvent(
            device_id=self._device_info.device_id,
            event_type=event_type,
            data=data,
        )
        await self._event_bus.publish(event)

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_payload(self) -> dict[str, Any]:
        """Serialise the driver's current state to a JSON-safe dictionary.

        The payload format::

            {
                "device_id": "...",
                "device_type": "switch",
                "state": {"power": True, ...},   # only non-None fields
                "properties": {"name": "...", ...},
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        """
        state_dict: dict[str, Any] = {}
        for field_name in ("power", "brightness", "color_temp", "color",
                           "temperature", "humidity", "motion_detected",
                           "door_open", "target_temperature", "hvac_mode"):
            val = getattr(self._device_info.state, field_name, None)
            if val is not None:
                state_dict[field_name] = val

        props = self._device_info.properties
        return {
            "device_id": self._device_info.device_id,
            "device_type": self.DEVICE_TYPE.value,
            "state": state_dict,
            "properties": {
                "name": props.name,
                "room": props.room,
                "location": props.location,
                "manufacturer": props.manufacturer,
                "model": props.model,
                "firmware_version": props.firmware_version,
                "poll_interval": props.poll_interval,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> BaseDeviceDriver:
        """Create a driver instance from a payload dictionary.

        Missing fields are replaced with defaults.  The ``device_type`` in
        the payload is ignored — the caller's class determines the type.
        """
        state_data = payload.get("state", {})
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

        raw_props = payload.get("properties", {})
        properties = DeviceProperties(
            name=raw_props.get("name", ""),
            room=raw_props.get("room", "default"),
            location=raw_props.get("location", ""),
            manufacturer=raw_props.get("manufacturer", "Fiona IoT"),
            model=raw_props.get("model", "v1"),
            firmware_version=raw_props.get("firmware_version", "1.0.0"),
            poll_interval=raw_props.get("poll_interval", 60),
        )

        device_info = DeviceInfo(
            device_id=payload.get("device_id", ""),
            device_type=cls.DEVICE_TYPE,
            properties=properties,
            state=state,
        )

        return cls(device_info)

    # ── Validation hook ───────────────────────────────────────────────────

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate an incoming state dict before applying it.

        Subclasses **should** override this method to enforce type-specific
        constraints (e.g. brightness range, colour format).  The base
        implementation is a no-op.

        Raises :exc:`ValueError` if any field is invalid.
        """
        # No-op in the base class.
        _ = state
