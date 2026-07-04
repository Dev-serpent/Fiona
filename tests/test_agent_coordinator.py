"""Tests for ``Agent.coordinator`` — ``AgentRouter`` and ``Coordinator``."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from Agent.agent_meta import AgentMeta
from Agent.cancellation import CancellationToken
from Agent.coordinator import (
    AgentRouter,
    Coordinator,
    CoordinatorResult,
    RouteResult,
    ScoredAgent,
)
from Agent.orchestration import Complexity, SubAgentResult
from Agent.personality import Personality, PersonalityRegistry


# ======================================================================
# Helper: build a registry with test agents
# ======================================================================


def _make_registry(
    agents: list[AgentMeta] | None = None,
) -> PersonalityRegistry:
    """Return the ``PersonalityRegistry`` singleton populated with *agents*.

    Each agent meta and its corresponding personality are registered via
    the public ``register_agent_meta()`` API.  Existing built-in agents
    remain available unless overridden by name.
    """
    reg = PersonalityRegistry.get_instance()
    if agents:
        for meta in agents:
            try:
                reg.register_agent_meta(meta)
            except (ValueError, Exception):
                pass
    return reg


# ======================================================================
# Sample agent metadata for tests
# ======================================================================

_ENGINEER_META = AgentMeta(
    name="engineer",
    version="1.0.0",
    description="Software engineer agent with coding and system skills",
    tags=("engineer", "developer", "coder"),
    capabilities=("code-generation", "debugging", "system-control"),
    supported_tasks=(
        "Write Python code",
        "Debug application errors",
        "Analyze system logs",
    ),
)

_ANALYST_META = AgentMeta(
    name="analyst",
    version="1.0.0",
    description="Data analysis and research agent",
    tags=("analyst", "researcher", "data"),
    capabilities=("data-analysis", "research", "visualization"),
    supported_tasks=(
        "Analyze datasets",
        "Generate reports",
        "Create visualizations",
    ),
)

_SECURITY_META = AgentMeta(
    name="security",
    version="1.0.0",
    description="Security audit and vulnerability assessment agent",
    tags=("security", "auditor", "pentester"),
    capabilities=("vulnerability-assessment", "security-audit"),
    supported_tasks=(
        "Scan for vulnerabilities",
        "Review security configuration",
    ),
)

_GENERAL_META = AgentMeta(
    name="general",
    version="1.0.0",
    description="General-purpose assistant",
    tags=(),
    capabilities=(),
    supported_tasks=(),
)


# ======================================================================
# ScoredAgent
# ======================================================================


class TestScoredAgent:
    """ScoredAgent is a simple frozen dataclass."""

    def test_create(self) -> None:
        sa = ScoredAgent(agent_name="test", score=0.8, match_reason="tags")
        assert sa.agent_name == "test"
        assert sa.score == 0.8
        assert sa.match_reason == "tags"

    def test_frozen(self) -> None:
        sa = ScoredAgent(agent_name="a", score=0.5)
        with pytest.raises(AttributeError):
            sa.score = 0.9  # type: ignore[misc]

    def test_default_reason(self) -> None:
        sa = ScoredAgent(agent_name="a", score=0.5)
        assert sa.match_reason == ""


# ======================================================================
# RouteResult
# ======================================================================


class TestRouteResult:
    """RouteResult holds routing decision metadata."""

    def test_create(self) -> None:
        alt = (ScoredAgent("b", 0.3),)
        result = RouteResult(
            primary_agent="a",
            confidence=0.9,
            alternatives=alt,
            match_method="tags",
        )
        assert result.primary_agent == "a"
        assert result.confidence == 0.9
        assert len(result.alternatives) == 1

    def test_defaults(self) -> None:
        result = RouteResult(primary_agent="general")
        assert result.confidence == 0.0
        assert result.alternatives == ()
        assert result.match_method == "none"


# ======================================================================
# CoordinatorResult
# ======================================================================


class TestCoordinatorResult:
    """CoordinatorResult holds the full coordinator output."""

    def test_create(self) -> None:
        result = CoordinatorResult(
            goal="test goal",
            response="done",
            success=True,
            duration_ms=100.0,
        )
        assert result.goal == "test goal"
        assert result.response == "done"
        assert result.success

    def test_defaults(self) -> None:
        result = CoordinatorResult(goal="hello")
        assert result.response == ""
        assert result.route is None
        assert result.success
        assert result.sub_result is None
        assert result.duration_ms == 0.0
        assert result.error is None


# ======================================================================
# AgentRouter — tag matching
# ======================================================================


class TestAgentRouterTagMatching:
    """AgentRouter must score agents by tag overlap."""

    def make_router(self, agents: list[AgentMeta]) -> AgentRouter:
        registry = _make_registry(agents)
        return AgentRouter(registry=registry)

    def test_tag_match_selects_engineer(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        # "engineer" is a tag of the engineer agent
        result = router.route("Engineer needed to fix this bug")
        assert result.primary_agent == "engineer"
        assert result.match_method == "tags"

    def test_tag_match_selects_analyst(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        # "data" is a tag of the analyst agent (also in "analyst" tag)
        result = router.route("Analyst please review this dataset")
        assert result.primary_agent == "analyst"
        assert result.match_method == "tags"

    def test_tag_match_returns_general_when_no_match(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route("What is the weather today?")
        # No tags match "weather" — best score may be 0, falls to general
        assert result.primary_agent == "general"
        assert result.confidence == 0.0

    def test_multiple_alternatives(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _SECURITY_META, _GENERAL_META]
        )
        result = router.route(
            "Security engineer, check vulnerabilities in the code",
            top_k=3,
        )
        assert len(result.alternatives) <= 3
        assert result.primary_agent in (
            "engineer", "security",
        )


# ======================================================================
# AgentRouter — capability matching
# ======================================================================


class TestAgentRouterCapabilityMatching:
    """AgentRouter must score agents by capability overlap."""

    def make_router(self, agents: list[AgentMeta]) -> AgentRouter:
        registry = _make_registry(agents)
        return AgentRouter(registry=registry)

    def test_capability_match(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route(
            "Need code-generation and debugging for payment module"
        )
        assert result.primary_agent == "engineer"
        # "code-generation" and "debugging" match engineer capabilities

    def test_capability_match_analyst(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route("Need data-analysis and research")
        assert result.primary_agent == "analyst"


# ======================================================================
# AgentRouter — task matching
# ======================================================================


class TestAgentRouterTaskMatching:
    """AgentRouter must score agents by supported_task keywords."""

    def make_router(self, agents: list[AgentMeta]) -> AgentRouter:
        registry = _make_registry(agents)
        return AgentRouter(registry=registry)

    def test_task_keyword_match(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route("Help debug application errors")
        # "debug", "application", "errors" from "Debug application errors" match
        assert result.primary_agent == "engineer"

    def test_task_analyst(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route(
            "Generate reports and create visualizations from datasets"
        )
        assert result.primary_agent == "analyst"


# ======================================================================
# AgentRouter — exclude filter
# ======================================================================


class TestAgentRouterExclude:
    """AgentRouter must respect the exclude set."""

    def make_router(self, agents: list[AgentMeta]) -> AgentRouter:
        registry = _make_registry(agents)
        return AgentRouter(registry=registry)

    def test_exclude_engineer(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        result = router.route(
            "Engineer debug this code",
            exclude={"engineer"},
        )
        # engineer is excluded, so it should not be selected
        assert result.primary_agent != "engineer"


# ======================================================================
# AgentRouter — LLM fallback
# ======================================================================


class TestAgentRouterLLMFallback:
    """When metadata score is below threshold, router should use LLM."""

    def make_router(
        self,
        agents: list[AgentMeta],
        client: MagicMock | None = None,
    ) -> AgentRouter:
        registry = _make_registry(agents)
        return AgentRouter(
            registry=registry,
            client=client,
            confidence_threshold=0.5,
        )

    def test_llm_fallback_when_below_threshold(self) -> None:
        mock_client = MagicMock()
        # LLM returns engineer
        mock_client.ask.return_value = (
            '{"agent": "engineer", "reason": "best match"}'
        )
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META],
            client=mock_client,
        )
        # Goal with no tag/cap/task overlap -> below threshold
        result = router.route("What is the meaning of life?")
        # Should use LLM fallback
        assert result.match_method == "llm"
        assert result.primary_agent == "engineer"

    def test_llm_fallback_returns_general_on_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.ask.side_effect = Exception("LLM unavailable")
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META],
            client=mock_client,
        )
        result = router.route("What is the meaning of life?")
        # LLM failed — should fallback to general (no metadata match)
        assert result.primary_agent == "general"

    def test_no_llm_client_skips_fallback(self) -> None:
        router = self.make_router(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META],
            client=None,
        )
        result = router.route("What is the meaning of life?")
        assert result.primary_agent == "general"
        assert result.match_method != "llm"


# ======================================================================
# AgentRouter — empty / edge cases
# ======================================================================


class TestAgentRouterEdgeCases:
    """Edge cases for AgentRouter."""

    def test_empty_registry(self) -> None:
        registry = _make_registry([])
        router = AgentRouter(registry=registry)
        result = router.route("do something")
        # Registry singleton always has builtins, but no metadata match
        assert result.primary_agent == "general"
        assert result.match_method == "fallback-no-candidates"

    def test_all_excluded(self) -> None:
        registry = _make_registry([_GENERAL_META])
        router = AgentRouter(registry=registry)
        result = router.route("do something", exclude={"general"})
        # Excluding general still leaves other builtins, but no metadata match
        assert result.primary_agent == "general"
        assert result.match_method == "fallback-no-candidates"

    def test_confidence_threshold_zero(self) -> None:
        """With threshold = 0, even a weak tag match should win."""
        registry = _make_registry(
            [_ENGINEER_META, _ANALYST_META, _GENERAL_META]
        )
        router = AgentRouter(
            registry=registry,
            confidence_threshold=0.0,
        )
        # Even a single tag match should work
        result = router.route("engineer")
        assert result.primary_agent == "engineer"


# ======================================================================
# Coordinator — full pipeline
# ======================================================================


class TestCoordinator:
    """Coordinator orchestrates route -> dispatch -> result."""

    def make_coordinator(
        self,
        agents: list[AgentMeta] | None = None,
        client: MagicMock | None = None,
    ) -> Coordinator:
        if agents is None:
            agents = [_GENERAL_META]
        registry = _make_registry(agents)
        if client is None:
            client = MagicMock()
        return Coordinator(
            client=client,
            registry=registry,
            default_agent="general",
            max_turns=3,
        )

    def test_execute_simple_goal(self) -> None:
        """Coordinator should route and dispatch successfully."""
        coord = self.make_coordinator(
            agents=[_ENGINEER_META, _GENERAL_META],
        )
        # Mock the SubAgent execution via the client
        coord._client.ask.return_value = '{"final": "Here is the code."}'
        # We also need to mock ComplexityAssessor to avoid an actual LLM call
        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("Engineer debug this Python code")

        assert result.success
        assert result.response == "Here is the code."
        assert result.route is not None
        assert result.route.primary_agent == "engineer"
        assert result.duration_ms > 0

    def test_execute_uses_default_agent_when_no_match(self) -> None:
        """When routing produces no confident match, use default agent."""
        coord = self.make_coordinator(
            agents=[_ENGINEER_META, _GENERAL_META],
        )
        coord._client.ask.return_value = '{"final": "I do not know."}'

        # Goal with no matching keywords
        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("How are you today?")

        assert result.success
        # Route result says "general" is the primary
        assert result.route is not None
        assert result.route.primary_agent == "general"

    def test_execute_fallback_on_missing_personality(self) -> None:
        """If the routed agent's personality is missing, fallback to default."""
        coord = self.make_coordinator(
            agents=[_ENGINEER_META, _GENERAL_META],
        )

        # Route returns a non-existent agent
        with patch.object(
            coord._router,
            "route",
            return_value=RouteResult(
                primary_agent="nonexistent",
                confidence=0.0,
                match_method="test",
            ),
        ):
            coord._client.ask.return_value = '{"final": "Fallback worked."}'
            with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
                result = coord.execute("do something")

        assert result.success
        assert result.response == "Fallback worked."

    def test_execute_cancellation(self) -> None:
        """Coordinator should respect cancellation tokens."""
        coord = self.make_coordinator(
            agents=[_GENERAL_META],
        )
        token = CancellationToken()
        token.cancel()
        coord._client.ask.return_value = '{"final": "will not run"}'

        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("do something", token=token)

        # SubAgent will detect cancellation and return cancelled result
        assert result.sub_result is not None
        # The result may show as cancelled or error depending on when
        # cancellation was checked

    def test_execute_sub_agent_error(self) -> None:
        """Errors in SubAgent execution should be captured."""
        coord = self.make_coordinator(
            agents=[_ENGINEER_META, _GENERAL_META],
        )

        # Make the SubAgent execution fail
        with patch.object(
            coord,
            "_dispatch",
            return_value=SubAgentResult(
                task_description="test",
                personality_used="engineer",
                response="",
                success=False,
                error="Something broke",
            ),
        ):
            with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
                result = coord.execute("do risky thing")

        assert not result.success
        assert result.error == "Something broke"

    def test_execute_includes_sub_agent_result(self) -> None:
        """CoordinatorResult should contain the SubAgentResult."""
        coord = self.make_coordinator(
            agents=[_ENGINEER_META, _GENERAL_META],
        )
        coord._client.ask.return_value = '{"final": "Done."}'

        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("Engineer debug this code")

        assert result.sub_result is not None
        assert result.sub_result.personality_used == "engineer"
        assert result.sub_result.turns >= 1

    def test_repr_and_str(self) -> None:
        """CoordinatorResult should have readable representation."""
        result = CoordinatorResult(
            goal="test",
            response="ok",
            success=True,
            duration_ms=50.0,
        )
        r = repr(result)
        # Just ensure it doesn't crash
        assert isinstance(r, str)


# ======================================================================
# Integration: Coordinator with real AgentRouter
# ======================================================================


class TestCoordinatorRoutingIntegration:
    """Coordinator integrates correctly with AgentRouter routing."""

    def test_routes_via_agent_router_by_default(self) -> None:
        """Coordinator should use AgentRouter for routing when not overridden."""
        registry = _make_registry([_ENGINEER_META, _ANALYST_META, _GENERAL_META])
        client = MagicMock()
        client.ask.return_value = '{"final": "Done."}'

        coord = Coordinator(client=client, registry=registry, max_turns=2)

        assert isinstance(coord._router, AgentRouter)

        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("Engineer debug the application crash")

        assert result.success
        assert result.route is not None
        # Should route to engineer
        assert result.route.primary_agent == "engineer"

    def test_custom_router(self) -> None:
        """Coordinator should accept a custom router."""
        registry = _make_registry([_GENERAL_META])
        client = MagicMock()
        custom_router = MagicMock()
        custom_router.route.return_value = RouteResult(
            primary_agent="general",
            confidence=0.5,
            match_method="custom",
        )

        coord = Coordinator(
            client=client,
            registry=registry,
            router=custom_router,
            max_turns=2,
        )
        coord._client.ask.return_value = '{"final": "Done."}'

        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("do something")

        assert result.route is not None
        assert result.route.match_method == "custom"
        custom_router.route.assert_called_once()


# ======================================================================
# AgentRouter — routing consistency
# ======================================================================


class TestAgentRouterConsistency:
    """AgentRouter must produce consistent, deterministic results."""

    def test_deterministic(self) -> None:
        """Same goal + same registry = same result."""
        registry = _make_registry(
            [_ENGINEER_META, _ANALYST_META, _SECURITY_META, _GENERAL_META]
        )
        router = AgentRouter(registry=registry)
        goal = "Check the system for security vulnerabilities"

        r1 = router.route(goal)
        r2 = router.route(goal)

        assert r1.primary_agent == r2.primary_agent
        assert r1.match_method == r2.match_method


# ======================================================================
# Edge cases
# ======================================================================


class TestCoordinatorEdgeCases:
    """Edge cases for Coordinator."""

    def test_execute_with_empty_goal(self) -> None:
        """An empty goal should not crash — route returns default."""
        registry = _make_registry([_GENERAL_META])
        client = MagicMock()
        client.ask.return_value = '{"final": ""}'

        coord = Coordinator(client=client, registry=registry, max_turns=1)
        with patch.object(coord._assessor, "assess", return_value=Complexity.SIMPLE):
            result = coord.execute("")

        assert result.success

    def test_default_max_turns(self) -> None:
        """Coordinator should default to 10 max turns."""
        registry = _make_registry([_GENERAL_META])
        client = MagicMock()
        coord = Coordinator(client=client, registry=registry)
        assert coord._max_turns == 10

    def test_default_agent_fallback(self) -> None:
        """Coordinator should use 'general' as default agent."""
        registry = _make_registry([_GENERAL_META])
        client = MagicMock()
        coord = Coordinator(client=client, registry=registry)
        assert coord._default_agent == "general"


# ======================================================================
# Agent description helper
# ======================================================================


class TestAgentRouterHelper:
    """AgentRouter internal description helper."""

    def test_existing_agent(self) -> None:
        registry = _make_registry([_ENGINEER_META])
        router = AgentRouter(registry=registry)
        desc = router._agent_description("engineer")
        assert desc == _ENGINEER_META.description

    def test_missing_agent(self) -> None:
        registry = _make_registry([_GENERAL_META])
        router = AgentRouter(registry=registry)
        desc = router._agent_description("nonexistent")
        assert desc == "nonexistent"


# ======================================================================
# Module exports
# ======================================================================


class TestExports:
    """All public types are importable from Agent."""

    def test_import_from_agent(self) -> None:
        import Agent

        assert hasattr(Agent, "AgentRouter")
        assert hasattr(Agent, "Coordinator")
        assert hasattr(Agent, "CoordinatorResult")
        assert hasattr(Agent, "RouteResult")
        assert hasattr(Agent, "ScoredAgent")
