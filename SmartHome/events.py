"""Event bus and event-handling utilities for the Smart Home platform.

Provides a lightweight publish/subscribe mechanism that allows decoupled
components to react to device events without direct dependencies on one
another.
"""

from __future__ import annotations

from typing import Any

from SmartHome.interfaces import EventHandler
from SmartHome.models import DeviceEvent


class EventBus:
    """Simple in-process pub/sub event bus for device events.

    Usage::

        bus = EventBus()
        bus.subscribe("state_changed", my_handler)
        await bus.publish(DeviceEvent(device_id="...", event_type="state_changed", ...))
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register *handler* to be called for every event of *event_type*.

        The same handler can be registered multiple times — it will be
        invoked once per registration.
        """
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a previously-registered *handler* for *event_type*.

        If the handler was registered more than once, only the *first*
        occurrence is removed.
        """
        handlers = self._handlers.get(event_type)
        if handlers is not None:
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    async def publish(self, event: DeviceEvent) -> None:
        """Deliver *event* to every handler registered for its ``event_type``.

        All handlers are awaited in registration order.  If a handler
        raises, subsequent handlers are still invoked (the exception is
        not propagated so that one failing listener does not silence
        others).
        """
        for handler in self._handlers.get(event.event_type, []):
            try:
                await handler(event)
            except Exception:
                # Log and swallow so one bad handler does not break the bus.
                # A production EventBus would route this through the platform
                # logger.
                import logging  # noqa: PLC0415  -- import inside method is intentional

                logging.getLogger(__name__).exception(
                    "Handler %r raised handling event %s", handler, event.event_id,
                )

    @property
    def handlers(self) -> dict[str, list[EventHandler]]:
        """Return a copy of the current handler map (read-only snapshot)."""
        return {k: list(v) for k, v in self._handlers.items()}
