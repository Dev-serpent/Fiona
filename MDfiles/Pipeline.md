Fiona Execution Pipeline — Complete Analysis
1. End-to-End Task Flow
Below traces a user request from shell to completion, following the primary execution path (CLI → AgentOrchestrator). Three orchestrators coexist — this is the one actually wired to the CLI.
Step-by-Step Trace
USER INPUT
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 0: ENTRY POINT                                           │
│  pyproject.toml [line 56]: entry_points = "fiona = fiona.cli:main" │
└─────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 1: ARGUMENT PARSING (fiona/cli.py)                            │
│                                                                      │
│  main() [line 93]                                                    │
│    ├─ _normalize_help_args(argv) [line 94]    — convert "help"→"--help"│
│    ├─ _should_delegate_to_quiktieper(argv)?   — QuikTieper shortcut  │
│    ├─ _build_parser() [line 105]              — argparse tree        │
│    ├─ parser.parse_args(argv) [line 106]      — → args.layer, etc.   │
│    ├─ Top-level flags? --list-macros / --run-macro / --tray-only     │
│    └─ args.layer dispatch [line 123]          — if/elif chain        │
│         │                                                           │
│         ▼                                                          │
│    args.layer == "agent" → _run_agent(args) [line 132]              │
└──────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌───────────────────────────────────────────────────────────────────────┐
│  PHASE 2: AGENT SUBCOMMAND (fiona/cli.py, _run_agent() line 984)     │
│                                                                       │
│  _run_agent(args)                                                     │
│    ├─ args.agent_command == "commands"?  → print command_registry()   │
│    ├─ args.agent_command == "status"?    → print client.health()      │
│    ├─ args.agent_command == "run"?       → [PRIMARY PATH]             │
│    │    ├─ from Agent import AgentOrchestrator   [line 1002]          │
│    │    ├─ goal = " ".join(args.goal)           [line 1003]           │
│    │    ├─ orchestrator = AgentOrchestrator(client) [line 1004]       │
│    │    ├─ orchestrator.max_turns = args.turns    [line 1005]           │
│    │    └─ result = orchestrator.run_goal(goal)   [line 1009]         │
│    └─ args.agent_command == "ask"?       → client.ask(prompt, ...)    │
└───────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: ORCHESTRATOR — PLAN + APPROVAL + EXECUTE                      │
│  (Agent/orchestrator.py, AgentOrchestrator.run_goal() [line 44])         │
│                                                                          │
│  ┌─── SUB-PHASE 3A: PLAN GENERATION [lines 50-81] ─────────────────┐    │
│  │                                                                  │    │
│  │  Loop (up to max_turns):                                        │    │
│  │   1. Build system prompt via _build_system_prompt() [line 204]:  │    │
│  │      - Loads command_registry() → dict of all available commands │    │
│  │      - If self._personality_name set: loads Personality from     │    │
│  │        PersonalityRegistry, appends after personality prompt      │    │
│  │      - Otherwise: hardcoded Fiona operator prompt [line 292]     │    │
│  │   2. client.ask(prompt, system_prompt) → LLM response [line 60] │    │
│  │      - HTTP POST to http://localhost:11434/api/chat              │    │
│  │      - Default model: qwen3:8b-en                                │    │
│  │   3. _parse_response(response) [line 260]:                       │    │
│  │      - Extracts first JSON {...} from text                       │    │
│  │      - Returns AgentTurn(thought, action_name, action_input)     │    │
│  │   4. If no action_name → planning complete, break                │    │
│  │   5. _estimate_risk(action) [line 285] → "high"/"medium"/"low"   │    │
│  │   6. Append PlannedStep to plan_steps list                       │    │
│  │                                                                  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─── SUB-PHASE 3B: HUMAN APPROVAL [lines 87-99] ───────────────────┐   │
│  │                                                                   │   │
│  │  1. self.approval_manager.submit_plan(goal, steps)  [line 87]     │   │
│  │     - ApprovalManager (FionaCore/approval.py [line 69])           │   │
│  │     - Stores plan, generates plan_id, notifies Tkinter GUI        │   │
│  │  2. self.approval_manager.wait_for_approval(plan_id, timeout=300) │   │
│  │     [line 94]                                                     │   │
│  │     - Blocks up to 300 seconds for human decision                 │   │
│  │     - Returns 'approved', 'denied', or 'timeout'                  │   │
│  │  3. If denied/timeout → returns plan status + reason [line 98]    │   │
│  │                                                                   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─── SUB-PHASE 3C: EXECUTION [lines 101-112] ─────────────────────┐    │
│  │                                                                  │    │
│  │  For each PlannedStep:                                          │    │
│  │   1. Mark plan step as executing                                 │    │
│  │   2. self._execute_action(step.action, step.params) [line 297]: │    │
│  │      - Monolithic if/elif chain (~130 lines) dispatching to:    │    │
│  │        ├─ SeeOnDesk: seeondesk_list, seeondesk_active, etc.     │    │
│  │        ├─ FionaCore/ActionRouter: press, click, move, text,     │    │
│  │        │   launch_binding, macro                                │    │
│  │        ├─ DataClient: dataclient_mine                           │    │
│  │        ├─ RecallVault: recall_remember, recall_search           │    │
│  │        ├─ FionaCore CLI: fiona_status (via subprocess)          │    │
│  │        ├─ BrowserAutomation: browser_status, navigate, click,   │    │
│  │        │   type, screenshot                                     │    │
│  │        └─ SciRetrieval: sciretrieval_query                      │    │
│  │   3. Append observation to history                              │    │
│  │                                                                  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Result: return f"Plan completed. Summary: {summary}"                    │
└──────────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 4: OUTPUT (fiona/cli.py _run_agent() [lines 1010-1012])       │
│                                                                      │
│  print("-" * 40)                                                     │
│  print(f"Final Outcome: {final_thought}")                            │
│  (output goes to stdout)                                             │
└──────────────────────────────────────────────────────────────────────┘
2. Secondary Entry Points
Dashboard REST API (fionaLocalPages)
POST /api/v1/agent/goal  (server/handlers/agent.py [line 99])
  │
  └─ run_agent_goal(goal=goal)  [line 114]
       │
       └─ Agent/orchestrator.py, run_agent_goal() [line 450]
            │
            └─ AgentOrchestrator(personality_name="controller").run_goal(goal)
                 │
                 └─ (same Phase 3 flow as CLI — plan → approve → execute)
POST /api/v1/agent/ask  (server/handlers/agent.py [line 38])
  │
  ├─ Optional: sci_retrieval_bridge.on_scientific_query() for enrichment
  └─ OllamaClient.ask(prompt, system=system, ...) — simple text generation, no tools
Dashboard CRUD (agents_crud.py)
Manages in-memory agent metadata only — name, model, system_prompt, status string. Does not start/stop LLM processes. Separate from PersonalityRegistry and AgentManager.
3. Three Coexisting Orchestrators
Fiona has three orchestrators, each with different design goals:
Orchestrator	File	Lines	Entry Trigger	Routing Method	Decomposition	Approval	Parallel Exec	Tool Dispatch
AgentOrchestrator	Agent/orchestrator.py	452	cli.py fiona agent run, dashboard /agent/goal	Single personality (optional)	Simple step-by-step LLM planning	✅ ApprovalManager (FionaCore)	No	Hardcoded if/elif (_execute_action)
ForemanAgent	Agent/orchestration.py	1099	Programmatic import only	ComplexityAssessor → TaskPlan.from_llm()	✅ Multi-agent decomposition with topological sort	❌	✅ ThreadPoolExecutor	SubAgent → SafeActionRouter
Coordinator	Agent/coordinator.py	690	DI container (register_coordinator)	AgentRouter (tags→capabilities→tasks→LLM fallback)	Single-agent routing (no decomposition)	❌	No	SubAgent → SafeActionRouter
Key observation: Only AgentOrchestrator is wired to actual user-facing entry points (CLI and dashboard). ForemanAgent and Coordinator are available for programmatic use but have no CLI or API bindings. The Coordinator is registered in the DI container but never invoked by the current public interface.
4. Text-Based Architecture / Sequence Diagram
                          ╔══════════════════════════════╗
                          ║       USER / CLIENT          ║
                          ║  (shell, browser, Tkinter)   ║
                          ╚══════════════════════════════╝
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌────────────┐  ┌────────────┐  ┌──────────────┐
            │ CLI        │  │ Dashboard  │  │ Tkinter GUI  │
            │ fiona.cli  │  │ Flask +    │  │ (approval    │
            │            │  │ aiohttp    │  │  dialogs)    │
            └─────┬──────┘  └──────┬─────┘  └──────┬───────┘
                  │                │                │
                  ▼                │                │
            ┌────────────┐         │                │
            │ _run_agent │         │                │
            │ [cli:984]  │         │                │
            └─────┬──────┘         │                │
                  │                │                │
                  ▼                ▼                │
            ┌──────────────────────────────┐        │
            │    AgentOrchestrator         │        │
            │    .run_goal()               │        │
            │    [orch.py:44]              │        │
            └──────┬──────────────┬────────┘        │
                   │              │                 │
         ┌─────────▼──────┐  ┌────▼──────────┐     │
         │  Phase 1:     │  │  Phase 3:     │     │
         │  LLM Planning │  │  Execution    │     │
         │  (Ollama)     │  │  (actions)    │     │
         └────────┬──────┘  └────┬──────────┘     │
                  │              │                 │
                  ▼              ▼                 │
            ┌────────────────────────┐             │
            │  Phase 2: Approval     │◄────────────┘
            │  ApprovalManager       │  Tkinter dialog
            │  [FionaCore/approval]  │  blocks here
            └────────────────────────┘

  ═══════════════ COMPONENT INTERACTION DETAIL ═══════════════

  AgentOrchestrator
     │
     ├──► PersonalityRegistry  [personality.py:55]
     │       └──► stores: Personality (name, system_prompt, allowed_tools)
     │       └──► stores: AgentMeta (tags, capabilities, supported_tasks)
     │       └──► loaded from: agents/*.md (YAML front matter + body)
     │       └──► builtins: general, planner, engineer, analyst, security, controller
     │
     ├──► OllamaClient  [Agent/ollama.py]
     │       └──► urlopen() → http://localhost:11434/api/chat
     │       └──► also: http://localhost:11434/api/tags (health)
     │       └──► wrapped by: OllamaProvider [llm.py:159]
     │       └──► also wrapped by: OpenAIProvider [llm.py:301]
     │
     ├──► _execute_action()  [orch.py:297]  ← HARDCODED DISPATCH
     │       │
     │       ├──► SeeOnDesk (seeondesk_list, etc.)  [import]
     │       │       └──► (tracks active window, processes)
     │       │
     │       ├──► ActionRouter (FionaCore)  [press, click, move, text...]
     │       │       └──► keyboard/mouse simulation
     │       │       └──► app launching via QuikTieper
     │       │
     │       ├──► DataClient (dataclient_mine)  [import]
     │       │       └──► web scraping / data retrieval
     │       │
     │       ├──► RecallVault (recall_remember, recall_search)  [import]
     │       │       └──► key-value memory store
     │       │
     │       ├──► subprocess.run (fiona_status)  [orch.py:357]
     │       │       └──► python -m fiona.cli fat api
     │       │
     │       ├──► BrowserAutomation (browser_*)  [import]
     │       │       └──► Playwright-based browser control
     │       │
     │       └──► SciRetrieval (sciretrieval_query)  [import]
     │               └──► scientific literature search
     │
     ├──► CommandRegistry  [command_registry.py]
     │       └──► provides available commands + apps to LLM prompt
     │
     ├──► PermissionEnforcer  [permission.py:20]  (used by SubAgent only)
     │       └──► checks Personality.permits(tool_name) before execution
     │
     └──► SafeActionRouter  [permission.py:44]
             └──► wraps ActionRouter with PermissionEnforcer gate

  ═══════════════ SUPPORTING SYSTEMS ═══════════════

  DI Container (fiona/di.py)
     ├── registers: event_bus, plugin.manager, agent.manager,
     │              coordinator, tool.runtime, sci_retrieval.*, email.*
     └── used by: FionaInspector, Dashboard, PluginManager

  Plugin System (fiona/plugin_system.py)
     ├── PluginManager.discover() → plugin.json/yaml
     ├── PluginManager.load() → FionaPlugin.activate(container)
     ├── PluginManager.register_agent/tool/skill/command/event_handler
     └── PluginManager.scan_agents() → agents/*.md

  Memory System (Agent/memory.py)
     ├── MemoryProvider (ABC)
     │    ├── InMemoryProvider (default, thread-safe dict)
     │    └── ChatStoreMemoryProvider (adapter)
     ├── MemoryManager (facade, 6 namespaces)
     │    └── conversation, task, workspace, user, agent, project
     └── used by: (no current integration with AgentOrchestrator)

  Skills System (Agent/skill.py + skills/*.yaml)
     ├── Skill dataclass (name, tools, instruction, tags)
     ├── SkillRegistry (register, discover, search, list_by_tool)
     └── 3 builtin skills: web-research, code-analysis, data-analysis

  LLM Providers (Agent/llm.py)
     ├── LLMProvider (ABC): chat, stream, count_tokens, health
     │    ├── OllamaProvider (wraps OllamaClient)
     │    └── OpenAIProvider (openai SDK, configurable base_url)
     ├── ProviderRegistry (name→provider mapping)
     └── LLMManager (facade, auto-registers Ollama default)

  Validation Agents (fiona/validators/)
     ├── CodeReviewValidator (AST analysis, style checks)
     ├── SecurityReviewValidator (secret detection, injection patterns)
     └── DocsReviewValidator (placeholder, line length checks)

  FionaInspector (fiona/introspection.py)
     └── system_status(), list_agents(), list_skills(), list_plugins(),
         list_tools(), check_llm_health(), get_memory_summary(), full_report()
5. Module Dependency Map
                                                      ┌──────────────┐
                                                      │  fiona/cli   │
                                                      │  .py:1995    │
                                                      └──────┬───────┘
                                                             │
                    ┌────────────────────────────────────────┼──────────────┐
                    │                                        │              │
                    ▼                                        ▼              ▼
          ┌─────────────────┐                     ┌──────────────────┐     ...
          │  AgentOrchestrator │                   │  Agent.ollama    │
          │  (orch.py:29)   │                     │  OllamaClient    │
          │  [plan+approve+ │                     │  .ask()          │
          │   execute]      │                     │  .chat()         │
          └────────┬────────┘                     │  .health()       │
                   │                              └────────┬─────────┘
        ┌──────────┼──────────┐                            │
        ▼          ▼          ▼                            ▼
  ┌─────────┐ ┌──────────┐ ┌──────────────┐    ┌──────────────────┐
  │FionaCore│ │FionaCore │ │SeeOnDesk     │    │  http://localhost │
  │Approval │ │ActionRout│ │BrowserAuto-  │    │  :11434/api/chat  │
  │Manager  │ │          │ │mation, etc.  │    └──────────────────┘
  └─────────┘ └──────────┘ └──────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  Persona / Agent Registry (Agent/personality.py)                │
  │  PersonalityRegistry (singleton)                                │
  │    ├── _personalities: dict[str, Personality]                   │
  │    └── _agent_metas: dict[str, AgentMeta]                       │
  │         ▲                                                       │
  │         │ reads                                                  │
  │    ┌────┴───────────┐                                           │
  │    │  AgentManager  │  (agent_manager.py)                       │
  │    │  lifecycle +   │                                           │
  │    │  hot-reload    │                                           │
  │    └────────────────┘                                           │
  │         ▲                                                       │
  │         │ synchronizes                                          │
  │    ┌────┴───────────┐                                           │
  │    │  PluginManager │  (fiona/plugin_system.py)                 │
  │    │  discovers .md │                                           │
  │    │  + plugin.yaml │                                           │
  │    └────────────────┘                                           │
  └─────────────────────────────────────────────────────────────────┘
         │
         ▼
  ┌────────────────┐
  │  agents/*.md   │  ← YAML front matter → AgentMeta → Personality
  │  6 builtins    │
  └────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  DI Container (fiona/di.py)                                     │
  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
  │  │ agent.manager    │  │ coordinator       │  │ plugin.manager│  │
  │  │ AgentManager     │  │ Coordinator       │  │ PluginManager │  │
  │  └──────────────────┘  └──────────────────┘  └───────────────┘  │
  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
  │  │ event_bus        │  │ tool.runtime      │  │ sci_retrieval │  │
  │  │ EventBus         │  │ ToolRuntime       │  │ .* services   │  │
  │  └──────────────────┘  └──────────────────┘  └───────────────┘  │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  Alternative execution paths (not CLI-wired):                    │
  │                                                                  │
  │  ForemanAgent (orchestration.py:699)                             │
  │    ├── ComplexityAssessor → assess(goal)                         │
  │    ├── TaskPlan.from_llm() → decompose + validate + topo-sort    │
  │    ├── _run_parallel() → ThreadPoolExecutor + SubAgent           │
  │    ├── _run_sequential() → SubAgent one-by-one                   │
  │    └── _synthesize() → LLM merges sub-results                   │
  │                                                                  │
  │  Coordinator (coordinator.py:429)                                │
  │    ├── AgentRouter.route(goal)                                   │
  │    │     tags → capabilities → tasks → LLM fallback              │
  │    └── SubAgent.execute(goal) [ReAct loop]                      │
  │         └── OllamaClient + SafeActionRouter                      │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  Tool System (concrete)                                          │
  │                                                                  │
  │  Agent/tool_runtime.py                                           │
  │    ToolRegistry.create_default()                                 │
  │      ├── SciToolRegistry (UnitConverter, ChemResolver, etc.)     │
  │      ├── SeeOnDesk.tools                                         │
  │      └── Communications.email_tools                              │
  │                                                                  │
  │  Agent/orchestrator.py:_execute_action()                         │
  │      (separate hardcoded dispatch — NOT using ToolRuntime)       │
  └─────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────┐
  │  Web Dashboard (fionaLocalPages)                                 │
  │                                                                  │
  │  Flask (port 5000) ←→ aiohttp (port 8765)                        │
  │  aiohttp app.py → 23 handler modules → ~140 REST endpoints      │
  │    handlers/agent.py → run_agent_goal() → AgentOrchestrator      │
  │    handlers/agents_crud.py → in-memory agent metadata store      │
  │    handlers/tools_handler.py → ToolRuntime (but routes NOT wired)│
  │    ws_server.py → WebSocketManager (JSON-RPC, periodic push)     │
  └─────────────────────────────────────────────────────────────────┘
6. Error & Failure Propagation
Layer 1 — CLI Argument Parsing
_normalize_help_args → argparse.ParseError → prints help and exits
Layer 2 — Dispatch (_run_agent)
  ├─ OllamaClient() init: no error (dataclass)
  ├─ client.health(): OllamaError → propagates up; cli prints traceback
  └─ AgentOrchestrator(client):
       └─ run_goal(goal):
            ├─
            │  PHASE 1 — LLM plan:
            │    client.ask() → OllamaError (connection refused, timeout)
            │      → raises → _run_agent catches? No → propagates to main()
            │    _parse_response() → JSONDecodeError → treated as no-action → breaks loop
            │
            ├─
            │  PHASE 2 — Approval:
            │    approval_manager.submit_plan() → no hard failures (stores in-memory)
            │    approval_manager.wait_for_approval() → timeout (300s) → returns 'timeout'
            │      → treated as denial → returns denial message
            │
            └─
               PHASE 3 — Execution:
                 _execute_action(name, params):
                   ├─ Unknown action name → KeyError? No, falls through if/elif silently
                   │   → returns f"No implementation for action: {name}"
                   ├─ ImportError for optional module → caught? YES, inside each if/elif block
                   │   → returns error string
                   ├─ SubprocessError (fiona_status) → caught → returns stderr as result
                   ├─ BrowserAutomation failure → caught? YES, try/except in browser_* blocks
                   │   → returns error message
                   └─ Any other Exception → no catch at execute_action level
                        → propagates up through run_goal() to cli.py
Layer 3 — Main CLI (cli.py:main)
  _run_agent() → no try/except at this level
  parser.parse_args → SystemExit (argparse default on error)
  sys.exit(1) on various failures
Dashboard Error Path
  handler function:
    try:
        body = await request.json()
    except Exception:
        raise ApiError(400, "Invalid JSON body")
    
    try:
        result = run_agent_goal(goal=goal)
    except Exception as exc:
        raise ApiError(502, f"Agent request failed: {exc}")
ForemanAgent Fallback Chain (3 fallbacks)
  execute(goal)
    ├─ assess → SIMPLE? → _run_simple() — no planning needed
    ├─ decompose → PlanValidationError?
    │    └─ [FALLBACK A] _run_simple()
    ├─ execution_order → PlanValidationError?
    │    └─ [FALLBACK B] _run_simple()
    └─ _synthesize → LLM call fails?
         └─ [FALLBACK C] plain-text format all results
7. Assumptions and Uncertainties
Known Gaps
1. AgentOrchestrator vs ToolRuntime disconnect: The legacy _execute_action() has its own hardcoded dispatch separate from the newer ToolRuntime system. Tools registered via the plugin system or ToolRegistry are invisible to AgentOrchestrator.run_goal(). Only run_goal_async() uses ToolRuntime.
2. Memory system not wired: MemoryManager exists in the Agent/ package but is not integrated into AgentOrchestrator, ForemanAgent, or Coordinator. No agent uses MemoryManager.store() or retrieve() during execution.
3. Skills system not wired: Skills are registered and discoverable but no agent prompt builder actually calls SkillRegistry.get_required_tools() to inject skill instructions into system prompts.
4. LLMManager/ProviderRegistry unused: LLMManager and ProviderRegistry exist but none of the three orchestrators use them — they all call OllamaClient directly. The provider abstraction layer is unused by the execution pipeline.
5. Coordinator unplugged: Although registered in the DI container, Coordinator has no CLI binding, no API endpoint, and no user-facing entry point. It's available for programmatic import but sits idle.
6. Validation agents orphaned: CodeReviewValidator, SecurityReviewValidator, and DocsReviewValidator register themselves as agents but have no caller — no orchestrator routes goals to them, and no dashboard page invokes them.
7. Tools handler routes not wired: tools_handler.py is imported in app.py but its routes (/api/v1/tools) are never registered — the endpoints exist in code but are unreachable from the dashboard.
Architectural Uncertainties
1. Intent of three orchestrators: Unclear whether they are meant to be (a) three stages of a migration path, (b) three interchangeable strategies, or (c) three independent systems for different use cases. They have no shared interface or common base class.
2. Event bus usage: The event bus has extensive wiring (agent lifecycle events, coordinator events, plugin events) but no subscribers exist in the current codebase. Events are published but never consumed.
3. Hot-reload purpose: AgentManager.start_hot_reload() runs a background polling thread that calls reload_all() every 5 seconds. This would overwrite personality registrations continuously — possibly a development-only feature.
4. FionaInspector instantiation: FionaInspector creates its own DI container in every method if one isn't provided (container = FionaContainer() on each call). This means each inspection call reconstructs the entire service graph, which could be slow.
5. Dual agent stores: PersonalityRegistry (singleton) and PluginManager both maintain agent registrations. AgentManager bridges them, but PersonalityRegistry doesn't go through AgentManager for its builtins — it registers directly in __init__. This means builtins bypass enable/disable and hot-reload tracking.
8. Summary of Current State
Entry Points:   CLI (fiona agent run/ask)
                Dashboard (POST /api/v1/agent/goal, /ask)
                Programmatic (import Agent)

Active Path:    CLI → AgentOrchestrator → Ollama → hardcoded tools

Orchestrators:  AgentOrchestrator  [WIRED to CLI + Dashboard]
                ForemanAgent       [UNWIRED — programmatic only]
                Coordinator        [UNWIRED — programmatic only]

Tools Path 1:   _execute_action()  [hardcoded if/elif — ~20 actions]
Tools Path 2:   ToolRuntime        [async tool-calling — unused by CLI]

Plugin System:  Discovers & registers agents/plugins
                No runtime integration with orchestrators

Memory System:  Fully implemented, zero runtime usage
Skills System:  Fully implemented, zero runtime usage
LLM Providers:  Fully implemented, zero runtime usage
Validation:     Fully implemented, zero runtime usage
Event Bus:      Fully wired publishers, zero subscribers
This is the complete picture of the execution pipeline as it currently stands.
# Todos
[✓] Map entry points and request intake
[✓] Trace orchestration / routing logic
[✓] Map agent execution and tool dispatch
[✓] Identify integration points and error paths
[✓] Produce flow diagram and dependency map
All done. The analysis covers the complete end-to-end pipeline with:
- Step-by-step task flow — from fiona agent run shell invocation through argument parsing → AgentOrchestrator.run_goal() → 3-phase execution (plan → approve → execute) → output
- Architecture/sequence diagram — ASCII component interaction map showing every module and communication channel
- Dependency map — hierarchical module graph with interconnections
- Error propagation — failure modes at each layer (CLI, approval timeout, action execution, fallback chains)
- Assumptions and uncertainties — 7 known gaps and 5 architectural uncertainties
The key takeaway for your public-apis/public-apis integration point: the Coordinator (in the DI container) is the cleanest integration target — it already has AgentRouter with metadata-driven routing, event bus wiring, and a pure dispatch pipeline. It's fully built but unplugged. The ToolRuntime is the correct tool invocation interface for any new API tools. Both are ready to wire up without touching the legacy AgentOrchestrator._execute_action() dispatch.
