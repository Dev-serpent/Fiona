"""Shared fixtures for SmartHome tests."""
from __future__ import annotations

from typing import Any

import pytest

from SmartHome.devices.door import DoorSensorDriver
from SmartHome.devices.humidity import HumiditySensorDriver
from SmartHome.devices.lights import LightDriver
from SmartHome.devices.motion import MotionSensorDriver
from SmartHome.devices.plug import PlugDriver
from SmartHome.devices.switch import SwitchDriver
from SmartHome.devices.temperature import TemperatureSensorDriver
from SmartHome.devices.thermostat import ThermostatDriver
from SmartHome.events import EventBus
from SmartHome.models import DeviceInfo, DeviceProperties, DeviceType


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh :class:`EventBus` instance."""
    return EventBus()


@pytest.fixture
def device_properties() -> DeviceProperties:
    """Return a default :class:`DeviceProperties` instance."""
    return DeviceProperties(name="Test Device", room="living_room")


# ── Driver factories ─────────────────────────────────────────────────────


@pytest.fixture
def light_driver() -> LightDriver:
    """Return a :class:`LightDriver` with default settings."""
    return LightDriver()


@pytest.fixture
def switch_driver() -> SwitchDriver:
    """Return a :class:`SwitchDriver` with default settings."""
    return SwitchDriver()


@pytest.fixture
def plug_driver() -> PlugDriver:
    """Return a :class:`PlugDriver` with default settings."""
    return PlugDriver()


@pytest.fixture
def motion_driver() -> MotionSensorDriver:
    """Return a :class:`MotionSensorDriver` with default settings."""
    return MotionSensorDriver()


@pytest.fixture
def temp_driver() -> TemperatureSensorDriver:
    """Return a :class:`TemperatureSensorDriver` with default settings."""
    return TemperatureSensorDriver()


@pytest.fixture
def humidity_driver() -> HumiditySensorDriver:
    """Return a :class:`HumiditySensorDriver` with default settings."""
    return HumiditySensorDriver()


@pytest.fixture
def door_driver() -> DoorSensorDriver:
    """Return a :class:`DoorSensorDriver` with default settings."""
    return DoorSensorDriver()


@pytest.fixture
def thermostat_driver() -> ThermostatDriver:
    """Return a :class:`ThermostatDriver` with default settings."""
    return ThermostatDriver()


@pytest.fixture(params=[
    pytest.param("light_driver", marks=pytest.mark.driver),
    pytest.param("switch_driver", marks=pytest.mark.driver),
    pytest.param("plug_driver", marks=pytest.mark.driver),
    pytest.param("motion_driver", marks=pytest.mark.driver),
    pytest.param("temp_driver", marks=pytest.mark.driver),
    pytest.param("humidity_driver", marks=pytest.mark.driver),
    pytest.param("door_driver", marks=pytest.mark.driver),
    pytest.param("thermostat_driver", marks=pytest.mark.driver),
])
def any_driver(request: Any) -> Any:
    """Parametrized fixture that yields each driver type."""
    return request.getfixturevalue(request.param)
