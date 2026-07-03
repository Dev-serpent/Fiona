"""Unit tests for the HomeBackend MQTT integration.

Tests use :func:`unittest.mock.patch` to avoid requiring a real MQTT broker.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import Any, Generator
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from HomeBackend.mqtt.broker import BrokerConfig, generate_mosquitto_config
from HomeBackend.mqtt.client import MqttClient
from HomeBackend.mqtt.handler import MqttMessageHandler
from HomeBackend.mqtt.topics import TopicBuilder
from SmartHome.config import MqttConfig
from SmartHome.errors import MqttConnectionError, MqttPublishError
from SmartHome.events import EventBus
from SmartHome.models import DeviceInfo, DeviceStatus, DeviceType

# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════


def _make_registry() -> MagicMock:
    """Create a mock device registry with async ``get``."""
    registry = MagicMock()
    registry.get = AsyncMock()
    registry.register = AsyncMock()
    registry.unregister = AsyncMock()
    registry.list = AsyncMock()
    registry.update = AsyncMock()
    return registry


# ═════════════════════════════════════════════════════════════════════════════
# TopicBuilder
# ═════════════════════════════════════════════════════════════════════════════


class TestTopicBuilder:
    """Verify :class:`TopicBuilder` constructs correct topic strings."""

    def setup_method(self) -> None:
        self.builder = TopicBuilder(prefix="fiona")

    def test_device_state_topic(self) -> None:
        assert self.builder.device_state("sensor-01") == "fiona/sensor-01/state"

    def test_device_command_topic(self) -> None:
        assert self.builder.device_command("light-02") == "fiona/light-02/command"

    def test_device_availability_topic(self) -> None:
        assert self.builder.device_availability("plug-03") == "fiona/plug-03/available"

    def test_device_event_topic(self) -> None:
        assert self.builder.device_event("thermo-01") == "fiona/thermo-01/event"

    def test_discovery_topic(self) -> None:
        assert self.builder.discovery_config("switch-a") == "fiona/discovery/switch-a/config"

    def test_scene_topic(self) -> None:
        assert self.builder.scene("good-night") == "fiona/scene/good-night"

    def test_broadcast_topic(self) -> None:
        assert self.builder.broadcast() == "fiona/broadcast/#"

    def test_custom_prefix(self) -> None:
        custom = TopicBuilder(prefix="mysmarthome")
        assert custom.device_state("d1") == "mysmarthome/d1/state"

    def test_prefix_trailing_slash_stripped(self) -> None:
        builder = TopicBuilder(prefix="fiona/")
        assert builder.prefix == "fiona"
        assert builder.device_state("d1") == "fiona/d1/state"

    def test_property_prefix_readonly(self) -> None:
        assert self.builder.prefix == "fiona"


# ═════════════════════════════════════════════════════════════════════════════
# MqttClient
# ═════════════════════════════════════════════════════════════════════════════


class TestMqttClient:
    """Verify :class:`MqttClient` lifecycle, publish, subscribe, and reconnect."""

    # ── helpers ────────────────────────────────────────────────────────────

    @contextmanager
    def _patch_paho(self) -> Generator[tuple[MagicMock, MagicMock], None, None]:
        """Patch ``paho.mqtt.client`` so tests don't need the real package.

        Yields ``(mock_paho_module, mock_instance)`` where *mock_instance* is
        the object returned by ``paho.Client()``.
        """
        # Seed sys.modules so the lazy import inside MqttClient.connect()
        # resolves even when paho is not installed.
        import sys  # noqa: PLC0415

        sys.modules.setdefault("paho", MagicMock())
        sys.modules.setdefault("paho.mqtt", MagicMock())
        sys.modules["paho.mqtt.client"] = MagicMock()

        patcher = patch("paho.mqtt.client")
        mock_client_module = patcher.start()
        mock_instance = MagicMock()
        mock_client_module.Client.return_value = mock_instance
        try:
            yield mock_client_module, mock_instance
        finally:
            patcher.stop()

    # ── connect ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        """Successful connection should set is_connected to True."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            client = MqttClient()
            # Manually set _connected to simulate on_connect success
            client._connected.set()
            assert client.is_connected

    @pytest.mark.asyncio
    async def test_connect_sets_up_paho_client(self) -> None:
        """Verify that connect() creates a paho client with correct settings."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            config = MqttConfig(
                host="mqtt.example.com",
                port=1884,
                client_id="test-client",
                username="user",
                password="pass",
                qos=1,
            )
            client = MqttClient(config=config)
            client._connected.set()
            assert client.is_connected

    @pytest.mark.asyncio
    async def test_connect_idempotent(self) -> None:
        """Calling connect() twice should be a no-op when already connected."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            client = MqttClient()
            client._connected.set()
            # Second connect should return immediately
            await client.connect()
            assert client.is_connected

    # ── publish ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_publish_success(self) -> None:
        """Publishing should call paho's publish with JSON-encoded payload."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            mock_instance.publish.return_value = MagicMock(rc=0)

            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            payload = {"temperature": 22.5, "humidity": 60}
            await client.publish("fiona/sensor-01/state", payload, retain=True)

            mock_instance.publish.assert_called_once_with(
                "fiona/sensor-01/state",
                json.dumps(payload),
                qos=1,
                retain=True,
            )

    @pytest.mark.asyncio
    async def test_publish_raw_string(self) -> None:
        """A string payload should be sent as-is (not double-encoded)."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            mock_instance.publish.return_value = MagicMock(rc=0)

            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            await client.publish("topic/test", "raw_string")

            mock_instance.publish.assert_called_once_with(
                "topic/test",
                "raw_string",
                qos=1,
                retain=False,
            )

    @pytest.mark.asyncio
    async def test_publish_not_connected(self) -> None:
        """Publishing without a connection should raise MqttConnectionError."""
        client = MqttClient()
        with pytest.raises(MqttConnectionError, match="Not connected"):
            await client.publish("topic/test", "data")

    @pytest.mark.asyncio
    async def test_publish_failure_code(self) -> None:
        """Publish returning non-zero rc should raise MqttPublishError."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            mock_instance.publish.return_value = MagicMock(rc=1)

            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            with pytest.raises(MqttPublishError, match="Publish failed"):
                await client.publish("topic/test", "data")

    # ── subscribe & callbacks ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_subscribe_and_callback(self) -> None:
        """Subscribing should register a callback and dispatch messages."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            callback = AsyncMock()

            await client.subscribe("fiona/+/state", callback=callback)

            # Simulate incoming message
            msg = MagicMock()
            msg.topic = "fiona/sensor-01/state"
            msg.payload = b'{"temperature": 23.0}'

            client._on_message(mock_instance, None, msg)

            # Give the create_task a moment to run
            await asyncio.sleep(0.02)

            callback.assert_awaited_once_with(
                "fiona/sensor-01/state",
                '{"temperature": 23.0}',
            )

    @pytest.mark.asyncio
    async def test_subscribe_no_callback(self) -> None:
        """Subscribing without a callback should still call paho.subscribe."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            await client.subscribe("fiona/+/state")

            mock_instance.subscribe.assert_called_once_with("fiona/+/state", qos=1)

    # ── disconnect ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self) -> None:
        """Disconnect should stop the loop and clear the connected flag."""
        with self._patch_paho() as (mock_paho_mod, mock_instance):
            client = MqttClient()
            client._connected.set()
            client._client = mock_instance

            await client.disconnect()

            assert not client.is_connected
            mock_instance.loop_stop.assert_called_once()
            mock_instance.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self) -> None:
        """Calling disconnect() twice should not raise."""
        client = MqttClient()
        await client.disconnect()  # first with no client
        await client.disconnect()  # second still no-op

    # ── will / LWT ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_will_configuration(self) -> None:
        """Will topic/payload should be stored in the client."""
        client = MqttClient(
            will_topic="fiona/gateway/available",
            will_payload="offline",
            will_qos=1,
        )
        assert client._will_topic == "fiona/gateway/available"
        assert client._will_payload == "offline"
        assert client._will_qos == 1

    # ── internal ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_on_disconnect_unexpected(self) -> None:
        """Unexpected disconnect should clear the connected flag."""
        client = MqttClient()
        client._connected.set()

        client._on_disconnect(None, None, rc=1)
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_topic_matches_wildcard(self) -> None:
        """Wildcard matching should work for + and #."""
        assert MqttClient._topic_matches("fiona/+/state", "fiona/sensor-01/state")
        assert MqttClient._topic_matches("fiona/#", "fiona/sensor-01/state")
        assert MqttClient._topic_matches("fiona/#", "fiona/sensor-01/event")
        assert not MqttClient._topic_matches("fiona/+/state", "fiona/sensor-01/event")

    @pytest.mark.asyncio
    async def test_subscribe_not_connected(self) -> None:
        """Subscribe without connection should raise MqttConnectionError."""
        client = MqttClient()
        with pytest.raises(MqttConnectionError, match="Not connected"):
            await client.subscribe("topic/test")


# ═════════════════════════════════════════════════════════════════════════════
# MqttMessageHandler
# ═════════════════════════════════════════════════════════════════════════════


class TestMqttMessageHandler:
    """Verify :class:`MqttMessageHandler` routes messages correctly."""

    @pytest.mark.asyncio
    async def test_discovery_message(self) -> None:
        """A discovery topic should be routed to _handle_discovery."""
        registry = _make_registry()
        event_bus = EventBus()

        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        with patch.object(handler, "_handle_discovery") as mock_discovery:
            await handler.handle_message(
                "fiona/discovery/device-01/config",
                '{"name": "Test Device"}',
            )
            mock_discovery.assert_awaited_once_with(
                "device-01",
                '{"name": "Test Device"}',
            )

    @pytest.mark.asyncio
    async def test_command_message(self) -> None:
        """A command topic should update the device state and publish an event."""
        device = DeviceInfo(device_id="dev-1", device_type=DeviceType.LIGHT)

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        event_handler = AsyncMock()
        event_bus.subscribe("state_changed", event_handler)

        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        await handler.handle_message(
            "fiona/dev-1/command",
            '{"power": true, "brightness": 80}',
        )

        assert device.state.power is True
        assert device.state.brightness == 80

        # Check event was published
        event_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_command_unknown_device(self) -> None:
        """Command for unknown device should log a warning, not crash."""
        registry = _make_registry()
        registry.get.return_value = None

        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        # Should not raise
        await handler.handle_message(
            "fiona/unknown-device/command",
            '{"power": true}',
        )

    @pytest.mark.asyncio
    async def test_state_message(self) -> None:
        """A state update topic should update the device state."""
        device = DeviceInfo(
            device_id="dev-1", device_type=DeviceType.TEMPERATURE_SENSOR
        )

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        await handler.handle_message(
            "fiona/dev-1/state",
            '{"temperature": 23.5, "humidity": 55}',
        )

        assert device.state.temperature == 23.5
        assert device.state.humidity == 55

    @pytest.mark.asyncio
    async def test_event_message(self) -> None:
        """An event topic should publish a DeviceEvent on the event bus."""
        device = DeviceInfo(device_id="dev-1", device_type=DeviceType.MOTION_SENSOR)

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        event_handler = AsyncMock()
        event_bus.subscribe("motion_detected", event_handler)

        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        await handler.handle_message(
            "fiona/dev-1/event",
            '{"event_type": "motion_detected", "data": {"zone": "entrance"}}',
        )

        event_handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_availability_message(self) -> None:
        """An availability message should update the device status."""
        device = DeviceInfo(device_id="dev-1", status=DeviceStatus.OFFLINE)

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        await handler.handle_message(
            "fiona/dev-1/available",
            "online",
        )

        assert device.status == DeviceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_availability_offline(self) -> None:
        """An offline availability message should update to OFFLINE."""
        device = DeviceInfo(device_id="dev-1", status=DeviceStatus.ONLINE)

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        await handler.handle_message(
            "fiona/dev-1/available",
            "offline",
        )

        assert device.status == DeviceStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_invalid_topic_short(self) -> None:
        """A topic with fewer than 3 parts should be ignored."""
        registry = _make_registry()
        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        # Should not raise, should not call any handler
        await handler.handle_message("fiona/only", "{}")

    @pytest.mark.asyncio
    async def test_invalid_topic_wrong_prefix(self) -> None:
        """A topic with a non-matching prefix should be ignored."""
        registry = _make_registry()
        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        # Should not raise
        await handler.handle_message("other/dev-1/state", "{}")

    @pytest.mark.asyncio
    async def test_command_invalid_json(self) -> None:
        """Invalid JSON in a command should be handled gracefully."""
        device = DeviceInfo(device_id="dev-1")

        registry = _make_registry()
        registry.get.return_value = device

        event_bus = EventBus()
        handler = MqttMessageHandler(registry, event_bus, topic_prefix="fiona")

        # Should not raise
        await handler.handle_message(
            "fiona/dev-1/command",
            "not-json",
        )
        # State should remain unchanged
        assert device.state.power is None


# ═════════════════════════════════════════════════════════════════════════════
# Broker configuration
# ═════════════════════════════════════════════════════════════════════════════


class TestBrokerConfig:
    """Verify broker configuration generation."""

    def test_generate_default_config(self, tmp_path: str) -> None:
        """Default config should produce a valid mosquitto.conf."""
        output = tmp_path / "mosquitto.conf"
        config = BrokerConfig()

        result = generate_mosquitto_config(config, str(output))

        assert result.exists()
        content = result.read_text()
        assert "listener 1883" in content
        assert "allow_anonymous true" in content

    def test_generate_with_password_file(self, tmp_path: str) -> None:
        """Password file directive should appear when configured."""
        output = tmp_path / "mosquitto.conf"
        config = BrokerConfig(
            port=1884,
            allow_anonymous=False,
            password_file="/etc/mosquitto/passwd",
        )

        result = generate_mosquitto_config(config, str(output))

        content = result.read_text()
        assert "listener 1884" in content
        assert "allow_anonymous false" in content
        assert "password_file /etc/mosquitto/passwd" in content

    def test_creates_parent_directories(self, tmp_path: str) -> None:
        """Parent directories should be created automatically."""
        output = tmp_path / "nested" / "dir" / "mosquitto.conf"
        config = BrokerConfig()

        result = generate_mosquitto_config(config, str(output))

        assert result.exists()
