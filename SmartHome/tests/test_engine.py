"""Integration tests for the AutomationEngine."""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from SmartHome.devices.registry import DeviceRegistry
from SmartHome.events import EventBus
from SmartHome.models import DeviceEvent, DeviceInfo, DeviceProperties, DeviceType
from SmartHome.rules.actions import Action, ActionContext, DelayAction, SetStateAction
from SmartHome.rules.conditions import Condition, DeviceCondition
from SmartHome.rules.engine import AutomationEngine
from SmartHome.rules.rules import ScheduleRule, StateChangeRule


# ── Helpers ──────────────────────────────────────────────────────────────

class AlwaysTrueCondition(Condition):
    async def evaluate(self, event, registry=None) -> bool:
        return True


class AlwaysFalseCondition(Condition):
    async def evaluate(self, event, registry=None) -> bool:
        return False


class TrackingAction(Action):
    """Action that records invocations for later inspection."""

    def __init__(self) -> None:
        self.calls: list[tuple[ActionContext, str]] = []

    async def execute(self, context: ActionContext) -> None:
        self.calls.append((context, "executed"))


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def device_registry() -> DeviceRegistry:
    reg = DeviceRegistry()
    return reg


@pytest.fixture
def engine(event_bus: EventBus, device_registry: DeviceRegistry) -> AutomationEngine:
    eng = AutomationEngine(registry=device_registry, event_bus=event_bus)
    return eng


@pytest.fixture
def switch_event() -> DeviceEvent:
    return DeviceEvent(
        device_id="switch-1",
        event_type="state_changed",
        data={"power": True},
    )


# ── CRUD ─────────────────────────────────────────────────────────────────

class TestEngineCRUD:
    async def test_add_rule(self, engine: AutomationEngine) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
        )
        rule_id = await engine.add_rule(rule)
        assert rule_id == rule.rule_id
        rules = await engine.list_rules()
        assert len(rules) == 1
        assert rules[0].rule_id == rule_id

    async def test_remove_rule(self, engine: AutomationEngine) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
        )
        rule_id = await engine.add_rule(rule)
        removed = await engine.remove_rule(rule_id)
        assert removed is True
        rules = await engine.list_rules()
        assert len(rules) == 0

    async def test_remove_nonexistent(self, engine: AutomationEngine) -> None:
        removed = await engine.remove_rule("nonexistent")
        assert removed is False

    async def test_get_rule(self, engine: AutomationEngine) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
            rule_id="get-me",
        )
        await engine.add_rule(rule)
        got = await engine.get_rule("get-me")
        assert got is rule

    async def test_enable_disable(self, engine: AutomationEngine) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
            rule_id="toggle",
        )
        await engine.add_rule(rule)
        assert rule.enabled is True

        await engine.disable_rule("toggle")
        assert rule.enabled is False

        await engine.enable_rule("toggle")
        assert rule.enabled is True

    async def test_enable_unknown(self, engine: AutomationEngine) -> None:
        result = await engine.enable_rule("unknown")
        assert result is False

    async def test_disable_unknown(self, engine: AutomationEngine) -> None:
        result = await engine.disable_rule("unknown")
        assert result is False


# ── Event dispatch ───────────────────────────────────────────────────────

class TestEngineDispatch:
    async def test_event_triggers_matching_rule(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        action = TrackingAction()
        rule = StateChangeRule(
            condition=DeviceCondition(device_id="switch-1"),
            action=action,
        )
        await engine.add_rule(rule)
        await engine.start()

        await engine.evaluate(switch_event)
        assert len(action.calls) == 1

        await engine.stop()

    async def test_event_no_match(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        action = TrackingAction()
        rule = StateChangeRule(
            condition=DeviceCondition(device_id="switch-999"),  # wrong ID
            action=action,
        )
        await engine.add_rule(rule)
        await engine.start()

        await engine.evaluate(switch_event)
        assert len(action.calls) == 0

        await engine.stop()

    async def test_multiple_rules_all_fire(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        action1 = TrackingAction()
        action2 = TrackingAction()
        rule1 = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action1,
        )
        rule2 = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action2,
        )
        await engine.add_rule(rule1)
        await engine.add_rule(rule2)
        await engine.start()

        await engine.evaluate(switch_event)
        assert len(action1.calls) == 1
        assert len(action2.calls) == 1

        await engine.stop()

    async def test_error_isolation(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        """A failing rule should not prevent other rules from executing."""

        class BrokenCondition(Condition):
            async def evaluate(self, event, registry=None):
                raise RuntimeError("broken")

        good_action = TrackingAction()
        bad_rule = StateChangeRule(
            condition=BrokenCondition(),
            action=AsyncMock(spec=Action),
        )
        good_rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=good_action,
        )
        await engine.add_rule(bad_rule)
        await engine.add_rule(good_rule)
        await engine.start()

        await engine.evaluate(switch_event)
        assert len(good_action.calls) == 1

        await engine.stop()

    async def test_disabled_rule_skipped(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        action = TrackingAction()
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action,
            enabled=False,
        )
        await engine.add_rule(rule)
        await engine.start()

        await engine.evaluate(switch_event)
        assert len(action.calls) == 0

        await engine.stop()

    async def test_evaluate_before_start_is_noop(
        self, engine: AutomationEngine, switch_event: DeviceEvent
    ) -> None:
        action = TrackingAction()
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action,
        )
        await engine.add_rule(rule)
        # engine not started
        await engine.evaluate(switch_event)
        assert len(action.calls) == 0


# ── Schedule ─────────────────────────────────────────────────────────────

class TestEngineSchedule:
    async def test_interval_rule_fires(
        self, engine: AutomationEngine
    ) -> None:
        action = TrackingAction()
        rule = ScheduleRule(
            action=action,
            interval=0.01,  # very short interval
        )
        await engine.add_rule(rule)
        await engine.start()

        # Tick the scheduler manually
        await engine._tick_scheduler()
        assert len(action.calls) == 1

        await engine.stop()

    async def test_schedule_rule_not_due(
        self, engine: AutomationEngine
    ) -> None:
        action = TrackingAction()
        rule = ScheduleRule(
            action=action,
            interval=3600.0,  # 1 hour — won't be due
        )
        await engine.add_rule(rule)
        await engine.start()

        await engine._tick_scheduler()
        # First call always fires (last_fired is None)
        assert len(action.calls) == 1

        # Second tick — shouldn't fire again
        await engine._tick_scheduler()
        assert len(action.calls) == 1

        await engine.stop()


# ── Start/Stop ───────────────────────────────────────────────────────────

class TestEngineLifecycle:
    async def test_start_sets_running(self, engine: AutomationEngine) -> None:
        assert engine.is_running is False
        await engine.start()
        assert engine.is_running is True
        await engine.stop()
        assert engine.is_running is False

    async def test_start_twice_is_noop(self, engine: AutomationEngine) -> None:
        await engine.start()
        await engine.start()  # should not crash
        assert engine.is_running is True
        await engine.stop()

    async def test_stop_cancels_scheduler(self, engine: AutomationEngine) -> None:
        await engine.start()
        task = engine._scheduler_task
        assert task is not None
        assert not task.done()
        await engine.stop()
        assert task.done()

    async def test_event_bus_integration(
        self, event_bus: EventBus, engine: AutomationEngine
    ) -> None:
        """Events published on the EventBus should reach the engine."""
        action = TrackingAction()
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action,
        )
        await engine.add_rule(rule)
        await engine.start()

        # Publish via event bus
        event = DeviceEvent(
            device_id="test-device",
            event_type="state_changed",
            data={"power": True},
        )
        await event_bus.publish(event)
        await asyncio.sleep(0.01)  # let the event propagate
        assert len(action.calls) >= 1

        await engine.stop()

    async def test_without_event_bus(self) -> None:
        """Engine should work without an EventBus."""
        eng = AutomationEngine(registry=None, event_bus=None)
        action = TrackingAction()
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action,
        )
        await eng.add_rule(rule)
        await eng.start()
        assert eng.is_running is True

        # Direct evaluate should still work
        event = DeviceEvent(
            device_id="d1", event_type="state_changed", data={}
        )
        await eng.evaluate(event)
        assert len(action.calls) == 1

        await eng.stop()
