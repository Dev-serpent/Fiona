"""Integration tests — ActionRegistry wiring, AgentOrchestrator integration."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from fiona.actions import ActionHandler, ActionRegistry


class _PingHandler(ActionHandler):
    @property
    def name(self) -> str:
        return "ping"

    def execute(self, params: dict[str, Any]) -> str:
        return "pong"


class TestActionRegistryApiCatalogDefaults(unittest.TestCase):
    """Verify that ActionRegistry auto-loads API catalog handlers."""

    def test_default_registry_has_api_handlers(self) -> None:
        """The default ActionRegistry should include api_search, api_info,
        and api_categories from the apicatalog package."""
        registry = ActionRegistry()
        self.assertIn("api_search", registry)
        self.assertIn("api_info", registry)
        self.assertIn("api_categories", registry)

    def test_api_search_can_run(self) -> None:
        """api_search should execute without error (returns 'no results' or
        actual results depending on whether the real repo is cloned)."""
        registry = ActionRegistry()
        result = registry.run("api_search", {"query": "weather"})
        # Should either find results or give a helpful message
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestOrchestratorIntegration(unittest.TestCase):
    """Verify AgentOrchestrator.__init__ accepts action_registry and
    _execute_action checks it first."""

    def test_orchestrator_accepts_registry(self) -> None:
        """AgentOrchestrator should accept an action_registry parameter."""
        from Agent.orchestrator import AgentOrchestrator

        registry = ActionRegistry()
        orchestrator = AgentOrchestrator(
            client=MagicMock(),
            approval_manager=MagicMock(),
            action_registry=registry,
        )
        self.assertIs( orchestrator._action_registry, registry)

    def test_orchestrator_creates_default_registry(self) -> None:
        """When no action_registry is given, AgentOrchestrator should
        create a default one."""
        from Agent.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(
            client=MagicMock(),
            approval_manager=MagicMock(),
        )
        self.assertIsNotNone(orchestrator._action_registry)

    def test_execute_action_checks_registry_first(self) -> None:
        """_execute_action should dispatch to registry before falling
        through to the legacy if/elif chain."""
        from Agent.orchestrator import AgentOrchestrator

        registry = ActionRegistry()
        registry.register("ping", _PingHandler())

        orchestrator = AgentOrchestrator(
            client=MagicMock(),
            approval_manager=MagicMock(),
            action_registry=registry,
        )

        result = orchestrator._execute_action("ping", {})
        self.assertEqual(result, "pong")

    def test_unknown_action_falls_through(self) -> None:
        """An action not in the registry should fall through to the
        legacy chain and return 'Unknown action'."""
        from Agent.orchestrator import AgentOrchestrator

        registry = ActionRegistry()
        orchestrator = AgentOrchestrator(
            client=MagicMock(),
            approval_manager=MagicMock(),
            action_registry=registry,
        )

        result = orchestrator._execute_action("nonexistent_action_xyz", {})
        self.assertIn("Unknown action", result)

    def test_legacy_action_still_works(self) -> None:
        """Existing legacy actions should still work via the if/elif chain."""
        from Agent.orchestrator import AgentOrchestrator

        registry = ActionRegistry()
        orchestrator = AgentOrchestrator(
            client=MagicMock(),
            approval_manager=MagicMock(),
            action_registry=registry,
        )

        # sciretrieval_query is a legacy action — it should go through the
        # if/elif chain (and fail with relevant error, not "Unknown action")
        result = orchestrator._execute_action("sciretrieval_query", {"query": "test"})
        # It should NOT say "Unknown action"
        self.assertNotIn("Unknown action", result)


if __name__ == "__main__":
    unittest.main()
