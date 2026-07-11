# Fiona Modular Platform Restructure

> Completed: July 2026
> Branch: `restructure/phase-1`

## Motivation

The original Fiona codebase was flat — 20+ subsystem packages, config directories,
tests, CLI entry point, and web frontend all lived at the project root. This made
navigation, comprehension, packaging, and CI difficult. The goal was to reorganize
into a modular platform where each concern has a clear home.

## Goal

```
Fiona/
├── fiona-core/      ← All subsystem packages + core implementation + shims
├── fiona-cli/       ← CLI entry point
├── fiona-pages/     ← Web dashboard (was fionaLocalPages)
├── fiona-tests/     ← All tests
├── fiona-gitdev/    ← Git/CI dev tooling
├── fiona-examples/  ← Example usage scripts
├── fiona-docs/      ← MkDocs documentation site (gitignored)
├── fionaDocsPage/   ← Original docs deployment (preserved, gitignored)
├── scripts/         ← Utility scripts
├── pyproject.toml
├── README.md
└── (minimal root config files)
```

## What Was Done

### Phase 1 — fiona-core (merged core)
- `fiona/` (umbrella package) + `FionaCore/` (shared primitives) → merged into
  `fiona-core/fiona_core/`
- Name collision resolved: `FionaCore/actions.py` → `fiona_core/_core_actions.py`,
  unified exports in `fiona_core/actions/__init__.py`
- `fiona-core/fiona_core/plugin_system.py` base-dir calculation changed from rigid
  `parent.parent` to upward search for `pyproject.toml`

### Phase 2 — fiona-cli (CLI extraction)
- `fiona/cli.py` → `fiona-cli/fiona_cli/cli.py`
- Entry point in `pyproject.toml`: `fiona = "fiona_cli.cli:main"`
- All imports updated from `from fiona.xxx` / `from FionaCore.xxx` to
  `from fiona_core.xxx`

### Phase 3 — Backward-compat shims
- Old `fiona/` and `FionaCore/` packages became thin re-export shims that
  redirect imports to `fiona_core`
- Shim uses `sys.modules` aliases + PEP 562 `__getattr__` fallback
- 14+ submodule stub files created at `fiona/tools/models.py` etc. so
  `from fiona.tools.models import ToolCall` still works
- `fiona/cli.py` shim re-exports `main`, `_handle_list_macros`,
  `_handle_run_macro` from `fiona_cli.cli`

### Phase 4 — fiona-pages (web dashboard)
- `fionaLocalPages/` → `fiona-pages/` (`git mv`)
- Python package renamed `fionaLocalPages` → `fiona_pages`
- 26 import lines updated across server handlers
- Path calculations in `app.py`, `flask_app.py`, `files.py` fixed

### Phase 5 — fiona-docs (documentation site)
- `fionaDocsPage/` copied to `fiona-docs/` (gitignored, separate deployment)
- Original `fionaDocsPage/` preserved at root
- 26 documentation files updated to reflect new architecture paths

### Phase 6 — fiona-tests (test migration)
- `tests/` → `fiona-tests/fiona_tests/` (`git mv`, 119 files)
- `pyproject.toml`: `testpaths = ["fiona-tests"]`, packages updated

### Phase 7 — Mantatree (new foundation layer)
- Created at `fiona-core/Mantatree/mantatree/`
- Core interfaces: `Link`, `LinkType`, `LinkGraph`, `LinkStore` ABC
- Foundation only — no wiring to existing subsystems yet

### Phase 8 — fiona-gitdev + fiona-examples
- `fiona-gitdev/fiona_gitdev/` with VERSION, hooks/, ci/, scaffold stub
- 4 example scripts under `fiona-examples/`

### Phase 9 — pyproject.toml & packaging
- Entry point changed to `fiona = "fiona_cli.cli:main"`
- `[tool.setuptools.packages]` lists all packages explicitly
- `[tool.setuptools.package-dir]` maps each package to its subdirectory
  (e.g., `Agent = "fiona-core/Agent"`)
- `[tool.setuptools.package-data]` for CamComs esp32payload

### Phase 10 — Root cleanup
- 20+ subsystem packages moved from root into `fiona-core/`:
  Agent, BrowserAutomation, Calendar, CamComs, CmdTrace, Communications,
  DataClient, EyeControl, GNS3Automation, HomeBackend, Laboratory, PhiConnect,
  QuikTieper, RecallVault, SciPhi, SciRetrieval, SeeOnDesk, SmartHome,
  TerminalAssist, Voice
- Config/data directories moved: `actions/`, `agents/`, `config/`, `rules/`, `skills/`
- **Vsee** and **cad** modules removed entirely (not just moved — deleted)
- `MDfiles/` and `PDFs/` document directories moved into `fiona-core/`
- Leftover empty `tests/` directory removed

### Phase 11 — Regression fixes
- **eyecontrol CLI subcommand**: Added to `_build_parser()` (was missing entirely)
- **Agent status `base_url`**: Added to success response (was only on error path)
- **Stale test paths**: 4 test files + `plugin_system.py` fixed for new directory layout
- **Stale test expectations**: 3 tests updated for new `sciretrieval_query` command
- **Dependency fix**: `aiohttp` pinned to `<3.14` for `aioresponses` compatibility
- **Missing deps**: `pytesseract`, `selenium`, `webdriver-manager` installed

## Current Layout

```
Fiona/
├── fiona-core/
│   ├── fiona_core/          # Merged fiona/ + FionaCore/ implementation
│   ├── fiona/               # Backward-compat shim → fiona_core
│   ├── FionaCore/           # Backward-compat shim → fiona_core
│   ├── Mantatree/           # New relationship/ontology layer
│   ├── Agent/               # Subsystem packages (20+)
│   ├── QuikTieper/
│   ├── CamComs/
│   ├── ... (all subsystems)
│   ├── actions/             # Data/config directories
│   ├── agents/
│   ├── config/
│   ├── rules/
│   ├── skills/
│   ├── MDfiles/
│   └── PDFs/
├── fiona-cli/
│   └── fiona_cli/cli.py     # CLI entry point
├── fiona-pages/
│   └── fiona_pages/         # Web dashboard (was fionaLocalPages)
├── fiona-tests/
│   └── fiona_tests/         # All tests
├── fiona-gitdev/
│   └── fiona_gitdev/
├── fiona-examples/          # Example scripts
├── fiona-docs/              # MkDocs site (gitignored)
├── fionaDocsPage/           # Original docs deployment (gitignored)
├── scripts/                 # Utility scripts
├── pyproject.toml
├── README.md
└── restructure.md           # This file
```

## Backward Compatibility

All old import paths continue to work via shims:

| Old import | New canonical import |
|------------|---------------------|
| `import fiona` | `import fiona_core` (shim → fiona_core) |
| `from fiona.tools.models import ToolCall` | `from fiona_core.tools import models` |
| `from FionaCore.actions import execute_action` | `from fiona_core.actions import execute_action` |
| `python3 -m fiona.cli` | `fiona` (console script) |
| `from Agent import AgentManager` | Same — Agent is now at `fiona-core/Agent/` |

## Modules Removed

| Module | Reason |
|--------|--------|
| **Vsee** (`Vsee/`) | 3D wireframe viewer, experimental, unused |
| **CAD** (`cad/`) | Experimental parametric modeler, unused |

## Test Results (Post-Restructure)

- **2,168 tests pass**, 0 failures caused by restructure
- 19 pre-existing test-isolation failures (shared singleton state, order-dependent)
- All 37 critical import paths verified (platform + subsystems + shims)
- `pip install -e .` succeeds cleanly
- `mkdocs build --strict` passes with zero errors

## Documentation

The `fionaDocsPage/` directory (original docs deployment) was updated to reflect
the new architecture — 26 files modified covering module paths, project layout,
removed modules, and operations guides.
