"""Agent lifecycle events for the Fiona event bus.

All event classes extend ``fiona.interfaces.Event`` so they can be
published on the existing ``EventBus``.

Usage::

    from fiona.interfaces import EventBus
    from Agent.events import AgentRegistered, AgentRouted

    bus = EventBus()
    bus.publish(AgentRegistered(
        source="agent_manager", agent_name="my-agent", version="1.0.0"
    ))
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fiona.interfaces import Event


# ---------------------------------------------------------------------------
# Agent lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentLifecycleEvent(Event):
    """Base for all agent lifecycle events.

    Attributes:
        agent_name: Name of the affected agent.
    """

    agent_name: str


@dataclass(frozen=True)
class AgentRegistered(AgentLifecycleEvent):
    """Published when an agent is registered in the system.

    Attributes:
        version: Agent version string.
        source_path: Filesystem path to the agent definition, or ``None``.
        plugin_name: Name of the plugin that registered this agent, or ``None``.
    """

    version: str = ""
    source_path: str | None = None
    plugin_name: str | None = None


@dataclass(frozen=True)
class AgentUnregistered(AgentLifecycleEvent):
    """Published when an agent is removed from the system."""


@dataclass(frozen=True)
class AgentEnabled(AgentLifecycleEvent):
    """Published when an agent is enabled for routing."""


@dataclass(frozen=True)
class AgentDisabled(AgentLifecycleEvent):
    """Published when an agent is disabled (excluded from routing)."""


@dataclass(frozen=True)
class AgentReloaded(AgentLifecycleEvent):
    """Published when an agent's definition is reloaded from disk.

    Attributes:
        version: New version string after reload.
    """

    version: str = ""


# ---------------------------------------------------------------------------
# Routing / orchestration events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentRouted(Event):
    """Published when a goal is routed to an agent.

    Attributes:
        goal: The original user goal.
        agent_name: The chosen agent name.
        confidence: Match confidence (0.0 – 1.0).
        match_method: How the match was determined (tags, capabilities, llm).
        alternatives: Number of alternative candidates considered.
    """

    goal: str
    agent_name: str
    confidence: float = 0.0
    match_method: str = "none"
    alternatives: int = 0


@dataclass(frozen=True)
class AgentExecutionStarted(Event):
    """Published when agent execution begins.

    Attributes:
        goal: The goal being executed.
        agent_name: The executing agent.
        max_turns: Maximum allowed ReAct turns.
    """

    goal: str
    agent_name: str
    max_turns: int = 10


@dataclass(frozen=True)
class AgentExecutionCompleted(Event):
    """Published when agent execution finishes.

    Attributes:
        goal: The original goal.
        agent_name: The agent used.
        success: Whether execution succeeded.
        duration_ms: Wall-clock time in milliseconds.
        turns: Number of ReAct turns taken.
        error: Error message if execution failed, or ``None``.
    """

    goal: str
    agent_name: str
    success: bool = True
    duration_ms: float = 0.0
    turns: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Plugin lifecycle events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginLifecycleEvent(Event):
    """Base for plugin lifecycle events.

    Attributes:
        plugin_name: Name of the affected plugin.
    """

    plugin_name: str


@dataclass(frozen=True)
class PluginLoaded(PluginLifecycleEvent):
    """Published when a plugin is loaded and activated.

    Attributes:
        version: Plugin version string.
        components: Tuple of component types the plugin provides.
    """

    version: str = ""
    components: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginUnloaded(PluginLifecycleEvent):
    """Published when a plugin is unloaded."""


__all__ = [
    "AgentDisabled",
    "AgentEnabled",
    "AgentExecutionCompleted",
    "AgentExecutionStarted",
    "AgentLifecycleEvent",
    "AgentRegistered",
    "AgentReloaded",
    "AgentRouted",
    "AgentUnregistered",
    "PluginLifecycleEvent",
    "PluginLoaded",
    "PluginUnloaded",
]
