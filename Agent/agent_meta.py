"""Agent metadata model — the machine-readable definition of an agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from Agent.personality import Personality


@dataclass(frozen=True)
class AgentMeta:
    """Self-describing metadata for a Fiona agent.

    This extends the ``Personality`` concept with rich metadata that allows
    the framework to discover, route, and compose agents without hardcoding
    any information about them.

    Every agent is defined by a Markdown file with YAML front matter that
    maps directly to the fields of this dataclass.
    """

    # ── Identity ──────────────────────────────────────────────────────
    name: str
    """Unique identifier for this agent (lowercase, hyphenated)."""

    version: str
    """Semantic version string (e.g. ``"1.0.0"``)."""

    description: str
    """Human-readable description of the agent's role and purpose."""

    tags: tuple[str, ...] = ()
    """Searchable tags for discovery and routing."""

    author: str = "Fiona"
    """Agent author / maintainer."""

    # ── LLM configuration (the ``Personality`` subset) ────────────────
    system_prompt: str = ""
    """System prompt sent to the LLM for this agent.

    If empty, the Markdown file body (after the YAML front matter) is used.
    """

    conversational_system_prompt: str | None = None
    """Alternative prompt used for casual / conversational queries."""

    model_override: str | None = None
    """Specific LLM model to use (``None`` = use the platform default)."""

    # ── Capabilities ──────────────────────────────────────────────────
    capabilities: tuple[str, ...] = ()
    """High-level capabilities (e.g. ``"code-generation"``, ``"system-audit"``)."""

    supported_tasks: tuple[str, ...] = ()
    """Specific task descriptions this agent can handle."""

    preferred_tools: tuple[str, ...] = ()
    """Tool names this agent is permitted to use.

    An empty tuple means *all* tools are permitted (equivalent to
    ``Personality.allowed_tools = None``).
    """

    restrictions: tuple[str, ...] = ()
    """Behavioural rules / limitations expressed in natural language."""

    examples: tuple[dict[str, str], ...] = ()
    """Example interactions (``{"query": ..., "response": ...}``)."""

    confidence_threshold: float = 0.7
    """Minimum confidence (0.0 – 1.0) for accepting a task match."""

    # ── Composition ───────────────────────────────────────────────────
    dependencies: tuple[str, ...] = ()
    """Other agent or skill names required by this agent."""

    skills: tuple[str, ...] = ()
    """Names of reusable Skills this agent composes."""

    # ── Source tracking ───────────────────────────────────────────────
    source_path: str | None = None
    """Filesystem path to the ``.md`` file this agent was loaded from."""

    # ── Conversions ───────────────────────────────────────────────────

    def to_personality(self) -> Any:  # returns Personality (lazy import to avoid circular)
        """Convert to a backward-compatible ``Personality``.

        Existing subsystems that expect a ``Personality`` instance can
        call this method to obtain one.
        """
        from Agent.personality import Personality

        return Personality(
            name=self.name,
            description=self.description,
            system_prompt=self.system_prompt,
            conversational_system_prompt=self.conversational_system_prompt,
            allowed_tools=(
                frozenset(self.preferred_tools) if self.preferred_tools else None
            ),
            model_override=self.model_override,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize all metadata to a plain dict for introspection / APIs."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tags": list(self.tags),
            "author": self.author,
            "capabilities": list(self.capabilities),
            "supported_tasks": list(self.supported_tasks),
            "preferred_tools": list(self.preferred_tools),
            "restrictions": list(self.restrictions),
            "examples": list(self.examples),
            "confidence_threshold": self.confidence_threshold,
            "dependencies": list(self.dependencies),
            "skills": list(self.skills),
            "source_path": self.source_path,
            "model_override": self.model_override,
        }

    @classmethod
    def from_personality(
        cls,
        p: Any,  # Personality (lazy import)
        *,
        source_path: str | None = None,
        **overrides: Any,
    ) -> AgentMeta:
        """Create an ``AgentMeta`` from an existing ``Personality``.

        This is used internally to wrap the hardcoded built-in personalities
        into the new agent metadata format.
        """
        kwargs: dict[str, Any] = dict(
            name=p.name,
            version="1.0.0",
            description=p.description,
            system_prompt=p.system_prompt,
            conversational_system_prompt=p.conversational_system_prompt,
            model_override=p.model_override,
            preferred_tools=tuple(p.allowed_tools) if p.allowed_tools else (),
            source_path=source_path,
            tags=(p.name,),
            author="Fiona",
        )
        kwargs.update(overrides)
        return cls(**kwargs)
