"""ToolRuntime — central tool registry, executor, and orchestration facade.

This module implements the ABCs defined in ``fiona.tools.interfaces``.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fiona.tools.interfaces import ITool, IToolExecutor, IToolRegistry
from fiona.tools.models import (
    ToolCall,
    ToolCategory,
    ToolContext,
    ToolLimits,
    ToolResult,
    ToolSpec,
)
from Agent.adapters.ollama_adapter import tool_spec_to_ollama
from SciRetrieval.scitools.registry import SciToolRegistry


class ToolRegistry(IToolRegistry):
    """Central registry that aggregates tools from all sources.

    Receives tools from SciToolRegistry, Agent commands, and other
    subsystems.  Exports them as Ollama-compatible tool definitions.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}
        self._tool_sources: dict[str, str] = {}

    def register(self, tool: ITool, source: str = "internal") -> None:
        """Register a tool under its ``spec.name``.

        Args:
            tool: The tool instance.
            source: Human-readable source label for debugging.

        Raises:
            ValueError: A tool with the same name is already registered.
        """
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(
                f"Tool {name!r} already registered (existing source: "
                f"{self._tool_sources.get(name, 'unknown')}, "
                f"new source: {source})"
            )
        self._tools[name] = tool
        self._tool_sources[name] = source

    def get(self, name: str) -> ITool | None:
        """Look up a tool by name.

        Returns:
            The registered :class:`ITool`, or *None* if not found.
        """
        return self._tools.get(name)

    def list(self) -> list[ToolSpec]:
        """Return specs for all registered tools."""
        return [t.spec for t in self._tools.values()]

    def list_by_category(self, category: ToolCategory) -> list[ToolSpec]:
        """Return specs for tools matching the given category.

        Args:
            category: The :class:`ToolCategory` to filter by.

        Returns:
            List of matching :class:`ToolSpec` objects.
        """
        return [
            t.spec for t in self._tools.values() if t.spec.category == category
        ]

    def to_ollama_tools(self) -> list[dict]:
        """Export all registered tools as Ollama ``/api/chat`` tool definitions."""
        return [tool_spec_to_ollama(t.spec) for t in self._tools.values()]

    @classmethod
    def create_default(cls) -> ToolRegistry:
        """Create a registry pre-populated with all built-in tools.

        Seeds from :meth:`SciToolRegistry.create_default`,
        :func:`SeeOnDesk.tools.register_desk_tools`, and can be
        extended with additional tools afterward.
        """
        registry = cls()
        sci_registry = SciToolRegistry.create_default()
        for spec in sci_registry.list_specs():
            tool = sci_registry.get(spec.name)
            if tool is not None:
                registry.register(tool, source="scitools")
        try:
            from SeeOnDesk.tools import register_desk_tools

            register_desk_tools(registry)
        except ImportError:
            pass
        try:
            from Communications.email_tools import register_email_tools

            register_email_tools(registry)
        except ImportError:
            pass
        return registry


class ToolExecutor(IToolExecutor):
    """Executes tool calls by routing to the correct implementation.

    Handles:

    - Tool lookup in the registry
    - ToolContext construction
    - Execution with timeout
    - Error handling per tool (never crashes the agent)
    - Limit enforcement
    """

    def __init__(
        self,
        registry: ToolRegistry,
        limits: ToolLimits | None = None,
    ) -> None:
        self._registry = registry
        self._limits = limits or ToolLimits()
        self._round_count: int = 0

    @property
    def limits(self) -> ToolLimits:
        return self._limits

    @property
    def round_count(self) -> int:
        return self._round_count

    def reset_round_count(self) -> None:
        self._round_count = 0

    async def execute(
        self, call: ToolCall, context: ToolContext | None = None
    ) -> ToolResult:
        """Execute a single tool call.

        Args:
            call: The canonical :class:`ToolCall` with name + arguments.
            context: Optional :class:`ToolContext`; creates a default one
                if *None*.

        Returns:
            :class:`ToolResult` — always returns a result, never raises.
        """
        ctx = context or ToolContext(logger=logging.getLogger(__name__))
        self._round_count += 1

        tool = self._registry.get(call.function_name)
        if tool is None:
            return ToolResult(
                success=False,
                content=f"Unknown tool: {call.function_name}",
                error=f"No tool registered with name '{call.function_name}'",
            )

        # Enforce execution time limit
        start = time.monotonic()
        try:
            result = await tool.run(context=ctx, **call.arguments)
            elapsed = time.monotonic() - start
            if elapsed > self._limits.max_execution_time_seconds:
                return ToolResult(
                    success=False,
                    content=(
                        f"Tool {call.function_name} exceeded time limit "
                        f"({elapsed:.1f}s > "
                        f"{self._limits.max_execution_time_seconds}s)"
                    ),
                    error="timeout",
                )
            return result
        except Exception as exc:
            elapsed = time.monotonic() - start
            ctx.logger.error(
                "Tool %s failed after %.1fs: %s",
                call.function_name,
                elapsed,
                exc,
            )
            return ToolResult(
                success=False,
                content=f"Tool {call.function_name} failed: {exc}",
                error=str(exc),
            )

    async def execute_many(
        self,
        calls: list[ToolCall],
        context: ToolContext | None = None,
    ) -> list[ToolResult]:
        """Execute multiple tool calls.

        Independent calls can be parallelized.  For now, sequential is
        fine (parallel ``asyncio.gather`` can be added later).
        """
        results: list[ToolResult] = []
        for call in calls[: self._limits.max_tool_calls_per_round]:
            result = await self.execute(call, context)
            results.append(result)
        return results


class ToolRuntime:
    """Facade that combines :class:`ToolRegistry` + :class:`ToolExecutor`.

    This is what ``AgentOrchestrator`` imports and uses.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        executor: ToolExecutor | None = None,
    ) -> None:
        self.registry = registry or ToolRegistry.create_default()
        self.executor = executor or ToolExecutor(self.registry)

    def get_ollama_tools(self) -> list[dict]:
        """Return all tools in Ollama ``/api/chat`` format."""
        return self.registry.to_ollama_tools()

    async def execute_tool(
        self, call: ToolCall, context: ToolContext | None = None
    ) -> ToolResult:
        """Execute a single tool call through the executor."""
        return await self.executor.execute(call, context)

    async def execute_tool_calls(
        self,
        calls: list[ToolCall],
        context: ToolContext | None = None,
    ) -> list[ToolResult]:
        """Execute multiple tool calls."""
        return await self.executor.execute_many(calls, context)

    def reset(self) -> None:
        """Reset round counter for a new conversation."""
        self.executor.reset_round_count()
