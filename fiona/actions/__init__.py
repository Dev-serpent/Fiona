"""Action Registry — lightweight runtime dispatch for named actions.

This package provides the :class:`ActionHandler` abstract base and the
:class:`ActionRegistry` that maps action names to handlers.  It is the
bridge between the legacy ``AgentOrchestrator._execute_action`` if/elif
chain and the future ``ToolRuntime`` / ``Coordinator`` architecture.
"""

from fiona.actions.handler import ActionHandler
from fiona.actions.registry import ActionRegistry

__all__ = [
    "ActionHandler",
    "ActionRegistry",
]
