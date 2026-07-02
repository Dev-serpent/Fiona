# Architecture Review: Browser Automation + 3js CAD Frontend

> **Review Date:** 2026-06-22  
> **Scope:** Full critical evaluation of the proposed implementation roadmap  
> **Status:** Draft for engineering team review  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Validation](#2-architecture-validation)
3. [Subsystem Interface Contracts](#3-subsystem-interface-contracts)
4. [Lifecycle State Machines](#4-lifecycle-state-machines)
5. [Error Handling & Recovery](#5-error-handling--recovery)
6. [Abstraction Layers](#6-abstraction-layers)
7. [Dependency Injection & IoC](#7-dependency-injection--ioc)
8. [Event-Driven Architecture](#8-event-driven-architecture)
9. [Extension Points & Plugin Architecture](#9-extension-points--plugin-architecture)
10. [Performance Targets](#10-performance-targets)
11. [Observability Strategy](#11-observability-strategy)
12. [Coding Standards & Conventions](#12-coding-standards--conventions)
13. [Frontend-Backend Protocol Specification](#13-frontend-backend-protocol-specification)
14. [State Synchronization Strategy](#14-state-synchronization-strategy)
15. [Architecture Decision Records](#15-architecture-decision-records)
16. [Testing Strategy](#16-testing-strategy)
17. [Scope, Assumptions & Non-Goals](#17-scope-assumptions--non-goals)
18. [Revised Milestone Structure](#18-revised-milestone-structure)

---

## 1. Executive Summary

### Overall Assessment

The proposed roadmap is **architecturally sound in direction** but **insufficiently rigorous for production** in its current form. The core insight — separating the CAD kernel from the frontend via a JSON bridge, and wrapping browser automation in a dedicated package — is correct. However, the design contains several architectural weaknesses that will produce significant technical debt if not addressed before implementation begins.

### Critical Issues Found

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | Singleton `BrowserSession` with no lifecycle management | **High** | Leaked browser processes, no crash recovery, untestable |
| 2 | No abstraction over browser provider | **High** | Locked into Playwright; swapping to CDP or Selenium requires rewrite |
| 3 | Async wrapper in synchronous CLI | **High** | Event loop conflicts, thread-safety bugs, poor error propagation |
| 4 | CAD server is a single-document monolith | **High** | Cannot support multi-document workflows; no isolation |
| 5 | No formal frontend-backend protocol | **High** | Brittle version coupling, no capability negotiation, no graceful degradation |
| 6 | HTTP server on localhost with zero security | **Medium** | Any local process can execute arbitrary CAD commands |
| 7 | Full-state sync on every operation | **Medium** | Scales poorly with document complexity; network becomes bottleneck |
| 8 | No observability | **Medium** | Production debugging impossible; no metrics, tracing, or structured logging |
| 9 | No error recovery strategy | **Medium** | Crashes leave orphaned browser processes and corrupted documents |
| 10 | No dependency injection | **Medium** | All subsystems are hard-wired; unit testing requires mocking globals |
| 11 | No plugin architecture | **Low-Medium** | CAD primitives, exporters, and browser providers are hard-coded |
| 12 | Electron vs. browser decision deferred | **Low** | Architecture depends on this choice; deferral causes rework |

### Recommended Action

**Adopt the revised architecture in Section 2 before writing implementation code.** The changes are primarily in interface design, dependency management, and lifecycle handling — they do not invalidate the milestone structure or the general approach, but they reorder and reframe tasks to build a solid foundation.

---

## 2. Architecture Validation

### 2.1 Current Proposed Architecture (as per roadmap)

```
┌─────────────────────────────┐   ┌──────────────────────────────┐
│    BrowserAutomation/       │   │   CAD Python Server          │
│  ┌───────────────────────┐  │   │  ┌────────────────────────┐  │
│  │  BrowserSession       │  │   │  │  Single Document       │  │
│  │  (Singleton)          │  │   │  │  HTTP/WS Server        │  │
│  │  sync_wrappers()      │  │   │  │  REST endpoints        │  │
│  └───────────────────────┘  │   │  └────────────────────────┘  │
│  ┌───────────────────────┐  │   │         │                    │
│  │  navigation.py         │  │   │  ┌──────┴──────────┐        │
│  │  interaction.py        │  │   │  │  CAD Kernel      │        │
│  │  extraction.py         │  │   │  │  (cad/core,      │        │
│  │  screenshot.py         │  │   │  │   cad/geometry,  │        │
│  └───────────────────────┘  │   │  │   cad/commands)  │        │
└─────────────────────────────┘   │  └─────────────────┘        │
                                  └──────────────────────────────┘
                                           │ JSON over HTTP/WS
                                  ┌────────┴────────┐
                                  │  3js Frontend    │
                                  │  (Electron/Web)  │
                                  └─────────────────┘
```

### 2.2 Identified Architectural Weaknesses

#### Weakness 1: Singleton BrowserSession

**Problem:** The roadmap specifies a `BrowserSession` singleton accessed via `get_instance()`. This creates:
- **No isolation** — all CLI commands, agent calls, and remote actions share one browser. A failed navigation in one context affects all.
- **No lifecycle** — if the browser crashes, the singleton is dead. No auto-restart.
- **No multi-identity** — cannot maintain separate browser profiles (e.g., personal vs. work).
- **Untestable** — shared global state makes parallel test execution impossible.

**Solution:** Replace with a `BrowserManager` that owns a pool of `BrowserContext` objects.

#### Weakness 2: No Browser Provider Abstraction

**Problem:** `BrowserSession` directly imports Playwright. If we later want:
- Chrome DevTools Protocol (CDP) directly
- Selenium WebDriver
- A cloud browser service (BrowserStack, LambdaTest)
- A headless Chrome via subprocess

...the entire package must be rewritten.

**Solution:** Define a `BrowserProvider` ABC that the rest of the system depends on. Playwright is one implementation.

#### Weakness 3: Sync Wrappers Around Async API

**Problem:** The plan calls for synchronous CLI handlers that call `asyncio.run()` on Playwright's async API. This:
- Fails if there's already an event loop in the thread
- Blocks the thread for the duration of every browser operation
- Makes cancellation impossible
- Prevents concurrent browser operations

**Solution:** The `BrowserAutomation` package exposes an async API internally. CLI handlers use a dedicated event loop managed by the `BrowserManager`. Agent integration uses async dispatch.

#### Weakness 4: Single-Document CAD Server

**Problem:** The CAD server holds exactly one `Document` instance in memory. This:
- Prevents comparing two documents side by side
- Makes "revert to saved" require re-loading from disk
- Creates ambiguity when multiple frontends connect (whose document is live?)
- Prevents background processing (e.g., exporting one document while editing another)

**Solution:** A `DocumentManager` that maps UUIDs to documents. The protocol includes a `document_id` in every request.

#### Weakness 5: No Formal Protocol

**Problem:** Ad hoc REST endpoints with no versioning, schema, or capability negotiation.

**Solution:** A formal JSON-RPC 2.0 based protocol with versioning, capability discovery, and typed error codes (see Section 13).

#### Weakness 6: No Access Control on Localhost

**Problem:** Running an HTTP server on localhost with no authentication means any local process (or XSS-vulnerable web page) can execute arbitrary CAD commands, read/open any file the user has access to, and exfiltrate document data.

**Solution:** Origin-based CSRF protection, a bearer token exchanged at connection time, and command-scoped authorization.

### 2.3 Revised Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Fiona Process                                │
│                                                                     │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │    BrowserAutomation/       │  │   CAD/                       │  │
│  │                             │  │                              │  │
│  │  ┌───────────────────────┐  │  │  ┌────────────────────────┐  │  │
│  │  │ BrowserManager        │  │  │  │ DocumentManager        │  │  │
│  │  │  ┌───────────────┐    │  │  │  │  ┌──────────┐         │  │  │
│  │  │  │ BrowserPool   │    │  │  │  │  │ Document │         │  │  │
│  │  │  │ ┌───────────┐ │    │  │  │  │  │ (active) │         │  │  │
│  │  │  │ │ Context 1 │ │    │  │  │  │  └──────────┘         │  │  │
│  │  │  │ │ Context 2 │ │    │  │  │  │  ┌──────────┐         │  │  │
│  │  │  │ └───────────┘ │    │  │  │  │  │ Document │         │  │  │
│  │  │  └───────────────┘    │  │  │  │  │ (backgd) │         │  │  │
│  │  │  provider: IProvider  │  │  │  │  └──────────┘         │  │  │
│  │  └───────────────────────┘  │  │  └────────────────────────┘  │  │
│  │                             │  │                              │  │
│  │  ┌───────────────────────┐  │  │  ┌────────────────────────┐  │  │
│  │  │ SessionManager        │  │  │  │ CommandExecutor        │  │  │
│  │  │ (one per CLI/Agent)   │  │  │  │ (undo/redo stack per   │  │  │
│  │  └───────────────────────┘  │  │  │  document)             │  │  │
│  │                             │  │  └────────────────────────┘  │  │
│  └─────────────────────────────┘  │                              │  │
│                                   │  ┌────────────────────────┐  │  │
│  ┌─────────────────────────────┐  │  │ ExportManager          │  │  │
│  │ EventBus (pub/sub)          │──│──│ (provider-based)       │  │  │
│  └─────────────────────────────┘  │  └────────────────────────┘  │  │
│                                   └──────────────────────────────┘  │
│                                            │                        │
│  ┌─────────────────────────────┐           │ JSON-RPC 2.0 over WS   │
│  │  FionaLog (structured       │  ┌────────┴────────┐               │
│  │   logging + metrics)        │  │  Server         │               │
│  └─────────────────────────────┘  │  (aiohttp or    │               │
│                                   │   FastAPI)      │               │
│  ┌─────────────────────────────┐  └────────┬────────┘               │
│  │  Health/Status API          │           │                        │
│  └─────────────────────────────┘  ┌────────┴────────┐               │
│                                   │  3js Frontend    │               │
│                                   │  (Vite + 3js    │               │
│                                   │   + React/Vue)  │               │
│                                   └─────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.4 Key Architectural Principles

| Principle | Application |
|---|---|
| **Program to interfaces, not implementations** | All providers (browser, renderer, export, primitive) use ABCs |
| **Dependency inversion** | High-level modules depend on abstractions; concrete implementations are injected |
| **Single responsibility** | Each class has exactly one concern (e.g., `BrowserManager` manages lifecycle, `BrowserContext` wraps a single context) |
| **Explicit lifecycle** | Every resource has a `start/stop/pause/resume` cycle with defined state transitions |
| **Fail closed** | On any error, systems degrade to safe defaults rather than undefined behavior |
| **Observability by default** | Every operation produces structured logs, metrics, and traces |

---

## 3. Subsystem Interface Contracts

### 3.1 BrowserAutomation

#### `IBrowserProvider` — Abstract Browser Backend

```python
class IBrowserProvider(ABC):
    """Interface for browser automation backends."""

    @abstractmethod
    async def launch(self, config: BrowserConfig) -> IBrowserInstance:
        """Launch a browser instance. Raises BrowserLaunchError on failure."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Provider identifier, e.g. 'selenium', 'cdp'."""
        ...

    @abstractmethod
    def capabilities(self) -> set[str]:
        """Set of supported features, e.g. {'screenshot', 'pdf', 'network_intercept', 'js_eval'}."""
        ...
```

#### `IBrowserInstance` — Running Browser

```python
class IBrowserInstance(ABC):
    """A running browser process."""

    @abstractmethod
    async def create_context(self, *, incognito: bool = True,
                             viewport: ViewportConfig | None = None) -> IBrowserContext:
        """Create an isolated browser context (akin to an incognito profile)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Kill the browser process. Idempotent. Raises BrowserShutdownError on failure."""
        ...

    @property
    @abstractmethod
    def is_closed(self) -> bool: ...

    @property
    @abstractmethod
    def pid(self) -> int | None: ...
```

#### `IBrowserContext` — Isolated Session

```python
class IBrowserContext(ABC):
    """An isolated browser session (cookies, storage, auth)."""

    @abstractmethod
    async def navigate(self, url: str, *, timeout: float = 30.0,
                       wait_until: NavigationEvent = "load") -> NavigationResult:
        """Navigate to URL. Raises NavigationTimeout, NavigationError."""
        ...

    @abstractmethod
    async def click(self, selector: str, *, timeout: float = 5.0) -> None:
        """Click element matching CSS selector. Raises SelectorTimeout, ElementNotFound."""
        ...

    @abstractmethod
    async def type_text(self, selector: str, text: str, *,
                        delay: float = 0.01, timeout: float = 5.0) -> None:
        """Type text into element. Raises SelectorTimeout, ElementNotInteractable."""
        ...

    @abstractmethod
    async def get_text(self, selector: str, *, timeout: float = 5.0) -> str:
        """Get text content of element. Raises SelectorTimeout."""
        ...

    @abstractmethod
    async def screenshot(self, *, path: str | None = None,
                         full_page: bool = False) -> bytes:
        """Capture screenshot. Returns PNG bytes if path is None."""
        ...

    @abstractmethod
    async def evaluate(self, js: str, *,
                       timeout: float = 5.0) -> Any:
        """Execute JavaScript in page context. Raises ScriptExecutionError."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close context. Idempotent."""
        ...

    @property
    @abstractmethod
    def is_closed(self) -> bool: ...

    @property
    @abstractmethod
    def context_id(self) -> str: ...
```

#### `BrowserManager` — Lifecycle Owner

```python
class BrowserManager:
    """Manages browser lifecycle, provider selection, and context pooling.

    Thread-safety: All public methods are thread-safe via asyncio lock.
    State ownership: Owns all IBrowserInstance and IBrowserContext objects.
    """

    def __init__(self, provider: IBrowserProvider,
                 config: BrowserConfig,
                 event_bus: EventBus | None = None):
        self._provider = provider
        self._config = config
        self._event_bus = event_bus
        self._instance: IBrowserInstance | None = None
        self._lock = asyncio.Lock()
        self._state = BrowserManagerState.STOPPED

    async def start(self) -> None:
        """Launch browser. Raises BrowserLaunchError."""

    async def stop(self, *, force: bool = False) -> None:
        """Stop browser and all contexts. Idempotent."""

    async def create_context(self, **kwargs) -> IBrowserContext:
        """Create a new isolated context. Raises BrowserNotRunning."""

    async def restart(self) -> None:
        """Stop and start again. Useful for crash recovery."""

    @property
    def state(self) -> BrowserManagerState: ...

    @property
    def provider_name(self) -> str: ...
```

#### `BrowserManagerState` — Lifecycle Enum

```python
class BrowserManagerState(Enum):
    STOPPED = "stopped"          # Initial state, not started
    STARTING = "starting"        # Launch in progress
    RUNNING = "running"          # Healthy, accepting commands
    DEGRADED = "degraded"        # Running but with errors (e.g., one context crashed)
    STOPPING = "stopping"        # Shutdown in progress
    ERROR = "error"              # Unrecoverable error, manual restart required
```

#### Data Types

```python
@dataclass(frozen=True)
class BrowserConfig:
    browser_type: str = "chromium"     # chromium, firefox, webkit
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    data_dir: str | None = None        # Persistent profile directory
    proxy: str | None = None
    args: tuple[str, ...] = ()

@dataclass(frozen=True)
class NavigationResult:
    url: str
    status_code: int
    title: str
    duration_ms: float
    redirect_chain: tuple[str, ...]

class NavigationEvent(Enum):
    LOAD = "load"              # Full page load
    DOM_CONTENT = "domcontentloaded"
    NETWORK_IDLE = "networkidle"

# Error hierarchy
class BrowserError(Exception): ...
class BrowserLaunchError(BrowserError): ...
class BrowserNotRunning(BrowserError): ...
class BrowserShutdownError(BrowserError): ...
class BrowserTimeout(BrowserError): ...
class NavigationTimeout(BrowserTimeout): ...
class SelectorTimeout(BrowserTimeout): ...
class ElementNotFound(BrowserError): ...
class ElementNotInteractable(BrowserError): ...
class ScriptExecutionError(BrowserError): ...
class BrowserCrashError(BrowserError): ...
```

### 3.2 CAD Document Server

#### `IDocumentManager` — Document Registry

```python
class IDocumentManager(ABC):
    """Manages multiple CAD documents."""

    @abstractmethod
    def create_document(self, name: str = "Untitled") -> DocumentHandle:
        """Create a new empty document. Returns handle with UUID."""
        ...

    @abstractmethod
    def open_document(self, path: str) -> DocumentHandle:
        """Load a .cad file. Raises DocumentLoadError, DocumentNotFound."""
        ...

    @abstractmethod
    def save_document(self, doc_id: str, path: str | None = None) -> str:
        """Save document. Returns the path saved to. Raises DocumentSaveError."""
        ...

    @abstractmethod
    def get_document(self, doc_id: str) -> Document | None:
        """Get document by ID. Returns None if not found."""
        ...

    @abstractmethod
    def close_document(self, doc_id: str) -> None:
        """Close document. Raises DocumentNotOpen if already closed."""
        ...

    @abstractmethod
    def list_documents(self) -> list[DocumentHandle]:
        """List all open documents."""
        ...

    @abstractmethod
    def active_document(self) -> Document | None:
        """Get the currently active (frontmost) document."""
        ...
```

#### `DocumentHandle` — Lightweight Reference

```python
@dataclass(frozen=True)
class DocumentHandle:
    doc_id: str               # UUID
    name: str
    path: str | None          # Saved path, None if unsaved
    object_count: int
    is_modified: bool
    created_at: float
    modified_at: float
```

#### `ICommandExecutor` — Command Dispatch

```python
class ICommandExecutor(ABC):
    """Executes commands against a document with undo/redo tracking."""

    @abstractmethod
    def execute(self, doc_id: str, command_name: str,
                **kwargs: Any) -> CommandResult:
        """Execute command. Mutates document. Raises CommandError, DocumentNotOpen."""
        ...

    @abstractmethod
    def undo(self, doc_id: str) -> DocumentSnapshot:
        """Undo last operation. Raises NothingToUndo."""
        ...

    @abstractmethod
    def redo(self, doc_id: str) -> DocumentSnapshot:
        """Redo next operation. Raises NothingToRedo."""
        ...

    @abstractmethod
    def can_undo(self, doc_id: str) -> bool: ...

    @abstractmethod
    def can_redo(self, doc_id: str) -> bool: ...

    @abstractmethod
    def clear_history(self, doc_id: str) -> None: ...

@dataclass(frozen=True)
class CommandResult:
    success: bool
    message: str
    document_snapshot: dict   # Full to_dict() snapshot
    created_objects: list[str]   # UIDs of newly created objects
    modified_objects: list[str]  # UIDs of modified objects
    deleted_objects: list[str]   # UIDs of deleted objects
    execution_time_ms: float
    warnings: list[str]

# Error hierarchy
class CommandError(Exception): ...
class CommandNotFound(CommandError): ...
class InvalidArguments(CommandError): ...
class DocumentNotOpen(CommandError): ...
class NothingToUndo(CommandError): ...
class NothingToRedo(CommandError): ...
class DocumentLoadError(CommandError): ...
class DocumentSaveError(CommandError): ...
```

#### `IExportProvider` — Export Abstraction

```python
class IExportProvider(ABC):
    """Export a document to a specific format."""

    @abstractmethod
    def format_name(self) -> str:
        """e.g. 'stl', 'obj', 'svg', 'step'."""
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """e.g. ['.stl', '.STL']."""
        ...

    @abstractmethod
    def export(self, doc: Document, path: str,
              **options: Any) -> ExportResult:
        """Export document to file. Raises ExportError."""
        ...

@dataclass(frozen=True)
class ExportResult:
    path: str
    format: str
    size_bytes: int
    duration_ms: float
    warnings: list[str]

class ExportError(Exception): ...
```

### 3.3 EventBus — Cross-Cutting Pub/Sub

```python
class EventBus:
    """In-process publish/subscribe event bus.

    Thread-safety: All methods are thread-safe.
    No ordering guarantees between subscribers of the same event.
    """

    def subscribe(self, event_type: type[Event],
                  callback: Callable[[Event], None]) -> Subscription:
        """Register a subscriber. Returns Subscription token for unsubscribe."""

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a subscriber. Idempotent."""

    def publish(self, event: Event) -> None:
        """Publish event to all subscribers. Non-blocking (fire-and-forget)."""

    def publish_and_wait(self, event: Event, timeout: float = 5.0) -> None:
        """Publish and wait for all subscribers to complete. Raises TimeoutError."""

@dataclass
class Subscription:
    event_type: type
    callback_id: str

# Event hierarchy
class Event:
    timestamp: float
    source: str

class DocumentEvent(Event):
    doc_id: str

class DocumentCreated(DocumentEvent): ...
class DocumentModified(DocumentEvent): ...
class DocumentSaved(DocumentEvent): ...
class DocumentClosed(DocumentEvent): ...
class ObjectSelected(DocumentEvent):
    uid: str | None

class BrowserEvent(Event):
    context_id: str

class BrowserLaunched(BrowserEvent): ...
class BrowserCrashed(BrowserEvent):
    reason: str
class BrowserContextCreated(BrowserEvent): ...
class BrowserContextClosed(BrowserEvent): ...
class NavigationCompleted(BrowserEvent):
    url: str
    status: int
```

### 3.4 Server Protocol Messages

See Section 13 for the full protocol specification. Key message types:

```python
# Request/Response (JSON-RPC 2.0)
@dataclass
class RpcRequest:
    jsonrpc: str = "2.0"
    id: str                  # UUID
    method: str              # e.g. "document.execute_command"
    params: dict

@dataclass
class RpcResponse:
    jsonrpc: str = "2.0"
    id: str                  # Correlates to request
    result: Any | None       # Present on success
    error: RpcError | None   # Present on failure

@dataclass
class RpcError:
    code: int                # Standard JSON-RPC codes + custom
    message: str
    data: dict | None

# Notifications (no response expected)
@dataclass
class RpcNotification:
    jsonrpc: str = "2.0"
    method: str
    params: dict

# Events pushed from server to client
@dataclass
class ServerEvent:
    type: str                # "document_updated", "object_selected", etc.
    data: dict
    timestamp: float
```

---

## 4. Lifecycle State Machines

### 4.1 BrowserManager Lifecycle

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        v                                             │
  ┌─────────┐   start()   ┌──────────┐   on_launch   ┌─────────┐
  │ STOPPED │─────────────>│ STARTING │──────────────>│ RUNNING │
  └─────────┘              └──────────┘               └────┬────┘
        ^                                                    │
        │                    ┌──────────┐                   │
        │  stop()            │ STOPPING │<───────────────────┤
        └────────────────────│          │   stop()           │
                             └──────────┘                   │
        ┌─────────┐              │                          │
        │  ERROR  │<─────────────┘                          │
        └─────────┘   crash detected                        │
              ^                                              │
              │         ┌──────────┐                        │
              └─────────│ DEGRADED │<────────────────────────┤
                  retry  └──────────┘  context_crash(s)     │
                    succeeds            but browser alive    │
                                                        restart()
```

**State transitions:**

| From | To | Trigger | Action |
|---|---|---|---|
| `STOPPED` | `STARTING` | `start()` | Acquire lock, call `provider.launch()` |
| `STARTING` | `RUNNING` | Launch success | Set instance, publish `BrowserLaunched` |
| `STARTING` | `ERROR` | Launch failure | Publish error, set state, raise to caller |
| `RUNNING` | `DEGRADED` | Context crash (browser alive) | Create replacement context, publish warning |
| `RUNNING` | `STOPPING` | `stop()` | Close all contexts, close instance |
| `DEGRADED` | `RUNNING` | Auto-recovery | New context created successfully |
| `DEGRADED` | `ERROR` | Browser process exit detected | Attempt `restart()` once |
| `DEGRADED` | `STOPPING` | `stop()` | Normal shutdown |
| `ERROR` | `STOPPING` | `stop()` | Force-close zombie processes |
| `STOPPING` | `STOPPED` | All resources closed | Cleanup complete |
| Any | `ERROR` | Unhandled exception | Catch, log, clean up, set state |

### 4.2 CAD Document Lifecycle

```
  ┌──────────┐  create    ┌──────────┐  first edit   ┌────────────┐
  │ NOT_SAVED │──────────>│  CLEAN   │──────────────>│  MODIFIED  │
  └───────────┘           └──────────┘               └─────┬──────┘
                                                           │
                                                           │ save()
                                                           v
                                                      ┌──────────┐
                                                      │  CLEAN   │
                                                      └──────────┘
  ┌───────────┐  close()   ┌──────────┐
  │  CLOSED   │<───────────│  ANY     │
  └───────────┘            └──────────┘

  Transient states:
  ┌───────────┐
  │  LOADING  │──→ CLEAN (on success) | CLOSED (on error)
  └───────────┘
  ┌───────────┐
  │  SAVING   │──→ CLEAN (on success) | MODIFIED (on error)
  └───────────┘
```

### 4.3 Frontend Connection Lifecycle

```
  ┌──────────┐  WS connect   ┌──────────┐  handshake   ┌──────────┐
  │ DISCONN. │──────────────>│CONNECTING│─────────────>│CONNECTED │
  └──────────┘               └──────────┘              └────┬─────┘
       ^                                                      │
       │                                                      │
       │  WS close/timeout    ┌──────────┐  failed heartbeat │
       └──────────────────────│RECONNECT │<───────────────────┘
                              │ (backoff)│
                              └────┬─────┘
                                   │
                          max_retries exceeded
                                   │
                              ┌────┴─────┐
                              │  OFFLINE  │
                              │ (read-only│
                              │  cache)   │
                              └──────────┘
```

**Reconnection policy:** Exponential backoff with jitter. Start at 1s, double each attempt, cap at 30s. Max 10 retries, then enter `OFFLINE` mode.

---

## 5. Error Handling & Recovery

### 5.1 Retry Policies

```python
@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError, TimeoutError, BrowserTimeout
    )
    on_retry: Callable[[int, Exception], None] | None = None
```

**Applied to:**

| Operation | Policy | Rationale |
|---|---|---|
| Browser launch | 3 retries, 2s base | Browser may need multiple attempts |
| Page navigation | 2 retries, 1s base | Transient network failures |
| Document save | 3 retries, 1s base | File system contention |
| WebSocket connect | Exponential 1-30s, 10 max | Server may be starting up |
| Command execution | No retry | Commands are not idempotent |

### 5.2 Timeout Behavior

| Operation | Default Timeout | Configurable | Behavior on Timeout |
|---|---|---|---|
| Browser launch | 30s | Yes | Raise `BrowserLaunchTimeout`, set state to ERROR |
| Page navigation | 30s | Yes | Raise `NavigationTimeout`, page may be in undefined state |
| Click | 5s | Yes | Raise `SelectorTimeout` |
| Text type | 5s | Yes | Raise `SelectorTimeout` |
| Command execution | 60s | Yes | Raise `CommandTimeout`, document state undefined |
| Document save | 30s | Yes | Raise `DocumentSaveError`, document still in memory |
| Export | 120s | Yes | Raise `ExportError` |
| WebSocket response | 10s | Yes | Treat as disconnected, attempt reconnect |

### 5.3 Crash Recovery

#### Browser Crash

```python
# BrowserManager detects crash via:
# 1. Process exit notification from Playwright
# 2. Healthy heartbeat timeouts
# 3. Context operations raising BrowserCrashError

async def _on_browser_crash(self, reason: str) -> None:
    self._logger.error("Browser crashed", reason=reason, pid=self._instance.pid)
    self._event_bus.publish(BrowserCrashed(reason=reason))

    # Attempt automatic restart once
    try:
        self._state = BrowserManagerState.STOPPING
        await self._cleanup_zombie_processes()
        self._state = BrowserManagerState.STARTING
        await self._provider.launch(self._config)
        self._state = BrowserManagerState.RUNNING
        self._logger.info("Browser auto-restarted successfully")
        self._event_bus.publish(BrowserLaunched())
    except Exception as e:
        self._state = BrowserManagerState.ERROR
        self._logger.error("Auto-restart failed", error=str(e))
        # Notify all pending operations with CrashError
        self._fail_pending_operations(BrowserCrashError(reason))
```

#### CAD Server Crash

```python
# DocumentManager saves periodic auto-recovery snapshots
async def _auto_save_recovery(self, interval_s: int = 60) -> None:
    while self._running:
        await asyncio.sleep(interval_s)
        for doc_id, doc in self._documents.items():
            if doc.is_modified:
                recovery_path = self._recovery_dir / f"{doc_id}.autocad"
                CadSerializer.serialize_to_file(doc, recovery_path)
                self._logger.debug("Auto-recovery saved", doc_id=doc_id,
                                   path=str(recovery_path))
```

### 5.4 Resource Cleanup Guarantees

```python
class ResourceGuard:
    """Context manager ensuring resource cleanup even on exceptions."""

    def __init__(self, resource_name: str, cleanup: Callable[[], Awaitable[None]]):
        self._name = resource_name
        self._cleanup = cleanup
        self._closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                await self._cleanup()
            except Exception as e:
                logger.error("Resource cleanup failed",
                             resource=self._name, error=str(e))

# Usage:
async with ResourceGuard("browser-context-1", context.close):
    await context.navigate("https://example.com")
    await context.click("#button")
# Guaranteed: context.close() is called even if click raises
```

### 5.5 Graceful Degradation

| Degraded Condition | Behavior |
|---|---|
| No browser installed | `fiona browser status` shows "not available", suggest `pip install fiona[browser]` |
| CAD server port busy | Try next port, log warning, tell user `fiona ficad --port N` |
| WebSocket disconnected | Frontend shows "Connection lost — changes will be saved locally" banner, reconnects automatically |
| Export provider missing | Available formats listed dynamically; unknown format returns clear error with supported list |
| GPU unavailable for 3js | 3js falls back to WebGL software renderer (`renderer = new THREE.WebGLRenderer({ forceSoftwareRenderer: true })`) |
| File system read-only | Document operations succeed in memory; save attempts show clear "write protected" error |

---

## 6. Abstraction Layers

### 6.1 Browser Provider Abstraction

```
┌──────────────────────────────────────────────┐
│            IBrowserProvider                   │
│  (abstract interface, depends on nothing)     │
├──────────────────────────────────────────────┤
│ launch(config) → IBrowserInstance             │
│ name() → str                                 │
│ capabilities() → set[str]                    │
└──────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
┌────────┴───────┐  ┌────────┴───────┐  ┌────────┴───────┐
│ Playwright     │  │ CDPProvider    │  │ Selenium       │
│ Provider       │  │ (chrome-       │  │ Provider       │
│                │  │  devtools-     │  │ (future)       │
│ pip install    │  │  protocol)     │  │                │
│ fiona[browser] │  │ no extra deps  │  │ pip install    │
└────────────────┘  └────────────────┘  │ fiona[selenium]│
                                        └────────────────┘
```

**Why this matters:** If Playwright has a breaking change, or if a user prefers a different backend, the rest of the system is unaffected. The `BrowserManager` only knows about `IBrowserProvider`.

### 6.2 Export Provider Abstraction

```
┌──────────────────────────────────────┐
│          IExportProvider              │
├──────────────────────────────────────┤
│ format_name() → str                  │
│ supported_extensions() → list[str]   │
│ export(doc, path, **options)         │
└──────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
┌────────┴───────┐  ┌────────┴───────┐  ┌────────┴───────┐
│ StlExport      │  │ ObjExport      │  │ StepExport     │
│ Provider       │  │ Provider       │  │ Provider       │
│ (built-in)     │  │ (built-in)     │  │ (community)    │
│ cad/io/        │  │ cad/io/        │  │ cad/plugins/   │
│ export_stl.py  │  │ export_obj.py  │  │                │
└────────────────┘  └────────────────┘  └────────────────┘
```

**Registration pattern:**

```python
# In cad/io/__init__.py or a registry
class ExportManager:
    def __init__(self):
        self._providers: dict[str, IExportProvider] = {}

    def register(self, provider: IExportProvider) -> None:
        self._providers[provider.format_name()] = provider

    def get(self, format_name: str) -> IExportProvider:
        if format_name not in self._providers:
            raise ExportError(f"Unsupported format: {format_name}. "
                              f"Supported: {list(self._providers.keys())}")
        return self._providers[format_name]

    def list_formats(self) -> list[str]:
        return list(self._providers.keys())

# Built-in registration in server startup:
export_manager.register(StlExportProvider())
export_manager.register(ObjExportProvider())
export_manager.register(SvgExportProvider())
# Community plugins can call export_manager.register() at startup
```

### 6.3 Primitive Provider Abstraction

Future-proofing for community-contributed primitives:

```python
class IPrimitiveFactory(ABC):
    """Creates CAD objects from type names."""

    @abstractmethod
    def create(self, type_name: str, name: str, **kwargs) -> CADObject:
        """Create a primitive. Raises UnknownPrimitiveError."""
        ...

    @abstractmethod
    def list_types(self) -> list[PrimitiveTypeInfo]:
        """List available primitive types with metadata for UI."""
        ...

@dataclass(frozen=True)
class PrimitiveTypeInfo:
    type_name: str
    display_name: str
    category: str                # "3D", "2D", "Sketch", "Feature"
    icon: str | None
    default_properties: dict     # For auto-generating creation dialogs
    description: str
```

### 6.4 CAD Renderer Abstraction

```python
class ICadRenderer(ABC):
    """Abstract viewport renderer. Could be 3js, SVG, or terminal ASCII."""

    @abstractmethod
    def render(self, scene: SceneDescription) -> RenderOutput:
        """Render a scene description to the output format."""
        ...

    @abstractmethod
    def capabilities(self) -> set[str]:
        """e.g. {'wireframe', 'shading', 'selection_highlight', 'axes'}"""
        ...

@dataclass(frozen=True)
class SceneDescription:
    camera: CameraState
    objects: list[RenderObject]
    grid: GridConfig
    selection: list[str]           # UIDs of selected objects

@dataclass(frozen=True)
class RenderObject:
    uid: str
    type: str
    properties: dict
    transform: list[list[float]]   # 4x4 matrix

@dataclass(frozen=True)
class RenderOutput:
    format: str                    # "png", "svg", "json", "ascii"
    data: bytes | str
```

---

## 7. Dependency Injection & IoC

### 7.1 Problem with Current Design

The roadmap describes singletons (`BrowserSession.get_instance()`), direct imports (`from cad.core.document import Document`), and global state (`active_document()`). These are:
- **Untestable** — cannot substitute mocks for isolated tests
- **Brittle** — changing a dependency requires touching every consumer
- **Non-obvious** — which module holds which state is implicit

### 7.2 Proposed IoC Container

```python
# fiona/di.py — Central dependency injection container

from dataclasses import dataclass, field
from typing import Any

class FionaContainer:
    """Simple service container. Not a full DI framework — just enough to
    avoid global singletons while remaining pytest-friendly."""

    def __init__(self):
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable] = {}

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a concrete instance (e.g., EventBus, Config)."""
        self._services[name] = instance

    def register_factory(self, name: str, factory: Callable) -> None:
        """Register a factory (called once, result cached)."""
        self._factories[name] = factory

    def resolve(self, name: str) -> Any:
        """Resolve a service. Raises KeyError if not registered."""
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            instance = self._factories[name]()
            self._services[name] = instance  # Cache
            return instance
        raise KeyError(f"Service not registered: {name}")

# Application bootstrap (fiona/cli.py):
def build_production_container() -> FionaContainer:
    container = FionaContainer()
    container.register_instance("config", load_config())
    container.register_instance("event_bus", EventBus())
    container.register_factory("browser_provider",
                               lambda: PlaywrightProvider())
    container.register_factory("export_manager",
                               lambda: _build_export_manager())
    container.register_factory("document_manager",
                               lambda: DocumentManager(
                                   container.resolve("event_bus")))
    container.register_factory("command_executor",
                               lambda: LiveCommandExecutor(
                                   container.resolve("document_manager")))
    return container

def build_test_container() -> FionaContainer:
    container = FionaContainer()
    container.register_instance("config", TestConfig())
    container.register_instance("event_bus", EventBus())
    container.register_factory("browser_provider",
                               lambda: MockBrowserProvider())
    container.register_factory("export_manager",
                               lambda: MockExportManager())
    container.register_factory("document_manager",
                               lambda: InMemoryDocumentManager())
    container.register_factory("command_executor",
                               lambda: TestCommandExecutor(...))
    return container
```

### 7.3 What Gets Injected

| Service | Interface | Scope | Default Implementation |
|---|---|---|---|
| `config` | `FionaConfig` | Singleton | Load from `~/.config/fiona/config.json` |
| `event_bus` | `EventBus` | Singleton | In-process pub/sub |
| `browser_provider` | `IBrowserProvider` | Singleton | `PlaywrightProvider` |
| `export_manager` | `ExportManager` | Singleton | Default exporters |
| `document_manager` | `IDocumentManager` | Singleton | `SqliteDocumentManager` |
| `command_executor` | `ICommandExecutor` | Singleton | `LiveCommandExecutor` |
| `logger` | `FionaLogger` | Singleton | JSON file + stdout |
| `browser_manager` | `BrowserManager` | Singleton | Injected with provider + config |

---

## 8. Event-Driven Architecture

### 8.1 Why Events

Without events, subsystems must import each other directly to communicate:

```python
# Tight coupling (current pattern)
class BrowserManager:
    def on_crash(self):
        tray_icon.update_status("red")  # Direct import
        logger.warning("Browser crashed")  # Direct import
        notifier.send("Browser crashed")  # Direct import
```

With events:

```python
# Loose coupling (proposed)
class BrowserManager:
    def on_crash(self):
        self._event_bus.publish(BrowserCrashed(reason="..."))
        # No knowledge of who cares

class TrayIconUpdater:
    def __init__(self, event_bus):
        event_bus.subscribe(BrowserCrashed, self._on_browser_crash)
```

### 8.2 Event Flow Diagram

```
User clicks "Create Box" in frontend
  ↓
Frontend sends RPC: document.execute_command("create_box", {width:10})
  ↓
Server dispatches to CommandExecutor.execute()
  ↓
  ├── Pushes undo snapshot
  ├── Executes command (mutates Document)
  ├── Pushes redo snapshot
  ├── Publishes DocumentModified(doc_id, change_set)
  │     ↓
  │     ├── ExportManager (marks re-export needed)
  │     ├── TrayIconUpdater (updates modified indicator)
  │     ├── AutoSaveScheduler (reschedules background save)
  │     └── WebSocket publisher (pushes diff to frontend)
  │           ↓
  │           Frontend receives event, applies diff, re-renders
  └── Returns RPC response with full snapshot
```

### 8.3 Key Events

| Event | Publisher | Subscribers |
|---|---|---|
| `DocumentCreated` | DocumentManager | WS publisher, RecentFiles |
| `DocumentModified` | CommandExecutor | WS publisher, AutoSave, TrayIcon, StatusBar |
| `DocumentSaved` | DocumentManager | WS publisher, RecentFiles, StatusBar |
| `DocumentClosed` | DocumentManager | WS publisher, RecentFiles |
| `BrowserLaunched` | BrowserManager | TrayIcon, StatusBar |
| `BrowserCrashed` | BrowserManager | TrayIcon, Notifier, AutoRestart |
| `NavigationCompleted` | BrowserContext | Agent (for observation), CmdTrace |
| `ServerStarted` | Server | TrayIcon |
| `ServerStopping` | Server | All (graceful shutdown) |
| `ConnectionOpened` | WS Server | StatusBar |
| `ConnectionClosed` | WS Server | StatusBar |

---

## 9. Extension Points & Plugin Architecture

### 9.1 Plugin System (Reusing Existing Plugin Infrastructure)

The `cad/plugins/` directory already contains a plugin discovery and lifecycle system. This should be generalized and reused.

```python
# fiona/plugin_system.py
class PluginManager:
    """Discovers and loads plugins from configured directories."""

    def __init__(self, search_paths: list[str]):
        self._search_paths = search_paths
        self._plugins: dict[str, FionaPlugin] = {}

    def discover(self) -> list[PluginManifest]:
        """Scan search paths for plugin metadata files."""

    def load(self, plugin_name: str) -> FionaPlugin:
        """Load a plugin by name."""

    def load_all(self) -> list[FionaPlugin]:
        """Discover and load all plugins."""

    def unload(self, plugin_name: str) -> None:
        """Unload a previously loaded plugin."""

class FionaPlugin(ABC):
    """Base class for all Fiona plugins."""

    @abstractmethod
    def manifest(self) -> PluginManifest: ...

    @abstractmethod
    def activate(self, container: FionaContainer) -> None:
        """Register services, commands, providers."""
        ...

    @abstractmethod
    def deactivate(self) -> None:
        """Clean up resources."""
        ...
```

### 9.2 Extension Points Registry

| Extension Point | Interface | Example Plugins |
|---|---|---|
| Browser provider | `IBrowserProvider` | PlaywrightProvider, CDPProvider, SeleniumProvider |
| Export format | `IExportProvider` | STL, OBJ, SVG, STEP, IGES, Collada, glTF |
| Import format | `IImportProvider` | STEP, IGES, DXF, DWG, FreeCAD FCStd |
| CAD primitive | `IPrimitiveFactory` | Custom parametric shapes, lattice structures |
| CAD command | `cad.commands.Command` | Custom operations, measurement tools |
| Renderer backend | `ICadRenderer` | 3js, SVG, terminal, PDF |
| Agent personality | `Agent.personality.Personality` | Custom role definitions |
| Macro step type | `MacroStep` extensions | Custom wait types, custom conditions |
| CLI command | `fiona.cli` extensions | Third-party subcommands |

### 9.3 Plugin Discovery Paths

```python
# Default search order:
SEARCH_PATHS = [
    "~/.config/fiona/plugins/",          # User-installed plugins
    "/usr/local/share/fiona/plugins/",   # System-installed plugins
    "./fiona_plugins/",                  # Project-local plugins (development)
]
```

---

## 10. Performance Targets

### 10.1 Browser Automation

| Metric | Target | Measurement Method |
|---|---|---|
| Browser launch time | `< 3s` (headed), `< 1.5s` (headless) | `time_command()` wrapper |
| Navigation to `load` event | `< 2s` (local network), `< 5s` (internet) | `PerformanceObserver` API |
| Click response time | `< 500ms` (from CLI call to action) | Timing decorator |
| Screenshot capture | `< 1s` (full page, 1920×1080) | `time.perf_counter()` |
| Memory per context | `< 200MB` (idle page) | `psutil.Process().memory_info()` |
| Context creation | `< 500ms` | Timing decorator |
| Concurrent contexts | `>= 5` without degradation | Load test |
| Crash recovery | `< 5s` to auto-restart | Simulated crash test |

### 10.2 CAD Server

| Metric | Target | Measurement Method |
|---|---|---|
| Server startup | `< 500ms` (cold), `< 200ms` (warm) | `time.perf_counter()` |
| Command execution (create primitive) | `< 50ms` | Timing decorator |
| Full document serialization | `< 100ms` (1000 objects) | Benchmark with generated data |
| Full scene rebuild (3js) | `< 500ms` (1000 objects) | `performance.now()` in browser |
| Incremental update (single object) | `< 50ms` | Client-side timing |
| Undo/redo | `< 100ms` (including state snapshot) | Timing decorator |
| Export STL (1000 faces) | `< 1s` | Benchmark |
| WebSocket round-trip (command) | `< 10ms` (local) | Ping/pong measurement |
| Memory per document | `< 50MB` (1000 objects) | `psutil.Process().memory_info()` |
| Maximum open documents | `>= 10` | Load test |

### 10.3 Frontend (3js)

| Metric | Target | Measurement Method |
|---|---|---|
| Initial page load | `< 2s` (cold cache), `< 1s` (warm) | `Navigation Timing API` |
| Time to interactive | `< 3s` | Lighthouse audit |
| Frame rate (100 objects) | `>= 60fps` | `requestAnimationFrame` delta |
| Frame rate (1000 objects) | `>= 30fps` | `requestAnimationFrame` delta |
| Frame rate (10000 objects) | `>= 15fps` | `requestAnimationFrame` delta |
| Selection response | `< 100ms` | `performance.now()` |
| Memory usage (1000 objects) | `< 200MB` | `performance.memory` |
| Bundle size (gzipped) | `< 500KB` | Build tool report |
| FCP (First Contentful Paint) | `< 1.5s` | Lighthouse audit |

---

## 11. Observability Strategy

### 11.1 Structured Logging

```python
# fiona/logging.py
import structlog  # Or json standard library

class FionaLogger:
    """Structured logger producing JSON lines for production,
    pretty-printed for development."""

    def __init__(self, name: str, level: str = "INFO",
                 output: str = "stdout"):
        self._name = name
        self._level = level
        self._output = output

    def info(self, msg: str, **context) -> None: ...
    def warning(self, msg: str, **context) -> None: ...
    def error(self, msg: str, **context) -> None: ...
    def debug(self, msg: str, **context) -> None: ...

# Log format (JSON lines):
# {"ts": "2026-06-22T10:30:00.123Z", "level": "INFO", "logger": "browser",
#  "msg": "Browser launched", "pid": 12345, "browser_type": "chromium",
#  "duration_ms": 2450}
```

**Every log line must include:** timestamp, level, logger name, message, correlation ID (tied to request or session).

### 11.2 Tracing

```python
# fiona/tracing.py
import uuid
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    start_time: float
    end_time: float | None = None
    status: str = "ok"
    attributes: dict = field(default_factory=dict)

class Tracer:
    """OpenTelemetry-compatible tracing (stdlib only, no OT dependency required)."""

    @contextmanager
    def span(self, operation: str, **attributes):
        span = Span(
            trace_id=self._trace_id,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=self._current_span_id,
            operation=operation,
            start_time=time.monotonic(),
        )
        self._current_span_id = span.span_id
        try:
            yield span
        except Exception as e:
            span.status = "error"
            span.attributes["error"] = str(e)
            raise
        finally:
            span.end_time = time.monotonic()
            self._emit(span)
            self._current_span_id = span.parent_span_id

# Usage:
with tracer.span("browser.navigate", url="https://example.com"):
    with tracer.span("provider.launch"):
        await provider.launch(config)
    result = await context.navigate(url)
```

### 11.3 Metrics

```python
# fiona/metrics.py
class MetricsRegistry:
    """Simple metrics collector. Future: Prometheus integration."""

    def counter(self, name: str, tags: dict = None) -> "Counter": ...
    def gauge(self, name: str, tags: dict = None) -> "Gauge": ...
    def histogram(self, name: str, tags: dict = None) -> "Histogram": ...

# Key metrics to collect:
METRICS = {
    # Browser
    "browser.launch.duration_ms": Histogram,
    "browser.navigation.duration_ms": Histogram,
    "browser.navigation.status": Counter,    # Tagged by status code
    "browser.crash.count": Counter,
    "browser.active_contexts": Gauge,
    # CAD
    "cad.command.duration_ms": Histogram,     # Tagged by command name
    "cad.command.count": Counter,             # Tagged by command name
    "cad.document.count": Gauge,
    "cad.document.object_count": Gauge,
    "cad.export.duration_ms": Histogram,      # Tagged by format
    "cad.serialize.duration_ms": Histogram,
    # Server
    "server.connection.count": Gauge,
    "server.request.duration_ms": Histogram,  # Tagged by method
    "server.ws.message_count": Counter,
    # System
    "system.memory.rss_mb": Gauge,
    "system.cpu.percent": Gauge,
}
```

### 11.4 Health Endpoint

```
GET /api/health
{
  "status": "ok" | "degraded" | "error",
  "version": "0.1.0",
  "uptime_seconds": 12345,
  "components": {
    "server": { "status": "ok", "uptime": 12345 },
    "browser": {
      "status": "running" | "stopped" | "error",
      "provider": "selenium",
      "context_count": 2,
      "uptime": 5432
    },
    "document_manager": {
      "status": "ok",
      "document_count": 3,
      "total_objects": 47
    }
  },
  "resources": {
    "memory_rss_mb": 156.2,
    "cpu_percent": 4.3
  }
}
```

### 11.5 Debug Tooling

| Tool | Purpose | Endpoint / Command |
|---|---|---|
| Structured log viewer | `fiona logs --follow --level DEBUG` | CLI |
| Live metrics dashboard | Real-time metrics in terminal | `fiona metrics` |
| Span dump | View recent traces | `GET /api/debug/traces?limit=100` |
| State inspector | Inspect internal state | `GET /api/debug/state` |
| Event log | View recent bus events | `GET /api/debug/events` |
| Profile endpoint | CPU/memory profiler | `POST /api/debug/profile` → download `.prof` |
| Slow query log | Commands exceeding threshold | Automatic (default threshold 500ms) |

---

## 12. Coding Standards & Conventions

### 12.1 Repository Organization

```
Fiona/
├── BrowserAutomation/          # New: browser automation package
│   ├── __init__.py
│   ├── _provider.py            # IBrowserProvider, IBrowserInstance, IBrowserContext
│   ├── _manager.py             # BrowserManager (lifecycle, pooling)
│   ├── _selenium_provider.py    # Selenium implementation
│   ├── _config.py              # BrowserConfig, ViewportConfig
│   ├── _errors.py              # Error hierarchy
│   └── _types.py               # Data types (NavigationResult, etc.)
├── cad/
│   ├── server/                 # New: API server package
│   │   ├── __init__.py
│   │   ├── _server.py          # HTTP/WS server
│   │   ├── _handlers.py        # Request handlers
│   │   ├── _protocol.py        # RPC types
│   │   └── _frontend/          # New: 3js frontend (Vite project)
│   │       ├── package.json
│   │       ├── vite.config.js
│   │       ├── src/
│   │       │   ├── main.js
│   │       │   ├── scene/
│   │       │   ├── panels/
│   │       │   └── client/     # API client + WS handler
│   │       └── dist/           # Built output (committed? debated)
│   ├── core/                   # Existing (unchanged)
│   ├── geometry/               # Existing (unchanged)
│   └── ...                     # Existing (unchanged)
├── fiona/
│   ├── di.py                   # New: dependency injection container
│   ├── logging.py              # New: structured logging
│   ├── tracing.py              # New: tracing
│   ├── metrics.py              # New: metrics
│   └── plugin_system.py        # New: generalized plugin system
├── tests/
│   ├── browser/                # New: browser automation tests
│   ├── cad_server/             # New: CAD server tests
│   ├── cad_frontend/           # New: 3js frontend tests
│   └── ...existing...
└── docs/
    ├── architecture/           # New: ADRs, diagrams
    ├── browser-automation/     # New: user docs
    └── ficad/                  # New: CAD user docs
```

**Naming convention:** Private modules prefixed with `_` (e.g., `_provider.py`). Public API exported in `__init__.py` via `__all__`.

### 12.2 API Versioning Policy

| Version Scheme | Applied To |
|---|---|
| `package.__version__` | Python packages (semantic versioning) |
| `protocol_version` in RPC handshake | Frontend-backend protocol |
| `format_version` in `.cad` files | Document serialization format |
| `api_version` in health endpoint | HTTP API |

**Backward compatibility policy:**
- Minor version bumps: backward compatible (new fields, optional)
- Major version bumps: may break compatibility; old version supported for 6 months
- Document format: always backward-readable (reader handles N-1 version)

### 12.3 Testing Expectations

| Test Type | Required For | Minimum Coverage |
|---|---|---|
| Unit tests | All public functions/methods | 90% line coverage |
| Integration tests | All CLI commands, all API endpoints | 80% path coverage |
| Contract tests | Interface implementations | 100% of interface methods |
| Performance tests | All subsystems with targets | Per Section 10 |
| Security tests | Auth, CSRF, input validation | Per threat model |
| Regression tests | Every bug fix | 100% of fixed bugs |

### 12.4 Documentation Requirements

| Artifact | Required For | Format |
|---|---|---|
| Docstrings | Every public function/class | Google-style |
| `__init__.py` | Every package | Module docstring with `__all__` |
| README | Every subsystem | Markdown |
| ADRs | Every significant decision | `docs/architecture/adr-NNN-title.md` |
| API docs | Server endpoints | OpenAPI 3.0 spec |
| User guide | Browser Automation + ficad | Markdown in `docs/` |
| Tutorial | Getting started | Step-by-step with examples |

---

## 13. Frontend-Backend Protocol Specification

### 13.1 Transport

- **Primary:** WebSocket (`ws://127.0.0.1:{port}/ws`)
- **Fallback:** HTTP POST to `http://127.0.0.1:{port}/rpc` (for environments where WebSocket is unavailable)
- **Port:** Default 8765, configurable via `--port`

### 13.2 Protocol: JSON-RPC 2.0 with Extensions

Based on the [JSON-RPC 2.0 specification](https://www.jsonrpc.org/specification), with extensions for CAD-specific features.

#### Connection Handshake

```
Client → Server:
{
  "jsonrpc": "2.0",
  "method": "handshake",
  "params": {
    "client_version": "0.1.0",
    "client_name": "fiona-cad-frontend",
    "capabilities": ["full_state", "incremental_updates", "camera_sync"],
    "protocol_versions": ["1.0", "2.0"]
  }
}

Server → Client:
{
  "jsonrpc": "2.0",
  "result": {
    "server_version": "0.1.0",
    "protocol_version": "2.0",
    "session_id": "uuid",
    "server_capabilities": ["full_state", "incremental_updates",
                            "camera_sync", "export_stl", "export_obj"],
    "heartbeat_interval_s": 30,
    "initial_state": { ... }  // Full document snapshot
  }
}
```

#### Method Catalog

**Document Methods:**

| Method | Params | Returns | Description |
|---|---|---|---|
| `document.list` | `{}` | `[DocumentHandle]` | List open documents |
| `document.create` | `{name?}` | `DocumentHandle` | Create new document |
| `document.open` | `{path}` | `DocumentHandle` | Open .cad file |
| `document.save` | `{doc_id, path?}` | `{path}` | Save document |
| `document.close` | `{doc_id}` | `{}` | Close document |
| `document.get_state` | `{doc_id}` | `{document: {...}}` | Full state snapshot |
| `document.get_diff` | `{doc_id, since_version}` | `{patch}` | Incremental patch |

**Command Methods:**

| Method | Params | Returns | Description |
|---|---|---|---|
| `command.execute` | `{doc_id, name, kwargs}` | `CommandResult` | Execute command |
| `command.undo` | `{doc_id}` | `CommandResult` | Undo last |
| `command.redo` | `{doc_id}` | `CommandResult` | Redo last |
| `command.can_undo` | `{doc_id}` | `{can_undo: bool}` | Check undo |
| `command.can_redo` | `{doc_id}` | `{can_redo: bool}` | Check redo |
| `command.list` | `{}` | `[{name, aliases, params}]` | Available commands |

**Camera Methods:**

| Method | Params | Returns | Description |
|---|---|---|---|
| `camera.get` | `{doc_id}` | `CameraState` | Current camera |
| `camera.set` | `{doc_id, camera}` | `{}` | Set camera |
| `camera.reset` | `{doc_id}` | `{}` | Reset to default |

**Export Methods:**

| Method | Params | Returns | Description |
|---|---|---|---|
| `export.formats` | `{}` | `[{name, extensions}]` | Available formats |
| `export.run` | `{doc_id, format, path, options?}` | `ExportResult` | Export document |

**Server Methods:**

| Method | Params | Returns | Description |
|---|---|---|---|
| `server.health` | `{}` | HealthStatus | Server health |
| `server.capabilities` | `{}` | `{capabilities: [...]}` | Server capabilities |
| `server.ping` | `{}` | `{pong: timestamp}` | Heartbeat check |

**Browser Methods (optional, if browser is integrated into CAD server):**

| Method | Params | Returns |
|---|---|---|
| `browser.status` | `{}` | `{state, provider, context_count}` |
| `browser.navigate` | `{url, context_id?}` | `NavigationResult` |
| `browser.click` | `{selector, context_id?}` | `{}` |
| `browser.type` | `{selector, text, context_id?}` | `{}` |
| `browser.screenshot` | `{context_id?}` | `{png_base64}` |

#### Notification Methods (Server → Client)

| Notification | Data | Description |
|---|---|---|
| `document_updated` | `{doc_id, change_set, version}` | Document modified |
| `document_saved` | `{doc_id, path}` | Document saved |
| `object_selected` | `{doc_id, uid}` | Selection changed |
| `camera_changed` | `{doc_id, camera}` | Camera moved (if server-side control) |
| `command_completed` | `{doc_id, command_name, duration_ms}` | Command finished |
| `server.shutting_down` | `{reason, timeout_s}` | Server going down |
| `error` | `{code, message, details?}` | Server-side error |
| `heartbeat` | `{server_time}` | Periodic keepalive |

#### Error Codes

| Code | Meaning | When |
|---|---|---|
| `-32700` | Parse error | Invalid JSON |
| `-32600` | Invalid Request | Not a valid RPC message |
| `-32601` | Method not found | Unknown method name |
| `-32602` | Invalid params | Missing required field, wrong type |
| `-32603` | Internal error | Unhandled server exception |
| `-32000` | Document not open | Invalid doc_id |
| `-32001` | Command not found | Unknown command name |
| `-32002` | Command execution failed | Command raised an error |
| `-32003` | Nothing to undo | Undo stack empty |
| `-32004` | Nothing to redo | Redo stack empty |
| `-32005` | Export failed | Export error |
| `-32006` | Browser not running | Browser not started |
| `-32007` | Operation timeout | Operation exceeded timeout |
| `-32008` | Version conflict | Document modified since last snapshot |
| `-32099` | Server shutting down | Server in shutdown state |

### 13.3 Protocol Evolution Strategy

```
Protocol 1.0 ──→ Protocol 1.1 ──→ Protocol 2.0
   │                  │                  │
   ├── Full state     ├── Add            ├── Breaking changes
   │    sync          │  incremental     │   (e.g., remove field,
   ├── Basic RPC      │  updates         │    change type)
   ├── No caps        ├── Capability     │
   └── No heartbeat   │  negotiation     │
                      ├── Heartbeat      │
                      └── New methods    │
                                         └── Old protocol supported
                                              for 6 months after 2.0
                                              release
```

**Version detection:** During `handshake`, client sends `protocol_versions: ["1.0", "1.1"]`. Server responds with the highest mutually supported version.

---

## 14. State Synchronization Strategy

### 14.1 Current Approach (Phase 1): Full-State Sync

Every command response includes the **full document snapshot** (`Document.to_dict()`). The frontend replaces its entire scene tree on each response.

**Advantages:**
- Simple to implement and reason about
- No diff/patch logic required
- Immune to sync drift (always authoritative)
- Easy undo/redo (swap snapshots)

**Disadvantages:**
- Bandwidth: a document with 1000 objects could be 2-5MB per response
- Latency: frontend must rebuild entire scene on every mutation
- No offline support (must be connected to get state)

### 14.2 Evolution Path (Phase 2+): Incremental Updates

Introduce a **change-set** model after the basic system is stable:

```python
@dataclass
class ChangeSet:
    version: int                    # Monotonic version counter
    doc_id: str
    created: list[CADObject]        # New objects with full data
    modified: list[dict]            # {uid, changed_properties: {...}}
    deleted: list[str]              # UIDs of removed objects
    parent_version: int             # Previous version (for conflict detection)
```

**Frontend logic:**
```javascript
class SceneManager {
  applyChangeSet(changeSet) {
    // Remove deleted objects
    for (const uid of changeSet.deleted) {
      this.scene.remove(this.objects[uid]);
      delete this.objects[uid];
    }
    // Update modified objects
    for (const mod of changeSet.modified) {
      this.objects[mod.uid].updateProperties(mod.changedProperties);
    }
    // Add new objects
    for (const obj of changeSet.created) {
      const mesh = this.createMesh(obj);
      this.objects[obj.uid] = mesh;
      this.scene.add(mesh);
    }
    this.version = changeSet.version;
  }
}
```

### 14.3 Hybrid Strategy (Recommended)

```
Phase 1 (MVP):     Full-state sync only
Phase 2 (3 months): Add incremental updates as optimization
Phase 3 (6 months): Add CRDT-based sync for multi-user collaboration
```

**Detection:** Server advertises `capabilities: ["full_state", "incremental_updates"]`. Frontend subscribes to incremental mode via `document.subscribe_incremental`. Server falls back to full-state if client doesn't support incremental.

**Conflict resolution:** Simple last-writer-wins with version checks. If a command is executed on snapshot version 5 but the document is now at version 7, the server returns error code `-32008` (Version conflict). The frontend must re-fetch full state.

### 14.4 Frontend State Architecture

```javascript
// Frontend state management (using a simple store pattern)
class CadStore {
  constructor() {
    this.document = null;        // Last known document state
    this.version = 0;            // Monotonic version
    this.camera = defaultCamera;
    this.selection = new Set();  // Selected UIDs
    this.undoStack = [];         // Local undo stack (optimistic)
    this.redoStack = [];
    this.isDirty = false;
    this.offlineChanges = [];    // Queued changes while disconnected
  }

  // Called on every full-state response
  setFullState(document) {
    this.document = document;
    this.version = document.version;
    this.isDirty = false;
  }

  // Called on incremental updates
  applyChanges(changeSet) {
    // Apply changes to this.document
    // Update this.version
    // Trigger re-render of affected objects only
  }

  // Optimistic local update (respond instantly, sync with server)
  applyLocal(command, kwargs) {
    const snapshot = JSON.parse(JSON.stringify(this.document));
    this.undoStack.push(snapshot);
    // Apply mutation locally (if deterministic)
    // Send to server asynchronously
    // On server response: reconcile if needed
  }
}
```

---

## 15. Architecture Decision Records

### ADR-001: Use JSON-RPC 2.0 for Frontend-Backend Communication

**Status:** Accepted  
**Context:** Need a formal protocol between 3js frontend and Python CAD server.  
**Decision:** Use JSON-RPC 2.0 over WebSocket, with HTTP POST fallback.  
**Rationale:**
- Standard, well-documented specification
- Request/response correlation via `id` field
- Built-in error handling via `error` object
- Notification support for server→client events
- Minimal tooling required (stdlib `json` suffices)
- REST would require defining resource URLs for every operation; RPC maps naturally to command execution

**Rejected Alternatives:**
- **REST:** More cognitive overhead for command execution; no natural way to stream events
- **gRPC:** Requires protobuf compilation, complex toolchain, overkill for local communication
- **Custom protocol:** Avoid inventing yet another protocol when JSON-RPC 2.0 fits perfectly

**Trade-offs:**
- JSON serialization has overhead vs. protobuf (~2-5x larger messages)
- No built-in schema validation (must validate manually or add JSON Schema)
- No built-in streaming (must layer on top via WebSocket)

### ADR-002: Async-First Design for BrowserAutomation

**Status:** Accepted  
**Context:** Playwright provides an async API, but Fiona's CLI is synchronous.  
**Decision:** All `BrowserAutomation` internals use async. CLI handlers run on a dedicated event loop managed by `BrowserManager`.  
**Rationale:**
- Playwright's API is async; wrapping it in sync `asyncio.run()` calls is fragile
- Async allows concurrent browser operations (multiple tabs, parallel page loads)
- Cancellation is possible via `asyncio.Task.cancel()`
- Future agent integration can use async dispatch natively

**Rejected Alternatives:**
- **Sync wrappers around async:** `asyncio.run()` fails if an event loop exists; blocks thread; no cancellation
- **Thread-per-operation:** Complex synchronization; thread-safety bugs; resource overhead
- **Process-per-operation:** Heavyweight; no shared state

**Trade-offs:**
- Async complexity is higher than sync
- Requires `asyncio` knowledge from contributors
- CLI handlers need event loop management

### ADR-003: Separate DocumentManager from CommandExecutor

**Status:** Accepted  
**Context:** The initial design bundled document management and command execution into one server.  
**Decision:** Split into `IDocumentManager` (document lifecycle) and `ICommandExecutor` (command processing with undo/redo).  
**Rationale:**
- Single Responsibility: one class manages documents, another executes commands
- Testability: can test command executor with mock document manager
- Replaceability: document storage can change (in-memory → SQLite → cloud) without affecting commands
- Undo/redo history is per-document, but the command executor manages it

**Rejected Alternatives:**
- **Single class managing everything:** Tight coupling, harder to test, violates SRP
- **Undo/redo in Document class:** Blows up Document's responsibility

### ADR-004: Full-State Sync First, Incremental Later

**Status:** Accepted  
**Context:** Frontend needs to display CAD document state.  
**Decision:** Start with full-state sync on every command response. Add incremental updates as an optimization in Phase 2.  
**Rationale:**
- Full-state is simpler to implement and debug
- "Make it work, then make it fast"
- For initial document sizes (< 100 objects), full-state overhead is negligible
- Incremental updates add significant complexity (diff computation, patch application, conflict resolution)

**Rejected Alternatives:**
- **Incremental from day one:** Adds 2-3 weeks of engineering before MVP works
- **Operational Transformation:** Over-engineered for single-user
- **CRDT:** Way too complex for v1

**Trade-offs:**
- Phase 1 will have higher bandwidth usage
- Frontend will do full scene rebuilds instead of targeted updates
- Migration to incremental later requires both client and server changes

### ADR-005: Electron Deferred — Browser-First for v1

**Status:** Accepted  
**Context:** The roadmap was unclear about Electron vs. browser.  
**Decision:** Ship v1 as a web app served by the Python server, opened in the user's default browser. Electron only if native file dialogs, window management, or system tray integration become essential.  
**Rationale:**
- Browser is simpler to develop and debug (no Electron build pipeline)
- Hot reload with Vite dev server is trivial
- No distribution complexity (no electron-builder, no code signing)
- Users can open `http://127.0.0.1:8765` in any browser
- Electron can be layered on later if needed without changing the frontend code (just wrap the URL)

**Rejected Alternatives:**
- **Electron for v1:** 2-3 weeks of build pipeline before any CAD work; bloat (200MB+ binary)
- **Tauri:** Requires Rust, adds complexity

### ADR-006: Z-Up Coordinate Convention

**Status:** Accepted  
**Context:** Three.js defaults to Y-up, but the Python CAD kernel uses Z-up.  
**Decision:** Use Z-up in Three.js (`camera.up.set(0, 0, 1)`) to match the Python kernel.  
**Rationale:**
- Avoids coordinate transformation bugs in the Python→JS bridge
- All existing CAD tests use Z-up
- Obvious mapping: `properties.x → mesh.position.x`, `properties.y → mesh.position.y`, `properties.z → mesh.position.z`

**Rejected Alternatives:**
- **Convert to Y-up in the bridge:** Every primitive would need a rotation; mental model mismatch between Python and JS
- **Convert in the server:** Server would need to track two coordinate systems; complex and error-prone

**Trade-offs:**
- OrbitControls needs adjustment (`controls.target` works with any up vector)
- Some Three.js examples assume Y-up; must mentally translate
- Grid helper defaults to XZ plane; must rotate to XY

### ADR-007: Plugin System Shares Existing Infrastructure

**Status:** Accepted  
**Context:** `cad/plugins/` already has plugin discovery.  
**Decision:** Generalize the existing plugin system into `fiona/plugin_system.py` and reuse it for browser providers, exporters, and CAD primitives.  
**Rationale:**
- Avoids duplicating plugin infrastructure across subsystems
- Existing `cad/plugins/` already handles discovery, loading, and lifecycle
- A single entry point for plugins is easier for community contributors

---

## 16. Testing Strategy

### 16.1 Test Pyramid

```
                  ╱╲
                 ╱ E2E ╲
                ╱ Tests ╲
               ╱──────────╲
              ╱            ╲
             ╱ Integration  ╲
            ╱    Tests       ╲
           ╱──────────────────╲
          ╱                    ╲
         ╱    Contract Tests    ╲
        ╱────────────────────────╲
       ╱                          ╲
      ╱        Unit Tests          ╲
     ╱──────────────────────────────╲
```

| Layer | Count Goal | Speed | What It Covers |
|---|---|---|---|
| Unit | Thousands | ms | Individual functions, classes, methods |
| Contract | 10s | ms | Interface implementations match spec |
| Integration | 100s | seconds | CLI commands, API endpoints, browser interactions |
| E2E | 10s | minutes | Full workflows: CAD create→edit→export→reload |

### 16.2 Test Categories

#### Unit Tests

```python
# tests/browser/test_browser_manager.py
class TestBrowserManagerStateMachine:
    def test_stopped_to_running(self): ...
    def test_running_to_error_on_crash(self): ...
    def test_error_recovery_restarts(self): ...
    def test_double_stop_is_idempotent(self): ...
    def test_context_creation_fails_when_stopped(self): ...

# tests/cad_server/test_command_executor.py
class TestCommandExecutor:
    def test_execute_creates_object(self): ...
    def test_undo_restores_previous_state(self): ...
    def test_redo_after_undo(self): ...
    def test_undo_empty_stack_raises(self): ...
    def test_execute_with_invalid_args(self): ...
```

#### Contract Tests

```python
# tests/browser/test_provider_contract.py
class BrowserProviderContract:
    """Abstract test suite that every provider implementation must pass."""

    @abstractmethod
    def create_provider(self) -> IBrowserProvider: ...

    def test_launch_returns_instance(self):
        provider = self.create_provider()
        instance = await provider.launch(BrowserConfig(headless=True))
        assert isinstance(instance, IBrowserInstance)
        await instance.close()

    def test_context_supports_navigation(self):
        provider = self.create_provider()
        instance = await provider.launch(BrowserConfig(headless=True))
        ctx = await instance.create_context()
        result = await ctx.navigate("about:blank")
        assert result.status_code == 200
        await ctx.close()
        await instance.close()

    # ... 20+ tests covering every interface method, error condition, and edge case

class TestPlaywrightProvider(BrowserProviderContract):
    def create_provider(self) -> IBrowserProvider:
        return PlaywrightProvider()
```

#### Integration Tests

```python
# tests/cad_server/test_server_integration.py
class TestCadServerIntegration:
    async def test_full_workflow(self):
        """Create document → create box → undo → redo → export → reopen."""
        # Start server
        server = await start_test_server()
        client = CadRpcClient("ws://127.0.0.1:9876")

        # Handshake
        await client.handshake()

        # Create document
        handle = await client.call("document.create", {"name": "test"})

        # Create box
        result = await client.call("command.execute", {
            "doc_id": handle.doc_id,
            "name": "create_box",
            "kwargs": {"width": 10, "height": 20, "depth": 30}
        })
        assert result.created_objects == 1

        # Undo
        undo_result = await client.call("command.undo", {"doc_id": handle.doc_id})
        assert undo_result.deleted_objects == [result.created_objects[0]]

        # Redo
        redo_result = await client.call("command.redo", {"doc_id": handle.doc_id})
        assert len(redo_result.created_objects) == 1

        # Export
        export_result = await client.call("export.run", {
            "doc_id": handle.doc_id,
            "format": "stl",
            "path": "/tmp/test_export.stl"
        })
        assert os.path.exists(export_result.path)

        await client.close()
        await server.stop()

# tests/browser/test_cli_integration.py
class TestBrowserCliIntegration:
    def test_status_without_browser(self):
        result = subprocess.run(
            [sys.executable, "-m", "fiona.cli", "browser", "status"],
            capture_output=True, text=True
        )
        assert "stopped" in result.stdout

    def test_navigate_requires_browser(self):
        result = subprocess.run(
            [sys.executable, "-m", "fiona.cli", "browser", "navigate", "about:blank"],
            capture_output=True, text=True
        )
        assert "Browser not running" in result.stdout
```

#### Performance Tests

```python
# tests/benchmarks/test_cad_serialization.py
class BenchmarkCadSerialization:
    def test_serialize_1000_random_objects(self, benchmark):
        doc = generate_random_document(1000)
        result = benchmark(CadSerializer.serialize, doc)
        assert len(result) < 5_000_000  # < 5MB

    def test_deserialize_1000_objects(self, benchmark):
        json_str = CadSerializer.serialize(generate_random_document(1000))
        result = benchmark(CadSerializer.deserialize, json_str)
        assert result.object_count == 1000

# tests/browser/benchmarks/test_browser_navigation.py
class BenchmarkBrowserNavigation:
    async def test_navigate_local_server(self):
        """Navigate to a local HTTP server 100 times, measure p50/p95/p99."""
        server = LocalTestServer(html="<h1>Hello</h1>")
        await server.start()
        ctx = await browser.create_context()
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            await ctx.navigate(server.url)
            latencies.append(time.perf_counter() - start)
        p50 = sorted(latencies)[50]
        p95 = sorted(latencies)[95]
        p99 = sorted(latencies)[99]
        assert p50 < 0.2  # 200ms
        assert p95 < 0.5  # 500ms
        assert p99 < 1.0  # 1000ms
```

#### Load Tests

```python
# tests/cad_server/load/test_concurrent_clients.py
class TestConcurrentClients:
    async def test_10_concurrent_clients(self):
        """10 clients simultaneously creating objects."""
        clients = [CadRpcClient() for _ in range(10)]
        await asyncio.gather(*[c.handshake() for c in clients])

        async def create_objects(client):
            handle = await client.call("document.create")
            for i in range(100):
                await client.call("command.execute", {
                    "doc_id": handle.doc_id,
                    "name": "create_box",
                    "kwargs": {"width": i}
                })
            return handle

        handles = await asyncio.gather(*[create_objects(c) for c in clients])
        assert len(handles) == 10
```

#### Security Tests

```python
# tests/security/test_cad_server_auth.py
class TestCadServerSecurity:
    def test_no_csrf_via_origin_header(self):
        """Requests without expected Origin header should be rejected."""
        ...

    def test_path_traversal_in_open(self):
        """document.open with ../../etc/passwd should fail safely."""
        ...

    def test_large_payload_rejected(self):
        """Payloads over 10MB should be rejected."""
        ...

    def test_websocket_origin_check(self):
        """WebSocket connections from unexpected origins should be rejected."""
        ...

    def test_localhost_only_by_default(self):
        """Server should bind to 127.0.0.1, not 0.0.0.0, for security."""
        ...
```

#### Fuzz Testing

```python
# tests/fuzz/test_protocol_fuzzing.py
class TestProtocolFuzzing:
    def test_malformed_json_rejected(self):
        """Send corrupted JSON; server should return parse error, not crash."""
        ...

    def test_out_of_range_values(self):
        """Negative dimensions, NaN, Infinity — should be rejected."""
        ...

    def test_unknown_methods(self):
        """Unknown method names should receive MethodNotFound error."""
        ...

    def test_sequential_id_reuse(self):
        """Reusing a request ID should not cause confusion."""
        ...
```

### 16.3 CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: Fiona CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install ruff mypy
      - run: ruff check .
      - run: mypy fiona/ BrowserAutomation/ cad/ --strict

  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[test]"
      - run: python -m pytest tests/ -v --cov=fiona --cov=BrowserAutomation --cov=cad

  contract-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[test,browser]"
      - run: python -m pytest tests/ -v -m contract

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test,browser]"
      - run: |
          python -m pytest tests/browser/test_cli_integration.py -v
          python -m pytest tests/cad_server/test_server_integration.py -v

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: cd cad/server/_frontend && npm install
      - run: cd cad/server/_frontend && npm run test
      - run: cd cad/server/_frontend && npm run build

  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test,browser]" pytest-benchmark
      - run: python -m pytest tests/benchmarks/ -v --benchmark-json=benchmark.json
      - uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark.json

  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit safety
      - run: bandit -r fiona/ BrowserAutomation/ cad/ -f json -o bandit-report.json
      - run: safety check -r requirements.txt --json > safety-report.json
      - uses: actions/upload-artifact@v4
        with:
          name: security-reports
          path: "*-report.json"
```

---

## 17. Scope, Assumptions & Non-Goals

### 17.1 Project Scope (What We ARE Building)

| In Scope | Detail |
|---|---|
| **Browser Automation** | A dedicated `BrowserAutomation/` package with Playwright provider, CLI, agent integration, and macro support |
| **CAD 3js Frontend** | A web-based 3D CAD frontend replacing the Tkinter viewport, served by a Python HTTP/WS server |
| **CAD Server** | A local API server exposing the CAD kernel via JSON-RPC over WebSocket |
| **Formal Protocol** | Versioned, capability-negotiated JSON-RPC 2.0 protocol between frontend and backend |
| **Incremental Sync** | Path from full-state to incremental change-set synchronization |
| **Plugin System** | Generalized plugin architecture for browser providers, exporters, and CAD primitives |
| **Observability** | Structured logging, tracing, metrics, health endpoints |
| **Testing** | Unit, contract, integration, performance, security, fuzz, E2E |
| **Documentation** | ADRs, API docs, user guides, tutorials |

### 17.2 Assumptions

- **Local execution:** The CAD server and browser automation run on the same machine as the user. Remote access is explicitly out of scope for v1.
- **Python 3.11+:** All Python code targets 3.11 minimum (matching existing Fiona requirement).
- **Modern browser:** The 3js frontend targets browsers supporting WebGL 2.0 and ES2020. No IE11 support.
- **Linux primary:** Fiona is a Linux-first project. macOS may work but is not actively tested. Windows is not targeted.
- **Single user:** No multi-user or multi-session support. One user, one CAD server instance, one frontend.
- **Playwright default:** The default browser provider is Playwright with Chromium. Additional providers are community contributions.
- **No cloud services:** No authentication, no remote storage, no SaaS. Everything is local-first.

### 17.3 Constraints

| Constraint | Rationale |
|---|---|
| No framework lock-in | The DI container must support swapping any component without framework changes |
| Zero external deps for kernel | `cad/core`, `cad/geometry`, `cad/commands` must not require external packages |
| Async-first but sync-compatible | Core async design must still support synchronous CLI usage |
| Backward-compatible `.cad` format | Existing `.cad` files must load correctly in the new server |
| CmdTrace integration | All routed actions (browser, CAD) must be traceable through CmdTrace |
| 740+ existing tests must pass | No regressions in existing test suite |

### 17.4 Explicit Non-Goals

| Out of Scope | Rationale | Future Possibility |
|---|---|---|
| Multi-user collaboration | CRDT/OT complexity unjustified for v1 | Post-v1 if demand arises |
| Remote browser automation | Security implications of remote browser control | Post-v1 with VPN/SSH tunnel |
| Mobile browser automation | Touch event complexity, device emulation | Not planned |
| Cloud CAD storage | S3/cloud sync, sharing, version control | Post-v1 plugin |
| Real-time multi-viewport | Synchronized camera across multiple clients | Post-v2 |
| VR/AR viewer | WebXR integration | Community plugin |
| STEP/IGES import | Format complexity, ecosystem maturity | Community plugin |
| Machine learning for CAD | Generative design, topology optimization | Separate research track |
| Electron desktop shell | Build complexity, binary size | Post-v1 if needed |
| WASM/C++ CAD kernel | Performance gains vs. maintenance cost | If Python performance becomes bottleneck |
| Windows/macOS support | Fiona is Linux-first; cross-platform GUI testing burden | Open PRs accepted |
| Commercial licensing | AGPL/LGPL decision deferred | Post-v1 if publishing |

---

## 18. Revised Milestone Structure

The original milestone structure is preserved but reordered and refactored to reflect the architectural changes.

### Phase 0: Foundation (Weeks 1-2)

| Task | Original | Changes |
|---|---|---|
| **0.1** Create `fiona/di.py` — DI container | *New* | Precedes all other work |
| **0.2** Create `fiona/logging.py` — structured logging | *New* | All new code logs immediately |
| **0.3** Create `fiona/tracing.py` — tracing infrastructure | *New* | TDD: write trace tests first |
| **0.4** Create `fiona/metrics.py` — metrics registry | *New* | Instrument all subsystems |
| **0.5** Create `fiona/plugin_system.py` — generalized plugins | *New* | Extends existing `cad/plugins/` |
| **0.6** Define all interface ABCs (`IBrowserProvider`, `IDocumentManager`, etc.) | *New* | Contract-first development |
| **0.7** Write contract test suites for all interfaces | *New* | TDD: contracts before implementations |
| **0.8** Set up CI/CD pipeline | *New* | Lint, unit, contract gates |
| **0.9** Write ADR-001 through ADR-007 | *New* | Document architectural decisions |

### Phase 1: Browser Automation (Weeks 3-5)

| Task | Original | Changes |
|---|---|---|
| **1.1** Implement `PlaywrightProvider` (implements `IBrowserProvider`) | B1.1, B1.2 | Interface-driven; no singleton |
| **1.2** Implement `BrowserManager` with state machine | B1.2 | Full lifecycle, crash recovery, pool |
| **1.3** Implement `BrowserContext` (wraps Playwright context) | B1.1 | Async-first, typed results |
| **1.4** Implement navigation, interaction, extraction, screenshot modules | B1.1 | All return typed dataclasses |
| **1.5** Add browser optional dependency to `pyproject.toml` | B1.3 | Unchanged |
| **1.6** CLI integration (`fiona browser ...`) | B2.1, B2.2 | Uses dedicated event loop from `BrowserManager` |
| **1.7** ActionSpec + agent integration | B3.1-B3.4 | Unchanged |
| **1.8** Macro + security integration | B4.1-B4.3 | Unchanged |
| **1.9** Unit + contract + integration tests | B5.1-B5.4 | Contract tests added; performance benchmarks added |
| **1.10** Browser automation user documentation | *New* | Tutorial, CLI reference, examples |

### Phase 2: CAD Server MVP (Weeks 6-8)

| Task | Original | Changes |
|---|---|---|
| **2.0** Fix existing CAD bugs | C1.1-C1.5 | Unchanged, but gating |
| **2.1** Implement `DocumentManager` (multi-document, handle-based) | C2.1 | Replaces single-document assumption |
| **2.2** Implement `CommandExecutor` with per-document undo/redo | C2.2 | Separated from DocumentManager |
| **2.3** Implement `ExportManager` with provider pattern | C2.3 | Provider-based, extensible |
| **2.4** Implement JSON-RPC 2.0 server (WebSocket + HTTP) | C2.1-C2.6 | Formal protocol replaces ad hoc REST |
| **2.5** Implement handshake, capability negotiation, heartbeat | C2.7 | Protocol compliance |
| **2.6** Full-state sync on all responses | C2.2 | Phase 1 sync strategy |
| **2.7** CLI integration (`fiona ficad` → starts server + browser) | C2.5 | Server-managed lifecycle |
| **2.8** Server unit + contract + integration tests | C9.1 | Protocol conformance tests |
| **2.9** Security tests (CSRF, path traversal, payload limits) | *New* | Hardens server before frontend connects |

### Phase 3: 3js Frontend MVP (Weeks 9-12)

| Task | Original | Changes |
|---|---|---|
| **3.0** Frontend project scaffold (Vite + Three.js) | C3.1 | Unchanged |
| **3.1** Implement JSON-RPC client in JavaScript | C6.1, C6.2 | Formal protocol client, not ad hoc fetch |
| **3.2** Z-up Three.js scene with OrbitControls | C3.2-C3.4 | Camera matches Python kernel |
| **3.3** Primitive renderers (Box, Cylinder, Sphere, Cone, Torus) | C3.5, C3.6 | Factory pattern for extensibility |
| **3.4** Scene rebuild from full-state JSON | C3.7 | Phase 1 sync |
| **3.5** Project Tree panel | C4.2 | Sends command on delete/rename |
| **3.6** Property Editor panel | C4.3 | Type-appropriate widgets |
| **3.7** Toolbar (create primitives, undo/redo, grid, reset view) | C4.5 | All commands go through RPC |
| **3.8** Menu bar (File, Edit, View, Tools, Help) | C4.6 | File operations through RPC |
| **3.9** Status bar (object count, coordinates, mode) | C4.7 | Updates via server events |
| **3.10** Keyboard shortcuts | C4.8 | Unchanged |
| **3.11** Viewport interactions (orbit, pan, zoom, select, context menu) | C5.1-C5.6 | Ray-picking, selection highlight, grid, axes |
| **3.12** WebSocket event handling (document_updated, selection) | C6.2 | Event-driven sync |
| **3.13** Camera sync (server ↔ client) | C6.3 | Bidirectional camera state |
| **3.14** Frontend unit + integration tests | C9.2 | Vitest for JS, Playwright for E2E |

### Phase 4: Polish & Optimization (Weeks 13-16)

| Task | Original | Changes |
|---|---|---|
| **4.1** Incremental change-set sync (server + client) | *New* | Optimization over full-state |
| **4.2** Offline mode (read-only cache, queued changes) | *New* | Graceful degradation |
| **4.3** 2D Sketch editor (orthographic view, drawing tools, constraint visualization) | C8.2 | Deferred from MVP |
| **4.4** Part feature visualization (Pad, Pocket, Revolve) | C8.1 | Deferred from MVP |
| **4.5** Assembly visualization (hierarchy, transforms) | C8.3 | Deferred from MVP |
| **4.6** Performance optimization (InstancedMesh, LOD, debounced rebuilds) | C8.4 | Based on benchmark results |
| **4.7** Console panel (command input, history, output) | C4.4 | Matches Tkinter ConsolePanel |
| **4.8** Theme support (dark/light) | C8.5 | Unchanged |
| **4.9** Performance benchmarks and optimization pass | *New* | Meet targets from Section 10 |
| **4.10** Full E2E tests (CAD create→edit→export→reload workflow) | C9.3 | Unchanged |
| **4.11** Load tests (10 concurrent clients, 1000-object documents) | *New* | Stress-test the server |
| **4.12** Final documentation pass | *New* | API docs, user guide, troubleshooting |

### Dependency Graph (Revised)

```
Phase 0: Foundation
  ├── 0.1 DI Container ──────────────────────────────────────────┐
  ├── 0.2 Logging ─────┐                                         │
  ├── 0.3 Tracing ──────┤                                         │
  ├── 0.4 Metrics ──────┤                                         │
  ├── 0.5 Plugin Sys ───┤                                         │
  ├── 0.6 Interfaces ───┼── All other phases depend on these      │
  ├── 0.7 Contracts ────┘                                         │
  ├── 0.8 CI/CD                                                   │
  └── 0.9 ADRs                                                    │
                                                                  │
Phase 1: Browser Automation                                       │
  ├── 1.1 PlaywrightProvider ←── depends on 0.6, 0.7             │
  ├── 1.2 BrowserManager ←── depends on 1.1                      │
  ├── 1.3 BrowserContext ←── depends on 1.1                      │
  ├── 1.4 Modules ←── depends on 1.3                             │
  ├── 1.5 pyproject.toml                                          │
  ├── 1.6 CLI (depends on 1.2, 1.4)                              │
  ├── 1.7 Agent (depends on 1.6)                                 │
  ├── 1.8 Security                                               │
  ├── 1.9 Tests (depends on 1.1-1.8)                             │
  └── 1.10 Docs                                                  │
                                                                  │
Phase 2: CAD Server MVP                                           │
  ├── 2.0 Fix bugs                                                │
  ├── 2.1 DocumentManager ←── depends on 0.1                     │
  ├── 2.2 CommandExecutor ←── depends on 2.1                     │
  ├── 2.3 ExportManager ←── depends on 0.5                       │
  ├── 2.4 RPC Server ←── depends on 2.1, 2.2                    │
  ├── 2.5 Protocol (handshake, caps)                             │
  ├── 2.6 Full-state sync                                         │
  ├── 2.7 CLI (depends on 2.4)                                   │
  ├── 2.8 Tests (depends on 2.1-2.7)                             │
  └── 2.9 Security tests                                          │
                                                                  │
Phase 3: 3js Frontend MVP                                         │
  ├── 3.0 Scaffold                                                │
  ├── 3.1 RPC client ←── depends on 2.4                          │
  ├── 3.2 Three.js scene (depends on 3.0)                        │
  ├── 3.3 Primitive renderers (depends on 3.2)                   │
  ├── 3.4 Scene rebuild (depends on 3.1, 3.3)                    │
  ├── 3.5-3.10 UI panels (depends on 3.4)                        │
  ├── 3.11 Viewport interactions (depends on 3.4)                │
  ├── 3.12 WebSocket handler (depends on 3.1)                    │
  ├── 3.13 Camera sync (depends on 3.12)                         │
  └── 3.14 Frontend tests                                         │
                                                                  │
Phase 4: Polish & Optimization                                    │
  ├── 4.1 Incremental sync (depends on 2.6, 3.12)                │
  ├── 4.2 Offline mode (depends on 4.1)                          │
  ├── 4.3-4.5 Advanced features                                  │
  ├── 4.6 Performance optimization                               │
  ├── 4.7 Console panel                                          │
  ├── 4.8 Theme support                                          │
  ├── 4.9 Benchmarks                                             │
  ├── 4.10 E2E tests                                             │
  ├── 4.11 Load tests                                            │
  └── 4.12 Final documentation                                   │
```

---

## Appendix A: Glossary

| Term | Definition |
|---|---|
| **Browser context** | Isolated browser session with its own cookies, storage, and auth (similar to an incognito profile) |
| **Browser provider** | An implementation of `IBrowserProvider` wrapping a specific browser automation library |
| **Change set** | A collection of created, modified, and deleted object IDs representing an incremental document update |
| **Document handle** | A lightweight reference to an open document (doc_id, name, path, modified status) |
| **Event bus** | An in-process pub/sub system for loose coupling between subsystems |
| **Full-state sync** | Returning the entire document JSON on every command response |
| **Incremental sync** | Returning only the changes since the last known version |
| **JSON-RPC** | A lightweight remote procedure call protocol using JSON for encoding |
| **Lifecycle state machine** | A finite state machine defining valid states and transitions for a resource |
| **Provider** | An implementation of an abstract interface that can be swapped without changing consumers |
| **RPC method** | A named operation callable via JSON-RPC |
| **Scope** | The set of Fiona's responsibilities (browser automation, CAD, etc.) |

---

## Appendix B: File Manifest (New Files)

```
Fiona/
├── fiona/
│   ├── __init__.py              # Modified: export di, logging, tracing, metrics
│   ├── di.py                    # NEW: dependency injection container
│   ├── logging.py               # NEW: structured logger
│   ├── tracing.py               # NEW: span-based tracing
│   ├── metrics.py               # NEW: metrics registry
│   └── plugin_system.py         # NEW: generalized plugin manager
├── BrowserAutomation/
│   ├── __init__.py              # NEW
│   ├── _provider.py             # NEW: IBrowserProvider, IBrowserInstance, IBrowserContext
│   ├── _manager.py              # NEW: BrowserManager (state machine)
│   ├── _selenium_provider.py # NEW: Selenium implementation
│   ├── _config.py               # NEW: BrowserConfig
│   ├── _errors.py               # NEW: error hierarchy
│   └── _types.py                # NEW: dataclasses
├── cad/
│   ├── _server.py               # NEW: RPC server (JSON-RPC 2.0)
│   ├── _protocol.py             # NEW: RPC message types
│   ├── _document_manager.py     # NEW: IDocumentManager impl
│   ├── _command_executor.py     # NEW: ICommandExecutor impl
│   ├── _export_manager.py       # NEW: ExportManager
│   └── _frontend/               # NEW: complete 3js frontend
│       ├── package.json
│       ├── vite.config.js
│       ├── index.html
│       ├── src/
│       │   ├── main.js
│       │   ├── store.js          # CadStore (state management)
│       │   ├── client.js         # RPC client
│       │   ├── scene/
│       │   │   ├── SceneManager.js
│       │   │   ├── PrimitiveFactory.js
│       │   │   └── CameraSync.js
│       │   ├── panels/
│       │   │   ├── Toolbar.js
│       │   │   ├── ProjectTree.js
│       │   │   ├── PropertyEditor.js
│       │   │   ├── ConsolePanel.js
│       │   │   └── StatusBar.js
│       │   └── styles/
│       │       └── main.css
│       └── tests/
│           ├── SceneManager.test.js
│           ├── PrimitiveFactory.test.js
│           └── client.test.js
├── tests/
│   ├── browser/
│   │   ├── test_browser_manager.py
│   │   ├── test_provider_contract.py
│   │   └── benchmarks/
│   │       └── test_navigation.py
│   ├── cad_server/
│   │   ├── test_document_manager.py
│   │   ├── test_command_executor.py
│   │   ├── test_server_integration.py
│   │   ├── test_protocol.py
│   │   ├── test_export_manager.py
│   │   ├── security/
│   │   │   └── test_csrf.py
│   │   ├── load/
│   │   │   └── test_concurrent.py
│   │   └── benchmarks/
│   │       └── test_serialization.py
│   ├── fiona/
│   │   ├── test_di.py
│   │   ├── test_logging.py
│   │   └── test_plugin_system.py
│   └── fuzz/
│       └── test_protocol_fuzzing.py
└── docs/
    ├── architecture/
    │   ├── adr-001-json-rpc-protocol.md
    │   ├── adr-002-async-first-browser.md
    │   ├── adr-003-separate-doc-and-command.md
    │   ├── adr-004-full-state-then-incremental.md
    │   ├── adr-005-browser-first-not-electron.md
    │   ├── adr-006-z-up-coordinate-convention.md
    │   └── adr-007-generalized-plugin-system.md
    ├── browser-automation/
    │   ├── README.md
    │   ├── getting-started.md
    │   └── api-reference.md
    └── ficad/
        ├── README.md
        ├── user-guide.md
        └── developer-guide.md
```

---

## Appendix C: Risk Register

| ID | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Playwright API breaking changes | Low | High | `IBrowserProvider` abstraction contains blast radius; update Playwright independently | Browser team |
| R2 | WebGL compatibility issues on Linux | Medium | Medium | Test on Intel, AMD, and NVIDIA; `forceSoftwareRenderer` fallback; document known issues | Frontend team |
| R3 | Python async event loop conflicts with Tkinter | Medium | High | CAD server runs in separate process; no Tkinter in server process; `BrowserManager` has dedicated loop | Server team |
| R4 | `.cad` file format drift between old and new serializers | Low | Medium | Shared `Document.to_dict()`/`from_dict()` code path ensures consistency | CAD kernel team |
| R5 | Large documents (>10k objects) cause frontend lag | Medium | Medium | InstancedMesh, LOD, incremental sync, worker-thread serialization | Frontend team |
| R6 | Contributor learning curve with async + DI + contracts | Medium | Low | Comprehensive developer guide, ADRs, contract test examples | Docs team |
| R7 | Tkinter CAD GUI becomes unmaintained during 3js migration | Low | Low | Keep Tkinter code alive; remove only when 3js reaches feature parity | CAD team |
| R8 | Port conflicts with other local services | Low | Low | Auto-detect free port; `--port` flag; document in troubleshooting | Server team |

---

*End of Architecture Review. This document should be treated as a living specification — update ADRs as decisions are revisited, and flag new risks as they emerge.*
