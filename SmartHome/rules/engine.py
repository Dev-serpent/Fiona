"""Automation engine — event-driven and time-based rule execution.

Implements :class:`SmartHome.interfaces.IAutomationEngine`.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from SmartHome.events import EventBus
from SmartHome.interfaces import IAutomationEngine
from SmartHome.models import DeviceEvent
from SmartHome.rules.actions import ActionContext
from SmartHome.rules.rules import ScheduleRule, StateChangeRule

logger = logging.getLogger(__name__)

# Maximum number of chained evaluations before the engine suspects a loop.
_MAX_EVALUATE_DEPTH = 10

# How often the scheduler loop ticks (seconds).
_SCHEDULER_TICK = 30


class AutomationEngine(IAutomationEngine):
    """Event-driven and time-based automation engine.

    Usage::

        engine = AutomationEngine(registry=..., event_bus=...)
        rule = StateChangeRule(condition=..., action=...)
        await engine.add_rule(rule)
        await engine.start()
        # ... events flow through the engine ...
        await engine.stop()
    """

    def __init__(
        self,
        registry: Any = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus

        # Rule storage
        self._rules: dict[str, Any] = {}  # rule_id → AutomationRule
        self._lock = asyncio.Lock()

        # Lifecycle
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None

        # Depth tracking for loop detection
        self._evaluate_depth: int = 0

        # Delay task tracking (shared with ActionContext)
        self._pending_delays: set[asyncio.Task] = set()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """``True`` when the engine is actively processing events."""
        return self._running

    # ── Rule CRUD ────────────────────────────────────────────────────────

    async def add_rule(self, rule: Any) -> str:
        """Register a new automation rule.

        Args:
            rule: A :class:`StateChangeRule` or :class:`ScheduleRule`.

        Returns:
            The ``rule_id`` assigned to the rule.
        """
        async with self._lock:
            context = self._build_context()
            # Wire the rule with context and registry
            if hasattr(rule, "_wire"):
                rule._wire(context, registry=self._registry)
            self._rules[rule.rule_id] = rule
        logger.info("AutomationEngine: rule %s added (%s)", rule.rule_id, type(rule).__name__)
        return rule.rule_id

    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by its *rule_id*.

        Returns:
            ``True`` if the rule was found and removed.
        """
        async with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                logger.info("AutomationEngine: rule %s removed", rule_id)
                return True
        return False

    async def list_rules(self) -> list[Any]:
        """Return all registered automation rules."""
        async with self._lock:
            return list(self._rules.values())

    async def get_rule(self, rule_id: str) -> Any | None:
        """Look up a rule by its *rule_id*.

        Returns:
            The rule or ``None`` if not found.
        """
        return self._rules.get(rule_id)

    # ── Enable / Disable ─────────────────────────────────────────────────

    async def enable_rule(self, rule_id: str) -> bool:
        """Enable a previously-disabled rule.

        Returns:
            ``True`` if the rule was found and enabled.
        """
        async with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return False
            rule.enabled = True
            logger.info("AutomationEngine: rule %s enabled", rule_id)
            return True

    async def disable_rule(self, rule_id: str) -> bool:
        """Disable an enabled rule without removing it.

        Returns:
            ``True`` if the rule was found and disabled.
        """
        async with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                return False
            rule.enabled = False
            logger.info("AutomationEngine: rule %s disabled", rule_id)
            return True

    # ── Event dispatch ───────────────────────────────────────────────────

    async def evaluate(self, event: DeviceEvent) -> None:
        """Dispatch a device event to all enabled :class:`StateChangeRule` instances.

        Args:
            event: The device event to evaluate.
        """
        if not self._running:
            return

        # Depth tracking for loop detection
        self._evaluate_depth += 1
        if self._evaluate_depth > _MAX_EVALUATE_DEPTH:
            logger.warning(
                "AutomationEngine: evaluate depth exceeded %d — "
                "possible rule loop, dropping event %s",
                _MAX_EVALUATE_DEPTH,
                event.event_id,
            )
            self._evaluate_depth -= 1
            return

        try:
            rules = self._get_rules_snapshot()
            for rule in rules:
                if not rule.enabled:
                    continue
                if isinstance(rule, StateChangeRule):
                    try:
                        await rule.evaluate(event)
                    except Exception:
                        logger.exception(
                            "AutomationEngine: error evaluating rule %s",
                            rule.rule_id,
                        )
        finally:
            self._evaluate_depth -= 1

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the automation engine.

        * Subscribes to the :class:`EventBus` (if attached).
        * Launches the scheduler loop for time-based rules.
        """
        if self._running:
            return
        self._running = True

        # Subscribe to relevant event types
        if self._event_bus is not None:
            self._event_bus.subscribe("state_changed", self.evaluate)

        # Start scheduler loop
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        logger.info("AutomationEngine: started")

    async def stop(self) -> None:
        """Stop the automation engine.

        * Unsubscribes from the :class:`EventBus`.
        * Cancels the scheduler loop.
        * Cancels any pending :class:`DelayAction` tasks.
        """
        self._running = False

        # Unsubscribe from EventBus
        if self._event_bus is not None:
            self._event_bus.unsubscribe("state_changed", self.evaluate)

        # Cancel scheduler loop
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

        # Cancel pending delay tasks
        for task in list(self._pending_delays):
            task.cancel()
        self._pending_delays.clear()

        logger.info("AutomationEngine: stopped")

    # ── Action context builder ───────────────────────────────────────────

    def _build_context(self) -> ActionContext:
        """Create an :class:`ActionContext` wired to this engine's services."""
        return ActionContext(
            registry=self._registry,
            set_state=self._set_device_state,
            activate_scene=self._activate_scene,
            event_bus=self._event_bus,
            _delay_tracker=self._pending_delays,
        )

    async def _set_device_state(
        self, device_id: str, state: dict[str, Any]
    ) -> None:
        """Internal callback used by :class:`SetStateAction`.

        Updates the device's state in the registry and publishes a
        ``state_changed`` event.
        """
        if self._registry is None:
            logger.warning(
                "Cannot set state for %s: no registry attached", device_id
            )
            return

        info = await self._registry.get(device_id)
        if info is None:
            logger.warning(
                "Cannot set state for %s: device not found in registry",
                device_id,
            )
            return

        # Update state fields
        for key, value in state.items():
            if hasattr(info.state, key):
                setattr(info.state, key, value)

        # Publish event so other rules can react
        if self._event_bus is not None:
            event = DeviceEvent(
                device_id=device_id,
                event_type="state_changed",
                data=state,
            )
            await self._event_bus.publish(event)

    async def _activate_scene(self, scene_id: str) -> None:
        """Internal callback used by :class:`SceneAction`.

        Looks up the scene and applies its state to each referenced device.
        """
        if self._registry is None:
            logger.warning(
                "Cannot activate scene %s: no registry attached", scene_id
            )
            return

        # We need a scene store.  For now, log the request.
        # In a production build, the engine would be wired to a scene store.
        logger.info(
            "Scene activation requested: %s (scene store not yet wired)",
            scene_id,
        )

    # ── Scheduler ────────────────────────────────────────────────────────

    async def _scheduler_loop(self) -> None:
        """Background task that periodically ticks schedule-based rules."""
        while self._running:
            try:
                await self._tick_scheduler()
            except Exception:
                logger.exception("AutomationEngine: scheduler loop error")
            await asyncio.sleep(_SCHEDULER_TICK)

    async def _tick_scheduler(self) -> None:
        """Evaluate all :class:`ScheduleRule` instances against the current time."""
        rules = self._get_rules_snapshot()
        tick_event = DeviceEvent(
            device_id="__scheduler__",
            event_type="scheduler_tick",
            data={},
        )
        for rule in rules:
            if not rule.enabled:
                continue
            if isinstance(rule, ScheduleRule):
                try:
                    await rule.evaluate(tick_event)
                except Exception:
                    logger.exception(
                        "AutomationEngine: error in schedule rule %s",
                        rule.rule_id,
                    )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_rules_snapshot(self) -> list[Any]:
        """Return a copy of the rules list (thread-safe)."""
        # No lock needed here because we are in asyncio and the dict is not
        # mutated from multiple coroutines without explicit locking.
        # However, we copy for consistency during iteration.
        return list(self._rules.values())


__all__ = ["AutomationEngine"]
