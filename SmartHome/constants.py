"""Constants and topic patterns for the Smart Home / IoT platform."""

from __future__ import annotations

# ── MQTT Topic Patterns ──────────────────────────────────────────────────────
TOPIC_DEVICE_STATE = "{prefix}/{device_id}/state"            # Device publishes state
TOPIC_DEVICE_COMMAND = "{prefix}/{device_id}/command"         # Controller sends commands
TOPIC_DEVICE_AVAILABILITY = "{prefix}/{device_id}/available"  # LWT / availability
TOPIC_DEVICE_EVENT = "{prefix}/{device_id}/event"             # Device event notifications
TOPIC_BROADCAST = "{prefix}/broadcast/#"                      # Broadcast topics
TOPIC_DISCOVERY = "{prefix}/discovery"                        # Device discovery
TOPIC_SCENE = "{prefix}/scene/{scene_id}"                     # Scene activation

# ── MQTT QoS Levels ──────────────────────────────────────────────────────────
QOS_AT_MOST_ONCE = 0    # Telemetry / sensor readings
QOS_AT_LEAST_ONCE = 1   # Commands / state updates (default)
QOS_EXACTLY_ONCE = 2    # Critical commands (rarely needed)

# ── Timing ───────────────────────────────────────────────────────────────────
DEFAULT_POLL_INTERVAL = 60     # seconds
MQTT_RECONNECT_DELAY_MIN = 1   # seconds
MQTT_RECONNECT_DELAY_MAX = 120 # seconds
DEVICE_TIMEOUT = 10            # seconds

# ── Defaults ─────────────────────────────────────────────────────────────────
DEFAULT_ROOM = "default"
