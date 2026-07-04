"""Markdown agent file loader — parses YAML front matter into ``AgentMeta``.

This module discovers and loads agent definitions from ``.md`` files with
YAML front matter (delimited by ``---``).  An agent Markdown file looks like::

    ---
    name: my-agent
    version: 1.0.0
    description: Example agent
    ---

    The rest of the file is the default system prompt.

Adding an agent requires **no code changes** — simply place a ``.md`` file
in the ``agents/`` directory (or any configured agent directory).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from Agent.agent_meta import AgentMeta

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False

log = logging.getLogger(__name__)

# ── Public API ────────────────────────────────────────────────────────


def parse_agent_file(filepath: str | Path) -> AgentMeta | None:
    """Parse a single Markdown agent file into an ``AgentMeta``.

    Returns ``None`` (and logs a warning) if the file cannot be parsed,
    has invalid YAML, or is missing required fields.
    """
    path = Path(filepath)
    if not path.is_file():
        log.warning("Agent file not found: %s", path)
        return None

    raw = path.read_text(encoding="utf-8")
    meta_dict, body = _split_front_matter(raw)

    if meta_dict is None:
        log.warning("No valid YAML front matter in %s", path)
        return None

    meta_dict["source_path"] = str(path.resolve())

    # If no system_prompt in front matter, use the file body
    if "system_prompt" not in meta_dict or not meta_dict["system_prompt"]:
        meta_dict["system_prompt"] = body.strip()

    return _dict_to_agent_meta(meta_dict, path)


def discover_agents(directory: str | Path) -> list[AgentMeta]:
    """Scan *directory* recursively for Markdown agent files.

    Returns a list of successfully parsed ``AgentMeta`` objects.  Files
    that fail to parse are logged and skipped (graceful degradation).
    """
    root = Path(directory)
    if not root.is_dir():
        log.debug("Agent directory does not exist: %s", root)
        return []

    agents: list[AgentMeta] = []
    for entry in sorted(root.rglob("*.md")):
        # Skip README files which are documentation, not agents
        if entry.name.upper() == "README.md":
            continue
        meta = parse_agent_file(entry)
        if meta is not None:
            agents.append(meta)

    return agents


def load_agent(filepath: str | Path) -> AgentMeta | None:
    """Convenience alias for ``parse_agent_file()``."""
    return parse_agent_file(filepath)


# ── Internal helpers ──────────────────────────────────────────────────


def _split_front_matter(raw: str) -> tuple[dict[str, Any] | None, str]:
    """Split a Markdown file into YAML front matter dict and body text.

    Returns ``(front_matter_dict, body_string)``.  If the file has no
    valid ``---``-delimited front matter, the first element is ``None``
    and *body* is the entire file content.
    """
    stripped = raw.lstrip()
    if not stripped.startswith("---"):
        return None, stripped

    # Find the closing ---
    end_idx = stripped.find("---", 3)
    if end_idx == -1:
        return None, stripped

    yaml_block = stripped[3:end_idx]
    body = stripped[end_idx + 3 :].strip()

    if not _YAML_AVAILABLE:
        log.error(
            "PyYAML is required to parse agent markdown files. "
            "Install it with: pip install PyYAML"
        )
        return None, body

    try:
        data = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        log.warning("YAML parse error in front matter: %s", exc)
        return None, body

    if not isinstance(data, dict):
        log.warning("YAML front matter did not produce a dict (got %s)", type(data).__name__)
        return None, body

    return data, body


def _dict_to_agent_meta(data: dict[str, Any], path: Path) -> AgentMeta | None:
    """Convert a parsed YAML dict into an ``AgentMeta``, validating required fields."""
    # ── Required fields ───────────────────────────────────────────────
    name = _ensure_str(data, "name")
    version = _ensure_str(data, "version")
    description = _ensure_str(data, "description")

    if not name:
        log.warning("Agent in %s is missing required field 'name'", path)
        return None
    if not version:
        log.warning("Agent '%s' (%s) is missing required field 'version'", name, path)
        return None
    if not description:
        log.warning("Agent '%s' (%s) is missing required field 'description'", name, path)
        return None

    # ── Optional list fields ──────────────────────────────────────────
    tags = _ensure_tuple_str(data, "tags")
    capabilities = _ensure_tuple_str(data, "capabilities")
    supported_tasks = _ensure_tuple_str(data, "supported_tasks")
    preferred_tools = _ensure_tuple_str(data, "preferred_tools")
    restrictions = _ensure_tuple_str(data, "restrictions")
    dependencies = _ensure_tuple_str(data, "dependencies")
    skills = _ensure_tuple_str(data, "skills")

    # ── Examples ──────────────────────────────────────────────────────
    examples_raw = data.get("examples", [])
    if not isinstance(examples_raw, (list, tuple)):
        examples_raw = []
    examples: tuple[dict[str, str], ...] = ()
    for item in examples_raw:
        if isinstance(item, dict):
            q = str(item.get("query", ""))
            r = str(item.get("response", ""))
            examples = examples + ({"query": q, "response": r},)

    # ── Optional scalar fields ────────────────────────────────────────
    system_prompt = _ensure_str(data, "system_prompt", allow_empty=True)
    conversational_prompt = _ensure_str(data, "conversational_prompt")
    model_override = _ensure_str(data, "model_override")
    author = _ensure_str(data, "author") or "Fiona"

    confidence_raw = data.get("confidence_threshold", 0.7)
    try:
        confidence = float(confidence_raw)
    except (ValueError, TypeError):
        confidence = 0.7

    return AgentMeta(
        name=name,
        version=version,
        description=description,
        tags=tags,
        author=author,
        system_prompt=system_prompt,
        conversational_system_prompt=conversational_prompt,
        model_override=model_override or None,
        capabilities=capabilities,
        supported_tasks=supported_tasks,
        preferred_tools=preferred_tools,
        restrictions=restrictions,
        examples=examples,
        confidence_threshold=confidence,
        dependencies=dependencies,
        skills=skills,
        source_path=str(path.resolve()),
    )


def _ensure_str(data: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    """Extract a string value from *data*, returning ``""`` on missing/wrong type."""
    val = data.get(key)
    if val is None:
        return ""
    if not isinstance(val, str):
        val = str(val)
    if not allow_empty and not val.strip():
        return ""
    return val.strip()


def _ensure_tuple_str(data: dict[str, Any], key: str) -> tuple[str, ...]:
    """Extract a tuple of strings from a list/tuple field."""
    val = data.get(key, ())
    if not isinstance(val, (list, tuple)):
        return ()
    result: list[str] = []
    for item in val:
        if isinstance(item, str):
            s = item.strip()
            if s:
                result.append(s)
    return tuple(result)
