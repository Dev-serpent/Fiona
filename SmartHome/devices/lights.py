"""Light driver — supports power, brightness, colour temperature, and colour."""
from __future__ import annotations

import re
from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType

# Validation constants
BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100
COLOR_TEMP_MIN = 2000   # Kelvin — warm
COLOR_TEMP_MAX = 6500   # Kelvin — cool daylight
COLOR_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class LightDriver(BaseDeviceDriver):
    """Driver for a smart light / bulb.

    State fields:
        * ``power`` (:class:`bool`) — on/off.
        * ``brightness`` (:class:`int`) — 0–100.
        * ``color_temp`` (:class:`int`) — colour temperature in Kelvin
          (2000–6500).
        * ``color`` (:class:`str`) — hex colour string, e.g. ``"#ff8800"``.
    """

    DEVICE_TYPE = DeviceType.LIGHT

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set the light state with validation."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate light-specific state fields."""
        if "power" in state and not isinstance(state["power"], bool):
            raise ValueError("Light 'power' must be a boolean")

        if "brightness" in state:
            b = state["brightness"]
            if not isinstance(b, int) or isinstance(b, bool):
                raise ValueError("Light 'brightness' must be an integer")
            if b < BRIGHTNESS_MIN or b > BRIGHTNESS_MAX:
                raise ValueError(
                    f"Light 'brightness' {b} out of range "
                    f"[{BRIGHTNESS_MIN}, {BRIGHTNESS_MAX}]"
                )

        if "color_temp" in state:
            ct = state["color_temp"]
            if not isinstance(ct, int) or isinstance(ct, bool):
                raise ValueError("Light 'color_temp' must be an integer")
            if ct < COLOR_TEMP_MIN or ct > COLOR_TEMP_MAX:
                raise ValueError(
                    f"Light 'color_temp' {ct} out of range "
                    f"[{COLOR_TEMP_MIN}, {COLOR_TEMP_MAX}]"
                )

        if "color" in state:
            c = state["color"]
            if not isinstance(c, str) or not COLOR_HEX_RE.match(c):
                raise ValueError(
                    f"Light 'color' {c!r} is not a valid hex colour "
                    f"(expected #RRGGBB)"
                )


__all__ = ["LightDriver"]
