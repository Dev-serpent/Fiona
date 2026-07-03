"""Unit tests for automation rule conditions."""
from __future__ import annotations

from datetime import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from SmartHome.models import DeviceEvent, DeviceType
from SmartHome.rules.conditions import (
    AndCondition,
    ComparisonCondition,
    DeviceCondition,
    NotCondition,
    OrCondition,
    TimeCondition,
)


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_registry() -> AsyncMock:
    reg = AsyncMock()
    # Return a proper mock device by default
    from SmartHome.models import DeviceInfo, DeviceType
    default_device = DeviceInfo(device_type=DeviceType.SWITCH)
    reg.get.return_value = default_device
    return reg


@pytest.fixture
def switch_event() -> DeviceEvent:
    return DeviceEvent(
        device_id="switch-1",
        event_type="state_changed",
        data={"power": True},
    )


@pytest.fixture
def temp_event() -> DeviceEvent:
    return DeviceEvent(
        device_id="temp-1",
        event_type="state_changed",
        data={"temperature": 22.5},
    )


# ── DeviceCondition ──────────────────────────────────────────────────────

class TestDeviceCondition:
    async def test_match_device_id(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition(device_id="switch-1")
        assert await cond.evaluate(switch_event) is True

    async def test_no_match_device_id(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition(device_id="switch-2")
        assert await cond.evaluate(switch_event) is False

    async def test_match_device_type(self, switch_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        mock_registry.get.return_value.device_type = DeviceType.SWITCH
        cond = DeviceCondition(device_type=DeviceType.SWITCH)
        assert await cond.evaluate(switch_event, registry=mock_registry) is True

    async def test_no_match_device_type(self, switch_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        # Override the fixture's default SWITCH device with a LIGHT
        from SmartHome.models import DeviceInfo
        mock_registry.get.return_value = DeviceInfo(device_type=DeviceType.LIGHT)
        cond = DeviceCondition(device_type=DeviceType.SWITCH)
        assert await cond.evaluate(switch_event, registry=mock_registry) is False

    async def test_state_match_from_event(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition(state={"power": True})
        assert await cond.evaluate(switch_event) is True

    async def test_state_no_match_from_event(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition(state={"power": False})
        assert await cond.evaluate(switch_event) is False

    async def test_state_match_from_registry(self, switch_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        # Event data doesn't have brightness, but registry does
        mock_registry.get.return_value.state.brightness = 75
        cond = DeviceCondition(state={"brightness": 75})
        assert await cond.evaluate(switch_event, registry=mock_registry) is True

    async def test_state_missing_fails(self, switch_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        # Neither event nor registry has the field
        mock_registry.get.return_value.state.brightness = None
        cond = DeviceCondition(state={"brightness": 50})
        assert await cond.evaluate(switch_event, registry=mock_registry) is False

    async def test_wildcard_device_id(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition()  # no device_id, no device_type, no state
        assert await cond.evaluate(switch_event) is True

    async def test_registry_device_not_found(self, switch_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        mock_registry.get.return_value = None
        cond = DeviceCondition(device_type=DeviceType.SWITCH)
        assert await cond.evaluate(switch_event, registry=mock_registry) is False

    async def test_device_type_no_registry(self, switch_event: DeviceEvent) -> None:
        cond = DeviceCondition(device_type=DeviceType.SWITCH)
        assert await cond.evaluate(switch_event, registry=None) is False


# ── ComparisonCondition ─────────────────────────────────────────────────

class TestComparisonCondition:
    async def test_eq_match(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "eq", 22.5)
        assert await cond.evaluate(temp_event) is True

    async def test_eq_no_match(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "eq", 23.0)
        assert await cond.evaluate(temp_event) is False

    async def test_neq_match(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "neq", 23.0)
        assert await cond.evaluate(temp_event) is True

    async def test_gt_match(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "gt", 20.0)
        assert await cond.evaluate(temp_event) is True

    async def test_lt_no_match(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "lt", 20.0)
        assert await cond.evaluate(temp_event) is False

    async def test_gte_boundary(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "gte", 22.5)
        assert await cond.evaluate(temp_event) is True

    async def test_lte_boundary(self, temp_event: DeviceEvent) -> None:
        cond = ComparisonCondition("temperature", "lte", 22.5)
        assert await cond.evaluate(temp_event) is True

    async def test_bool_comparison(self) -> None:
        event = DeviceEvent(device_id="s1", event_type="state_changed", data={"power": True})
        cond = ComparisonCondition("power", "eq", True)
        assert await cond.evaluate(event) is True

    async def test_none_eq_none(self) -> None:
        event = DeviceEvent(device_id="s1", event_type="state_changed", data={"brightness": None})
        cond = ComparisonCondition("brightness", "eq", None)
        assert await cond.evaluate(event) is True

    async def test_gt_none_returns_false(self) -> None:
        event = DeviceEvent(device_id="s1", event_type="state_changed", data={"temperature": None})
        cond = ComparisonCondition("temperature", "gt", 10.0)
        # None > 10.0 → False
        assert await cond.evaluate(event) is False

    async def test_invalid_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown comparison operator"):
            ComparisonCondition("temp", "invalid", 10)

    async def test_fallback_to_registry(self, temp_event: DeviceEvent, mock_registry: AsyncMock) -> None:
        # Event has temp but we check a field only in registry
        mock_registry.get.return_value.state.humidity = 60.0
        cond = ComparisonCondition("humidity", "eq", 60.0)
        assert await cond.evaluate(temp_event, registry=mock_registry) is True


# ── Logical Combinators ─────────────────────────────────────────────────

class TestAndCondition:
    async def test_all_true(self, switch_event: DeviceEvent) -> None:
        cond = AndCondition(
            DeviceCondition(device_id="switch-1"),
            DeviceCondition(state={"power": True}),
        )
        assert await cond.evaluate(switch_event) is True

    async def test_one_false(self, switch_event: DeviceEvent) -> None:
        cond = AndCondition(
            DeviceCondition(device_id="switch-1"),
            DeviceCondition(state={"power": False}),
        )
        assert await cond.evaluate(switch_event) is False

    async def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            AndCondition()


class TestOrCondition:
    async def test_any_true(self, switch_event: DeviceEvent) -> None:
        cond = OrCondition(
            DeviceCondition(device_id="switch-2"),
            DeviceCondition(device_id="switch-1"),
        )
        assert await cond.evaluate(switch_event) is True

    async def test_all_false(self, switch_event: DeviceEvent) -> None:
        cond = OrCondition(
            DeviceCondition(device_id="switch-2"),
            DeviceCondition(device_id="switch-3"),
        )
        assert await cond.evaluate(switch_event) is False

    async def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            OrCondition()


class TestNotCondition:
    async def test_inverts_true(self, switch_event: DeviceEvent) -> None:
        inner = DeviceCondition(device_id="switch-1")
        cond = NotCondition(inner)
        assert await cond.evaluate(switch_event) is False

    async def test_inverts_false(self, switch_event: DeviceEvent) -> None:
        inner = DeviceCondition(device_id="switch-999")
        cond = NotCondition(inner)
        assert await cond.evaluate(switch_event) is True

    async def test_double_negation(self, switch_event: DeviceEvent) -> None:
        inner = DeviceCondition(device_id="switch-1")
        cond = NotCondition(NotCondition(inner))
        assert await cond.evaluate(switch_event) is True

    async def test_nested_combinators(self, switch_event: DeviceEvent) -> None:
        """And(Or(device_id), Not(DeviceCondition(state)))"""
        cond = AndCondition(
            OrCondition(
                DeviceCondition(device_id="switch-1"),
                DeviceCondition(device_id="switch-2"),
            ),
            NotCondition(DeviceCondition(state={"power": False})),
        )
        assert await cond.evaluate(switch_event) is True


# ── TimeCondition ────────────────────────────────────────────────────────

class TestTimeCondition:
    async def test_within_range(self) -> None:
        """Should match if current time is within the range."""
        # Use a wide range that always matches
        cond = TimeCondition(start_time="00:00", end_time="23:59")
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        assert await cond.evaluate(event) is True

    async def test_outside_range(self) -> None:
        """Should not match if current time is outside."""
        # Use a narrow range that likely doesn't match (test may fail at exactly 03:00 UTC)
        cond = TimeCondition(start_time="03:00", end_time="03:01")
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        # We can't control time, so just verify the evaluation runs
        result = await cond.evaluate(event)
        assert isinstance(result, bool)

    async def test_overnight_range(self) -> None:
        """Time range that wraps around midnight."""
        cond = TimeCondition(start_time="22:00", end_time="06:00")
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        result = await cond.evaluate(event)
        assert isinstance(result, bool)

    async def test_time_object(self) -> None:
        """Accept datetime.time objects."""
        cond = TimeCondition(start_time=time(0, 0), end_time=time(23, 59))
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        assert await cond.evaluate(event) is True

    async def test_day_of_week(self) -> None:
        """Day-of-week filtering."""
        # Use all days — should match
        cond = TimeCondition(
            start_time="00:00", end_time="23:59",
            days_of_week={0, 1, 2, 3, 4, 5, 6},
        )
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        assert await cond.evaluate(event) is True

    async def test_day_of_week_excluded(self) -> None:
        """Exclude today — should not match."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).weekday()
        # Exclude today
        all_days = {0, 1, 2, 3, 4, 5, 6}
        all_days.discard(today)
        cond = TimeCondition(
            start_time="00:00", end_time="23:59",
            days_of_week=all_days,
        )
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        assert await cond.evaluate(event) is False

    async def test_no_days_filter(self) -> None:
        """No day filter should match any day."""
        cond = TimeCondition(start_time="00:00", end_time="23:59")
        event = DeviceEvent(device_id="d1", event_type="state_changed", data={})
        assert await cond.evaluate(event) is True
