"""Tests for the Markdown agent file loader (agent_loader.py)."""

from __future__ import annotations

import os
import tempfile
import unittest

from Agent.agent_loader import parse_agent_file, discover_agents
from Agent.agent_meta import AgentMeta


class TestParseAgentFile(unittest.TestCase):
    """Parsing individual .md files with YAML front matter."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, content: str) -> str:
        path = os.path.join(self._dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.lstrip("\n"))
        return path

    def test_minimal_valid_agent(self) -> None:
        path = self._write("test.md", """\
---
name: test-agent
version: 1.0.0
description: A test agent
---

You are a test agent.
""")
        meta = parse_agent_file(path)
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta.name, "test-agent")
        self.assertEqual(meta.version, "1.0.0")
        self.assertEqual(meta.description, "A test agent")
        self.assertEqual(meta.system_prompt, "You are a test agent.")
        self.assertEqual(meta.author, "Fiona")  # default
        self.assertEqual(meta.tags, ())  # default
        self.assertEqual(meta.preferred_tools, ())  # default
        self.assertIsNone(meta.model_override)
        self.assertIsNotNone(meta.source_path)
        self.assertTrue(meta.source_path.endswith("test.md"))  # type: ignore[union-attr]

    def test_system_prompt_in_front_matter_overrides_body(self) -> None:
        path = self._write("override.md", """\
---
name: override-agent
version: 1.0.0
description: Override test
system_prompt: This is from front matter.
---

This is the body and should NOT be the system prompt.
""")
        meta = parse_agent_file(path)
        assert meta is not None
        self.assertEqual(meta.system_prompt, "This is from front matter.")

    def test_body_used_when_no_system_prompt(self) -> None:
        path = self._write("body.md", """\
---
name: body-agent
version: 1.0.0
description: Body test
---

This is the system prompt from the body.
It can span multiple lines.
""")
        meta = parse_agent_file(path)
        assert meta is not None
        self.assertEqual(meta.system_prompt, "This is the system prompt from the body.\nIt can span multiple lines.")

    def test_full_metadata(self) -> None:
        path = self._write("full.md", """\
---
name: full-agent
version: 2.1.0
description: Full featured agent
author: Test Author
tags: [ai, test, automation]
capabilities:
  - code-generation
  - system-analysis
supported_tasks:
  - Write Python code
  - Analyze system state
preferred_tools:
  - press
  - click
  - fiona_status
restrictions:
  - Never modify production
model_override: qwen3:8b-en
confidence_threshold: 0.9
dependencies:
  - skill-python
skills:
  - python
  - yaml
examples:
  - query: "Write hello world"
    response: "print('hello world')"
  - query: "Check status"
    response: "Running fiona_status"
---

System prompt.
""")
        meta = parse_agent_file(path)
        assert meta is not None
        self.assertEqual(meta.name, "full-agent")
        self.assertEqual(meta.version, "2.1.0")
        self.assertEqual(meta.description, "Full featured agent")
        self.assertEqual(meta.author, "Test Author")
        self.assertEqual(meta.tags, ("ai", "test", "automation"))
        self.assertEqual(meta.capabilities, ("code-generation", "system-analysis"))
        self.assertEqual(meta.supported_tasks, ("Write Python code", "Analyze system state"))
        self.assertEqual(meta.preferred_tools, ("press", "click", "fiona_status"))
        self.assertEqual(meta.restrictions, ("Never modify production",))
        self.assertEqual(meta.model_override, "qwen3:8b-en")
        self.assertEqual(meta.confidence_threshold, 0.9)
        self.assertEqual(meta.dependencies, ("skill-python",))
        self.assertEqual(meta.skills, ("python", "yaml"))
        self.assertEqual(len(meta.examples), 2)
        self.assertEqual(meta.examples[0]["query"], "Write hello world")
        self.assertEqual(meta.examples[0]["response"], "print('hello world')")
        self.assertEqual(meta.system_prompt, "System prompt.")

    def test_missing_name_returns_none(self) -> None:
        path = self._write("no_name.md", """\
---
version: 1.0.0
description: No name
---

Body.
""")
        self.assertIsNone(parse_agent_file(path))

    def test_missing_version_returns_none(self) -> None:
        path = self._write("no_ver.md", """\
---
name: no-ver
description: No version
---

Body.
""")
        self.assertIsNone(parse_agent_file(path))

    def test_missing_description_returns_none(self) -> None:
        path = self._write("no_desc.md", """\
---
name: no-desc
version: 1.0.0
---

Body.
""")
        self.assertIsNone(parse_agent_file(path))

    def test_empty_front_matter_returns_none(self) -> None:
        path = self._write("empty.md", """\
---
---

Body.
""")
        self.assertIsNone(parse_agent_file(path))

    def test_no_front_matter_uses_body_as_prompt(self) -> None:
        path = self._write("no_fm.md", """\
No front matter at all.
Just a body.
""")
        meta = parse_agent_file(path)
        self.assertIsNone(meta)  # no front matter → can't get name/version/description

    def test_invalid_yaml_returns_none(self) -> None:
        path = self._write("bad_yaml.md", """\
---
name: bad
version: 1.0.0
description: Bad YAML
invalid: [unclosed
---

Body.
""")
        self.assertIsNone(parse_agent_file(path))

    def test_conversational_prompt(self) -> None:
        path = self._write("conv.md", """\
---
name: conv-agent
version: 1.0.0
description: Conversational agent
conversational_prompt: This is the chat prompt.
---

System prompt.
""")
        meta = parse_agent_file(path)
        assert meta is not None
        self.assertEqual(meta.conversational_system_prompt, "This is the chat prompt.")
        self.assertEqual(meta.system_prompt, "System prompt.")

    def test_nonexistent_file_returns_none(self) -> None:
        self.assertIsNone(parse_agent_file("/nonexistent/path.md"))

    def test_empty_preferred_tools_list(self) -> None:
        path = self._write("empty_tools.md", """\
---
name: empty-tools
version: 1.0.0
description: No preferred tools
preferred_tools: []
---

Body.
""")
        meta = parse_agent_file(path)
        assert meta is not None
        self.assertEqual(meta.preferred_tools, ())  # () means all tools permitted


class TestDiscoverAgents(unittest.TestCase):
    """Directory scanning for agent files."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, subdir: str, name: str, content: str) -> str:
        d = os.path.join(self._dir, subdir)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content.lstrip("\n"))
        return path

    def test_discover_single_agent(self) -> None:
        self._write("", "hello.md", """\
---
name: hello
version: 1.0.0
description: Hello agent
---

Hello.
""")
        agents = discover_agents(self._dir)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "hello")

    def test_discover_multiple_agents(self) -> None:
        self._write("", "a.md", """\
---
name: agent-a
version: 1.0.0
description: Agent A
---

A.
""")
        self._write("", "b.md", """\
---
name: agent-b
version: 1.0.0
description: Agent B
---

B.
""")
        agents = discover_agents(self._dir)
        self.assertEqual(len(agents), 2)
        names = {a.name for a in agents}
        self.assertEqual(names, {"agent-a", "agent-b"})

    def test_discover_skips_readme(self) -> None:
        self._write("", "README.md", "# Just docs")
        self._write("", "real.md", """\
---
name: real-agent
version: 1.0.0
description: A real agent
---

Real.
""")
        agents = discover_agents(self._dir)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "real-agent")

    def test_discover_recursive_subdirectories(self) -> None:
        self._write("sub", "deep.md", """\
---
name: deep-agent
version: 1.0.0
description: Deep agent
---

Deep.
""")
        agents = discover_agents(self._dir)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "deep-agent")

    def test_discover_skips_invalid_agents(self) -> None:
        self._write("", "valid.md", """\
---
name: valid-agent
version: 1.0.0
description: Valid
---

OK.
""")
        self._write("", "invalid.md", """\
---
name:  # missing name
version: 1.0.0
description: Invalid
---

Bad.
""")
        agents = discover_agents(self._dir)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "valid-agent")

    def test_discover_nonexistent_directory(self) -> None:
        agents = discover_agents("/nonexistent/path")
        self.assertEqual(agents, [])

    def test_discover_empty_directory(self) -> None:
        agents = discover_agents(self._dir)
        self.assertEqual(agents, [])

    def test_load_agent_alias(self) -> None:
        from Agent.agent_loader import load_agent

        path = self._write("", "alias.md", """\
---
name: alias-agent
version: 1.0.0
description: Alias test
---

Body.
""")
        meta = load_agent(path)
        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta.name, "alias-agent")


class TestBuiltinAgentsOnDisk(unittest.TestCase):
    """Verify that the builtin agent .md files in agents/builtins/ load correctly."""

    def _project_root(self) -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_builtins_directory_exists(self) -> None:
        builtins_dir = os.path.join(self._project_root(), "agents", "builtins")
        self.assertTrue(os.path.isdir(builtins_dir))

    def test_all_six_builtins_exist(self) -> None:
        builtins_dir = os.path.join(self._project_root(), "agents", "builtins")
        agents = discover_agents(builtins_dir)
        names = {a.name for a in agents}
        expected = {"general", "planner", "engineer", "analyst", "security", "controller"}
        self.assertEqual(names, expected)

    def test_builtin_general_matches_hardcoded(self) -> None:
        from Agent.personality import PersonalityRegistry

        reg = PersonalityRegistry(agent_dirs=[])
        hardcoded = reg.get_agent_meta("general")
        # Load from disk
        builtins_dir = os.path.join(self._project_root(), "agents", "builtins")
        agents = discover_agents(builtins_dir)
        disk = {a.name: a for a in agents}
        self.assertIn("general", disk)
        # The disk version should have the same core identity
        self.assertEqual(disk["general"].name, hardcoded.name)
        self.assertEqual(disk["general"].description, hardcoded.description)

    def test_disk_version_can_produce_personality(self) -> None:
        builtins_dir = os.path.join(self._project_root(), "agents", "builtins")
        agents = discover_agents(builtins_dir)
        for agent in agents:
            p = agent.to_personality()
            self.assertEqual(p.name, agent.name)
            self.assertEqual(p.system_prompt, agent.system_prompt)
            # Verify tool mapping
            if agent.preferred_tools:
                self.assertEqual(p.allowed_tools, frozenset(agent.preferred_tools))
            else:
                self.assertIsNone(p.allowed_tools)


if __name__ == "__main__":
    unittest.main()
