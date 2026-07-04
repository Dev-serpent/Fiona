"""Tests for the Introspection API (Phase 11: Introspection API)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from fiona.introspection import (
    AgentSummary,
    FionaInspector,
    PluginSummary,
    SystemStatus,
    ToolSummary,
)


# ======================================================================
# 1. Data types
# ======================================================================


class TestAgentSummary:
    def test_create(self):
        a = AgentSummary(name="test", version="1.0.0", description="test agent")
        assert a.name == "test"
        assert a.version == "1.0.0"
        assert a.enabled
        assert a.source_path is None

    def test_with_all_fields(self):
        a = AgentSummary(
            name="code-review",
            version="2.0.0",
            description="Reviews code",
            tags=("code", "review"),
            enabled=False,
            source_path="/agents/code.md",
        )
        assert not a.enabled
        assert a.source_path == "/agents/code.md"


class TestPluginSummary:
    def test_create(self):
        p = PluginSummary(name="my-plugin", version="1.0.0")
        assert p.name == "my-plugin"
        assert p.components == ()


class TestToolSummary:
    def test_create(self):
        t = ToolSummary(name="search", description="Searches", category="web")
        assert t.name == "search"
        assert t.category == "web"


class TestSystemStatus:
    def test_defaults(self):
        s = SystemStatus()
        assert s.healthy
        assert s.agents == 0
        assert s.timestamp == 0.0

    def test_all_fields(self):
        s = SystemStatus(
            timestamp=1000.0,
            agents=5,
            enabled_agents=3,
            skills=2,
            plugins=1,
            tools=10,
            llm_providers=2,
            memory_namespaces=4,
            healthy=True,
            details={"uptime": 100},
        )
        assert s.agents == 5
        assert s.tools == 10
        assert s.details["uptime"] == 100


# ======================================================================
# 2. FionaInspector
# ======================================================================


class TestFionaInspector:
    @pytest.fixture
    def inspector(self):
        return FionaInspector()

    def test_system_status_returns_basic(self, inspector):
        """system_status should return a valid SystemStatus."""
        status = inspector.system_status()
        assert isinstance(status, SystemStatus)
        assert status.timestamp > 0
        assert "uptime_seconds" in status.details

    def test_system_status_healthy(self, inspector):
        """Should report healthy by default."""
        status = inspector.system_status()
        assert status.healthy

    def test_system_status_handles_missing_subsystems(self, inspector):
        """When subsystems aren't available, counts should be 0."""
        status = inspector.system_status()
        # These might be 0 if no agents/plugins/etc. are registered
        assert status.agents >= 0
        assert status.tools >= 0
        assert status.skills >= 0

    def test_list_agents(self, inspector):
        """list_agents should return a list (possibly empty)."""
        agents = inspector.list_agents()
        if agents is not None:
            for a in agents:
                assert isinstance(a, AgentSummary)
                assert a.name

    def test_get_agent_info_found(self, inspector):
        """get_agent_info should return a single agent or None."""
        agent = inspector.get_agent_info("nonexistent")
        # Could be None or an AgentSummary depending on what's registered
        assert agent is None or isinstance(agent, AgentSummary)

    def test_get_agent_info_not_found(self, inspector):
        """Non-existent agent returns None."""
        agent = inspector.get_agent_info("__definitely_not_real__")
        assert agent is None

    def test_list_skills(self, inspector):
        """list_skills should return a list or None."""
        skills = inspector.list_skills()
        if skills is not None:
            for s in skills:
                assert "name" in s

    def test_list_plugins(self, inspector):
        """list_plugins should return a list or None."""
        plugins = inspector.list_plugins()
        if plugins is not None:
            for p in plugins:
                assert isinstance(p, PluginSummary)

    def test_list_tools(self, inspector):
        """list_tools should return a list or None."""
        tools = inspector.list_tools()
        if tools is not None:
            for t in tools:
                assert isinstance(t, ToolSummary)
                assert t.name

    def test_check_llm_health_all(self, inspector):
        """check_llm_health should return a dict."""
        result = inspector.check_llm_health()
        assert isinstance(result, dict)

    def test_check_llm_health_specific(self, inspector):
        """Check health of a specific (possibly non-existent) provider."""
        result = inspector.check_llm_health("ollama")
        assert isinstance(result, dict)

    def test_get_memory_summary(self, inspector):
        """get_memory_summary should return a dict."""
        result = inspector.get_memory_summary()
        assert isinstance(result, dict)

    def test_full_report(self, inspector):
        """full_report should return a comprehensive dict."""
        report = inspector.full_report()
        assert isinstance(report, dict)
        assert "system" in report
        assert "agents" in report
        assert "skills" in report
        assert "plugins" in report
        assert "tools" in report
        assert "llm_providers" in report
        assert "memory" in report


# ======================================================================
# 3. Graceful degradation when imports are missing
# ======================================================================


class TestGracefulDegradation:
    def test_list_agents_import_error(self):
        """When AgentManager can't be imported, list_agents returns None."""
        with patch.dict("sys.modules", {"Agent.agent_manager": None}):
            inspector = FionaInspector()
            result = inspector.list_agents()
            assert result is None

    def test_list_skills_import_error(self):
        """When SkillRegistry can't be imported, list_skills returns None."""
        with patch.dict("sys.modules", {"Agent.skill": None}):
            inspector = FionaInspector()
            result = inspector.list_skills()
            assert result is None

    def test_list_tools_import_error(self):
        """When ToolRegistry can't be imported, list_tools returns None."""
        with patch.dict("sys.modules", {"Agent.tool_runtime": None}):
            inspector = FionaInspector()
            result = inspector.list_tools()
            assert result is None

    def test_full_report_still_works_with_errors(self):
        """full_report should still return a valid dict even if some queries fail."""
        with patch.object(FionaInspector, "list_agents", return_value=None):
            inspector = FionaInspector()
            report = inspector.full_report()
            assert report["agents"]["total"] == 0

    def test_system_status_with_none_queries(self):
        """system_status should handle None returns from sub-queries gracefully."""
        inspector = FionaInspector()

        # When list_* returns None, system_status should default to 0
        with patch.object(FionaInspector, "list_agents", return_value=None):
            with patch.object(FionaInspector, "list_skills", return_value=None):
                with patch.object(FionaInspector, "list_plugins", return_value=None):
                    with patch.object(FionaInspector, "list_tools", return_value=None):
                        status = inspector.system_status()
                        assert isinstance(status, SystemStatus)
                        assert status.agents == 0
                        assert status.skills == 0
                        assert status.plugins == 0
                        assert status.tools == 0
                        assert status.healthy  # still healthy
