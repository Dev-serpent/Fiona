"""Introspection API for Fiona.

Provides programmatic access to the runtime state of the Fiona system:
agents, skills, plugins, tools, LLM providers, memory namespaces, and
system health.

This is the single source of truth for all introspection queries.
Both the CLI and any web API should delegate to this module.

Usage::

    from fiona.introspection import FionaInspector

    inspector = FionaInspector()
    status = inspector.system_status()
    agents = inspector.list_agents()
"""

from __future__ import annotations

import importlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ======================================================================
# 1. Data types for introspection results
# ======================================================================


@dataclass
class SystemStatus:
    """Overall system health and component counts.

    Attributes:
        timestamp: Unix timestamp of the status snapshot.
        agents: Number of registered agents.
        enabled_agents: Number of enabled agents.
        skills: Number of registered skills.
        plugins: Number of discovered plugins.
        tools: Number of registered tools.
        llm_providers: Number of registered LLM providers.
        memory_namespaces: Number of memory namespaces.
        healthy: Whether the system is considered healthy.
        details: Dictionary with additional component-level details.
    """

    timestamp: float = 0.0
    agents: int = 0
    enabled_agents: int = 0
    skills: int = 0
    plugins: int = 0
    tools: int = 0
    llm_providers: int = 0
    memory_namespaces: int = 0
    healthy: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSummary:
    """Public summary of a single agent.

    Attributes:
        name: Agent identifier.
        version: Semantic version.
        description: Human-readable description.
        tags: Searchable tags.
        enabled: Whether this agent participates in routing.
        source_path: Filesystem path, if known.
    """

    name: str
    version: str
    description: str = ""
    tags: tuple[str, ...] = ()
    enabled: bool = True
    source_path: str | None = None


@dataclass
class PluginSummary:
    """Public summary of a single plugin.

    Attributes:
        name: Plugin identifier.
        version: Semantic version.
        description: Short summary.
        components: Tuple of component types.
    """

    name: str
    version: str
    description: str = ""
    components: tuple[str, ...] = ()


@dataclass
class ToolSummary:
    """Public summary of a single tool.

    Attributes:
        name: Tool name for invocation.
        description: What the tool does.
        category: Domain category.
        source: Origin of the tool registration.
    """

    name: str
    description: str = ""
    category: str = ""
    source: str = ""


# ======================================================================
# 2. FionaInspector — the introspection facade
# ======================================================================


class FionaInspector:
    """Facade that aggregates runtime state from all Fiona subsystems.

    Each ``list_*`` method returns ``None`` if the corresponding subsystem
    is not available (not imported, not registered, etc.), making it safe
    to call even when components are missing.
    """

    def __init__(self) -> None:
        self._start_time = time.time()

    # ------------------------------------------------------------------
    # System-level queries
    # ------------------------------------------------------------------

    def system_status(self) -> SystemStatus:
        """Return a snapshot of overall system health."""
        agents = self.list_agents() or []
        enabled = [a for a in agents if a.enabled]
        skills = self.list_skills()
        plugins = self.list_plugins()
        tools = self.list_tools()
        providers = self._get_provider_names()
        memory = self._get_memory_namespaces()

        details: dict[str, Any] = {
            "uptime_seconds": time.time() - self._start_time,
        }

        # Try to include Coordinator routing stats
        try:
            from Agent.coordinator import Coordinator

            details["routing_available"] = True
        except (ImportError, Exception):
            details["routing_available"] = False

        return SystemStatus(
            timestamp=time.time(),
            agents=len(agents),
            enabled_agents=len(enabled),
            skills=len(skills or []),
            plugins=len(plugins or []),
            tools=len(tools or []),
            llm_providers=len(providers or []),
            memory_namespaces=len(memory or []),
            healthy=True,
            details=details,
        )

    # ------------------------------------------------------------------
    # Agent queries
    # ------------------------------------------------------------------

    def list_agents(self) -> list[AgentSummary] | None:
        """Return summaries of all registered agents."""
        try:
            from Agent.agent_manager import AgentManager

            # Try container-registered manager first, then create a default
            try:
                from fiona.di import FionaContainer

                container = FionaContainer()
                mgr = container.resolve("agent.manager")
            except Exception:
                mgr = AgentManager()

            agents = mgr.list()
            return [
                AgentSummary(
                    name=a.name,
                    version=a.version,
                    description=a.description,
                    tags=tuple(a.tags or []),
                    enabled=a.enabled,
                    source_path=a.source_path,
                )
                for a in agents
            ]
        except Exception as exc:
            logger.debug("list_agents failed: %s", exc)
            return None

    def get_agent_info(self, name: str) -> AgentSummary | None:
        """Return summary for a single agent by name."""
        agents = self.list_agents()
        if agents is None:
            return None
        for a in agents:
            if a.name == name:
                return a
        return None

    # ------------------------------------------------------------------
    # Skill queries
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict[str, Any]] | None:
        """Return summaries of all registered skills."""
        try:
            from Agent.skill import SkillRegistry

            registry = SkillRegistry()
            return [
                {
                    "name": s.name,
                    "version": s.version,
                    "description": s.description,
                    "tools": s.tools,
                    "tags": s.tags,
                }
                for s in registry.list()
            ]
        except Exception as exc:
            logger.debug("list_skills failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Plugin queries
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[PluginSummary] | None:
        """Return summaries of all discovered plugins."""
        try:
            from fiona.plugin_system import PluginManager

            pm = PluginManager()
            manifests = pm.list_manifests()
            return [
                PluginSummary(
                    name=m.name,
                    version=m.version,
                    description=m.description,
                    components=m.components,
                )
                for m in manifests
            ]
        except Exception as exc:
            logger.debug("list_plugins failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Tool queries
    # ------------------------------------------------------------------

    def list_tools(self) -> list[ToolSummary] | None:
        """Return summaries of all registered tools."""
        try:
            from Agent.tool_runtime import ToolRegistry

            registry = ToolRegistry.create_default()
            specs = registry.list()
            return [
                ToolSummary(
                    name=s.name,
                    description=s.description,
                    category=s.category.value if hasattr(s.category, "value") else str(s.category),
                    source="scitools",
                )
                for s in specs
            ]
        except Exception as exc:
            logger.debug("list_tools failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # LLM provider queries
    # ------------------------------------------------------------------

    def _get_provider_names(self) -> list[str]:
        """Return names of registered LLM providers."""
        try:
            from Agent.llm import LLMManager

            mgr = LLMManager()
            return mgr.list_providers()
        except Exception:
            return []

    def check_llm_health(self, provider_name: str | None = None) -> dict[str, Any]:
        """Check health of LLM providers.

        Args:
            provider_name: Specific provider to check, or all if ``None``.

        Returns:
            Dict mapping provider name → health status.
        """
        try:
            from Agent.llm import LLMManager

            mgr = LLMManager()
            result: dict[str, Any] = {}
            if provider_name:
                provider = mgr.get_provider(provider_name)
                if provider is None:
                    return {provider_name: {"error": f"Unknown provider: {provider_name}"}}
                try:
                    result[provider_name] = {"healthy": provider.health()}
                except Exception as e:
                    result[provider_name] = {"healthy": False, "error": str(e)}
            else:
                for name in mgr.list_providers():
                    provider = mgr.get_provider(name)
                    if provider is not None:
                        try:
                            result[name] = {"healthy": provider.health()}
                        except Exception as e:
                            result[name] = {"healthy": False, "error": str(e)}
            return result
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Memory queries
    # ------------------------------------------------------------------

    def _get_memory_namespaces(self) -> list[str]:
        """Return names of active memory namespaces."""
        try:
            from Agent.memory import MemoryManager

            mgr = MemoryManager()
            return mgr.list_namespaces()
        except Exception:
            return []

    def get_memory_summary(self) -> dict[str, Any]:
        """Return a summary of memory usage per namespace."""
        try:
            from Agent.memory import MemoryManager

            mgr = MemoryManager()
            return {
                "namespaces": mgr.list_namespaces(),
                "counts": mgr.get_summary(),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # System-wide query
    # ------------------------------------------------------------------

    def full_report(self) -> dict[str, Any]:
        """Return a comprehensive report of the entire system.

        This is a convenience method that aggregates all introspection
        data into a single dictionary, suitable for JSON serialisation.
        """
        status = self.system_status()
        agents = self.list_agents()
        skills = self.list_skills()
        plugins = self.list_plugins()
        tools = self.list_tools()
        providers = self._get_provider_names()
        memory = self._get_memory_namespaces()

        return {
            "system": {
                "timestamp": status.timestamp,
                "uptime_seconds": status.details.get("uptime_seconds", 0),
                "healthy": status.healthy,
            },
            "agents": {
                "total": status.agents,
                "enabled": status.enabled_agents,
                "list": [
                    {"name": a.name, "version": a.version, "tags": list(a.tags), "enabled": a.enabled}
                    for a in (agents or [])
                ],
            },
            "skills": {
                "total": status.skills,
                "list": skills or [],
            },
            "plugins": {
                "total": status.plugins,
                "list": [
                    {"name": p.name, "version": p.version, "components": list(p.components)}
                    for p in (plugins or [])
                ],
            },
            "tools": {
                "total": status.tools,
                "list": [
                    {"name": t.name, "category": t.category}
                    for t in (tools or [])
                ],
            },
            "llm_providers": {
                "total": status.llm_providers,
                "list": providers,
            },
            "memory": {
                "namespaces": memory,
            },
        }


__all__ = [
    "AgentSummary",
    "FionaInspector",
    "PluginSummary",
    "SystemStatus",
    "ToolSummary",
]
