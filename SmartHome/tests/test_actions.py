"""Unit tests for automation rule actions."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from SmartHome.rules.actions import (
    Action,
    ActionContext,
    DelayAction,
    SceneAction,
    SetStateAction,
    WebhookAction,
)


@pytest.fixture
def context() -> ActionContext:
    return ActionContext(
        registry=AsyncMock(),
        set_state=AsyncMock(),
        activate_scene=AsyncMock(),
        http_session=None,
        event_bus=None,
    )


# ── SetStateAction ───────────────────────────────────────────────────────

class TestSetStateAction:
    async def test_executes(self, context: ActionContext) -> None:
        action = SetStateAction(device_id="light-1", state={"power": True})
        await action.execute(context)
        context.set_state.assert_awaited_once_with("light-1", {"power": True})

    async def test_no_set_state_fn(self) -> None:
        """Logs warning when context has no set_state."""
        ctx = ActionContext()
        action = SetStateAction(device_id="d1", state={"power": False})
        # Should not raise
        await action.execute(ctx)

    async def test_set_state_raises(self, context: ActionContext) -> None:
        """Error is logged, not propagated."""
        context.set_state = AsyncMock(side_effect=RuntimeError("fail"))
        action = SetStateAction(device_id="d1", state={"power": True})
        await action.execute(context)  # should not raise


# ── SceneAction ──────────────────────────────────────────────────────────

class TestSceneAction:
    async def test_executes(self, context: ActionContext) -> None:
        action = SceneAction(scene_id="scene-1")
        await action.execute(context)
        context.activate_scene.assert_awaited_once_with("scene-1")

    async def test_no_activate_scene_fn(self) -> None:
        ctx = ActionContext()
        action = SceneAction(scene_id="scene-1")
        await action.execute(ctx)  # should not raise

    async def test_activate_scene_raises(self, context: ActionContext) -> None:
        context.activate_scene = AsyncMock(side_effect=RuntimeError("fail"))
        action = SceneAction(scene_id="scene-1")
        await action.execute(context)  # should not raise


# ── WebhookAction ────────────────────────────────────────────────────────

class TestWebhookAction:
    async def test_creates_with_defaults(self) -> None:
        action = WebhookAction(url="https://example.com/hook")
        assert action._method == "POST"
        assert action._payload is None

    async def test_get_method(self) -> None:
        action = WebhookAction(url="https://example.com/hook", method="GET")
        assert action._method == "GET"

    async def test_execute_no_http_error(self) -> None:
        """Should not raise even if no HTTP client is available."""
        action = WebhookAction(url="https://example.com/hook")
        ctx = ActionContext()
        # Just verify it doesn't crash — actual HTTP would fail
        await action.execute(ctx)


# ── DelayAction ──────────────────────────────────────────────────────────

class TestDelayAction:
    async def test_clamps_negative_delay(self) -> None:
        action = DelayAction(delay=-5.0, action=SetStateAction("d1", {"power": True}))
        assert action._delay == 0.0

    async def test_executes_nested_action(self, context: ActionContext) -> None:
        inner = SetStateAction(device_id="d1", state={"power": True})
        action = DelayAction(delay=0.01, action=inner)
        await action.execute(context)
        # Give the background task a moment to run
        import asyncio
        await asyncio.sleep(0.05)
        context.set_state.assert_awaited_once_with("d1", {"power": True})

    async def test_delay_tracked_in_context(self, context: ActionContext) -> None:
        inner = SetStateAction(device_id="d1", state={"power": True})
        action = DelayAction(delay=10.0, action=inner)  # long delay
        await action.execute(context)
        assert len(context._delay_tracker) == 1
        # Clean up
        import asyncio
        for task in context._delay_tracker:
            task.cancel()
        await asyncio.sleep(0)


# ── Action context ───────────────────────────────────────────────────────

class TestActionContext:
    def test_defaults(self) -> None:
        ctx = ActionContext()
        assert ctx.registry is None
        assert ctx.set_state is None
        assert ctx.activate_scene is None
        assert ctx.http_session is None
        assert ctx.event_bus is None

    def test_with_values(self) -> None:
        set_state = AsyncMock()
        ctx = ActionContext(set_state=set_state)
        assert ctx.set_state is set_state
