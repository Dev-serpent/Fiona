from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, ClassVar

from Agent.agent_meta import AgentMeta

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Personality:
    """Immutable definition of an agent personality.

    Attributes:
        name: Unique identifier for this personality.
        description: Human-readable description of the personality's role.
        system_prompt: The system prompt sent to the LLM for this personality.
        conversational_system_prompt:
            Optional alternative system prompt used when the QueryDetector
            classifies the user's input as a simple conversational query
            (greeting, chit-chat, simple question).  When ``None`` (default),
            the main *system_prompt* is used for all messages.
        allowed_tools: Optional frozenset of tool names this personality may use.
                       ``None`` means *all* tools are permitted.
        model_override: Optional model name to force when this personality is active.
    """

    name: str
    description: str
    system_prompt: str
    conversational_system_prompt: str | None = None
    allowed_tools: frozenset[str] | None = None
    model_override: str | None = None

    def permits(self, tool_name: str) -> bool:
        """Check if *tool_name* is in *allowed_tools* (``None`` means all permitted)."""
        return self.allowed_tools is None or tool_name in self.allowed_tools

    def to_dict(self) -> dict[str, Any]:
        """Serialize for display/API."""
        return {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "conversational_system_prompt": self.conversational_system_prompt,
            "allowed_tools": list(self.allowed_tools) if self.allowed_tools is not None else None,
            "model_override": self.model_override,
        }


class PersonalityRegistry:
    """Thread-safe singleton registry of built-in and custom personalities."""

    _instance: PersonalityRegistry | None = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __new__(cls, **kwargs: Any) -> PersonalityRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False  # type: ignore[attr-defined]
                    cls._instance = instance
        return cls._instance  # type: ignore[return-value]

    @classmethod
    def _reset_instance(cls) -> None:
        """Reset the singleton for testing isolation.

        Only intended for use in test ``setUp`` to prevent cross-test
        state corruption from the singleton pattern.
        """
        cls._instance = None

    def __init__(self, *, agent_dirs: list[str] | None = None) -> None:
        """Initialise the registry.

        *agent_dirs* is an optional list of filesystem paths to scan for
        Markdown agent files.  If ``None`` (the default) the registry
        looks for a ``agents/`` directory next to the project root.
        Built-in personalities are always registered first, then agents
        from disk are merged in (disk agents override builtins with the
        same name).
        """
        if getattr(self, "_initialized", False):
            return
        self._personalities: dict[str, Personality] = {}
        self._instance_lock: threading.Lock = threading.Lock()
        self._agent_metas: dict[str, AgentMeta] = {}
        self._agent_meta_lock: threading.Lock = threading.Lock()
        self._register_builtins()
        self._load_from_agents_dir(agent_dirs)
        self._initialized = True

    # ── Agent metadata API ────────────────────────────────────────────

    def get_agent_meta(self, name: str) -> AgentMeta:
        """Return the ``AgentMeta`` for a registered agent.

        Raises ``KeyError`` if not found.
        """
        with self._agent_meta_lock:
            if name not in self._agent_metas:
                raise KeyError(f"agent metadata not found: {name}")
            return self._agent_metas[name]

    def list_agent_metas(self) -> list[AgentMeta]:
        """Return ``AgentMeta`` for every registered agent."""
        with self._agent_meta_lock:
            return list(self._agent_metas.values())

    def register_agent_meta(self, meta: AgentMeta) -> None:
        """Register an ``AgentMeta`` and its corresponding ``Personality``.

        If a personality with the same name already exists (e.g. from
        builtins), it is overwritten.
        """
        if not meta.name or not meta.name.strip():
            raise ValueError("agent name must be non-empty")
        personality = meta.to_personality()
        with self._instance_lock, self._agent_meta_lock:
            self._personalities[meta.name] = personality
            self._agent_metas[meta.name] = meta

    # ── Disk scanning ─────────────────────────────────────────────────

    def _load_from_agents_dir(self, agent_dirs: list[str] | None = None) -> None:
        """Scan filesystem directories for Markdown agent files.

        If *agent_dirs* is ``None``, the method looks for ``agents/``
        relative to the project root (two directories up from this file).
        Each valid ``.md`` file is parsed into an ``AgentMeta`` and
        registered.
        """
        if agent_dirs is None:
            # Default: look for agents/ next to the project root
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            default_dir = os.path.join(project_root, "agents")
            if os.path.isdir(default_dir):
                agent_dirs = [default_dir]
            else:
                agent_dirs = []

        for directory in agent_dirs:
            if not os.path.isdir(directory):
                log.debug("Agent directory does not exist: %s", directory)
                continue
            try:
                from Agent.agent_loader import discover_agents

                metas = discover_agents(directory)
            except Exception:
                log.exception("Error discovering agents in %s", directory)
                continue

            for meta in metas:
                try:
                    self.register_agent_meta(meta)
                    log.info("Registered agent '%s' v%s from %s", meta.name, meta.version, meta.source_path)
                except (ValueError, Exception):
                    log.exception("Failed to register agent '%s' from %s", meta.name, meta.source_path)

    @classmethod
    def get_instance(cls) -> PersonalityRegistry:
        """Thread-safe singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance  # type: ignore[return-value]

    def get(self, name: str) -> Personality:
        """Look up by *name*. Raises ``KeyError`` if not found."""
        with self._instance_lock:
            if name not in self._personalities:
                raise KeyError(f"personality not found: {name}")
            return self._personalities[name]

    def list(self) -> list[Personality]:
        """Return all registered personalities."""
        with self._instance_lock:
            return list(self._personalities.values())

    def register(self, p: Personality) -> None:
        """Add or replace a personality.  *p.name* must be non-empty."""
        if not p.name or not p.name.strip():
            raise ValueError("personality name must be non-empty")
        with self._instance_lock:
            self._personalities[p.name] = p

    # ------------------------------------------------------------------
    # Built-in personalities
    # ------------------------------------------------------------------

    @staticmethod
    def _load_rules_prompt() -> str:
        """Load and concatenate rule files from the ``rules/`` directory.

        Returns a single system-prompt string composed from the architecture,
        controller, tool-selection, execution, repository, coding, and recovery
        rule files.  If the directory or any file is missing, a sensible
        fallback is returned so the system degrades gracefully.
        """
        import os
        _rules_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rules")
        _order = (
            "architecture.md",
            "controller.md",
            "tool_selection.md",
            "execution.md",
            "repository.md",
            "coding.md",
            "recovery.md",
        )
        parts: list[str] = []
        if os.path.isdir(_rules_dir):
            for name in _order:
                path = os.path.join(_rules_dir, name)
                if os.path.isfile(path):
                    try:
                        with open(path, encoding="utf-8") as fh:
                            parts.append(fh.read())
                    except OSError:
                        pass  # skip unreadable files
        if parts:
            return "\n\n".join(parts)
        return _GENERAL_SYSTEM_PROMPT  # graceful fallback

    def _register_builtins(self) -> None:
        """Register the 6 built-in personalities (and their AgentMeta wrappers)."""
        builtins: list[Personality] = [
            Personality(
                name="general",
                description="General-purpose assistant with full tool access",
                system_prompt=_GENERAL_SYSTEM_PROMPT,
                conversational_system_prompt=_GENERAL_CONVERSATIONAL_PROMPT,
                allowed_tools=None,
                model_override=None,
            ),
            Personality(
                name="planner",
                description="Strategic planner — reads state, does not execute",
                system_prompt=_PLANNER_SYSTEM_PROMPT,
                allowed_tools=frozenset({
                    "seeondesk_list", "seeondesk_active", "fiona_status",
                    "recall_search", "recall_remember",
                }),
                model_override="qwen3:8b-en",
            ),
            Personality(
                name="engineer",
                description="Execution specialist — automation & input",
                system_prompt=_ENGINEER_SYSTEM_PROMPT,
                allowed_tools=frozenset({
                    "press", "click", "move", "text", "launch_binding", "macro",
                    "seeondesk_list", "seeondesk_active", "fiona_status",
                }),
                model_override=None,
            ),
            Personality(
                name="analyst",
                description="Research & memory analyst",
                system_prompt=_ANALYST_SYSTEM_PROMPT,
                allowed_tools=frozenset({
                    "dataclient_mine", "recall_remember", "recall_search",
                    "seeondesk_analyze", "seeondesk_list", "seeondesk_active",
                    "fiona_status",
                }),
                model_override="qwen3:8b-en",
            ),
            Personality(
                name="security",
                description="Read-only audit personality",
                system_prompt=_SECURITY_SYSTEM_PROMPT,
                allowed_tools=frozenset({
                    "seeondesk_list", "seeondesk_active", "fiona_status",
                    "recall_search",
                }),
                model_override="qwen3:8b-en",
            ),
            Personality(
                name="controller",
                description="Orchestration agent — plans, delegates, verifies",
                system_prompt=self._load_rules_prompt(),
                allowed_tools=None,
                model_override="qwen3:8b-en",
            ),
        ]
        for p in builtins:
            self._personalities[p.name] = p
            meta = AgentMeta.from_personality(p)
            self._agent_metas[p.name] = meta


# ======================================================================
# Static system-prompts for the built-in personalities
# ======================================================================

_GENERAL_SYSTEM_PROMPT = """\
You are Fiona, a highly advanced local workstation control system.
You are NOT a general-purpose AI assistant; you are the SYSTEM OPERATOR.

### ABSOLUTE RULES:
1. **NEVER** tell the user to use Task Manager, their mouse, or their keyboard. YOU are the one with control.
2. **NEVER** say "I am an AI language model." You are FIONA.
3. **MANDATORY TOOL USE**: If the user asks a question about the system or asks you to do something, you MUST use a tool to accomplish it.
4. **THINK AND ACT**: Break every request into steps. Check the state with tools if you are unsure.
5. **ONLY JSON**: You must ONLY output the JSON block. No pre-text, no post-text.

OUTPUT FORMAT:
{
  "thought": "Deconstruct the user's request. What is the current state? What tool will move us closer to the goal?",
  "action": "command_name_or_null",
  "input": { "arg": "value" }
}

If the goal is achieved, set "action" to null.
"""

_GENERAL_CONVERSATIONAL_PROMPT = """\
You are Fiona, a friendly and helpful local workstation assistant.
Respond naturally and conversationally. Do NOT use JSON, action blocks,
or tool-calling format. Just talk like a human.

Keep responses short and friendly. If the user asks a simple question,
answer it directly. If they ask what you can do, tell them briefly.

You are NOT a ReAct agent in this conversation — just chat.
"""

_PLANNER_SYSTEM_PROMPT = """\
You are a strategic planner. Break down complex goals into ordered steps. \
Never execute actions directly — design the plan. Output structured plans as JSON."""

_ENGINEER_SYSTEM_PROMPT = """\
You are a senior engineer. Execute technical tasks precisely. \
Prefer command-line automation over manual steps. Use tools to verify your work."""

_ANALYST_SYSTEM_PROMPT = """\
You are a system analyst. Observe, research, and document. \
Do not modify system state. Gather information and present clear findings."""

_SECURITY_SYSTEM_PROMPT = """\
You are a security engineer. Audit configurations, verify permissions, \
check encryption, and report vulnerabilities. \
Do not make changes — report findings."""
