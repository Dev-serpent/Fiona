"""Milestone 4: Advanced Orchestration Engine.

Provides:
- Complexity assessment (simple/moderate/complex) via LLM
- Task decomposition into sub-goals via LLM with validation
- Sub-agent ReAct execution loop with permission enforcement
- Topological execution planning (parallel/sequential layers)
- Result synthesis via foreman coordinator
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from Agent.cancellation import CancellationToken, CancelledError
from Agent.chat_store import ChatStore
from Agent.ollama import OllamaClient, OllamaError
from Agent.permission import AgentPermissionError, PermissionEnforcer, SafeActionRouter
from Agent.personality import Personality, PersonalityRegistry

logger = logging.getLogger(__name__)


# ======================================================================
# 1a. Enums & Config
# ======================================================================


class Complexity(enum.Enum):
    """Complexity classification for user goals."""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ForemanConfig:
    """Configuration knobs for the ForemanAgent orchestration pipeline."""
    parallel_by_default: bool = False
    max_sub_agents: int = 5
    max_turns_per_sub_agent: int = 10
    max_plan_retries: int = 2
    context_max_tokens: int = 2048
    default_personality: str = "general"

    @classmethod
    def from_agent_config(cls, agent_config: Any) -> ForemanConfig:
        """Build from an ``AgentConfig`` (lazy import to avoid circular deps).

        Args:
            agent_config: An ``Agent.config.AgentConfig`` instance.

        Returns:
            A new ``ForemanConfig`` with values mapped from the agent config.
        """
        return cls(
            parallel_by_default=agent_config.parallel_by_default,
            max_sub_agents=agent_config.max_sub_agents,
            max_turns_per_sub_agent=agent_config.max_turns_per_sub_agent,
            max_plan_retries=agent_config.max_plan_retries,
            context_max_tokens=agent_config.context_max_tokens,
            default_personality=agent_config.default_agent,
        )


# ======================================================================
# 1b. PlanValidationError
# ======================================================================


class PlanValidationError(RuntimeError):
    """Raised when an LLM-generated plan fails schema validation."""
    pass


# ======================================================================
# 1c. SubGoalSpec & TaskPlan
# ======================================================================


@dataclass(frozen=True)
class SubGoalSpec:
    """A single sub-goal within a decomposed TaskPlan."""
    id: str
    description: str
    assigned_personality: str
    depends_on: tuple[str, ...] = ()
    parallel: bool = False


@dataclass(frozen=True)
class TaskPlan:
    """A decomposed plan consisting of multiple sub-goals with dependencies."""
    goal: str
    sub_goals: tuple[SubGoalSpec, ...]

    # ------------------------------------------------------------------
    # LLM-based plan generation
    # ------------------------------------------------------------------

    @classmethod
    def from_llm(
        cls,
        client: OllamaClient,
        goal: str,
        *,
        max_retries: int = 2,
        registry: PersonalityRegistry | None = None,
        max_sub_goals: int = 5,
    ) -> TaskPlan:
        """Ask an LLM to decompose *goal* into sub-goals.

        Parameters
        ----------
        client:
            Ollama client for LLM calls.
        goal:
            The user's original goal.
        max_retries:
            Number of retries on validation failure.
        registry:
            Personality registry for validation.  If ``None`` the
            global singleton is used.
        max_sub_goals:
            Maximum sub-goals the LLM should generate.

        Returns
        -------
        TaskPlan
            Validated task plan.

        Raises
        ------
        PlanValidationError
            If all retries are exhausted.
        """
        registry = registry or PersonalityRegistry.get_instance()
        available = "\n".join(
            f"  - {p.name}: {p.description}" for p in registry.list()
        )

        prompt = _DECOMPOSITION_PROMPT_TEMPLATE.format(
            goal=goal,
            max_sub_goals=max_sub_goals,
            personalities=available,
        )

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = client.ask(
                    prompt=prompt,
                    system_prompt=(
                        "You are a task decomposition specialist. "
                        "Output ONLY valid JSON, no other text."
                    ),
                )
                data = cls._parse_llm_json(response)
                if data is None:
                    raise PlanValidationError(
                        f"LLM response did not contain valid JSON: {response[:200]}"
                    )

                sub_goal_dicts = data.get("sub_goals")
                if not isinstance(sub_goal_dicts, list) or len(sub_goal_dicts) == 0:
                    raise PlanValidationError(
                        "LLM response missing 'sub_goals' list"
                    )

                specs: list[SubGoalSpec] = []
                for sg in sub_goal_dicts:
                    if not isinstance(sg, dict):
                        raise PlanValidationError(
                            f"Sub-goal entry is not a dict: {sg!r}"
                        )
                    sid = sg.get("id", "")
                    if not isinstance(sid, str) or not sid.strip():
                        raise PlanValidationError(
                            f"Sub-goal missing valid 'id': {sg!r}"
                        )
                    desc = sg.get("description", "")
                    if not isinstance(desc, str) or not desc.strip():
                        raise PlanValidationError(
                            f"Sub-goal '{sid}' missing valid 'description'"
                        )
                    personality_name = sg.get("assigned_personality", "")
                    if not isinstance(personality_name, str) or not personality_name.strip():
                        raise PlanValidationError(
                            f"Sub-goal '{sid}' missing valid 'assigned_personality'"
                        )
                    depends = sg.get("depends_on", [])
                    if not isinstance(depends, (list, tuple)):
                        depends = ()
                    depends_tuple = tuple(str(d) for d in depends)
                    parallel = bool(sg.get("parallel", False))

                    specs.append(SubGoalSpec(
                        id=sid,
                        description=desc,
                        assigned_personality=personality_name,
                        depends_on=depends_tuple,
                        parallel=parallel,
                    ))

                plan = cls(goal=goal, sub_goals=tuple(specs))
                plan.validate(registry=registry)
                return plan

            except PlanValidationError as exc:
                last_error = exc
                logger.warning(
                    "Plan validation failed (attempt %d/%d): %s",
                    attempt + 1, max_retries + 1, exc,
                )
            except (OllamaError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1, max_retries + 1, exc,
                )

        raise PlanValidationError(
            f"Failed to generate valid plan after {max_retries + 1} attempt(s): {last_error}"
        )

    @staticmethod
    def _parse_llm_json(text: str) -> dict[str, Any] | None:
        """Extract a JSON object from LLM response text."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            if isinstance(data, dict):
                return data
            return None
        except (ValueError, json.JSONDecodeError):
            return None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, registry: PersonalityRegistry | None = None) -> None:
        """Validate the plan.

        Checks:
        - All sub_goals have unique IDs.
        - All ``depends_on`` references exist.
        - No circular dependencies.
        - ``assigned_personality`` values are valid registry names.

        Raises ``PlanValidationError`` on failure.
        """
        registry = registry or PersonalityRegistry.get_instance()

        # -- unique IDs -------------------------------------------------
        ids_seen: set[str] = set()
        for sg in self.sub_goals:
            if sg.id in ids_seen:
                raise PlanValidationError(
                    f"Duplicate sub-goal ID: {sg.id!r}"
                )
            ids_seen.add(sg.id)

        # -- all depends_on references exist ----------------------------
        all_ids = {sg.id for sg in self.sub_goals}
        for sg in self.sub_goals:
            for dep in sg.depends_on:
                if dep not in all_ids:
                    raise PlanValidationError(
                        f"Sub-goal {sg.id!r} depends on unknown ID {dep!r}"
                    )

        # -- no circular dependencies -----------------------------------
        if self._detect_cycles(list(self.sub_goals)):
            raise PlanValidationError(
                "Circular dependency detected in task plan"
            )

        # -- valid personality names ------------------------------------
        for sg in self.sub_goals:
            try:
                registry.get(sg.assigned_personality)
            except KeyError:
                raise PlanValidationError(
                    f"Sub-goal {sg.id!r} references unknown personality "
                    f"{sg.assigned_personality!r}"
                )

    # ------------------------------------------------------------------
    # Topological sort
    # ------------------------------------------------------------------

    def execution_order(self) -> list[list[SubGoalSpec]]:
        """Topological sort: returns layers of parallel-independent tasks.

        Each inner list contains tasks that can execute in parallel.
        Outer list must be executed sequentially in order.
        """
        remaining = {sg.id: sg for sg in self.sub_goals}
        # Build dependency counts
        in_degree: dict[str, int] = {}
        for sg in self.sub_goals:
            in_degree[sg.id] = len(sg.depends_on)

        layers: list[list[SubGoalSpec]] = []

        while remaining:
            # Find nodes with no remaining dependencies
            ready = [
                sg for sg_id, sg in remaining.items()
                if in_degree[sg_id] == 0
            ]
            if not ready:
                # Should not happen if validate() was called, but guard
                raise PlanValidationError(
                    "Cannot compute execution order: remaining nodes "
                    "all have unsatisfied dependencies"
                )

            layers.append(ready)

            # Remove ready nodes
            for sg in ready:
                del remaining[sg.id]
                # Decrease in-degree for dependents
                for other_id, other_sg in remaining.copy().items():
                    if sg.id in other_sg.depends_on:
                        in_degree[other_id] -= 1

        return layers

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_cycles(specs: list[SubGoalSpec]) -> bool:
        """DFS-based cycle detection in the dependency graph.

        Returns ``True`` if a cycle exists.
        """
        adj: dict[str, list[str]] = {sg.id: list(sg.depends_on) for sg in specs}
        WHITE, GRAY, BLACK = 0, 1, 2
        colour: dict[str, int] = {sg_id: WHITE for sg_id in adj}

        def dfs(node: str) -> bool:
            if colour[node] == GRAY:
                return True  # back-edge = cycle
            if colour[node] == BLACK:
                return False
            colour[node] = GRAY
            for neighbour in adj.get(node, []):
                if neighbour in colour and dfs(neighbour):
                    return True
            colour[node] = BLACK
            return False

        for node in adj:
            if colour[node] == WHITE:
                if dfs(node):
                    return True
        return False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "goal": self.goal,
            "sub_goals": [
                {
                    "id": sg.id,
                    "description": sg.description,
                    "assigned_personality": sg.assigned_personality,
                    "depends_on": list(sg.depends_on),
                    "parallel": sg.parallel,
                }
                for sg in self.sub_goals
            ],
        }


# ======================================================================
# Decomposition prompt template (module-level constant)
# ======================================================================

_DECOMPOSITION_PROMPT_TEMPLATE = """\
You are a task decomposition specialist. Break down the following goal into \
at most {max_sub_goals} sub-goals that can be executed by specialized agent personalities.

Goal: {goal}

Available personalities:
{personalities}

For each sub-goal, specify:
- id: a unique identifier (e.g., "step-1", "step-2")
- description: what needs to be done
- assigned_personality: which personality should handle this \
(must be one of the available personalities listed above)
- depends_on: list of sub-goal IDs that must complete first \
(empty list for no dependencies)
- parallel: whether this sub-goal can run in parallel with others \
at the same dependency level

Respond with ONLY valid JSON in the following structure (no other text):
{{
  "sub_goals": [
    {{
      "id": "step-1",
      "description": "...",
      "assigned_personality": "...",
      "depends_on": [],
      "parallel": false
    }}
  ]
}}"""


# ======================================================================
# 1d. ComplexityAssessor
# ======================================================================


class ComplexityAssessor:
    """LLM-based complexity classifier.

    Sends the goal to an LLM and asks it to classify as
    ``simple``, ``moderate``, or ``complex``.
    """

    _CLASSIFICATION_PROMPT = """\
Classify the following user request as 'simple', 'moderate', or 'complex'.

Simple: Can be answered with one tool call or immediate knowledge.
Moderate: Requires 2-3 steps but a single agent can handle it.
Complex: Requires multiple specialized agents working in sequence.

Request: {goal}

Respond with ONLY a JSON object: {{"classification": "simple", "reason": "..."}}
"""

    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    def assess(self, goal: str) -> Complexity:
        """Send *goal* to LLM for complexity classification.

        Returns ``Complexity`` enum on success.
        Falls back to ``Complexity.MODERATE`` on error.
        """
        try:
            prompt = self._CLASSIFICATION_PROMPT.format(goal=goal)
            response = self._client.ask(
                prompt=prompt,
                temperature=0.1,
                max_tokens=128,
            )
            data = self._extract_json(response)
            if data is None:
                logger.warning(
                    "ComplexityAssessor: could not parse JSON from LLM response"
                )
                return Complexity.MODERATE

            raw = data.get("classification", "").strip().lower()
            for c in Complexity:
                if c.value == raw:
                    return c

            logger.warning(
                "ComplexityAssessor: unrecognised classification %r, "
                "falling back to MODERATE",
                raw,
            )
            return Complexity.MODERATE

        except CancelledError:
            raise
        except (OllamaError, json.JSONDecodeError, Exception) as exc:
            logger.warning(
                "ComplexityAssessor: error during assessment (%s), "
                "falling back to MODERATE",
                exc,
            )
            return Complexity.MODERATE

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Extract a JSON object from text that may have surrounding content."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            if isinstance(data, dict):
                return data
            return None
        except (ValueError, json.JSONDecodeError):
            return None


# ======================================================================
# 1e. SubAgentResult & SubAgent
# ======================================================================


@dataclass
class SubAgentResult:
    """Outcome of a single sub-agent execution."""
    task_description: str
    personality_used: str
    response: str
    success: bool = True
    error: str | None = None
    turns: int = 0
    duration_ms: float = 0.0
    cancelled: bool = False


class SubAgent:
    """A personality-wrapped agent using SafeActionRouter for tool access.

    Executes a ReAct loop:
    Think -> Act -> Observe -> Repeat until final answer or max turns.
    """

    def __init__(
        self,
        personality: Personality,
        client: OllamaClient,
        router: SafeActionRouter,
        *,
        max_turns: int = 10,
    ) -> None:
        self._personality = personality
        self._client = client
        self._router = router
        self._max_turns = max_turns
        self._turns_taken: int = 0
        self._history: list[tuple[str, str, str]] = []  # (action, input_str, observation)

    @property
    def turns(self) -> int:
        """Return the number of turns from the last ``execute()`` call."""
        return self._turns_taken

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        goal: str,
        token: CancellationToken,
        on_turn: Callable[[str], None] | None = None,
    ) -> str:
        """ReAct loop.

        Each turn:
        1. Checks ``CancellationToken``.
        2. Sends context + prompt to LLM.
        3. Parses JSON response — expects either ``final`` or ``action``.
        4. If ``action``: executes via ``SafeActionRouter.run()``.
        5. Appends observation to conversation history.
        6. Repeats until final answer or ``max_turns``.

        Returns the final response string.
        """
        self._turns_taken = 0
        self._history = []
        system_prompt = self._personality.system_prompt

        for turn_idx in range(1, self._max_turns + 1):
            token.raise_if_cancelled()
            self._turns_taken = turn_idx

            prompt = self._build_react_prompt(goal)
            response = self._client.ask(
                prompt=prompt,
                system_prompt=system_prompt,
            )

            if on_turn:
                on_turn(response)

            data = self._extract_json(response)
            if data is None:
                # If we cannot parse JSON, treat the raw response as final
                logger.debug(
                    "SubAgent: could not parse JSON from LLM (turn %d), "
                    "treating as final answer",
                    turn_idx,
                )
                return response

            # Check for final answer
            final = data.get("final")
            if final is not None:
                return str(final)

            # Check for action
            action_name = data.get("action")
            if not action_name:
                # No action and no final — use thought or raw response
                return data.get("thought", response)

            action_input = data.get("input", {})
            input_str = json.dumps(action_input) if action_input else "{}"

            # Execute the action via SafeActionRouter
            try:
                result = self._router.run_with_fallback(action_name, source="agent")
                if result.ok:
                    observation = result.detail
                else:
                    observation = f"Failed: {result.detail}"
            except Exception as exc:
                observation = f"Error: {exc}"

            self._history.append((action_name, input_str, observation))

            if on_turn:
                on_turn(f"  -> {action_name}: {observation}")

        # Max turns reached — return the accumulated context
        return (
            f"Reached maximum of {self._max_turns} turns. "
            f"Last state: {self._format_history()}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_react_prompt(self, goal: str) -> str:
        """Build the ReAct prompt for the current turn."""
        parts: list[str] = [f"Goal: {goal}"]

        for action_name, input_str, observation in self._history:
            parts.append(f"Action: {action_name}")
            parts.append(f"Input: {input_str}")
            parts.append(f"Observation: {observation}")

        parts.append("")
        # ---- Available tools/apps (visible to the LLM) -----------------------
        from Agent import command_registry
        registry = command_registry()
        parts.append("AVAILABLE COMMANDS:")
        parts.append(json.dumps(registry["commands"], indent=2))
        parts.append("AVAILABLE APPLICATIONS (use with launch_binding):")
        parts.append(json.dumps(registry["apps"], indent=2))
        parts.append("")
        # ---- Action-selection instruction ------------------------------------
        parts.append(
            "Think step by step. Respond with JSON using ONE of these formats:\n"
            '{"thought": "...", "final": "Your final answer here"}\n'
            "OR\n"
            '{"thought": "...", "action": "<tool_name>", "input": {...}}'
        )

        return "\n".join(parts)

    def _format_history(self) -> str:
        """Format history for the max-turns-reached message."""
        if not self._history:
            return "No actions taken."
        entries = []
        for i, (action, inp, obs) in enumerate(self._history, 1):
            entries.append(
                f"  [{i}] {action}({inp}) -> {obs}"
            )
        return "\n".join(entries)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        """Extract a JSON object from text that may have surrounding content."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            return data if isinstance(data, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None


# ======================================================================
# 1f. ForemanAgent
# ======================================================================

_SUB_AGENT_RESULT_TEMPLATE = """\
--- Sub-goal: {task_description} ---
Personality: {personality_used}
Status: {status}
Response: {response}
"""

_SYNTHESIS_PROMPT_TEMPLATE = """\
You are a foreman coordinator. Synthesize the following sub-agent results \
into a coherent final response for the user.

Original goal: {goal}

Sub-agent results:
{results}

Provide a clear, concise response that addresses the user's original goal. \
If any sub-goal failed or was cancelled, mention that briefly. \
Do not describe the internal orchestration — just present the final result.
"""


class ForemanAgent:
    """High-level orchestration agent.

    Pipeline:
    1. Complexity gate (LLM-based classification).
    2. Simple goals → single SubAgent directly.
    3. Moderate/complex goals → decompose via ``TaskPlan.from_llm()``.
    4. Execute sub-goals in topological order (sequential or parallel).
    5. Synthesize results into a final response.
    """

    def __init__(
        self,
        client: OllamaClient,
        registry: PersonalityRegistry,
        chat_store: ChatStore | None = None,
        config: ForemanConfig | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._chat_store = chat_store
        self._config = config if config is not None else ForemanConfig()
        self._assessor = ComplexityAssessor(client)

    @classmethod
    def from_agent_config(
        cls,
        client: OllamaClient,
        registry: PersonalityRegistry,
        agent_config: Any,  # Agent.config.AgentConfig
        chat_store: ChatStore | None = None,
    ) -> ForemanAgent:
        """Create a ``ForemanAgent`` from an ``AgentConfig``.

        Args:
            client: Ollama LLM client.
            registry: Personality / agent registry.
            agent_config: An ``AgentConfig`` instance with orchestration settings.
            chat_store: Optional chat persistence store.

        Returns:
            A configured ``ForemanAgent``.
        """
        foreman_config = ForemanConfig.from_agent_config(agent_config)
        return cls(
            client=client,
            registry=registry,
            chat_store=chat_store,
            config=foreman_config,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        goal: str,
        personality: str = "general",
        token: CancellationToken | None = None,
    ) -> str:
        """Full orchestration pipeline.

        Parameters
        ----------
        goal:
            The user's goal/request.
        personality:
            Default personality for simple goals.
        token:
            Optional cancellation token checked throughout execution.

        Returns
        -------
        str
            Final synthesized response.
        """
        token = token or CancellationToken()

        # Step 1: Assess complexity
        complexity = self._assess(goal)
        logger.info("ForemanAgent: complexity=%s for goal=%r", complexity.value, goal)

        # Step 2: Simple path — single SubAgent
        if complexity == Complexity.SIMPLE:
            token.raise_if_cancelled()
            return self._run_simple(goal, personality, token)

        # Step 3: Moderate/complex — decompose & orchestrate
        try:
            plan = self._decompose(goal)
        except PlanValidationError as exc:
            logger.warning(
                "ForemanAgent: plan decomposition failed (%s), "
                "falling back to simple agent",
                exc,
            )
            token.raise_if_cancelled()
            return self._run_simple(goal, personality, token)

        # Step 4: Execute layers
        all_results: list[SubAgentResult] = []
        try:
            layers = plan.execution_order()
        except PlanValidationError:
            # Fall back to simple agent on order computation failure
            token.raise_if_cancelled()
            return self._run_simple(goal, personality, token)

        for layer in layers:
            token.raise_if_cancelled()

            # Split layer into parallel vs sequential sub-groups
            parallel_specs = [s for s in layer if s.parallel or self._config.parallel_by_default]
            sequential_specs = [s for s in layer if s not in parallel_specs]

            if parallel_specs:
                results = self._run_parallel(parallel_specs, token)
                all_results.extend(results)

            if sequential_specs:
                results = self._run_sequential(sequential_specs, token)
                all_results.extend(results)

            # Check if any execution was cancelled
            if any(r.cancelled for r in all_results):
                break

        # Step 5: Synthesize
        token.raise_if_cancelled()
        return self._synthesize(goal, all_results, token)

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _assess(self, goal: str) -> Complexity:
        """Assess complexity via LLM."""
        return self._assessor.assess(goal)

    def _decompose(self, goal: str) -> TaskPlan:
        """Decompose goal into a TaskPlan via LLM.

        Falls back to ``PlanValidationError`` if all retries exhausted.
        """
        return TaskPlan.from_llm(
            self._client,
            goal,
            max_retries=self._config.max_plan_retries,
            registry=self._registry,
            max_sub_goals=self._config.max_sub_agents,
        )

    def _run_simple(
        self,
        goal: str,
        personality_name: str,
        token: CancellationToken,
    ) -> str:
        """Execute a simple goal with a single SubAgent."""
        try:
            personality = self._registry.get(personality_name)
        except KeyError:
            personality = self._registry.get(self._config.default_personality)

        enforcer = PermissionEnforcer(personality)
        router = SafeActionRouter(enforcer)
        sub_agent = SubAgent(
            personality,
            self._client,
            router,
            max_turns=self._config.max_turns_per_sub_agent,
        )

        result = sub_agent.execute(goal, token)
        self._maybe_store(personality_name, goal, result)
        return result

    def _dispatch_sub_agent(
        self,
        spec: SubGoalSpec,
        token: CancellationToken,
    ) -> SubAgentResult:
        """Dispatch a single sub-goal to a SubAgent and collect the result."""
        start_time = time.perf_counter()

        try:
            personality = self._registry.get(spec.assigned_personality)
        except KeyError as exc:
            return SubAgentResult(
                task_description=spec.description,
                personality_used=spec.assigned_personality,
                response="",
                success=False,
                error=f"Unknown personality: {exc}",
                duration_ms=(time.perf_counter() - start_time) * 1000,
                cancelled=False,
            )

        enforcer = PermissionEnforcer(personality)
        router = SafeActionRouter(enforcer)
        sub_agent = SubAgent(
            personality,
            self._client,
            router,
            max_turns=self._config.max_turns_per_sub_agent,
        )

        try:
            response = sub_agent.execute(spec.description, token)
            duration_ms = (time.perf_counter() - start_time) * 1000
            result = SubAgentResult(
                task_description=spec.description,
                personality_used=spec.assigned_personality,
                response=response,
                success=True,
                turns=sub_agent.turns,
                duration_ms=duration_ms,
                cancelled=False,
            )
        except CancelledError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            result = SubAgentResult(
                task_description=spec.description,
                personality_used=spec.assigned_personality,
                response="",
                success=False,
                error="Cancelled",
                turns=sub_agent.turns,
                duration_ms=duration_ms,
                cancelled=True,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("SubAgent execution failed for %r", spec.id)
            result = SubAgentResult(
                task_description=spec.description,
                personality_used=spec.assigned_personality,
                response="",
                success=False,
                error=str(exc),
                turns=sub_agent.turns,
                duration_ms=duration_ms,
                cancelled=False,
            )

        self._maybe_store(spec.assigned_personality, spec.description, result.response)
        return result

    def _run_sequential(
        self,
        specs: list[SubGoalSpec],
        token: CancellationToken,
    ) -> list[SubAgentResult]:
        """Execute sub-goals sequentially."""
        results: list[SubAgentResult] = []
        for spec in specs:
            token.raise_if_cancelled()
            result = self._dispatch_sub_agent(spec, token)
            results.append(result)
            if result.cancelled:
                break
        return results

    def _run_parallel(
        self,
        specs: list[SubGoalSpec],
        token: CancellationToken,
    ) -> list[SubAgentResult]:
        """Execute sub-goals in parallel using threads.

        Note: due to the GIL and blocking I/O, ``concurrent.futures.ThreadPoolExecutor``
        provides effective parallelism for LLM-bound sub-agents.
        """
        import concurrent.futures

        results: list[SubAgentResult] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(specs)) as executor:
            future_map = {
                executor.submit(self._dispatch_sub_agent, spec, token): spec
                for spec in specs
            }
            for future in concurrent.futures.as_completed(future_map):
                try:
                    results.append(future.result())
                except Exception as exc:
                    # Note: CancelledError is caught inside _dispatch_sub_agent
                    # and returned as a SubAgentResult with cancelled=True, so
                    # it will never propagate here as an exception.
                    failed_spec = future_map[future]
                    failed_spec = future_map[future]
                    logger.exception("Parallel sub-agent failed for %r", failed_spec.id)
                    results.append(SubAgentResult(
                        task_description=failed_spec.description,
                        personality_used=failed_spec.assigned_personality,
                        response="",
                        success=False,
                        error=str(exc),
                    ))
        return results

    def _synthesize(
        self,
        goal: str,
        results: list[SubAgentResult],
        token: CancellationToken,
    ) -> str:
        """Synthesize sub-agent results into a final response via LLM."""
        token.raise_if_cancelled()

        if not results:
            return f"Goal: {goal}\n\nNo sub-agents were executed."

        formatted_parts: list[str] = []
        for i, r in enumerate(results, 1):
            status = "SUCCESS" if r.success else "FAILED"
            if r.cancelled:
                status = "CANCELLED"
            formatted_parts.append(
                _SUB_AGENT_RESULT_TEMPLATE.format(
                    task_description=r.task_description,
                    personality_used=r.personality_used,
                    status=status,
                    response=r.response if r.response else (r.error or "No response"),
                )
            )

        prompt = _SYNTHESIS_PROMPT_TEMPLATE.format(
            goal=goal,
            results="\n".join(formatted_parts),
        )

        try:
            # Use the default personality for synthesis
            personality = self._registry.get(self._config.default_personality)
            response = self._client.ask(
                prompt=prompt,
                system_prompt=personality.system_prompt,
            )
            return response
        except CancelledError:
            raise
        except (OllamaError, Exception) as exc:
            logger.warning("ForemanAgent: synthesis failed (%s), returning raw results", exc)
            # Fallback: format results as plain text
            parts = [f"Goal: {goal}", ""]
            for r in results:
                parts.append(f"- {r.task_description} ({r.personality_used}): "
                             f"{'OK' if r.success else 'FAILED'}")
                if r.response:
                    parts.append(f"  {r.response}")
            return "\n".join(parts)

    # ------------------------------------------------------------------
    # Storage helper
    # ------------------------------------------------------------------

    def _maybe_store(self, personality_name: str, description: str, response: str) -> None:
        """Store the interaction in the chat store if one is configured."""
        if self._chat_store is None:
            return
        try:
            session_id = self._chat_store.create_session(personality=personality_name)
            self._chat_store.add_message(
                session_id,
                "user",
                description,
                personality=personality_name,
            )
            self._chat_store.add_message(
                session_id,
                "agent",
                response,
                personality=personality_name,
            )
        except CancelledError:
            raise
        except Exception as exc:
            logger.warning("ForemanAgent: failed to store in chat store: %s", exc)
