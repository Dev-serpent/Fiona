"""Composable condition types for automation rules.

Conditions are evaluated against a :class:`DeviceEvent` to determine whether
a rule's action should be triggered.  Conditions can be combined logically
using :class:`AndCondition`, :class:`OrCondition`, and :class:`NotCondition`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, time, timezone
from typing import Any, Optional

from SmartHome.models import DeviceEvent, DeviceType

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

_OPERATORS = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
}


# ── Base ─────────────────────────────────────────────────────────────────


class Condition(ABC):
    """Abstract base class for all rule conditions.

    Subclasses implement :meth:`evaluate` which returns ``True`` when the
    condition is satisfied.
    """

    @abstractmethod
    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        """Evaluate this condition against *event*.

        Args:
            event: The device event that triggered evaluation.
            registry: Optional :class:`IDeviceRegistry` for device lookups.

        Returns:
            ``True`` if the condition matches.
        """


# ── Device Condition ─────────────────────────────────────────────────────


class DeviceCondition(Condition):
    """Matches events based on device identity and state values.

    The condition succeeds when:
    * ``device_id`` matches (if specified), **and**
    * ``device_type`` matches (if specified, requires registry), **and**
    * Every key in ``state`` matches the corresponding value in the event
      data or current device state.
    """

    def __init__(
        self,
        device_id: str | None = None,
        device_type: DeviceType | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        self._device_id = device_id
        self._device_type = device_type
        self._state = state or {}

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        # 1. Device ID check
        if self._device_id is not None and event.device_id != self._device_id:
            return False

        # 2. Device type check (requires registry)
        if self._device_type is not None:
            if registry is None:
                logger.debug(
                    "DeviceCondition requires registry for device_type check"
                )
                return False
            info = await registry.get(event.device_id)
            if info is None or info.device_type != self._device_type:
                return False

        # 3. State field matching
        for key, expected in self._state.items():
            # First check event data
            actual = event.data.get(key)
            # Fall back to registry state lookup
            if actual is None and registry is not None:
                info = await registry.get(event.device_id)
                if info is not None:
                    actual = getattr(info.state, key, None)
            # Missing field → condition fails
            if actual is None:
                return False
            # Compare
            if actual != expected:
                return False

        return True


# ── Comparison Condition ─────────────────────────────────────────────────


class ComparisonCondition(Condition):
    """Compares a single state field against a reference value.

    Operators: ``eq``, ``neq``, ``gt``, ``lt``, ``gte``, ``lte``.

    The field value is resolved from the event data first, then from the
    registry device state as a fallback.
    """

    def __init__(
        self,
        field: str,
        operator: str,
        value: Any,
    ) -> None:
        if operator not in _OPERATORS:
            raise ValueError(
                f"Unknown comparison operator {operator!r}; "
                f"expected one of {sorted(_OPERATORS)}"
            )
        self._field = field
        self._operator = operator
        self._value = value

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        # Resolve the field value
        actual = event.data.get(self._field)
        if actual is None and registry is not None:
            info = await registry.get(event.device_id)
            if info is not None:
                actual = getattr(info.state, self._field, None)

        op_func = _OPERATORS[self._operator]
        return op_func(actual, self._value)


# ── Logical Combinators ──────────────────────────────────────────────────


class AndCondition(Condition):
    """Logical AND — all sub-conditions must be true.

    Short-circuits on the first ``False`` evaluation.
    """

    def __init__(self, *conditions: Condition) -> None:
        if not conditions:
            raise ValueError("AndCondition requires at least one sub-condition")
        self._conditions = conditions

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        for cond in self._conditions:
            if not await cond.evaluate(event, registry=registry):
                return False
        return True


class OrCondition(Condition):
    """Logical OR — at least one sub-condition must be true.

    Short-circuits on the first ``True`` evaluation.
    """

    def __init__(self, *conditions: Condition) -> None:
        if not conditions:
            raise ValueError("OrCondition requires at least one sub-condition")
        self._conditions = conditions

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        for cond in self._conditions:
            if await cond.evaluate(event, registry=registry):
                return True
        return False


class NotCondition(Condition):
    """Logical NOT — inverts the result of the wrapped condition."""

    def __init__(self, condition: Condition) -> None:
        self._condition = condition

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        return not await self._condition.evaluate(event, registry=registry)


# ── Time Condition ───────────────────────────────────────────────────────


class TimeCondition(Condition):
    """Matches events based on time-of-day and day-of-week.

    Time ranges can wrap around midnight (e.g. 22:00–06:00).

    Args:
        start_time: Start of the time range (``"HH:MM"`` string or
            :class:`datetime.time`).
        end_time: End of the time range.
        days_of_week: Optional set of day numbers where 0=Monday, 6=Sunday.
            When ``None``, all days match.
    """

    def __init__(
        self,
        start_time: str | time,
        end_time: str | time,
        days_of_week: set[int] | None = None,
    ) -> None:
        self._start = self._parse_time(start_time)
        self._end = self._parse_time(end_time)
        self._days = days_of_week

    @staticmethod
    def _parse_time(val: str | time) -> time:
        if isinstance(val, time):
            return val
        parts = val.split(":")
        return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)

    async def evaluate(
        self,
        event: DeviceEvent,
        registry: Any = None,
    ) -> bool:
        now = datetime.now(timezone.utc).time()

        # Day-of-week check
        if self._days is not None:
            today = datetime.now(timezone.utc).weekday()  # 0=Monday
            if today not in self._days:
                return False

        # Time range check (handles overnight wrapping)
        if self._start <= self._end:
            return self._start <= now <= self._end
        # Wraps around midnight
        return now >= self._start or now <= self._end


__all__ = [
    "AndCondition",
    "ComparisonCondition",
    "Condition",
    "DeviceCondition",
    "NotCondition",
    "OrCondition",
    "TimeCondition",
]
