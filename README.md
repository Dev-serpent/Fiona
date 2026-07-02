# Fiona

Fiona is a local host-control platform inspired by JARVIS-style workstation automation. It combines a modern web dashboard, encrypted device communication, desktop awareness, voice control, macros, automations, a local Ollama AI bridge, and a growing ecosystem of subsystems — all running locally with zero cloud dependency.

For a broader overview, visit: https://dev-serpent.github.io/Project_Fiona/

---

# Section 1 — FLoP: Fiona Local Pages (Web Frontend)

FLoP is the primary user interface for Fiona — a server-rendered web dashboard served by Flask (port 5000) alongside an aioHTTP API/WebSocket server (port 8765). It replaces the earlier single-page application with a faster, more reliable multi-page architecture.

> **Open FLoP:** [http://fiona.agent:5000](http://fiona.agent:5000)
>
> **API server:** [http://fiona.agent:8765](http://fiona.agent:8765)

## Quick Start

```bash
cd Fiona
./scripts/fiona-pages-start        # Start both servers
./scripts/fiona-pages-stop         # Stop both servers
```

Both servers start automatically. Open `http://fiona.agent:5000` in any browser.

## Page Overview

FLoP ships with **24 server-rendered pages**, all backed by real backend data:

| Page | Route | Features |
|------|-------|----------|
| **Dashboard** | `/` | Live CPU/memory/disk/uptime metrics with 10s auto-polling, quick-action cards, notification summary |
| **AI Chat** | `/chat` | Session management, message send/receive, session sidebar |
| **Agents** | `/agents` | Agent listing, status, model info |
| **Actions** | `/actions` | Action library, run action, risk/permission display |
| **Settings** | `/settings` | Full configuration tree with inline editing |
| **Terminal** | `/terminal` | Terminal emulator (JS-powered) |
| **SeeOnDesk** | `/desktop` | Active window, system resources, installed apps, running processes |
| **Task Queue** | `/tasks` | Kanban board, create/edit/delete tasks, status transitions |
| **Notifications** | `/notifications` | Notification center, dismiss, clear all |
| **Macros** | `/macros` | Macro list with search, run, step count, shortcut display |
| **Key Bindings** | `/bindings` | Binding table with search |
| **Voice Commands** | `/voice` | Voice service status, setup guide, command reference |
| **RecallVault** | `/recall` | Key-value store with search, copy, truncation |
| **Logs** | `/logs` | Terminal-style log viewer with live metric updates |
| **CamComs** | `/camcoms` | CamComs service status, pairing, camera/audio features |
| **Workspace** | `/workspace` | Virtual desktops, system information |
| **Plugins** | `/plugins` | Plugin list with enable/disable status |
| **Configuration** | `/config` | Config file viewer with search, expand/collapse JSON |
| **Diagnostics** | `/diagnostics` | System information, health checks, network interfaces, processes |
| **Dev Tools** | `/devtools` | Developer tools overview |
| **PhiConnect** | `/phiconnect` | PhiConnect status, trusted peers list |
| **Browser** | `/browser` | Browser automation status and controls |
| **File Explorer** | `/files` | File browser with breadcrumb, sizes, dates |
| **Performance** | `/performance` | Live CPU/memory/disk resource cards with 10s polling |

## Architecture

FLoP runs **two co-operative servers**:

```
┌─────────────────────────────────────────────────────────┐
│                   Browser (port 5000)                    │
│  Jinja2-rendered HTML · CSS variables · Vanilla JS      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────┴──────────────────────────────────┐
│  Flask Server (flask_app.py, port 5000)                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 24 page routes + 9 AJAX POST endpoints           │   │
│  │ Templates: templates_jinja/ (26 files)           │   │
│  │ Static: css/, js/, images/                       │   │
│  └──────────────┬───────────────────────────────────┘   │
│                 │ _call_handler() bridge                 │
│  ┌──────────────┴───────────────────────────────────┐   │
│  │ aioHTTP Handler Modules (server/handlers/)        │   │
│  │ 24 handler files, 150+ async functions            │   │
│  └──────────────┬───────────────────────────────────┘   │
└─────────────────┼────────────────────────────────────────┘
                  │
┌─────────────────┴────────────────────────────────────────┐
│  aioHTTP API Server (app.py, port 8765)                   │
│  REST API at /api/v1/ · WebSocket at /ws · SSE at /stream │
│  Static files · SPA redirect → Flask (port 5000)         │
└──────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Server-rendered pages** (Jinja2) instead of client-side Handlebars — eliminates `{{#if}}` template rendering bugs in the browser
- **Direct Python imports** — page data functions import handler modules directly instead of making HTTP loopback calls
- **`_call_handler()` bridge** — wraps aioHTTP async handlers with mock requests so Flask can reuse them without modification
- **AJAX POST endpoints** for interactive actions (task CRUD, settings save, chat send, action run, notification dismiss) — no full-page postbacks
- **Auto-polling JS** on dashboard, performance, and logs pages — updates metrics in-place every 10 seconds via `fetch()`
- **Dual-server architecture** — Flask serves rendered pages, aioHTTP continues serving the REST API and WebSocket for any remaining SPA integration

## Interactive Features

FLoP pages support live user interaction without page reloads:

| Feature | Page | Mechanism |
|---------|------|-----------|
| Task CRUD | Tasks | Modal form, status buttons, delete — all via `POST /tasks/*` |
| Settings save | Settings | Inline editing, Save All — via `POST /settings/save` |
| Chat send | Chat | Send button + Enter key — via `POST /chat/send` |
| New chat | Chat | New Session button — via `POST /chat/new` |
| Run action | Actions | Run button per row — via `POST /actions/run` |
| Clear/dismiss | Notifications | Clear All + per-item dismiss — via `POST /notifications/*` |
| Search/filter | Macros, Config, Recall | Client-side JS filtering |
| Copy value | Config, Recall | Clipboard API with fallback |
| Expand JSON | Config | Toggle expand/collapse for nested values |
| Live metrics | Dashboard, Performance, Logs | 10s auto-poll via `GET /api/v1/system/metrics` |

## Data Flow

```
User clicks "Create Task"
  → JS fetch(POST /tasks/create, {title, priority})
  → Flask route: import tasks.create_task
  → _call_handler_post(create_task, body)
  → creates MagicMock request with JSON body
  → runs create_task(mock_request) in new event loop
  → returns JSON response
  → JS: if ok, location.reload()
```

---

# Section 2 — CLI & Subsystems

## Installation

```bash
git clone <repo-url> Fiona
cd Fiona
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Conda works too:

```bash
conda create -n fiona python=3.13
conda activate fiona
git clone <repo-url> Fiona
cd Fiona
pip install -e .
```

Core dependencies: `cryptography`, `pynput`, `numpy`, `pandas`, `requests`.

After installation:

```bash
fiona                  # Open the CLI help
fiona edit             # Open the Tkinter GUI editor
```

When running from a source checkout before installing the console script:

```bash
cd Fiona
python3 -m fiona.cli <command>
```

## Subsystem Overview

Fiona exposes **fifteen sibling subsystems**, each in its own package:

| Subsystem | Directory | Purpose |
|-----------|-----------|---------|
| **QuikTieper** | `QuikTieper/` | Local access layer — keyboard chords, app launching, shortcuts, pointer control, remote action execution |
| **CamComs** | `CamComs/` | Encrypted communication — X25519 key agreement, AES-GCM payloads, Ed25519 signatures, ESP32 sender protocol, pairing, trust management |
| **FionaCore** | `FionaCore/` | Shared primitives — action routing, ACL permissions, shell safety, macro engine, verification prompts, notifications, speech |
| **Voice** | `Voice/` | Voice interface — wake-word detection, push-to-talk, feedback engine |
| **Vsee** | `Vsee/` | 3D hologram viewer — point/edge wireframe rendering |
| **Agent** | `Agent/` | Local Ollama bridge — think-act-observe loop, command registry, tool runtime |
| **PhiConnect** | `PhiConnect/` | Encrypted computer-to-computer chat using CamComs crypto primitives |
| **SeeOnDesk** | `SeeOnDesk/` | Desktop awareness — active window detection, process tracking, workspace monitoring |
| **TerminalAssist** | `TerminalAssist/` | btop-inspired terminal dashboard (`fAT`), Zellij workspace helper |
| **RecallVault** | `RecallVault/` | Persistent key-value store with categories, tags, TTL/expiry, import/export (JSON/CSV), timestamped backups, statistics, and optional TF-IDF semantic search |
| **SciPhi** | `SciPhi/` | Scientific computing framework — model definition, OpsimKernel orchestration, hypothesis engine, uncertainty analysis, domain solvers (physics, chemistry, biology, earth science, engineering) |
| **SciRetrieval** | `SciRetrieval/` | Scientific knowledge retrieval — domain-aware query routing to NCBI/PubChem/NIST with normalization, entity resolution, and caching |
| **CmdTrace** | `CmdTrace/` | Action trace observability — JSONL audit log with statistics, advanced search, CSV/JSON export, auto-compaction by size/age, and live tail monitoring |
| **DataClient** | `DataClient/` | Research and data collection — web mining, deep research, CSV/JSON/SQLite table editor |
| **EyeControl** | `EyeControl/` | Optional camera-based eye-controlled mouse tracker |

## CLI Commands

Once installed (`pip install -e .`):

```bash
fiona                          # Show help
fiona edit                     # Open the shared Tkinter GUI editor
fiona init                     # Create default bindings config
fiona list                     # List configured app launch chords
fiona run                      # Start the global QuikTieper listener
fiona seeondesk active         # Show currently focused window
fiona seeondesk status         # Full desktop-awareness snapshot
fiona recall remember <k> <v>  # Store a recall item (--category, --ttl-seconds, --tags)
fiona recall search <q>        # Search recall items
fiona recall forget <k>        # Remove a recall item
fiona recall stats             # Show vault statistics (entries, categories, tags, storage)
fiona recall export            # Export vault to JSON or CSV (--format, --output)
fiona recall import <file>     # Import entries from JSON or CSV file
fiona recall backup            # Create a timestamped backup of the vault
fiona action history           # Show recent action trace log
fiona action stats             # Show trace statistics (per-action counts, success/failure, durations)
fiona action export            # Export trace to JSON or CSV
fiona action compact           # Compact/rotate trace by size or age
fiona action tail              # Live-follow new trace entries
fiona agent status             # Check Ollama connection
fiona agent ask --model <m> "prompt"   # Ask the local AI model
fiona agent commands           # List available agent commands
fiona camcoms smoke-test       # Test encryption/decryption
fiona camcoms keygen --device-id host  # Generate identity keys
fiona camcoms trust --public <file>    # Trust a sender public key
fiona camcoms receive           # Start the CamComs receiver
fiona host status               # Host service status
fiona host run                  # Start the unified host service
fiona fat status                # Terminal dashboard status
fiona fat run                   # Launch Zellij workspace
fiona vsee                      # Open standalone hologram viewer
fiona phiconnect                # Open encrypted chat app
fiona dataclient mine <topic>   # Quick web research
fiona dataclient deep <topic>   # Deep research
fiona sire query "question"     # Scientific knowledge retrieval
fiona sciphi run "prompt"       # SciPhi simulation (via OpsimKernel pipeline)
fiona sciphi explore "topic"    # Interactive SciPhi exploration mode
fiona import-apps               # Import desktop .desktop launchers
fiona assign-keys               # Assign launch keys to apps
fiona --tray-only               # System tray icon only
fiona --discover-actions        # Discover available actions
```

### Module-form (before installation):

```bash
python3 -m fiona.cli <command>
```

## Project Layout

```text
fiona/                  Umbrella package and CLI entrypoint
QuikTieper/             Local access/action layer (key chords, app launcher)
CamComs/                Communication/encryption/host-service/pairing
CamComs/esp32payload/   ESP32 sender payload template
FionaCore/              Shared action, ACL, macro, voice, security primitives
Voice/                  Wake word, push-to-talk, and feedback engine
Vsee/                   3D point/edge hologram model
Agent/                  Local Ollama client with planning loop, tool runtime
PhiConnect/             Encrypted computer-to-computer chat app
SeeOnDesk/              Desktop awareness, process tracking, workspace watcher
TerminalAssist/         btop-inspired terminal dashboard (fAT), Zellij helper
RecallVault/            Persistent remembrance store
SciRetrieval/           Scientific knowledge retrieval subsystem
SciPhi/                 Scientific computing framework (OpsimKernel, models, solvers)
Calendar/               Events, reminders, and scheduling subsystem
DataClient/             Research/data collection app
EyeControl/             Optional camera-based eye tracker
CmdTrace/               Action trace logging
fionaLocalPages/        Web frontend (FLoP) — Flask + Jinja2 templates
fionaLocalPages/server/ API server (aioHTTP), REST handlers, Flask routes
fionaLocalPages/templates_jinja/  Jinja2 page templates (26 files)
scripts/                Local launch wrappers (fiona-pages-start, fiona-edit, etc.)
tests/                  Python tests (1018+)
```

## Optional Dependencies

```bash
pip install -e ".[eyecontrol]"     # OpenCV, MediaPipe for eye tracker
pip install pvporcupine             # Best wake word detection
pip install snowboy                 # Alternative wake word
pip install pystray Pillow          # System tray icon
pip install -e ".[sciretrieval]"    # aioHTTP for SciRetrieval providers
pip install -e ".[sciphi]"         # scipy, sympy, matplotlib for SciPhi solvers and visualization
```

System tools for local control: `ydotool`, `kdotool`, `xdotool`, `xprop`, `aplay`, `paplay`, `notify-send`, `scrot`.

## Key Subsystem Details

### QuikTieper (Local Access Layer)

Listens for simultaneous global key chords and runs configured actions:

- App launching from chord bindings (e.g., `alt + b + r + v` opens Brave)
- Desktop application discovery from `.desktop` launchers
- App-specific shortcuts gated by active-window matching
- Shell command execution with safety checks
- Pointer movement and click helpers
- Allowlisted remote actions for CamComs instructions
- Structured macro instructions with nested steps

Config path: `~/.config/fiona/bindings.json`

### CamComs (Encrypted Communication)

Current direction: `ESP32 sender → encoded encrypted HTTP POST → Fiona host receiver`

Implemented: X25519 key agreement, HKDF-SHA256, AES-GCM, Ed25519 signatures, base64url JSON envelopes, trusted sender store with expiry, replay protection, host receiver, pairing protocol, key rotation.

### FionaCore (Shared Primitives)

- **Action Router** — Central dispatch with ACL and verification
- **ACL System** — Sender-scoped permissions (`local`, `ssh`, `websocket`, `ble`)
- **Shell Safety** — Blocks 30+ destructive shell patterns
- **Macro Engine** — Waits, conditions, branching, GOTO, variable interpolation
- **Verification Prompts** — Desktop or terminal prompts for high-risk actions

### Agent & Ollama

The Agent bridge communicates with Ollama's local OpenAI-compatible API:

```bash
python3 -m fiona.cli agent ask --model qwen3:8b "What is the status?"
```

Includes a think-act-observe loop for tool use and scientific query enrichment.

### SciRetrieval (Scientific Knowledge Retrieval)

SciRetrieval provides domain-aware scientific literature and database retrieval:

```bash
python3 -m fiona.cli sire query "What is the band gap of silicon carbide?"
```

**Providers:**
- **NCBI** — PubMed article search, E-Utilities (ESummary, EFetch, ESearch)
- **PubChem** — compound search, substance search, chemical property lookup
- **NIST** — physical constant and material property database queries

**Architecture:**
- `MainText` → Scientific Domain Identifier → Provider Selection → SciLab processing
- Temporary-by-default memory with one-link-deep SQLite exception for long-term traces
- CPU-inspired hierarchical caching for NIST datasets
- All queries routed through a DI-resolved bridge: `GetData(dataset, request)`
- 6 REST API endpoints exposed via FLoP at `/api/v1/sciretrieval/*`

### SciPhi (Scientific Computing Framework)

SciPhi is a scientific computing framework for defining models, connecting them to numerical solvers, and running simulations with uncertainty analysis and provenance tracking. It follows a strict directive workflow: **Analyze → Consult Documentation → Design Before Coding → Build Using Opsim → Validate Scientific Correctness → Test**.

```bash
python3 -m sciphi run "SIR epidemiological model with vaccination"
python3 -m sciphi explore "quantum harmonic oscillator"
```

**Architecture — OpsimKernel Pipeline:**

```
User/Agent Request → OpsimKernel → Simulation Advisor → Scientific Planner
  → Hypothesis Engine → Model Selector → Problem Compiler
  → Solver Selection Engine → Solver → Validation
  → Uncertainty Analysis → Provenance → Report
```

**Key components:**

| Component | Module | Purpose |
|-----------|--------|---------|
| **OpsimKernel** | `kernel/opsim.py` | Central orchestration — routes queries through the full pipeline |
| **Simulation Advisor** | `kernel/advisor.py` | Analyzes query intent, suggests simulation strategies |
| **Scientific Planner** | `kernel/planner.py` | Decomposes problems into step-by-step scientific plans |
| **Model Selector** | `kernel/compiler.py` | Selects and instantiates domain models |
| **Problem Compiler** | `kernel/compiler.py` | Compiles models + parameters into computational problems |
| **Hypothesis Engine** | `kernel/hypothesis.py` | Form-aware hypothesis generation with 6 evaluation strategies |
| **Solver Selector** | `kernel/solver_selector.py` | Picks optimal solver based on problem form |
| **Validation** | `kernel/evaluator.py` | Scientific correctness checks, convergence validation |
| **Uncertainty** | `kernel/uncertainty.py` | Error propagation, Monte Carlo uncertainty estimation |
| **Provenance** | `kernel/provenance.py` | Complete audit trail — every simulation step recorded |
| **Report** | `kernel/report.py` | Structured investigation reports |

**Domain Models** (12+ built-in):

| Domain | Models |
|--------|--------|
| **Physics** | Kinematics, Dynamics, Thermodynamics, Electromagnetism, Quantum |
| **Chemistry** | Equilibrium, Reaction kinetics, Stoichiometry |
| **Biology** | Epidemiology (SIR/SEIR), Population dynamics |
| **Earth Science** | Climate modeling |
| **Engineering** | Circuits, Structural mechanics |

**Solvers** (4 categories, 7 implementations):

| Category | Solvers |
|----------|---------|
| **Deterministic** | ODE solver (RK4, Euler), Algebraic solver |
| **Stochastic** | Monte Carlo simulation |
| **Optimization** | Gradient descent, simulated annealing |
| **Symbolic** | Analytical solution derivation (via sympy) |

**Design principles:**
- **Models** describe the science, never the computation
- **Solvers** describe the computation, never the science
- **OpsimKernel** bridges both, remaining domain-agnostic
- stdlib-first: numpy core, scipy/sympy/matplotlib optional
- Every simulation goes through the Problem Compiler → Solver Selection Engine → Solver pipeline, never directly
- Provenance by construction — every transformation recorded automatically

**Test coverage:** 394+ tests (72 hypothesis tests, form-aware generation, 6 evaluation strategies, ranking methods)

## Running Tests

```bash
python -m pytest tests/ -v
# 1450+ tests across all subsystems (394 in SciPhi, 49 in test_cmdtrace_recallvault.py)
python -m compileall Agent CamComs DataClient EyeControl FionaCore PhiConnect \
  QuikTieper SciPhi SciRetrieval SeeOnDesk TerminalAssist Voice Vsee fiona
```

## Current State

**Working today:**

- FLoP web frontend with 24 server-rendered pages, AJAX interactions, real-time polling
- Installable Fiona umbrella CLI with 40+ commands
- Shared Tkinter GUI editor with 7 tabs
- Standalone Vsee, PhiConnect, DataClient GUIs
- SeeOnDesk desktop-awareness with process tracking and workspace awareness
- EyeControl optional camera tracker
- fAT terminal dashboard and Zellij layout helper
- QuikTieper binding editor/listener/action runner
- CamComs encryption/decryption/transport/receiver/pairing/key rotation
- Trusted sender lifecycle with expiry and audit logging
- Host service config/status/run with GUI systemd controls
- ACL sender-scoped permission system, shell safety, extended macro engine
- Voice wake-word detection, push-to-talk, feedback engine
- Ollama local inference bridge with planning loop
- Encrypted computer-to-computer chat (PhiConnect)
- Scientific knowledge retrieval (NCBI/PubChem/NIST) with caching
- SciPhi scientific computing framework — OpsimKernel pipeline, 12+ domain models, 7 solvers, hypothesis engine, uncertainty analysis, provenance
- CmdTrace action audit log with statistics, advanced search, export (JSON/CSV), auto-compaction, and live tail
- RecallVault key-value store with TTL expiry, tags, import/export (JSON/CSV), timestamped backup, statistics dashboard, and TF-IDF semantic search
- Python test suite (1450+ tests)

**Still in progress:**

- Full AI agent planner/tool loop (partial: think-act-observe exists)
- Screen-recording/ML classifier for SeeOnDesk
- ESP32 firmware hardware verification
- Encrypted replies from host back to trusted devices
- Release packaging and per-platform dependency guidance
