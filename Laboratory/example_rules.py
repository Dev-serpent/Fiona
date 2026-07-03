"""Example automation rules for the Fiona IoT Laboratory.

These rules demonstrate the capabilities of the automation engine and can
be loaded into the :class:`AutomationEngine` at startup.
"""
from __future__ import annotations

from SmartHome.models import DeviceType
from SmartHome.rules.actions import DelayAction, SceneAction, SetStateAction
from SmartHome.rules.conditions import (
    AndCondition,
    ComparisonCondition,
    DeviceCondition,
    NotCondition,
    OrCondition,
    TimeCondition,
)
from SmartHome.rules.rules import ScheduleRule, StateChangeRule


def build_example_rules() -> list:
    """Return a list of example :class:`AutomationRule` instances.

    Each rule is fully wired with conditions and actions ready to be
    registered with an :class:`AutomationEngine`.
    """
    rules = []

    # ── Rule 1: Motion-activated light ────────────────────────────────────
    # When hallway motion is detected and it's dark, turn on the living room light.
    rules.append(
        StateChangeRule(
            rule_id="motion_light",
            condition=AndCondition(
                DeviceCondition(
                    device_id="hallway-motion",
                    state={"motion_detected": True},
                ),
                TimeCondition(start_time="18:00", end_time="07:00"),
            ),
            action=SetStateAction(
                device_id="living-room-light",
                state={"power": True, "brightness": 80},
            ),
        )
    )

    # ── Rule 2: Away mode — turn everything off ───────────────────────────
    # When the front door is closed after 10 PM, turn off lights and plug.
    rules.append(
        StateChangeRule(
            rule_id="away_mode",
            condition=AndCondition(
                DeviceCondition(
                    device_id="front-door",
                    state={"door_open": False},
                ),
                TimeCondition(start_time="22:00", end_time="06:00"),
            ),
            action=AndAction(
                SetStateAction("living-room-light", {"power": False}),
                SetStateAction("bedroom-light", {"power": False}),
                SetStateAction("garage-plug", {"power": False}),
            ),
        )
    )

    # ── Rule 3: Temperature alert ─────────────────────────────────────────
    # When outdoor temperature exceeds 35°C, log an alert.
    rules.append(
        StateChangeRule(
            rule_id="temp_alert",
            condition=AndCondition(
                DeviceCondition(device_id="outdoor-temp"),
                ComparisonCondition("temperature", "gt", 35.0),
            ),
            action=SetStateAction(
                device_id="living-room-thermostat",
                state={"hvac_mode": "cool", "target_temperature": 24.0},
            ),
        )
    )

    # ── Rule 4: Morning schedule ──────────────────────────────────────────
    # Every weekday at 07:00, turn on the bedroom light gradually.
    rules.append(
        ScheduleRule(
            rule_id="morning_alarm",
            cron_expression="0 7 * * 1-5",
            action=AndAction(
                SetStateAction("bedroom-light", {"power": True, "brightness": 30}),
                DelayAction(
                    delay=300.0,  # 5 minutes
                    action=SetStateAction(
                        "bedroom-light", {"brightness": 80}
                    ),
                ),
            ),
        )
    )

    # ── Rule 5: Night mode ───────────────────────────────────────────────
    # Between 23:00 and 06:00, turn off all lights if any are left on.
    rules.append(
        ScheduleRule(
            rule_id="night_mode",
            interval=600.0,  # check every 10 minutes
            action=SetStateAction(
                "living-room-light", {"power": False},
            ),
        )
    )

    return rules


# ── Helper: composite action ─────────────────────────────────────────────

class AndAction:
    """Executes multiple actions in sequence.

    This is a convenience composite that runs child actions one after
    another.  It wraps the list so it can be passed where a single
    :class:`Action` is expected.
    """

    def __init__(self, *actions) -> None:
        self._actions = actions

    async def execute(self, context) -> None:
        for action in self._actions:
            if hasattr(action, "execute"):
                await action.execute(context)
