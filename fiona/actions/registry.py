"""Central registry for named action handlers.

This is the bridge between the legacy ``_execute_action`` if/elif chain
and the future ``ToolRuntime``.  Actions registered here are discoverable
by ``AgentOrchestrator``, and later by ``Coordinator`` / ``ToolRuntime``
via the ``ActionHandlerTool`` adapter.
"""

from __future__ import annotations

import threading
from typing import Any

from fiona.actions.handler import ActionHandler


class ActionRegistry:
    """Thread-safe registry that maps action names to handlers.

    Usage::

        registry = ActionRegistry()
        handler = registry.lookup("api_search")
        if handler is not None:
            result = handler.execute({"query": "weather"})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}
        self._lock = threading.RLock()
        self._load_defaults()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        """Import and register built-in action providers.

        Uses lazy imports so no heavy initialisation happens until the
        registry is actually created.  This is intentionally **not**
        based on ``PluginManager`` so the registry has zero dependencies
        on newer Fiona components.  When ``PluginManager`` comes online
        it simply calls ``registry.register()`` as an additional path.
        """
        # API catalog actions
        try:
            from fiona.apicatalog.actions import (
                ApiInfoHandler,
                ApiListCategoriesHandler,
                ApiSearchHandler,
            )

            self._register_handler(ApiSearchHandler())
            self._register_handler(ApiInfoHandler())
            self._register_handler(ApiListCategoriesHandler())
        except ImportError:
            pass  # apicatalog package not installed — skip gracefully

    def _register_handler(self, handler: ActionHandler) -> None:
        """Register a handler keyed by ``handler.name``."""
        self._handlers[handler.name] = handler

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, name: str, handler: ActionHandler) -> None:
        """Register *handler* under *name*.

        This is the public entry point for plugins and tests.
        """
        with self._lock:
            self._handlers[name] = handler

    def lookup(self, name: str) -> ActionHandler | None:
        """Return the handler registered for *name*, or ``None``."""
        with self._lock:
            return self._handlers.get(name)

    def run(self, name: str, params: dict[str, Any]) -> str:
        """Lookup *name* and call ``handler.execute(params)``.

        Raises ``KeyError`` if no handler is registered for *name*.
        """
        handler = self.lookup(name)
        if handler is None:
            msg = f"No handler registered for '{name}'"
            raise KeyError(msg)
        return handler.execute(params)

    def list_actions(self) -> list[dict]:
        """Return all registered actions as Ollama-compatible function specs.

        Used later by LLM function-calling integration.
        """
        return [h.to_tool_spec() for h in self._handlers.values()]

    def __contains__(self, name: str) -> bool:
        return self.lookup(name) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._handlers)
