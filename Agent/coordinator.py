"""Pure Coordinator Orchestrator — metadata-driven agent routing and dispatch.

Provides:
- ``AgentRouter``: Routes goals to agents based on ``AgentMeta`` metadata
  (tags, capabilities, supported_tasks) with LLM-based fallback.
- ``Coordinator``: Pure orchestrator that accepts a goal, routes it to the
  best matching agent, dispatches execution, and returns a structured result.

This module does **not** perform task decomposition — it routes the *entire*
goal to a single best-fit agent (the ForemanAgent still handles multi-agent
decomposition for complex goals).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from Agent.events import (
        AgentExecutionCompleted,
        AgentExecutionStarted,
        AgentRouted,
    )

    _HAS_EVENTS = True
except ImportError:
    _HAS_EVENTS = False

from Agent.cancellation import CancellationToken
from Agent.ollama import OllamaClient
from Agent.orchestration import (
    Complexity,
    ComplexityAssessor,
    SubAgent,
    SubAgentResult,
)
from Agent.permission import PermissionEnforcer, SafeActionRouter
from Agent.personality import PersonalityRegistry

logger = logging.getLogger(__name__)


# ======================================================================
# 1. Routing data types
# ======================================================================


@dataclass(frozen=True)
class ScoredAgent:
    """A candidate agent with a match score and reason.

    Attributes:
        agent_name: Name of the agent (matches ``AgentMeta.name``).
        score: Match score between 0.0 and 1.0.
        match_reason: Human-readable explanation of the match.
    """

    agent_name: str
    score: float
    match_reason: str = ""


@dataclass(frozen=True)
class RouteResult:
    """Result of routing a goal to an agent.

    Attributes:
        primary_agent: Name of the best-matching agent.
        confidence: Match confidence of the primary agent (0.0 – 1.0).
        alternatives: List of next-best ``ScoredAgent`` entries.
        match_method: Description of the matching strategy used
            (e.g. ``"tags"``, ``"capabilities"``, ``"llm"``).
    """

    primary_agent: str
    confidence: float = 0.0
    alternatives: tuple[ScoredAgent, ...] = ()
    match_method: str = "none"


@dataclass
class CoordinatorResult:
    """Structured result from a ``Coordinator`` execution.

    Attributes:
        goal: The original goal/request.
        response: The final response string.
        route: The ``RouteResult`` describing agent selection.
        success: Whether execution completed without errors.
        sub_result: The ``SubAgentResult`` from agent execution.
        duration_ms: Total wall-clock time in milliseconds.
        error: Error message if execution failed.
    """

    goal: str
    response: str = ""
    route: RouteResult | None = None
    success: bool = True
    sub_result: SubAgentResult | None = None
    duration_ms: float = 0.0
    error: str | None = None


# ======================================================================
# 2. AgentRouter — metadata-driven routing engine
# ======================================================================


class AgentRouter:
    """Routes a goal to the best-matching agent using ``AgentMeta`` metadata.

    Matching strategy (in order):
    1. **Tag match**: Scores agents by how many of their ``tags`` appear in
       the goal text.
    2. **Capability match**: Scores agents by how many of their
       ``capabilities`` appear in the goal text.
    3. **Task match**: Scores agents by how many keywords from their
       ``supported_tasks`` appear in the goal text.
    4. **LLM fallback**: If no metadata match exceeds the
       ``confidence_threshold``, asks the LLM to classify the goal.
    """

    def __init__(
        self,
        registry: PersonalityRegistry,
        client: OllamaClient | None = None,
        *,
        confidence_threshold: float = 0.3,
    ) -> None:
        """Initialise the router.

        Args:
            registry: The ``PersonalityRegistry`` containing registered agents.
            client: Optional ``OllamaClient`` for LLM-based fallback routing.
            confidence_threshold: Minimum metadata-match score (0.0 – 1.0)
                before falling back to LLM classification.  Default 0.3.
        """
        self._registry = registry
        self._client = client
        self._threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        goal: str,
        *,
        top_k: int = 3,
        exclude: set[str] | None = None,
    ) -> RouteResult:
        """Route *goal* to the best-matching agent.

        Args:
            goal: The user's goal or request text.
            top_k: Maximum number of alternatives to include.
            exclude: Optional set of agent names to exclude from routing.

        Returns:
            A ``RouteResult`` with the primary agent and alternatives.
        """
        exclude = exclude or set()
        agents = self._get_candidates(exclude)
        if not agents:
            return RouteResult(
                primary_agent="general",
                confidence=0.0,
                match_method="fallback-empty",
            )

        goal_lower = goal.lower()

        # 1. Tag matching
        tagged = self._score_by_tags(goal_lower, agents)
        best_tagged = max(tagged, key=lambda s: s.score) if tagged else None

        # 2. Capability matching
        capped = self._score_by_capabilities(goal_lower, agents)
        best_capped = max(capped, key=lambda s: s.score) if capped else None

        # 3. Task matching
        tasked = self._score_by_tasks(goal_lower, agents)
        best_tasked = max(tasked, key=lambda s: s.score) if tasked else None

        # Combine: take the best across all strategies
        candidates: list[ScoredAgent] = []
        seen: set[str] = set()

        for scored_list in (tagged, capped, tasked):
            for sa in scored_list:
                if sa.agent_name not in seen:
                    candidates.append(sa)
                    seen.add(sa.agent_name)

        candidates.sort(key=lambda s: s.score, reverse=True)

        if not candidates:
            # No metadata match — try LLM fallback before giving up
            if self._client is not None:
                llm_name = self._route_via_llm(goal, agents)
                if llm_name is not None:
                    return RouteResult(
                        primary_agent=llm_name,
                        confidence=0.8,
                        alternatives=(),
                        match_method="llm",
                    )
            return RouteResult(
                primary_agent="general",
                confidence=0.0,
                match_method="fallback-no-candidates",
            )

        best = candidates[0]

        # 4. LLM fallback if below threshold
        if best.score < self._threshold and self._client is not None:
            llm_name = self._route_via_llm(goal, agents)
            if llm_name is not None:
                return RouteResult(
                    primary_agent=llm_name,
                    confidence=0.8,  # LLM-based — moderate confidence
                    alternatives=tuple(candidates[:top_k]),
                    match_method="llm",
                )

        return RouteResult(
            primary_agent=best.agent_name,
            confidence=best.score,
            alternatives=tuple(candidates[:top_k]),
            match_method=self._best_method(best.agent_name, tagged, capped, tasked),
        )

    # ------------------------------------------------------------------
    # Scoring strategies
    # ------------------------------------------------------------------

    def _score_by_tags(
        self,
        goal_lower: str,
        agents: list[ScoredAgent],
    ) -> list[ScoredAgent]:
        """Score agents by tag overlap with the goal."""
        scored: list[ScoredAgent] = []
        for sa in agents:
            try:
                meta = self._registry.get_agent_meta(sa.agent_name)
            except KeyError:
                continue
            if not meta.tags:
                continue
            matches = sum(
                1 for tag in meta.tags if tag.lower() in goal_lower
            )
            score = min(matches / max(len(meta.tags), 1), 1.0)
            if score > 0:
                scored.append(
                    ScoredAgent(
                        agent_name=sa.agent_name,
                        score=score,
                        match_reason=f"matched {matches}/{len(meta.tags)} tags",
                    )
                )
        return scored

    def _score_by_capabilities(
        self,
        goal_lower: str,
        agents: list[ScoredAgent],
    ) -> list[ScoredAgent]:
        """Score agents by capability overlap with the goal."""
        scored: list[ScoredAgent] = []
        for sa in agents:
            try:
                meta = self._registry.get_agent_meta(sa.agent_name)
            except KeyError:
                continue
            if not meta.capabilities:
                continue
            matches = sum(
                1 for cap in meta.capabilities if cap.lower() in goal_lower
            )
            score = min(matches / max(len(meta.capabilities), 1), 1.0)
            if score > 0:
                scored.append(
                    ScoredAgent(
                        agent_name=sa.agent_name,
                        score=score,
                        match_reason=f"matched {matches}/{len(meta.capabilities)} caps",
                    )
                )
        return scored

    def _score_by_tasks(
        self,
        goal_lower: str,
        agents: list[ScoredAgent],
    ) -> list[ScoredAgent]:
        """Score agents by supported_task keyword overlap with the goal."""
        scored: list[ScoredAgent] = []
        for sa in agents:
            try:
                meta = self._registry.get_agent_meta(sa.agent_name)
            except KeyError:
                continue
            if not meta.supported_tasks:
                continue
            # Extract keywords from task descriptions
            task_keywords = set()
            for task in meta.supported_tasks:
                for word in task.lower().split():
                    # Filter to meaningful words (len > 3, not stop words)
                    if len(word) > 3 and word not in _STOP_WORDS:
                        task_keywords.add(word.strip(".,!?;:"))
            if not task_keywords:
                continue
            matches = sum(1 for kw in task_keywords if kw in goal_lower)
            score = min(matches / max(len(task_keywords), 1), 1.0)
            if score > 0:
                scored.append(
                    ScoredAgent(
                        agent_name=sa.agent_name,
                        score=score,
                        match_reason=f"matched {matches} task keywords",
                    )
                )
        return scored

    def _route_via_llm(
        self,
        goal: str,
        agents: list[ScoredAgent],
    ) -> str | None:
        """Fallback: ask the LLM to classify the goal to the best agent.

        Returns the agent name, or ``None`` if the LLM call fails.
        """
        if self._client is None:
            return None

        agent_list = "\n".join(
            f"- {sa.agent_name}: {self._agent_description(sa.agent_name)}"
            for sa in agents
        )

        prompt = f"""Classify the following user request to the most appropriate agent.

Available agents:
{agent_list}

User request: {goal}

Respond with ONLY a JSON object: {{"agent": "agent_name", "reason": "..."}}
"""

        try:
            response = self._client.ask(
                prompt=prompt,
                temperature=0.1,
                max_tokens=128,
            )
            import json

            data = _extract_json(response)
            if data is None:
                return None
            agent_name = data.get("agent", "")
            if agent_name and any(
                sa.agent_name == agent_name for sa in agents
            ):
                return agent_name
            return None
        except Exception as exc:
            logger.warning("AgentRouter LLM fallback failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_candidates(
        self,
        exclude: set[str],
    ) -> list[ScoredAgent]:
        """Return all registered agents as scored candidates (score = 0)."""
        candidates: list[ScoredAgent] = []
        for meta in self._registry.list_agent_metas():
            if meta.name in exclude:
                continue
            candidates.append(ScoredAgent(agent_name=meta.name, score=0.0))
        return candidates

    @staticmethod
    def _best_method(
        agent_name: str,
        tagged: list[ScoredAgent],
        capped: list[ScoredAgent],
        tasked: list[ScoredAgent],
    ) -> str:
        """Determine which strategy produced the best match."""
        for method_name, scored_list in [
            ("tags", tagged),
            ("capabilities", capped),
            ("tasks", tasked),
        ]:
            for sa in scored_list:
                if sa.agent_name == agent_name:
                    return method_name
        return "unknown"

    def _agent_description(self, agent_name: str) -> str:
        """Return a short description string for an agent from the registry."""
        try:
            meta = self._registry.get_agent_meta(agent_name)
            return meta.description or agent_name
        except KeyError:
            return agent_name


# ======================================================================
# 3. Coordinator — pure orchestrator
# ======================================================================


class Coordinator:
    """Pure coordinator orchestrator.

    Pipeline:
    1. Assess goal complexity (reuses ``ComplexityAssessor``).
    2. Route the goal to the best agent via ``AgentRouter``.
    3. Dispatch execution via ``SubAgent`` (using the matched agent's
       personality).
    4. Return a ``CoordinatorResult`` with the response and routing metadata.

    This orchestrator is intentionally simpler than ``ForemanAgent`` — it
    does **not** decompose goals into sub-goals.  It routes the entire goal
    to a single best-fit agent.  For multi-agent decomposition, use
    ``ForemanAgent`` instead.
    """

    def __init__(
        self,
        client: OllamaClient,
        registry: PersonalityRegistry,
        router: AgentRouter | None = None,
        *,
        max_turns: int = 10,
        default_agent: str = "general",
        event_bus: Any = None,
    ) -> None:
        """Initialise the coordinator.

        Args:
            client: The LLM client used by ``SubAgent`` and for LLM-based
                routing fallback.
            registry: The ``PersonalityRegistry`` with registered agents.
            router: Optional custom ``AgentRouter``.  If ``None``, a default
                router is created using the provided *client* and *registry*.
            max_turns: Maximum ReAct turns per agent execution.
            default_agent: Fallback agent name when routing produces no
                confident match.
            event_bus: Optional ``EventBus`` for publishing routing and
                execution events.
        """
        self._client = client
        self._registry = registry
        self._router = router or AgentRouter(
            registry=registry,
            client=client,
        )
        self._max_turns = max_turns
        self._default_agent = default_agent
        self._assessor = ComplexityAssessor(client)
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        goal: str,
        token: CancellationToken | None = None,
    ) -> CoordinatorResult:
        """Full coordinator pipeline.

        Args:
            goal: The user's goal or request.
            token: Optional cancellation token.

        Returns:
            A ``CoordinatorResult`` with the response and routing metadata.
        """
        token = token or CancellationToken()
        start = time.monotonic()

        # 1. Assess complexity (used for logging / future branching)
        complexity = self._assessor.assess(goal)
        logger.info(
            "Coordinator: assessed goal complexity = %s", complexity.value
        )

        # 2. Route to best agent
        route = self._router.route(goal)
        agent_name = route.primary_agent
        logger.info(
            "Coordinator: routed to agent %r (method=%s, confidence=%.2f)",
            agent_name,
            route.match_method,
            route.confidence,
        )
        self._publish(
            AgentRouted(
                source="coordinator",
                timestamp=time.time(),
                goal=goal,
                agent_name=agent_name,
                confidence=route.confidence,
                match_method=route.match_method,
                alternatives=len(route.alternatives),
            )
        )

        # 3. Resolve personality and create SubAgent
        try:
            personality = self._registry.get(agent_name)
        except KeyError:
            # Fallback to default agent
            logger.warning(
                "Coordinator: agent %r not found, falling back to %r",
                agent_name,
                self._default_agent,
            )
            agent_name = self._default_agent
            personality = self._registry.get(agent_name)

        # 4. Create permission enforcer + router
        enforcer = PermissionEnforcer(personality)
        action_router = SafeActionRouter(enforcer)

        # 5. Execute via SubAgent
        self._publish(
            AgentExecutionStarted(
                source="coordinator",
                timestamp=time.time(),
                goal=goal,
                agent_name=agent_name,
                max_turns=self._max_turns,
            )
        )
        sub_result = self._dispatch(goal, personality, action_router, token)

        elapsed = (time.monotonic() - start) * 1000

        result = CoordinatorResult(
            goal=goal,
            response=sub_result.response,
            route=route,
            success=sub_result.success and not sub_result.cancelled,
            sub_result=sub_result,
            duration_ms=elapsed,
            error=sub_result.error,
        )

        self._publish(
            AgentExecutionCompleted(
                source="coordinator",
                timestamp=time.time(),
                goal=goal,
                agent_name=agent_name,
                success=result.success,
                duration_ms=elapsed,
                turns=sub_result.turns if sub_result else 0,
                error=result.error,
            )
        )

        logger.info(
            "Coordinator: completed in %.0f ms (success=%s)",
            elapsed,
            result.success,
        )
        return result

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def set_event_bus(self, event_bus: Any) -> None:
        """Set or replace the event bus used for publishing coordinator events.

        Args:
            event_bus: An ``EventBus`` instance.
        """
        self._event_bus = event_bus

    def _publish(self, event: Any) -> None:
        """Publish an event on the configured event bus (no-op if not set)."""
        if self._event_bus is not None and _HAS_EVENTS:
            self._event_bus.publish(event)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        goal: str,
        personality: Any,  # Personality
        action_router: SafeActionRouter,
        token: CancellationToken,
    ) -> SubAgentResult:
        """Create a ``SubAgent`` and execute the goal.

        Returns:
            A ``SubAgentResult`` capturing the outcome.
        """
        sub = SubAgent(
            personality=personality,
            client=self._client,
            router=action_router,
            max_turns=self._max_turns,
        )
        start = time.monotonic()
        try:
            response = sub.execute(goal, token)
            elapsed = (time.monotonic() - start) * 1000
            return SubAgentResult(
                task_description=goal,
                personality_used=personality.name,
                response=response,
                success=True,
                turns=sub.turns,
                duration_ms=elapsed,
                cancelled=token.is_cancelled(),
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return SubAgentResult(
                task_description=goal,
                personality_used=personality.name,
                response="",
                success=False,
                error=str(exc),
                turns=sub.turns,
                duration_ms=elapsed,
                cancelled=token.is_cancelled(),
            )


# ======================================================================
# 4. Internal helpers
# ======================================================================

# Common English stop words (short words unlikely to be meaningful for matching)
_STOP_WORDS: frozenset[str] = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "any",
    "can", "has", "had", "was", "were", "will", "with", "this",
    "that", "from", "have", "been", "what", "which", "their",
    "there", "when", "where", "how", "would", "could", "should",
    "about", "into", "over", "also", "than", "then", "very",
    "just", "like", "make", "more", "some", "such", "than",
    "them", "then", "they", "well", "your",
})


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from text that may have surrounding content."""
    import json

    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        return data if isinstance(data, dict) else None
    except (ValueError, json.JSONDecodeError):
        return None


__all__ = [
    "AgentRouter",
    "Coordinator",
    "CoordinatorResult",
    "RouteResult",
    "ScoredAgent",
]
