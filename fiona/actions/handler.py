"""Abstract base for all registered actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ActionHandler(ABC):
    """Single action that can be invoked by name.

    Handlers are discoverable, self-describing, and completely decoupled
    from ``AgentOrchestrator``.  They can be migrated to ``ITool`` later
    via the ``ActionHandlerTool`` adapter.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique action name (e.g. ``"api_search"``)."""

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> str:
        """Execute the action and return a human-readable result.

        The return type (``str``) matches the signature expected by
        ``AgentOrchestrator._execute_action`` so that handlers can be
        plugged into the legacy dispatch path without any adapters.
        """

    def to_tool_spec(self) -> dict:
        """Return an OpenAI-compatible function-calling schema.

        Override in subclasses to expose structured parameter schemas.
        The default returns a minimal generic spec.

        Used later when migrating to ``ToolRuntime`` / LLM function calling.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }
