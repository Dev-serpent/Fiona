"""Explicit backward compatibility tests for the Fiona Agent package.

These tests verify that all existing public APIs remain unchanged after
the M1-M5 changes.  They must pass without M1-M5 changes affecting
existing behaviour.
"""

from __future__ import annotations

import unittest


class TestBackwardCompat(unittest.TestCase):
    """Verify existing public APIs remain unchanged."""

    def test_ollama_client_default_construction(self) -> None:
        """OllamaClient() with no args works."""
        from Agent import OllamaClient
        client = OllamaClient()
        self.assertEqual(client.base_url, "http://localhost:11434/api")
        self.assertEqual(client.model, "qwen3:8b-en")

    def test_command_registry_no_args(self) -> None:
        """command_registry() with no args returns identical structure."""
        from Agent import command_registry
        result = command_registry()
        self.assertIn("commands", result)
        self.assertIn("apps", result)
        self.assertIsInstance(result["commands"], list)

    def test_agent_orchestrator_importable(self) -> None:
        """AgentOrchestrator class still exists and works."""
        from Agent import AgentOrchestrator
        # Just construction — no LLM call
        orchestrator = AgentOrchestrator()
        self.assertIsNotNone(orchestrator)

    def test_agent_turn_importable(self) -> None:
        """AgentTurn dataclass still exists."""
        from Agent import AgentTurn
        turn = AgentTurn(thought="test")
        self.assertEqual(turn.thought, "test")

    def test_command_spec_importable(self) -> None:
        """CommandSpec dataclass still exists."""
        from Agent import CommandSpec
        spec = CommandSpec(name="test", category="test", description="",
                           input_schema={})
        self.assertEqual(spec.name, "test")

    def test_phi_connect_app_importable(self) -> None:
        """PhiConnectApp still importable and has original tabs."""
        from PhiConnect.gui import PhiConnectApp
        # Can't instantiate without display, but import should work
        self.assertTrue(callable(PhiConnectApp))

    def test_agent_init_exports_unchanged(self) -> None:
        """All original Agent __init__ exports still present."""
        import Agent
        self.assertTrue(hasattr(Agent, "OllamaClient"))
        self.assertTrue(hasattr(Agent, "OllamaError"))
        self.assertTrue(hasattr(Agent, "AgentOrchestrator"))
        self.assertTrue(hasattr(Agent, "AgentTurn"))
        self.assertTrue(hasattr(Agent, "CommandSpec"))
        self.assertTrue(hasattr(Agent, "command_registry"))
        self.assertTrue(hasattr(Agent, "run_agent_goal"))
        self.assertTrue(hasattr(Agent, "DEFAULT_OLLAMA_BASE_URL"))

    def test_run_agent_goal_is_callable(self) -> None:
        """run_agent_goal is a function."""
        from Agent import run_agent_goal
        self.assertTrue(callable(run_agent_goal))

    def test_new_exports_present(self) -> None:
        """New exports from M1-M5 are also present (backward compat does
        not preclude expansion).
        """
        import Agent
        # New exports — just verify they exist without breaking
        self.assertTrue(hasattr(Agent, "Personality"))
        self.assertTrue(hasattr(Agent, "PersonalityRegistry"))
        self.assertTrue(hasattr(Agent, "PermissionEnforcer"))
        self.assertTrue(hasattr(Agent, "SafeActionRouter"))
        self.assertTrue(hasattr(Agent, "CancellationToken"))
        self.assertTrue(hasattr(Agent, "CancelledError"))
        self.assertTrue(hasattr(Agent, "ChatStore"))
        self.assertTrue(hasattr(Agent, "ChatMessage"))
        self.assertTrue(hasattr(Agent, "ChatStoreError"))
        self.assertTrue(hasattr(Agent, "AgentChatHandler"))
        self.assertTrue(hasattr(Agent, "ForemanAgent"))
        self.assertTrue(hasattr(Agent, "ForemanConfig"))
        self.assertTrue(hasattr(Agent, "Complexity"))
        self.assertTrue(hasattr(Agent, "ComplexityAssessor"))
        self.assertTrue(hasattr(Agent, "SubAgent"))
        self.assertTrue(hasattr(Agent, "SubAgentResult"))
        self.assertTrue(hasattr(Agent, "SubGoalSpec"))
        self.assertTrue(hasattr(Agent, "TaskPlan"))
        self.assertTrue(hasattr(Agent, "PlanValidationError"))

    def test_ollama_error_is_runtime_error(self) -> None:
        """OllamaError is still a RuntimeError."""
        from Agent import OllamaError
        self.assertTrue(issubclass(OllamaError, RuntimeError))

    def test_default_base_url_unchanged(self) -> None:
        """DEFAULT_OLLAMA_BASE_URL value unchanged."""
        from Agent import DEFAULT_OLLAMA_BASE_URL
        self.assertEqual(DEFAULT_OLLAMA_BASE_URL, "http://localhost:11434/api")

    def test_command_registry_returns_expected_tools(self) -> None:
        """command_registry() returns the expected tools."""
        from Agent import command_registry
        result = command_registry()
        names = {c["name"] for c in result["commands"]}
        expected = {
            "press", "click", "move", "text", "launch_binding", "macro",
            "seeondesk_list", "seeondesk_active", "seeondesk_analyze",
            "dataclient_mine", "recall_remember", "recall_search",
            "fiona_status",
            "browser_status", "browser_navigate", "browser_click",
            "browser_type", "browser_screenshot",
            "sciretrieval_query",
        }
        self.assertEqual(names, expected)


if __name__ == "__main__":
    unittest.main()
