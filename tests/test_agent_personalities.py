from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from Agent import (
    AgentPermissionError,
    OllamaClient,
    PermissionEnforcer,
    Personality,
    PersonalityRegistry,
    SafeActionRouter,
    command_registry,
)
from Agent.permission import AgentPermissionError as InternalPermissionError
from FionaCore import ActionResult


# ======================================================================
# Personality unit tests
# ======================================================================

class TestPersonality(unittest.TestCase):
    """Personality dataclass construction, permits(), to_dict()."""

    def test_create(self) -> None:
        p = Personality(
            name="test",
            description="A test personality",
            system_prompt="You are a test.",
        )
        self.assertEqual(p.name, "test")
        self.assertEqual(p.description, "A test personality")
        self.assertEqual(p.system_prompt, "You are a test.")
        self.assertIsNone(p.allowed_tools)
        self.assertIsNone(p.model_override)

    def test_permits_all_when_allowed_tools_is_none(self) -> None:
        p = Personality(name="any", description="x", system_prompt="x")
        self.assertTrue(p.permits("press"))
        self.assertTrue(p.permits("click"))
        self.assertTrue(p.permits("anything_else"))

    def test_permits_specific_tool(self) -> None:
        p = Personality(
            name="limited",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"press", "click"}),
        )
        self.assertTrue(p.permits("press"))
        self.assertTrue(p.permits("click"))
        self.assertFalse(p.permits("text"))
        self.assertFalse(p.permits("macro"))

    def test_permits_empty_set_denies_all(self) -> None:
        p = Personality(
            name="empty",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset(),
        )
        self.assertFalse(p.permits("press"))
        self.assertFalse(p.permits("click"))

    def test_to_dict(self) -> None:
        p = Personality(
            name="test",
            description="A test",
            system_prompt="Be testy.",
            allowed_tools=frozenset({"a", "b"}),
            model_override="gpt4",
        )
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["description"], "A test")
        self.assertEqual(d["system_prompt"], "Be testy.")
        self.assertCountEqual(d["allowed_tools"], ["a", "b"])
        self.assertEqual(d["model_override"], "gpt4")

    def test_to_dict_allowed_tools_none(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x")
        d = p.to_dict()
        self.assertIsNone(d["allowed_tools"])

    def test_frozen_cannot_mutate(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x")
        with self.assertRaises(AttributeError):
            p.name = "y"  # type: ignore[misc]

    def test_model_override_can_be_none(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x")
        self.assertIsNone(p.model_override)


# ======================================================================
# PersonalityRegistry unit tests
# ======================================================================

class TestPersonalityRegistry(unittest.TestCase):
    """Singleton behaviour, lookup, registration, built-ins."""

    def setUp(self) -> None:
        # Force a fresh singleton for each test by clearing the class-level
        # instance.  We must be careful not to interfere with other tests
        # that rely on the singleton.  We restore it in tearDown.
        self._old_instance = PersonalityRegistry._instance
        PersonalityRegistry._instance = None

    def tearDown(self) -> None:
        PersonalityRegistry._instance = self._old_instance

    def test_singleton_same_instance(self) -> None:
        r1 = PersonalityRegistry()
        r2 = PersonalityRegistry()
        self.assertIs(r1, r2)

    def test_get_instance_class_method(self) -> None:
        r1 = PersonalityRegistry.get_instance()
        r2 = PersonalityRegistry.get_instance()
        self.assertIs(r1, r2)

    def test_get_builtin_exists(self) -> None:
        reg = PersonalityRegistry()
        p = reg.get("general")
        self.assertEqual(p.name, "general")

    def test_get_missing_raises_key_error(self) -> None:
        reg = PersonalityRegistry()
        with self.assertRaises(KeyError):
            reg.get("nonexistent")

    def test_list_returns_all_builtins(self) -> None:
        reg = PersonalityRegistry()
        names = {p.name for p in reg.list()}
        self.assertEqual(names, {"general", "planner", "engineer", "analyst", "security", "controller"})

    def test_register_custom_personality(self) -> None:
        reg = PersonalityRegistry()
        p = Personality(name="custom", description="Custom", system_prompt="Custom prompt.")
        reg.register(p)
        self.assertIs(reg.get("custom"), p)

    def test_register_replace_existing(self) -> None:
        reg = PersonalityRegistry()
        p1 = Personality(name="dup", description="first", system_prompt="A")
        p2 = Personality(name="dup", description="second", system_prompt="B")
        reg.register(p1)
        reg.register(p2)
        self.assertEqual(reg.get("dup").description, "second")

    def test_register_empty_name_raises(self) -> None:
        reg = PersonalityRegistry()
        with self.assertRaises(ValueError):
            reg.register(Personality(name="", description="x", system_prompt="x"))

    def test_register_whitespace_name_raises(self) -> None:
        reg = PersonalityRegistry()
        with self.assertRaises(ValueError):
            reg.register(Personality(name="   ", description="x", system_prompt="x"))


# ======================================================================
# Built-in personality verification
# ======================================================================

class TestBuiltinPersonalities(unittest.TestCase):
    """Verify the 5 built-in personalities match the spec."""

    def setUp(self) -> None:
        self._old_instance = PersonalityRegistry._instance
        PersonalityRegistry._instance = None
        self.reg = PersonalityRegistry()

    def tearDown(self) -> None:
        PersonalityRegistry._instance = self._old_instance

    # -- general ---------------------------------------------------------

    def test_general_name_and_tools(self) -> None:
        p = self.reg.get("general")
        self.assertEqual(p.name, "general")
        self.assertIsNone(p.allowed_tools)  # None = all permitted
        self.assertIsNone(p.model_override)
        # Should contain the Fiona identity rules
        self.assertIn("SYSTEM OPERATOR", p.system_prompt)
        self.assertNotIn("AVAILABLE TOOLS", p.system_prompt)  # dynamic part excluded

    # -- planner ---------------------------------------------------------

    def test_planner_name_and_tools(self) -> None:
        p = self.reg.get("planner")
        self.assertEqual(p.name, "planner")
        expected_tools = frozenset({
            "seeondesk_list", "seeondesk_active", "fiona_status",
            "recall_search", "recall_remember",
        })
        self.assertEqual(p.allowed_tools, expected_tools)
        self.assertEqual(p.model_override, "qwen3:8b-en")
        self.assertIn("strategic planner", p.system_prompt.lower())

    def test_planner_denies_input_tools(self) -> None:
        p = self.reg.get("planner")
        self.assertFalse(p.permits("press"))
        self.assertFalse(p.permits("click"))
        self.assertFalse(p.permits("text"))
        self.assertFalse(p.permits("launch_binding"))
        self.assertFalse(p.permits("macro"))
        self.assertFalse(p.permits("seeondesk_analyze"))
        self.assertFalse(p.permits("dataclient_mine"))

    def test_planner_allows_observe_tools(self) -> None:
        p = self.reg.get("planner")
        self.assertTrue(p.permits("seeondesk_list"))
        self.assertTrue(p.permits("seeondesk_active"))
        self.assertTrue(p.permits("fiona_status"))
        self.assertTrue(p.permits("recall_search"))
        self.assertTrue(p.permits("recall_remember"))

    # -- engineer --------------------------------------------------------

    def test_engineer_name_and_tools(self) -> None:
        p = self.reg.get("engineer")
        self.assertEqual(p.name, "engineer")
        expected_tools = frozenset({
            "press", "click", "move", "text", "launch_binding", "macro",
            "seeondesk_list", "seeondesk_active", "fiona_status",
        })
        self.assertEqual(p.allowed_tools, expected_tools)
        self.assertIsNone(p.model_override)
        self.assertIn("senior engineer", p.system_prompt.lower())

    def test_engineer_allows_input_tools(self) -> None:
        p = self.reg.get("engineer")
        self.assertTrue(p.permits("press"))
        self.assertTrue(p.permits("click"))
        self.assertTrue(p.permits("move"))
        self.assertTrue(p.permits("text"))
        self.assertTrue(p.permits("launch_binding"))
        self.assertTrue(p.permits("macro"))

    def test_engineer_denies_analysis_tools(self) -> None:
        p = self.reg.get("engineer")
        self.assertFalse(p.permits("seeondesk_analyze"))
        self.assertFalse(p.permits("dataclient_mine"))
        self.assertFalse(p.permits("recall_remember"))
        self.assertFalse(p.permits("recall_search"))

    # -- analyst ---------------------------------------------------------

    def test_analyst_name_and_tools(self) -> None:
        p = self.reg.get("analyst")
        self.assertEqual(p.name, "analyst")
        expected_tools = frozenset({
            "dataclient_mine", "recall_remember", "recall_search",
            "seeondesk_analyze", "seeondesk_list", "seeondesk_active",
            "fiona_status",
        })
        self.assertEqual(p.allowed_tools, expected_tools)
        self.assertEqual(p.model_override, "qwen3:8b-en")
        self.assertIn("system analyst", p.system_prompt.lower())

    def test_analyst_denies_input_tools(self) -> None:
        p = self.reg.get("analyst")
        self.assertFalse(p.permits("press"))
        self.assertFalse(p.permits("click"))
        self.assertFalse(p.permits("move"))
        self.assertFalse(p.permits("text"))
        self.assertFalse(p.permits("launch_binding"))
        self.assertFalse(p.permits("macro"))

    # -- security --------------------------------------------------------

    def test_security_name_and_tools(self) -> None:
        p = self.reg.get("security")
        self.assertEqual(p.name, "security")
        expected_tools = frozenset({
            "seeondesk_list", "seeondesk_active", "fiona_status",
            "recall_search",
        })
        self.assertEqual(p.allowed_tools, expected_tools)
        self.assertEqual(p.model_override, "qwen3:8b-en")
        self.assertIn("security engineer", p.system_prompt.lower())

    def test_security_denies_mutation_tools(self) -> None:
        p = self.reg.get("security")
        self.assertFalse(p.permits("press"))
        self.assertFalse(p.permits("click"))
        self.assertFalse(p.permits("text"))
        self.assertFalse(p.permits("macro"))
        self.assertFalse(p.permits("dataclient_mine"))
        self.assertFalse(p.permits("recall_remember"))
        self.assertFalse(p.permits("seeondesk_analyze"))


# ======================================================================
# PermissionEnforcer unit tests
# ======================================================================

class TestPermissionEnforcer(unittest.TestCase):
    """Enforcer allow/deny logic."""

    def test_allows_when_permitted(self) -> None:
        p = Personality(
            name="test",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"allowed_tool"}),
        )
        enforcer = PermissionEnforcer(p)
        self.assertTrue(enforcer.check_tool("allowed_tool"))
        # Should not raise
        enforcer.assert_tool_allowed("allowed_tool")

    def test_denies_when_not_permitted(self) -> None:
        p = Personality(
            name="test",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"allowed_tool"}),
        )
        enforcer = PermissionEnforcer(p)
        self.assertFalse(enforcer.check_tool("other_tool"))

    def test_assert_raises_permission_error(self) -> None:
        p = Personality(name="lim", description="x", system_prompt="x",
                        allowed_tools=frozenset({"a"}))
        enforcer = PermissionEnforcer(p)
        with self.assertRaises(InternalPermissionError) as ctx:
            enforcer.assert_tool_allowed("b")
        self.assertEqual(ctx.exception.tool_name, "b")
        self.assertEqual(ctx.exception.personality_name, "lim")

    def test_assert_raises_exported_alias(self) -> None:
        p = Personality(name="lim", description="x", system_prompt="x",
                        allowed_tools=frozenset({"a"}))
        enforcer = PermissionEnforcer(p)
        with self.assertRaises(AgentPermissionError):
            enforcer.assert_tool_allowed("b")

    def test_allows_all_when_no_restrictions(self) -> None:
        p = Personality(name="free", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        self.assertTrue(enforcer.check_tool("anything"))
        enforcer.assert_tool_allowed("anything")  # no raise

    def test_personality_property(self) -> None:
        p = Personality(name="prop_test", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        self.assertIs(enforcer.personality, p)


# ======================================================================
# SafeActionRouter unit tests
# ======================================================================

class _MockActionRouter:
    """Minimal mock that records calls and returns fixed results."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, dict]] = []

    def run(self, name: str, **kwargs: object) -> ActionResult:
        self.runs.append((name, kwargs))
        return ActionResult(ok=True, action=name, detail="mock")

    def list_actions(self) -> list[dict[str, object]]:
        return [
            {"name": "press"},
            {"name": "click"},
            {"name": "fiona_status"},
            {"name": "recall_search"},
        ]


class TestSafeActionRouter(unittest.TestCase):
    """Permission check then delegation."""

    def test_permitted_action_passes_through(self) -> None:
        p = Personality(
            name="test",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"tool_a"}),
        )
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        router = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        result = router.run("tool_a")
        self.assertTrue(result.ok)
        self.assertEqual(result.action, "tool_a")
        self.assertEqual(len(mock.runs), 1)
        self.assertEqual(mock.runs[0][0], "tool_a")

    def test_denied_action_raises_permission_error(self) -> None:
        p = Personality(
            name="test",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"tool_a"}),
        )
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        router = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        with self.assertRaises(InternalPermissionError) as ctx:
            router.run("tool_b")
        self.assertEqual(ctx.exception.tool_name, "tool_b")
        self.assertEqual(ctx.exception.personality_name, "test")
        # Ensure the underlying router was NOT called
        self.assertEqual(len(mock.runs), 0)

    def test_no_restrictions_passes_all(self) -> None:
        p = Personality(name="free", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        router = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        result = router.run("any_tool")
        self.assertTrue(result.ok)
        self.assertEqual(len(mock.runs), 1)

    def test_list_allowed_actions_all_permitted(self) -> None:
        p = Personality(name="free", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        router = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        actions = router.list_allowed_actions()
        self.assertEqual(len(actions), 4)

    def test_list_allowed_actions_filtered(self) -> None:
        p = Personality(
            name="filtered",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"press", "fiona_status"}),
        )
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        router = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        actions = router.list_allowed_actions()
        names = {a["name"] for a in actions}
        self.assertEqual(names, {"press", "fiona_status"})

    def test_router_and_enforcer_properties(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        sar = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]
        self.assertIs(sar.router, mock)
        self.assertIs(sar.enforcer, enforcer)

    def test_run_passes_kwargs(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock = _MockActionRouter()
        sar = SafeActionRouter(enforcer, router=mock)  # type: ignore[arg-type]

        sar.run("press", source="agent", permission_profile="local",
                dry_run=True, timeout_seconds=15.0)
        _name, kwargs = mock.runs[0]
        self.assertEqual(kwargs["source"], "agent")
        self.assertEqual(kwargs["dry_run"], True)
        self.assertEqual(kwargs["timeout_seconds"], 15.0)

    def test_default_router_created_when_none(self) -> None:
        p = Personality(name="x", description="x", system_prompt="x",
                        allowed_tools=frozenset({"press"}))
        enforcer = PermissionEnforcer(p)
        sar = SafeActionRouter(enforcer)
        from FionaCore import ActionRouter
        self.assertIsInstance(sar.router, ActionRouter)

    def test_error_message_format(self) -> None:
        p = Personality(name="test_personality", description="x", system_prompt="x",
                        allowed_tools=frozenset({"allowed"}))
        enforcer = PermissionEnforcer(p)
        with self.assertRaises(InternalPermissionError) as ctx:
            enforcer.assert_tool_allowed("forbidden_tool")
        msg = str(ctx.exception)
        self.assertIn("test_personality", msg)
        self.assertIn("forbidden_tool", msg)


# ======================================================================
# command_registry filtering tests
# ======================================================================

class TestCommandRegistryFiltering(unittest.TestCase):
    """Verify command_registry() filters correctly when enforcer is provided."""

    def test_without_enforcer_returns_all(self) -> None:
        reg = command_registry()
        names = {c["name"] for c in reg["commands"]}
        # All 13 tools from DEFAULT_ALLOWED_ACTIONS
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

    def test_with_enforcer_filters(self) -> None:
        p = Personality(
            name="limited",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset({"press", "click"}),
        )
        enforcer = PermissionEnforcer(p)
        reg = command_registry(enforcer=enforcer)
        names = {c["name"] for c in reg["commands"]}
        self.assertEqual(names, {"press", "click"})

    def test_with_enforcer_no_tools_allowed(self) -> None:
        p = Personality(
            name="empty",
            description="x",
            system_prompt="x",
            allowed_tools=frozenset(),
        )
        enforcer = PermissionEnforcer(p)
        reg = command_registry(enforcer=enforcer)
        self.assertEqual(len(reg["commands"]), 0)

    def test_with_general_enforcer_no_filtering(self) -> None:
        p = Personality(name="general", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        reg = command_registry(enforcer=enforcer)
        names = {c["name"] for c in reg["commands"]}
        self.assertEqual(len(names), 19)


# ======================================================================
# OllamaClient personality integration tests
# ======================================================================

class TestOllamaClientPersonality(unittest.TestCase):
    """OllamaClient uses personality.system_prompt and model_override."""

    def test_default_ask_without_personality(self) -> None:
        """When no personality is set, the original default prompt is used."""
        captured: list[dict] = []

        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "ok"}}).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data.decode("utf-8")))  # type: ignore[union-attr]
            return FakeResponse()

        with patch("Agent.ollama.urlopen", fake_urlopen):
            client = OllamaClient()
            client.ask("hello")

        sys_msg = captured[0]["messages"][0]
        self.assertEqual(sys_msg["role"], "system")
        self.assertEqual(sys_msg["content"],
                         "You are Fiona, a local workstation control assistant.")

    def test_personality_model_override(self) -> None:
        p = Personality(
            name="planner",
            description="x",
            system_prompt="Plan mode.",
            model_override="planner-model",
        )
        client = OllamaClient(personality=p)
        self.assertEqual(client.model, "planner-model")

    def test_personality_no_model_override_uses_default(self) -> None:
        p = Personality(name="general", description="x", system_prompt="Be general.")
        client = OllamaClient(personality=p)
        self.assertEqual(client.model, "qwen3:8b-en")

    def test_personality_system_prompt_used_by_default(self) -> None:
        p = Personality(
            name="custom",
            description="x",
            system_prompt="You are a custom personality.",
        )
        captured: list[dict] = []

        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "ok"}}).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data.decode("utf-8")))  # type: ignore[union-attr]
            return FakeResponse()

        with patch("Agent.ollama.urlopen", fake_urlopen):
            client = OllamaClient(personality=p)
            client.ask("hello")

        sys_msg = captured[0]["messages"][0]
        self.assertEqual(sys_msg["content"], "You are a custom personality.")

    def test_explicit_system_prompt_overrides_personality(self) -> None:
        p = Personality(
            name="custom",
            description="x",
            system_prompt="Personality prompt.",
        )
        captured: list[dict] = []

        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "ok"}}).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data.decode("utf-8")))  # type: ignore[union-attr]
            return FakeResponse()

        with patch("Agent.ollama.urlopen", fake_urlopen):
            client = OllamaClient(personality=p)
            client.ask("hello", system_prompt="Explicit override.")

        sys_msg = captured[0]["messages"][0]
        self.assertEqual(sys_msg["content"], "Explicit override.")

    def test_ask_without_personality_backward_compat(self) -> None:
        """Calling ask() with no personality and no override uses the old default."""
        captured: list[dict] = []

        class FakeResponse:
            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *_: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"message": {"content": "ok"}}).encode("utf-8")

        def fake_urlopen(request: object, timeout: float) -> FakeResponse:
            captured.append(json.loads(request.data.decode("utf-8")))  # type: ignore[union-attr]
            return FakeResponse()

        with patch("Agent.ollama.urlopen", fake_urlopen):
            client = OllamaClient(model="standard-model")
            client.ask("hello")

        self.assertEqual(captured[0]["model"], "standard-model")
        sys_msg = captured[0]["messages"][0]
        self.assertEqual(sys_msg["content"],
                         "You are Fiona, a local workstation control assistant.")

    def test_personality_unchanged_after_construction(self) -> None:
        p = Personality(name="x", description="x", system_prompt="X")
        client = OllamaClient(personality=p)
        self.assertIs(client.personality, p)


# ======================================================================
# AgentPermissionError import alias
# ======================================================================

class TestAgentPermissionErrorAlias(unittest.TestCase):
    """AgentPermissionError is the same class as the internal one."""

    def test_alias_matches_internal(self) -> None:
        self.assertIs(AgentPermissionError, InternalPermissionError)

    def test_can_catch_with_alias(self) -> None:
        p = Personality(name="test", description="x", system_prompt="x",
                        allowed_tools=frozenset())
        enforcer = PermissionEnforcer(p)
        with self.assertRaises(AgentPermissionError):
            enforcer.assert_tool_allowed("anything")


# ======================================================================
# Smoke test: verify the exercise commands from the spec
# ======================================================================

class TestMilestone1Smoke(unittest.TestCase):
    """Verification commands from the milestone specification."""

    def test_imports_work(self) -> None:
        from Agent import (  # noqa: F811
            Personality,
            PersonalityRegistry,
            PermissionEnforcer,
            SafeActionRouter,
        )
        self.assertTrue(Personality is not None)

    def test_backward_compat_ollama(self) -> None:
        c = OllamaClient()
        self.assertIsNotNone(c)

    def test_backward_compat_command_registry(self) -> None:
        r = command_registry()
        self.assertIn("commands", r)
        self.assertIn("apps", r)


if __name__ == "__main__":
    unittest.main()
