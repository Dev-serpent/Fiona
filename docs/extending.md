# Extension Guide

This guide explains how to extend the Fiona IoT subsystem with custom
device drivers, conditions, actions, and rules.

---

## Adding a Device Driver

Device drivers live in `SmartHome/devices/` and extend
`BaseDeviceDriver`.

### Step 1: Create the driver class

```python
# SmartHome/devices/co2_sensor.py
from __future__ import annotations

from typing import Any

from SmartHome.devices.base import BaseDeviceDriver
from SmartHome.models import DeviceType


class CO2SensorDriver(BaseDeviceDriver):
    """Simulated CO₂ sensor."""

    _device_type = DeviceType.CUSTOM  # or add a new DeviceType enum member

    # Optional: define a range for validation
    _MIN_CO2: float = 300.0
    _MAX_CO2: float = 5000.0

    def __init__(self, device_id: str, name: str = "") -> None:
        super().__init__(device_id=device_id, name=name)
        self._state: dict[str, Any] = {
            "co2_ppm": None,
            "unit": "ppm",
        }

    def _validate_state(self, state: dict[str, Any]) -> None:
        """Validate CO₂ reading before applying."""
        if "co2_ppm" in state and state["co2_ppm"] is not None:
            val = state["co2_ppm"]
            if not isinstance(val, (int, float)):
                raise TypeError(f"co2_ppm must be numeric, got {type(val).__name__}")
            if not self._MIN_CO2 <= val <= self._MAX_CO2:
                raise ValueError(
                    f"co2_ppm {val} out of range "
                    f"[{self._MIN_CO2}, {self._MAX_CO2}]"
                )
```

### Step 2: Register in the package

```python
# SmartHome/devices/__init__.py
from SmartHome.devices.co2_sensor import CO2SensorDriver

__all__ = [
    # ... existing exports ...
    "CO2SensorDriver",
]
```

### Step 3: Update DeviceType enum (optional)

```python
# SmartHome/models.py
class DeviceType(str, Enum):
    # ... existing members ...
    CO2_SENSOR = "co2_sensor"
```

---

## Adding a Condition

Conditions implement `ICondition` and return `True`/`False`.

### Simple custom condition

```python
from SmartHome.rules.conditions import ICondition


class HumidityThresholdCondition(ICondition):
    """True when humidity exceeds a threshold for a specific device."""

    def __init__(self, device_id: str, threshold: float) -> None:
        self._device_id = device_id
        self._threshold = threshold

    async def evaluate(self, context: dict[str, Any]) -> bool:
        registry = context.get("device_registry")
        if registry is None:
            return False
        device = registry.get(self._device_id)
        if device is None:
            return False
        humidity = device.get_state().get("humidity")
        return humidity is not None and humidity > self._threshold
```

### Composing with existing conditions

```python
from SmartHome.rules.conditions import AndCondition, TimeCondition

complex_condition = AndCondition(
    HumidityThresholdCondition(device_id="basement-humidity", threshold=70.0),
    TimeCondition(start_time="00:00", end_time="06:00"),
)
```

---

## Adding an Action

Actions implement `IAction` with an `execute` method.

### Custom action

```python
from SmartHome.rules.actions import ActionContext, IAction


class LogAction(IAction):
    """Logs a message when executed."""

    def __init__(self, message: str) -> None:
        self._message = message

    async def execute(self, context: ActionContext) -> None:
        logger.info("[ACTION] %s", self._message)
```

### Composite action

```python
from SmartHome.rules.actions import DelayAction, SetStateAction

morning_light = AndAction(
    SetStateAction("bedroom-light", {"power": True, "brightness": 30}),
    DelayAction(delay=300.0, action=SetStateAction("bedroom-light", {"brightness": 80})),
)
```

---

## Adding a Rule

### State-change rule

```python
from SmartHome.rules.conditions import DeviceCondition
from SmartHome.rules.actions import SetStateAction
from SmartHome.rules.rules import StateChangeRule

rule = StateChangeRule(
    rule_id="co2_alert",
    condition=DeviceCondition(device_id="basement-co2-sensor"),
    action=SetStateAction("kitchen-switch", {"power": True}),
)
```

### Schedule rule

```python
from SmartHome.rules.actions import SetStateAction
from SmartHome.rules.rules import ScheduleRule

ventilation = ScheduleRule(
    rule_id="ventilation",
    cron_expression="0 */2 * * *",  # every 2 hours
    action=SetStateAction("kitchen-switch", {"power": True}),
)
```

---

## Registering in the Engine

```python
from SmartHome.rules.engine import AutomationEngine
from SmartHome.events import EventBus

engine = AutomationEngine(event_bus=EventBus())
engine.add_rule(my_rule)
engine.start()

# Later:
engine.stop()
```
