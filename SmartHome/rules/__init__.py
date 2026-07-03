"""Automation rules engine for the Smart Home platform.

Provides composable conditions, pluggable actions, rule types, and the
:class:`AutomationEngine` that orchestrates event-driven and time-based
automation.
"""
from __future__ import annotations

from SmartHome.rules.actions import Action, ActionContext, DelayAction, SceneAction, SetStateAction, WebhookAction
from SmartHome.rules.conditions import (
    AndCondition,
    ComparisonCondition,
    Condition,
    DeviceCondition,
    NotCondition,
    OrCondition,
    TimeCondition,
)
from SmartHome.rules.engine import AutomationEngine
from SmartHome.rules.rules import ScheduleRule, StateChangeRule

__all__ = [
    "Action",
    "ActionContext",
    "AndCondition",
    "AutomationEngine",
    "ComparisonCondition",
    "Condition",
    "DelayAction",
    "DeviceCondition",
    "NotCondition",
    "OrCondition",
    "ScheduleRule",
    "SceneAction",
    "SetStateAction",
    "StateChangeRule",
    "TimeCondition",
    "WebhookAction",
]
