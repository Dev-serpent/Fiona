"""Error hierarchy for the Smart Home / IoT platform."""

from __future__ import annotations


class SmartHomeError(Exception):
    """Base error for all Smart Home platform errors."""


class DeviceNotFoundError(SmartHomeError):
    """Raised when a device is not found in the registry."""


class DeviceOfflineError(SmartHomeError):
    """Raised when attempting to communicate with an offline device."""


class DeviceTimeoutError(SmartHomeError):
    """Raised when a device communication times out."""


class MqttConnectionError(SmartHomeError):
    """Raised when the MQTT broker connection fails."""


class MqttPublishError(SmartHomeError):
    """Raised when publishing an MQTT message fails."""


class AutomationError(SmartHomeError):
    """Raised when an automation rule evaluation fails."""


class RuleNotFoundError(SmartHomeError):
    """Raised when an automation rule is not found."""


class GNS3ConnectionError(SmartHomeError):
    """Raised when connecting to a GNS3 server fails."""


class GNS3ProjectError(SmartHomeError):
    """Raised when a GNS3 project operation fails."""
