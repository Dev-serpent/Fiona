"""Thermostat driver — heating/cooling thermostat with target temperature."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType

# Validation constants
TARGET_TEMP_MIN = 5.0    # °C
TARGET_TEMP_MAX = 35.0   # °C
TEMP_MIN = -40.0
TEMP_MAX = 85.0
VALID_HVAC_MODES = {"heat", "cool", "auto", "off"}


class ThermostatDriver(BaseDeviceDriver):
    """Driver for a thermostat device.

    State fields:
        * ``power`` (:class:`bool`) — on/off.
        * ``temperature`` (:class:`float`) — current ambient temperature (°C).
        * ``target_temperature`` (:class:`float`) — desired temperature (°C,
          5–35).
        * ``hvac_mode`` (:class:`str`) — one of ``"heat"``, ``"cool"``,
          ``"auto"``, ``"off"``.
    """

    DEVICE_TYPE = DeviceType.THERMOSTAT

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set the thermostat state with validation."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate thermostat-specific state fields."""
        if "power" in state and not isinstance(state["power"], bool):
            raise ValueError("Thermostat 'power' must be a boolean")

        if "temperature" in state:
            temp = state["temperature"]
            if not isinstance(temp, (int, float)):
                raise ValueError("Thermostat 'temperature' must be a number")
            if temp < TEMP_MIN or temp > TEMP_MAX:
                raise ValueError(
                    f"Thermostat 'temperature' {temp} out of range "
                    f"[{TEMP_MIN}, {TEMP_MAX}]"
                )

        if "target_temperature" in state:
            tt = state["target_temperature"]
            if not isinstance(tt, (int, float)):
                raise ValueError("Thermostat 'target_temperature' must be a number")
            if tt < TARGET_TEMP_MIN or tt > TARGET_TEMP_MAX:
                raise ValueError(
                    f"Thermostat 'target_temperature' {tt} out of range "
                    f"[{TARGET_TEMP_MIN}, {TARGET_TEMP_MAX}]"
                )

        if "hvac_mode" in state:
            hvac = state["hvac_mode"]
            if not isinstance(hvac, str) or hvac.lower() not in VALID_HVAC_MODES:
                raise ValueError(
                    f"Thermostat 'hvac_mode' {hvac!r} is not valid; "
                    f"expected one of {sorted(VALID_HVAC_MODES)}"
                )
            # Normalise to lowercase
            state["hvac_mode"] = hvac.lower()


__all__ = ["ThermostatDriver"]
