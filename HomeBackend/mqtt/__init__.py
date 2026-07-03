"""MQTT integration for the HomeBackend service.

Provides an async MQTT client with auto-reconnect, LWT, and retained messages;
a topic builder for constructing MQTT topic strings from device IDs; a message
handler that routes incoming messages to device drivers and automation; and a
broker configuration generator.
"""

from __future__ import annotations

from HomeBackend.mqtt.client import MqttClient
from HomeBackend.mqtt.topics import TopicBuilder
from HomeBackend.mqtt.handler import MqttMessageHandler

__all__ = ["MqttClient", "TopicBuilder", "MqttMessageHandler"]
