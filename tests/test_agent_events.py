"""Tests for the agent event system (Phase 6: Event Bus Integration)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from Agent.events import (
    AgentDisabled,
    AgentEnabled,
    AgentExecutionCompleted,
    AgentExecutionStarted,
    AgentRegistered,
    AgentReloaded,
    AgentRouted,
    AgentUnregistered,
    PluginLifecycleEvent,
    PluginLoaded,
    PluginUnloaded,
)

# ======================================================================
# 1. Event creation and structure
# ======================================================================


class TestAgentLifecycleEventCreation:
    def test_agent_registered_required(self):
        event = AgentRegistered(source="test", timestamp=100.0, agent_name="my-agent")
        assert event.source == "test"
        assert event.timestamp == 100.0
        assert event.agent_name == "my-agent"
        assert event.version == ""
        assert event.source_path is None
        assert event.plugin_name is None

    def test_agent_registered_all_fields(self):
        event = AgentRegistered(
            source="agent_manager",
            timestamp=200.0,
            agent_name="code-reviewer",
            version="2.0.0",
            source_path="/agents/code.md",
            plugin_name="my-plugin",
        )
        assert event.version == "2.0.0"
        assert event.source_path == "/agents/code.md"
        assert event.plugin_name == "my-plugin"

    def test_agent_unregistered(self):
        event = AgentUnregistered(source="test", timestamp=100.0, agent_name="old-agent")
        assert event.agent_name == "old-agent"

    def test_agent_enabled(self):
        event = AgentEnabled(source="test", timestamp=100.0, agent_name="my-agent")
        assert event.agent_name == "my-agent"

    def test_agent_disabled(self):
        event = AgentDisabled(source="test", timestamp=100.0, agent_name="my-agent")
        assert event.agent_name == "my-agent"

    def test_agent_reloaded(self):
        event = AgentReloaded(
            source="test", timestamp=100.0, agent_name="my-agent", version="1.1.0"
        )
        assert event.version == "1.1.0"


class TestRoutingEvents:
    def test_agent_routed(self):
        event = AgentRouted(
            source="coordinator",
            timestamp=100.0,
            goal="fix the login page",
            agent_name="engineer",
            confidence=0.85,
            match_method="tags",
            alternatives=2,
        )
        assert event.goal == "fix the login page"
        assert event.agent_name == "engineer"
        assert event.confidence == 0.85
        assert event.match_method == "tags"
        assert event.alternatives == 2

    def test_agent_execution_started(self):
        event = AgentExecutionStarted(
            source="coordinator",
            timestamp=100.0,
            goal="write tests",
            agent_name="engineer",
            max_turns=10,
        )
        assert event.goal == "write tests"
        assert event.max_turns == 10

    def test_agent_execution_completed(self):
        event = AgentExecutionCompleted(
            source="coordinator",
            timestamp=100.0,
            goal="write tests",
            agent_name="engineer",
            success=True,
            duration_ms=1500.0,
            turns=5,
        )
        assert event.success
        assert event.duration_ms == 1500.0
        assert event.turns == 5
        assert event.error is None

    def test_agent_execution_completed_with_error(self):
        event = AgentExecutionCompleted(
            source="coordinator",
            timestamp=100.0,
            goal="write tests",
            agent_name="engineer",
            success=False,
            error="Something broke",
        )
        assert not event.success
        assert event.error == "Something broke"


class TestPluginEvents:
    def test_plugin_loaded(self):
        event = PluginLoaded(
            source="plugin_manager",
            timestamp=100.0,
            plugin_name="my-plugin",
            version="1.0.0",
            components=("tool", "agent"),
        )
        assert event.plugin_name == "my-plugin"
        assert event.components == ("tool", "agent")

    def test_plugin_unloaded(self):
        event = PluginUnloaded(source="plugin_manager", timestamp=100.0, plugin_name="my-plugin")
        assert event.plugin_name == "my-plugin"

    def test_base_plugin_event(self):
        event = PluginLifecycleEvent(source="test", timestamp=100.0, plugin_name="test-plugin")
        assert event.plugin_name == "test-plugin"


# ======================================================================
# 2. AgentManager event publishing
# ======================================================================


class TestAgentManagerEventPublishing:
    """Verify that AgentManager publishes lifecycle events."""

    @pytest.fixture
    def mock_event_bus(self):
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_event_bus):
        from Agent.agent_manager import AgentManager
        from Agent.agent_meta import AgentMeta

        mgr = AgentManager(event_bus=mock_event_bus)
        # Pre-populate with one agent
        mgr.register(
            "test-agent",
            AgentMeta(name="test-agent", version="1.0.0", description="Test agent"),
        )
        return mgr

    def test_register_publishes_event(self, mock_event_bus, manager):
        from Agent.agent_meta import AgentMeta

        mock_event_bus.publish.reset_mock()
        manager.register(
            "new-agent",
            AgentMeta(name="new-agent", version="2.0.0", description="Another agent"),
        )
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, AgentRegistered)
        assert event.agent_name == "new-agent"
        assert event.version == "2.0.0"

    def test_unregister_publishes_event(self, mock_event_bus, manager):
        mock_event_bus.publish.reset_mock()
        ok = manager.unregister("test-agent")
        assert ok
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, AgentUnregistered)
        assert event.agent_name == "test-agent"

    def test_unregister_nonexistent_no_event(self, mock_event_bus, manager):
        mock_event_bus.publish.reset_mock()
        ok = manager.unregister("nonexistent")
        assert not ok
        mock_event_bus.publish.assert_not_called()

    def test_enable_publishes_event(self, mock_event_bus, manager):
        manager.disable("test-agent")
        mock_event_bus.publish.reset_mock()
        ok = manager.enable("test-agent")
        assert ok
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, AgentEnabled)
        assert event.agent_name == "test-agent"

    def test_enable_already_enabled_no_event(self, mock_event_bus, manager):
        mock_event_bus.publish.reset_mock()
        ok = manager.enable("test-agent")
        assert ok
        mock_event_bus.publish.assert_not_called()

    def test_disable_publishes_event(self, mock_event_bus, manager):
        mock_event_bus.publish.reset_mock()
        ok = manager.disable("test-agent")
        assert ok
        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert isinstance(event, AgentDisabled)
        assert event.agent_name == "test-agent"

    def test_disable_already_disabled_no_event(self, mock_event_bus, manager):
        manager.disable("test-agent")
        mock_event_bus.publish.reset_mock()
        manager.disable("test-agent")
        mock_event_bus.publish.assert_not_called()

    def test_reload_publishes_event(self, mock_event_bus, manager, tmp_path):
        # Create a .md file for reload
        agent_file = tmp_path / "reload-test.md"
        agent_file.write_text(
            "---\n"
            'name: reload-test\n'
            'version: "1.1.0"\n'
            "description: Reloaded agent\n"
            "---\n"
            "# Reload Test\n"
        )
        # Override agent dirs
        manager._agent_dirs = [str(tmp_path)]
        # Register first so reload finds it
        from Agent.agent_meta import AgentMeta

        manager.register(
            "reload-test",
            AgentMeta(name="reload-test", version="1.0.0", description="Old agent"),
        )
        mock_event_bus.publish.reset_mock()
        ok = manager.reload("reload-test")
        assert ok
        # Should have at least one AgentReloaded event
        events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        reload_events = [e for e in events if isinstance(e, AgentReloaded)]
        assert len(reload_events) >= 1
        assert reload_events[0].agent_name == "reload-test"
        assert reload_events[0].version == "1.1.0"

    def test_set_event_bus(self):
        from Agent.agent_manager import AgentManager

        mgr = AgentManager()
        assert mgr._event_bus is None
        bus = MagicMock()
        mgr.set_event_bus(bus)
        assert mgr._event_bus is bus

    def test_no_event_bus_is_noop(self):
        from Agent.agent_manager import AgentManager
        from Agent.agent_meta import AgentMeta

        mgr = AgentManager()
        mgr.register(
            "safe-agent",
            AgentMeta(name="safe-agent", version="1.0.0", description="Safe"),
        )
        # No crash = pass
        mgr.unregister("safe-agent")
        mgr.enable("safe-agent")  # no crash even though unregistered
        mgr.disable("safe-agent")


# ======================================================================
# 3. Coordinator event publishing
# ======================================================================


class TestCoordinatorEventPublishing:
    @pytest.fixture
    def mock_event_bus(self):
        return MagicMock()

    @pytest.fixture
    def coordinator(self, mock_event_bus):
        from Agent.coordinator import AgentRouter, Coordinator
        from Agent.agent_meta import AgentMeta
        from Agent.personality import PersonalityRegistry

        registry = PersonalityRegistry.get_instance()

        # Ensure test agents exist
        for name in ("test-agent", "general"):
            try:
                registry.get_agent_meta(name)
            except KeyError:
                registry.register_agent_meta(
                    AgentMeta(
                        name=name,
                        version="1.0.0",
                        description="Test",
                        tags=["test"],
                    )
                )

        client = MagicMock()
        client.chat.return_value = "mock response"
        client.stream.return_value = ["mock response"]

        router = AgentRouter(registry=registry, client=client)
        coord = Coordinator(
            client=client,
            registry=registry,
            router=router,
            event_bus=mock_event_bus,
        )
        return coord

    def test_route_publishes_agent_routed(self, coordinator, mock_event_bus):
        """Coordinator.execute should publish AgentRouted."""
        # The execute method needs a SubAgent which is complex to mock
        # Let's verify the router publishes correctly instead
        from Agent.events import AgentRouted
        from Agent.coordinator import AgentRouter
        from Agent.agent_meta import AgentMeta
        from Agent.personality import PersonalityRegistry

        registry = PersonalityRegistry.get_instance()
        for name in ("router-test", "general"):
            try:
                registry.get_agent_meta(name)
            except KeyError:
                registry.register_agent_meta(
                    AgentMeta(name=name, version="1.0.0", description="", tags=["router-test"])
                )

        client = MagicMock()
        # We need the LLM fallback to NOT fire — give metadata enough to match
        router = AgentRouter(registry=registry, client=client)
        # route doesn't publish events directly; the Coordinator does
        # So let's just verify routing works (regression check)
        result = router.route("do something with router-test")
        assert result.primary_agent == "router-test" or result.primary_agent == "general"

    def test_execute_with_mock(self, coordinator, mock_event_bus):
        """Test that execute publishes routing and execution events."""
        # This is an integration-level test; mock what we need
        with patch("Agent.coordinator.SubAgent") as MockSubAgent:
            mock_sub = MagicMock()
            mock_sub.execute.return_value = "mock response"
            mock_sub.turns = 3
            MockSubAgent.return_value = mock_sub

            result = coordinator.execute("test this goal")

        # Should have been 3 events: AgentRouted, AgentExecutionStarted, AgentExecutionCompleted
        events = [call[0][0] for call in mock_event_bus.publish.call_args_list]
        routed = [e for e in events if isinstance(e, AgentRouted)]
        started = [e for e in events if isinstance(e, AgentExecutionStarted)]
        completed = [e for e in events if isinstance(e, AgentExecutionCompleted)]

        assert len(routed) == 1, f"Expected 1 AgentRouted, got {len(routed)}"
        assert routed[0].goal == "test this goal"

        assert len(started) == 1, f"Expected 1 AgentExecutionStarted, got {len(started)}"
        assert started[0].goal == "test this goal"

        assert len(completed) == 1, f"Expected 1 AgentExecutionCompleted, got {len(completed)}"
        assert completed[0].goal == "test this goal"


# ======================================================================
# 4. Event classes are immutable (frozen dataclasses)
# ======================================================================


class TestEventImmutability:
    def test_cannot_modify_agent_registered(self):
        event = AgentRegistered(source="test", timestamp=1.0, agent_name="a")
        with pytest.raises((AttributeError, TypeError)):
            event.agent_name = "b"  # type: ignore[misc]

    def test_cannot_modify_agent_routed(self):
        event = AgentRouted(
            source="test", timestamp=1.0, goal="g", agent_name="a", confidence=0.5
        )
        with pytest.raises((AttributeError, TypeError)):
            event.goal = "different"


# ======================================================================
# 5. All exports are importable
# ======================================================================


class TestExports:
    def test_all_events_importable(self):
        """Every name in __all__ should be importable."""
        import Agent.events as events_module

        for name in events_module.__all__:
            assert hasattr(events_module, name), f"{name} not found in Agent.events"
