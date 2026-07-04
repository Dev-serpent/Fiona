"""Tests for AgentMeta — the self-describing agent metadata model."""

from __future__ import annotations

import unittest

from Agent.agent_meta import AgentMeta
from Agent.personality import Personality, PersonalityRegistry


class TestAgentMeta(unittest.TestCase):
    """AgentMeta dataclass construction, conversions, serialization."""

    def test_create_minimal(self) -> None:
        meta = AgentMeta(
            name="test-agent",
            version="1.0.0",
            description="A test agent",
        )
        self.assertEqual(meta.name, "test-agent")
        self.assertEqual(meta.version, "1.0.0")
        self.assertEqual(meta.description, "A test agent")
        self.assertEqual(meta.author, "Fiona")  # default
        self.assertEqual(meta.tags, ())  # default
        self.assertEqual(meta.confidence_threshold, 0.7)  # default

    def test_create_full(self) -> None:
        meta = AgentMeta(
            name="full-agent",
            version="2.1.0",
            description="Full featured",
            tags=("ai", "test"),
            author="Test Author",
            system_prompt="You are a test agent.",
            conversational_system_prompt="Chat mode.",
            model_override="gpt4",
            capabilities=("code-gen", "analysis"),
            supported_tasks=("write code", "review code"),
            preferred_tools=("python", "git"),
            restrictions=("no deploy",),
            examples=({"query": "hello", "response": "hi"},),
            confidence_threshold=0.85,
            dependencies=("skill-1",),
            skills=("python",),
            source_path="/tmp/test.md",
        )
        self.assertEqual(meta.name, "full-agent")
        self.assertEqual(meta.model_override, "gpt4")
        self.assertEqual(meta.capabilities, ("code-gen", "analysis"))
        self.assertEqual(len(meta.examples), 1)
        self.assertEqual(meta.examples[0]["query"], "hello")

    def test_to_personality(self) -> None:
        meta = AgentMeta(
            name="test-agent",
            version="1.0.0",
            description="A test agent",
            system_prompt="You are a test agent.",
            preferred_tools=("tool_a", "tool_b"),
            model_override="custom-model",
        )
        p = meta.to_personality()
        self.assertIsInstance(p, Personality)
        self.assertEqual(p.name, "test-agent")
        self.assertEqual(p.description, "A test agent")
        self.assertEqual(p.system_prompt, "You are a test agent.")
        self.assertEqual(p.allowed_tools, frozenset({"tool_a", "tool_b"}))
        self.assertEqual(p.model_override, "custom-model")
        self.assertIsNone(p.conversational_system_prompt)

    def test_to_personality_empty_tools_means_all(self) -> None:
        meta = AgentMeta(
            name="open-agent",
            version="1.0.0",
            description="All tools agent",
            system_prompt="Be open.",
            preferred_tools=(),
        )
        p = meta.to_personality()
        self.assertIsNone(p.allowed_tools)  # () → None → all permitted

    def test_to_personality_none_tools_means_all(self) -> None:
        meta = AgentMeta(
            name="open-agent",
            version="1.0.0",
            description="All tools agent",
            system_prompt="Be open.",
        )
        p = meta.to_personality()
        self.assertIsNone(p.allowed_tools)  # default () → None → all permitted

    def test_to_dict(self) -> None:
        meta = AgentMeta(
            name="dict-agent",
            version="1.0.0",
            description="Dictionary test",
            tags=("tag1", "tag2"),
            capabilities=("cap1",),
            preferred_tools=("tool1",),
        )
        d = meta.to_dict()
        self.assertEqual(d["name"], "dict-agent")
        self.assertEqual(d["version"], "1.0.0")
        self.assertEqual(d["tags"], ["tag1", "tag2"])
        self.assertEqual(d["capabilities"], ["cap1"])
        self.assertEqual(d["preferred_tools"], ["tool1"])
        self.assertEqual(d["source_path"], None)

    def test_from_personality(self) -> None:
        p = Personality(
            name="test",
            description="A test personality",
            system_prompt="You are a test.",
            conversational_system_prompt="Chat.",
            allowed_tools=frozenset({"tool_a", "tool_b"}),
            model_override="test-model",
        )
        meta = AgentMeta.from_personality(p)
        self.assertEqual(meta.name, "test")
        self.assertEqual(meta.version, "1.0.0")  # default
        self.assertEqual(meta.description, "A test personality")
        self.assertEqual(meta.system_prompt, "You are a test.")
        self.assertEqual(meta.conversational_system_prompt, "Chat.")
        self.assertEqual(meta.model_override, "test-model")
        self.assertEqual(set(meta.preferred_tools), {"tool_a", "tool_b"})
        self.assertEqual(meta.tags, ("test",))
        self.assertEqual(meta.author, "Fiona")
        self.assertIsNone(meta.source_path)

    def test_from_personality_with_overrides(self) -> None:
        p = Personality(
            name="test",
            description="Original",
            system_prompt="Original prompt.",
        )
        meta = AgentMeta.from_personality(
            p,
            source_path="/tmp/test.md",
            version="2.0.0",
            tags=("custom", "tag"),
        )
        self.assertEqual(meta.version, "2.0.0")
        self.assertEqual(meta.tags, ("custom", "tag"))
        self.assertEqual(meta.source_path, "/tmp/test.md")

    def test_frozen_cannot_mutate(self) -> None:
        meta = AgentMeta(name="x", version="1.0", description="x")
        with self.assertRaises(AttributeError):
            meta.name = "y"  # type: ignore[misc]


class TestAgentMetaIntegration(unittest.TestCase):
    """Integration: PersonalityRegistry exposes AgentMeta for builtins."""

    def setUp(self) -> None:
        self._old_instance = PersonalityRegistry._instance  # type: ignore[attr-defined]
        PersonalityRegistry._instance = None  # type: ignore[attr-defined]

    def tearDown(self) -> None:
        PersonalityRegistry._instance = self._old_instance  # type: ignore[attr-defined]

    def test_builtins_have_agent_meta(self) -> None:
        reg = PersonalityRegistry(agent_dirs=[])  # don't scan disk
        meta = reg.get_agent_meta("general")
        self.assertEqual(meta.name, "general")
        self.assertEqual(meta.version, "1.0.0")
        self.assertIn("SYSTEM OPERATOR", meta.system_prompt)

    def test_all_builtins_have_agent_meta(self) -> None:
        reg = PersonalityRegistry(agent_dirs=[])
        metas = reg.list_agent_metas()
        names = {m.name for m in metas}
        self.assertEqual(
            names, {"general", "planner", "engineer", "analyst", "security", "controller"}
        )

    def test_agent_meta_can_produce_personality(self) -> None:
        reg = PersonalityRegistry(agent_dirs=[])
        meta = reg.get_agent_meta("planner")
        p = meta.to_personality()
        self.assertIsInstance(p, Personality)
        self.assertEqual(p.name, "planner")
        self.assertEqual(p.model_override, "qwen3:8b-en")
        expected_tools = frozenset({
            "seeondesk_list", "seeondesk_active", "fiona_status",
            "recall_search", "recall_remember",
        })
        self.assertEqual(p.allowed_tools, expected_tools)

    def test_register_agent_meta(self) -> None:
        from Agent import PersonalityRegistry

        reg = PersonalityRegistry(agent_dirs=[])
        meta = AgentMeta(
            name="custom",
            version="1.0.0",
            description="Custom agent",
            system_prompt="Custom prompt.",
            preferred_tools=("tool_x",),
        )
        reg.register_agent_meta(meta)
        self.assertEqual(reg.get_agent_meta("custom").name, "custom")
        # Should also be accessible as a Personality
        p = reg.get("custom")
        self.assertEqual(p.name, "custom")

    def test_register_agent_meta_overrides_builtin(self) -> None:
        reg = PersonalityRegistry(agent_dirs=[])
        meta = AgentMeta(
            name="general",
            version="2.0.0",
            description="Overridden general",
            system_prompt="Overridden prompt.",
        )
        reg.register_agent_meta(meta)
        self.assertEqual(reg.get_agent_meta("general").version, "2.0.0")
        p = reg.get("general")
        self.assertEqual(p.system_prompt, "Overridden prompt.")

    def test_get_missing_agent_meta_raises(self) -> None:
        reg = PersonalityRegistry(agent_dirs=[])
        with self.assertRaises(KeyError):
            reg.get_agent_meta("nonexistent")


if __name__ == "__main__":
    unittest.main()
