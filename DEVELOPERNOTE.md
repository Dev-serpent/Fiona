## Fiona Developer Notes

This file records the current Fiona project structure, runtime setup, and latest verification results.

## Project Structure

Fiona is the umbrella project. It exposes the following subsystems:

- `QuikTieper`: the local access layer for keyboard, mouse, app launch, clicks, and shortcuts
- `CamComs`: the communication layer for encoded/encrypted host communication
- `Vsee`: the 3D coordinate hologram viewer
- `Agent`: the local LM Studio bridge, orchestration engine, and command registry
- `PhiConnect`: the standalone encrypted computer-to-computer chat app
- `SeeOnDesk`: the desktop-awareness layer for active app/window identification
- `DataClient`: the standalone research/data collection app
- `EyeControl`: optional camera-based eye-controlled mouse tracker
- `TerminalAssist`: Fiona Terminal Assistance (`fAT`) terminal dashboard and Zellij workspace helper
- `BrowserAutomation`: Selenium-based browser automation with state machine management
- `FionaCore`: shared modules (approval system, action router, macros, permissions, ACL, DI)
- `cad`: CAD platform — parametric 3D modeling core + JSON-RPC 2.0 server + 3js frontend
- `fionaLocalPages`: Web dashboard SPA — aiohttp REST API backend (24 handler modules, 115+ endpoints) + 27 HTML/JS frontend pages served as a browser-based control surface alongside the CLI and Tkinter GUI

Current file structure:

```text
Fiona/
├── fiona/                  umbrella package and CLI entrypoint
├── FionaCore/              shared modules (approval, actions, macros, permissions, ACL, DI)
│   ├── approval.py         Human-in-the-loop plan approval system
│   ├── actions.py          ActionSpec router with ACL and permissions
│   ├── macros.py           Macro engine v2 with waits, conditions, branching
│   ├── permissions.py      Permission profiles
│   ├── acl.py              Sender ACL rules
│   ├── verification.py     Verification prompt system
│   ├── shell_safety.py     Destructive command regex safety wrapper
│   └── di.py               Dependency injection container
├── cad/                    CAD platform
│   ├── core/               Document, Object, Property system
│   ├── geometry/            Primitives, math, transforms, modifiers
│   ├── constraints/         Constraint types and solver
│   ├── sketch/              2D sketch workspace
│   ├── part/                Part features (Pad, Pocket, Revolve, etc.)
│   ├── assembly/            Assembly hierarchy and constraints
│   ├── commands/            Command registry and built-in commands
│   ├── scripting/           Python scripting console
│   ├── rendering/           Viewport, camera, projection
│   ├── plugins/             Plugin manager
│   ├── io/                  STL, OBJ, SVG exporters
│   ├── server/              JSON-RPC 2.0 WebSocket server + 3js frontend
│   │   ├── _server.py           CadServer (HTTP + WebSocket, stdlib-only)
│   │   ├── _handlers.py         RPC method dispatch (document, command, export, approval)
│   │   ├── _protocol.py         JSON-RPC 2.0 codec, error codes, ServerEvent
│   │   ├── _document_manager.py Document lifecycle with EventBus publishing
│   │   ├── _command_executor.py Snapshot-based undo/redo with change classification
│   │   ├── _export_manager.py   STL/OBJ/SVG export provider registry
│   │   ├── _websocket_handler.py RFC 6455 WebSocket (stdlib-only)
│   │   ├── _app_builder.py      DI container wiring
│   │   └── _frontend/           3js frontend (Vite + Three.js)
│   │       ├── src/
│   │       │   ├── main.js          Entry point, WebSocket lifecycle, event handlers
│   │       │   ├── client.js        RpcClient (JSON-RPC 2.0 over WebSocket)
│   │       │   ├── store.js         CadStore (central state)
│   │       │   ├── scene/           SceneManager, CameraSync, meshes
│   │       │   ├── panels/          Toolbar, ProjectTree, PropertyEditor, ConsolePanel,
│   │       │   │                    StatusBar, AgentConsole
│   │       │   └── styles/main.css  Dark theme stylesheet
│   │       └── dist/               Production build output
│   └── tests/                (removed — old 446 fixture tests deleted 2026-06-22)
├── BrowserAutomation/       Selenium-based browser automation
│   ├── _manager.py          BrowserManager with state machine (STOPPED/ERROR→STARTING→RUNNING)
│   ├── _selenium_provider.py Selenium WebDriver provider (Chrome binary resolution, headless)
│   ├── _session_manager.py  Thread-safe sync wrapper around async browser API
│   ├── _config.py           BrowserConfig dataclass (headless, viewport, proxy, data_dir)
│   ├── _errors.py           Error hierarchy
│   └── __init__.py          Convenience wrappers, get_browser_manager() (module-level singleton)
├── QuikTieper/             local access layer implementation
├── CamComs/                communication/encryption layer implementation
│   └── esp32payload/       ESP32 sender payload template
├── Vsee/                   3D point/edge hologram viewer model
├── Agent/                  local LM Studio bridge, orchestrator, command registry
├── PhiConnect/             encrypted computer-to-computer chat app
├── SeeOnDesk/              desktop awareness and active-window identification
├── DataClient/             research/data collection app
├── EyeControl/             optional eye-controlled mouse tracker integration
├── TerminalAssist/         fAT terminal dashboard and Zellij layout generation
├── Voice/                  Wake word, push-to-talk, feedback engine
├── tests/                  Python tests
│   ├── browser/            BrowserAutomation tests (50)
│   ├── cad_server/         CAD server tests (140)
│   ├── contracts/          Interface contract tests (140)
│   └── ...                 Existing test suite
├── fionaLocalPages/        Web dashboard SPA (aiohttp + HTML + vanilla JS)
│   ├── server/app.py       API server (aiohttp, 10+ handler modules, 40+ endpoints)
│   ├── server/handlers/    REST handler modules (agents_crud, browser, terminal, quiktieper, settings, etc.)
│   ├── js/                 Frontend JS (app.js, router.js, api.js, state.js, template-loader.js, components/)
│   ├── css/                Stylesheets (globals, components, layout, themes, animations)
│   ├── pages/              26 page modules (SPA pages, one per route)
│   ├── templates/          26 HTML template files (loaded via template-loader.js)
│   └── index.html          SPA shell with static sidebar HTML
├── scripts/                local launch wrappers
├── fionaDocsPage/          Documentation site
├── .backups/               timestamped backup snapshots
├── fiona.egg-info/         editable-install metadata
├── README.md
├── DEVELOPERNOTE.md
├── ARCHITECTURE_REVIEW.md  Architecture specification with ADRs
├── pyproject.toml
├── devlog.md
├── dependencies.md
├── logo.svg
└── .gitignore
```

Current direction for communication:

- ESP32 is the sender.
- The host running Fiona is the receiver.
- ESP32 sends encoded encrypted envelopes to a host IP endpoint.
- The host decodes and decrypts using its CamComs private identity.

Important directories:

```text
fiona/                 umbrella package and CLI entrypoint
QuikTieper/            access layer implementation
CamComs/               communication/encryption layer implementation
CamComs/esp32payload/  ESP32 sender payload template
Vsee/                  3D coordinate hologram viewer implementation
Agent/                 local LM Studio bridge
PhiConnect/            encrypted computer-to-computer chat implementation
SeeOnDesk/             desktop awareness and active-window identification
DataClient/            research/data collection implementation
EyeControl/            optional camera-based eye-controlled mouse tracker
TerminalAssist/        Fiona Terminal Assistance terminal UI helpers
tests/                 Python verification tests
```

Make sure to put this in bashrc for convinience and run the aliased cmd from the project root:

```bash 
alias fiona='python3 -m fiona.cli'
```

however this 'fiona' cmd described through the projects is not created yet: So replace fiona with python3 -m fiona.cli

The umbrella CLI supports both layers:

```bash
fiona edit
fiona run
fiona list
fiona import-apps --dry-run
fiona import-apps
fiona normalize-app-cmds --dry-run
fiona normalize-app-cmds
fiona assign-keys --dry-run
fiona assign-keys
fiona quiktieper edit
fiona quiktieper run
fiona quiktieper list
fiona camcoms smoke-test
fiona camcoms keygen
fiona camcoms paths
fiona camcoms encrypt
fiona camcoms decrypt
fiona camcoms send
fiona camcoms trust
fiona camcoms trust --list
fiona camcoms trust --remove esp32
fiona camcoms audit
fiona camcoms receive
fiona camcoms service init
fiona camcoms service status
fiona camcoms service run
fiona host init
fiona host status
fiona host run
fiona phiconnect
fiona seeondesk active
fiona seeondesk status
fiona dataclient
fiona dataclient mine "topic" --out ./research.csv
fiona dataclient deep "topic" --out ./deep.csv --depth 1 --page-limit 50
fiona eyecontrol status
fiona eyecontrol run --camera-index 0 --no-click
fiona cli
fiona cli --preview
fiona fat status
fiona fat tui
fiona fat layout --print
fiona fat run
fiona ficad                          # Start CAD server + 3js frontend
fiona ficad --headless               # Headless CAD CLI mode
fiona ficad --doc my_doc.cad         # Load document on startup
fiona ficad --port 8765              # Custom port (default 8765)
fiona ficad --no-browser             # Don't auto-open browser tab
fiona browser start                  # Start browser automation engine
fiona browser stop                   # Stop browser automation engine
fiona browser status                 # Show browser status
fiona browser navigate <url>         # Navigate browser to URL
fiona browser click <selector>       # Click element by CSS selector
fiona browser type <sel> <text>      # Type text into element
fiona browser screenshot             # Capture screenshot
fiona approval pending               # List plans awaiting human approval
fiona approval list                  # List all plan history
fiona approval approve <plan_id>     # Approve a pending plan
fiona approval deny <plan_id>        # Deny a pending plan
```

## Missing Issues

These are known project gaps that still need implementation. Manual GUI/workflow roughness is intentionally not listed here.

- The ESP32 payload now has a real firmware crypto adapter implementation using `mbedtls` and `libsodium`.
- Implemented X25519 key agreement, HKDF-SHA256 key derivation, AES-GCM encryption, and Ed25519 signing.
- Added NTP synchronization to the ESP32 payload to ensure valid Unix timestamps for the host's `ReplayGuard`.
- Refined WiFi reconnection behavior and added basic retry logic for message delivery.
- Fixed JSON canonicalization in the ESP32 template to match Python's `sort_keys=True` (putting `ciphertext` at the start of the signed JSON).
- Verified compatibility with Python's `cryptography` library primitives.
- Added support for both 32-byte seed and 64-byte full secret key formats for Ed25519 provisioning.
- ESP32 payload now requires `libsodium` (built-in to ESP32 core), `mbedtls` (built-in), and `ArduinoJson` 6.x/7.x.
- On 2026-06-03, hardware-ready crypto logic was refined in `CamComs/esp32payload/esp32payload.ino`.
- **Verified via Simulation**: Created `tests/test_esp32_firmware_sim.py` which mocks the exact C++ implementation of canonicalization and encoding to ensure 100% compatibility with the host's `CamComs` module.
- The ESP32 path still needs hardware validation and a robust pairing/provisioning UI.
- On 2026-06-20, the **CAD platform** (`cad/`) was added to `main` from the `windows-ide` branch. It is a FreeCAD-inspired parametric 3D modeling system with:
  - Geometry primitives (Box, Cylinder, Cone, Sphere, Torus, Line, Circle, Arc, etc.)
  - 2D Sketch workspace with entities, constraints, and constraint solver
  - Part features (Pad, Pocket, Revolve, Loft, Sweep, Fillet, Chamfer, Shell)
  - Assembly hierarchy with parts, subassemblies, and assembly constraints
  - Command system with registry, aliases, and built-in commands
  - Python scripting console for interactive CAD automation
  - Plugin manager for extensibility
  - 3D viewport with Camera, projection, and render backend abstraction
  - STL/OBJ/SVG export
  - 6 production bugs fixed (init ordering, console doc reference, sketch add_point, sphere STL indexing, SVG viewBox formatting)
  - **446 tests, all passing** (up from 38)
  - New CLI command: `fiona ficad` with `--headless`, `--doc`, and GUI launch modes
- Voice, speech output, desktop tray/background status, and rich desktop notifications are still not implemented.
- SeeOnDesk does not yet have screen recording or an ML classifier; the current implementation uses desktop/window metadata.

Recently fixed:

- CamComs host service skeleton exists through `fiona camcoms service init/status/run`.
- Fiona now also exposes the host service directly through `fiona host init/status/run`.
- CamComs host receiver/server exists through `fiona camcoms receive`.
- Decrypted CamComs messages route into an allowlisted QuikTieper remote-action runner.
- Host service config now controls receiver host/port, replay path, audit path, trusted directory, listener startup, dry-run execution, and allowed remote actions.
- Host service status now reports system/session info, QuikTieper app/binding summary, import checks, command checks, key/trust paths, audit path, replay path, and receiver port availability when requested.
- Host service can optionally own the QuikTieper listener and CamComs receiver in one process.
- QuikTieper can now discover installed Linux desktop applications from `.desktop` files and import them into the config with unassigned launch keys.
- QuikTieper app import now filters games, education apps, settings panels, helper launchers, demos, uninstallers, and most `K...` apps by default while keeping a practical allowlist such as Konsole, Kate, KWrite, KCalc, KDE Connect, KDE System Settings, Kdenlive, KDevelop, KMail, KOrganizer, KRDC, and KSystemLog.
- On 2026-05-19, filtered app import wrote 244 new launch entries to `~/.config/fiona/bindings.json`; imported entries are visible in the GUI and remain unassigned until launch keys are set.
- On 2026-05-19, generated launch keys were assigned for the 244 imported app entries. The assignment preserves the original default app chords, uses `alt` plus three distinct safer letters for generated launch chords, and checks uniqueness by pressed-key set.
- On 2026-05-19, `normalize-app-cmds` was added and applied. Fiona now has 251 app launch entries, no unassigned launch keys, and no duplicate launch key sets. The command preset pass normalizes common apps such as Brave, VS Code, Terminal, Files, KDE tools, Jupyter, media apps, and system utilities while preserving installed full-path/AppImage fallbacks when needed.
- Trusted sender public keys are stored under `~/.config/fiona/camcoms/trusted`.
- Trusted sender lifecycle now includes list/add/remove helpers and CLI access.
- CamComs audit logging records accepted/rejected host message processing and can be read through `fiona camcoms audit`.
- Replay protection rejects duplicate or stale `message_id` / `created_at` envelopes.
- Remote instruction payloads use strict JSON.
- Remote instruction payloads now support a structured `macro` instruction with nested validated steps.
- Private key files support optional passphrase encryption.
- The GUI now includes a Host tab for config init/status, trusted device inspection/removal, audit log viewing, and host path visibility.
- The GUI now includes a Debug tab that can view/edit project text files, restricted to `tests`, `scripts`, `QuikTieper`, and `CamComs`.
- The project now includes `Vsee`, a separate sibling package for point/edge 3D hologram viewing.
- The GUI now includes a Vsee tab with editable point and edge tables, a dark grid canvas, and rotation/scale controls for rendering connected 3D wireframe shapes.
- The project now includes `Agent`, a local Ollama bridge for chat-completion inference.
- Fiona now exposes `fiona agent status` and `fiona agent ask` for Ollama integration.
- Fiona now exposes `fiona vsee` for a separate `Vsee Holography` window outside the main `fiona edit` GUI.
- The project now includes `PhiConnect`, a standalone encrypted computer-to-computer chat app outside `fiona edit`.
- PhiConnect creates local chat identities, stores a peer public key for outbound encryption, trusts peer public keys for inbound verification, encrypts outbound chat with CamComs, decrypts inbound chat, and shows a rolling 3-minute chat window.
- PhiConnect defaults to port `5000` for local communication. The GUI can now set listen host/port, set a peer public key, and use the local public key for Fiona loopback testing on `127.0.0.1:5000`.
- The project now includes `SeeOnDesk`, a sibling package for desktop-awareness snapshots.
- Fiona now exposes `fiona seeondesk active` and `fiona seeondesk status`.
- SeeOnDesk currently identifies the active app/window through `kdotool` on KDE/Wayland and `xdotool`/`xprop` fallback paths when available.
- The project now includes `DataClient`, a standalone research app outside `fiona edit`.
- Fiona now exposes `fiona dataclient` for the GUI, `fiona dataclient mine` for quick topic mining, `fiona dataclient deep` for bounded deep research, `fiona dataclient convert` for CSV/JSON/SQLite conversion, and `fiona dataclient view` for terminal previews.
- DataClient exports research CSV files with topic, URL, title, summary, depth, and parent URL fields.
- DataClient now includes MiniExcel, a lightweight CSV/JSON/SQLite viewer/editor with selected-cell editing, row/column creation, row deletion, save/export support, and a safe formula bar for cell references/ranges and common functions.
- DataClient GUI now has a Miner menu for quick mining, deep research, and clearing the miner log.
- The project now includes `RecallVault`, a persistent remembrance store for key-value snippets and categories.
- Fiona now exposes `fiona recall remember/search/forget/clear/categories` for memory management.
- The project now includes `CmdTrace`, a high-performance JSONL-based observability log for all routed actions.
- Fiona now exposes `fiona action history` and `fiona action clear` for auditing system activity.
- `fiona action history` supports filtering by specific action name with `--name`.
- The imported tracker now lives at `EyeControl/Eye_Controlled_Mouse_Tracker.py` and is wrapped as the optional `EyeControl` package.
- Fiona now exposes `fiona eyecontrol status` and `fiona eyecontrol run`.
- EyeControl imports OpenCV, MediaPipe, PyAutoGUI, and camera resources only at runtime, so normal Fiona imports and tests do not require a camera.
- The project now includes `TerminalAssist`, a high-fidelity terminal dashboard and sliding command center exposed through `fiona fat`.
- fAT Dashboard now includes comprehensive system metrics: **Hostname**, **Kernel**, **CPU (Model/Usage/Temp/Speed)**, **Memory/Swap**, **Disk (Usage/IO)**, **Network (IP/Traffic/Signal)**, **GPU**, **Power (Battery/AC)**, and **Security (Firewall/Updates)**.
- fAT TUI was upgraded to a **fullscreen-style layout** with a guaranteed 1-second non-blocking auto-refresh engine.
- fAT TUI now includes **Quick Actions** for session control (Lock/Logout/Suspend) with automatic Desktop Environment detection (KDE/GNOME/XFCE).
- Fiona now exposes a **system status JSON API** through the top-level `fiona api` shortcut.
- Fiona now exposes `fiona fat`, `fiona fat status`, `fiona fat api`, `fiona fat layout`, and `fiona fat run`.
- Fiona now exposes `fiona cli`, a sliding curses-based command center for common Fiona workflows.
- `fiona fat tui` opens the same command center through the fAT namespace.
- The fAT command center now captures one-shot command output inside an in-app output panel. Interactive or long-running actions are marked external and still run through the real terminal/session.
- Fiona now exposes `fiona host install-service` to print or write a user systemd service file for startup/background operation.
- Launcher scripts point at `/home/Dhruv/Documents/Projects/Fiona`.
- README matches the current Fiona / QuikTieper / CamComs structure.
- GUI handler coverage exists for the CamComs smoke-test handler without requiring a display.

## Missing From Jarvis Except The AI Agent

recorded on 2026-05-19. Fiona already has a local action layer (`QuikTieper`), encrypted communication layer (`CamComs`), GUI, host-service skeleton, audit log, trusted-device storage, debug editor, basic `Vsee` wireframe hologram viewer, separate Vsee Holography window, standalone PhiConnect encrypted chat, a desktop-awareness layer (`SeeOnDesk`), a standalone research app (`DataClient`), and a local Ollama inference bridge (`Agent`).
 Ignoring the AI agent itself, these are the remaining systems needed for it to feel like a Jarvis-style host:

1. Real always-on service lifecycle: `fiona host install-service` can generate the user systemd unit, but Fiona still needs service enable/disable/status wrappers, clean shutdown, restart policy tuning, and GUI status integration.
2. Real ESP32 device link: the ESP32 payload now has refined firmware crypto, NTP sync, and reconnection logic. It still needs a provisioning UI, host discovery, and hardware testing on more chip variants.
3. Secure pairing flow: Fiona needs first-time pairing, fingerprint display/approval, trusted key installation, host public key provisioning, key rotation, and device removal UX.
4. Stronger command router: current routing is basic allowlisted JSON actions. It still needs sender-specific permissions, richer action categories, named command registry, better result objects, and safety prompts for risky actions.
5. Deeper system awareness: SeeOnDesk now provides a first active-window/app snapshot. Fiona still needs process registry, workspace/session state, available-action discovery, device state, richer command history search, and screen/visual recognition.
6. Voice and input surface: no wake word, push-to-talk, speech-to-text, typed command console, or confirmation flow exists yet.
7. Feedback layer: Fiona needs spoken responses, desktop notifications, visible status overlay/tray indicators, clear local failure states, and encrypted replies back to ESP32 or other devices.
8. Desktop tray/background control: no tray icon, quick open, pause/resume, service status indicator, or quit control exists yet.
9. GUI control center expansion: Host tab exists, but it still needs live receiver start/stop, listener start/stop, connected-device state, last-message view, test command buttons, pairing UI, and service logs.
10. Automation/macro expansion: basic nested macros exist, but waits, conditions, window targeting, named reusable macros, branching, and per-step failure handling are not implemented.
11. Security hardening: passphrase keys, trust store, replay protection, and audit log exist, but file permission checks, replay cleanup policy, key rotation, secure pairing, and threat-oriented validation still need work.
12. Vsee/holography expansion: Vsee is currently a point/edge wireframe viewer. It still needs saved scenes, import/export, richer primitives, camera controls, animation, live data binding, and any real hologram/projection output path.
13. Packaging and public install polish: README is public-facing, but Fiona still needs stable package discovery, tested console-script install, dependency install guidance per platform, and release packaging.
14. Cross-platform/runtime reliability: the current control stack is Linux/KDE/Wayland-oriented. Fiona still needs clearer platform support boundaries, graceful degradation, and dependency checks for missing tools like `ydotool`, `kdotool`, and `pynput`.
15. Agent training/fine-tuning system: Ollama integration is local inference only. Fiona still needs dataset capture, training/fine-tuning scripts, GPU/runtime selection, resource limits, evaluation, and rollback before any real model training should be attempted.

## Build Order

Most basic to most advanced:

1. Done: unified Fiona config at `~/.config/fiona/config.json` for QuikTieper path, CamComs key paths, trusted directory, receiver host/port, dry-run mode, allowed actions, replay path, and audit log.
2. Done: host service skeleton through `fiona host init/status/run`.
3. Done: service health checks verify config, key files, trusted dir, `ydotool`, `kdotool`, listener import, audit/replay dirs, and receiver port binding when requested.
4. Done: CamComs receiver integration is owned by `HostService.run`.
5. Done: QuikTieper listener can be owned by the host service through `start_quiktieper_listener`.
6. Done: remote action router connects decrypted CamComs instructions to configured QuikTieper actions with `execute_remote_actions` and `allowed_remote_actions`.
7. Done: standalone encrypted computer-to-computer chat exists through PhiConnect.
8. Partial: GUI Host tab shows config, health status, trusted keys, logs, and paths; live receiver process controls still need expansion.
9. Done: command history / audit log records accepted/rejected host message processing and is visible through CLI/GUI.
10. Done: trusted device manager can list, add, remove, and inspect stored sender public key JSON.
11. Partial: configurable macro layer supports structured multi-step remote actions; waits, conditions, window targeting, named macros, and per-step failure handling remain.
12. Partial: local structured success/failure result objects exist; response messages to sender and local notifications still remain.
13. Not started: desktop tray / background status.
14. Done: refined crypto adapter for X25519, HKDF-SHA256, AES-GCM, Ed25519, and NTP sync in firmware.
15. Not started: ESP32 pairing flow.
16. Not started: voice / speech interface.
17. Partial: desktop awareness through SeeOnDesk active-window snapshots; screen recording and ML recognition remain.

## Setup

The project is currently expected to run from the `quiktieper` Conda environment.

```bash
source ~/Applications/miniconda3/etc/profile.d/conda.sh
conda activate quiktieper
cd /home/Dhruv/Documents/Projects/Fiona
```

Install the project in editable mode after dependency changes:

```bash
pip install -e .
```

Required Python packages:

- `python` 3.11+
- `pynput`
- `cryptography`
- `numpy`
- `pandas`
- `requests`
- `wayland-automation` for optional Wayland pointer automation fallback

Required system tools for the launcher:

- `bash`
- `kdotool`
- `ydotool`
- `ydotoold`
- `tk` / `tkinter`
- optional fallback tools: `xprop`, `xdotool`

## Part 1: QuikTieper Launcher

QuikTieper is Fiona's keyboard control layer. It listens for global simultaneous key chords and launches apps or app-specific shortcuts.

Create the default config:

```bash
python3 -m fiona.cli init
```

List configured bindings:

```bash
python3 -m fiona.cli list
```

Start the global listener:

```bash
python3 -m fiona.cli run
```

Open the GUI editor:

```bash
python3 -m fiona.cli edit
```

Equivalent umbrella CLI commands:

```bash
fiona edit
fiona quiktieper edit
```

Preferred launcher wrappers:

```bash
./scripts/fiona-edit
./scripts/fiona-run
```

These wrappers:

- activate the `quiktieper` Conda environment
- request privilege up front for `ydotoold` with `pkexec` if needed
- start Fiona normally as the desktop user

The default config path is:

```text
~/.config/fiona/bindings.json
```

Example app commands used in the default config:

- `brave`
- `code`
- `konsole`
- `dolphin`

Runtime assumptions:

- Current target desktop is KDE Plasma on Wayland.
- App-specific shortcut routing prefers `kdotool`.
- Mouse movement and click actions prefer `ydotool`.
- `xprop` and `xdotool` are fallback / legacy paths.

## SeeOnDesk Desktop Awareness

SeeOnDesk is Fiona's current desktop-awareness subsystem. It does not do screen recording or ML recognition yet; it identifies the focused app/window through desktop metadata.

Current commands:

```bash
fiona seeondesk active
fiona seeondesk status
```

Current implementation:

- prefers `kdotool` for KDE/Wayland focused-window detection
- falls back to `xdotool` and `xprop` on X11-compatible sessions
- returns active window id, app class, inferred app name, title, process id, process name, session type, and desktop name when available
- fails closed with `backend: unavailable` when run from a sandbox/service without desktop session access

## Part 2: CamComs Communication

CamComs is Fiona's communications layer. The current implemented parts are:

- `CamComs/encryption.py`: public/private encryption and signing
- `CamComs/codec.py`: base64url JSON envelope encoding/decoding
- `CamComs/transport.py`: HTTP POST client for encoded messages
- `CamComs/esp32payload/`: ESP32 sender payload template

The current model is ESP32 sender to host receiver.

Run the CamComs tests:

```bash
python3 -m unittest tests.test_camcoms_encryption tests.test_camcoms_transport
```

Minimal ESP32-to-host smoke test:

```bash
fiona camcoms smoke-test
```

Expected output:

```text
{"keys":["alt","s"],"type":"press","version":1}
```

What the CamComs encrypter currently provides:

- `CamComsIdentity.generate()` creates a device identity.
- Each identity has an X25519 encryption keypair.
- Each identity has an Ed25519 signing keypair.
- `identity.public_bundle` is safe to share with another device.
- `encrypt_message(...)` encrypts a payload to the recipient public key.
- `decrypt_message(...)` decrypts using the recipient private key.
- `decrypt_text(...)` is a UTF-8 text helper around `decrypt_message(...)`.
- Sender signatures are verified during decrypt when `expected_sender` is provided.
- Tampered messages and wrong-recipient messages raise `CamComsCryptoError`.
- Remote instruction payloads use strict JSON objects, for example `{"keys":["alt","s"],"type":"press","version":1}`.

The encrypted envelope uses:

- X25519 for public/private key agreement
- HKDF-SHA256 for message key derivation
- AES-GCM for authenticated encryption
- Ed25519 for sender signatures

### ESP32 Payload

ESP32 payload files:

```text
CamComs/esp32payload/README.md
CamComs/esp32payload/esp32payload.ino
```

Host receiver identity:

```bash
fiona camcoms keygen --device-id host
```

ESP32 sender identity for provisioning:

```bash
fiona camcoms keygen --device-id esp32
```

The ESP32 payload needs:

- host device id
- host encryption public key
- ESP32 device id
- ESP32 signing private key

The ESP32 static encryption private key is not needed for the current one-way sender-to-host direction. It becomes relevant once the host also encrypts replies back to the ESP32.

Default visible key paths:

```text
~/.config/fiona/camcoms/host.private.json
~/.config/fiona/camcoms/host.public.json
~/.config/fiona/camcoms/esp32.private.json
~/.config/fiona/camcoms/esp32.public.json
```

## Validation Commands

Run the launcher CLI check:

```bash
fiona list
```

Run all current tests:

```bash
python -m unittest discover -s tests -v
```

Latest result, run on 2026-06-25:

```text
Tests run via python -m pytest tests/ -v:
  Passed: 1413+ (pytest, includes CLI surface suite)
  Pre-existing env failures: ~14 (numpy.rec, no camera, no network)

BrowserAutomation:
  24 tests pass (state machine, graceful start, ERROR recovery)
  28 tests skipped (old Playwright provider tests, preserved as dead code)

CAD server + contracts:
  98 + 140 = 238 tests pass

CAD frontend (vitest):
  87 tests pass

CLI command surface (new):
  2 tests, 54 subtests — all CLI --help output clean, 22 smoke commands pass

Compile check:
  python -m compileall passes for all packages
```

Test suites can be run independently:

```bash
# Run all tests (pytest)
python -m pytest

# CAD server + contract tests
python -m pytest tests/cad_server/ tests/contracts/

# Browser automation tests
python -m pytest tests/browser/

# Agent tests (orchestrator excluded due to pre-existing plan-approval changes)
python -m pytest tests/test_agent_personalities.py tests/test_agent_backward_compat.py
```

Note: The old `cad/tests/` (446 fixture tests) were removed on 2026-06-22.
All existing tests use `pytest`. Legacy `unittest`-style tests are in `tests/` and run via `pytest`.

Direct host-service CLI smoke checks, run on 2026-05-05:

```bash
python -m fiona.cli host init --config /tmp/fiona-host-test.json --force
python -m fiona.cli host status --config /tmp/fiona-host-test.json
python -m fiona.cli camcoms audit --path /tmp/fiona-audit-missing.log --limit 5
python -m fiona.cli camcoms trust --list --trusted-dir /tmp/fiona-trusted-missing
```

Latest direct CLI result:

```text
host init wrote /tmp/fiona-host-test.json
host status returned config, checks, system summary, and QuikTieper app/binding summary
camcoms audit returned an empty event list for a missing audit log
camcoms trust --list returned an empty sender list for a missing trusted directory
```

Run the CamComs ESP32-to-host smoke test:

```bash
fiona camcoms smoke-test
```

Latest output:

```text
{"keys":["alt","s"],"type":"press","version":1}
```

Compile the main packages:

```bash
python -m compileall Agent CamComs DataClient EyeControl PhiConnect QuikTieper SeeOnDesk TerminalAssist Vsee fiona
```

Latest result, run on 2026-05-26:

```text
Compiled without syntax errors.
```

## fionaLocalPages — Web Dashboard

The `fionaLocalPages/` directory is a self-contained web dashboard SPA served from an aiohttp backend.

### Start the server

```bash
./scripts/fiona-pages-start              # default port 8765
./scripts/fiona-pages-start --port 8080  # custom port
./scripts/fiona-pages-start --debug      # verbose logging
```

### Architecture

**Python backend** (aiohttp) → **HTML templates** (`.html` files in `templates/`) → **JS modules** (thin SPA layer)

- **Backend**: `server/app.py` — aiohttp server with 24 handler modules, 115+ REST endpoints at `/api/v1/`, WebSocket at `/ws`, SSE at `/api/v1/stream`
- **Frontend**: 27 page modules in `pages/`, each with `render()` + `mount()` + `destroy()`. Templates loaded at runtime via `js/template-loader.js` using `{{variable}}` interpolation.
- **Router**: Hash-based SPA router (`js/router.js`) with lazy-loaded pages, lifecycle hooks, active nav tracking, object-export fix for blank-page bug
- **State**: Observable store (`js/state.js`) with localStorage persistence
- **Styling**: Dark-first glassmorphism design system — 5 CSS files (globals, components, layout, themes, animations)
- **Terminal**: All terminal logic is in the Python backend. `cwd` is tracked server-side in a module-level `_cwd` variable (`handlers/terminal.py`). Every `subprocess.run()` call passes `cwd=_cwd`. The JS client is a thin input/output relay — it reads `cwd` from `data.cwd` in each response. New `GET /api/v1/terminal/cwd` endpoint for initial directory on mount.

### Backend Handler Modules (24 handler modules, 115+ routes)

| Module | Endpoints |
|---|---|
| `handlers/agents_crud.py` | 7 (list/create/pause/resume/stop/restart agents + model check) |
| `handlers/browser.py` | 7+ (start/stop/status/navigate/click/type/screenshot) |
| `handlers/terminal.py` | 4 (execute + autocomplete GET/POST + cwd) |
| `handlers/quiktieper.py` | 8 (status/presets/desktop-apps/import-apps/assign-keys/launcher) |
| `handlers/settings_handler.py` | 2 (GET/PUT settings.txt) |
| `handlers/bindings.py` | 3 (get/save bindings, list apps) |
| `handlers/notifications_handler.py` | 3 (list/create/dismiss) |
| `handlers/phiconnect.py` | 5 (status/identity/messages/send/trust) |
| `handlers/actions.py` | 3 (list/get/run actions) |
| `handlers/agent.py` | 5 (sessions CRUD + message streaming) |
| `handlers/system.py` | 2 (health/capabilities) |
| `handlers/voice.py` | 2 (status/command) |
| `handlers/files.py` | 3 (list/read/write) |
| `handlers/config.py` | 2 (get/update config) |
| `handlers/desktop.py` | 1 (desktop status) |
| `handlers/recall.py` | 4 (search/remember/forget/categories) |
| `handlers/macros.py` | 5 (CRUD + run) |
| `handlers/camcoms.py` | 4 (status/encrypt/decrypt/send) |
| `handlers/tasks.py` | 1 (list tasks) |
| `handlers/plugins.py` | 1 (list plugins) |
| `handlers/tools_handler.py` | 2 (list/execute tools) |
| `handlers/sciretrieval.py` | 1 (scientific search) |
| **27 routes** in the SPA (`js/app.js`) — every page handles loading, error, empty, and data states. |

## Debugging Files

Primary debug log:

```text
~/.config/fiona/debug.log
```

Fallback debug log:

```text
/tmp/fiona-debug.log
```

These logs may contain:

- key press / release traces
- binding match / skip reasons
- active window detection results
- pointer backend success / failure
- shell command launch events

## Agent Personalities & Orchestration System

Added 2026-06-20 as part of the agent expansion milestone.

### New Subsystems

#### Personality System (`Agent/personality.py`)
- `Personality` frozen dataclass with name, description, system_prompt, allowed_tools, model_override
- `PersonalityRegistry` thread-safe singleton with 5 built-in personalities:
  - `general`: All tools, general-purpose assistant
  - `planner`: Read-only analysis tools, strategic planning
  - `engineer`: Automation and execution tools
  - `analyst`: Research and memory tools
  - `security`: Read-only security audit tools
- `PermissionEnforcer` (`Agent/permission.py`) — runtime tool authorization gate
- `SafeActionRouter` (`Agent/permission.py`) — wraps ActionRouter with personality-based permission checks

#### SQLite Chat Persistence (`Agent/chat_store.py`)
- `ChatStore` — thread-safe SQLite-backed chat storage with WAL mode
- Schema: `sessions` + `messages` tables with indexes
- Context window builder with token-aware truncation
- JSONL import for migration from legacy formats

#### Cancellation System (`Agent/cancellation.py`)
- `CancellationToken` — threading.Event-based cooperative cancellation
- `CancelledError` — raised when operation is cancelled
- Used across all layers from GUI to LLM calls

#### Query Detector (`Agent/query_detector.py`)
- `QueryDetector` — stateless heuristic classifier (zero LLM calls)
- `QueryOrTask` enum: `QUERY` or `TASK`
- Classifies user input as conversational query vs. actionable task using regex patterns:
  - Query: greetings, chit-chat, simple questions, short messages
  - Task: action verbs (`make`, `create`, `build`…), technical references (`.py`, `api`, `database`…), very long messages
- Integrated into `ForemanChatHandler.send_message()`: when Foreman is enabled,
  queries are routed through the simple `AgentChatHandler` (single LLM call) instead
  of the full orchestration pipeline — avoids wasting tokens on planning/decomposition.
- When routing a query to the simple handler, the personality's
  `conversational_system_prompt` is used instead of the standard ReAct prompt.
  This prevents the model from outputting JSON `thought`/`action` blocks for
  simple greetings and questions — it responds naturally.
- `force_foreman=True` bypasses detection (explicit override).

#### Orchestration Engine (`Agent/orchestration.py`)
- `ComplexityAssessor` — LLM-based goal complexity classification
- `TaskPlan` — validated goal decomposition with retry logic
- `SubAgent` — personality-wrapped ReAct agent with SafeActionRouter
- `ForemanAgent` — top-level orchestrator: assess → decompose → execute → synthesize
- `ForemanConfig` — configuration dataclass (parallel default off, configurable limits)

#### PhiConnect Agent Tab (`PhiConnect/gui.py` — Agent tab)
- New "Agent" tab in PhiConnect notebook
- Personality selector dropdown (5 personalities)
- Color-coded chat display (blue user, green agent, grey system, red error, orange cancelled)
- Cancel button with full cancellation propagation
- Foreman toggle for advanced orchestration
- Foreman configuration in Settings tab

### Backward Compatibility
All existing Agent APIs remain unchanged:
- `AgentOrchestrator`, `AgentTurn`, `CommandSpec`, `OllamaClient`, `command_registry()`, `run_agent_goal()`
- PhiConnect Chat and Settings tabs are untouched

### New Dependencies
None. All new code uses Python 3.11+ stdlib only.

### Test Coverage
- `tests/test_agent_personalities.py` — 59 tests
- `tests/test_agent_chat_store.py` — 54 tests
- `tests/test_agent_chat_handler.py` — 36 tests
- `tests/test_agent_orchestration.py` — 66 tests
- `tests/test_agent_foreman_handler.py` — 59 tests
- `tests/test_agent_stress.py` — 28 tests
- `tests/test_agent_backward_compat.py` — 12 tests
- `tests/test_agent_query_detector.py` — 53 tests

Total new tests: ~367

## BrowserAutomation System

Added 2026-06-22. Rewritten 2026-06-30: **Playwright replaced with Selenium** for browser automation.

### Components

- `BrowserAutomation/_manager.py` — `BrowserManager` with state machine: `STOPPED/ERROR → STARTING → RUNNING`. `start()` accepts `{STOPPED, ERROR}` as valid pre-states; clears stale `_contexts` and `_instance` on restart from ERROR; no-op when already RUNNING.
- `BrowserAutomation/_selenium_provider.py` — Selenium WebDriver provider implementing `IBrowserProvider`, `IBrowserInstance`, `IBrowserContext` ABCs. Chrome binary resolution (in order): ① `FIONA_CHROME_BINARY` env var, ② system `google-chrome-stable` on PATH, ③ Playwright-downloaded Chrome at `~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome` as fallback. Lazy imports for graceful fallback when Selenium not installed. (The old `_playwright_provider.py` and its test file have been removed — no longer dead code to preserve.)
- `BrowserAutomation/_session_manager.py` — Thread-safe synchronous wrapper around the async browser automation API for CLI/agent sessions. Uses `SeleniumBrowserProvider`.
- `BrowserAutomation/_config.py` — `BrowserConfig` dataclass. `DEFAULT_HEADLESS = True` (browser invisible by default — "echo-off" mode).
- `BrowserAutomation/_errors.py` — Full error hierarchy (BrowserLaunchError, BrowserNotRunning, ElementNotFound, etc.)
- `BrowserAutomation/__init__.py` — Convenience wrappers: `get_browser_manager()` (module-level singleton), `navigate()`, `click_element()`, etc.

### EventBus Integration

- `BrowserManager.__init__(event_bus=...)` — publishes `BrowserLaunched`, `BrowserCrashed`, `BrowserContextCreated`, `NavigationCompleted` events
- Events defined in `fiona/interfaces.py` with `BrowserEvent` base class

### CLI

```bash
fiona browser start|stop|status
fiona browser navigate <url>
fiona browser click <selector>
fiona browser type <selector> <text>
fiona browser screenshot [--output path] [--full-page]
```

### Dependencies

Required: `selenium>=4.20.0`, `webdriver-manager>=4.0.0`

### Tests

- `tests/browser/test_browser_manager.py` — 24 tests: State machine transitions, `ERROR→STARTING` recovery, graceful start (no-op on running, recovery from ERROR)

## CAD Server — JSON-RPC 2.0 WebSocket Server

Added 2026-06-22. Stdlib-only async WebSocket server with JSON-RPC 2.0 protocol and 3js frontend.

### Components

- `cad/server/_server.py` — `CadServer` (HTTP + WebSocket, stdlib-only `asyncio`)
- `cad/server/_websocket_handler.py` — RFC 6455 WebSocket implementation (frame parsing, heartbeat, reconnection)
- `cad/server/_protocol.py` — JSON-RPC 2.0 codec (RpcRequest, RpcResponse, ServerEvent, error codes)
- `cad/server/_handlers.py` — `RequestHandler` with RPC method dispatch (document.*, command.*, export.*, server.*, approval.*)
- `cad/server/_document_manager.py` — Thread-safe document lifecycle with EventBus publishing
- `cad/server/_command_executor.py` — Snapshot-based undo/redo with change classification
- `cad/server/_export_manager.py` — STL/OBJ/SVG export provider registry
- `cad/server/_app_builder.py` — `FionaContainer` DI wiring

### RPC Methods

| Group | Methods |
|---|---|
| `document.*` | `list`, `create`, `open`, `save`, `close`, `get_state` |
| `command.*` | `execute`, `undo`, `redo`, `can_undo`, `can_redo`, `list` |
| `export.*` | `formats`, `run` |
| `server.*` | `health`, `capabilities`, `ping` |
| `approval.*` | `list`, `pending`, `approve`, `deny`, `thinking` |
| `system` | `handshake` |

### EventBus Integration

- `CadServer.__init__(event_bus=...)` — subscribes to `DocumentEvent` subtypes and bridges to WebSocket `ServerEvent` broadcast
- Server lifecycle events: `server_started`, `server_stopped`
- Document changes are broadcast as `document_updated` events (incremental changeset when available, full snapshot fallback)
- Approval events: `plan_updated`, `plan_approved`, `plan_denied`, `agent_thinking`

### Tests

- `tests/cad_server/test_protocol.py` — JSON-RPC 2.0 protocol conformance
- `tests/cad_server/test_document_manager.py` — Document lifecycle, EventBus publishing
- `tests/cad_server/test_command_executor.py` — Undo/redo, change classification
- `tests/cad_server/test_export_manager.py` — Provider registration, export formats
- `tests/contracts/test_interface_contracts.py` — 140 contract tests across all interfaces
- 288 tests total (cad server + contracts)

## 3js Frontend — Vite + Three.js CAD Viewer

Added 2026-06-22. Dark-themed Three.js frontend with Z-up convention, OrbitControls, and full UI panels.

### Panels

| Panel | Purpose |
|---|---|
| Toolbar | File, Create, Actions, View menus |
| Project Tree | Object list with search/filter, select/delete/focus |
| Property Editor | Editable property form for selected objects |
| Console | Interactive command input + output |
| Status Bar | Connection state, object count, messages |
| Agent Console | Plan approval panel (hidden by default, shown via "Agent" nav tab) |

### Key Features

- WebSocket JSON-RPC 2.0 client with auto-reconnection (exponential backoff)
- Camera sync between frontend and backend (bidirectional)
- Incremental changeset application (created/modified/deleted objects)
- Toast notification system
- AgentConsole: real-time plan updates via WebSocket events (not polling), streaming agent thinking display, approve/deny buttons
- Production build: ~537KB JS + 11KB CSS (minified)

### Build

```bash
cd cad/server/_frontend && npm install && npm run build
```

### Serve

```bash
fiona ficad --port 8765
# Frontend served at http://127.0.0.1:8765
```

## Human-in-the-Loop Approval System

Added 2026-06-22. Thread-safe plan approval queue with blocking wait and WebSocket event broadcasting.

### Components

- `FionaCore/approval.py` — `ApprovalManager` with plan lifecycle (PENDING→APPROVED/DENIED→EXECUTING→COMPLETED/FAILED/CANCELLED)
- `Agent/orchestrator.py` — 4-phase flow: plan generation → submit → wait for approval → execute
- `cad/server/_handlers.py` — 5 RPC handlers: `approval.list`, `approval.pending`, `approval.approve`, `approval.deny`, `approval.thinking`
- `cad/server/_handlers.py` — `_setup_approval_listener()` bridges ApprovalManager changes → WebSocket broadcast
- `cad/server/_frontend/src/panels/AgentConsole.js` — Real-time plan display via WebSocket events

### EventBus Integration

- `ApprovalManager.__init__(event_bus=...)` publishes plan status changes
- WebSocket events: `plan_updated`, `plan_approved`, `plan_denied`, `agent_thinking`

### CLI

```bash
fiona approval pending    # List plans awaiting human approval
fiona approval list       # List all plan history
fiona approval approve <plan_id>
fiona approval deny <plan_id>
```

## Agent Browser Command Registration

Added 2026-06-22. Browser automation commands are registered across all four agent layers:

| Layer | File | Entries |
|---|---|---|
| ActionSpec | `FionaCore/actions.py` | 7 entries (browser.status/start/stop/navigate/click/type/screenshot) |
| CommandSpec | `Agent/command_registry.py` | 5 entries + added to DEFAULT_ALLOWED_ACTIONS |
| Orchestrator dispatch | `Agent/orchestrator.py` | 6 handlers in `_execute_action()` + risk estimates |
| CLI | `fiona/cli.py` | Full CLI subcommand with argument parsing |

## EventBus Wiring — Real-Time Event Propagation

Added 2026-06-22. The `EventBus` (defined in `fiona/interfaces.py`) is now wired across all major components:

### Event Catalog

| Event Class | Published By | Consumers |
|---|---|---|
| `DocumentCreated` | DocumentManager | WebSocket clients (via CadServer bridge) |
| `DocumentModified` | DocumentManager (via _replace_document) | WebSocket clients |
| `DocumentSaved` | DocumentManager | WebSocket clients |
| `DocumentClosed` | DocumentManager | WebSocket clients |
| `BrowserLaunched` | BrowserManager | EventBus subscribers |
| `BrowserCrashed` | BrowserManager | EventBus subscribers |
| `BrowserContextCreated` | BrowserManager | EventBus subscribers |
| `NavigationCompleted` | BrowserManager | EventBus subscribers |
| `server_started/stopped` | CadServer | WebSocket clients |
| `plan_updated/approved/denied` | RequestHandler | WebSocket clients |
| `agent_thinking` | RequestHandler | WebSocket clients |
| `document_updated` | RequestHandler | WebSocket clients (incremental changeset) |

### Wiring Diagram

```
EventBus
  ├── BrowserManager (publishes lifecycle events)
  ├── DocumentManager (publishes document lifecycle events)
  ├── ApprovalManager (publishes plan status changes)
  └── CadServer
       ├── subscribes to DocumentEvent → bridges to WebSocket ServerEvent
       ├── publishes server_started/stopped
       └── RequestHandler broadcasts approval + document events
```

## Permission Notes

`ydotoold` may need privileged startup depending on the machine setup.

Fiona may attempt daemon startup using:

```text
pkexec ydotoold
sudo -n ydotoold
ydotoold
```

---

## SciPhi — Scientific Operating System

*This section is the authoritative reference for all SciPhi development. Update it when architecture decisions change.*

### Philosophy

SciPhi is not a simulation library. It is a **scientific operating system** whose central component is the **Opsim Kernel** — a reasoning engine that plans, constructs, executes, validates, and explains scientific investigations. It behaves like a lead scientist coordinating a research team, not like a function that computes equations.

### Final Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User / Agent Request                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Opsim Kernel (opsim.py)                │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Simulation   │  │  Scientific  │  │  Hypothesis   │  │
│  │   Advisor     │  │   Planner    │  │   Engine      │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                 │                   │          │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌───────┴───────┐  │
│  │   Problem    │  │   Model      │  │  Uncertainty  │  │
│  │   Compiler   │  │   Selector   │  │   Analyzer    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────────┘  │
│         │                 │                              │
│  ┌──────┴─────────────────┴──────┐                      │
│  │      Solver Selection Engine   │                      │
│  └──────┬────────────────────────┘                      │
└─────────┼────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐     ┌─────────────────────────────┐
│  Models (models/)    │     │  Solvers (solvers/)         │
│                     │     │                             │
│  ┌─────────────────┐│     │  ┌─────────────────────────┐│
│  │ physics/        ││     │  │ deterministic/          ││
│  │ chemistry/      ││     │  │ stochastic/             ││
│  │ biology/        ││     │  │ symbolic/               ││
│  │ earth/          ││     │  │ optimization/           ││
│  │ engineering/    ││     │  │ hybrid/                 ││
│  │ math/           ││     │  └─────────────────────────┘│
│  └─────────────────┘│     │  Declare capabilities,      │
│  Declare equations, │     │  never know the science      │
│  never know the     │     └─────────────────────────────┘
│  computation        │
└─────────────────────┘
          │                         │
          └─────────┬───────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│           Validation & Evaluation            │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Physical  │  │ Unit     │  │ Stability │  │
│  │ Sanity    │  │ Analysis │  │ Analysis  │  │
│  └──────────┘  └──────────┘  └───────────┘  │
│  ┌──────────┐  ┌────────────────────────┐   │
│  │ Evidence │  │   Provenance Tracker   │   │
│  │ Check    │  │   (every decision)     │   │
│  └──────────┘  └────────────────────────┘   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│           Report Generation                  │
│  Findings, uncertainty, limitations,         │
│  assumptions, traceability chain             │
└─────────────────────────────────────────────┘
```

### Design Principles

| Principle | Meaning |
|-----------|---------|
| **Models describe the science, not the computation** | Equations, variables, assumptions, constraints. No solver logic. |
| **Solvers describe the computation, not the science** | Numerical methods, convergence criteria. No domain knowledge. |
| **Opsim bridges both** | Classifies, plans, compiles, selects, executes, validates. |
| **Simulation-first, but analytical when possible** | Simulation Advisor avoids unnecessary computation. |
| **Provenance by construction** | Every decision tracked as structured data, not afterthought logging. |
| **Domain-agnostic kernel** | Core kernel never imports physics, chemistry, etc. New domains are plugins. |

### Data Flow

```
User Input
    │
    ▼
OpsimKernel.investigate(query: str) → InvestigationReport
    │
    ├── Advisor.should_simulate(plan) → bool
    ├── Planner.create_plan(query) → InvestigationPlan
    ├── Compiler.compile(model, plan) → ComputationalProblem
    ├── SolverSelector.select(problem) → Solver
    ├── Solver.solve(problem) → SimulationResult
    ├── Evaluator.validate(result, plan) → ValidationReport
    ├── Uncertainty.analyze(result, plan) → UncertaintyEstimate
    ├── Provenance.record(plan, solver, result, validation, uncertainty) → ProvenanceRecord
    └── Report.compile(plan, result, validation, uncertainty, provenance) → InvestigationReport
```

### Component Specifications

#### Opsim Kernel (`kernel/opsim.py`)

The central orchestrator. Owns the full lifecycle:

1. Receive query → hand to Simulation Advisor
2. If simulation needed → hand to Scientific Planner
3. Planner selects model → Problem Compiler translates to computational form
4. Solver Selection Engine matches form to solver capabilities
5. Execute solver → results back through Validation → Uncertainty → Evaluation
6. Provenance tracker records every decision
7. Report generator compiles final output

```python
class OpsimKernel:
    async def investigate(self, query: str) -> InvestigationReport: ...
    async def simulate(self, model_id: str, params: dict) -> SimulationResult: ...
    async def validate(self, result: SimulationResult) -> ValidationReport: ...
    def list_models(self, domain: str = None) -> list[ModelInfo]: ...
    def list_solvers(self) -> list[SolverInfo]: ...
```

#### Simulation Advisor (`kernel/advisor.py`)

Before any computation: checks for analytical/closed-form solutions, dimensional analysis sufficiency, conservation law shortcuts, known results. If yes → short-circuit. If no → dispatch to Planner.

#### Scientific Planner (`kernel/planner.py`)

Produces a structured `InvestigationPlan`:

```python
@dataclass
class InvestigationPlan:
    domain: ScientificDomain
    governing_equations: list[Equation]
    variables: list[Variable]
    parameters: list[Parameter]
    assumptions: list[Assumption]
    constraints: list[Constraint]
    boundary_conditions: list[BoundaryCondition]
    required_accuracy: AccuracyLevel
    mathematical_form: MathematicalForm  # ODE, PDE, algebraic, stochastic, ...
```

#### Hypothesis Engine (`kernel/hypothesis.py`)

Generates testable hypotheses for each investigation, each independently evaluated after simulation:

```python
@dataclass
class Hypothesis:
    statement: str
    null_hypothesis: str
    variables: list[str]
    expected_outcome: str
    test_method: str
```

#### Problem Compiler (`kernel/compiler.py`)

The critical translation layer. Takes a `ScientificModel` and produces a `ComputationalProblem`. Introduces no science — purely translates. Discretization strategies are chosen based on the model's declared form and required accuracy.

```python
@dataclass
class ComputationalProblem:
    mathematical_form: MathematicalForm
    discretization: Discretization | None
    equations: list[ComputableEquation]
    initial_conditions: dict
    boundary_conditions: dict
    parameter_ranges: dict
    tolerance: float
    constraints: list[Constraint]
```

#### Solver Selection Engine (`kernel/solver_selector.py`)

Treats solver selection as constraint satisfaction — matches `ComputationalProblem` against solver capability declarations:

```python
@dataclass
class SolverCapabilities:
    name: str
    forms: list[MathematicalForm]
    methods: list[str]
    order: list[int]
    supports_parallel: bool
    handles_stiff: bool | None
    error_estimation: bool
```

#### Scientific Model (`models/`)

Self-contained module per domain. Declares equations, variables, parameters, constants, assumptions, constraints, and classifies its own mathematical form. Never references solvers.

```python
class ScientificModel(ABC):
    @property
    @abstractmethod
    def domain(self) -> ScientificDomain: ...
    @property
    @abstractmethod
    def equations(self) -> list[Equation]: ...
    @property
    @abstractmethod
    def variables(self) -> list[Variable]: ...
    @property
    @abstractmethod
    def parameters(self) -> list[Parameter]: ...
    @property
    @abstractmethod
    def mathematical_form(self) -> MathematicalForm: ...
    @property
    def assumptions(self) -> list[Assumption]: ...
    @property
    def constraints(self) -> list[Constraint]: ...
    @property
    def constants(self) -> list[PhysicalConstant]: ...
```

#### Solver (`solvers/`)

Pure computational engine. Never references domain knowledge.

```python
class Solver(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> SolverCapabilities: ...
    @abstractmethod
    async def solve(self, problem: ComputationalProblem) -> SimulationResult: ...
```

#### Validation & Evaluation (`kernel/evaluator.py`, `kernel/uncertainty.py`)

- Physical sanity: energy conservation, bounds checking, limit behavior
- Unit consistency: dimensional analysis
- Numerical stability: convergence, mesh sensitivity
- Evidence comparison: against known experimental/literature values
- Uncertainty propagation: Monte Carlo or analytic error propagation

#### Provenance Tracker (`kernel/provenance.py`)

Structured record of every scientific decision:

```python
@dataclass
class ProvenanceRecord:
    query: str
    model_id: str
    model_version: str
    equations_used: list[str]
    constants_used: list[dict]
    data_sources: list[str]
    solver_id: str
    solver_config: dict
    assumptions: list[str]
    approximations: list[str]
    validation_results: list[ValidationCheck]
    uncertainty: UncertaintyEstimate
    timestamp: datetime
```

#### Report Generator (`kernel/report.py`)

Compiles all phases into a structured scientific report with: executive summary, methodology (model, solver, assumptions), results (tables, figures, key numbers), validation summary, uncertainty and limitations, traceability chain, hypothesis evaluation results.

### Module Structure

```
SciPhi/
├── __init__.py                  # Public API, version
├── kernel/
│   ├── __init__.py
│   ├── opsim.py                 # Core orchestrator
│   ├── advisor.py               # Simulation Advisor
│   ├── planner.py               # Scientific Planner
│   ├── hypothesis.py            # Hypothesis Engine
│   ├── compiler.py              # Problem Compiler
│   ├── solver_selector.py       # Solver Selection Engine
│   ├── evaluator.py             # Scientific evaluation & validation
│   ├── uncertainty.py           # Error propagation & confidence
│   ├── provenance.py            # Provenance tracking
│   └── report.py                # Report generation
├── models/
│   ├── __init__.py              # Model registry
│   ├── physics/
│   │   ├── __init__.py
│   │   ├── kinematics.py
│   │   ├── dynamics.py
│   │   ├── thermodynamics.py
│   │   ├── electromagnetism.py
│   │   └── quantum.py
│   ├── chemistry/
│   ├── biology/
│   ├── earth/
│   ├── engineering/
│   └── math/
├── solvers/
│   ├── __init__.py              # Solver registry
│   ├── deterministic/
│   │   ├── ode_solver.py
│   │   ├── pde_solver.py
│   │   └── algebraic_solver.py
│   ├── stochastic/
│   │   └── monte_carlo.py
│   ├── symbolic/
│   │   └── symbolic_solver.py
│   └── optimization/
│       └── optimizer.py
├── data/
│   ├── __init__.py
│   ├── constants.py             # CODATA physical constants
│   └── units.py                 # Unit system with conversions
├── interfaces/
│   ├── __init__.py
│   ├── model.py                 # ScientificModel ABC
│   └── solver.py                # Solver ABC
├── visualization/
│   └── __init__.py
├── reports/
│   └── __init__.py
├── cli.py                       # SciPhi CLI (registered in fiona/cli.py)
└── tests/
    ├── test_kernel.py
    ├── test_compiler.py
    ├── test_solver_selector.py
    └── test_domains/
```

### Implementation Status (2026-06-30)

| Phase | Focus | Status | Deliverables |
|-------|-------|--------|-------------|
| **1** | Kernel Core | ✅ Complete | ABCs, Opsim orchestrator, Advisor, Planner, Compiler, Solver Selector. Hypothesis engine. Unit tests. |
| **2** | Infrastructure | ✅ Complete | CODATA constants (17), unit converter (21 units), Provenance, Report, Evaluator, Uncertainty. Tests. |
| **3** | Physics Models | ✅ Complete | 5 models: kinematics, dynamics, thermodynamics, electromagnetism, quantum. 80 tests. |
| **4** | Reference Solvers | ✅ Complete | 5 solvers: ODE (RK4/Euler/DOPRI5), algebraic (Newton/bisection/fixed-point), Monte Carlo, symbolic (SymPy), optimizer (gradient/Nelder-Mead/BFGS). 61 tests. |
| **5** | Integration & CLI | ✅ Complete | `fiona sciphi research/simulate/validate/list-models/list-solvers`. 3 ActionSpec entries. |
| **6** | More Domains | ✅ Complete | Chemistry (3 models), Biology (2 models), Earth (1 model), Engineering (2 models). 164 tests. |
| **7** | Visualization | ✅ Complete | `plot_result()`, `plot_report()`, `plot_comparison()`. Dark theme. 17 tests. |
| **8** | Hypothesis Expansion (M9b) | ✅ Complete | Form-aware generation (ODE→steady-state/conservation/monotonicity; Algebraic→uniqueness/bounds; Optimization→global optimum; Stochastic→mean convergence; PDE→stability), 6 data-driven evaluation strategies, ranking methods. 72 new tests. |
| **9** | Documentation (M9c) | ✅ Complete | `fionaDocsPage/docs/modules/sciphi.md` — architecture, Opsim pipeline, models/solvers table, CLI usage, visualization, provenance |

**Test suite**: 394 passed, 6 skipped (sympy not installed).

### Integration With Fiona

| Point | Mechanism | Status |
|-------|-----------|--------|
| CLI | `fiona sciphi <subcommand>` via `fiona/cli.py` | ✅ Done |
| Agent | `ActionSpec` in `FionaCore/actions.py` | ✅ Done |
| pyproject.toml | `SciPhi` and subpackages in `[tool.setuptools] packages` | ✅ Done |
| fionaLocalPages | `/api/v1/sciretrieval` route in aiohttp server | ✅ Done (sciretrieval handler) |
| EventBus | Simulation lifecycle events | 🔲 Planned |

### Current CLI Usage

```bash
# Full scientific investigation (Opsim pipeline)
fiona sciphi research "What is the trajectory of a projectile launched at 45 degrees?"

# Run a specific model directly
fiona sciphi simulate KinematicsModel --params '{"initial_angle": 45, "initial_velocity": 10}'

# Validate an existing result
fiona sciphi validate result.json

# List available models
fiona sciphi list-models
fiona sciphi list-models --domain physics
fiona sciphi list-models --domain chemistry

# List available solvers
fiona sciphi list-solvers
```

— SciPhi section end —
