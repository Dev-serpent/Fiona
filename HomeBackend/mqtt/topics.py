"""MQTT topic hierarchy builder.

Topic hierarchy::

    fiona/{device_id}/state          — Device telemetry/state (publish)
    fiona/{device_id}/command        — Commands to device (subscribe)
    fiona/{device_id}/available      — LWT / availability
    fiona/{device_id}/event          — Device events
    fiona/discovery/{device_id}/config  — Discovery announcements
    fiona/scene/{scene_id}           — Scene activation
    fiona/broadcast/#                — Broadcast messages
"""

from __future__ import annotations

from SmartHome.constants import (
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_COMMAND,
    TOPIC_DEVICE_EVENT,
    TOPIC_DEVICE_STATE,
    TOPIC_DISCOVERY,
    TOPIC_SCENE,
)


class TopicBuilder:
    """Build MQTT topic strings from device IDs and properties.

    All topic strings are derived from a configurable *prefix* (default
    ``"fiona"``) so that renaming the top-level namespace is a single change.

    Usage::

        builder = TopicBuilder(prefix="fiona")
        state_topic = builder.device_state("sensor-01")
        # → "fiona/sensor-01/state"
    """

    def __init__(self, prefix: str = "fiona") -> None:
        """Initialise the builder with the given topic *prefix*.

        Args:
            prefix: The top-level namespace for all topics (default ``"fiona"``).
                    Trailing slashes are stripped automatically.
        """
        self._prefix = prefix.rstrip("/")

    # ── Device topics ────────────────────────────────────────────────────────

    def device_state(self, device_id: str) -> str:
        """Return the topic a device publishes its state to."""
        return TOPIC_DEVICE_STATE.format(prefix=self._prefix, device_id=device_id)

    def device_command(self, device_id: str) -> str:
        """Return the topic a device listens on for commands."""
        return TOPIC_DEVICE_COMMAND.format(prefix=self._prefix, device_id=device_id)

    def device_availability(self, device_id: str) -> str:
        """Return the topic a device announces its availability on."""
        return TOPIC_DEVICE_AVAILABILITY.format(prefix=self._prefix, device_id=device_id)

    def device_event(self, device_id: str) -> str:
        """Return the topic a device publishes events on."""
        return TOPIC_DEVICE_EVENT.format(prefix=self._prefix, device_id=device_id)

    # ── Discovery ───────────────────────────────────────────────────────────

    def discovery_config(self, device_id: str) -> str:
        """Return the topic for a device's discovery configuration announcement."""
        base = TOPIC_DISCOVERY.format(prefix=self._prefix)
        return f"{base}/{device_id}/config"

    # ── Scene ───────────────────────────────────────────────────────────────

    def scene(self, scene_id: str) -> str:
        """Return the topic for scene activation messages."""
        return TOPIC_SCENE.format(prefix=self._prefix, scene_id=scene_id)

    # ── Broadcast ───────────────────────────────────────────────────────────

    def broadcast(self) -> str:
        """Return the broadcast topic filter (``#`` wildcard)."""
        return f"{self._prefix}/broadcast/#"

    # ── Property access ─────────────────────────────────────────────────────

    @property
    def prefix(self) -> str:
        """The configured topic prefix (read-only)."""
        return self._prefix
