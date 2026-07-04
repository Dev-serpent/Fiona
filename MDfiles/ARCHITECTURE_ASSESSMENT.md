# Fiona — Architecture Assessment

> **Date:** 2026-06-20
> **Evaluated against:** *"A middleware platform that enables AI agents to control desktop applications, browsers, and system functions through a standardized interface"*

---

## 1. Middleware Platform — ~80%

Fiona functions as a middleware layer sitting between the user/AI and the operating system.

| Component | Role |
|-----------|------|
| `FionaCore/actions.py` | Central action routing |
| `FionaCore/acl.py` | Access control / permissions filtering |
| `FionaCore/shell_safety.py` | Shell command safety validation |
| `FionaCore/macro_engine.py` | Scripted macro execution |
| `CmdTrace` | Observability / audit log for every routed action |

### Gaps
- No formal request/response bus or message protocol
- Actions routed through Python function calls rather than a network-transparent middleware bus
- Not framework-abstracted — middleware-ish but not fully decoupled

---

## 2. AI Agent Enablement — ~75%

The `Agent/` subpackage provides local LLM integration and agent orchestration.

| Capability | Status |
|-----------|--------|
| Ollama bridge (local LLM) | ✅ Implemented |
| Think-act-observe loop | ✅ Implemented |
| Command registry (`Agent/personality.py`, `Agent/chat_handler.py`) | ✅ Implemented |
| Foreman multi-agent orchestration (`Agent/orchestration.py`, `Agent/orchestrator.py`) | ✅ Implemented |
| Cancellation tokens | ✅ Implemented |
| Permission gates | ✅ Implemented |
| Personality system prompts | ✅ Implemented |
| Query detector (`Agent/query_detector.py`) | ✅ Implemented |

### Gaps
- **Coupled to Ollama** — no provider abstraction layer. Swapping to OpenAI, Claude, or a different backend requires code changes.
- Agent interface (`Agent/chat_handler.py`) is not published as an external API / SDK.

---

## 3. Desktop Application Control — ~85%

Handled by `QuikTieper/` and `SeeOnDesk/`.

| Capability | Module | Status |
|-----------|--------|--------|
| Keyboard chord detection & shortcut binding | `QuikTieper/` | ✅ |
| App launching via launcher | `QuikTieper/` | ✅ |
| Pointer movement & clicks | `QuikTieper/` | ✅ |
| Desktop app listing | `QuikTieper/desktop_apps.py` | ✅ |
| Remote action execution | `QuikTieper/` | ✅ |
| Focused window detection | `SeeOnDesk/` | ✅ |
| Workspace tracking | `SeeOnDesk/` | ✅ |
| Process monitoring | `SeeOnDesk/` | ✅ |

### Gaps
- No programmatic control **within** applications (e.g., no API to interact with app menus, no window manipulation beyond focus detection)
- Controls *what runs* and *where the pointer goes*, but not *what the app does internally*

---

## 4. Browser Control — ~20%

**Weakest area.** Fiona has virtually no browser automation capability.

| Capability | Status |
|-----------|--------|
| Browser automation (Selenium, Playwright, CDP) | ❌ Not implemented |
| Browser extension | ❌ Not implemented |
| Tab management | ❌ Not implemented |
| Page navigation | ❌ Not implemented |
| DOM interaction | ❌ Not implemented |
| Launch browser via QuikTieper | ✅ (but only launches, no control) |

### What's needed for full browser control
- Headless/headed browser automation engine (Playwright recommended)
- Page navigation, form filling, data extraction
- Session and cookie management
- Screenshot / PDF capture

---

## 5. System Function Control — ~90%

The most mature area of the platform.

| Module | Capability | Status |
|--------|-----------|--------|
| `FionaCore/actions.py` | Execute system commands via action registry | ✅ |
| `FionaCore/shell_safety.py` | Whitelist/blacklist shell commands | ✅ |
| `FionaCore/permissions.py` | Permission prompts & verification | ✅ |
| `FionaCore/macros.py` | Macro recording & playback | ✅ |
| `FionaCore/voice.py` | Speech synthesis | ✅ |
| `FionaCore/notifications.py` | Desktop notifications | ✅ |
| `Voice/` | Wake word, push-to-talk, audio feedback | ✅ |
| `TerminalAssist/` | Terminal dashboard, Zellij workspace control | ✅ |
| `CamComs/` | Encrypted communication / device pairing | ✅ |
| `RecallVault/` | Persistent key/value storage | ✅ |
| `CmdTrace/` | High-performance JSONL observability log | ✅ |

### Gaps
- No power management (suspend/hibernate)
- No file system abstraction layer
- No clipboard API beyond what the OS provides

---

## 6. Standardized Interface — ~60%

The current interface is primarily Python import-based. There is no language-agnostic API.

| Interface | Status |
|-----------|--------|
| `fiona` CLI dispatcher | ✅ Stable entry point |
| `FionaCore/actions.py` action registry | ✅ Structured but Python-only |
| `Agent/` command registry | ✅ Agent-facing command catalog |
| ACL / permissions layer | ✅ Security interface defined |
| REST API | ❌ Not implemented |
| gRPC / WebSocket API | ❌ Not implemented |
| JSON-RPC / message bus | ❌ Not implemented |
| Schema-defined command protocol | ❌ Not implemented |
| Client SDK for non-Python agents | ❌ Not implemented |

---

## Overall Score

| Dimension | Score |
|-----------|-------|
| Middleware Platform | 80% |
| AI Agent Enablement | 75% |
| Desktop App Control | 85% |
| Browser Control | 20% |
| System Function Control | 90% |
| Standardized Interface | 60% |
| **Overall** | **~68%** |

---

## Recommended Roadmap to 100%

### High-impact, low-effort
1. **Agent provider abstraction** — Decouple `Agent/chat_handler.py` from Ollama by adding a provider interface (OpenAI-compatible API wrapper already partially there).
2. **Local HTTP/WebSocket server** — Expose FionaCore actions over a simple FastAPI or Unix socket server so non-Python agents can call them.

### High-impact, moderate-effort
3. **Browser automation integration** — Add Playwright or CDP support. This alone fills the biggest gap. A `fiona browser` CLI subcommand with navigation, search, and data extraction.
4. **Browser extension** — Create a companion extension that Fiona can communicate with for deeper browser integration.

### Lower-impact, nice-to-have
5. **Schema-defined protocol** — Define a JSON-Schema or OpenAPI spec for all actions/commands.
6. **Power management** — Suspend, hibernate, shutdown controls.
7. **File system abstraction** — Read/write/search files through the middleware.
8. **Clipboard API** — Programmatic clipboard read/write.

---

## Key Strengths to Preserve

- **Modular architecture** — 13 sibling sub-packages that can be developed independently
- **Security-first design** — ACL, shell safety, encrypted communication, permission prompts
- **Observability** — CmdTrace provides a unified JSONL audit log for every routed action
- **CLI-first** — All functionality accessible via `fiona <subcommand>`
- **Extensibility** — Macro engine, action registry, personality system all support plugins