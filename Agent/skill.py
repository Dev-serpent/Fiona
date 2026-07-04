"""Skill System — reusable composed capabilities for Fiona agents.

Skills are named collections of tools, instructions, and metadata that
agents can compose into their capabilities.  Unlike agents, skills are
not full personalities — they are building blocks.

A skill:

- has a name, description, version
- declares which tools it requires
- provides an instruction/prompt template
- can be loaded from YAML files
- can be shared across multiple agents (via ``AgentMeta.skills``)

Usage::

    registry = SkillRegistry()
    skill = Skill(name="web-search", description="Search the web",
                  tools=["web_search", "web_fetch"],
                  instruction="Use the web_search tool to find information.")
    registry.register(skill)
    loaded = registry.get("web-search")
    tools = registry.get_required_tools(["web-search", "recent-files"])
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ======================================================================
# 1. Skill dataclass
# ======================================================================


@dataclass(frozen=True)
class Skill:
    """A reusable composed capability.

    Attributes:
        name: Unique skill identifier.
        description: Human-readable description.
        version: Semantic version string.
        tools: List of tool names this skill requires.
        instruction: Prompt instruction template for the skill.
        tags: Optional list of tags for discovery/filtering.
        metadata: Optional additional key-value metadata.
    """

    name: str
    description: str = ""
    version: str = "1.0.0"
    tools: list[str] = field(default_factory=list)
    instruction: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ======================================================================
# 2. YAML loader
# ======================================================================


def load_skill_from_yaml(path: str | Path) -> Skill | None:
    """Parse a single YAML skill file and return a ``Skill``.

    The file must contain a YAML dictionary with at least a ``name``
    field.  All other fields are optional.

    Returns:
        A ``Skill``, or ``None`` if the file cannot be parsed.
    """
    import yaml

    path = Path(path).expanduser().resolve()
    if not path.is_file():
        logger.warning("Skill file not found: %s", path)
        return None

    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as exc:
        logger.warning("Failed to parse skill file %s: %s", path, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Skill file %s does not contain a YAML dict", path)
        return None

    name = data.get("name")
    if not name:
        logger.warning("Skill file %s has no 'name' field", path)
        return None

    return Skill(
        name=str(name),
        description=str(data.get("description", "")),
        version=str(data.get("version", "1.0.0")),
        tools=list(data.get("tools", [])),
        instruction=str(data.get("instruction", "")),
        tags=list(data.get("tags", [])),
        metadata=dict(data.get("metadata", {})),
    )


def discover_skills(skill_dir: str | Path) -> list[Skill]:
    """Scan a directory for ``.yaml``/``.yml`` skill files.

    Args:
        skill_dir: Directory path to scan.

    Returns:
        List of parsed ``Skill`` objects (files that fail parsing are
        skipped with a warning).
    """
    skill_dir = Path(skill_dir).expanduser().resolve()
    if not skill_dir.is_dir():
        logger.debug("Skill directory not found: %s", skill_dir)
        return []

    skills: list[Skill] = []
    for entry in sorted(skill_dir.iterdir()):
        if entry.suffix.lower() in (".yaml", ".yml"):
            skill = load_skill_from_yaml(entry)
            if skill is not None:
                skills.append(skill)
    return skills


# ======================================================================
# 3. SkillRegistry
# ======================================================================


class SkillRegistry:
    """Central registry for reusable skills.

    Supports registration from code or from YAML files, with
    directory discovery and introspection queries.
    """

    def __init__(self, skill_dirs: list[str] | None = None) -> None:
        """
        Args:
            skill_dirs: Optional list of directories to auto-discover
                skill YAML files from.  If ``None``, defaults to the
                project ``skills/`` directory.
        """
        self._skills: dict[str, Skill] = {}
        self._event_bus: Any = None

        if skill_dirs is None:
            base = Path(__file__).resolve().parent.parent
            default_dir = base / "skills"
            if default_dir.is_dir():
                skill_dirs = [str(default_dir)]

        if skill_dirs:
            for d in skill_dirs:
                self.discover(d)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, skill: Skill) -> None:
        """Register a skill.

        Args:
            skill: The skill to register.

        Raises:
            ValueError: If a skill with the same name is already
                registered.
        """
        if not skill.name:
            raise ValueError("Skill name must be non-empty")
        if skill.name in self._skills:
            raise ValueError(
                f"Skill {skill.name!r} is already registered "
                f"(version {self._skills[skill.name].version})"
            )
        self._skills[skill.name] = skill

    def register_or_replace(self, skill: Skill) -> None:
        """Register or update a skill without raising on duplicates."""
        self._skills[skill.name] = skill

    def discover(self, skill_dir: str | Path) -> int:
        """Scan a directory and register any skill YAML files found.

        Args:
            skill_dir: Directory containing ``.yaml``/``.yml`` skill files.

        Returns:
            Number of skills successfully registered.
        """
        count = 0
        for skill in discover_skills(skill_dir):
            try:
                self.register_or_replace(skill)
                count += 1
            except Exception as exc:
                logger.warning("Failed to register skill %r: %s", skill.name, exc)
        logger.info("SkillRegistry: discovered %d skills from %s", count, skill_dir)
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name.

        Returns:
            The skill, or ``None`` if not found.
        """
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        """Return all registered skills, sorted by name."""
        return sorted(self._skills.values(), key=lambda s: s.name)

    def search(self, query: str) -> list[Skill]:
        """Search skills by name, description, or tags.

        Args:
            query: Free-text search string.

        Returns:
            Matching skills (case-insensitive substring match).
        """
        q = query.lower()
        results: list[Skill] = []
        for skill in self._skills.values():
            if (
                q in skill.name.lower()
                or q in skill.description.lower()
                or any(q in tag.lower() for tag in skill.tags)
            ):
                results.append(skill)
        return results

    def list_by_tool(self, tool_name: str) -> list[Skill]:
        """Return all skills that require the given tool."""
        return [
            skill for skill in self._skills.values() if tool_name in skill.tools
        ]

    def get_required_tools(self, skill_names: list[str]) -> set[str]:
        """Return the union of all tools required by the named skills.

        Args:
            skill_names: List of skill names.

        Returns:
            Set of tool names.
        """
        tools: set[str] = set()
        for name in skill_names:
            skill = self.get(name)
            if skill is not None:
                tools.update(skill.tools)
        return tools

    def remove(self, name: str) -> bool:
        """Remove a skill from the registry.

        Returns:
            ``True`` if the skill existed.
        """
        return self._skills.pop(name, None) is not None

    def count(self) -> int:
        """Return the number of registered skills."""
        return len(self._skills)

    # ------------------------------------------------------------------
    # Tool integration
    # ------------------------------------------------------------------

    def get_tool_suggestions(self, agent_tools: list[str]) -> list[Skill]:
        """Return skills that leverage tools the agent already has.

        This helps suggest relevant skills to an agent based on its
        existing tool set.

        Args:
            agent_tools: List of tool names the agent has.

        Returns:
            Skills sorted by most tools matched.
        """
        agent_set = set(agent_tools)
        scored: list[tuple[Skill, int]] = []
        for skill in self._skills.values():
            overlap = len(agent_set & set(skill.tools))
            if overlap > 0:
                scored.append((skill, overlap))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scored]

    # ------------------------------------------------------------------
    # Event bus
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: Any) -> None:
        """Set the event bus for publishing skill lifecycle events."""
        self._event_bus = event_bus


__all__ = [
    "Skill",
    "SkillRegistry",
    "discover_skills",
    "load_skill_from_yaml",
]
