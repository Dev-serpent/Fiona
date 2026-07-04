"""Tests for Agent configuration system (AgentConfig, load_agent_config)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from Agent.config import AgentConfig, load_agent_config


class TestAgentConfig(unittest.TestCase):
    """AgentConfig dataclass defaults and conversions."""

    def test_defaults_match_hardcoded(self) -> None:
        """Verify defaults match the current hardcoded values."""
        cfg = AgentConfig()
        self.assertEqual(cfg.ollama_base_url, "http://localhost:11434/api")
        self.assertEqual(cfg.default_model, "qwen3:8b-en")
        self.assertEqual(cfg.llm_timeout_seconds, 120.0)
        self.assertEqual(cfg.llm_temperature, 0.3)
        self.assertEqual(cfg.llm_max_tokens, 2048)
        self.assertEqual(cfg.parallel_by_default, False)
        self.assertEqual(cfg.max_sub_agents, 5)
        self.assertEqual(cfg.max_turns_per_sub_agent, 10)
        self.assertEqual(cfg.max_plan_retries, 2)
        self.assertEqual(cfg.context_max_tokens, 2048)
        self.assertEqual(cfg.default_agent, "general")
        self.assertEqual(cfg.enable_hot_reload, False)
        self.assertEqual(cfg.hot_reload_poll_interval, 5.0)

    def test_to_foreman_config(self) -> None:
        cfg = AgentConfig(
            parallel_by_default=True,
            max_sub_agents=3,
            max_turns_per_sub_agent=8,
            max_plan_retries=1,
            context_max_tokens=1024,
            default_agent="planner",
        )
        fc = cfg.to_foreman_config()
        from Agent.orchestration import ForemanConfig

        self.assertIsInstance(fc, ForemanConfig)
        self.assertEqual(fc.parallel_by_default, True)
        self.assertEqual(fc.max_sub_agents, 3)
        self.assertEqual(fc.max_turns_per_sub_agent, 8)
        self.assertEqual(fc.max_plan_retries, 1)
        self.assertEqual(fc.context_max_tokens, 1024)
        self.assertEqual(fc.default_personality, "planner")

    def test_to_dict_roundtrip(self) -> None:
        cfg = AgentConfig(default_model="custom-model", enable_hot_reload=True)
        d = cfg.to_dict()
        self.assertEqual(d["default_model"], "custom-model")
        self.assertEqual(d["enable_hot_reload"], True)
        self.assertEqual(d["ollama_base_url"], "http://localhost:11434/api")

    def test_frozen_cannot_mutate(self) -> None:
        cfg = AgentConfig()
        with self.assertRaises(AttributeError):
            cfg.default_model = "other"  # type: ignore[misc]

    def test_agent_dirs_default_resolved(self) -> None:
        """Default agent_dirs should contain the project's agents/ directory."""
        cfg = AgentConfig()
        if cfg.agent_dirs:
            # At least one dir, and it should point to a real agents/ folder
            self.assertTrue(any("agents" in d for d in cfg.agent_dirs))


class TestLoadAgentConfig(unittest.TestCase):
    """Config file loading with YAML and env-var overrides."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = Path(self._tmp.name)
        self._saved_env: dict[str, str] = {}
        # Save env vars we might override
        for key in os.environ:
            if key.startswith("FIONA_AGENT_"):
                self._saved_env[key] = os.environ[key]

    def tearDown(self) -> None:
        # Restore env vars
        for key in list(os.environ.keys()):
            if key.startswith("FIONA_AGENT_"):
                del os.environ[key]
        os.environ.update(self._saved_env)
        self._tmp.cleanup()

    def test_load_defaults_when_no_file(self) -> None:
        """With no config file and no env vars, should return defaults."""
        cfg = load_agent_config(path="/nonexistent/config.yaml")
        self.assertEqual(cfg.default_model, "qwen3:8b-en")
        self.assertEqual(cfg.parallel_by_default, False)

    def test_load_from_yaml(self) -> None:
        path = self._dir / "agent.yaml"
        path.write_text("""\
default_model: "custom-model"
max_sub_agents: 10
enable_hot_reload: true
""")
        cfg = load_agent_config(path=path)
        self.assertEqual(cfg.default_model, "custom-model")
        self.assertEqual(cfg.max_sub_agents, 10)
        self.assertEqual(cfg.enable_hot_reload, True)
        # Fields not in YAML should still be defaults
        self.assertEqual(cfg.ollama_base_url, "http://localhost:11434/api")

    def test_env_var_overrides(self) -> None:
        os.environ["FIONA_AGENT_DEFAULT_MODEL"] = "env-model"
        os.environ["FIONA_AGENT_MAX_SUB_AGENTS"] = "8"
        os.environ["FIONA_AGENT_ENABLE_HOT_RELOAD"] = "true"
        os.environ["FIONA_AGENT_PARALLEL_BY_DEFAULT"] = "1"

        cfg = load_agent_config(path="/nonexistent")
        self.assertEqual(cfg.default_model, "env-model")
        self.assertEqual(cfg.max_sub_agents, 8)
        self.assertEqual(cfg.enable_hot_reload, True)
        self.assertEqual(cfg.parallel_by_default, True)

    def test_env_var_overrides_yaml(self) -> None:
        """Env vars should take precedence over YAML values."""
        path = self._dir / "agent.yaml"
        path.write_text("""\
default_model: "yaml-model"
max_sub_agents: 3
""")
        os.environ["FIONA_AGENT_DEFAULT_MODEL"] = "env-wins"

        cfg = load_agent_config(path=path)
        self.assertEqual(cfg.default_model, "env-wins")  # env overrides YAML
        self.assertEqual(cfg.max_sub_agents, 3)  # from YAML, not overridden

    def test_custom_env_prefix(self) -> None:
        os.environ["MY_PREFIX_DEFAULT_MODEL"] = "prefix-model"
        cfg = load_agent_config(
            path="/nonexistent",
            env_prefix="MY_PREFIX_",
        )
        self.assertEqual(cfg.default_model, "prefix-model")

    def test_partial_yaml_merges_with_defaults(self) -> None:
        path = self._dir / "agent.yaml"
        path.write_text("default_model: partial")
        cfg = load_agent_config(path=path)
        self.assertEqual(cfg.default_model, "partial")
        self.assertEqual(cfg.llm_temperature, 0.3)  # default

    def test_invalid_env_value_ignored(self) -> None:
        """Invalid bool values should not crash."""
        os.environ["FIONA_AGENT_ENABLE_HOT_RELOAD"] = "not-a-bool"
        cfg = load_agent_config(path="/nonexistent")
        # Should not raise; invalid bools become False
        self.assertIsInstance(cfg, AgentConfig)

    def test_agent_dirs_from_yaml(self) -> None:
        path = self._dir / "agent.yaml"
        path.write_text("""\
agent_dirs:
  - "/custom/path"
  - "/another/path"
""")
        cfg = load_agent_config(path=path)
        self.assertIn("/custom/path", cfg.agent_dirs)
        self.assertIn("/another/path", cfg.agent_dirs)

    def test_chat_store_path_default(self) -> None:
        cfg = load_agent_config(path="/nonexistent")
        self.assertIn("chat.db", cfg.chat_store_path)

    def test_foreman_config_roundtrip(self) -> None:
        """AgentConfig -> ForemanConfig -> back via dict should preserve values."""
        from Agent.orchestration import ForemanConfig

        cfg = AgentConfig(
            parallel_by_default=True,
            max_sub_agents=7,
            default_agent="engineer",
        )
        fc = ForemanConfig.from_agent_config(cfg)
        self.assertEqual(fc.parallel_by_default, True)
        self.assertEqual(fc.max_sub_agents, 7)
        self.assertEqual(fc.default_personality, "engineer")

    def test_foreman_agent_from_agent_config(self) -> None:
        """ForemanAgent.from_agent_config should produce a working agent."""
        from Agent import PersonalityRegistry

        reg = PersonalityRegistry(agent_dirs=[])
        cfg = AgentConfig(parallel_by_default=True, max_sub_agents=3)

        # Mock client that doesn't call real Ollama
        from unittest.mock import MagicMock
        from Agent.ollama import OllamaClient

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = '{"classification": "simple", "reason": "test"}'

        from Agent.orchestration import ForemanAgent

        agent = ForemanAgent.from_agent_config(
            client=mock_client,
            registry=reg,
            agent_config=cfg,
        )
        self.assertIsNotNone(agent)
        self.assertEqual(agent._config.parallel_by_default, True)
        self.assertEqual(agent._config.max_sub_agents, 3)


class TestAgentConfigDefaultFile(unittest.TestCase):
    """Verify the shipped config/agent.yaml file loads correctly."""

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def test_default_config_file_exists(self) -> None:
        path = self._project_root() / "config" / "agent.yaml"
        self.assertTrue(path.is_file(), f"Expected config file at {path}")

    def test_default_config_loads(self) -> None:
        path = self._project_root() / "config" / "agent.yaml"
        cfg = load_agent_config(path=path)
        self.assertEqual(cfg.default_model, "qwen3:8b-en")
        self.assertEqual(cfg.ollama_base_url, "http://localhost:11434/api")
        self.assertEqual(cfg.default_agent, "general")
        self.assertFalse(cfg.enable_hot_reload)


if __name__ == "__main__":
    unittest.main()
