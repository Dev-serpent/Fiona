"""Smart Home / IoT platform integration package.

Foundation layer providing data models, interfaces, configuration, event
handling, and device abstraction for the Fiona IoT ecosystem.
"""

from __future__ import annotations

from SmartHome.config import HomeBackendConfig, MqttConfig, load_homebackend_config, load_mqtt_config
from SmartHome.constants import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_ROOM,
    DEVICE_TIMEOUT,
    MQTT_RECONNECT_DELAY_MAX,
    MQTT_RECONNECT_DELAY_MIN,
    QOS_AT_LEAST_ONCE,
    QOS_AT_MOST_ONCE,
    QOS_EXACTLY_ONCE,
    TOPIC_BROADCAST,
    TOPIC_DEVICE_AVAILABILITY,
    TOPIC_DEVICE_COMMAND,
    TOPIC_DEVICE_EVENT,
    TOPIC_DEVICE_STATE,
    TOPIC_DISCOVERY,
    TOPIC_SCENE,
)
from SmartHome.errors import (
    AutomationError,
    DeviceNotFoundError,
    DeviceOfflineError,
    DeviceTimeoutError,
    GNS3ConnectionError,
    GNS3ProjectError,
    MqttConnectionError,
    MqttPublishError,
    RuleNotFoundError,
    SmartHomeError,
)
from SmartHome.events import EventBus
from SmartHome.interfaces import AutomationRule, EventHandler, IAutomationEngine, IDeviceDriver, IDeviceRegistry
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

# Re-export device-related classes.
try:
    from SmartHome.devices.base import BaseDeviceDriver  # noqa: F811
except ImportError:  # pragma: no cover
    BaseDeviceDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.door import DoorSensorDriver  # noqa: F811
except ImportError:
    DoorSensorDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.humidity import HumiditySensorDriver  # noqa: F811
except ImportError:
    HumiditySensorDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.lights import LightDriver  # noqa: F811
except ImportError:
    LightDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.motion import MotionSensorDriver  # noqa: F811
except ImportError:
    MotionSensorDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.plug import PlugDriver  # noqa: F811
except ImportError:
    PlugDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.registry import DeviceRegistry  # noqa: F811
except ImportError:
    DeviceRegistry = None  # type: ignore[assignment]

try:
    from SmartHome.devices.switch import SwitchDriver  # noqa: F811
except ImportError:
    SwitchDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.temperature import TemperatureSensorDriver  # noqa: F811
except ImportError:
    TemperatureSensorDriver = None  # type: ignore[assignment]

try:
    from SmartHome.devices.thermostat import ThermostatDriver  # noqa: F811
except ImportError:
    ThermostatDriver = None  # type: ignore[assignment]

# Re-export rule-related classes.
try:
    from SmartHome.rules.conditions import (  # noqa: F811
        AndCondition,
        ComparisonCondition,
        Condition,
        DeviceCondition,
        NotCondition,
        OrCondition,
        TimeCondition,
    )
except ImportError:
    Condition = None  # type: ignore[assignment]
    DeviceCondition = None  # type: ignore[assignment]
    ComparisonCondition = None  # type: ignore[assignment]
    AndCondition = None  # type: ignore[assignment]
    OrCondition = None  # type: ignore[assignment]
    NotCondition = None  # type: ignore[assignment]
    TimeCondition = None  # type: ignore[assignment]

try:
    from SmartHome.rules.actions import (  # noqa: F811
        Action,
        ActionContext,
        DelayAction,
        SceneAction,
        SetStateAction,
        WebhookAction,
    )
except ImportError:
    Action = None  # type: ignore[assignment]
    ActionContext = None  # type: ignore[assignment]
    SetStateAction = None  # type: ignore[assignment]
    SceneAction = None  # type: ignore[assignment]
    WebhookAction = None  # type: ignore[assignment]
    DelayAction = None  # type: ignore[assignment]

try:
    from SmartHome.rules.rules import ScheduleRule, StateChangeRule  # noqa: F811
except ImportError:
    StateChangeRule = None  # type: ignore[assignment]
    ScheduleRule = None  # type: ignore[assignment]

try:
    from SmartHome.rules.engine import AutomationEngine  # noqa: F811
except ImportError:
    AutomationEngine = None  # type: ignore[assignment]

__all__ = [
    # models
    "DeviceType",
    "DeviceStatus",
    "DeviceState",
    "DeviceProperties",
    "DeviceInfo",
    "DeviceEvent",
    "Room",
    "Scene",
    # interfaces
    "EventHandler",
    "IDeviceDriver",
    "IDeviceRegistry",
    "IAutomationEngine",
    "AutomationRule",
    # errors
    "SmartHomeError",
    "DeviceNotFoundError",
    "DeviceOfflineError",
    "DeviceTimeoutError",
    "MqttConnectionError",
    "MqttPublishError",
    "AutomationError",
    "RuleNotFoundError",
    "GNS3ConnectionError",
    "GNS3ProjectError",
    # config
    "MqttConfig",
    "HomeBackendConfig",
    "load_mqtt_config",
    "load_homebackend_config",
    # constants
    "TOPIC_DEVICE_STATE",
    "TOPIC_DEVICE_COMMAND",
    "TOPIC_DEVICE_AVAILABILITY",
    "TOPIC_DEVICE_EVENT",
    "TOPIC_BROADCAST",
    "TOPIC_DISCOVERY",
    "TOPIC_SCENE",
    "QOS_AT_MOST_ONCE",
    "QOS_AT_LEAST_ONCE",
    "QOS_EXACTLY_ONCE",
    "DEFAULT_POLL_INTERVAL",
    "MQTT_RECONNECT_DELAY_MIN",
    "MQTT_RECONNECT_DELAY_MAX",
    "DEVICE_TIMEOUT",
    "DEFAULT_ROOM",
    # events
    "EventBus",
    # devices
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
    # rules — conditions
    "Condition",
    "DeviceCondition",
    "ComparisonCondition",
    "AndCondition",
    "OrCondition",
    "NotCondition",
    "TimeCondition",
    # rules — actions
    "Action",
    "ActionContext",
    "SetStateAction",
    "SceneAction",
    "WebhookAction",
    "DelayAction",
    # rules — rule types
    "StateChangeRule",
    "ScheduleRule",
    # rules — engine
    "AutomationEngine",
]
