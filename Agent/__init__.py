"""Fiona local-agent integration layer."""

from Agent.cancellation import CancellationToken, CancelledError
from Agent.chat_handler import AgentChatHandler
from Agent.chat_store import ChatMessage, ChatStore, ChatStoreError, estimate_tokens
from Agent.command_registry import CommandSpec, command_registry
from Agent.agent_manager import AgentInfo, AgentManager
from Agent.agent_meta import AgentMeta
from Agent.agent_loader import parse_agent_file, discover_agents, load_agent
from Agent.config import AgentConfig, load_agent_config
from Agent.coordinator import AgentRouter, Coordinator, CoordinatorResult, RouteResult, ScoredAgent
from Agent.skill import Skill, SkillRegistry, discover_skills, load_skill_from_yaml
from Agent.ollama import (
    ChatResponse,
    DEFAULT_OLLAMA_BASE_URL,
    OllamaClient,
    OllamaError,
    ToolCall,
)
LMStudioClient = OllamaClient
LMStudioError = OllamaError
from Agent.orchestration import (
    Complexity,
    ComplexityAssessor,
    ForemanAgent,
    ForemanConfig,
    PlanValidationError,
    SubAgent,
    SubAgentResult,
    SubGoalSpec,
    TaskPlan,
)
from Agent.orchestrator import AgentOrchestrator, AgentTurn, run_agent_goal
from Agent.permission import (
    AgentPermissionError,
    PermissionEnforcer,
    SafeActionRouter,
)
from Agent.personality import Personality, PersonalityRegistry
from Agent.query_detector import QueryDetector, QueryOrTask

__all__ = [
    "AgentChatHandler",
    "AgentInfo",
    "AgentManager",
    "AgentMeta",
    "AgentOrchestrator",
    "AgentPermissionError",
    "AgentRouter",
    "AgentTurn",
    "CancellationToken",
    "CancelledError",
    "ChatMessage",
    "ChatResponse",
    "ChatStore",
    "ChatStoreError",
    "CommandSpec",
    "Complexity",
    "ComplexityAssessor",
    "Coordinator",
    "CoordinatorResult",
    "DEFAULT_OLLAMA_BASE_URL",
    "discover_agents",
    "ForemanAgent",
    "ForemanConfig",
    "load_agent",
    "OllamaClient",
    "OllamaError",
    "LMStudioClient",
    "LMStudioError",
    "parse_agent_file",
    "PermissionEnforcer",
    "Personality",
    "PersonalityRegistry",
    "PlanValidationError",
    "QueryDetector",
    "QueryOrTask",
    "RouteResult",
    "SafeActionRouter",
    "ScoredAgent",
    "Skill",
    "SkillRegistry",
    "discover_skills",
    "load_skill_from_yaml",
    "SubAgent",
    "SubAgentResult",
    "SubGoalSpec",
    "TaskPlan",
    "ToolCall",
    "command_registry",
    "estimate_tokens",
    "run_agent_goal",
]
