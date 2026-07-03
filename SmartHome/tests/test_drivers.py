"""Unit tests for all concrete device drivers."""
from __future__ import annotations

from typing import Any

import pytest

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.devices.door import DoorSensorDriver
from SmartHome.devices.humidity import HumiditySensorDriver
from SmartHome.devices.lights import LightDriver
from SmartHome.devices.motion import MotionSensorDriver
from SmartHome.devices.plug import PlugDriver
from SmartHome.devices.switch import SwitchDriver
from SmartHome.devices.temperature import TemperatureSensorDriver
from SmartHome.devices.thermostat import ThermostatDriver
from SmartHome.models import DeviceEvent, DeviceInfo, DeviceType


# ── Basic lifecycle tests (shared by all drivers) ───────────────────────

class TestDriverLifecycle:
    """Tests every driver shares — creation, connect, disconnect, ping."""

    async def test_default_creation(self, any_driver: BaseDeviceDriver) -> None:
        """Each driver initialises with the correct DeviceType."""
        assert any_driver.DEVICE_TYPE is not None

    async def test_device_type_set(self, any_driver: BaseDeviceDriver) -> None:
        """The device_info.device_type matches the class constant."""
        assert any_driver._device_info.device_type == any_driver.DEVICE_TYPE

    async def test_initial_state_not_connected(self, any_driver: BaseDeviceDriver) -> None:
        """A newly-created driver is not connected."""
        assert not any_driver.is_connected

    async def test_virtual_connect(self, any_driver: BaseDeviceDriver) -> None:
        """connect() returns True; is_connected becomes True."""
        result = await any_driver.connect()
        assert result is True
        assert any_driver.is_connected is True

    async def test_virtual_ping(self, any_driver: BaseDeviceDriver) -> None:
        """ping() returns True when connected."""
        await any_driver.connect()
        assert await any_driver.ping() is True

    async def test_disconnect(self, any_driver: BaseDeviceDriver) -> None:
        """disconnect() sets is_connected to False."""
        await any_driver.connect()
        await any_driver.disconnect()
        assert any_driver.is_connected is False

    async def test_get_state_returns_current(self, any_driver: BaseDeviceDriver) -> None:
        """get_state() returns the same object as device_info.state."""
        assert await any_driver.get_state() is any_driver._device_info.state

    async def test_to_payload_roundtrip(self, any_driver: BaseDeviceDriver) -> None:
        """to_payload() then from_payload() produces an equivalent driver."""
        driver_class = type(any_driver)
        payload = any_driver.to_payload()
        restored = driver_class.from_payload(payload)
        assert restored.DEVICE_TYPE == any_driver.DEVICE_TYPE
        assert restored._device_info.state == any_driver._device_info.state

    async def test_set_state_empty_dict(self, any_driver: BaseDeviceDriver) -> None:
        """set_state({}) is a no-op returning True."""
        result = await any_driver.set_state({})
        assert result is True

    async def test_set_state_ignores_unknown_fields(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        """Unknown keys in set_state are silently ignored."""
        result = await any_driver.set_state({"nonexistent_field": 42})
        assert result is True

    async def test_event_publishing_on_set_state(
        self, any_driver: BaseDeviceDriver, event_bus: Any
    ) -> None:
        """With event bus attached, set_state publishes a state_changed event."""
        received: list[DeviceEvent] = []

        async def handler(event: DeviceEvent) -> None:
            received.append(event)

        event_bus.subscribe("state_changed", handler)
        any_driver.set_event_bus(event_bus)

        await any_driver.set_state({"power": True})
        assert len(received) >= 1
        assert received[0].event_type == "state_changed"
        assert received[0].device_id == any_driver._device_info.device_id


# ── SwitchDriver ─────────────────────────────────────────────────────────

class TestSwitchDriver:
    async def test_type(self, switch_driver: SwitchDriver) -> None:
        assert switch_driver.DEVICE_TYPE == DeviceType.SWITCH

    async def test_set_power(self, switch_driver: SwitchDriver) -> None:
        await switch_driver.set_state({"power": True})
        assert (await switch_driver.get_state()).power is True

    async def test_set_power_invalid(self, switch_driver: SwitchDriver) -> None:
        with pytest.raises(ValueError, match="Switch.*power.*boolean"):
            await switch_driver.set_state({"power": "yes"})


# ── PlugDriver ───────────────────────────────────────────────────────────

class TestPlugDriver:
    async def test_type(self, plug_driver: PlugDriver) -> None:
        assert plug_driver.DEVICE_TYPE == DeviceType.PLUG

    async def test_set_power(self, plug_driver: PlugDriver) -> None:
        await plug_driver.set_state({"power": True})
        assert (await plug_driver.get_state()).power is True

    async def test_set_power_invalid(self, plug_driver: PlugDriver) -> None:
        with pytest.raises(ValueError, match="Plug.*power.*boolean"):
            await plug_driver.set_state({"power": 1})


# ── MotionSensorDriver ───────────────────────────────────────────────────

class TestMotionSensorDriver:
    async def test_type(self, motion_driver: MotionSensorDriver) -> None:
        assert motion_driver.DEVICE_TYPE == DeviceType.MOTION_SENSOR

    async def test_set_motion(self, motion_driver: MotionSensorDriver) -> None:
        await motion_driver.set_state({"motion_detected": True})
        assert (await motion_driver.get_state()).motion_detected is True

    async def test_set_motion_invalid(self, motion_driver: MotionSensorDriver) -> None:
        with pytest.raises(ValueError, match="motion_detected.*boolean"):
            await motion_driver.set_state({"motion_detected": "yes"})


# ── DoorSensorDriver ─────────────────────────────────────────────────────

class TestDoorSensorDriver:
    async def test_type(self, door_driver: DoorSensorDriver) -> None:
        assert door_driver.DEVICE_TYPE == DeviceType.DOOR_SENSOR

    async def test_set_door(self, door_driver: DoorSensorDriver) -> None:
        await door_driver.set_state({"door_open": True})
        assert (await door_driver.get_state()).door_open is True

    async def test_set_door_invalid(self, door_driver: DoorSensorDriver) -> None:
        with pytest.raises(ValueError, match="door_open.*boolean"):
            await door_driver.set_state({"door_open": "maybe"})


# ── TemperatureSensorDriver ──────────────────────────────────────────────

class TestTemperatureSensorDriver:
    async def test_type(self, temp_driver: TemperatureSensorDriver) -> None:
        assert temp_driver.DEVICE_TYPE == DeviceType.TEMPERATURE_SENSOR

    async def test_set_temperature(self, temp_driver: TemperatureSensorDriver) -> None:
        await temp_driver.set_state({"temperature": 22.5})
        assert (await temp_driver.get_state()).temperature == 22.5

    async def test_set_temperature_invalid_type(
        self, temp_driver: TemperatureSensorDriver
    ) -> None:
        with pytest.raises(ValueError, match="TemperatureSensor.*number"):
            await temp_driver.set_state({"temperature": "hot"})

    async def test_set_temperature_out_of_range_low(
        self, temp_driver: TemperatureSensorDriver
    ) -> None:
        with pytest.raises(ValueError, match="out of range"):
            await temp_driver.set_state({"temperature": -50.0})

    async def test_set_temperature_out_of_range_high(
        self, temp_driver: TemperatureSensorDriver
    ) -> None:
        with pytest.raises(ValueError, match="out of range"):
            await temp_driver.set_state({"temperature": 100.0})


# ── HumiditySensorDriver ─────────────────────────────────────────────────

class TestHumiditySensorDriver:
    async def test_type(self, humidity_driver: HumiditySensorDriver) -> None:
        assert humidity_driver.DEVICE_TYPE == DeviceType.HUMIDITY_SENSOR

    async def test_set_humidity(self, humidity_driver: HumiditySensorDriver) -> None:
        await humidity_driver.set_state({"humidity": 55.0})
        assert (await humidity_driver.get_state()).humidity == 55.0

    async def test_set_humidity_invalid_type(
        self, humidity_driver: HumiditySensorDriver
    ) -> None:
        with pytest.raises(ValueError, match="HumiditySensor.*number"):
            await humidity_driver.set_state({"humidity": "damp"})

    async def test_set_humidity_out_of_range(
        self, humidity_driver: HumiditySensorDriver
    ) -> None:
        with pytest.raises(ValueError, match="out of range"):
            await humidity_driver.set_state({"humidity": 101.0})


# ── LightDriver ──────────────────────────────────────────────────────────

class TestLightDriver:
    async def test_type(self, light_driver: LightDriver) -> None:
        assert light_driver.DEVICE_TYPE == DeviceType.LIGHT

    async def test_set_power(self, light_driver: LightDriver) -> None:
        await light_driver.set_state({"power": True})
        assert (await light_driver.get_state()).power is True

    async def test_set_brightness(self, light_driver: LightDriver) -> None:
        await light_driver.set_state({"brightness": 75})
        assert (await light_driver.get_state()).brightness == 75

    async def test_set_brightness_low(self, light_driver: LightDriver) -> None:
        await light_driver.set_state({"brightness": 0})
        assert (await light_driver.get_state()).brightness == 0

    async def test_set_brightness_out_of_range_low(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="brightness.*out of range"):
            await light_driver.set_state({"brightness": -1})

    async def test_set_brightness_out_of_range_high(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="brightness.*out of range"):
            await light_driver.set_state({"brightness": 101})

    async def test_set_brightness_not_int(self, light_driver: LightDriver) -> None:
        with pytest.raises(ValueError, match="brightness.*integer"):
            await light_driver.set_state({"brightness": 50.5})

    async def test_set_color_temp(self, light_driver: LightDriver) -> None:
        await light_driver.set_state({"color_temp": 4000})
        assert (await light_driver.get_state()).color_temp == 4000

    async def test_set_color_temp_out_of_range_low(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="color_temp.*out of range"):
            await light_driver.set_state({"color_temp": 1000})

    async def test_set_color_temp_out_of_range_high(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="color_temp.*out of range"):
            await light_driver.set_state({"color_temp": 7000})

    async def test_set_color(self, light_driver: LightDriver) -> None:
        await light_driver.set_state({"color": "#ff8800"})
        assert (await light_driver.get_state()).color == "#ff8800"

    async def test_set_color_invalid_format(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="color.*not a valid hex"):
            await light_driver.set_state({"color": "red"})

    async def test_set_color_invalid_short_hex(
        self, light_driver: LightDriver
    ) -> None:
        with pytest.raises(ValueError, match="color.*not a valid hex"):
            await light_driver.set_state({"color": "#FFF"})


# ── ThermostatDriver ─────────────────────────────────────────────────────

class TestThermostatDriver:
    async def test_type(self, thermostat_driver: ThermostatDriver) -> None:
        assert thermostat_driver.DEVICE_TYPE == DeviceType.THERMOSTAT

    async def test_set_power(self, thermostat_driver: ThermostatDriver) -> None:
        await thermostat_driver.set_state({"power": True})
        assert (await thermostat_driver.get_state()).power is True

    async def test_set_temperature(self, thermostat_driver: ThermostatDriver) -> None:
        await thermostat_driver.set_state({"temperature": 24.0})
        assert (await thermostat_driver.get_state()).temperature == 24.0

    async def test_set_target_temperature(
        self, thermostat_driver: ThermostatDriver
    ) -> None:
        await thermostat_driver.set_state({"target_temperature": 21.5})
        assert (await thermostat_driver.get_state()).target_temperature == 21.5

    async def test_set_hvac_mode(self, thermostat_driver: ThermostatDriver) -> None:
        await thermostat_driver.set_state({"hvac_mode": "cool"})
        assert (await thermostat_driver.get_state()).hvac_mode == "cool"

    async def test_set_hvac_mode_auto(self, thermostat_driver: ThermostatDriver) -> None:
        await thermostat_driver.set_state({"hvac_mode": "auto"})
        assert (await thermostat_driver.get_state()).hvac_mode == "auto"

    async def test_set_hvac_mode_invalid(
        self, thermostat_driver: ThermostatDriver
    ) -> None:
        with pytest.raises(ValueError, match="hvac_mode.*not valid"):
            await thermostat_driver.set_state({"hvac_mode": "heatpump"})

    async def test_set_target_temp_out_of_range_low(
        self, thermostat_driver: ThermostatDriver
    ) -> None:
        with pytest.raises(ValueError, match="target_temperature.*out of range"):
            await thermostat_driver.set_state({"target_temperature": 0.0})

    async def test_set_target_temp_out_of_range_high(
        self, thermostat_driver: ThermostatDriver
    ) -> None:
        with pytest.raises(ValueError, match="target_temperature.*out of range"):
            await thermostat_driver.set_state({"target_temperature": 40.0})

    async def test_set_hvac_mode_uppercase_normalized(
        self, thermostat_driver: ThermostatDriver
    ) -> None:
        await thermostat_driver.set_state({"hvac_mode": "HEAT"})
        assert (await thermostat_driver.get_state()).hvac_mode == "heat"


# ── Payload serialization (across all drivers) ──────────────────────────

class TestPayloadSerialization:
    """Tests for to_payload / from_payload across driver types."""

    async def test_payload_contains_device_id(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        payload = any_driver.to_payload()
        assert "device_id" in payload
        assert payload["device_id"] == any_driver._device_info.device_id

    async def test_payload_contains_device_type(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        payload = any_driver.to_payload()
        assert "device_type" in payload
        assert payload["device_type"] == any_driver.DEVICE_TYPE.value

    async def test_payload_contains_timestamp(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        payload = any_driver.to_payload()
        assert "timestamp" in payload
        assert payload["timestamp"] is not None

    async def test_payload_omits_none_state(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        """Fields with None values should not appear in the state dict."""
        payload = any_driver.to_payload()
        state = payload.get("state", {})
        # All fields should be absent because they default to None
        for key in ("power", "brightness", "color_temp", "color",
                    "temperature", "humidity", "motion_detected",
                    "door_open", "target_temperature", "hvac_mode"):
            assert key not in state or state[key] is not None

    async def test_payload_roundtrip_with_state(
        self, any_driver: BaseDeviceDriver
    ) -> None:
        """Setting state then roundtripping preserves the changes."""
        driver_class = type(any_driver)

        # Set a reasonable state value that works for this driver type
        sample: dict[str, Any] = {}
        dt = any_driver.DEVICE_TYPE
        if dt in (DeviceType.SWITCH, DeviceType.PLUG, DeviceType.LIGHT,
                  DeviceType.THERMOSTAT):
            sample["power"] = True
        if dt == DeviceType.LIGHT:
            sample["brightness"] = 80
            sample["color_temp"] = 3500
            sample["color"] = "#aabbcc"
        if dt == DeviceType.MOTION_SENSOR:
            sample["motion_detected"] = True
        if dt == DeviceType.DOOR_SENSOR:
            sample["door_open"] = True
        if dt == DeviceType.TEMPERATURE_SENSOR:
            sample["temperature"] = 22.0
        if dt == DeviceType.HUMIDITY_SENSOR:
            sample["humidity"] = 60.0
        if dt == DeviceType.THERMOSTAT:
            sample["temperature"] = 23.0
            sample["target_temperature"] = 21.0
            sample["hvac_mode"] = "heat"

        if sample:
            await any_driver.set_state(sample)

        payload = any_driver.to_payload()
        restored = driver_class.from_payload(payload)

        for key, expected_val in sample.items():
            actual_val = getattr(restored._device_info.state, key)
            assert actual_val == expected_val, (
                f"Field {key!r}: expected {expected_val!r}, got {actual_val!r}"
            )
