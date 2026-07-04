"""Centralised configuration for the Agent subsystem.

Provides:
- ``AgentConfig`` dataclass with all configuration knobs
- ``load_agent_config()`` — loads from YAML + env-var overrides
- Defaults that exactly match the current hardcoded values
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False

log = logging.getLogger(__name__)

# ── Environment-variable prefix ───────────────────────────────────────
_ENV_PREFIX = "FIONA_AGENT_"


def _project_root() -> Path:
    """Return the project root directory (two levels up from this file)."""
    return Path(__file__).resolve().parent.parent


def _default_agent_dirs() -> tuple[str, ...]:
    """Resolve the default agent directories at runtime."""
    root = _project_root()
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        return (str(agents_dir),)
    return ()


def _default_chat_store_path() -> str:
    """Default path for the chat store database."""
    return str(Path.home() / ".fiona" / "chat.db")


# ── Config dataclass ──────────────────────────────────────────────────


@dataclass(frozen=True)
class AgentConfig:
    """Centralised configuration for Fiona's Agent subsystem.

    Every field has a sensible default that matches the current hardcoded
    behaviour so the system works out-of-the-box without any config file.
    """

    # ── LLM provider ──────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434/api"
    """Base URL for the Ollama API (including the ``/api`` suffix)."""

    default_model: str = "qwen3:8b-en"
    """Default LLM model identifier."""

    llm_timeout_seconds: float = 120.0
    """Timeout for each LLM API call."""

    llm_temperature: float = 0.3
    """Default temperature for LLM calls."""

    llm_max_tokens: int = 2048
    """Maximum tokens in LLM responses."""

    # ── Agent discovery ───────────────────────────────────────────────
    agent_dirs: tuple[str, ...] = field(default_factory=_default_agent_dirs)
    """Directories to scan for Markdown agent files."""

    # ── Orchestration (ForemanAgent / Coordinator) ────────────────────
    parallel_by_default: bool = False
    """When ``True``, sub-goals execute in parallel unless marked sequential."""

    max_sub_agents: int = 5
    """Maximum sub-agents in a single decomposed plan."""

    max_turns_per_sub_agent: int = 10
    """Maximum ReAct turns per sub-agent before forced termination."""

    max_plan_retries: int = 2
    """Number of retries when LLM decomposition fails validation."""

    context_max_tokens: int = 2048
    """Token budget for context-window assembly."""

    default_agent: str = "general"
    """Default agent name when none is specified."""

    # ── Memory / persistence ──────────────────────────────────────────
    chat_store_path: str = field(default_factory=_default_chat_store_path)
    """Filesystem path to the SQLite chat store database."""

    # ── Hot reload ────────────────────────────────────────────────────
    enable_hot_reload: bool = False
    """When ``True``, watch agent directories for changes and reload."""

    hot_reload_poll_interval: float = 5.0
    """Polling interval (seconds) for hot-reload file watcher."""

    # ── Conversions ───────────────────────────────────────────────────

    def to_foreman_config(self) -> Any:
        """Produce a ``ForemanConfig`` matching the orchestration subset.

        Avoids a hard import dependency; the caller imports ``ForemanConfig``.
        """
        from Agent.orchestration import ForemanConfig

        return ForemanConfig(
            parallel_by_default=self.parallel_by_default,
            max_sub_agents=self.max_sub_agents,
            max_turns_per_sub_agent=self.max_turns_per_sub_agent,
            max_plan_retries=self.max_plan_retries,
            context_max_tokens=self.context_max_tokens,
            default_personality=self.default_agent,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for logging / introspection."""
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Path):
                value = str(value)
            result[f.name] = value
        return result


# ── Config loader ─────────────────────────────────────────────────────

_DEFAULT_CONFIG_PATHS: tuple[str, ...] = (
    str(Path.home() / ".config" / "fiona" / "agent.yaml"),
    str(Path.home() / ".fiona" / "agent.yaml"),
    str(_project_root() / "config" / "agent.yaml"),
)


def load_agent_config(
    path: str | Path | None = None,
    *,
    env_prefix: str = _ENV_PREFIX,
) -> AgentConfig:
    """Load ``AgentConfig`` from a YAML file with environment overrides.

    Resolution order (later sources override earlier ones):
    1. ``AgentConfig`` defaults
    2. YAML file (first found in search path)
    3. Environment variables ``FIONA_AGENT_<UPPER_CASED_FIELD_NAME>``

    Args:
        path: Explicit config file path.  When ``None``, the function
            searches ``~/.config/fiona/agent.yaml``,
            ``~/.fiona/agent.yaml``, and ``config/agent.yaml`` (relative
            to the project root) in that order.
        env_prefix: Prefix for environment-variable overrides.

    Returns:
        A populated ``AgentConfig`` instance.
    """
    # Start with defaults
    config_dict: dict[str, Any] = {}

    # 1. Load from YAML
    yaml_path = _resolve_config_path(path)
    if yaml_path is not None:
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            if _YAML_AVAILABLE:
                data = yaml.safe_load(raw)
                if isinstance(data, dict):
                    config_dict.update(data)
            else:
                log.warning("PyYAML not available; skipping config file %s", yaml_path)
        except Exception as exc:
            log.warning("Failed to load config from %s: %s", yaml_path, exc)

    # 2. Override from environment variables
    for f in fields(AgentConfig):
        env_key = f"{env_prefix}{f.name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            config_dict[f.name] = _coerce_env_value(env_val, f.type)

    # 3. Build the dataclass
    # Filter to only valid fields
    valid_field_names = {f.name for f in fields(AgentConfig)}
    filtered = {k: v for k, v in config_dict.items() if k in valid_field_names}

    return AgentConfig(**filtered)


# ── Internal helpers ──────────────────────────────────────────────────


def _resolve_config_path(path: str | Path | None) -> Path | None:
    """Resolve the config file path, searching default locations if needed."""
    if path is not None:
        p = Path(path)
        return p if p.is_file() else None

    for candidate in _DEFAULT_CONFIG_PATHS:
        p = Path(candidate)
        if p.is_file():
            return p
    return None


def _coerce_env_value(value: str, target_type: type) -> Any:
    """Coerce an environment-variable string to the target type."""
    if target_type is bool or target_type == "bool":
        return value.lower() in ("1", "true", "yes", "on")
    if target_type is int or target_type == "int":
        try:
            return int(value)
        except ValueError:
            return value
    if target_type is float or target_type == "float":
        try:
            return float(value)
        except ValueError:
            return value
    if target_type in (tuple, list) or "tuple" in str(target_type):
        # Comma-separated values: "a,b,c" → ("a", "b", "c")
        parts = [v.strip() for v in value.split(",") if v.strip()]
        return tuple(parts)
    return value
