"""Unit tests for rule types (StateChangeRule, ScheduleRule)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from SmartHome.models import DeviceEvent
from SmartHome.rules.actions import Action, ActionContext, SetStateAction
from SmartHome.rules.conditions import Condition, DeviceCondition
from SmartHome.rules.rules import ScheduleRule, StateChangeRule


# ── Helpers ──────────────────────────────────────────────────────────────

class AlwaysTrueCondition(Condition):
    """A condition that always evaluates to True."""

    async def evaluate(self, event: DeviceEvent, registry=None) -> bool:
        return True


class AlwaysFalseCondition(Condition):
    """A condition that always evaluates to False."""

    async def evaluate(self, event: DeviceEvent, registry=None) -> bool:
        return False


@pytest.fixture
def action_double() -> AsyncMock:
    """A mock action that tracks calls."""
    mock = AsyncMock(spec=Action)
    mock.execute = AsyncMock()
    return mock


@pytest.fixture
def action_context() -> ActionContext:
    return ActionContext()


@pytest.fixture
def switch_event() -> DeviceEvent:
    return DeviceEvent(
        device_id="switch-1",
        event_type="state_changed",
        data={"power": True},
    )


# ── StateChangeRule ──────────────────────────────────────────────────────

class TestStateChangeRule:
    async def test_triggers_on_match(
        self, action_double: AsyncMock, action_context: ActionContext, switch_event: DeviceEvent
    ) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action_double,
        )
        rule._wire(action_context)
        await rule.evaluate(switch_event)
        action_double.execute.assert_awaited_once()

    async def test_does_not_trigger_on_no_match(
        self, action_double: AsyncMock, action_context: ActionContext, switch_event: DeviceEvent
    ) -> None:
        rule = StateChangeRule(
            condition=AlwaysFalseCondition(),
            action=action_double,
        )
        rule._wire(action_context)
        await rule.evaluate(switch_event)
        action_double.execute.assert_not_called()

    async def test_disabled_rule_does_not_execute(
        self, action_double: AsyncMock, action_context: ActionContext, switch_event: DeviceEvent
    ) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=action_double,
            enabled=False,
        )
        rule._wire(action_context)
        await rule.evaluate(switch_event)
        action_double.execute.assert_not_called()

    async def test_auto_generates_rule_id(self) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
        )
        assert rule.rule_id is not None
        assert len(rule.rule_id) > 0

    async def test_custom_rule_id(self) -> None:
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
            rule_id="my-rule",
        )
        assert rule.rule_id == "my-rule"

    async def test_error_in_condition_logged_not_raised(
        self, action_context: ActionContext, switch_event: DeviceEvent
    ) -> None:
        """A failing condition should not propagate the exception."""

        class BrokenCondition(Condition):
            async def evaluate(self, event, registry=None):
                raise RuntimeError("condition failed")

        rule = StateChangeRule(
            condition=BrokenCondition(),
            action=AsyncMock(spec=Action),
        )
        rule._wire(action_context)
        # Should not raise
        await rule.evaluate(switch_event)

    async def test_no_context_no_crash(
        self, switch_event: DeviceEvent
    ) -> None:
        """Rule without wired context should not crash."""
        rule = StateChangeRule(
            condition=AlwaysTrueCondition(),
            action=AsyncMock(spec=Action),
        )
        # _wire not called — context is None
        await rule.evaluate(switch_event)

    async def test_state_change_rule_with_device_condition(
        self, action_context: ActionContext, switch_event: DeviceEvent
    ) -> None:
        """Integration: DeviceCondition match triggers action."""
        action = AsyncMock(spec=Action)
        rule = StateChangeRule(
            condition=DeviceCondition(device_id="switch-1"),
            action=action,
        )
        rule._wire(action_context)
        await rule.evaluate(switch_event)
        action.execute.assert_awaited_once()


# ── ScheduleRule ─────────────────────────────────────────────────────────

class TestScheduleRule:
    async def test_requires_schedule(self) -> None:
        """Must provide cron or interval."""
        with pytest.raises(ValueError, match="requires either"):
            ScheduleRule(action=AsyncMock(spec=Action))

    async def test_interval_due_on_first_call(
        self, action_double: AsyncMock, action_context: ActionContext
    ) -> None:
        """First evaluation fires immediately for interval rules."""
        rule = ScheduleRule(
            action=action_double,
            interval=60.0,
        )
        rule._wire(action_context)
        tick = DeviceEvent(
            device_id="__scheduler__",
            event_type="scheduler_tick",
            data={},
        )
        await rule.evaluate(tick)
        action_double.execute.assert_awaited_once()

    async def test_interval_not_due_yet(
        self, action_double: AsyncMock, action_context: ActionContext
    ) -> None:
        """Second evaluation within interval should not fire."""
        rule = ScheduleRule(
            action=action_double,
            interval=60.0,
        )
        rule._wire(action_context)
        tick = DeviceEvent(
            device_id="__scheduler__",
            event_type="scheduler_tick",
            data={},
        )
        # First call fires
        await rule.evaluate(tick)
        assert action_double.execute.await_count == 1

        # Second call — not due yet
        await rule.evaluate(tick)
        assert action_double.execute.await_count == 1

    async def test_disabled_rule_does_not_fire(
        self, action_double: AsyncMock, action_context: ActionContext
    ) -> None:
        rule = ScheduleRule(
            action=action_double,
            interval=0.01,
            enabled=False,
        )
        rule._wire(action_context)
        tick = DeviceEvent(
            device_id="__scheduler__",
            event_type="scheduler_tick",
            data={},
        )
        await rule.evaluate(tick)
        action_double.execute.assert_not_called()

    async def test_invalid_cron_expression_raises(self) -> None:
        """A bad cron expression should raise ValueError when croniter is installed."""
        from SmartHome.rules.rules import HAS_CRONITER
        if HAS_CRONITER:
            with pytest.raises(ValueError, match="Invalid cron"):
                ScheduleRule(
                    action=AsyncMock(spec=Action),
                    cron_expression="not-a-cron",
                )
        else:
            # Without croniter, expression is stored as-is
            rule = ScheduleRule(
                action=AsyncMock(spec=Action),
                cron_expression="not-a-cron",
            )
            assert rule._cron_expression == "not-a-cron"
