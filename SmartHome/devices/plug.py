"""Plug driver — a smart plug with on/off control.

Distinct from :class:`SwitchDriver` only in its ``DeviceType``
(:attr:`DeviceType.PLUG`).  Future phases may add energy-monitoring
fields here.
"""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType


class PlugDriver(BaseDeviceDriver):
    """Driver for a smart plug.

    State fields:
        * ``power`` (:class:`bool`) — whether the plug is supplying power.
    """

    DEVICE_TYPE = DeviceType.PLUG

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set the plug state.  Only ``power`` is accepted."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate plug state fields."""
        if "power" in state and not isinstance(state["power"], bool):
            raise ValueError("Plug 'power' must be a boolean")


__all__ = ["PlugDriver"]
