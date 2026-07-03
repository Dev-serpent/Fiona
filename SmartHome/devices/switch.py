"""Switch driver — a simple on/off power switch."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType


class SwitchDriver(BaseDeviceDriver):
    """Driver for a basic on/off switch.

    State fields:
        * ``power`` (:class:`bool`) — whether the switch is turned on.
    """

    DEVICE_TYPE = DeviceType.SWITCH

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set the switch state.  Only ``power`` is accepted."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate switch state fields."""
        if "power" in state and not isinstance(state["power"], bool):
            raise ValueError("Switch 'power' must be a boolean")


__all__ = ["SwitchDriver"]
