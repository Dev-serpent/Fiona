"""Pluggable action types for automation rules.

Actions are executed when a rule's condition is satisfied.  Each action
receives an :class:`ActionContext` that provides access to the platform's
services (registry, state setting, scene activation, HTTP client, etc.).
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from SmartHome.events import EventBus

logger = logging.getLogger(__name__)

# ── Action Context ───────────────────────────────────────────────────────

# Type alias for the ``set_state`` callable injected by the engine.
SetStateFn = Callable[[str, dict[str, Any]], Awaitable[None]]
ActivateSceneFn = Callable[[str], Awaitable[None]]


@dataclass
class ActionContext:
    """Context provided to every :class:`Action` when it executes.

    The :class:`AutomationEngine` populates this before invoking any action.
    Fields may be ``None`` if the corresponding service is not attached.
    """

    registry: Any = None
    """Optional :class:`IDeviceRegistry` instance."""

    set_state: Optional[SetStateFn] = None
    """Callable to set a device's state (``async (device_id, state_dict)``)."""

    activate_scene: Optional[ActivateSceneFn] = None
    """Callable to activate a scene (``async (scene_id)``)."""

    http_session: Any = None
    """Optional HTTP client session (e.g. ``aiohttp.ClientSession``)."""

    event_bus: Optional[EventBus] = None
    """Optional :class:`EventBus` for publishing action events."""

    _delay_tracker: set[asyncio.Task] = field(default_factory=set, repr=False)
    """Tracking set for pending :class:`DelayAction` tasks (internal)."""


# ── Base ─────────────────────────────────────────────────────────────────


class Action(ABC):
    """Abstract base class for all rule actions.

    Subclasses implement :meth:`execute` which performs the action's work.
    """

    @abstractmethod
    async def execute(self, context: ActionContext) -> None:
        """Execute this action.

        Args:
            context: The :class:`ActionContext` providing access to platform
                services.
        """


# ── SetStateAction ───────────────────────────────────────────────────────


class SetStateAction(Action):
    """Sets the state of a device when executed.

    Args:
        device_id: The target device.
        state: A dictionary of state fields to update.
    """

    def __init__(self, device_id: str, state: dict[str, Any]) -> None:
        self._device_id = device_id
        self._state = dict(state)

    async def execute(self, context: ActionContext) -> None:
        if context.set_state is not None:
            try:
                await context.set_state(self._device_id, self._state)
                logger.info(
                    "SetStateAction: state applied to %s", self._device_id
                )
            except Exception:
                logger.exception(
                    "SetStateAction: failed to set state for %s", self._device_id
                )
        else:
            logger.warning(
                "SetStateAction: no set_state callable in context "
                "(device %s)",
                self._device_id,
            )


# ── SceneAction ──────────────────────────────────────────────────────────


class SceneAction(Action):
    """Activates a scene when executed.

    Args:
        scene_id: The scene to activate.
    """

    def __init__(self, scene_id: str) -> None:
        self._scene_id = scene_id

    async def execute(self, context: ActionContext) -> None:
        if context.activate_scene is not None:
            try:
                await context.activate_scene(self._scene_id)
                logger.info("SceneAction: scene %s activated", self._scene_id)
            except Exception:
                logger.exception(
                    "SceneAction: failed to activate scene %s", self._scene_id
                )
        else:
            logger.warning(
                "SceneAction: no activate_scene callable in context "
                "(scene %s)",
                self._scene_id,
            )


# ── WebhookAction ────────────────────────────────────────────────────────


class WebhookAction(Action):
    """Sends an HTTP request to a webhook URL.

    Args:
        url: The target URL.
        method: HTTP method (default ``"POST"``).
        payload: Optional JSON-serialisable body.
        timeout: Request timeout in seconds (default 10).
    """

    def __init__(
        self,
        url: str,
        method: str = "POST",
        payload: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._url = url
        self._method = method.upper()
        self._payload = payload
        self._timeout = timeout

    async def execute(self, context: ActionContext) -> None:
        # Try aiohttp if available, otherwise fall back to requests via thread.
        try:
            import aiohttp

            await self._execute_aiohttp(context)
        except ImportError:
            await self._execute_requests(context)

    async def _execute_aiohttp(self, context: ActionContext) -> None:
        try:
            connector = context.http_session
            if connector is None:
                async with aiohttp.ClientSession() as session:
                    await self._do_request(session)
            else:
                # context.http_session is the session itself
                await self._do_request(context.http_session)
        except asyncio.TimeoutError:
            logger.warning("WebhookAction: timeout calling %s", self._url)
        except Exception:
            logger.exception("WebhookAction: failed calling %s", self._url)

    async def _do_request(self, session: Any) -> None:
        async with session.request(
            self._method,
            self._url,
            json=self._payload,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as resp:
            logger.info(
                "WebhookAction: %s %s → %d", self._method, self._url, resp.status
            )

    async def _execute_requests(self, context: ActionContext) -> None:
        try:
            import requests

            def _sync() -> None:
                resp = requests.request(
                    method=self._method,
                    url=self._url,
                    json=self._payload,
                    timeout=self._timeout,
                )
                logger.info(
                    "WebhookAction: %s %s → %d",
                    self._method,
                    self._url,
                    resp.status_code,
                )

            await asyncio.to_thread(_sync)
        except Exception:
            logger.exception("WebhookAction: failed calling %s", self._url)


# ── DelayAction ──────────────────────────────────────────────────────────


class DelayAction(Action):
    """Delays execution of a nested action by a given number of seconds.

    Args:
        delay: Seconds to wait before executing the nested action (clamped
            to 0 if negative).
        action: The inner action to execute after the delay.
    """

    def __init__(self, delay: float, action: Action) -> None:
        self._delay = max(0.0, delay)
        self._action = action

    async def execute(self, context: ActionContext) -> None:
        async def _delayed() -> None:
            await asyncio.sleep(self._delay)
            await self._action.execute(context)

        task = asyncio.create_task(_delayed())
        context._delay_tracker.add(task)
        task.add_done_callback(context._delay_tracker.discard)
        # Do not await — the action runs in the background.
        # The engine tracks these tasks for cancellation on stop().


__all__ = [
    "Action",
    "ActionContext",
    "DelayAction",
    "SceneAction",
    "SetStateAction",
    "WebhookAction",
]
