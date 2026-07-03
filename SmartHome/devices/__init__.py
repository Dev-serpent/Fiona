"""Device driver implementations for the Smart Home platform."""
from __future__ import annotations

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.devices.door import DoorSensorDriver
from SmartHome.devices.humidity import HumiditySensorDriver
from SmartHome.devices.lights import LightDriver
from SmartHome.devices.motion import MotionSensorDriver
from SmartHome.devices.plug import PlugDriver
from SmartHome.devices.registry import DeviceRegistry
from SmartHome.devices.switch import SwitchDriver
from SmartHome.devices.temperature import TemperatureSensorDriver
from SmartHome.devices.thermostat import ThermostatDriver

__all__ = [
    "BaseDeviceDriver",
    "DeviceRegistry",
    "DoorSensorDriver",
    "HumiditySensorDriver",
    "LightDriver",
    "MotionSensorDriver",
    "PlugDriver",
    "SwitchDriver",
    "TemperatureSensorDriver",
    "ThermostatDriver",
]
