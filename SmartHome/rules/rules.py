"""Rule types that bridge conditions and actions.

Two primary rule types are provided:

* :class:`StateChangeRule` — triggered by device events; evaluates a condition
  and, if matched, executes an action.
* :class:`ScheduleRule` — triggered by time (cron expression or fixed interval);
  executes an action when the schedule dictates.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from SmartHome.interfaces import AutomationRule
from SmartHome.models import DeviceEvent
from SmartHome.rules.actions import Action, ActionContext
from SmartHome.rules.conditions import Condition

logger = logging.getLogger(__name__)

# ── Cron matching (optional croniter dependency) ─────────────────────────

try:
    import croniter  # noqa: F401

    HAS_CRONITER = True
except ImportError:
    HAS_CRONITER = False


def _cron_matches(expression: str, moment: datetime) -> bool:
    """Check whether *moment* matches a cron expression.

    Uses ``croniter.match`` when available; otherwise raises
    :class:`NotImplementedError`.
    """
    if not HAS_CRONITER:
        raise NotImplementedError(
            "croniter is not installed.  Use interval-based scheduling instead, "
            "or install croniter: pip install croniter"
        )
    return croniter.croniter.match(expression, moment)


# ── StateChangeRule ──────────────────────────────────────────────────────


class StateChangeRule(AutomationRule):
    """An automation rule triggered by a device event.

    When an event arrives, the rule evaluates its condition.  If the
    condition matches, the associated action is executed.

    Args:
        condition: The condition to evaluate.
        action: The action to execute when the condition is met.
        rule_id: Optional unique identifier.  Auto-generated if omitted.
        enabled: Whether the rule starts enabled (default ``True``).
    """

    def __init__(
        self,
        condition: Condition,
        action: Action,
        rule_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.rule_id = rule_id or uuid4().hex
        self.enabled = enabled
        self._condition = condition
        self._action = action
        self._context: Optional[ActionContext] = None
        self._registry: Any = None

    # ── Internal wiring (set by AutomationEngine) ─────────────────────────

    def _wire(self, context: ActionContext, registry: Any = None) -> None:
        """Attach context and registry references (called by the engine)."""
        self._context = context
        self._registry = registry

    # ── Evaluation ───────────────────────────────────────────────────────

    async def evaluate(self, event: DeviceEvent) -> None:
        """Evaluate the condition and execute the action if matched.

        Args:
            event: The device event that triggered evaluation.
        """
        if not self.enabled:
            return
        try:
            matches = await self._condition.evaluate(
                event, registry=self._registry
            )
            if matches and self._context is not None:
                logger.debug(
                    "StateChangeRule %s: condition matched, executing action",
                    self.rule_id,
                )
                await self._action.execute(self._context)
        except Exception:
            logger.exception(
                "StateChangeRule %s: error during evaluation", self.rule_id
            )


# ── ScheduleRule ─────────────────────────────────────────────────────────


class ScheduleRule(AutomationRule):
    """An automation rule triggered by a schedule.

    Supports both cron expressions (via optional ``croniter`` dependency)
    and fixed-interval scheduling.  If both are provided, cron takes
    precedence.

    Args:
        action: The action to execute when the schedule fires.
        cron_expression: Standard cron expression (5 fields).  Requires
            the ``croniter`` package.
        interval: Fixed interval in seconds between executions.
        rule_id: Optional unique identifier.  Auto-generated if omitted.
        enabled: Whether the rule starts enabled (default ``True``).
    """

    def __init__(
        self,
        action: Action,
        cron_expression: str | None = None,
        interval: float | None = None,
        rule_id: str | None = None,
        enabled: bool = True,
    ) -> None:
        if not cron_expression and interval is None:
            raise ValueError(
                "ScheduleRule requires either cron_expression or interval"
            )

        self.rule_id = rule_id or uuid4().hex
        self.enabled = enabled
        self._action = action
        self._cron_expression = cron_expression
        self._interval = interval
        self.last_fired: Optional[datetime] = None
        self._context: Optional[ActionContext] = None
        self._registry: Any = None

        # Validate cron expression at construction time
        if cron_expression and HAS_CRONITER:
            try:
                croniter.croniter(cron_expression, datetime.now(timezone.utc))
            except Exception as exc:
                raise ValueError(
                    f"Invalid cron expression {cron_expression!r}: {exc}"
                ) from exc

    # ── Internal wiring (set by AutomationEngine) ─────────────────────────

    def _wire(self, context: ActionContext, registry: Any = None) -> None:
        self._context = context
        self._registry = registry

    # ── Evaluation ───────────────────────────────────────────────────────

    async def evaluate(self, event: DeviceEvent) -> None:
        """Check whether the schedule is due and execute the action.

        .. note::

            The *event* parameter is ignored for schedule rules — they
            only check the clock.  The engine passes a synthetic event
            with ``event_type="scheduler_tick"``.
        """
        if not self.enabled:
            return
        now = datetime.now(timezone.utc)

        try:
            if self._is_due(now):
                self.last_fired = now
                if self._context is not None:
                    logger.debug(
                        "ScheduleRule %s: due, executing action", self.rule_id
                    )
                    await self._action.execute(self._context)
        except Exception:
            logger.exception(
                "ScheduleRule %s: error during evaluation", self.rule_id
            )

    def _is_due(self, now: datetime) -> bool:
        """Determine whether the rule should fire at *now*."""
        # Cron takes precedence
        if self._cron_expression and HAS_CRONITER:
            try:
                return _cron_matches(self._cron_expression, now)
            except Exception:
                logger.exception(
                    "ScheduleRule %s: cron matching failed", self.rule_id
                )
                return False

        # Interval-based
        if self._interval is not None:
            if self.last_fired is None:
                # Never fired before — fire immediately
                return True
            elapsed = (now - self.last_fired).total_seconds()
            return elapsed >= self._interval

        return False


__all__ = [
    "ScheduleRule",
    "StateChangeRule",
]
