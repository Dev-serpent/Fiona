"""Tests for ``Agent.agent_manager`` — ``AgentManager`` lifecycle."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from Agent.agent_manager import AgentInfo, AgentManager
from Agent.agent_meta import AgentMeta
from Agent.personality import PersonalityRegistry


# ======================================================================
# Helpers
# ======================================================================

_ENGINEER_META = AgentMeta(
    name="engineer",
    version="1.0.0",
    description="Software engineer",
    tags=("engineer", "developer"),
    capabilities=("code-generation", "debugging"),
)

_GENERAL_META = AgentMeta(
    name="general",
    version="1.0.0",
    description="General-purpose assistant",
    tags=(),
    capabilities=(),
)

_CUSTOM_META = AgentMeta(
    name="custom-agent",
    version="2.0.0",
    description="A custom agent",
    tags=("custom",),
    capabilities=("special",),
)


# ======================================================================
# AgentInfo
# ======================================================================


class TestAgentInfo:
    """AgentInfo is a frozen dataclass with public fields."""

    def test_create(self) -> None:
        info = AgentInfo(
            name="test",
            version="1.0.0",
            description="Test agent",
            tags=("a", "b"),
            capabilities=("c",),
            enabled=True,
            source_path="/path/to/agent.md",
            plugin_name="my-plugin",
        )
        assert info.name == "test"
        assert info.enabled
        assert info.plugin_name == "my-plugin"

    def test_defaults(self) -> None:
        info = AgentInfo(name="test", version="1.0", description="d")
        assert info.enabled
        assert info.source_path is None
        assert info.plugin_name is None


# ======================================================================
# AgentManager — registration
# ======================================================================


class TestAgentManagerRegister:
    """AgentManager.register() must add to PersonalityRegistry + PluginManager."""

    def make_manager(
        self,
        plugin_manager: object = None,
    ) -> AgentManager:
        return AgentManager(
            registry=PersonalityRegistry.get_instance(),
            plugin_manager=plugin_manager,
            agent_dirs=[],
        )

    def test_register_adds_to_registry(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)

        info = mgr.get("custom-agent")
        assert info is not None
        assert info.name == "custom-agent"
        assert info.version == "2.0.0"

    def test_register_with_plugin_manager(self) -> None:
        pm = MagicMock()
        mgr = self.make_manager(plugin_manager=pm)
        mgr.register("custom-agent", _CUSTOM_META, plugin_name="test-plugin")

        # PluginManager's register_agent should have been called
        pm.register_agent.assert_called_once_with("custom-agent", _CUSTOM_META)

    def test_register_duplicate_overwrites(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        # Re-register same name — should overwrite without error
        mgr.register("custom-agent", _CUSTOM_META)
        assert mgr.get("custom-agent") is not None

    def test_register_empty_name_raises(self) -> None:
        mgr = self.make_manager()
        with pytest.raises(ValueError, match="non-empty"):
            mgr.register("", _CUSTOM_META)

    def test_register_enabled_by_default(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        assert mgr.is_enabled("custom-agent")


# ======================================================================
# AgentManager — unregister
# ======================================================================


class TestAgentManagerUnregister:
    """AgentManager.unregister() must remove from all registries."""

    def make_manager(self) -> AgentManager:
        return AgentManager(
            registry=PersonalityRegistry.get_instance(),
            agent_dirs=[],
        )

    def test_unregister_removes_agent(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        assert mgr.get("custom-agent") is not None

        result = mgr.unregister("custom-agent")
        assert result
        assert mgr.get("custom-agent") is None

    def test_unregister_nonexistent_returns_false(self) -> None:
        mgr = self.make_manager()
        result = mgr.unregister("nonexistent")
        assert not result

    def test_unregister_from_plugin_manager(self) -> None:
        pm = MagicMock()
        pm.get_registered_agents.return_value = {"custom-agent": _CUSTOM_META}
        mgr = self.make_manager()
        mgr._plugin_manager = pm
        mgr.register("custom-agent", _CUSTOM_META)

        result = mgr.unregister("custom-agent")
        assert result
        # PluginManager dict should have been popped
        pm.get_registered_agents.assert_called()

    def test_unregister_clears_enabled_state(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        mgr.disable("custom-agent")
        mgr.unregister("custom-agent")
        # After unregister, is_enabled should return True (default)
        assert mgr.is_enabled("custom-agent")


# ======================================================================
# AgentManager — enable / disable
# ======================================================================


class TestAgentManagerEnableDisable:
    """AgentManager.enable() / disable() toggle participation in routing."""

    def make_manager(self) -> AgentManager:
        return AgentManager(
            registry=PersonalityRegistry.get_instance(),
            agent_dirs=[],
        )

    def test_disable_agent(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        assert mgr.is_enabled("custom-agent")

        mgr.disable("custom-agent")
        assert not mgr.is_enabled("custom-agent")

    def test_enable_agent(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        mgr.disable("custom-agent")
        mgr.enable("custom-agent")
        assert mgr.is_enabled("custom-agent")

    def test_enable_nonexistent_returns_false(self) -> None:
        mgr = self.make_manager()
        result = mgr.enable("nonexistent")
        assert not result

    def test_disable_nonexistent_returns_false(self) -> None:
        mgr = self.make_manager()
        result = mgr.disable("nonexistent")
        assert not result

    def test_list_respects_enabled(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        mgr.disable("custom-agent")

        all_infos = mgr.list()
        enabled_infos = mgr.get_enabled()
        disabled_infos = mgr.get_disabled()

        # custom-agent should be in disabled list
        disabled_names = {i.name for i in disabled_infos}
        assert "custom-agent" in disabled_names

        # custom-agent should not be in enabled list
        enabled_names = {i.name for i in enabled_infos}
        assert "custom-agent" not in enabled_names

    def test_enabled_agent_names_property(self) -> None:
        mgr = self.make_manager()
        meta_a = AgentMeta(name="agent-a", version="1.0", description="A")
        meta_b = AgentMeta(name="agent-b", version="1.0", description="B")
        mgr.register("agent-a", meta_a)
        mgr.register("agent-b", meta_b)
        mgr.disable("agent-b")

        enabled = mgr.enabled_agent_names
        assert "agent-a" in enabled
        assert "agent-b" not in enabled


# ======================================================================
# AgentManager — queries
# ======================================================================


class TestAgentManagerQueries:
    """AgentManager.list(), get() must return AgentInfo objects."""

    def make_manager(self) -> AgentManager:
        return AgentManager(
            registry=PersonalityRegistry.get_instance(),
            agent_dirs=[],
        )

    def test_list_contains_registered_agents(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        infos = mgr.list()
        names = {i.name for i in infos}
        assert "custom-agent" in names

    def test_list_is_sorted(self) -> None:
        mgr = self.make_manager()
        mgr.register("z-agent", _CUSTOM_META)
        mgr.register("a-agent", _CUSTOM_META)
        infos = mgr.list()
        names = [i.name for i in infos if "agent" in i.name]
        assert names == sorted(names)

    def test_get_existing(self) -> None:
        mgr = self.make_manager()
        mgr.register("custom-agent", _CUSTOM_META)
        info = mgr.get("custom-agent")
        assert info is not None
        assert info.description == "A custom agent"
        assert info.capabilities == ("special",)

    def test_get_nonexistent_returns_none(self) -> None:
        mgr = self.make_manager()
        info = mgr.get("nonexistent")
        assert info is None


# ======================================================================
# AgentManager — reload from disk
# ======================================================================


class TestAgentManagerReload:
    """AgentManager.reload() and reload_all() must re-scan agent dirs."""

    def _write_agent_file(
        self, directory: Path, name: str, overrides: dict | None = None
    ) -> Path:
        import yaml

        data = {
            "name": name,
            "version": "1.0.0",
            "description": f"{name} agent",
        }
        if overrides:
            data.update(overrides)
        content = "---\n" + yaml.dump(data) + "---\nSystem prompt.\n"
        path = directory / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_reload_single_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            self._write_agent_file(d, "reload-me")
            mgr = AgentManager(agent_dirs=[str(d)])

            # First load via reload_all
            mgr.reload_all()
            assert mgr.get("reload-me") is not None

            # Update the file
            self._write_agent_file(d, "reload-me", {"version": "2.0.0"})

            # Reload single agent
            result = mgr.reload("reload-me")
            assert result
            info = mgr.get("reload-me")
            assert info is not None
            assert info.version == "2.0.0"

    def test_reload_nonexistent_returns_false(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        result = mgr.reload("nonexistent")
        assert not result

    def test_reload_all_discovers_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            self._write_agent_file(d, "alpha")
            self._write_agent_file(d, "beta")

            mgr = AgentManager(agent_dirs=[str(d)])
            count = mgr.reload_all()
            assert count == 2
            assert mgr.get("alpha") is not None
            assert mgr.get("beta") is not None

    def test_reload_all_preserves_disabled_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            self._write_agent_file(d, "toggle-agent")

            mgr = AgentManager(agent_dirs=[str(d)])
            mgr.reload_all()
            mgr.disable("toggle-agent")

            # Reload should preserve disabled state
            mgr.reload_all()
            assert not mgr.is_enabled("toggle-agent")


# ======================================================================
# AgentManager — hot-reload
# ======================================================================


class TestAgentManagerHotReload:
    """AgentManager.start_hot_reload() / stop_hot_reload()."""

    def test_start_and_stop(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        mgr.start_hot_reload(poll_interval=0.5)
        assert mgr._hot_reload_thread is not None
        assert mgr._hot_reload_thread.is_alive()

        mgr.stop_hot_reload()
        assert not mgr._hot_reload_thread.is_alive()

    def test_restart_hot_reload(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        mgr.start_hot_reload(poll_interval=0.3)
        mgr.stop_hot_reload()
        mgr.start_hot_reload(poll_interval=0.3)
        mgr.stop_hot_reload()
        # Should not crash

    def test_start_twice_logs_warning(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        mgr.start_hot_reload(poll_interval=0.3)
        # Second start should log warning but not raise
        mgr.start_hot_reload(poll_interval=0.3)
        mgr.stop_hot_reload()


# ======================================================================
# AgentManager — DI integration
# ======================================================================


class TestAgentManagerDIIntegration:
    """AgentManager should work with FionaContainer."""

    def test_di_factory(self) -> None:
        from fiona.di import FionaContainer, register_agent_manager

        c = FionaContainer()
        register_agent_manager(c)
        mgr = c.resolve("agent.manager")
        assert isinstance(mgr, AgentManager)

    def test_di_with_plugin_manager(self) -> None:
        from fiona.di import (
            FionaContainer,
            register_agent_manager,
            register_plugin_manager,
        )

        c = FionaContainer()
        register_plugin_manager(c, scan_agents=False)
        register_agent_manager(c)
        mgr = c.resolve("agent.manager")
        assert mgr._plugin_manager is not None


# ======================================================================
# Edge cases
# ======================================================================


class TestAgentManagerEdgeCases:
    """Edge cases for AgentManager."""

    def test_default_agent_dirs(self) -> None:
        """Without explicit agent_dirs, the project agents/ dir is used."""
        mgr = AgentManager()
        assert len(mgr._agent_dirs) > 0
        assert "agents" in mgr._agent_dirs[0]

    def test_empty_list(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        infos = mgr.list()
        assert isinstance(infos, list)
        # Should not crash even with no custom agents
        assert len(infos) >= 6  # Builtins

    def test_unregister_builtin(self) -> None:
        """Built-in agents can be unregistered."""
        mgr = AgentManager(agent_dirs=[])
        result = mgr.unregister("general")
        assert result
        assert mgr.get("general") is None

    def test_disable_builtin(self) -> None:
        mgr = AgentManager(agent_dirs=[])
        result = mgr.disable("planner")
        assert result
        assert not mgr.is_enabled("planner")

    def test_repr_agent_info(self) -> None:
        info = AgentInfo(name="a", version="1.0", description="d")
        r = repr(info)
        assert isinstance(r, str)
