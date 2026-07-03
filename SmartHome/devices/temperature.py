"""Temperature sensor driver — reads ambient temperature."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType

# Reasonable temperature range for indoor IoT sensors (°C).
TEMP_MIN = -40.0
TEMP_MAX = 85.0


class TemperatureSensorDriver(BaseDeviceDriver):
    """Driver for a temperature sensor.

    State fields:
        * ``temperature`` (:class:`float`) — current temperature in °C.

    .. note::

        In virtual mode ``set_state()`` is accepted for testing.  In
        production with a real sensor, writes would be rejected.
    """

    DEVICE_TYPE = DeviceType.TEMPERATURE_SENSOR

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set temperature state (virtual / test mode only)."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate temperature sensor state fields."""
        if "temperature" in state:
            temp = state["temperature"]
            if not isinstance(temp, (int, float)):
                raise ValueError("TemperatureSensor 'temperature' must be a number")
            if temp < TEMP_MIN or temp > TEMP_MAX:
                raise ValueError(
                    f"TemperatureSensor 'temperature' {temp} out of range "
                    f"[{TEMP_MIN}, {TEMP_MAX}]"
                )


__all__ = ["TemperatureSensorDriver", "TEMP_MIN", "TEMP_MAX"]
