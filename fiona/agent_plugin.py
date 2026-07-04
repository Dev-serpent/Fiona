"""Agent plugin support for the Fiona plugin system.

Extends ``FionaPlugin`` with agent-specific lifecycle hooks so that
plugins can declaratively register agents via ``AgentMeta``.

Usage::

    from fiona.agent_plugin import AgentPlugin
    from fiona.plugin_system import PluginManifest

    class MyAgentPlugin(AgentPlugin):

        def manifest(self) -> PluginManifest:
            return PluginManifest(
                name="my-agent",
                version="1.0.0",
                description="Registers a custom agent",
                plugin_type="agent",
                components=("agent",),
            )

        def get_agent_meta(self) -> "AgentMeta":
            from Agent.agent_meta import AgentMeta
            return AgentMeta(
                name="my-agent",
                role="Custom Agent",
                persona="You are a custom agent.",
                description="A custom agent registered via plugin",
                version="1.0.0",
            )

        def deactivate(self) -> None:
            pass  # nothing to clean up
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from fiona.plugin_system import FionaPlugin


class AgentPlugin(FionaPlugin):
    """A ``FionaPlugin`` that registers an agent with the system.

    Subclasses must implement :meth:`get_agent_meta` which provides
    the ``AgentMeta`` describing the agent to register.

    The ``activate()`` implementation calls ``container.register_agent()``
    with the result of ``get_agent_meta()``.  Subclasses may override
    ``activate()`` if they need additional registration steps.
    """

    @abstractmethod
    def get_agent_meta(self) -> Any:
        """Return the ``AgentMeta`` instance for this plugin's agent.

        Returns:
            An ``AgentMeta`` object (from ``Agent.agent_meta``) or any
            duck-type compatible object with ``name``, ``role``,
            ``persona``, and ``description`` attributes.
        """

    def activate(self, container: Any) -> None:
        """Register the agent meta with the plugin manager / container.

        Args:
            container: The ``PluginManager`` (or compatible object) that
                exposes ``register_agent()``.
        """
        meta = self.get_agent_meta()
        # Support both AgentMeta objects (with .name) and plain dicts
        name = meta.name if hasattr(meta, "name") else meta["name"]
        container.register_agent(name, meta)


__all__ = ["AgentPlugin"]
