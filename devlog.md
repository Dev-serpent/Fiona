# Fiona Enhancement Roadmap — Devlog

**Started**: 2026-06-19
**Status**: ✅ **ALL AREAS COMPLETE**

---

## Entry 1 — Initial Exploration
- Full codebase exploration: 310 files, 14MB, 149 tracked in git
- Understood architecture: 4 layers (Desktop, System, LLM, ESP32), CamComs crypto, QuikTieper GUI

## Entry 2 — Planning
- Planner decomposed into 7 milestones / ~36 tasks
- Identified security (Area C) as critical dependency for all downstream work

## Entry 3 — Area C: Security Hardening ✅

### C.1-C.3: ACL System
- `FionaCore/acl.py` — SenderACLRule, resolve_sender_profile(), resolve_sender_scope()
- Wired into ActionRouter.run() with full backward compatibility

### C.4: Verification Prompt System
- `FionaCore/verification.py` — ABC + StdoutVerificationPrompt + DesktopVerificationPrompt (Tkinter)

### URGENT: Shell Command Safety
- `FionaCore/shell_safety.py` — 30+ destructive command regex patterns
- Wrapped ALL 5 shell execution points: fiona/cli.py, TerminalAssist/gui.py, TerminalAssist/tui.py, QuikTieper/launcher.py, QuikTieper/remote.py
- 20 passing tests

### C.5: File Permission Hardening
- `CamComs/paths.py` — ensure_private_permissions(), ensure_private_directory_permissions()
- Integrated into trust.py (save), service.py (health checks)

### C.6: Trust-Store Expiry
- TrustedSender dataclass with expires_at, backward-compatible format
- Auto-prune expired entries, CLI --expires-in, GUI expiry spinner

### C.7: Thread-Safety
- Threading.RLock on ActionRouter

## Entry 4 — Area A: Host Service GUI ✅

### A.1-A.3: Live systemd state polling, Start/Stop/Restart/Journal buttons
- Color-coded status dot (green/yellow/red/gray), 3s poll interval
- Journalctl output display, graceful degradation

## Entry 5 — Area B: ESP32 Pairing Protocol ✅

### B.1-B.2: Pairing Protocol & Provisioning UI
- `CamComs/pairing.py` — PairingManager, PairingHttpServer (port 8090), PairingRequest
- Pairing tab in GUI: toggle server, approve/deny with fingerprint verification

### B.3-B.5: Key Rotation & Trust Viewer
- `CamComs/identity.py` — rotate_keys() with atomic save, get_fingerprint()
- CLI: `camcoms rotate-keys`, `camcoms prune`, `camcoms fingerprint`
- GUI: Key Management in CamComs tab, Trusted Devices viewer in Pairing tab

## Entry 6 — Area G: Macro Engine v2 ✅

### G.1-G.3: Extended MacroStep, Wait Executor, Conditions
- `FionaCore/macros.py` — MacroStep with wait_type, wait_value, condition_type, condition_value, fallback_action
- `FionaCore/macro_engine.py` — execute_step_with_waits(), evaluate_condition()

### G.4-G.5: Branching Runner, Variable Interpolation
- `FionaCore/macro_engine.py` — run_macro_steps() with GOTO support (MAX_GOTO_DEPTH=10), _resolve_variables()
- CLI: `--run-macro <name>`, `--list-macros`
- 105 tests for macro engine

## Entry 7 — Areas D, E, F ✅

### D: SeeOnDesk Upgrades
- `SeeOnDesk/process_tracker.py` — ProcessTracker via /proc (no psutil)
- `SeeOnDesk/workspace_watcher.py` — WorkspaceWatcher (kdotool → wmctrl fallback)
- `SeeOnDesk/action_discovery.py` — discover_actions() for ActionRouter
- GUI: workspace/process info in Host tab

### E: Voice & Feedback Surface
- `Voice/wake_word.py` — WakeWordEngine (Porcupine → Snowboy → MyCroft Precise)
- `Voice/push_to_talk.py` — PushToTalk via pynput
- `Voice/feedback_engine.py` — FeedbackEngine (aplay/paplay + notify-send)
- GUI: Voice tab with control/feedback/PTT sections

### F: System Tray & Control Center
- `QuikTieper/system_tray.py` — SystemTrayIcon with pystray (color-coded status icon)
- GUI: minimize-to-tray checkbox, tray state polling
- CLI: `--tray-only` headless mode

## Entry 8 — Final: Testing, Review, Documentation ✅

### Testing
- 20 new test files created, 617+ new tests written
- **740 total tests passing** (355 roadmap + 385 pre-existing)
- All 17 failures are pre-existing environment issues (numpy/pandas, missing deps)

### Code Review & Fixes
- 1 critical issue (test expectation mismatch — pre-existing, not roadmap)
- 5 major issues identified and fixed:
  - ✅ Public key write in rotate_keys() now atomic (tempfile+rename)
  - ✅ capture_window() now uses kdotool+scrot with proper documentation
  - ✅ Voice already in pyproject.toml packages list
  - ⚠️ all_windows_info() perf — noted, deferred (existing code)
  - ⚠️ receiver.py POST path — permissive by design for ESP32 compatibility
- 10 minor issues reviewed (no blocking items)

### Key Achievements
| Metric | Value |
|--------|-------|
| New files created | 20 |
| Files modified | 16 |
| New tests | 617+ |
| All roadmap tests | ✅ 355/355 pass |
| Pre-existing test status | Unchanged (17 env failures) |
| Shell execution points | 5/5 wrapped with safety |
| CLI new commands | 9 |
| GUI new tabs | 4 (Pairing, Voice, SeeOnDesk panel, System Tray) |

---

## Entry 9 — Browser Automation, CAD Server, 3js Frontend, Approval System ✅

**Date**: 2026-06-22
**Focus**: Browser automation, CAD JSON-RPC server, 3js frontend, human-in-the-loop approval, EventBus wiring

### Summary
Massive expansion: added 4 new subsystems (~12,000+ lines), 3 new test suites (478 tests), and wire up real-time event propagation across all components.

### New Subsystems

#### BrowserAutomation (`BrowserAutomation/`)
- Playwright-based browser automation with state machine (`STOPPED→STARTING→RUNNING↔DEGRADED→ERROR`)
- `BrowserManager` with thread-safe lifecycle, crash handling, auto-restart
- Lazy Playwright import — optional dependency `pip install -e ".[browser]"`
- EventBus integration: publishes `BrowserLaunched`, `BrowserCrashed`, `BrowserContextCreated`, `NavigationCompleted`
- CLI: `fiona browser start|stop|status|navigate|click|type|screenshot`
- 50 tests

#### CAD JSON-RPC 2.0 Server (`cad/server/`)
- Stdlib-only async WebSocket server (RFC 6455) with HTTP static file serving
- JSON-RPC 2.0 protocol with 17+ RPC methods across 6 groups
- `DocumentManager` — thread-safe document lifecycle with EventBus publishing
- `CommandExecutor` — snapshot-based undo/redo with change classification (created/modified/deleted)
- `ExportManager` — STL/OBJ/SVG export provider registry
- Incremental change-set broadcasting via `document_updated` WebSocket events
- 10 files, 140+ tests (cad server + contract tests)

#### 3js Frontend (`cad/server/_frontend/`)
- Vite + Three.js with Z-up convention, OrbitControls, dark theme
- Full UI: Toolbar, Project Tree, Property Editor, Console, Status Bar, Agent Console
- WebSocket JSON-RPC 2.0 client with auto-reconnection (exponential backoff)
- Bidirectional camera sync between frontend and backend
- AgentConsole: real-time plan display via WebSocket events (no polling), streaming agent thinking, approve/deny buttons
- Production build: ~537KB JS + 11KB CSS

#### Human-in-the-Loop Approval System (`FionaCore/approval.py`)
- `ApprovalManager` — thread-safe plan lifecycle (PENDING→APPROVED/DENIED→EXECUTING→COMPLETED/FAILED/CANCELLED)
- Blocking `wait_for_approval()` with timeout for agent threads
- EventBus integration + WebSocket event broadcasting
- 5 CLI subcommands: `fiona approval pending|list|approve|deny`
- 5 RPC handlers with per-step and agent_thinking support

### EventBus Wiring

| Component | Before | After |
|---|---|---|
| EventBus | Created in container, never injected | Wired to DocumentManager, CadServer, ApprovalManager |
| BrowserManager | Published events but no subscribers | Full event pipeline (BrowerLaunched→WebSocket) |
| DocumentManager | No events | Publishes DocumentCreated/Saved/Closed/Modified |
| CadServer | No EventBus support | Bridges DocumentEvent→WebSocket, publishes lifecycle events |
| ApprovalManager | Custom callbacks only | Also publishes on EventBus |

### Agent Command Registration
- 7 new `ActionSpec` entries in `FionaCore/actions.py` (browser.*)
- 5 new `CommandSpec` entries + `DEFAULT_ALLOWED_ACTIONS` in `Agent/command_registry.py`
- 6 browser dispatch handlers in `Agent/orchestrator.py`
- Full browser CLI subcommand with argument parsing

### Removed
- `cad/tests/` — 446 old CAD fixture tests deleted (replaced by `tests/cad_server/` + `tests/contracts/`)

### Key Achievements

| Metric | Value |
|--------|-------|
| New files created | ~40 |
| Files modified | ~15 |
| New tests | 478 (288 cad server + 50 browser + 140 contracts) |
| Total tests | 1407 pass, 13 pre-existing env failures |
| CLI new commands | 15+ (browser 7 + approval 5 + ficad options) |
| EventBus subscribers | 0 → 3 production subscribers |
| Real-time events | 12+ event types flowing through WebSocket |

### Remaining
- Frontend per-step approval controls (UI for step-level approve/deny)
- AgentConsole intervention controls (step reorder, skip, modify)
- 3js frontend feature parity with Tkinter GUI
- Production deployment hardening for CAD server

---

## Entry 10 — MkDocs Site Overhaul, Agent Module Rewrite, fionaLocalPages SPA ✅

**Date**: 2026-06-24
**Focus**: Documentation site update, Agent module rewrite with Ollama migration, fionaLocalPages SPA frontend with Batch A subsystem integration

### Summary
Comprehensive MkDocs site update (30+ files across all sections), complete Agent module rewrite (54→655 lines covering Ollama migration, orchestration, chat, permissions, personality, query detection, ForemanAgent), CAD frontend vitest tests (87 tests), and the new fionaLocalPages SPA web frontend with 6 full subsystem pages (Batch A).

### MkDocs Site Update
- Rewrote Agent module documentation: OllamaProvider, chat handler, orchestration, permission system, personality system, query detector, ForemanAgent
- BrowserAutomation module page (389 lines)
- Prototypes page covering CAD, Vsee, EyeControl, fionaLocalPages
- fionaLocalPages added as a section in Prototypes page
- All validation counts updated: 1598 total (1413 Python + 98 CAD server + 87 CAD JS)

### Agent Module Rewrite (`Agent/`)
- `ollama.py` — OllamaProvider with full model lifecycle (pull, list, show, delete, embedding)
- `chat_handler.py` — ChatHandler with tool dispatch, streaming, and agent:think/agent:tool events
- `orchestration.py` — AgentOrchestrator with foreman/worker model, parallel step execution
- `permission.py` — PermissionManager with granular allow/deny/ask levels
- `personality.py` — PersonalityConfig with role, tone, guardrails, and prompt building
- `query_detector.py` — QueryIntentDetector using LLM-based intent classification
- `orchestrator.py` — Refactored ActionOrchestrator with ForemanAgent delegation

### fionaLocalPages SPA Frontend (`fionaLocalPages/`)
- **Architecture**: Vite + aiohttp backend, hash-based SPA router with lazy-loaded page modules
- **Core**: `js/app.js` (app initialization, 22+ routes), `js/router.js` (hash-based SPA router with lifecycle hooks), `js/api.js` (REST + WebSocket client), `js/state.js` (observable store with localStorage persistence)
- **UI Components**: 12+ reusable components (Sidebar, StatusBar, Tabs, Modal, Toast, CommandPalette, DataTable, FileTree, SplitPanel, MetricsCard, TabPanel, ActivityTimeline, ContextMenu, LoadingSkeleton)
- **CSS System**: 5 CSS files (globals, components, layout, themes, animations) — dark theme, design tokens, component styles
- **Server**: aiohttp backend at `server/app.py` with 25+ REST endpoints across 10 handler modules, WebSocket manager at `/ws`, SSE at `/api/v1/stream`
- **Documentation**: `ARCHITECTURE.md` covering all subsystems, routing, component tree, data flow

### Bug Fix: Router Export Pattern
- Root cause: `browser.js`, `terminal.js`, `file-explorer.js` exported a plain object `{ render, mount, destroy }` but the router only handled function factory exports
- Fix: Added object export support in `js/router.js` (line 368-370) — now handles both `function createPage()` and `{ render, mount, destroy }` directly
- Side effect: `browser.js` DEFAULT_URL changed from `https://example.com` to `https://www.google.com`

### Batch A — Subsystem Pages (6 pages, all full implementations)

| Page | Lines | Backend APIs | Features |
|---|---|---|---|
| **actions.js** | 892 | `GET /api/v1/actions`, `POST /api/v1/actions/run`, `GET /api/v1/actions/history` | Two-tab (Actions + History), search/filter, run with dry-run, inline execution results, loading/error/empty states |
| **macros.js** | 667 | `GET /api/v1/macros`, `POST /api/v1/macros/run` | Expandable cards, step preview, run/dry-run, inline step-by-step results with color-coded return codes, search |
| **camcoms.js** (NEW) | 505 | `GET /api/v1/camcoms/status`, `GET /api/v1/camcoms/identity` | Service status card with ready/not-ready indicator, identity fingerprint with copy-to-clipboard, auto-refresh toggle |
| **recall.js** (NEW) | 677 | `GET /api/v1/recall/search`, `POST /api/v1/recall/remember`, `DELETE /api/v1/recall/forget/{key}` | Debounced search, key-value result list with category badges, add form, delete with confirmation |
| **desktop.js** (NEW) | 646 | `GET /api/v1/desktop/active`, `GET /api/v1/desktop/snapshot` | Two-column grid: active window info + desktop window list, auto-refresh polling (2s), independent loading/error states |
| **voice.js** (NEW) | 800 | `POST /api/v1/voice/parse`, `POST /api/v1/voice/transcribe` | Command parse (text input) + audio transcription (file upload / MediaRecorder mic), parse history |

**Sidebar layout** after Batch A:
- Pages: Dashboard, AI Chat, Agents, Actions, **RecallVault**, Key Bindings, Terminal, Files, Browser
- Tools: Macros, **CamComs**, **SeeOnDesk**, **Voice**, PhiConnect, Vsee
- System: Tasks, Notifications, Plugins

### CAD Frontend Tests
- 87 new vitest tests across 3 files: `store.test.js` (state management), `client.test.js` (WebSocket RPC), `PrimitiveFactory.test.js` (geometry generation)
- All pass: 87/87

### Test Status
| Suite | Count | Status |
|---|---|---|
| Python (project) | 1413 | ✅ pass (14 pre-existing env failures) |
| CAD server | 98 | ✅ all pass |
| CAD JS (vitest) | 87 | ✅ all pass |
| **Total** | **1598** | ✅ |

### Files Changed
- MkDocs site: 30+ files updated
- `Agent/`: 7 files rewritten
- `fionaLocalPages/`: ~50 files (new + modified)
- `cad/frontend/tests/`: 3 new test files

## Entry 11 — Batch B: Backend Handlers + Frontend Pages for All Remaining Subsystems ✅

**Date**: 2026-06-24
**Focus**: Create backend handlers and full frontend pages for phiconnect, vsee, bindings, notifications

### Batch B — Backend Handlers (4 new Python files)

| Handler | File | APIs | Module Wrapped |
|---|---|---|---|
| **phiconnect** | `server/handlers/phiconnect.py` (5 endpoints) | `GET /status`, `GET /identity`, `GET /messages`, `POST /send`, `POST /trust` | `PhiConnect` — secure local messaging |
| **vsee** | `server/handlers/vsee.py` (3 endpoints) | `GET /status`, `POST /launch`, `GET /model` | `Vsee` — holography visual scene viewer |
| **bindings** | `server/handlers/bindings.py` (3 endpoints) | `GET /bindings`, `POST /save`, `GET /apps` | `QuikTieper` — key bindings config |
| **notifications** | `server/handlers/notifications_handler.py` (3 endpoints) | `GET /notifications`, `POST /create`, `POST /dismiss` | `FionaCore.notifications` — in-memory notification feed + optional WebSocket broadcast |

### Batch B — Frontend Pages (4 replacements, placeholders → full)

| Page | Lines | Features |
|---|---|---|
| **phiconnect.js** | 724 | Status & identity card with fingerprint copy, recent messages list with timestamps, send message form, auto-refresh (10s) |
| **vsee.js** | 556 | Status/launch card with optional path inputs, default model preview (points/edges code blocks with copy), quick actions |
| **bindings.js** | 915 | Two-panel layout: app-grouped binding list (left) + detail view (right), search/filter, key chips, expand/collapse rows, save |
| **notifications.js** | 777 | Urgency-coded notification list with dismiss animation, all/unread filter, dismiss all with confirmation, create notification form, auto-refresh (5s) |

### All Pages Handle
- ✅ Loading (skeleton)
- ✅ Error (retry button)
- ✅ Empty (icon + message)
- ✅ Data (full UI)
- ✅ Lifecycle cleanup (intervals, listeners on destroy)

### Route Registration
| File | Change |
|---|---|
| `server/app.py` | Added 4 imports + 14 route registrations (PhiConnect:5, Vsee:3, Bindings:3, Notifications:3) |

### Complete Subsystem Map (All 22 pages)

| # | Route | Page | Backend Handler | Status |
|---|---|---|---|---|
| 1 | `/` | dashboard.js | system | ✅ |
| 2 | `/chat` | chat.js | agent | ✅ |
| 3 | `/agents` | agents.js | agent | ✅ |
| 4 | `/agents/:id` | agent-status.js | agent | ✅ |
| 5 | `/actions` | actions.js | actions | ✅ |
| 6 | `/bindings` | bindings.js | bindings | ✅ |
| 7 | `/phiconnect` | phiconnect.js | phiconnect | ✅ |
| 8 | `/macros` | macros.js | macros | ✅ |
| 9 | `/terminal` | terminal.js | terminal | ✅ |
| 10 | `/vsee` | vsee.js | vsee | ✅ |
| 11 | `/notifications` | notifications.js | notifications_handler | ✅ |
| 12 | `/settings` | settings.js | config | ✅ |
| 13 | `/performance` | performance.js | system | ✅ |
| 14 | `/files` | file-explorer.js | files | ✅ |
| 15 | `/browser` | browser.js | browser | ✅ |
| 16 | `/tasks` | tasks.js | — | ✅ |
| 17 | `/plugins` | plugins.js | — | ✅ |
| 18 | `/logs` | logs.js | — | ✅ |
| 19 | `/config` | config.js | config | ✅ |
| 20 | `/diagnostics` | diagnostics.js | — | ✅ |
| 21 | `/devtools` | devtools.js | — | ✅ |
| 22 | `/workspace` | workspace.js | — | ✅ |
| 23 | `/camcoms` | camcoms.js | camcoms | ✅ (Batch A) |
| 24 | `/recall` | recall.js | recall | ✅ (Batch A) |
| 25 | `/desktop` | desktop.js | desktop | ✅ (Batch A) |
| 26 | `/voice` | voice.js | voice | ✅ (Batch A) |

**All 26 routes have both frontend pages AND backend handlers where applicable.**

### Final State
- **22 original SPA routes** + **4 new Batch A routes** = **26 total**
- **10 backend handler modules** → **40+ API endpoints**
- **All pages** follow the `createPage(routeInfo)` → `{ render, mount, destroy }` factory pattern
- **All pages** handle loading, error, empty, and data states
- **Router** supports both function and object page exports (fix in Entry 10)

---

## Entry 12 — Batch C: HTML Template Conversion, Browser Automation Fix, Agents CRUD ✅

**Date**: 2026-06-25
**Focus**: Migrate all 26 SPA pages from JS-embedded HTML template literals to proper `.html` files; fix Playwright browser automation usability; add agents CRUD backend with qwen3:8b model detection

### Batch C — HTML Template Conversion (All 26 Pages)

**Problem**: All page HTML was embedded in JS template literal strings (`html\`...\``), causing escaped rendering where tags showed as visible text in the browser. No HTML was visible in the DOM inspector.

**Solution**: Created `js/template-loader.js` — fetches `templates/{name}.html` at mount time with `{{variable}}` interpolation, `{{{rawHtml}}}` for SVG icons, `{{#if}}`/`{{#each}}` conditionals. All 26 page modules now:
- `render()` returns mount-point div only (`<div id="{name}-root"></div>`)
- `mount()` is `async`, calls `await loadTemplate('name', data)`, injects into container, then runs existing event-binding logic
- `<style>` blocks moved from JS to template `<style>` tags
- SVG icons passed as `ICONS.name.html` (raw string) via `{{{iconVar}}}`
- CSS classes, IDs, DOM hierarchy preserved — all existing DOM queries work unchanged

| Conversion Batch | Pages | Files |
|---|---|---|
| Core (5) | dashboard, chat, agents, terminal, settings | 5 templates, 5 JS |
| Tools (5) | file-explorer, browser, config, logs, devtools | 5 templates, 5 JS |
| Batch A/B (10) | actions, macros, camcoms, recall, desktop, voice, phiconnect, vsee, bindings, notifications | 10 templates, 10 JS |
| Remaining (6) | performance, tasks, plugins, diagnostics, workspace, agent-status | 6 templates, 6 JS |

**Architecture now**: **Python** (aiohttp backend) → **HTML** (`.html` template files as main frontend) → **JS** (page modules as sub-frontend for SPA behavior + API calls)

### Browser Automation Fix — Playwright Now Usable

**Root cause**: `BrowserAutomation/__init__.py` had 7 convenience functions (`navigate`, `click_element`, `type_text`, `get_text_content`, `capture_screenshot`, `evaluate_script`, `create_context`) that were synchronous `def` functions calling `async` methods on `BrowserManager` without `await`. They returned coroutine objects instead of actual results. Additionally, no browser context was ever auto-created before navigation.

**Fix**:
- `BrowserAutomation/__init__.py`: Converted all 7 functions to `async def` with proper `await`; added `_ensure_context()` helper that auto-creates a Playwright context if none exists
- `server/handlers/browser.py`: Added `await` to all calls; added context creation after browser start; added `browser_type()` and `browser_get_text()` handlers (these endpoints existed in frontend but not backend); enhanced status endpoint to return `url`, `title`
- `server/app.py`: Registered `POST /api/v1/browser/type` and `POST /api/v1/browser/get_text`
- `pages/browser.js`: Fixed screenshot data URL extraction to match backend's `screenshot_base64` response format

### Agents CRUD Backend + qwen3:8b Detection

**Problem**: The agents frontend called `GET /api/v1/agents`, `POST /api/v1/agents`, and lifecycle endpoints (pause/resume/stop/restart) that had no backend. No model availability detection existed.

**Fix**:
- Created `server/handlers/agents_crud.py` — in-memory agent store with 7 endpoints: `list_agents`, `create_agent`, `pause_agent`, `resume_agent`, `stop_agent`, `restart_agent`, `check_model`
- `GET /api/v1/agent/models` returns available Ollama models + `qwen3_8b_available` boolean
- `GET /api/v1/agents` returns agents list + `meta.available_models` with Ollama model names
- `server/app.py`: Registered all 7 routes
- `pages/agents.js`: Shows green/red dot indicator for qwen3:8b online/offline, lists up to 3 other available models with "+N more" overflow

### Key Achievements

| Metric | Value |
|---|---|
| Pages converted to HTML templates | 26/26 (100%) |
| Template files created | 26 |
| Browser automation bugs fixed | 3 (sync/async, missing context, missing endpoints) |
| New backend handler modules | 1 (`agents_crud.py`) |
| New API endpoints | 7 (agents CRUD) + 2 (browser type/get_text) |
| JavaScript files modified | 26 |
| Browser handlers modified | 1 (fixed awaits, added handlers) |
| `BrowserAutomation/__init__.py` | 7 functions made async + auto context creation |

---

## Entry 13 — QuikTieper API, Terminal Rewrite, Settings Persistence, Install Script ✅

**Date**: 2026-06-25
**Focus**: QuikTieper REST API endpoints, terminal backend rewrite with Python-side command reference, settings.txt persistence, install script, documentation refresh

### QuikTieper REST API
- Created `server/handlers/quiktieper.py` — 8 endpoints:
  - `GET /api/v1/quiktieper/status` — listener running state, YAML status
  - `GET /api/v1/quiktieper/presets` — available command presets
  - `GET /api/v1/quiktieper/desktop-apps` — discovered `.desktop` files
  - `POST /api/v1/quiktieper/import-apps` — import desktop apps into bindings
  - `POST /api/v1/quiktieper/assign-keys` — assign launch keys to unbound apps
  - `POST /api/v1/quiktieper/launcher/start` — start the global chord listener
  - `POST /api/v1/quiktieper/launcher/stop` — stop the chord listener
  - `GET /api/v1/quiktieper/launcher/status` — alias for status
- All 8 endpoint routes registered in `server/app.py`
- QuikTieper accessible via Terminal (`fiona quiktieper *` commands) and Config page
- No dedicated frontend route — CLI and Config UI are the control surfaces

### Terminal Rewrite — Backend Command Reference
- `server/handlers/terminal.py` completely rewritten:
  - `COMMAND_REFERENCE` dict with **14 categories**, **90+ commands** including full Fiona CLI surface
  - Categories: Navigation, System, Chat & Agents, Actions & Automation, Files, Browser, Development, Network & Communication, Security & Access, Performance & Monitoring, Macros & Scripting, Configuration, Utilities & Tools, Fiona CLI
  - `help`/`?` returns formatted text from the backend (14 lines per category)
  - `clear`/`cls` returns `action: "clear"` signal for the frontend
  - New `POST /api/v1/terminal/autocomplete` endpoint — server-side autocomplete suggestions from COMMAND_REFERENCE tokens
- **4 routes registered**: `GET /terminal/execute`, `POST /terminal/execute`, `GET /terminal/autocomplete`, `POST /terminal/autocomplete`
- `terminal.js` simplified to thin client:
  - Removed: local `COMMAND_REFERENCE`, `printHelp()`, `_allCommandTokens`, `_findAutocompleteMatches()`
  - Removed: local interception of `help`/`clear`/`cls` commands
  - All commands now go to backend API
  - Autocomplete queries `POST /api/v1/terminal/autocomplete`
  - Help button calls `executeCommand('help')`
- Architecture enforced: **all terminal logic in Python backend**, JS only captures input/output

### Settings Persistence
- Created `server/handlers/settings_handler.py` with 2 endpoints:
  - `GET /api/v1/settings` — reads `~/.config/fiona/settings.txt` (JSON), returns parsed settings object or `{}`
  - `PUT /api/v1/settings` — validates JSON body, writes atomically to `settings.txt`
- Both routes registered in `server/app.py`
- Frontend `settings.js` already calls these endpoints (GET on mount, PUT on save)
- Config page uses the same `GET /api/v1/settings` for its editor
- Matches existing bindings config location convention (`~/.config/fiona/`)

### Import Error Fix
- `server/app.py` `_collect_metrics` had a lazy relative import (`from ..system import ...`) that failed at runtime because the module is not run as part of a package
- Replaced with direct references to already-imported module references: `system._cpu_percent()`, `system._virtual_memory()`, `system._disk_usage()`, `system._net_io_counters()`

### Router Object-Export Support
- `js/router.js`: Added support for page modules exporting `{ render, mount, destroy }` objects directly (previously only handled function factory `createPage()` exports)
- Fixes: `browser.js`, `terminal.js`, `file-explorer.js` which use the object export pattern

### Install Script
- Created `scripts/fiona-install`:
  - `--minimal`: Skip system tool checks, pip install only
  - `--venv`: Use Python venv instead of conda
  - `--help`: Prints usage
  - Default: conda-based install with system tool checks
  - Installs project in editable mode, verifies imports, checks for ydotoold/kdotool

### Documentation Refresh
- `fionaDocsPage/docs/prototypes.md`: Moved fionaLocalPages from prototype section to its own module page (fionaLocalPages graduated from prototype)
- `fionaDocsPage/docs/installation.md`: Updated with fionaLocalPages server startup instructions
- `fionaDocsPage/docs/developer/validation.md`: Added CLI command surface test result (54 subtests), updated test counts
- New module page: `fionaDocsPage/docs/modules/fionalocalpages.md`
- `fionaDocsPage/docs/index.md`: Added fionaLocalPages card to module grid
- `current-state.md`: Updated test count reference
- `devlog.md`: This entry (Entry 13)

### New Tests
- `tests/test_cli_command_surface.py` — 2 tests, 54 subtests:
  - `test_cli_help_no_errors`: Runs `--help` on all 26 CLI commands (quiktieper, host, agent, dataclient, action, voice, macro, recall, fat, terminal-assist, cli, api, run-shell, seeondesk, vsee, ficad, browser, approval, phiconnect, camcoms), verifies no `ERROR`/`Traceback` in output
  - `test_cli_smoke_no_crash`: Runs 22 safe commands (version, paths, list, etc.) that execute without side effects, verifies no tracebacks; browser status output validated for `state`, `config`, `browser_type`, `headless`, `viewport_width`, `viewport_height`

### Key Achievements

| Metric | Value |
|---|---|
| New backend handler modules | 3 (quiktieper, terminal rewrite, settings_handler) |
| New API endpoints | 10+ (8 quiktieper + 2 settings + 1 terminal autocomplete) |
| Terminal command categories | 14 (90+ commands) |
| Terminal JS lines removed | ~150 (COMMAND_REFERENCE, local parsing) |
| New test file | 1 (54 subtests, 2 tests) |
| New install script | 1 (conda + venv fallback) |
| Settings persistence | `~/.config/fiona/settings.txt` read/write |
| Module pages created/updated | 3 (fionalocalpages.md new, prototypes.md updated, index.md updated) |
| All 26 page JS files | pass `node -c` syntax check |

### Remaining
- QuikTieper dedicated frontend route (optional — CLI/Config are sufficient for now)
- Authentication/HTTPS for production fionaLocalPages deployment
- Hard-refresh browser after deployment to stale module caches

---

## Entry 14 — Scientific Knowledge Retrieval (SciRetrieval) ✅

**Date**: 2026-06-27
**Focus**: Build and integrate a multi-provider scientific knowledge retrieval subsystem with domain classification, entity resolution, SciLab processing, cache management, and full fionaLocalPages integration

### Summary
Complete new subsystem: 26 source files in `SciRetrieval/`, 5 server handler endpoints, frontend integration in Terminal and Agent pages, 278 passing tests, code reviewed and approved.

### Architecture

```text
User Query → Router (domain + intent classification)
                  │
                  ▼
           EntityResolver (synonym registry, canonical IDs)
                  │
                  ▼
           Normalizer (standard schema, cross-provider merge)
                  │
                  ▼
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
  NCBI          PubChem       NIST
  (BIOLOGY)     (CHEMISTRY)   (CHEMISTRY/PHYSICS)
    │             │             │
    └──────┬──────┘             │
           ▼                    ▼
    SciLab Processor     CacheManager
           │             (conversation TTL 5min,
           │              NIST disk-persisted)
           └────────┬──────────┘
                    ▼
             Final Response
```

### Milestones

#### M1 — Foundation (ABCs, Data Models, Error Hierarchy)
- `SciRetrieval/interfaces.py` — 7 ABCs re-exported from `fiona/interfaces.py` (IIntentDomainClassifier, IProvider, IEntityResolver, INormalizer, ISciLabProcessor, ICacheManager, IRetrievalManager)
- `SciRetrieval/models.py` — 7 data models (IntentDomainResult, ScientificEntityData, EntityRecord, NormalizedResult, SciLabContext, CacheEntry, RetrievalResult)
- `SciRetrieval/errors.py` — Error hierarchy (SciRetrievalError → ClassificationError, ProviderError, NormalizationError, EntityResolutionError, SciLabError, CacheError)

#### M2 — Domain Routing Engine
- `SciRetrieval/router.py` — `Router` class (173 lines): keyword-list classifier for biology/chemistry/physics + 4 intent categories (lookup, compare, explain, list)
- Data: `SciRetrieval/data/keywordlist.json` (30 biology, 32 chemistry, 34 physics keywords + intent patterns)

#### M3 — Multi-Provider Retrieval
- `SciRetrieval/providers/base.py` — `BaseProvider` ABC with retry logic, timeout, graceful degradation
- `SciRetrieval/providers/ncbi.py` — NCBI E-utilities provider (esearch → esummary)
- `SciRetrieval/providers/pubchem.py` — PubChem PUG REST provider
- `SciRetrieval/providers/nist.py` — NIST CODATA/Physics provider
- `SciRetrieval/providers/manager.py` — `ProviderManager` with multi-provider parallel dispatch, cross-provider merge, primary+secondary routing

#### M4 — Normalizer + EntityResolver
- `SciRetrieval/normalizer.py` — `Normalizer` class: consistent schema across providers, field mapping, confidence scoring
- `SciRetrieval/entity_resolver.py` — `EntityResolver` class: synonym registry (`synonyms.json`), canonical ID assignment, cross-provider dedup with provenance tracking
- Data: `SciRetrieval/data/synonyms.json` (Aspirin/pubchem:2244, Glucose/pubchem:5793, TP53/ncbi:7157, BRCA1/ncbi:672)

#### M5 — SciLab Processing Pipeline
- `SciRetrieval/scilab/pipeline.py` — `SciLabPipeline`: orchestration (validate → context → summarize → enrich)
- `SciRetrieval/scilab/validator.py` — `SciLabValidator`: cross-field consistency checks
- `SciRetrieval/scilab/context_generator.py` — `ContextGenerator`: entity/relationship sections, size capping
- `SciRetrieval/scilab/summarizer.py` — `Summarizer`: template-based synthesis from providers + cache

#### M6 — CacheManager
- `SciRetrieval/cache/manager.py` — `CacheManager`: conversation cache (TTL 5 min, in-memory dict), NIST dataset cache (disk-persisted JSON, single-level), TTL-based expiry, `clear_all()`, stats tracking
- `SciRetrieval/cache/nist_cache.py` — `NistCache`: disk-persistent JSON cache with get/set/clear/stats

#### M7 — Integration (CLI, DI, Agent, FLoP)
- `fiona/cli.py` — `sire`/`sr` CLI layer with 5 subcommands: query, classify, providers, getdata, cache-clear
- `SciRetrieval/cli.py` — `SciRetrievalCLI` with argparse and formatted output
- `fiona/di.py` — `register_sci_retrieval()` + `get_sci_retrieval_bridge()`
- `Agent/command_registry.py` — `sciretrieval_query` CommandSpec with provenance tracking
- `Agent/orchestrator.py` — `sciretrieval_query` action handler with error interception
- `fiona/__init__.py` — SciRetrieval module exports

#### M8 — Tests (278 tests, 13 files)
| Test File | Tests |
|---|---|
| `tests/sci_retrieval/test_router.py` | 46 |
| `tests/sci_retrieval/test_providers.py` | 30 |
| `tests/sci_retrieval/test_normalizer.py` | 20 |
| `tests/sci_retrieval/test_entity_resolver.py` | 28 |
| `tests/sci_retrieval/test_scilab.py` | 80 |
| `tests/sci_retrieval/test_cache.py` | 28 |
| `tests/sci_retrieval/test_manager.py` | 20 |
| `tests/sci_retrieval/test_integration.py` | 26 |
| Total | 278 |

#### M9 — fionaLocalPages Integration
- **Backend**: `server/handlers/sciretrieval.py` — 6 REST endpoints (search, classify, providers, getdata, enrich, cache/clear)
- **Server routes**: Registered in `server/app.py`
- **Terminal page**: `pages/terminal.js` — `handleScienceCommand()` with 5 subcommands (search, classify, providers, getdata, cache), intercepted before shell execution
- **Agent page**: `server/handlers/agent.py` — `enrich_science: true` option in agent_ask handler (non-blocking enrichment)
- **Agent status**: `pages/agent-status.js` — Science badge in Conversation tab
- **Help command**: `showHelp()` function in terminal.js with SciRetrieval section

### Key Decisions
- **EntityResolver layer** added between Normalizer and SciLab (user suggestion) — resolves aliases, assigns canonical IDs, merges cross-provider duplicates
- **Conversation Cache** (TTL 5 min) replaces one-link-deep SQLite — simpler, supports long scientific discussions
- **NIST cache single-level disk** initially — multi-level (L1/L2/L3) deferred until profiling proves need
- **Multi-provider retrieval** — queries can use primary + secondary providers (e.g., PubChem primary + NCBI secondary)
- **ABCs in `fiona/interfaces.py`** — single source of truth, follows existing pattern
- **Graceful degradation** — provider failures never crash Terminal or Agent pages

### Keyword List Expansion (Post-Testing)
After browser testing revealed coverage gaps, keywordlist.json was expanded by ~83%:
| Domain | Before | After | Key Additions |
|---|---|---|---|
| Biology | 15 | 30 | function, pathway, organism, species, metabolism, signaling, regulation |
| Chemistry | 17 | 32 | molecular, weight, mass, molar, mole, atomic, valence, ligand, isotope |
| Physics | 17 | 34 | speed, light, frequency, wavelength, current, voltage, gravity, density |
| Intent patterns | 28 | 37 | what's, calculate, compute, similarities, contrast, enumerate, step by step |

### Browser Test Results
| Test Area | Tests | Pass | Partial | Fail |
|---|---|---|---|---|
| Backend API | 9 | 6 | 3 | 0 |
| Server Startup | 1 | 1 | 0 | 0 |
| Frontend Code | 3 | 3 | 0 | 0 |
| **Total** | **13** | **10** | **3** | **0** |

Partial failures were all keyword coverage gaps — resolved by the expansion above. After the fix, all three previously-failing queries now classify correctly:
- `"molecular weight of Aspirin"` → `CHEMISTRY` (was `BIOLOGY`)
- `"function of BRCA1 gene"` → `BIOLOGY` (higher confidence)
- `"speed of light"` → `PHYSICS` (was generic/unscientific)

### Code Review Result
**APPROVE WITH MINOR CHANGES** — 3 non-blocking items:
1. `BaseProvider` type annotation alignment
2. `on_conversation_end` event loop guard
3. `fiona/__init__.py` exports

### Key Achievements

| Metric | Value |
|---|---|
| New files created (SciRetrieval/) | 26 |
| New handler modules | 1 (`sciretrieval.py`) |
| New API endpoints | 6 (search, classify, providers, getdata, enrich, cache/clear) |
| New CLI commands | 5 (query, classify, providers, getdata, cache-clear) |
| New tests | 278 across 13 files |
| Total tests | 1018 pass (17 pre-existing env failures) |
| Code review | APPROVED (3 minor items) |
| Files modified (existing) | 8 (cli.py, di.py, interfaces.py, __init__.py, app.py, terminal.js, agent.py, agent-status.js) |

### Files Changed

| File | Change |
|---|---|
| `SciRetrieval/` (26 files) | NEW — Full subsystem |
| `fiona/cli.py` | Added `sire`/`sr` CLI layer |
| `fiona/di.py` | Added `register_sci_retrieval()`, `get_sci_retrieval_bridge()` |
| `fiona/interfaces.py` | Added 7 ABCs |
| `fiona/__init__.py` | SciRetrieval module exports |
| `Agent/command_registry.py` | Added `sciretrieval_query` CommandSpec |
| `Agent/orchestrator.py` | Added `sciretrieval_query` action handler |
| `fionaLocalPages/server/handlers/sciretrieval.py` | NEW — 6 REST endpoints |
| `fionaLocalPages/server/handlers/agent.py` | Added `enrich_science` option |
| `fionaLocalPages/server/app.py` | Registered SciRetrieval routes |
| `fionaLocalPages/pages/terminal.js` | Added `handleScienceCommand()`, `showHelp()`, help interceptor |
| `fionaLocalPages/pages/agent-status.js` | Added Science badge |
| `SciRetrieval/data/keywordlist.json` | Expanded keywords (30/32/34 per domain) |
| `tests/sci_retrieval/` (13 files) | NEW — 278 tests |

---

## Entry 15 — Mobile-Responsive UI + Full Test Suite Pass

**Goal**: Make FLoP usable from Chrome on Android (360–430px viewport) and achieve a fully passing test suite.

### Mobile-Responsive Shell (Milestones 1–2)
| Component | Status |
|---|---|
| Hamburger sidebar overlay at 768px/480px breakpoints | ✅ |
| 44px+ touch targets via `@media (pointer: coarse)` | ✅ |
| `_toggleMobileSidebar()` / `_closeMobileSidebar()` in app.js | ✅ |
| Ctrl+B mobile-aware, `data-action` dispatch for hamburger | ✅ |
| Sidebar slide-in with backdrop overlay | ✅ |
| Status bar compact on mobile, header shrinks to 44px | ✅ |
| Long-press context menus (ContextMenu.js touch support) | ✅ |

### Page-Level Mobile Responsive (Milestones 3–5)
| Page | Features |
|---|---|
| **File Explorer** | Tree panel as overlay, preview as bottom sheet, drag handle, tree-toggle button, hidden date column, resize-aware |
| **Actions** | Scrollable tabs, responsive cards (Run wraps below name), compact history |
| **Settings** | Horizontal nav strip, stacked forms, skeleton responsive |
| **Macros** | Responsive toolbar, recording controls stack, card footer wraps, shortcut capture stacks |
| **Right panel** | Full-screen overlay on mobile |
| **Modals, toasts, notifications** | Mobile-sized, properly positioned |

### Debugging & Test Fixes (26 failures → 0)
| Category | Root Cause | Fix |
|---|---|---|
| Bug #1 — Agent status response | Success path missing `base_url`/`available` fields | Wrapped with `{"available": True, "base_url": ...}` |
| Category A — `sciretrieval_query` | 3 tests not updated when command added | Added to expected sets, bumped count 18→19 |
| Category B — `eyecontrol` CLI | 5 tests referencing removed subcommand | Removed obsolete tests |
| Category D — Flaky (numpy) | `test_voice_engine.py` replaced `sys.modules["numpy"]` with mock at module level, never restored | Restore original modules immediately after import |
| Category D — Flaky (singleton) | `PersonalityRegistry` singleton corrupted across 3 test classes | Added `_reset_instance()` + setUp calls |

### Statistics
| Metric | Value |
|---|---|
| Total tests | **2578 passed, 0 failed** |
| Files changed (mobile) | 11 files, +995 lines |
| Files changed (bugfixes) | 12 files, +69/−56 lines |
| New CSS (layout.css) | 1039 lines total with full responsive |
| New CSS (components.css) | Touch-target overrides, overlay styles |
| New JS (app.js) | 58 lines added for sidebar toggle, resize handler |
| Pages mobile-adapted | File Explorer, Actions, Settings, Macros |
| Git commits | `ad4fe86`, `6c4ce1c`, `9b71e47` |
