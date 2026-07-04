# JARVIS Roadmap — Gap Analysis & Build Plan

This document records all software components needed to evolve Fiona into a complete JARVIS-like system. It is organized by priority tier.

---

## ✅ Already Working (no build required)

| Capability | Module | Status |
|---|---|---|
| Wake word detection | `Voice/` | Done |
| Push-to-talk | `Voice/` | Done |
| Speech-to-text (Whisper) | `FionaCore/voice_engine.py` | Done |
| Reactive Q&A + ReAct loop | `Agent/orchestrator.py` | Done |
| Task decomposition & sub-agents | `Agent/orchestration.py` | Done |
| Plan generation + human approval | `Agent/orchestrator.py` | Done |
| Tool-calling via Ollama | `Agent/tool_runtime.py` | Done |
| Window title / workspace tracking | `SeeOnDesk/` | Done |
| Screen capture + LLM vision analysis | `SeeOnDesk/vision.py` | Done |
| Encrypted device-to-device comms | `CamComs/` | Done |
| Encrypted computer chat | `PhiConnect/` | Done |
| Macro engine (conditionals, branching, GOTO) | `FionaCore/macro_engine.py` | Done |
| Action system with ACL / permissions | `FionaCore/actions.py` | Done |
| Audit trail with search/export | `CmdTrace/` | Done |
| Persistent key-value memory | `RecallVault/` | Done |
| Plugin system | `fiona/plugin_system.py` | Done |
| Scientific knowledge retrieval | `SciRetrieval/` | Done |
| Scientific computing framework | `SciPhi/` | Done |
| Web dashboard (24 pages) | `fionaLocalPages/` | Done |
| Browser automation (Selenium) | `BrowserAutomation/` | Done |
| Desktop notifications | `FionaCore/notifications.py` | Done |

---

## 🔴 Tier 1 — Foundation (Conversation & Proactivity)

These are the biggest gaps — without them, Fiona feels like a CLI tool, not an AI assistant.

### 1. Streaming TTS + Conversational Voice Loop

**Files to create:**
- `Voice/streaming_tts.py` — Streaming TTS provider (Piper TTS local backend)
- `Voice/conversation_loop.py` — Full duplex: listen → transcribe → LLM → stream TTS → allow barge-in
- `Voice/vad.py` — Voice activity detection for endpoint detection
- `Voice/turn_state.py` — Speaking/listening state machine (handles interruption)

**What it does:**
- Replaces one-shot `spd-say` with natural streaming speech
- WebSocket-based audio streaming to/from FLoP dashboard
- Turn-taking: can be interrupted mid-sentence (barge-in)
- 200+ voices available via Piper TTS (all local, no API key)

**Dependencies:** `piper-tts` (or system Piper binary), `sounddevice`, `wave`

---

### 2. Proactive Agent (Ambient Awareness + Triggers)

**Files to create:**
- `Agent/proactive_engine.py` — Background monitors with trigger rules
- `Agent/scheduler.py` — Cron-like scheduling for agent actions
- `Agent/awareness_mode.py` — Ambient "low-priority" background listening
- `Agent/goal_store.py` — SQLite-backed long-running goal persistence

**What it does:**
- Scheduled agent triggers ("check CPU every 5 min, report if > 90%")
- Event-driven triggers (process crash, high load, new email → notify)
- Ambient background awareness mode (low resource, watches for patterns)
- Proactive suggestions ("you usually open terminal now — ready it?")
- Goals survive agent restarts

---

### 3. Long-Term Agent Memory (Episodic + Semantic)

**Files to create:**
- `Agent/episodic_memory.py` — Timeline of past events + outcomes
- `Agent/entity_extractor.py` — NLP entity extraction from conversations
- `Agent/summarizer.py` — Session summarization for compression
- `Agent/memory_retrieval.py` — RAG-style memory query + context injection

**What it does:**
- Chat sessions auto-summarized when they get long
- Entities (names, preferences, facts) extracted and stored in RecallVault
- Relevant past context injected into LLM prompts automatically
- Agent remembers what happened across sessions

---

## 🟠 Tier 2 — Perception (Understanding the World)

### 4. OCR (Screen Text Reading)

**Files to create:**
- `SeeOnDesk/ocr.py` — Tesseract OCR engine wrapper
- `SeeOnDesk/region_monitor.py` — Watch specific screen regions for text changes

**What it does:**
- Read text from any screen region on demand
- Real-time text change detection (new text appears → trigger)
- Agent tool: `read_screen_text(region=...)`

**Dependencies:** `tesserocr` or `pytesseract` + system `tesseract-ocr`

---

### 5. Real-Time Screen Monitoring + Change Detection

**Files to create:**
- `SeeOnDesk/screen_monitor.py` — Continuous screen polling + diff engine
- `SeeOnDesk/change_events.py` — Event emission on screen state changes

**What it does:**
- Frame-by-frame screen diffing (via mss or pyautogui)
- Visual change event system → triggers agent awareness
- Auto-dismiss popups, detect new UI states

---

### 6. Calendar / Time System

**Files to create:**
- `Calendar/event_store.py` — SQLite calendar persistence
- `Calendar/reminder_engine.py` — Time-based reminder dispatcher
- `Calendar/nlp_time.py` — Natural language date parsing
- `Calendar/cli.py` — CLI entry point

**What it does:**
- Create, list, edit, delete events
- Natural language input ("meeting tomorrow at 3pm", "remind me in 2 hours")
- Background reminder engine fires notifications at scheduled times
- Agent tools: `schedule_event`, `list_events`, `set_reminder`, `get_schedule`

**Status:** 🟢 IN PROGRESS (started 2026-07-01)

---

## 🟡 Tier 3 — Communication & Environment (Extending Reach)

### 7. Email Integration

**Files to create:**
- `Communications/email_client.py` — IMAP + SMTP wrapper
- `Communications/email_tools.py` — Agent tool definitions for email

**What it does:**
- Read inbox, search emails, parse content
- Send emails on behalf of user
- Agent tools: `read_inbox`, `send_email`, `search_email`
- Email notification triggers (important sender → alert)

---

### 8. Smart Home / IoT Platform Integration

**Files to create:**
- `SmartHome/home_assistant.py` — Home Assistant REST/WebSocket client
- `SmartHome/mqtt_bridge.py` — MQTT pub/sub client
- `SmartHome/device_registry.py` — Track connected devices + state
- `SmartHome/automation_rules.py` — Time/event-based automation

**What it does:**
- Control lights, thermostats, locks via voice or agent
- Device state tracking and dashboard
- Automation rules ("turn off lights at 11pm")
- Uses existing CamComs for encrypted device path

---

### 9. Push Notification Infrastructure

**Files to create:**
- `FionaCore/notification_store.py` — SQLite notification persistence
- `FionaCore/push_provider.py` — ntfy.sh / Gotify / Pushover client
- `fionaLocalPages/server/push.py` — WebSocket push endpoint

**What it does:**
- Notifications survive restarts (persistent history)
- Scheduled/delayed notifications
- Push to phone (ntfy.sh) when user is away from desk
- Actionable notifications with response buttons

---

## 🟢 Tier 4 — Learning & Personalization (Gets Better)

### 10. User Profiling + Preference Learning

**Files to create:**
- `Agent/user_profile.py` — User model + preference store
- `Agent/preference_learner.py` — Implicit learning from user behavior

**What it does:**
- Remembers user name, preferences, working hours
- Infers preferences from behavior (response length, tone, verbosity)
- Personalizes agent system prompt automatically

---

### 11. Habit Tracking + Behavioral Modeling

**Files to create:**
- `Agent/habit_tracker.py` — Activity pattern recorder
- `Agent/behavior_model.py` — Predict next likely action

**What it does:**
- Records what user does, when, for how long
- Detects daily rhythms and common sequences
- Predictive suggestions based on patterns

---

### 12. Feedback/Rating System

**Files to create:**
- `Agent/feedback_store.py` — Rating + correction persistence
- `Agent/learning_loop.py` — Feedback → model adjustment pipeline

**What it does:**
- Thumbs up/down on agent responses
- User corrections ingested as learning signal
- Performance metrics tracked over time

---

## 🔵 Tier 5 — Integration & Polish (Seamless Experience)

### 13. Multi-Modal Input Fusion

**Files to create:**
- `Agent/multi_modal_input.py` — Unified input stream with modality tags

**What it does:**
- Accepts voice + text + screen gesture simultaneously
- Cross-modal context (see + hear → combined understanding)
- Web dashboard voice input (browser microphone → STT → agent)

---

### 14. Context Engine (Cross-Session Awareness)

**Files to create:**
- `Agent/context_engine.py` — Cross-session context builder

**What it does:**
- Session stitching (what happened last time → carry forward)
- Task resumption prompts ("you were working on X — continue?")
- Environment-aware behavior (time of day, day of week, recent activity)

---

## Build Order Recommendation

| Phase | Items | Estimated effort |
|-------|-------|-----------------|
| **Phase 1** | Calendar/Time system | 3-5 days |
| **Phase 2** | Streaming TTS + Conversational voice | 5-7 days |
| **Phase 3** | Proactive agent + Long-term memory | 6-8 days |
| **Phase 4** | OCR + Screen monitoring | 4-5 days |
| **Phase 5** | Email + Smart Home | 5-7 days |
| **Phase 6** | Push notifications | 2-3 days |
| **Phase 7** | Learning (profiling, habits, feedback) | 4-5 days |
| **Phase 8** | Multi-modal + Context engine | 3-4 days |

**Total:** ~10-14 weeks

---

## Notes

- Start each phase by verifying it integrates with existing CLI (`fiona/cli.py`), Agent tools (`Agent/tool_runtime.py`), and FLoP dashboard (`fionaLocalPages/`)
- All new modules should include tests under `tests/`
- Prefer stdlib + minimal dependencies; make heavy deps optional (extras in pyproject.toml)
- Each subsystem should have its own `cli.py` for the `fiona <subsystem>` command group
