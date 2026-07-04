"""Agent Manager — unified lifecycle management for Fiona agents.

Provides:
- ``AgentManager``: A facade over ``PersonalityRegistry`` and
  ``PluginManager`` that offers a single API for agent lifecycle
  (register, unregister, reload, list, enable/disable).
- Hot-reload support (polling-based background thread).
- Bridge between the two parallel registration systems.

Usage::

    manager = AgentManager(registry, plugin_manager, agent_dirs=["agents"])
    manager.register(name="my-agent", meta=my_meta)
    agents = manager.list()
    manager.reload_all()
    manager.start_hot_reload(poll_interval=5.0)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from Agent.events import (
        AgentDisabled,
        AgentEnabled,
        AgentRegistered,
        AgentReloaded,
        AgentUnregistered,
    )

    _HAS_EVENTS = True
except ImportError:
    _HAS_EVENTS = False

from Agent.agent_meta import AgentMeta
from Agent.personality import PersonalityRegistry

logger = logging.getLogger(__name__)


# ======================================================================
# Data types
# ======================================================================


@dataclass(frozen=True)
class AgentInfo:
    """Public information about a registered agent.

    Attributes:
        name: Agent name (identifier).
        version: Semantic version string.
        description: Human-readable description.
        tags: Searchable keywords.
        capabilities: High-level capability names.
        enabled: Whether the agent is currently enabled (participates in routing).
        source_path: Filesystem path to the agent's ``.md`` file, or ``None``.
        plugin_name: Name of the plugin that registered this agent, or ``None``.
    """

    name: str
    version: str
    description: str
    tags: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    enabled: bool = True
    source_path: str | None = None
    plugin_name: str | None = None


# ======================================================================
# AgentManager
# ======================================================================


class AgentManager:
    """Unified agent lifecycle manager.

    Provides a single API that synchronises ``PersonalityRegistry`` and
    (optionally) ``PluginManager``.  All public methods are thread-safe.

    Attributes:
        registry: The underlying ``PersonalityRegistry`` singleton.
        plugin_manager: An optional ``PluginManager`` for plugin integration.
        agent_dirs: Directories to scan for Markdown agent files.
    """

    def __init__(
        self,
        registry: PersonalityRegistry | None = None,
        plugin_manager: Any = None,
        agent_dirs: list[str] | None = None,
        event_bus: Any = None,
    ) -> None:
        """Initialise the agent manager.

        Args:
            registry: A ``PersonalityRegistry`` instance.  If ``None``,
                the singleton is used.
            plugin_manager: An optional ``PluginManager`` for synchronising
                plugin-based agent registrations.
            agent_dirs: List of directories to scan for agent ``.md`` files.
                If ``None``, defaults to the project ``agents/`` directory.
            event_bus: An optional ``EventBus`` for publishing lifecycle events.
        """
        self._registry = registry or PersonalityRegistry.get_instance()
        self._plugin_manager = plugin_manager
        self._agent_dirs = list(agent_dirs) if agent_dirs else self._default_dirs()

        # Enabled/disabled tracking (beyond what PersonalityRegistry stores)
        self._enabled: dict[str, bool] = {}
        self._lock = threading.Lock()

        # Event bus for lifecycle events
        self._event_bus = event_bus

        # Hot-reload background thread
        self._hot_reload_thread: threading.Thread | None = None
        self._hot_reload_stop = threading.Event()
        self._hot_reload_interval: float = 5.0

    # ------------------------------------------------------------------
    # Public API — lifecycle
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        meta: AgentMeta,
        plugin_name: str | None = None,
    ) -> None:
        """Register an agent in all available registries.

        Args:
            name: Unique agent identifier.
            meta: The ``AgentMeta`` describing the agent.
            plugin_name: Optional plugin name (for tracking provenance).

        Raises:
            ValueError: If *name* is empty or already registered.
        """
        if not name or not name.strip():
            raise ValueError("Agent name must be non-empty")

        # PersonalityRegistry
        self._registry.register_agent_meta(meta)

        # PluginManager (if available)
        if self._plugin_manager is not None:
            try:
                self._plugin_manager.register_agent(name, meta)
            except ValueError:
                # Already registered in plugin manager — still ok, just log
                logger.debug("Agent %r already registered in PluginManager", name)

        # Internal tracking
        with self._lock:
            self._enabled[name] = True

        logger.info(
            "AgentManager: registered agent %r v%s%s",
            name,
            meta.version,
            f" (via plugin {plugin_name!r})" if plugin_name else "",
        )
        self._publish(
            AgentRegistered(
                source="agent_manager",
                timestamp=time.time(),
                agent_name=name,
                version=meta.version,
                source_path=meta.source_path,
                plugin_name=plugin_name,
            )
        )

    def unregister(self, name: str) -> bool:
        """Remove an agent from all registries.

        Args:
            name: Agent name to remove.

        Returns:
            ``True`` if the agent was found and removed.
        """
        found = False

        # PersonalityRegistry — no built-in unregister, so we manipulate
        # internal dicts directly (only way with current API).
        try:
            meta = self._registry.get_agent_meta(name)
            self._registry._agent_metas.pop(name, None)
            self._registry._personalities.pop(name, None)
            found = True
        except KeyError:
            pass

        # PluginManager
        if self._plugin_manager is not None:
            agents = self._plugin_manager.get_registered_agents()
            if name in agents:
                agents.pop(name, None)
                found = True

        with self._lock:
            self._enabled.pop(name, None)

        if found:
            logger.info("AgentManager: unregistered agent %r", name)
            self._publish(
                AgentUnregistered(source="agent_manager", timestamp=time.time(), agent_name=name)
            )
        return found

    def reload(self, name: str) -> bool:
        """Reload a single agent from disk.

        Re-scans the agent directories, finds the ``.md`` file for the
        named agent, parses it, and re-registers it.

        Args:
            name: Agent name to reload.

        Returns:
            ``True`` if the agent was found on disk and reloaded.
        """
        from Agent.agent_loader import parse_agent_file

        for agent_dir in self._agent_dirs:
            path = Path(agent_dir).expanduser().resolve()
            if not path.is_dir():
                continue
            for entry in path.rglob("*.md"):
                if entry.name.upper() == "README.md":
                    continue
                meta = parse_agent_file(str(entry))
                if meta is not None and meta.name == name:
                    # Re-register (overwrites existing)
                    enabled = self.is_enabled(name)
                    self.register(name, meta)
                    if not enabled:
                        self.disable(name)
                    logger.info("AgentManager: reloaded agent %r from %s", name, entry)
                    self._publish(
                        AgentReloaded(
                            source="agent_manager",
                            timestamp=time.time(),
                            agent_name=name,
                            version=meta.version,
                        )
                    )
                    return True
        logger.warning("AgentManager: cannot reload %r — not found on disk", name)
        return False

    def reload_all(self) -> int:
        """Re-scan all agent directories and register any agents found.

        Existing agents are updated (overwritten).  Agents that no longer
        have a corresponding file on disk are **not** removed (they stay
        in memory until explicitly unregistered).

        Returns:
            The number of agent files found and (re-)registered.
        """
        from Agent.agent_loader import discover_agents

        count = 0
        for agent_dir in self._agent_dirs:
            metas = discover_agents(agent_dir)
            for meta in metas:
                enabled = self.is_enabled(meta.name)
                self.register(meta.name, meta)
                if not enabled:
                    self.disable(meta.name)
                count += 1
        logger.info("AgentManager: reload_all found %d agents", count)
        return count

    # ------------------------------------------------------------------
    # Public API — enable / disable
    # ------------------------------------------------------------------

    def enable(self, name: str) -> bool:
        """Mark an agent as enabled (participates in routing).

        Args:
            name: Agent name.

        Returns:
            ``True`` if the agent exists and was enabled.
        """
        previously_enabled: bool | None = None
        with self._lock:
            if name not in self._enabled:
                # Check if it exists in the registry
                try:
                    self._registry.get_agent_meta(name)
                except KeyError:
                    return False
                self._enabled[name] = True
            previously_enabled = self._enabled.get(name, False)
            self._enabled[name] = True
        if not previously_enabled:
            self._publish(
                AgentEnabled(source="agent_manager", timestamp=time.time(), agent_name=name)
            )
        return True

    def disable(self, name: str) -> bool:
        """Mark an agent as disabled (excluded from routing).

        Args:
            name: Agent name.

        Returns:
            ``True`` if the agent exists and was disabled.
        """
        with self._lock:
            try:
                self._registry.get_agent_meta(name)
            except KeyError:
                return False
            was_disabled = not self._enabled.get(name, True)
            self._enabled[name] = False
        if not was_disabled:
            self._publish(
                AgentDisabled(source="agent_manager", timestamp=time.time(), agent_name=name)
            )
        return True

    def is_enabled(self, name: str) -> bool:
        """Check whether an agent is currently enabled.

        Args:
            name: Agent name.

        Returns:
            ``True`` if enabled, ``False`` if disabled or not found.
        """
        with self._lock:
            return self._enabled.get(name, True)

    # ------------------------------------------------------------------
    # Public API — queries
    # ------------------------------------------------------------------

    def list(self) -> list[AgentInfo]:
        """Return information about every registered agent.

        Returns:
            A list of ``AgentInfo`` objects, one per registered agent.
        """
        results: list[AgentInfo] = []
        for meta in self._registry.list_agent_metas():
            results.append(self._meta_to_info(meta))
        # Sort by name for deterministic output
        results.sort(key=lambda info: info.name)
        return results

    def get(self, name: str) -> AgentInfo | None:
        """Return information for a single agent.

        Args:
            name: Agent name.

        Returns:
            An ``AgentInfo``, or ``None`` if not found.
        """
        try:
            meta = self._registry.get_agent_meta(name)
            return self._meta_to_info(meta)
        except KeyError:
            return None

    def get_enabled(self) -> list[AgentInfo]:
        """Return only enabled agents."""
        return [a for a in self.list() if a.enabled]

    def get_disabled(self) -> list[AgentInfo]:
        """Return only disabled agents."""
        return [a for a in self.list() if not a.enabled]

    @property
    def enabled_agent_names(self) -> set[str]:
        """Return the set of currently enabled agent names."""
        with self._lock:
            return {
                name
                for name, enabled in self._enabled.items()
                if enabled
            }

    # ------------------------------------------------------------------
    # Hot-reload
    # ------------------------------------------------------------------

    def start_hot_reload(self, poll_interval: float = 5.0) -> None:
        """Start a background thread that polls agent directories for changes.

        Args:
            poll_interval: Seconds between scans (default: 5.0).
        """
        if self._hot_reload_thread is not None and self._hot_reload_thread.is_alive():
            logger.warning("AgentManager: hot-reload already running")
            return

        self._hot_reload_interval = poll_interval
        self._hot_reload_stop.clear()
        self._hot_reload_thread = threading.Thread(
            target=self._hot_reload_loop,
            name="agent-hot-reload",
            daemon=True,
        )
        self._hot_reload_thread.start()
        logger.info(
            "AgentManager: hot-reload started (interval=%.1fs)", poll_interval
        )

    def stop_hot_reload(self) -> None:
        """Signal the hot-reload background thread to stop."""
        self._hot_reload_stop.set()
        if self._hot_reload_thread is not None:
            self._hot_reload_thread.join(timeout=3.0)
            logger.info("AgentManager: hot-reload stopped")

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: Any) -> None:
        """Set or replace the event bus used for publishing lifecycle events.

        Args:
            event_bus: An ``EventBus`` instance.
        """
        self._event_bus = event_bus

    def _publish(self, event: Any) -> None:
        """Publish an event on the configured event bus (no-op if not set)."""
        if self._event_bus is not None and _HAS_EVENTS:
            self._event_bus.publish(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _meta_to_info(self, meta: AgentMeta) -> AgentInfo:
        """Convert an ``AgentMeta`` to a public ``AgentInfo``."""
        return AgentInfo(
            name=meta.name,
            version=meta.version,
            description=meta.description,
            tags=meta.tags,
            capabilities=meta.capabilities,
            enabled=self.is_enabled(meta.name),
            source_path=meta.source_path,
        )

    def _hot_reload_loop(self) -> None:
        """Background polling loop."""
        while not self._hot_reload_stop.is_set():
            self._hot_reload_stop.wait(timeout=self._hot_reload_interval)
            if self._hot_reload_stop.is_set():
                break
            try:
                self.reload_all()
            except Exception as exc:
                logger.warning("AgentManager: hot-reload scan error: %s", exc)

    @staticmethod
    def _default_dirs() -> list[str]:
        """Return the default agent directory path."""
        base = Path(__file__).resolve().parent.parent  # project root
        agents_dir = base / "agents"
        if agents_dir.is_dir():
            return [str(agents_dir)]
        return []


__all__ = [
    "AgentInfo",
    "AgentManager",
]
