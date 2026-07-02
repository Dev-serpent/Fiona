# Handoff — Fiona Development Session

**Date:** 2026-07-02
**Project:** Fiona — Desktop-class automation and AI agent frontend
**Total Tests:** 2090 (across all subsystems — +59 from email P0)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Completed Work — Tier 1 Foundation](#2-completed-work--tier-1-foundation)
3. [Completed Work — Tier 2 Perception](#3-completed-work--tier-2-perception)
4. [Completed Work — Voice Expansion](#4-completed-work--voice-expansion)
5. [Completed Work — Calendar System](#5-completed-work--calendar-system)
6. [Completed Work — Tier 3 Scaffolding](#6-completed-work--tier-3-scaffolding)
7. [Current State of the Codebase](#7-current-state-of-the-codebase)
8. [Test Results](#8-test-results)
9. [Key Design Decisions](#9-key-design-decisions)
10. [Known Issues & Technical Debt](#10-known-issues--technical-debt)
11. [Next Steps — Priority Order](#11-next-steps--priority-order)

---

## 1. Project Overview

Fiona is a desktop-class automation and AI agent frontend. It provides:
- **Voice interface** — wake word, push-to-talk, streaming TTS, conversation loop with barge-in
- **Agent/AI** — Ollama integration, tool-calling, ReAct loop, task decomposition
- **Desktop awareness** — window tracking, screen capture, OCR, screen monitoring, change detection
- **Encrypted communications** — CamComs device-to-device, PhiConnect encrypted chat
- **Browser automation** — Selenium-based web automation
- **Scientific computing** — SciPhi (symbolic/numeric), SciRetrieval (knowledge retrieval)
- **Macro engine** — branching, conditionals, GOTO
- **CAD platform** — FreeCAD-inspired parametric 3D modeler
- **Calendar** — SQLite-backed events, reminders, NLP time parsing
- **Web dashboard** — 24-page Flask/Jinja2 server-rendered interface
- **System tray** — background operation
- **Automation tools** — QuikTieper (key chords/launcher), TerminalAssist, RecallVault (memory)

---

## 2. Completed Work — Tier 1 Foundation

### 2.1 Scientific Knowledge Retrieval (SciRetrieval) — COMPLETE

Built and integrated a complete multi-provider scientific knowledge retrieval subsystem including ABCs, DI registration, CLI, Agent tools, Web UI integration, and 278 tests.

**26 files created in `SciRetrieval/`:**
- Router, Normalizer, EntityResolver, CacheManager, SciLab pipeline
- 3 providers: NCBI (biology), PubChem (chemistry), NIST (physics/chemistry)
- 278 passing tests across 13 test files

**Integration points:**
- `fiona/interfaces.py` — 7 new ABCs
- `fiona/cli.py` — `sire`/`sr` CLI layer (5 subcommands)
- `fiona/di.py` — `register_sci_retrieval()` with full DI wiring
- `Agent/tool_runtime.py` — SciToolRegistry integration
- `fionaLocalPages/` — 6 REST endpoints, science commands in Terminal page, Science badge

### 2.2 Browser Automation — COMPLETE (migrated Playwright → Selenium)

Previous session migrated from Playwright to Selenium. Removed `_playwright_provider.py` and its tests. Updated DI, interfaces, and documentation.

### 2.3 State Machine Fix — COMPLETE

Fixed `BrowserManager.start()` to accept ERROR state, allowing recovery from failed starts.

### 2.4 Security — COMPLETE

- Fixed CVE-2026-39892: bumped cryptography minimum to >=46.0.7
- Windows EXE compatibility layer added
- Complete security hardening, pairing protocol, macro engine v2, voice, tray, and SeeOnDesk upgrades

### 2.5 CAD Platform — COMPLETE

Full FreeCAD-inspired parametric modeling system with:
- Core document/object/property system
- Geometry primitives, boolean ops, transforms, modifiers
- Constraint solver
- Part features (extrude, revolve, fillet, chamfer, loft, sweep, shell, thread, helix)
- Assembly system
- GUI: main window, viewport, property editor, project tree, console, camera controls
- Server: WebSocket protocol, command executor, document manager, export manager
- Export: STL, OBJ, SVG, native `.cad` format
- Scripting console, plugin system, undo/redo
- CLI entry point via `fiona ficad`

### 2.6 Web Dashboard — COMPLETE

24-page Flask/Jinja2 server-rendered dashboard with real data and interactivity.

---

## 3. Completed Work — Tier 2 (Perception)

This session built the complete Tier 2 perception layer: OCR, screen monitoring, region monitoring, change events, and agent-callable tools. All 5 modules are complete and tested.

### 3.1 OCR Module (`SeeOnDesk/ocr.py`) — COMPLETE

**479 lines** — Tesseract-based OCR engine wrapper.

| Function | Purpose |
|---|---|
| `tesseract_available()` | Checks tesseract binary + pytesseract, cached after first call |
| `list_supported_languages()` | Returns list of installed Tesseract language packs |
| `read_image(path)` | OCR from an image file on disk |
| `read_image_pil(image)` | OCR from a PIL Image object directly |
| `read_screen_region(region)` | Screenshot + OCR (optionally cropped) |
| `read_window_region(window_id)` | Capture a specific window + OCR |
| `parse_region_string("x,y,w,h")` | Parse region string into tuple |
| `OcrResult` dataclass | text, confidence, boxes, language, error, success |

**Graceful degradation:** All public functions handle missing dependencies (no tesseract, no pytesseract, no PIL) by returning `OcrResult` with error info.

### 3.2 Screen Monitor (`SeeOnDesk/screen_monitor.py`) — COMPLETE

**415 lines** — Continuous screen polling with pixel-diff change detection via numpy.

| Component | Purpose |
|---|---|
| `ScreenChange` dataclass | timestamp, bbox, pixel_count, total_pixels, change_ratio, change_type, before/after paths, region |
| `compute_diff(before, after, threshold)` | Pixel-level diff engine returning changed bbox + pixel count |
| `ScreenMonitor` class | Threaded poller with configurable interval, region, threshold; on_change callback; start/stop lifecycle |

**Change classification:** `none` (< 0.1%), `minor` (0.1–5%), `significant` (5–50%), `full` (> 50%) — plus popup heuristic detection.

**Performance:** Only the changed region's bbox is computed (not full frame). Before/after screenshots saved to temp for debugging.

### 3.3 Region Monitor (`SeeOnDesk/region_monitor.py`) — COMPLETE

**362 lines** — OCR-based text change detection on specific screen regions.

| Component | Purpose |
|---|---|
| `RegionConfig` dataclass | region, poll_interval, lang, min_confidence, change_threshold ("any" or "content") |
| `RegionTextChange` dataclass | timestamp, watch_id, config, old_text, new_text, diff_type ("added", "removed", "changed", "unchanged"), old_confidence, new_confidence |
| `RegionMonitor` class | Manages multiple watched regions, each in its own daemon polling thread with `threading.Event` for clean shutdown; watch_region() returns a watch_id; unwatch_region() for cleanup |

### 3.4 Change Events (`SeeOnDesk/change_events.py`) — COMPLETE

**491 lines** — Unified pub/sub event system bridging monitors to consumers.

| Component | Purpose |
|---|---|
| `EventType` (StrEnum) | TEXT_CHANGED, SCREEN_CHANGED, POPUP_DETECTED, REGION_UPDATED, NEW_UI_STATE, MONITOR_STARTED, MONITOR_STOPPED |
| `ChangeEvent` dataclass | id, type, timestamp, source ("screen_monitor", "region_monitor"), data, metadata |
| `EventEmitter` class | subscribe(event_type, callback) → subscription token; unsubscribe(token); emit(event); thread-safe with RLock |
| `make_screen_change_adapter(emitter)` | Wraps an EventEmitter and returns a callback suitable for ScreenMonitor.on_change |
| `make_region_change_adapter(emitter)` | Wraps an EventEmitter and returns a callback suitable for RegionMonitor |

### 3.5 Perception Tools (`SeeOnDesk/tools.py`) — COMPLETE

**426 lines** — Three ITool implementations for Fiona's central tool system.

| Tool | Description |
|---|---|
| `ReadScreenTextTool` | OCR screen region or window; params: region (string "x,y,w,h"), window_id, lang, psm |
| `WatchRegionTool` | Start watching a screen region for text changes; params: region, lang, poll_interval, min_confidence, change_threshold, duration |
| `CheckOcrTool` | Check Tesseract availability and supported languages |

**Registration:** `register_desk_tools(registry)` registers all 3 tools with source="desk". Called automatically by `ToolRegistry.create_default()`.

### 3.6 SeeOnDesk `__init__.py` — Updated

Exports now include all OCR, screen_monitor, region_monitor, change_events, and tools symbols.

### 3.7 CLI Integration — COMPLETE

New SeeOnDesk CLI commands in `fiona/cli.py`:
```
fiona seeondesk ocr [--file path] [--region x,y,w,h] [--lang eng] [--psm 3]
fiona seeondesk check          # Check Tesseract availability
fiona seeondesk watch --region x,y,w,h [--interval 1.0] [--duration 60]
fiona seeondesk monitor [--region x,y,w,h] [--interval 1.0] [--threshold 30] [--duration 60]
```

### 3.8 Tier 2 Tests — COMPLETE (207 tests)

| Test file | Tests | Lines |
|---|---|---|
| `tests/test_ocr.py` | ~50+ | 390 |
| `tests/test_screen_monitor.py` | ~80+ | 709 |
| `tests/test_region_monitor.py` | ~50+ | 416 |
| `tests/test_change_events.py` | ~100+ | 967 |
| `tests/test_seeondesk_tools.py` | ~50+ | 414 |
| **Total** | **~330+** | **2896** |

### 3.9 pyproject.toml — UPDATED

Added:
```toml
perception = ["pytesseract>=0.3.10"]
```
And all Tier 3 packages registered in `[tool.setuptools.packages]`.

---

## 4. Completed Work — Voice Expansion

The Voice module was extended from 3 files (wake_word, push_to_talk, feedback_engine) to 7 files with full streaming TTS, VAD, conversation loop, and turn-taking.

### 4.1 Streaming TTS (`Voice/streaming_tts.py`) — COMPLETE

**321 lines** — Streaming TTS provider with Piper TTS local backend.

| Component | Purpose |
|---|---|
| `TTSConfig` dataclass | model_path, voice, rate, volume, device, provider ("piper" or "fallback") |
| `StreamingTTS` class | speak(text, callback) streams audio chunks; stop() for immediate interruption; uses Piper subprocess for local TTS with spd-say fallback |

### 4.2 Voice Activity Detection (`Voice/vad.py`) — COMPLETE

**293 lines** — Voice activity detection using webrtcvad with configurable aggressiveness.

| Component | Purpose |
|---|---|
| `VADConfig` dataclass | aggressiveness (0-3), frame_duration_ms, padding_duration_ms, min_speech_frames, min_silence_frames |
| `VADEngine` class | process(audio_frame) → VADState (SILENCE, SPEECH, STARTED, STOPPED); state machine with configurable padding |

### 4.3 Turn State Machine (`Voice/turn_state.py`) — COMPLETE

**252 lines** — Speaking/listening state machine handling interruption (barge-in).

| Component | Purpose |
|---|---|
| `TurnState` enum | LISTENING, PROCESSING, SPEAKING, BARGE_IN, IDLE, ERROR |
| `TurnConfig` dataclass | barge_in_enabled, interruption_timeout, cooldown_after_turn |
| `TurnStateMachine` class | State transitions with guard conditions; legal transition table enforced; events: utterance_start, utterance_end, processing_complete, speak_start, barge_in_detected, speak_complete, error, reset |

### 4.4 Conversation Loop (`Voice/conversation_loop.py`) — COMPLETE

**373 lines** — Full-duplex conversation loop: listen → transcribe → LLM → stream TTS.

| Component | Purpose |
|---|---|
| `LoopConfig` dataclass | wake_word_enabled, push_to_talk_enabled, model, stt_engine, tts_enabled, barge_in_enabled, vad_config, turn_config |
| `ConversationLoop` class | Orchestrates wake word → VAD → STT → LLM → TTS cycle; full event callbacks; clean start/stop lifecycle |

### 4.5 Voice `__init__.py` — Updated

Now exports 12 items including all 7 public classes.

---

## 5. Completed Work — Calendar System

### 5.1 Event Store (`Calendar/event_store.py`) — COMPLETE

**449 lines** — SQLite-backed calendar event and reminder persistence.

| Feature | Details |
|---|---|
| `EventStore` class | CRUD for events + reminders, recurrence support (daily/weekly/weekdays/monthly/yearly), full-text search, time-range queries |
| `get_store()` | Module-level singleton accessor |
| `DEFAULT_CALENDAR_PATH` | `~/.config/fiona/calendar.sqlite` |
| Reminders | Per-event reminders with trigger_at timestamp and notified flag |
| Recurrence | Expand recurring events into date range with `list_events(range_start, range_end)` |
| Thread-safe | SQLite with threading lock |

### 5.2 Reminder Engine (`Calendar/reminder_engine.py`) — COMPLETE

**161 lines** — Background daemon thread that polls for due reminders.

| Feature | Details |
|---|---|
| `ReminderEngine` class | Daemon thread polling every 15s for due reminders |
| `on_reminder` callback | Pluggable notification handler; default logs to console |
| `start_engine()` / `stop_engine()` | Module-level lifecycle functions |
| `get_engine()` | Singleton accessor |

### 5.3 NLP Time Parser (`Calendar/nlp_time.py`) — COMPLETE

**371 lines** — Natural language date/time parsing with dateparser + pure-Python fallback.

| Feature | Details |
|---|---|
| `parse_datetime(text)` | Parses "tomorrow at 3pm", "next monday", "in 2 hours", "next friday", "feb 14", "this weekend", etc. |
| `parse_duration(text)` | Parses "2 hours", "30 minutes", "1 day" into timedelta |
| `_HAS_DATEPARSER` | Uses dateparser if installed; otherwise pure-Python regex fallback |
| Fallback features | Relative days (today/tomorrow/yesterday), day names, time patterns (3pm, 15:30), next/last weekday, weekend, month-day patterns, relative durations |

### 5.4 Calendar CLI (`Calendar/cli.py`) — COMPLETE

**351 lines** — CLI entry point registered as `fiona calendar`.

```
fiona calendar list [--range-start] [--range-end]
fiona calendar add --title "Meeting" --at "tomorrow 3pm" [--duration 60] [--reminder 15]
fiona calendar show <event_id>
fiona calendar edit <event_id> --title "New title"
fiona calendar delete <event_id>
fiona calendar search <query>
fiona calendar reminders
fiona calendar subscribe <ics_url>
```

### 5.5 Calendar `__init__.py` — COMPLETE

Exports `EventStore`, `get_store`, `ReminderEngine`, `get_engine`, `start_engine`, `stop_engine`, `parse_datetime`, `parse_duration`.

### 5.6 CLI Integration — COMPLETE

Calendar CLI wired into `fiona/cli.py` at line 200:
```python
if args.layer == "calendar":
    _run_calendar(args)
    return
```

### 5.7 Calendar Tests — COMPLETE

**`tests/test_calendar.py`** — 330 lines, ~50+ tests covering event_store CRUD, NLP parsing, recurrence, reminders.

---

## 6. Completed Work — Tier 3 (Scaffolding)

### 6.1 Email Client (`Communications/email_client.py`) — BUILT (NOT FULLY INTEGRATED)

**421 lines** — Zero-dependency IMAP + SMTP email client using stdlib only.

| Component | Purpose |
|---|---|
| `EmailConfig` dataclass | imap_host, imap_port, smtp_host, smtp_port, username, password, use_ssl, important_senders, check_interval |
| `EmailMessage` dataclass | uid, subject, sender, recipients, date, body |
| `EmailClient` class | `connect()`, `disconnect()`, `list_inbox(max_results, folder)`, `read_email(uid)`, `search_emails(criteria)`, `send_email(to, subject, body, cc, bcc, attachments, html)`, `get_unread_count()`, `mark_as_read(uid)` |

**Graceful degradation:** All methods return error dicts on connection/auth failure instead of raising.

**Dependencies:** Pure stdlib (`imaplib`, `smtplib`, `email`). No external dependencies required.

### 6.2 Email CLI (`Communications/cli.py`) — BUILT (NOT FULLY INTEGRATED)

**298 lines** — CLI entry point ready for `fiona email` integration.

```
fiona email config [--imap-host] [--imap-port] [--smtp-host] [--smtp-port]
                   [--username] [--password] [--ssl]
fiona email inbox [--max 10] [--folder INBOX]
fiona email read <uid>
fiona email send --to "user@example.com" --subject "Hello" --body "Message"
fiona email search --query "subject:meeting"
fiona email unread
```

**Status:** `cli.py` exists but is NOT yet wired into `fiona/cli.py`. No `email_tools.py` file exists yet (agent tool definitions not yet built).

### 6.3 SmartHome Package — SCAFFOLD ONLY

`SmartHome/__init__.py` — Package docstring only. No implementation files exist yet.

Planned files (from JARVIS_ROADMAP.md):
- `SmartHome/home_assistant.py` — Home Assistant REST/WebSocket client
- `SmartHome/mqtt_bridge.py` — MQTT pub/sub client
- `SmartHome/device_registry.py` — Track connected devices + state
- `SmartHome/automation_rules.py` — Time/event-based automation

### 6.4 GNS3Automation Package — SCAFFOLD ONLY

`GNS3Automation/__init__.py` — Package docstring only. No implementation files.

### 6.5 HomeBackend Package — SCAFFOLD ONLY

`HomeBackend/__init__.py` — Package docstring only. No implementation files.

---

## 7. Current State of the Codebase

### 7.1 Directory Structure

```
fiona/
├── Agent/                    # Agent orchestration, tool runtime, Ollama client
├── BrowserAutomation/        # Selenium browser automation (Playwright removed)
├── cad/                      # FreeCAD-inspired parametric 3D modeler
│   ├── core/                 # Document, object, property, params
│   ├── geometry/             # Primitives, transforms, boolean, modifiers
│   ├── constraints/          # Constraint solver
│   ├── sketch/               # Sketch workspace
│   ├── part/                 # Features (extrude, revolve, fillet, etc.)
│   ├── assembly/             # Assembly system
│   ├── commands/             # Command registry, builtins, command stack
│   ├── scripting/            # Scripting console
│   ├── io/                   # STL, OBJ, SVG, native format export
│   ├── rendering/            # Viewport rendering
│   ├── plugins/              # Plugin manager
│   ├── gui/                  # Main window, property editor, viewport, tree, camera
│   ├── cli/                  # CLI entry point
│   └── server/               # WebSocket protocol, command executor, document/export manager
├── Calendar/                 # NEW — SQLite events, reminders, NLP time
│   ├── __init__.py
│   ├── event_store.py        # 449 lines
│   ├── reminder_engine.py    # 161 lines
│   ├── nlp_time.py           # 371 lines
│   └── cli.py                # 351 lines
├── CamComs/                  # Encrypted device-to-device communications
├── CmdTrace/                 # Audit trail with search/export
├── Communications/           # NEW — Email integration (partial)
│   ├── __init__.py
│   ├── email_client.py       # 421 lines — IMAP + SMTP client
│   └── cli.py                # 298 lines — CLI (not wired in)
├── DataClient/               # Search, scrape, summarize, export
├── EyeControl/               # Eye tracking subsystem
├── FionaCore/                # Core engine: actions, ACL, permissions, macros, voice, notifications
├── fiona/                    # Umbrella: CLI, DI, interfaces, plugin system, tracing
├── fionaLocalPages/          # Flask/Jinja2 web dashboard (24 pages)
├── GNS3Automation/           # NEW — Scaffold only (__init__.py)
├── HomeBackend/              # NEW — Scaffold only (__init__.py)
├── PhiConnect/               # Encrypted computer chat
├── QuikTieper/               # Key chord app launcher and macro system
├── RecallVault/              # Persistent key-value memory
├── SciPhi/                   # Scientific computing framework
├── SciRetrieval/             # Scientific knowledge retrieval
├── SeeOnDesk/                # Desktop awareness + Tier 2 Perception
│   ├── __init__.py           # Updated exports
│   ├── desktop.py            # Existing: window tracking
│   ├── vision.py             # Existing: screen capture, LLM vision
│   ├── process_tracker.py    # Existing
│   ├── workspace_watcher.py  # Existing
│   ├── action_discovery.py   # Existing
│   ├── ocr.py                # NEW — 479 lines
│   ├── screen_monitor.py     # NEW — 415 lines
│   ├── region_monitor.py     # NEW — 362 lines
│   ├── change_events.py      # NEW — 491 lines
│   └── tools.py              # NEW — 426 lines
├── SmartHome/                # NEW — Scaffold only (__init__.py)
├── TerminalAssist/           # Terminal dashboard and TUI
├── Voice/                    # Voice module — EXPANDED
│   ├── __init__.py           # Updated exports
│   ├── wake_word.py          # Existing
│   ├── push_to_talk.py       # Existing
│   ├── feedback_engine.py    # Existing
│   ├── streaming_tts.py      # NEW — 321 lines
│   ├── vad.py                # NEW — 293 lines
│   ├── turn_state.py         # NEW — 252 lines
│   └── conversation_loop.py  # NEW — 373 lines
├── Vsee/                     # Holography viewer
├── tests/                    # All project tests
└── pyproject.toml            # Updated with perception, communications, smarthome, home-backend
```

### 7.2 Line Counts for New/Modified Files (this session)

| File | Lines |
|---|---|
| `SeeOnDesk/ocr.py` | 479 |
| `SeeOnDesk/screen_monitor.py` | 415 |
| `SeeOnDesk/region_monitor.py` | 362 |
| `SeeOnDesk/change_events.py` | 491 |
| `SeeOnDesk/tools.py` | 426 |
| `SeeOnDesk/__init__.py` | 65 (updated) |
| `Calendar/event_store.py` | 449 |
| `Calendar/reminder_engine.py` | 161 |
| `Calendar/nlp_time.py` | 371 |
| `Calendar/cli.py` | 351 |
| `Calendar/__init__.py` | 33 |
| `Voice/conversation_loop.py` | 373 |
| `Voice/streaming_tts.py` | 321 |
| `Voice/vad.py` | 293 |
| `Voice/turn_state.py` | 252 |
| `Voice/__init__.py` | 27 (updated) |
| `Communications/email_client.py` | 421 |
| `Communications/cli.py` | 298 |
| `SmartHome/__init__.py` | 3 |
| `GNS3Automation/__init__.py` | 3 |
| `HomeBackend/__init__.py` | 3 |
| `fiona/cli.py` | 1975 (updated with SeeOnDesk + Calendar + Tools handlers) |
| `Agent/tool_runtime.py` | 245 (updated with register_desk_tools) |
| `pyproject.toml` | 79 (updated) |
| `tests/test_ocr.py` | 390 |
| `tests/test_screen_monitor.py` | 709 |
| `tests/test_region_monitor.py` | 416 |
| `tests/test_change_events.py` | 967 |
| `tests/test_seeondesk_tools.py` | 414 |
| `tests/test_calendar.py` | 330 |
| `tests/test_voice_loop.py` | 457 |
| **Total new/modified** | **~10,300 lines** |

### 7.2a New/Modified Files (this session — Email P0)

| File | Lines | Purpose |
|---|---|---|
| `Communications/cli.py` | 396 | Rewritten to match email_client.py API |
| `Communications/__init__.py` | 7 | Updated exports |
| `Communications/email_tools.py` | 570 | 4 ITool agent tools + registration |
| `fiona/cli.py` | 1995 | Added email parser + dispatch + handler |
| `Agent/tool_runtime.py` | 248 | Added register_email_tools call |
| `fiona/di.py` | 379 | Added register_email_client function |
| `tests/test_email_client.py` | ~350 | 21 tests for EmailClient |
| `tests/test_email_tools.py` | 678 | 38 tests for email tools |
| **Total new/modified** | **~2,200 lines** | |

### 7.3 Integration Status

| Subsystem | CLI (`fiona/cli.py`) | DI (`fiona/di.py`) | Agent Tools | Web UI | Tests |
|---|---|---|---|---|---|
| SciRetrieval | ✅ (`sire`/`sr`) | ✅ | ✅ SciToolRegistry | ✅ 6 endpoints | ✅ 278 |
| SeeOnDesk (existing) | ✅ (`seeondesk`) | ❌ | N/A | ✅ | ✅ |
| Tier 2 Perception | ✅ (ocr/watch/monitor) | ❌ | ✅ (3 tools via register_desk_tools) | ❌ | ✅ 330+ |
| Calendar | ✅ (`calendar`) | ❌ | ❌ | ❌ | ✅ 50+ |
| Voice (expanded) | ✅ (`voice`) | ❌ | ❌ | ❌ | ✅ (via test_voice_loop.py) |
| Communications/Email | ✅ (`email`) | ✅ (`register_email_client`) | ✅ (4 tools via register_email_tools) | ❌ | ✅ 59 |
| SmartHome | ❌ | ❌ | ❌ | ❌ | ❌ |
| GNS3Automation | ❌ | ❌ | ❌ | ❌ | ❌ |
| HomeBackend | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 8. Test Results

### 8.1 Overall

```
2031 tests collected across all subsystems
```

### 8.2 New Tests This Session

| Test file | Est. Tests | Status |
|---|---|---|
| `tests/test_ocr.py` | ~50 | ✅ Complete |
| `tests/test_screen_monitor.py` | ~80 | ✅ Complete |
| `tests/test_region_monitor.py` | ~50 | ✅ Complete |
| `tests/test_change_events.py` | ~100 | ✅ Complete |
| `tests/test_seeondesk_tools.py` | ~50 | ✅ Complete |
| `tests/test_calendar.py` | ~50 | ✅ Complete |
| `tests/test_voice_loop.py` | ~50 | ✅ Complete |

### 8.3 Existing Test Suites

| Area | Est. Tests | Notes |
|---|---|---|
| SciRetrieval | 278 | 13 files |
| SciPhi | ~50 | 9 files |
| BrowserAutomation | ~30 | 2 files |
| CAD server | ~40 | 4 files |
| Voice | ~50 | test_voice_loop.py + older voice tests |
| SeeOnDesk (existing) | ~30 | test_seeondesk.py, test_action_discovery, etc. |
| CamComs | ~80 | encryption, instructions, receiver, service, transport, trust |
| FionaCore | ~40 | acl, permissions, shell_safety, speech, verification, voice_engine |
| Agent | ~80 | backward_compat, chat_handler, orchestration, orchestrator, ollama, etc. |
| QuikTieper | ~20 | app_command_presets, key_assignment, remote, system_tray |
| Other | ~100 | cli, dataclient, desktop, esp32, eyecontrol, gui, macro, notifications, pairing, recall, terminal_assist, vault, vsee, workspace_watcher |
| **Total** | **~2031** | |

---

## 9. Key Design Decisions

### 9.1 Tier 2 (Perception)

| Decision | Rationale |
|---|---|
| **numpy for pixel diff** (not PIL) | numpy array comparison is orders of magnitude faster for frame-sized arrays |
| **Threaded monitors with Event for shutdown** | Avoids race conditions on stop; each region gets its own daemon thread |
| **OcrResult always returned (never raises)** | Consistent with existing Fiona pattern of graceful degradation |
| **Tesseract availability cached** | Avoids subprocess calls on every OCR operation |
| **EventEmitter with RLock** | Thread-safe emission; adapters bridge ScreenMonitor/RegionMonitor into unified stream |
| **Tools as ITool implementations** | Plugs directly into existing ToolRegistry/ToolRuntime without any adapter layer |
| **`register_desk_tools()` auto-called** | Zero-config; just create a ToolRegistry and all perception tools are available |

### 9.2 Calendar

| Decision | Rationale |
|---|---|
| **SQLite (not JSON)** | Supports queries, indexing, recurrence expansion, full-text search |
| **dateparser optional with fallback** | Heavy dependency (~10MB) for NLP; pure-Python fallback covers 90% of use cases |
| **ReminderEngine as daemon thread** | Simple, no external process needed; poll interval 15s is fine for desktop use |
| **ISO 8601 everywhere** | Standard datetime format for serialization |

### 9.3 Voice Expansion

| Decision | Rationale |
|---|---|
| **Piper TTS** | Fully local, 200+ voices, fast streaming, no API key |
| **webrtcvad for VAD** | Industry standard, lightweight, configurable aggressiveness |
| **TurnStateMachine with legal transitions** | Prevents invalid state transitions at the model level |
| **Barge-in support** | Configurable; key differentiator from one-shot voice assistants |

### 9.4 Communications/Email

| Decision | Rationale |
|---|---|
| **Pure stdlib (imaplib + smtplib)** | Zero external dependencies; avoids aiohttp complexity for email |
| **EmailConfig as dataclass** | Easy to serialize/deserialize for config persistence |

---

## 10. Known Issues & Technical Debt

### 10.1 Tier 2 (Perception)

1. **ScreenMonitor saves temp files for every frame** — The `before` and `after` screenshot paths in `ScreenChange` are saved to temp files. These accumulate if the monitor runs for a long time. A cleanup mechanism should be added, or save-to-temp should be optional.

2. **RegionMonitor polls regardless of screen changes** — Could be optimized to only OCR when ScreenMonitor detects a change in that region. No integration between the two monitors exists yet.

3. **Region string parsing is X11-style (top-left origin)** — Wayland compositors may use different coordinate systems. This should be documented.

4. **No OCR confidence filtering in OCR module** — `min_confidence` is in `RegionConfig` but not in `OcrResult` or the base OCR functions. All words are returned regardless of confidence.

### 10.2 Calendar

1. **No iCal import/export** — The `subscribe` command in CLI is incomplete. No ICS parsing exists yet.

2. **ReminderEngine has no persistent state** — If the process restarts, all pending reminders are lost until the engine polls again (max 15s gap). No crash recovery.

3. **No web UI** — Calendar has CLI but no FLoP dashboard pages yet.

### 10.3 Voice

1. **ConversationLoop not integrated with Agent** — The loop can listen → STT → TTS, but the LLM step is not yet wired to the Agent's Ollama client or tool runtime.

2. **Piper TTS not auto-downloaded** — Users must manually download Piper models. No model auto-discovery or download helper.

3. **No web UI** — Voice has no FLoP dashboard integration (mic button, status indicator, etc.).

### 10.4 Communications/Email

1. **CLI not wired into fiona/cli.py** — `fiona email` does not work yet.
2. **No email_tools.py** — Agent tool definitions for email not yet built.
3. **No DI registration** — EmailClient not registered in FionaContainer.
4. **No tests** — email_client.py and cli.py have zero tests.
5. **No web UI** — No email page in FLoP dashboard.

### 10.5 Tier 3 Packages (SmartHome, GNS3Automation, HomeBackend)

These are scaffolds only — `__init__.py` with a docstring and nothing else. All require full implementation.

### 10.6 Other

1. **Browser singleton** — `BrowserAutomation/__init__.py` holds module-level `_default_manager` singleton. ERROR state from failed start persists until `start()` called again (known, intentional).

2. **No Calendar tools for Agent** — Agent cannot schedule events or set reminders via tool calls.

---

## 11. Next Steps — Priority Order

### 🟢 Completed This Session

#### P0 — Wire Email CLI + Build Agent Email Tools ✅

All 5 items completed:

1. ✅ **Wired `Communications/cli.py` into `fiona/cli.py`** — `fiona email` command group works with: `list`, `read`, `send`, `search`, `config`, `watch`
2. ✅ **Created `Communications/email_tools.py`** — 4 agent tool definitions:
   - `read_inbox(max_results, folder)` — Read inbox emails
   - `send_email(to, subject, body, cc)` — Send emails
   - `search_email(query, max_results)` — Search emails
   - `get_unread_count(folder)` — Count unread
3. ✅ **Registered email tools** — `register_email_tools(registry)` wired into `ToolRegistry.create_default()` (4 tools at source="email")
4. ✅ **Wrote email tests** — 59 passing tests (21 for email_client.py, 38 for email_tools.py)
5. ✅ **Added DI registration** — `register_email_client()` in `fiona/di.py`

Additionally:
- ✅ Fixed `Communications/cli.py` (298→396 lines) — All API calls match actual `email_client.py` methods
- ✅ Updated `Communications/__init__.py` — Exports `EmailClient`, `EmailConfig`, `EmailMessage`
- ✅ Code reviewed — APPROVED with minor suggestions addressed

### 🔴 Tier 3 Priority (Next Session)

#### P1 — SmartHome Implementation

1. **`SmartHome/mqtt_bridge.py`** — MQTT pub/sub client using paho-mqtt
2. **`SmartHome/home_assistant.py`** — Home Assistant REST API client
3. **`SmartHome/device_registry.py`** — Connected device state tracking
4. **`SmartHome/automation_rules.py`** — Time/event-based rules
5. **CLI + Agent tools + tests**

#### P2 — GNS3Automation Implementation

1. **`GNS3Automation/client.py`** — GNS3 REST API client
2. **`GNS3Automation/project_manager.py`** — Project lifecycle management
3. **`GNS3Automation/node_manager.py`** — Node control (start/stop/configure)
4. **`GNS3Automation/link_manager.py`** — Link management
5. **CLI + Agent tools + tests**

### 🟡 Tier 2 Follow-up

#### P3 — Integration & Polish

1. **GUI region selector** — Click-and-drag UI to select screen regions instead of typing coordinates
2. **ScreenMonitor temp file cleanup** — Add periodic cleanup or optional temp saving
3. **OCR confidence filtering** — Add min_confidence parameter to read_image/read_screen_region
4. **Cross-monitor optimization** — Use ScreenMonitor changes to trigger RegionMonitor OCR only when needed
5. **Web UI for Tier 2** — OCR viewer + region monitor dashboard in FLoP

### 🟡 Tier 1 Follow-up

#### P4 — Calendar Web UI + Agent Tools

1. **Calendar page in FLoP dashboard** — Event list, create/edit forms, reminders display
2. **Agent Calendar tools** — `schedule_event`, `list_events`, `set_reminder`, `get_schedule`
3. **iCal import/export** — ICS file parsing and generation

#### P5 — Voice → Agent Integration

1. **Wire ConversationLoop to Agent** — LLM step calls Agent orchestrator instead of raw Ollama
2. **FLoP dashboard mic button** — Browser-based voice input
3. **Piper model download helper** — Auto-download models from Hugging Face

### 🔵 Long-term

#### P6 — Push Notification Infrastructure
- `FionaCore/notification_store.py` — SQLite notification persistence
- `FionaCore/push_provider.py` — ntfy.sh / Gotify / Pushover client
- `fionaLocalPages/server/push.py` — WebSocket push endpoint

#### P7 — Proactive Agent
- `Agent/proactive_engine.py` — Background monitors with trigger rules
- `Agent/scheduler.py` — Cron-like scheduling
- `Agent/goal_store.py` — SQLite-backed goal persistence

#### P8 — Long-Term Agent Memory
- `Agent/episodic_memory.py` — Timeline of past events
- `Agent/entity_extractor.py` — NLP entity extraction
- `Agent/summarizer.py` — Session summarization
- `Agent/memory_retrieval.py` — RAG-style memory query

#### P9 — Learning & Personalization
- User profiling, habit tracking, feedback system

---

## Appendix A: Complete File Inventory

### SeeOnDesk (Tier 2 — Perception)

| File | Lines | Purpose |
|---|---|---|
| `SeeOnDesk/__init__.py` | 65 | Package exports (updated) |
| `SeeOnDesk/ocr.py` | 479 | Tesseract OCR engine wrapper |
| `SeeOnDesk/screen_monitor.py` | 415 | Pixel-diff screen monitoring |
| `SeeOnDesk/region_monitor.py` | 362 | OCR-based region text monitoring |
| `SeeOnDesk/change_events.py` | 491 | Unified pub/sub event system |
| `SeeOnDesk/tools.py` | 426 | 3 ITool implementations for agent |
| `SeeOnDesk/desktop.py` | (existing) | Active window tracking |
| `SeeOnDesk/vision.py` | (existing) | Screen capture + LLM vision |
| `SeeOnDesk/process_tracker.py` | (existing) | Process tracking |
| `SeeOnDesk/workspace_watcher.py` | (existing) | Workspace change detection |
| `SeeOnDesk/action_discovery.py` | (existing) | Action discovery |

### Calendar

| File | Lines | Purpose |
|---|---|---|
| `Calendar/__init__.py` | 33 | Package exports |
| `Calendar/event_store.py` | 449 | SQLite event/reminder persistence |
| `Calendar/reminder_engine.py` | 161 | Background reminder daemon |
| `Calendar/nlp_time.py` | 371 | Natural language date parsing |
| `Calendar/cli.py` | 351 | CLI entry point |

### Voice (Expanded)

| File | Lines | Purpose |
|---|---|---|
| `Voice/__init__.py` | 27 | Package exports (updated) |
| `Voice/wake_word.py` | 94 | Wake word detection |
| `Voice/push_to_talk.py` | 80 | Push-to-talk |
| `Voice/feedback_engine.py` | 82 | Audio feedback |
| `Voice/streaming_tts.py` | 321 | Streaming TTS (Piper) |
| `Voice/vad.py` | 293 | Voice activity detection |
| `Voice/turn_state.py` | 252 | Turn-taking state machine |
| `Voice/conversation_loop.py` | 373 | Full duplex conversation loop |

### Communications (Complete — P0 Integrated)

| File | Lines | Purpose |
|---|---|---|
| `Communications/__init__.py` | 7 | Package exports (`EmailClient`, `EmailConfig`, `EmailMessage`) |
| `Communications/email_client.py` | 421 | IMAP + SMTP email client |
| `Communications/cli.py` | 396 | CLI entry point (wired as `fiona email`) |
| `Communications/email_tools.py` | 570 | 4 ITool agent tools + registration helper |

### New Scaffold Packages

| File | Lines | Purpose |
|---|---|---|
| `SmartHome/__init__.py` | 3 | Package docstring only |
| `GNS3Automation/__init__.py` | 3 | Package docstring only |
| `HomeBackend/__init__.py` | 3 | Package docstring only |

### Test Files

| File | Lines | Est. Tests | Purpose |
|---|---|---|---|
| `tests/test_ocr.py` | 390 | ~50 | OCR module tests |
| `tests/test_screen_monitor.py` | 709 | ~80 | Screen monitor tests |
| `tests/test_region_monitor.py` | 416 | ~50 | Region monitor tests |
| `tests/test_change_events.py` | 967 | ~100 | Change events tests |
| `tests/test_seeondesk_tools.py` | 414 | ~50 | Perception tools tests |
| `tests/test_calendar.py` | 330 | ~50 | Calendar tests |
| `tests/test_voice_loop.py` | 457 | ~50 | Conversation loop tests |
| `tests/test_email_client.py` | ~350 | 21 | EmailClient tests (mocked IMAP/SMTP) |
| `tests/test_email_tools.py` | 678 | 38 | Email agent tools tests |

---

*This handoff reflects the state of the codebase as of commit `39b56c9` (2026-07-02).*
