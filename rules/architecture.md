# Fiona Architecture Reference

## Project Structure

Fiona is a **monorepo** of ~20 sibling Python packages under a single
`pyproject.toml`. The `fiona/` umbrella package hosts the CLI entry point and
cross-cutting infrastructure. Each sibling package is a self-contained
subsystem.

### Top-Level Packages

| Package | Purpose | Key Files |
|---|---|---|
| `fiona/` | CLI entry point, DI container, interfaces, logging, metrics, tracing, plugin system | `cli.py`, `di.py`, `interfaces.py`, `logging.py`, `metrics.py`, `tracing.py`, `plugin_system.py` |
| `Agent/` | LLM agent integration (Ollama), orchestration, chat, permissions, personalities | `ollama.py`, `orchestrator.py`, `orchestration.py`, `personality.py`, `command_registry.py`, `chat_handler.py`, `chat_store.py`, `permission.py`, `cancellation.py`, `query_detector.py` |
| `FionaCore/` | Shared primitives: action router, permissions, approval, voice, macros, notifications, shell safety, verification | `actions.py`, `permissions.py`, `approval.py`, `voice.py`, `macros.py`, `notifications.py`, `shell_safety.py`, `verification.py`, `speech.py`, `acl.py`, `gui_theme.py`, `voice_engine.py`, `macro_engine.py` |
| `cad/` | Parametric 3D modeler with JSON-RPC 2.0 server and 3js frontend | `server/_app_builder.py`, `server/_server.py`, `server/_document_manager.py`, `server/_command_executor.py`, `server/_export_manager.py`, `server/_handlers.py`, `server/_protocol.py`, `server/_websocket_handler.py`, `server/_frontend/` |
| `BrowserAutomation/` | Selenium-based browser automation, state machine, module-level convenience API | `_manager.py`, `_selenium_provider.py`, `_config.py`, `_errors.py`, `_session_manager.py`, `__init__.py` |
| `QuikTieper/` | Local access layer: keyboard, mouse, app launcher | — |
| `CamComs/` | Encrypted computer-to-computer communication | — |
| `Voice/` | Wake word detection, audio feedback | — |
| `DataClient/` | Topic search, scraping, summarization, CSV export | — |
| `TerminalAssist/` | btop-style dashboard, Zellij workspace | — |
| `SeeOnDesk/` | Desktop-awareness snapshots | — |
| `Vsee/` | 3D coordinate hologram viewer | — |
| `PhiConnect/` | Encrypted computer-to-computer chat | — |
| `RecallVault/` | Structured remembrance storage | — |
| `EyeControl/` | MediaPipe-based eye tracking | — |
| `CmdTrace/` | Command trace storage | — |

## Key Design Patterns

### CLI Dispatch — `fiona/cli.py`
- Single `argparse` parser with ~20 layer-based subcommand groups.
- Each layer has an `_add_*` helper and a `_run_*` handler.
- Layers: `quiktieper`, `camcoms`, `agent`, `dataclient`, `action`, `voice`,
  `macro`, `recall`, `fat`, `cli`, `seeondesk`, `ficad`, `browser`, `approval`,
  `vsee`, `phiconnect`, `api`, `run-shell`.
- All layers share `_add_ollama_args(parser)` for `--model` and `--base-url`.
- Entry point: `fiona = "fiona.cli:main"` in `pyproject.toml`.

### DI Container — `fiona/di.py`
- `FionaContainer` with `register_instance()`, `register_factory()`, `resolve()`.
- Thread-safe via `threading.RLock()`.
- Used in `cad/server/_app_builder.py` to wire `document_manager`,
  `command_executor`, `export_manager`, `event_bus`.

### EventBus — `fiona/interfaces.py`
- In-process pub/sub with typed `Event` dataclasses.
- `subscribe(event_type, callback)` → `Subscription` token.
- `publish(event)` — fire-and-forget.
- Thread-safe via `threading.Lock()`.
- Event subtypes: `DocumentEvent`, `BrowserEvent`, `BrowserLaunched`,
  `NavigationCompleted`, etc.

### Action Router — `FionaCore/actions.py`
- `ActionRouter` with `dict[str, ActionSpec]` registry.
- `ActionSpec`: name, command, description, risk, permission, external, sender_scope, requires_confirmation.
- `run()` performs: ACL check → permission check → dry-run → external guard → verification prompt → subprocess execution.
- Thread-safe via `threading.RLock()`.
- `default_action_specs()` returns ~25 built-in actions.

### Permission Model — `FionaCore/permissions.py`
- `PermissionProfile`: name, max_risk, allowed_permissions (frozenset).
- Profiles: `local` (max risk=high), `agent` (max risk=medium), `remote_safe` (max risk=low).
- `permission_allows(profile, risk, permission)` checks both risk level and permission membership.

### Approval Manager — `FionaCore/approval.py`
- `PlanStatus`: PENDING → APPROVED/DENIED → EXECUTING → COMPLETED/FAILED/CANCELLED.
- `wait_for_approval(plan_id, timeout)` — blocking wait via `threading.Event`.
- Singleton via `get_approval_manager()`.

### Module-Level Singletons
- `BrowserAutomation.__init__`: `_default_manager`, `get_browser_manager()`.
- `FionaCore.approval`: `_default_manager`, `get_approval_manager()`.
- `fiona.metrics`: `metrics` singleton.
- `fiona.tracing`: `tracer` singleton.

### Lazy Optional Dependencies
- `BrowserAutomation` imports Selenium lazily (in `_selenium_provider.py`).
- `Voice` backends imported lazily.
- YAML support in `plugin_system.py` conditionally imported.

### Package Exports
Every sibling package defines an explicit `__all__` list in its `__init__.py`.
The `fiona/__init__.py` umbrella re-exports all siblings via `import ... as ...`
and `sys.modules` aliasing, plus `__getattr__` lazy loading for `ChordListener`.

## Testing Layout

```
tests/
├── browser/test_browser_manager.py            # 24 tests (Selenium state machine)
├── cad_server/test_command_executor.py, test_document_manager.py, test_export_manager.py, test_protocol.py
├── contracts/test_interface_contracts.py
└── test_*.py  (flat file-per-subsystem, ~55 files)
```

## Key CLI Commands

| Command | Action |
|---|---|
| `fiona agent --goal "..."` | Run agent orchestration |
| `fiona ficad --port 8765` | Start CAD server + 3js frontend |
| `fiona browser start` | Start browser automation |
| `fiona approval list` | List pending approval plans |
| `fiona approval approve <plan_id>` | Approve a plan |
| `fiona approval deny <plan_id>` | Deny a plan |

## Model Configuration

- Default model: `qwen3:8b-en` (set in `Agent/ollama.py`, `fiona/cli.py`,
  `Agent/personality.py`).
- Each `Personality` can specify a `model_override`.
- Controller personality uses `model_override="qwen3:8b-en"`.
