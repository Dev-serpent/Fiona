"""Tests for the Skill system (Phase 8: Skills & Tool Registry)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yaml

from Agent.skill import (
    Skill,
    SkillRegistry,
    discover_skills,
    load_skill_from_yaml,
)


# ======================================================================
# 1. Skill dataclass
# ======================================================================


class TestSkill:
    def test_create_basic(self):
        skill = Skill(name="test-skill", description="A test")
        assert skill.name == "test-skill"
        assert skill.description == "A test"
        assert skill.version == "1.0.0"
        assert skill.tools == []
        assert skill.instruction == ""
        assert skill.tags == []
        assert skill.metadata == {}

    def test_create_full(self):
        skill = Skill(
            name="full-skill",
            description="Full",
            version="2.0.0",
            tools=["tool_a", "tool_b"],
            instruction="Use tool_a first",
            tags=["tag1", "tag2"],
            metadata={"key": "val"},
        )
        assert skill.tools == ["tool_a", "tool_b"]
        assert skill.instruction == "Use tool_a first"
        assert skill.tags == ["tag1", "tag2"]
        assert skill.metadata == {"key": "val"}

    def test_immutable(self):
        skill = Skill(name="immutable", description="Can't change")
        with pytest.raises((AttributeError, TypeError)):
            skill.name = "new-name"  # type: ignore[misc]


# ======================================================================
# 2. YAML loading
# ======================================================================


class TestLoadSkillFromYaml:
    def test_load_valid(self, tmp_path):
        path = tmp_path / "test-skill.yaml"
        data = {
            "name": "from-yaml",
            "description": "Loaded from YAML",
            "version": "1.2.0",
            "tools": ["tool_a"],
            "instruction": "Do the thing",
            "tags": ["test"],
            "metadata": {"source": "yaml"},
        }
        path.write_text(yaml.dump(data))
        skill = load_skill_from_yaml(path)
        assert skill is not None
        assert skill.name == "from-yaml"
        assert skill.version == "1.2.0"
        assert skill.tools == ["tool_a"]
        assert skill.metadata["source"] == "yaml"

    def test_load_minimal(self, tmp_path):
        path = tmp_path / "minimal.yaml"
        path.write_text(yaml.dump({"name": "minimal"}))
        skill = load_skill_from_yaml(path)
        assert skill is not None
        assert skill.name == "minimal"
        assert skill.version == "1.0.0"
        assert skill.tools == []

    def test_file_not_found(self):
        skill = load_skill_from_yaml("/nonexistent/path.yaml")
        assert skill is None

    def test_invalid_yaml(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("{ invalid: yaml: broken")
        skill = load_skill_from_yaml(path)
        assert skill is None

    def test_empty_dict(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("{}")
        skill = load_skill_from_yaml(path)
        assert skill is None  # no name field

    def test_not_a_dict(self, tmp_path):
        path = tmp_path / "list.yaml"
        path.write_text(yaml.dump(["a", "b"]))
        skill = load_skill_from_yaml(path)
        assert skill is None


class TestDiscoverSkills:
    def test_discovers_yaml_files(self, tmp_path):
        for name in ("a.yaml", "b.yaml", "c.yml"):
            (tmp_path / name).write_text(yaml.dump({"name": name.replace(".", "-")}))
        skills = discover_skills(tmp_path)
        assert len(skills) == 3

    def test_skips_non_yaml(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not a skill")
        (tmp_path / "skill.yaml").write_text(yaml.dump({"name": "real-skill"}))
        skills = discover_skills(tmp_path)
        assert len(skills) == 1

    def test_skips_invalid_files(self, tmp_path):
        (tmp_path / "good.yaml").write_text(yaml.dump({"name": "good"}))
        (tmp_path / "bad.yaml").write_text("::: broken")
        skills = discover_skills(tmp_path)
        assert len(skills) == 1

    def test_empty_directory(self, tmp_path):
        skills = discover_skills(tmp_path / "empty")
        assert skills == []

    def test_nonexistent_directory(self):
        skills = discover_skills("/nonexistent/path")
        assert skills == []


# ======================================================================
# 3. SkillRegistry
# ======================================================================


class TestSkillRegistry:
    @pytest.fixture
    def registry(self):
        return SkillRegistry(skill_dirs=[])  # empty — no auto-discover

    def test_register(self, registry):
        skill = Skill(name="test", description="test skill")
        registry.register(skill)
        assert registry.count() == 1
        assert registry.get("test") is skill

    def test_register_duplicate_raises(self, registry):
        registry.register(Skill(name="dup", description="first"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(Skill(name="dup", description="second"))

    def test_register_empty_name_raises(self, registry):
        with pytest.raises(ValueError, match="non-empty"):
            registry.register(Skill(name="", description="empty"))

    def test_register_or_replace(self, registry):
        registry.register_or_replace(Skill(name="x", description="v1"))
        registry.register_or_replace(Skill(name="x", description="v2"))
        assert registry.count() == 1
        assert registry.get("x").description == "v2"

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_empty(self, registry):
        assert registry.list() == []

    def test_list_sorted(self, registry):
        registry.register(Skill(name="z", description="last"))
        registry.register(Skill(name="a", description="first"))
        names = [s.name for s in registry.list()]
        assert names == ["a", "z"]

    def test_remove_existing(self, registry):
        registry.register(Skill(name="tmp", description="temp"))
        assert registry.remove("tmp") is True
        assert registry.count() == 0

    def test_remove_nonexistent(self, registry):
        assert registry.remove("nonexistent") is False

    def test_search_by_name(self, registry):
        registry.register(Skill(name="web-search", description="search tool"))
        results = registry.search("web")
        assert len(results) == 1

    def test_search_by_description(self, registry):
        registry.register(Skill(name="fetcher", description="fetch web content"))
        results = registry.search("content")
        assert len(results) == 1

    def test_search_by_tag(self, registry):
        registry.register(
            Skill(name="analyser", description="data tool", tags=["data", "stats"])
        )
        results = registry.search("stats")
        assert len(results) == 1

    def test_search_no_match(self, registry):
        registry.register(Skill(name="a", description="alpha"))
        results = registry.search("omega")
        assert results == []

    def test_list_by_tool(self, registry):
        s1 = Skill(name="web", description="w", tools=["search", "fetch"])
        s2 = Skill(name="code", description="c", tools=["read", "grep"])
        s3 = Skill(name="other", description="o", tools=["search"])
        registry.register(s1)
        registry.register(s2)
        registry.register(s3)
        result = registry.list_by_tool("search")
        assert len(result) == 2
        assert {s.name for s in result} == {"web", "other"}

    def test_get_required_tools(self, registry):
        registry.register(Skill(name="a", description="a", tools=["t1", "t2"]))
        registry.register(Skill(name="b", description="b", tools=["t2", "t3"]))
        tools = registry.get_required_tools(["a", "b"])
        assert tools == {"t1", "t2", "t3"}

    def test_get_required_tools_missing_skill(self, registry):
        registry.register(Skill(name="a", description="a", tools=["t1"]))
        tools = registry.get_required_tools(["a", "nonexistent"])
        assert tools == {"t1"}


class TestSkillRegistryAutoDiscover:
    def test_auto_discover_default_dir(self):
        """When no skill_dirs given, SkillRegistry should scan skills/."""
        import tempfile
        from pathlib import Path

        # Temporarily patch the default path resolution
        with patch("Agent.skill.Path") as MockPath:
            mock_base = MagicMock()
            mock_default = MagicMock()
            mock_default.is_dir.return_value = True
            mock_default.__iter__.return_value = iter([])
            mock_base.parent.parent.__truediv__.return_value = mock_default
            MockPath.__file__ = MockPath  # type: ignore
            MockPath.resolve.return_value = mock_base

            registry = SkillRegistry(skill_dirs=None)
            assert registry.count() == 0  # no files in mock dir

    def test_discover_from_directory(self, tmp_path):
        # Create skill files
        (tmp_path / "a.yaml").write_text(
            __import__("yaml").dump({"name": "alpha", "description": "first"})
        )
        (tmp_path / "b.yaml").write_text(
            __import__("yaml").dump({"name": "beta", "description": "second"})
        )
        registry = SkillRegistry(skill_dirs=[str(tmp_path)])
        assert registry.count() == 2
        assert registry.get("alpha") is not None
        assert registry.get("beta") is not None

    def test_discover_skips_bad_files(self, tmp_path):
        (tmp_path / "good.yaml").write_text(
            __import__("yaml").dump({"name": "good"})
        )
        (tmp_path / "bad.yaml").write_text("::: broken")
        registry = SkillRegistry(skill_dirs=[str(tmp_path)])
        assert registry.count() == 1


class TestSkillRegistryToolIntegration:
    @pytest.fixture
    def registry(self):
        return SkillRegistry(skill_dirs=[])

    def test_get_tool_suggestions(self, registry):
        registry.register(
            Skill(name="web", tools=["search", "fetch"], description="web tools")
        )
        registry.register(
            Skill(name="code", tools=["read", "grep"], description="code tools")
        )
        registry.register(
            Skill(name="hybrid", tools=["search", "read"], description="hybrid")
        )

        suggestions = registry.get_tool_suggestions(["search", "fetch"])
        assert len(suggestions) == 2
        # web should be first (matches 2 tools), hybrid second (matches 1)
        assert suggestions[0].name == "web"
        assert suggestions[1].name == "hybrid"

    def test_get_tool_suggestions_no_match(self, registry):
        registry.register(Skill(name="code", tools=["read"], description="code"))
        suggestions = registry.get_tool_suggestions(["search"])
        assert suggestions == []

    def test_set_event_bus(self):
        registry = SkillRegistry()
        bus = MagicMock()
        registry.set_event_bus(bus)
        assert registry._event_bus is bus


# ======================================================================
# 4. Integration: skills directory parsing
# ======================================================================


class TestBuiltinSkills:
    def test_web_research_skill(self):
        """Verify the built-in web-research skill is valid."""
        skill = load_skill_from_yaml(
            "/home/Dhruv/Documents/Projects/Fiona/skills/web-research.yaml"
        )
        assert skill is not None
        assert skill.name == "web-research"
        assert "web_search" in skill.tools
        assert "web_fetch" in skill.tools
        assert "research" in skill.tags

    def test_code_analysis_skill(self):
        skill = load_skill_from_yaml(
            "/home/Dhruv/Documents/Projects/Fiona/skills/code-analysis.yaml"
        )
        assert skill is not None
        assert skill.name == "code-analysis"
        assert "read_file" in skill.tools
        assert "grep_search" in skill.tools

    def test_data_analysis_skill(self):
        skill = load_skill_from_yaml(
            "/home/Dhruv/Documents/Projects/Fiona/skills/data-analysis.yaml"
        )
        assert skill is not None
        assert skill.name == "data-analysis"
        assert "execute_python" in skill.tools
        assert "statistics" in skill.tags
