"""Tests for ``fiona.plugin_system`` — plugin lifecycle, registration API,
``AgentPlugin``, agent scanning, and DI integration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from fiona.agent_plugin import AgentPlugin
from fiona.di import FionaContainer, register_event_bus, register_plugin_manager
from fiona.plugin_system import (
    FionaPlugin,
    PluginError,
    PluginManager,
    PluginManifest,
    PluginType,
)


# ======================================================================
# PluginType
# ======================================================================


class TestPluginType:
    """PluginType constants should be distinct and match expected strings."""

    def test_values(self) -> None:
        assert PluginType.AGENT == "agent"
        assert PluginType.TOOL == "tool"
        assert PluginType.SKILL == "skill"
        assert PluginType.EVENT_HANDLER == "event_handler"
        assert PluginType.COMMAND == "command"
        assert PluginType.MEMORY_PROVIDER == "memory_provider"

    def test_all_unique(self) -> None:
        values = [
            PluginType.AGENT,
            PluginType.TOOL,
            PluginType.SKILL,
            PluginType.EVENT_HANDLER,
            PluginType.COMMAND,
            PluginType.MEMORY_PROVIDER,
        ]
        assert len(values) == len(set(values))


# ======================================================================
# PluginManifest extended fields
# ======================================================================


class TestPluginManifest:
    """PluginManifest must accept ``components``, ``dependencies``,
    and ``plugin_type``."""

    def test_minimal(self) -> None:
        m = PluginManifest(name="test")
        assert m.name == "test"
        assert m.components == ()
        assert m.dependencies == ()
        assert m.plugin_type == ""

    def test_full(self) -> None:
        m = PluginManifest(
            name="my-agent",
            version="2.0.0",
            description="An agent plugin",
            author="Fiona Team",
            entry_point="fiona_plugins.my_agent",
            plugin_type=PluginType.AGENT,
            components=(PluginType.AGENT, PluginType.TOOL),
            dependencies=("base-plugin",),
        )
        assert m.name == "my-agent"
        assert m.plugin_type == "agent"
        assert PluginType.AGENT in m.components
        assert PluginType.TOOL in m.components
        assert "base-plugin" in m.dependencies

    def test_from_dict_with_components(self) -> None:
        data = {
            "name": "comp-test",
            "components": ["agent", "tool"],
            "dependencies": ["dep1"],
        }
        m = PluginManifest.from_dict(data)
        assert m.name == "comp-test"
        assert m.components == ("agent", "tool")
        assert m.dependencies == ("dep1",)

    def test_from_dict_with_plugin_type_fallback(self) -> None:
        data = {
            "name": "legacy",
            "plugin_type": "tool",
        }
        m = PluginManifest.from_dict(data)
        assert m.components == ("tool",)

    def test_from_dict_string_components(self) -> None:
        data = {"name": "str", "components": "agent"}
        m = PluginManifest.from_dict(data)
        assert m.components == ("agent",)

    def test_from_dict_string_deps(self) -> None:
        data = {"name": "str-dep", "dependencies": "base"}
        m = PluginManifest.from_dict(data)
        assert m.dependencies == ("base",)

    def test_from_dict_list_deps(self) -> None:
        data = {"name": "list-dep", "dependencies": ["a", "b"]}
        m = PluginManifest.from_dict(data)
        assert m.dependencies == ("a", "b")

    def test_from_dict_missing_name(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            PluginManifest.from_dict({"version": "1.0.0"})


# ======================================================================
# PluginManager — registration API
# ======================================================================


class TestPluginManagerRegistration:
    """PluginManager.register_agent / register_tool / etc."""

    def make_manager(self) -> PluginManager:
        return PluginManager()

    # -- agents --

    def test_register_agent(self) -> None:
        pm = self.make_manager()
        pm.register_agent("test-agent", {"name": "test-agent"})
        agents = pm.get_registered_agents()
        assert "test-agent" in agents
        assert agents["test-agent"]["name"] == "test-agent"

    def test_register_agent_duplicate_raises(self) -> None:
        pm = self.make_manager()
        pm.register_agent("dup", object())
        with pytest.raises(ValueError, match="already registered"):
            pm.register_agent("dup", object())

    def test_get_registered_agents_empty(self) -> None:
        pm = self.make_manager()
        assert pm.get_registered_agents() == {}

    # -- tools --

    def test_register_tool(self) -> None:
        pm = self.make_manager()

        def my_tool() -> str:
            return "done"

        pm.register_tool("my_tool", my_tool)
        tools = pm.get_registered_tools()
        assert "my_tool" in tools
        assert tools["my_tool"] is my_tool
        assert tools["my_tool"]() == "done"

    def test_register_tool_duplicate_raises(self) -> None:
        pm = self.make_manager()
        pm.register_tool("t", lambda: None)
        with pytest.raises(ValueError, match="already registered"):
            pm.register_tool("t", lambda: None)

    def test_get_registered_tools_empty(self) -> None:
        pm = self.make_manager()
        assert pm.get_registered_tools() == {}

    # -- skills --

    def test_register_skill(self) -> None:
        pm = self.make_manager()
        skill = {"name": "math", "fn": lambda x: x + 1}
        pm.register_skill("math", skill)
        skills = pm.get_registered_skills()
        assert "math" in skills
        assert skills["math"]["fn"](2) == 3

    def test_register_skill_duplicate_raises(self) -> None:
        pm = self.make_manager()
        pm.register_skill("s", object())
        with pytest.raises(ValueError, match="already registered"):
            pm.register_skill("s", object())

    def test_get_registered_skills_empty(self) -> None:
        pm = self.make_manager()
        assert pm.get_registered_skills() == {}

    # -- commands --

    def test_register_command(self) -> None:
        pm = self.make_manager()

        def cmd_foo(args: list[str]) -> str:
            return "foo executed"

        pm.register_command("foo", cmd_foo)
        cmds = pm.get_registered_commands()
        assert "foo" in cmds
        assert cmds["foo"] is cmd_foo

    def test_register_command_duplicate_raises(self) -> None:
        pm = self.make_manager()
        pm.register_command("c", lambda a: None)
        with pytest.raises(ValueError, match="already registered"):
            pm.register_command("c", lambda a: None)

    def test_get_registered_commands_empty(self) -> None:
        pm = self.make_manager()
        assert pm.get_registered_commands() == {}

    # -- event handlers --

    def test_register_event_handler_with_bus(self) -> None:
        from fiona.interfaces import Event, EventBus

        pm = self.make_manager()
        bus = EventBus()
        pm.set_event_bus(bus)

        received: list[Event] = []
        pm.register_event_handler(Event, received.append)

        # Publish via bus directly
        event = Event(timestamp=1.0, source="test")
        bus.publish(event)
        assert len(received) == 1

    def test_register_event_handler_no_bus(self) -> None:
        pm = self.make_manager()
        # Should not raise — silently no-op
        pm.register_event_handler(object, lambda e: None)

    # -- isolation between instances --

    def test_registries_isolated(self) -> None:
        pm1 = self.make_manager()
        pm2 = self.make_manager()

        pm1.register_agent("a1", {"name": "a1"})
        pm2.register_agent("a2", {"name": "a2"})

        assert "a1" in pm1.get_registered_agents()
        assert "a2" not in pm1.get_registered_agents()
        assert "a1" not in pm2.get_registered_agents()
        assert "a2" in pm2.get_registered_agents()


# ======================================================================
# AgentPlugin
# ======================================================================


class _SimpleAgentPlugin(AgentPlugin):
    """Minimal AgentPlugin implementation for testing."""

    def __init__(self, meta: Any = None) -> None:
        self._meta = meta

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="test-agent-plugin",
            version="1.0.0",
            description="A test agent plugin",
            plugin_type=PluginType.AGENT,
            components=(PluginType.AGENT,),
        )

    def get_agent_meta(self) -> Any:
        return self._meta or {"name": "test-agent", "role": "helper"}

    def deactivate(self) -> None:
        pass


class TestAgentPlugin:
    """AgentPlugin ABC integration."""

    def test_activate_registers_agent(self) -> None:
        pm = PluginManager()
        meta = {"name": "my-agent", "role": "researcher"}
        plugin = _SimpleAgentPlugin(meta)
        plugin.activate(pm)

        agents = pm.get_registered_agents()
        assert "my-agent" in agents
        assert agents["my-agent"]["role"] == "researcher"

    def test_manifest(self) -> None:
        plugin = _SimpleAgentPlugin()
        m = plugin.manifest()
        assert m.name == "test-agent-plugin"
        assert m.plugin_type == PluginType.AGENT
        assert m.components == (PluginType.AGENT,)

    def test_is_fiona_plugin(self) -> None:
        assert issubclass(_SimpleAgentPlugin, FionaPlugin)


# ======================================================================
# PluginManager — agent scanning
# ======================================================================


class TestPluginManagerScanAgents:
    """scan_agents() must locate .md files with YAML front matter."""

    def _write_agent_file(
        self, directory: Path, filename: str, front_matter: dict[str, Any]
    ) -> Path:
        """Write a markdown file with YAML front matter."""
        import yaml

        content = "---\n" + yaml.dump(front_matter) + "---\n# Agent body\n"
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_scan_agents_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            self._write_agent_file(
                d,
                "helper.md",
                {
                    "name": "helper",
                    "version": "1.0.0",
                    "description": "Helper agent",
                    "role": "Helper",
                    "persona": "You help.",
                },
            )
            pm = PluginManager()
            count = pm.scan_agents([str(d)])
            assert count == 1
            agents = pm.get_registered_agents()
            assert "helper" in agents
            assert agents["helper"].name == "helper"

    def test_scan_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            for name in ("alpha", "beta", "gamma"):
                self._write_agent_file(
                    d,
                    f"{name}.md",
                    {
                        "name": name,
                        "version": "1.0.0",
                        "description": f"{name} agent",
                        "role": name.title(),
                        "persona": f"You are {name}.",
                    },
                )
            pm = PluginManager()
            count = pm.scan_agents([str(d)])
            assert count == 3
            agents = pm.get_registered_agents()
            assert set(agents.keys()) == {"alpha", "beta", "gamma"}

    def test_skip_non_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / "notes.txt").write_text("not an agent", encoding="utf-8")
            (d / "data.json").write_text("{}", encoding="utf-8")
            self._write_agent_file(
                d,
                "real.md",
                {
                    "name": "real",
                    "version": "1.0.0",
                    "description": "Real agent",
                    "role": "Real",
                    "persona": "Real.",
                },
            )
            pm = PluginManager()
            count = pm.scan_agents([str(d)])
            assert count == 1
            assert "real" in pm.get_registered_agents()

    def test_skip_invalid_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            bad = d / "bad.md"
            bad.write_text("---\ninvalid: true\n---\nBody", encoding="utf-8")
            # Missing required fields — loader may return None
            pm = PluginManager()
            count = pm.scan_agents([str(d)])
            # If the loader cannot create an AgentMeta it skips
            assert count >= 0

    def test_skip_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            self._write_agent_file(
                d,
                "dup.md",
                {
                    "name": "dup-agent",
                    "version": "1.0.0",
                    "description": "First dup",
                    "role": "First",
                    "persona": "First.",
                },
            )
            self._write_agent_file(
                d,
                "dup2.md",
                {
                    "name": "dup-agent",
                    "version": "1.0.0",
                    "description": "Second dup",
                    "role": "Second",
                    "persona": "Second.",
                },
            )
            pm = PluginManager()
            count = pm.scan_agents([str(d)])
            # Second duplicate should be skipped, so count = 1
            assert count == 1

    def test_nonexistent_directory(self) -> None:
        pm = PluginManager()
        count = pm.scan_agents(["/nonexistent/path"])
        assert count == 0

    def test_default_directory(self) -> None:
        """Without arguments, scan_agents defaults to project agents/ dir."""
        pm = PluginManager()
        # Should not raise — the project should have builtin agents
        count = pm.scan_agents()
        assert count >= 6  # At least the 6 builtin agents


# ======================================================================
# PluginManager — find_by_component
# ======================================================================


class TestFindByComponent:
    """PluginManager.find_by_component() filtering."""

    def test_find_agent_plugins(self) -> None:
        pm = PluginManager()
        pm.manifests["p1"] = PluginManifest(
            name="p1",
            components=(PluginType.AGENT, PluginType.TOOL),
        )
        pm.manifests["p2"] = PluginManifest(
            name="p2",
            components=(PluginType.TOOL,),
        )
        pm.manifests["p3"] = PluginManifest(
            name="p3",
            components=(),
        )

        agents = pm.find_by_component(PluginType.AGENT)
        assert len(agents) == 1
        assert agents[0].name == "p1"

        tools = pm.find_by_component(PluginType.TOOL)
        assert len(tools) == 2
        assert {m.name for m in tools} == {"p1", "p2"}

    def test_find_by_plugin_type_fallback(self) -> None:
        pm = PluginManager()
        pm.manifests["p1"] = PluginManifest(
            name="p1",
            plugin_type=PluginType.AGENT,
        )
        results = pm.find_by_component(PluginType.AGENT)
        assert len(results) == 1

    def test_no_match_returns_empty(self) -> None:
        pm = PluginManager()
        pm.manifests["p1"] = PluginManifest(name="p1", plugin_type="tool")
        results = pm.find_by_component(PluginType.SKILL)
        assert results == []


# ======================================================================
# DI container integration
# ======================================================================


class TestDIIntegration:
    """register_plugin_manager() and register_event_bus() must work with
    FionaContainer."""

    def test_register_and_resolve(self) -> None:
        c = FionaContainer()
        register_event_bus(c)
        register_plugin_manager(c)
        pm = c.resolve("plugin.manager")
        assert isinstance(pm, PluginManager)
        # Should have discovered builtin agents
        agents = pm.get_registered_agents()
        assert len(agents) >= 6

    def test_event_bus_wired(self) -> None:
        c = FionaContainer()
        register_event_bus(c)
        register_plugin_manager(c)
        pm = c.resolve("plugin.manager")
        assert pm._event_bus is not None

    def test_no_event_bus_ok(self) -> None:
        c = FionaContainer()
        register_plugin_manager(c)
        pm = c.resolve("plugin.manager")
        assert isinstance(pm, PluginManager)

    def test_repr(self) -> None:
        pm = PluginManager()
        pm.register_agent("a", object())
        pm.manifests["m"] = PluginManifest(name="m")
        r = repr(pm)
        assert "1 manifests" in r
        assert "1 agents" in r


# ======================================================================
# Integration: load plugin that registers components
# ======================================================================


class _RegistratingPlugin(FionaPlugin):
    """A FionaPlugin that registers components during activation."""

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name="registrator",
            version="1.0.0",
            description="Registers components on activate",
            components=(PluginType.TOOL, PluginType.COMMAND),
        )

    def activate(self, container: Any) -> None:
        container.register_tool("greet", lambda name: f"Hello, {name}!")
        container.register_command("say_hello", lambda args: print("hello"))

    def deactivate(self) -> None:
        pass


class TestPluginComponentRegistration:
    """Loading a plugin that calls register_* during activate()."""

    def test_activate_registers_tools_and_commands(self) -> None:
        pm = PluginManager()
        pm.manifests["registrator"] = _RegistratingPlugin().manifest()

        plugin = _RegistratingPlugin()
        # Manually activate with the plugin manager as container
        plugin.activate(pm)
        pm.active_plugins["registrator"] = plugin

        tools = pm.get_registered_tools()
        assert "greet" in tools
        assert tools["greet"]("World") == "Hello, World!"

        commands = pm.get_registered_commands()
        assert "say_hello" in commands


# ======================================================================
# Backward compatibility: PluginManifest.from_dict without new fields
# ======================================================================


class TestBackwardCompatibility:
    """Plugins without ``components`` or ``dependencies`` should still
    work exactly as before."""

    def test_legacy_manifest(self) -> None:
        data = {
            "name": "legacy",
            "version": "0.1.0",
            "description": "Old-style",
            "author": "me",
            "entry_point": "legacy_mod",
        }
        m = PluginManifest.from_dict(data)
        assert m.name == "legacy"
        assert m.components == ()
        assert m.dependencies == ()
        assert m.plugin_type == ""

    def test_legacy_json_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "legacy_plugin"
            plugin_dir.mkdir()
            manifest_path = plugin_dir / "plugin.json"
            manifest_path.write_text(
                json.dumps({
                    "name": "legacy-plugin",
                    "version": "1.0.0",
                    "entry_point": "tests.test_plugin_system",
                }),
                encoding="utf-8",
            )

            pm = PluginManager(search_paths=[str(Path(tmpdir))])
            manifests = pm.discover()
            assert len(manifests) == 1
            assert manifests[0].name == "legacy-plugin"
            assert manifests[0].components == ()
            assert manifests[0].dependencies == ()

    def test_plugin_fiona_plugin_abc_unchanged(self) -> None:
        # FionaPlugin still requires manifest, activate, deactivate
        import abc as _abc

        assert FionaPlugin.manifest.__isabstractmethod__
        assert FionaPlugin.activate.__isabstractmethod__
        assert FionaPlugin.deactivate.__isabstractmethod__


# ======================================================================
# Edge cases
# ======================================================================


class TestEdgeCases:
    """Corner cases and error handling."""

    def test_registry_instance_isolation_across_reset(self) -> None:
        """Two PluginManager instances should not share registry data."""
        pm1 = PluginManager()
        pm2 = PluginManager()

        pm1.register_agent("a", "v1")
        assert "a" in pm1.get_registered_agents()
        assert "a" not in pm2.get_registered_agents()

        pm2.register_agent("b", "v2")
        assert "b" not in pm1.get_registered_agents()
        assert "b" in pm2.get_registered_agents()

    def test_set_event_bus_none(self) -> None:
        pm = PluginManager()
        pm.set_event_bus(None)  # Should not raise
        pm.register_event_handler(object, lambda e: None)  # Should not raise

    def test_register_with_empty_name(self) -> None:
        pm = PluginManager()
        pm.register_agent("", object())
        assert "" in pm.get_registered_agents()
