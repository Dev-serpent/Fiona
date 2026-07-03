"""Door sensor driver — detects whether a door is open or closed."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType


class DoorSensorDriver(BaseDeviceDriver):
    """Driver for a door / window contact sensor.

    State fields:
        * ``door_open`` (:class:`bool`) — ``True`` when the door is open.

    .. note::

        In virtual mode ``set_state()`` is accepted for testing.  In
        production with a real sensor, writes would be rejected.
    """

    DEVICE_TYPE = DeviceType.DOOR_SENSOR

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set door state (virtual / test mode only)."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate door sensor state fields."""
        if "door_open" in state and not isinstance(state["door_open"], bool):
            raise ValueError("DoorSensor 'door_open' must be a boolean")


__all__ = ["DoorSensorDriver"]
