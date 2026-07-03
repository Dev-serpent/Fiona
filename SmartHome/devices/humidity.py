"""Humidity sensor driver — reads relative humidity percentage."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType


class HumiditySensorDriver(BaseDeviceDriver):
    """Driver for a humidity sensor.

    State fields:
        * ``humidity`` (:class:`float`) — relative humidity in % (0–100).

    .. note::

        In virtual mode ``set_state()`` is accepted for testing.  In
        production with a real sensor, writes would be rejected.
    """

    DEVICE_TYPE = DeviceType.HUMIDITY_SENSOR

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set humidity state (virtual / test mode only)."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate humidity sensor state fields."""
        if "humidity" in state:
            hum = state["humidity"]
            if not isinstance(hum, (int, float)):
                raise ValueError("HumiditySensor 'humidity' must be a number")
            if hum < 0.0 or hum > 100.0:
                raise ValueError(
                    f"HumiditySensor 'humidity' {hum} out of range [0, 100]"
                )


__all__ = ["HumiditySensorDriver"]
