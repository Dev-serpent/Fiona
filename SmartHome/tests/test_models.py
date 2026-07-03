"""Unit tests for ``SmartHome.models``."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from SmartHome.models import (
    DeviceEvent,
    DeviceInfo,
    DeviceProperties,
    DeviceState,
    DeviceStatus,
    DeviceType,
    Room,
    Scene,
)


class TestDeviceType:
    """Verify the ``DeviceType`` enumeration."""

    def test_values(self) -> None:
        assert DeviceType.LIGHT.value == "light"
        assert DeviceType.SWITCH.value == "switch"
        assert DeviceType.PLUG.value == "plug"
        assert DeviceType.MOTION_SENSOR.value == "motion_sensor"
        assert DeviceType.TEMPERATURE_SENSOR.value == "temperature_sensor"
        assert DeviceType.HUMIDITY_SENSOR.value == "humidity_sensor"
        assert DeviceType.DOOR_SENSOR.value == "door_sensor"
        assert DeviceType.THERMOSTAT.value == "thermostat"


class TestDeviceStatus:
    """Verify the ``DeviceStatus`` enumeration."""

    def test_values(self) -> None:
        assert DeviceStatus.ONLINE.value == "online"
        assert DeviceStatus.OFFLINE.value == "offline"
        assert DeviceStatus.ERROR.value == "error"
        assert DeviceStatus.UNKNOWN.value == "unknown"


class TestDeviceState:
    """Verify ``DeviceState`` default behaviour."""

    def test_defaults_are_none(self) -> None:
        """All fields should default to ``None``."""
        state = DeviceState()
        assert state.power is None
        assert state.brightness is None
        assert state.color_temp is None
        assert state.color is None
        assert state.temperature is None
        assert state.humidity is None
        assert state.motion_detected is None
        assert state.door_open is None
        assert state.target_temperature is None
        assert state.hvac_mode is None

    def test_partial_update(self) -> None:
        """Setting only some fields should leave others as ``None``."""
        state = DeviceState(power=True, brightness=80)
        assert state.power is True
        assert state.brightness == 80
        assert state.temperature is None
        assert state.humidity is None


class TestDeviceProperties:
    """Verify ``DeviceProperties`` defaults."""

    def test_defaults(self) -> None:
        props = DeviceProperties()
        assert props.name == ""
        assert props.room == "default"
        assert props.location == ""
        assert props.manufacturer == "Fiona IoT"
        assert props.model == "v1"
        assert props.firmware_version == "1.0.0"
        assert props.poll_interval == 60


class TestDeviceInfo:
    """Verify ``DeviceInfo`` construction."""

    def test_defaults(self) -> None:
        info = DeviceInfo()
        # device_id should be a non-empty hex string (UUID4)
        assert len(info.device_id) == 32
        assert info.device_type == DeviceType.SWITCH
        assert info.status == DeviceStatus.OFFLINE
        assert isinstance(info.properties, DeviceProperties)
        assert isinstance(info.state, DeviceState)
        assert info.last_seen is None
        assert isinstance(info.created_at, datetime)
        assert info.tags == []

    def test_custom_values(self) -> None:
        info = DeviceInfo(
            device_id="test-id",
            device_type=DeviceType.THERMOSTAT,
            status=DeviceStatus.ONLINE,
            tags=["living_room"],
        )
        assert info.device_id == "test-id"
        assert info.device_type == DeviceType.THERMOSTAT
        assert info.status == DeviceStatus.ONLINE
        assert info.tags == ["living_room"]


class TestDeviceEvent:
    """Verify ``DeviceEvent`` construction."""

    def test_defaults(self) -> None:
        event = DeviceEvent()
        assert len(event.event_id) == 32
        assert event.device_id == ""
        assert event.event_type == "state_changed"
        assert isinstance(event.timestamp, datetime)
        assert event.data == {}

    def test_custom_event(self) -> None:
        data = {"power": True, "brightness": 75}
        event = DeviceEvent(
            device_id="dev-1",
            event_type="state_changed",
            data=data,
        )
        assert event.device_id == "dev-1"
        assert event.event_type == "state_changed"
        assert event.data == data


class TestRoom:
    """Verify ``Room`` construction."""

    def test_defaults(self) -> None:
        room = Room()
        assert len(room.room_id) == 32
        assert room.name == ""
        assert room.floor == "1"
        assert room.device_ids == []

    def test_custom_room(self) -> None:
        room = Room(name="Living Room", floor="2", device_ids=["dev-1", "dev-2"])
        assert room.name == "Living Room"
        assert room.floor == "2"
        assert room.device_ids == ["dev-1", "dev-2"]


class TestScene:
    """Verify ``Scene`` construction."""

    def test_defaults(self) -> None:
        scene = Scene()
        assert len(scene.scene_id) == 32
        assert scene.name == ""
        assert scene.states == {}
        assert isinstance(scene.created_at, datetime)

    def test_custom_scene(self) -> None:
        states = {"dev-1": {"power": True, "brightness": 100}}
        scene = Scene(name="Good Night", states=states)
        assert scene.name == "Good Night"
        assert scene.states == states
