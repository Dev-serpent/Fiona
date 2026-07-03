"""MQTT message dispatcher — routes incoming messages to handlers.

The :class:`MqttMessageHandler` receives every inbound MQTT message and
directs it to the correct device driver or automation engine based on the
topic structure::

    fiona/{device_id}/command        → _handle_command
    fiona/{device_id}/state          → _handle_state
    fiona/{device_id}/event          → _handle_event
    fiona/{device_id}/available      → _handle_availability
    fiona/discovery/{device_id}/config → _handle_discovery
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from SmartHome.events import EventBus
from SmartHome.interfaces import IDeviceRegistry
from SmartHome.models import DeviceEvent, DeviceState

logger = logging.getLogger(__name__)


class MqttMessageHandler:
    """Dispatches incoming MQTT messages to device drivers and automation.

    The handler inspects the topic structure, extracts the device ID and
    sub-topic, and calls the appropriate private method.  Unknown or
    malformed topics are silently ignored (with a debug log line).
    """

    def __init__(
        self,
        registry: IDeviceRegistry,
        event_bus: EventBus,
        topic_prefix: str = "fiona",
    ) -> None:
        """Initialise the handler.

        Args:
            registry:      Device registry for looking up and updating devices.
            event_bus:     In-process event bus for publishing device events.
            topic_prefix:  The top-level MQTT topic namespace (default
                           ``"fiona"``).  Messages on other prefixes are
                           ignored.
        """
        self._registry = registry
        self._event_bus = event_bus
        self._prefix = topic_prefix.rstrip("/")

    # ── Main entry point ─────────────────────────────────────────────────────

    async def handle_message(self, topic: str, payload: str) -> None:
        """Route an incoming MQTT message to the appropriate handler.

        Args:
            topic:    The full MQTT topic string.
            payload:  The raw message payload (UTF-8 decoded).

        Messages whose prefix does not match ``self._prefix`` are silently
        ignored.  Exceptions raised by individual handlers are caught and
        logged so that one bad message does not disrupt subsequent ones.
        """
        logger.debug("MQTT message: %s -> %s", topic, payload[:200])

        try:
            parts = topic.split("/")
            if len(parts) < 3:
                logger.debug("Ignoring short topic: %s", topic)
                return

            prefix = parts[0]
            if prefix != self._prefix:
                return

            # fiona/discovery/{device_id}/config
            if parts[1] == "discovery" and len(parts) >= 4:
                await self._handle_discovery(parts[2], payload)
                return

            # fiona/{device_id}/...
            device_id = parts[1]
            subtopic = "/".join(parts[2:]) if len(parts) > 2 else ""

            if subtopic == "command":
                await self._handle_command(device_id, payload)
            elif subtopic == "state":
                await self._handle_state(device_id, payload)
            elif subtopic == "event":
                await self._handle_event(device_id, payload)
            elif subtopic == "available":
                await self._handle_availability(device_id, payload)
            else:
                logger.debug("Unknown subtopic: %s (device=%s)", subtopic, device_id)
        except Exception:  # noqa: BLE001
            logger.exception("Error handling MQTT message on topic: %s", topic)

    # ── Per-topic handlers ───────────────────────────────────────────────────

    async def _handle_discovery(self, device_id: str, payload: str) -> None:
        """Handle a device discovery announcement.

        Subclasses or downstream consumers should parse the payload (typically
        JSON) and register the device in the registry if it is not already
        known.

        Args:
            device_id: The device identifier from the topic.
            payload:   The raw message payload.
        """
        # Placeholder — concrete discovery logic lives in subclasses or
        # higher-level orchestrators.
        logger.info("Discovery announcement for device: %s", device_id)

    async def _handle_command(self, device_id: str, payload: str) -> None:
        """Handle a command message addressed to a device.

        The payload is expected to be a JSON-encoded dictionary of state
        values to set on the device.

        Args:
            device_id: The target device identifier.
            payload:   The raw message payload.
        """
        device = await self._registry.get(device_id)
        if device is None:
            logger.warning("Command for unknown device: %s", device_id)
            return

        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                logger.warning(
                    "Command payload for %s is not a dict: %s", device_id, type(data).__name__
                )
                return
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in command for %s: %s", device_id, exc)
            return

        # Update the local state copy
        for key, value in data.items():
            if hasattr(device.state, key):
                setattr(device.state, key, value)

        # Publish a state-changed event
        event = DeviceEvent(
            device_id=device_id,
            event_type="state_changed",
            data={"command": data},
        )
        await self._event_bus.publish(event)

        logger.info("Command applied to %s: %s", device_id, data)

    async def _handle_state(self, device_id: str, payload: str) -> None:
        """Handle a device state update.

        The payload is expected to be a JSON-encoded dictionary of state
        values reported by the device.

        Args:
            device_id: The reporting device identifier.
            payload:   The raw message payload.
        """
        device = await self._registry.get(device_id)
        if device is None:
            logger.warning("State update for unknown device: %s", device_id)
            return

        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                logger.warning(
                    "State payload for %s is not a dict: %s",
                    device_id,
                    type(data).__name__,
                )
                return
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in state update for %s: %s", device_id, exc)
            return

        # Apply state delta
        for key, value in data.items():
            if hasattr(device.state, key):
                setattr(device.state, key, value)

        # Publish a state-changed event
        event = DeviceEvent(
            device_id=device_id,
            event_type="state_changed",
            data={"state_update": data},
        )
        await self._event_bus.publish(event)

        logger.debug("State updated for %s: %s", device_id, data)

    async def _handle_event(self, device_id: str, payload: str) -> None:
        """Handle a device event notification.

        The payload is expected to be a JSON-encoded dictionary describing
        the event (e.g. ``{"event_type": "button_pressed", "data": {...}}``).

        Args:
            device_id: The device that generated the event.
            payload:   The raw message payload.
        """
        device = await self._registry.get(device_id)
        if device is None:
            logger.warning("Event from unknown device: %s", device_id)
            return

        try:
            data = json.loads(payload)
            if not isinstance(data, dict):
                logger.warning(
                    "Event payload for %s is not a dict: %s",
                    device_id,
                    type(data).__name__,
                )
                return
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in event from %s: %s", device_id, exc)
            return

        event_type = data.get("event_type", "device_event")
        event_data = data.get("data", data)

        event = DeviceEvent(
            device_id=device_id,
            event_type=event_type,
            data=event_data if isinstance(event_data, dict) else data,
        )
        await self._event_bus.publish(event)

        logger.info("Event from %s: %s", device_id, event_type)

    async def _handle_availability(self, device_id: str, payload: str) -> None:
        """Handle a device availability (online/offline) message.

        The payload is expected to be ``"online"`` or ``"offline"`` (or a JSON
        string with an ``"availability"`` key).

        Args:
            device_id: The device whose availability changed.
            payload:   The raw message payload.
        """
        from SmartHome.models import DeviceStatus  # import here for consistency

        device = await self._registry.get(device_id)
        if device is None:
            logger.warning("Availability for unknown device: %s", device_id)
            return

        # Determine new status from payload
        status_str = payload.strip().lower()
        if status_str == "online":
            new_status = DeviceStatus.ONLINE
        elif status_str in ("offline", "off"):
            new_status = DeviceStatus.OFFLINE
        else:
            logger.warning(
                "Unknown availability payload for %s: %s", device_id, payload
            )
            return

        if device.status != new_status:
            device.status = new_status
            logger.info("Device %s is now %s", device_id, new_status.value)

            event = DeviceEvent(
                device_id=device_id,
                event_type="availability_changed",
                data={"status": new_status.value},
            )
            await self._event_bus.publish(event)
