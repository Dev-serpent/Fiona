from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from Agent import OllamaClient, command_registry
from Agent.ollama import OllamaError
from Agent.personality import PersonalityRegistry
from Agent.tool_runtime import ToolRuntime
from FionaCore import ActionRouter, ActionResult
from FionaCore.approval import (
    ApprovalManager, PlannedStep, PlanStatus,
    get_approval_manager,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentTurn:
    thought: str
    action_name: str | None = None
    action_input: dict[str, Any] | None = None
    observation: str | None = None


class AgentOrchestrator:
    """
    Manages the autonomous execution loop for Fiona's workstation assistant.
    Uses an LLM to select and execute tools from the command registry.
    """
    def __init__(self, client: OllamaClient | None = None,
                 approval_manager: ApprovalManager | None = None,
                 personality_name: str | None = None,
                 action_registry: Any | None = None):
        self.client = client or OllamaClient()
        self.router = ActionRouter()
        self.history: List[AgentTurn] = []
        self.max_turns = 10
        self.approval_manager = approval_manager or get_approval_manager()
        self._personality_name = personality_name  # None = use hardcoded prompt
        # Lazy import to keep the Agent package decoupled from fiona.actions
        if action_registry is not None:
            self._action_registry = action_registry
        else:
            try:
                from fiona.actions import ActionRegistry
                self._action_registry = ActionRegistry()
            except ImportError:
                self._action_registry = None

    def run_goal(self, goal: str) -> str:
        """Attempt to achieve a user goal through human-approved actions."""
        self.history = []
        
        system_prompt = self._build_system_prompt()
        
        # Phase 1: Generate plan (think only, don't execute yet)
        plan_steps = []
        
        for turn_idx in range(self.max_turns):
            current_prompt = (
                f"Goal: {goal}\n\n"
                f"Plan so far: {self._format_plan_steps(plan_steps)}\n\n"
                f"What is the next step? Think step by step."
            )
            
            response_text = self.client.ask(
                current_prompt,
                system_prompt=system_prompt,
            )
            
            turn = self._parse_response(response_text)
            self.history.append(turn)
            
            if not turn.action_name:
                # Agent thinks it's done planning
                break
            
            plan_steps.append(PlannedStep(
                step_number=len(plan_steps) + 1,
                action=turn.action_name,
                params=turn.action_input or {},
                reasoning=turn.thought,
                risk=self._estimate_risk(turn.action_name),
            ))
            
            if len(plan_steps) >= self.max_turns:
                break
        
        if not plan_steps:
            return "No actions planned. " + (self.history[-1].thought if self.history else "")
        
        # Phase 2: Submit for human approval
        plan_id = self.approval_manager.submit_plan(
            goal=goal,
            steps=plan_steps,
            agent_id="fiona-agent",
        )
        
        # Phase 3: Wait for human decision
        status = self.approval_manager.wait_for_approval(plan_id, timeout=300)
        
        if status != 'approved':
            plan = self.approval_manager.get_plan(plan_id)
            reason = plan.get('decision_reason', '') if plan else ''
            return f"Plan was {status}. {reason}"
        
        self.approval_manager.mark_executing(plan_id)
        
        # Phase 4: Execute the approved plan
        observations = []
        for step in plan_steps:
            observation = self._execute_action(step.action, step.params)
            observations.append(f"Step {step.step_number} ({step.action}): {observation}")
        
        summary = "\n".join(observations)
        self.approval_manager.mark_completed(plan_id, summary=summary)
        
        return f"Plan completed.\n{summary}"

    async def run_goal_async(
        self,
        goal: str,
        tool_runtime: ToolRuntime | None = None,
    ) -> str:
        """Attempt to achieve a user goal using Ollama's native function-calling loop.

        When *tool_runtime* is provided, tools are registered and the model can
        invoke them through Ollama's tool-calling protocol.  When *tool_runtime*
        is ``None``, falls back to plain text generation (no tools).

        Args:
            goal: The user's goal or request.
            tool_runtime: Optional :class:`ToolRuntime` providing tool definitions
                and execution.  If ``None``, no tools are advertised.

        Returns:
            The final response text, or an error message if something went wrong.
        """
        system_prompt = self._build_system_prompt()

        if tool_runtime is not None:
            tools = tool_runtime.get_ollama_tools()
            if tools:
                tool_names = [
                    t.get("function", {}).get("name", "unknown")
                    for t in tools
                ]
                tool_hint = (
                    "You have access to tools. When a user asks a question that "
                    "requires computation, lookup, or formatting, use the "
                    "appropriate tool instead of guessing. Available tools: "
                    f"{', '.join(tool_names)}"
                )
                system_prompt = system_prompt + "\n\n" + tool_hint
        else:
            tools = None

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": goal},
        ]

        for _round in range(self.max_turns):
            try:
                response = self.client.chat(messages=messages, tools=tools)
            except OllamaError as e:
                return f"Error communicating with Ollama: {e}"

            if response.finish_reason == "stop":
                return response.content or "Task completed."

            if response.tool_calls:
                # Append assistant message with tool_calls in Ollama's format
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content or "",
                }

                raw_tool_calls: list[dict[str, Any]] = []
                for tc in response.tool_calls:
                    raw_tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": tc.arguments,
                        },
                    })
                assistant_msg["tool_calls"] = raw_tool_calls
                messages.append(assistant_msg)

                # Execute each tool call and append its result
                for tc in response.tool_calls:
                    result = await tool_runtime.execute_tool(tc)
                    messages.append({
                        "role": "tool",
                        "content": result.content,
                        "tool_call_id": tc.id,
                    })
            else:
                # finish_reason is neither "stop" nor do we have tool_calls
                # (e.g. "length"). Return what we have.
                return response.content or "Task completed."

        return (
            f"Max turns ({self.max_turns}) reached. "
            f"Last response: {messages[-1].get('content', '')}"
        )

    def _build_system_prompt(self) -> str:
        registry = command_registry()
        commands_str = json.dumps(registry["commands"], indent=2)
        apps_str = json.dumps(registry["apps"], indent=2)
        tool_section = f"""
AVAILABLE TOOLS:
{commands_str}

AVAILABLE APPLICATIONS (use with launch_binding):
{apps_str}

OUTPUT FORMAT:
{{
  "thought": "Deconstruct the user's request. What is the current state? What tool will move us closer to the goal?",
  "action": "command_name_or_null",
  "input": {{ "arg": "value" }}
}}

If the goal is achieved, set "action" to null.
"""

        # If a personality is set, append tool info after its system prompt
        if self._personality_name:
            try:
                registry = PersonalityRegistry.get_instance()
                p = registry.get(self._personality_name)
                return p.system_prompt + "\n\n" + tool_section
            except KeyError:
                pass  # fall through to hardcoded prompt

        return f"""You are Fiona, a highly advanced local workstation control system. 
You are NOT a general-purpose AI assistant; you are the SYSTEM OPERATOR.

### ABSOLUTE RULES:
1. **NEVER** tell the user to use Task Manager, their mouse, or their keyboard. YOU are the one with control.
2. **NEVER** say "I am an AI language model." You are FIONA.
3. **MANDATORY TOOL USE**: If the user asks a question about the system or asks you to do something, you MUST use a tool to accomplish it.
4. **THINK AND ACT**: Break every request into steps. Check the state with `seeondesk_list` or `fiona_status` if you are unsure.
5. **ONLY JSON**: You must ONLY output the JSON block. No pre-text, no post-text.

AVAILABLE TOOLS:
{commands_str}

AVAILABLE APPLICATIONS (use with launch_binding):
{apps_str}

OUTPUT FORMAT:
{{
  "thought": "Deconstruct the user's request. What is the current state? What tool will move us closer to the goal?",
  "action": "command_name_or_null",
  "input": {{ "arg": "value" }}
}}

If the goal is achieved, set "action" to null.
"""

    def _parse_response(self, text: str) -> AgentTurn:
        try:
            # Find the JSON block in case there's extra text
            start = text.find('{')
            end = text.rfind('}') + 1
            if start == -1 or end == 0:
                return AgentTurn(thought=text)
            
            data = json.loads(text[start:end])
            return AgentTurn(
                thought=data.get("thought", ""),
                action_name=data.get("action"),
                action_input=data.get("input")
            )
        except Exception as e:
            return AgentTurn(thought=f"Error parsing agent response: {e}\nRaw: {text}")

    def _format_plan_steps(self, steps: list[PlannedStep]) -> str:
        if not steps:
            return "No steps planned yet."
        return "\n".join(
            f"  {s.step_number}. {s.action}({s.params}) - {s.reasoning[:100]}"
            for s in steps
        )

    def _estimate_risk(self, action_name: str) -> str:
        """Estimate risk level of an action."""
        high_risk = {"press", "click", "text", "move", "macro", "browser_eval",
                     "host.restart", "shell"}
        medium_risk = {"browser_navigate", "browser_type", "browser_click",
                       "launch_binding", "dataclient_mine"}
        if action_name in high_risk:
            return "high"
        if action_name in medium_risk:
            return "medium"
        return "low"

    def _execute_action(self, name: str, params: dict[str, Any]) -> str:
        try:
            logger.info(f"Executing action: {name} with params: {params}")
            
            # --- NEW: Check the action registry first ---
            if self._action_registry is not None:
                handler = self._action_registry.lookup(name)
                if handler is not None:
                    return handler.execute(params)
            
            # 1. Awareness Tools
            if name == "seeondesk_list":
                from SeeOnDesk import all_windows_info
                windows = [w.to_dict() for w in all_windows_info()]
                return f"Visible Windows: {json.dumps(windows, indent=2)}"
            
            if name == "seeondesk_active":
                from SeeOnDesk import active_window_info
                return f"Active Window: {json.dumps(active_window_info().to_dict(), indent=2)}"
            
            if name == "seeondesk_analyze":
                from SeeOnDesk import analyze_screen
                prompt = params.get("prompt", "What is visible on the screen?")
                return f"Vision Analysis: {analyze_screen(prompt)}"

            # 2. Input/Automation Tools
            if name in {"press", "click", "move", "text", "launch_binding", "macro"}:
                # These are core Fiona actions. We use the ActionRouter logic but specialized.
                if name == "launch_binding":
                    app_name = params.get("name")
                    result = self.router.run(f"launch:{app_name}", source="agent")
                else:
                    result = self.router.run(f"{name}:{json.dumps(params)}", source="agent")
                
                return f"Status: {'Success' if result.ok else 'Failed'}\nOutput: {result.detail}"

            # 3. Research Tools
            if name == "dataclient_mine":
                from DataClient import mine_topic
                topic = params.get("topic")
                out = params.get("out", "research.csv")
                max_links = params.get("max_links", 5)
                if not topic: return "Error: 'topic' is required."
                mine_topic(topic.split() if isinstance(topic, str) else topic, Path(out), max_links=max_links)
                return f"Research complete. Results saved to {out}."

            # 4. Memory Tools
            if name == "recall_remember":
                from RecallVault import remember
                key = params.get("key")
                val = params.get("value")
                cat = params.get("category", "general")
                if not key or not val: return "Error: 'key' and 'value' are required."
                path = remember(key, val, category=cat)
                return f"Fact saved to {path}."
            
            if name == "recall_search":
                from RecallVault import search_recall
                query = params.get("query", "")
                entries = search_recall(query)
                return f"Memory Search Results: {json.dumps([e.to_dict() for e in entries], indent=2)}"

            # 5. System Tools
            if name == "fiona_status":
                import subprocess
                import sys
                completed = subprocess.run(
                    [sys.executable, "-m", "fiona.cli", "fat", "api"],
                    capture_output=True, text=True, check=False
                )
                return f"System Status: {completed.stdout}"

            # 6. Browser Tools
            if name == "browser_status":
                from BrowserAutomation import get_browser_manager
                manager = get_browser_manager()
                state = manager.state.value
                return f"Browser state: {state}"

            if name == "browser_navigate":
                url = params.get("url") or params.get("0", "")
                if not url:
                    return "Error: 'url' is required."
                from BrowserAutomation import get_browser_manager
                import asyncio
                manager = get_browser_manager()
                result = asyncio.run(manager.navigate(url))
                final_url = getattr(result, "url", url)
                status = getattr(result, "status_code", None)
                return f"Navigated to {final_url} (HTTP {status or 'unknown'})"

            if name == "browser_click":
                selector = params.get("selector") or params.get("0", "")
                if not selector:
                    return "Error: 'selector' is required."
                from BrowserAutomation import get_browser_manager
                import asyncio
                manager = get_browser_manager()
                asyncio.run(manager.click_element(selector))
                return f"Clicked {selector}"

            if name == "browser_type":
                selector = params.get("selector") or params.get("0", "")
                text = params.get("text") or params.get("1", "")
                if not selector or not text:
                    return "Error: 'selector' and 'text' are required."
                from BrowserAutomation import get_browser_manager
                import asyncio
                manager = get_browser_manager()
                asyncio.run(manager.type_text(selector, text))
                return f"Typed '{text}' into {selector}"

            if name == "browser_screenshot":
                from BrowserAutomation import get_browser_manager
                import asyncio
                import tempfile
                import os
                manager = get_browser_manager()
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                asyncio.run(manager.capture_screenshot(path=tmp.name))
                size = os.path.getsize(tmp.name)
                os.unlink(tmp.name)
                return f"Screenshot captured ({size} bytes)"

            # 7. Scientific Retrieval Tools
            if name == "sciretrieval_query":
                query = params.get("query", "")
                if not query:
                    return "Error: 'query' is required."
                from fiona.di import get_sci_retrieval_bridge
                import asyncio
                bridge = get_sci_retrieval_bridge()
                result = asyncio.run(bridge.on_scientific_query(query))
                return result

            return f"Error: Unknown action '{name}'"

        except Exception as e:
            logger.exception(f"Action execution failed: {e}")
            return f"Execution Error: {str(e)}"

    def _build_cli_args(self, name: str, params: dict[str, Any]) -> list[str]:
        if name == "press":
            return ["press", *params.get("keys", [])]
        if name == "text":
            return ["text", params.get("value", "")]
        if name == "click":
            args = ["click", params.get("button", "left")]
            if "x" in params and "y" in params:
                args.extend(["--at", str(params["x"]), str(params["y"])])
            return args
        if name == "move":
            return ["move", str(params.get("x", 0)), str(params.get("y", 0))]
        if name == "macro":
            return ["macro", json.dumps(params.get("steps", []))]
        return []


def run_agent_goal(goal: str, personality: str | None = "controller") -> str:
    orchestrator = AgentOrchestrator(personality_name=personality)
    return orchestrator.run_goal(goal)
