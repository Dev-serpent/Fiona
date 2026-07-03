"""Motion sensor driver — detects motion in its field of view."""
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceInfo, DeviceType


class MotionSensorDriver(BaseDeviceDriver):
    """Driver for a motion / presence sensor.

    State fields:
        * ``motion_detected`` (:class:`bool`) — whether motion is currently
          detected.

    .. note::

        In virtual mode ``set_state()`` is accepted for testing.  In
        production with a real sensor, writes would be rejected because
        motion state is read-only from hardware.
    """

    DEVICE_TYPE = DeviceType.MOTION_SENSOR

    def __init__(self, device_info: DeviceInfo | None = None) -> None:
        if device_info is None:
            device_info = DeviceInfo(device_type=self.DEVICE_TYPE)
        device_info.device_type = self.DEVICE_TYPE
        super().__init__(device_info)

    async def get_state(self) -> Any:
        """Return the current device state."""
        return self._device_info.state

    async def set_state(self, state: dict[str, Any]) -> bool:
        """Set motion state (virtual / test mode only)."""
        self._validate_state(state)
        return await super().set_state(state)

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate motion sensor state fields."""
        if "motion_detected" in state and not isinstance(state["motion_detected"], bool):
            raise ValueError("MotionSensor 'motion_detected' must be a boolean")


__all__ = ["MotionSensorDriver"]
