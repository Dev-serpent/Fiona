"""Formal interface contracts for all subsystems.

These ABCs define the boundaries between every component in Fiona.
Each abstract interface must be accompanied by a contract test suite
(see tests/contracts/) that verifies implementations match the spec.

All public types, errors, events, and interfaces are importable from
this single module so that contract testing and dependency injection
can rely on one stable source of truth.
"""

from __future__ import annotations

import abc
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrowserConfig:
    """Configuration for launching a browser instance.

    Attributes:
        browser_type: Which browser engine to use ('chromium', 'firefox', 'webkit').
        headless: Run without a visible UI window.
        viewport_width: Default viewport width in pixels.
        viewport_height: Default viewport height in pixels.
        data_dir: Persistent profile directory, or None for ephemeral.
        proxy: Proxy server URL, or None for direct connection.
        args: Additional command-line arguments passed to the browser process.
    """

    browser_type: str = "chromium"
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    data_dir: str | None = None
    proxy: str | None = None
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class NavigationResult:
    """Result of a page navigation operation.

    Attributes:
        url: Final URL after any redirects.
        status_code: HTTP status code of the final response.
        title: Page document title.
        duration_ms: Total navigation time in milliseconds.
        redirect_chain: Ordered sequence of URLs visited during redirects.
    """

    url: str
    status_code: int
    title: str
    duration_ms: float
    redirect_chain: tuple[str, ...]


class NavigationEvent(Enum):
    """Page-load readiness thresholds for navigation.

    Controls how long ``navigate()`` waits before considering the
    navigation complete.
    """

    LOAD = "load"
    """Wait for the full ``load`` event (all resources fetched)."""
    DOM_CONTENT = "domcontentloaded"
    """Wait only until the DOM is ready (faster, but styles/fonts may be missing)."""
    NETWORK_IDLE = "networkidle"
    """Wait until no network requests have been made for ~500 ms."""


@dataclass(frozen=True)
class DocumentHandle:
    """Lightweight reference to an open CAD document.

    Attributes:
        doc_id: Unique document identifier (UUID).
        name: Human-readable document name.
        path: Saved file path, or None if the document has never been saved.
        object_count: Number of CAD objects in the document.
        is_modified: True if there are unsaved changes.
        created_at: Unix timestamp of document creation.
        modified_at: Unix timestamp of the most recent modification.
    """

    doc_id: str
    name: str
    path: str | None
    object_count: int
    is_modified: bool
    created_at: float
    modified_at: float


@dataclass(frozen=True)
class CommandResult:
    """Outcome of executing a CAD command against a document.

    Attributes:
        success: Whether the command completed without errors.
        message: Human-readable status or error description.
        document_snapshot: Full serialised document state after execution.
        created_objects: UIDs of objects created by this command.
        modified_objects: UIDs of objects modified by this command.
        deleted_objects: UIDs of objects deleted by this command.
        execution_time_ms: Wall-clock time spent executing the command.
        warnings: Non-fatal diagnostic messages produced during execution.
    """

    success: bool
    message: str
    document_snapshot: dict[str, Any]
    created_objects: list[str]
    modified_objects: list[str]
    deleted_objects: list[str]
    execution_time_ms: float
    warnings: list[str]


@dataclass(frozen=True)
class ExportResult:
    """Outcome of a document export operation.

    Attributes:
        path: Absolute filesystem path where the export was written.
        format: Short format identifier (e.g. ``'stl'``, ``'obj'``).
        size_bytes: Size of the written file in bytes.
        duration_ms: Wall-clock time spent exporting.
        warnings: Non-fatal messages produced during export.
    """

    path: str
    format: str
    size_bytes: int
    duration_ms: float
    warnings: list[str]


# ---------------------------------------------------------------------------
# Error hierarchy – Browser
# ---------------------------------------------------------------------------


class BrowserError(Exception):
    """Base exception for all browser-automation failures."""


class BrowserLaunchError(BrowserError):
    """Browser process could not be started."""


class BrowserNotRunning(BrowserError):
    """Operation requires a running browser but none is available."""


class BrowserShutdownError(BrowserError):
    """Failed to cleanly shut down the browser process."""


class BrowserTimeout(BrowserError):
    """A browser operation exceeded its time limit."""


class NavigationTimeout(BrowserTimeout):
    """Page navigation did not complete within the configured timeout."""


class SelectorTimeout(BrowserTimeout):
    """Waiting for a DOM selector timed out."""


class ElementNotFound(BrowserError):
    """The specified DOM element does not exist in the page."""


class ElementNotInteractable(BrowserError):
    """The element was found but cannot be interacted with (e.g. hidden, disabled)."""


class ScriptExecutionError(BrowserError):
    """JavaScript evaluation inside the page failed."""


class BrowserCrashError(BrowserError):
    """The browser process terminated unexpectedly."""


class ExportError(Exception):
    """Base exception for export failures."""


# ---------------------------------------------------------------------------
# Error hierarchy – CAD / Document
# ---------------------------------------------------------------------------


class CommandError(Exception):
    """Base exception for all command-execution failures."""


class CommandNotFound(CommandError):
    """The requested command name does not exist in the registry."""


class InvalidArguments(CommandError):
    """The arguments supplied to a command are invalid."""


class DocumentNotOpen(CommandError):
    """The specified document ID does not refer to an open document."""


class NothingToUndo(CommandError):
    """Undo was requested but the undo stack is empty."""


class NothingToRedo(CommandError):
    """Redo was requested but the redo stack is empty."""


class DocumentLoadError(CommandError):
    """Failed to load a document from disk."""


class DocumentSaveError(CommandError):
    """Failed to save a document to disk."""


# ---------------------------------------------------------------------------
#  Browser Automation Interfaces
# ---------------------------------------------------------------------------


class IBrowserProvider(abc.ABC):
    """Abstract interface for browser automation backends.

    Implementations wrap a specific technology such as Playwright,
    Chrome DevTools Protocol (CDP), or Selenium WebDriver.
    """

    @abc.abstractmethod
    async def launch(self, config: BrowserConfig) -> IBrowserInstance:
        """Launch a new browser process.

        Args:
            config: Desired browser type, headless mode, viewport, etc.

        Returns:
            A running :class:`IBrowserInstance` representing the process.

        Raises:
            BrowserLaunchError: The browser could not be started
                (e.g. executable not found, port conflict).
        """
        ...

    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier.

        Returns:
            e.g. ``'selenium'``, ``'cdp'``.
        """
        ...

    @abc.abstractmethod
    def capabilities(self) -> set[str]:
        """Features supported by this provider.

        Returns:
            A set of capability strings, e.g.
            ``{'screenshot', 'pdf', 'network_intercept', 'js_eval'}``.
        """
        ...


class IBrowserInstance(abc.ABC):
    """A running browser process.

    Owns the OS-level browser process and provides factory methods
    for creating isolated browsing contexts.
    """

    @abc.abstractmethod
    async def create_context(self, **kwargs: Any) -> IBrowserContext:
        """Create a new isolated browser context (akin to an incognito profile).

        Args:
            **kwargs: Implementation-specific options such as
                ``incognito``, ``viewport``, ``user_agent``, etc.

        Returns:
            An :class:`IBrowserContext` whose cookies, storage, and auth
            are isolated from all other contexts.

        Raises:
            BrowserNotRunning: The browser process is not alive.
        """
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Kill the browser process and release all resources.

        This method is idempotent — calling it multiple times has
        no additional effect.

        Raises:
            BrowserShutdownError: The process could not be terminated.
        """
        ...

    @property
    @abc.abstractmethod
    def is_closed(self) -> bool:
        """True after :meth:`close` has completed (or the process crashed)."""
        ...

    @property
    @abc.abstractmethod
    def pid(self) -> int | None:
        """OS process ID of the browser, or *None* if not running."""
        ...


class IBrowserContext(abc.ABC):
    """An isolated browser session with its own cookies, storage, and auth.

    Analogous to a browser tab or an incognito window.  Contexts
    created from the same :class:`IBrowserInstance` are completely
    isolated from one another.
    """

    @abc.abstractmethod
    async def navigate(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        wait_until: NavigationEvent = NavigationEvent.LOAD,
    ) -> NavigationResult:
        """Navigate to a URL and wait for the page to reach the desired state.

        Args:
            url: The fully-qualified URL to navigate to.
            timeout: Maximum seconds to wait for navigation to complete.
            wait_until: Which page-load event signals readiness.

        Returns:
            A :class:`NavigationResult` containing the final URL, status,
            title, duration, and redirect chain.

        Raises:
            NavigationTimeout: The page did not load within *timeout*.
            BrowserCrashError: The browser process died during navigation.
        """
        ...

    @abc.abstractmethod
    async def click(self, selector: str, *, timeout: float = 5.0) -> None:
        """Click the first element matching a CSS selector.

        Args:
            selector: A valid CSS selector string.
            timeout: Maximum seconds to wait for the element to appear
                and become actionable.

        Raises:
            SelectorTimeout: No matching element appeared within *timeout*.
            ElementNotFound: The element was detached from the DOM before the click.
            ElementNotInteractable: The element exists but cannot be clicked
                (e.g. hidden by another element, disabled).
            BrowserCrashError: The browser process died during the operation.
        """
        ...

    @abc.abstractmethod
    async def type_text(
        self,
        selector: str,
        text: str,
        *,
        delay: float = 0.01,
        timeout: float = 5.0,
    ) -> None:
        """Type text into an editable element.

        Each character is typed individually with an optional delay
        between keystrokes to simulate human typing.

        Args:
            selector: CSS selector for the target input element.
            text: The text string to type.
            delay: Seconds to wait between keystrokes.
            timeout: Maximum seconds to wait for the element to appear.

        Raises:
            SelectorTimeout: The element did not appear within *timeout*.
            ElementNotInteractable: The element exists but is not editable.
            BrowserCrashError: The browser process died during the operation.
        """
        ...

    @abc.abstractmethod
    async def get_text(self, selector: str, *, timeout: float = 5.0) -> str:
        """Retrieve the ``textContent`` of the first matching element.

        Args:
            selector: CSS selector for the target element.
            timeout: Maximum seconds to wait for the element to appear.

        Returns:
            The text content of the element.

        Raises:
            SelectorTimeout: No matching element appeared within *timeout*.
            BrowserCrashError: The browser process died during the operation.
        """
        ...

    @abc.abstractmethod
    async def screenshot(
        self,
        *,
        path: str | None = None,
        full_page: bool = False,
    ) -> bytes:
        """Capture a screenshot of the current page.

        Args:
            path: If provided, the PNG image is written to this file.
            full_page: If True, capture the full scrollable page rather
                than just the visible viewport.

        Returns:
            Raw PNG bytes.  If *path* was provided the same bytes are
            returned so callers can always rely on the return value.
        """
        ...

    @abc.abstractmethod
    async def evaluate(self, js: str, *, timeout: float = 5.0) -> Any:
        """Execute JavaScript in the page's main frame context.

        Args:
            js: JavaScript source code to evaluate.
            timeout: Maximum seconds to wait for execution.

        Returns:
            The return value of the evaluated expression.  Simple types
            (str, int, float, bool, None, list, dict) are returned as-is;
            complex DOM objects are serialised as dictionaries.

        Raises:
            ScriptExecutionError: The script threw an exception or
                the return value could not be serialised.
            BrowserCrashError: The browser process died during execution.
        """
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the context and release all associated resources.

        Idempotent — subsequent calls have no effect.
        """
        ...

    @property
    @abc.abstractmethod
    def is_closed(self) -> bool:
        """True after :meth:`close` has been called on this context."""
        ...

    @property
    @abc.abstractmethod
    def context_id(self) -> str:
        """Stable unique identifier for this context (UUID)."""
        ...


# ---------------------------------------------------------------------------
#  CAD Document Interfaces
# ---------------------------------------------------------------------------


class IDocumentManager(abc.ABC):
    """Manages the lifecycle of zero or more open CAD documents.

    Documents are identified by UUID strings returned as part of
    :class:`DocumentHandle`.  The manager is responsible for loading,
    saving, and enumerating documents, but does **not** execute
    commands against them — that is the role of :class:`ICommandExecutor`.
    """

    @abc.abstractmethod
    def create_document(self, name: str = "Untitled") -> DocumentHandle:
        """Create a new, empty document.

        Args:
            name: A human-readable name for the document.

        Returns:
            A :class:`DocumentHandle` representing the new document.
        """
        ...

    @abc.abstractmethod
    def open_document(self, path: str) -> DocumentHandle:
        """Load a ``.cad`` file from disk and register it.

        Args:
            path: Absolute or relative filesystem path to the file.

        Returns:
            A :class:`DocumentHandle` for the opened document.

        Raises:
            DocumentLoadError: The file could not be read or parsed.
        """
        ...

    @abc.abstractmethod
    def save_document(self, doc_id: str, path: str | None = None) -> str:
        """Persist a document to disk.

        Args:
            doc_id: UUID of the document to save.
            path: Destination file path.  If *None*, the document's
                current path (from its :class:`DocumentHandle`) is used.

        Returns:
            The absolute path to which the document was saved.

        Raises:
            DocumentNotOpen: No document with *doc_id* is open.
            DocumentSaveError: The file could not be written.
        """
        ...

    @abc.abstractmethod
    def get_document(self, doc_id: str) -> Document | None:
        """Retrieve a document object by its identifier.

        Args:
            doc_id: UUID of the target document.

        Returns:
            The :class:`Document` instance, or *None* if no document
            with that ID is currently open.
        """
        ...

    @abc.abstractmethod
    def close_document(self, doc_id: str) -> None:
        """Close a document and release its resources.

        Unsaved changes are **not** automatically persisted — callers
        should call :meth:`save_document` first if needed.

        Args:
            doc_id: UUID of the document to close.

        Raises:
            DocumentNotOpen: The document is not open (idempotent
                if already closed).
        """
        ...

    @abc.abstractmethod
    def list_documents(self) -> list[DocumentHandle]:
        """Return metadata for every open document.

        Returns:
            A list of :class:`DocumentHandle` objects, one per open
            document.  May be empty.
        """
        ...

    @abc.abstractmethod
    def active_document(self) -> Document | None:
        """Return the currently active (front-most) document.

        The "active" document is the one that receives commands when
        no explicit *doc_id* is provided.

        Returns:
            The active :class:`Document`, or *None* if no documents
            are open.
        """
        ...


class ICommandExecutor(abc.ABC):
    """Executes named commands against a document with undo/redo tracking.

    Each document has its own independent undo and redo stacks.
    Operations are synchronous from the caller's perspective.
    """

    @abc.abstractmethod
    def execute(
        self,
        doc_id: str,
        command_name: str,
        **kwargs: Any,
    ) -> CommandResult:
        """Execute a named command on a document.

        The command is recorded on the document's undo stack so it can
        be later reversed via :meth:`undo`.

        Args:
            doc_id: UUID of the target document.
            command_name: Registered command name (e.g. ``'create_box'``).
            **kwargs: Command-specific keyword arguments.

        Returns:
            A :class:`CommandResult` describing the outcome.

        Raises:
            DocumentNotOpen: No document with *doc_id* is open.
            CommandNotFound: *command_name* is not in the command registry.
            InvalidArguments: The supplied arguments are invalid for
                the named command.
        """
        ...

    @abc.abstractmethod
    def undo(self, doc_id: str) -> dict[str, Any]:
        """Reverse the most recent command on the document's undo stack.

        Args:
            doc_id: UUID of the target document.

        Returns:
            A full document snapshot (``dict``) reflecting the state
            after the undo.

        Raises:
            DocumentNotOpen: No document with *doc_id* is open.
            NothingToUndo: The undo stack is empty.
        """
        ...

    @abc.abstractmethod
    def redo(self, doc_id: str) -> dict[str, Any]:
        """Re-apply the most recently undone command.

        Args:
            doc_id: UUID of the target document.

        Returns:
            A full document snapshot (``dict``) reflecting the state
            after the redo.

        Raises:
            DocumentNotOpen: No document with *doc_id* is open.
            NothingToRedo: The redo stack is empty.
        """
        ...

    @abc.abstractmethod
    def can_undo(self, doc_id: str) -> bool:
        """Check whether an undo operation is currently available.

        Args:
            doc_id: UUID of the target document.

        Returns:
            True if the undo stack is non-empty.
        """
        ...

    @abc.abstractmethod
    def can_redo(self, doc_id: str) -> bool:
        """Check whether a redo operation is currently available.

        Args:
            doc_id: UUID of the target document.

        Returns:
            True if the redo stack is non-empty.
        """
        ...

    @abc.abstractmethod
    def clear_history(self, doc_id: str) -> None:
        """Clear both the undo and redo stacks for a document.

        Args:
            doc_id: UUID of the target document.

        Raises:
            DocumentNotOpen: No document with *doc_id* is open.
        """
        ...


# ---------------------------------------------------------------------------
#  Export Interface
# ---------------------------------------------------------------------------


class IExportProvider(abc.ABC):
    """Converts a CAD document to a specific output format.

    Implementations are registered with an :class:`ExportManager`
    and selected by ``format_name()``.
    """

    @abc.abstractmethod
    def format_name(self) -> str:
        """Short identifier for the format, e.g. ``'stl'``, ``'obj'``, ``'svg'``.

        This value is used as the lookup key in the export registry.
        """
        ...

    @abc.abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions associated with this format.

        Returns:
            e.g. ``['.stl', '.STL']`` for the STL format.
        """
        ...

    @abc.abstractmethod
    def export(
        self,
        doc: Document,
        path: str,
        **options: Any,
    ) -> ExportResult:
        """Export *doc* to the file at *path*.

        Args:
            doc: The document to export.
            path: Destination filesystem path.
            **options: Format-specific options (e.g. precision,
                binary vs. ASCII encoding).

        Returns:
            An :class:`ExportResult` with metadata about the written file.

        Raises:
            ExportError: The export operation failed.
            DocumentNotOpen: The document is not in a valid state for export.
        """
        ...


# ---------------------------------------------------------------------------
#  Event system – types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """Base type for all events published on the :class:`EventBus`.

    Attributes:
        timestamp: Unix time (seconds since epoch) at publication.
        source: Identifier of the subsystem that published the event.
    """

    timestamp: float
    source: str


@dataclass(frozen=True)
class DocumentEvent(Event):
    """Base type for events related to a specific CAD document.

    Attributes:
        doc_id: UUID of the affected document.
    """

    doc_id: str


@dataclass(frozen=True)
class DocumentCreated(DocumentEvent):
    """Published when a new document is created via :meth:`IDocumentManager.create_document`."""


@dataclass(frozen=True)
class DocumentModified(DocumentEvent):
    """Published when the document's state changes after a command execution."""


@dataclass(frozen=True)
class DocumentSaved(DocumentEvent):
    """Published after a document has been persisted to disk."""


@dataclass(frozen=True)
class DocumentClosed(DocumentEvent):
    """Published when a document is closed."""


@dataclass(frozen=True)
class ObjectSelected(DocumentEvent):
    """Published when the active selection changes inside a document.

    Attributes:
        uid: UUID of the newly selected object, or *None* if the
            selection was cleared.
    """

    uid: str | None


@dataclass(frozen=True)
class BrowserEvent(Event):
    """Base type for events related to browser automation.

    Attributes:
        context_id: UUID of the browser context that produced the event.
    """

    context_id: str


@dataclass(frozen=True)
class BrowserLaunched(BrowserEvent):
    """Published when a browser instance has started successfully."""


@dataclass(frozen=True)
class BrowserCrashed(BrowserEvent):
    """Published when the browser process terminates unexpectedly.

    Attributes:
        reason: Human-readable description of the crash cause.
    """

    reason: str


@dataclass(frozen=True)
class BrowserContextCreated(BrowserEvent):
    """Published when a new :class:`IBrowserContext` is created."""


@dataclass(frozen=True)
class NavigationCompleted(BrowserEvent):
    """Published when a page navigation finishes.

    Attributes:
        url: The final URL after navigation (and any redirects).
        status: HTTP status code of the final response.
    """

    url: str
    status: int


# ---------------------------------------------------------------------------
#  Event bus – concrete pub/sub implementation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Subscription:
    """Token returned by :meth:`EventBus.subscribe`.

    Hold onto this value and pass it to :meth:`EventBus.unsubscribe`
    to unregister the callback.
    """

    event_type: type
    """The event type this subscription listens for."""
    callback_id: str
    """Opaque unique identifier for the callback within the bus."""


class EventBus:
    """In-process publish/subscribe event bus.

    Thread-safety:
        All public methods are thread-safe and may be called from any thread.

    Ordering:
        No ordering guarantees are made between subscribers of the same event
        type.  Subscribers are called in registration order, but this must
        not be relied upon.

    Error handling:
        :meth:`publish` silently swallows exceptions raised by individual
        subscribers.  :meth:`publish_and_wait` allows exceptions to propagate.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        # Internal storage: event_type -> list of (callback_id, callback) tuples.
        self._subscribers: dict[type[Event], list[tuple[str, Callable[[Event], None]]]] = {}

    def subscribe(
        self,
        event_type: type[Event],
        callback: Callable[[Event], None],
    ) -> Subscription:
        """Register a subscriber for *event_type*.

        The *callback* will be invoked for every event of the registered type
        (or a subtype) published after this call.

        Args:
            event_type: The event class to subscribe to (e.g. ``DocumentModified``).
                Subscribers also receive events that are instances of subclasses.
            callback: A callable accepting a single :class:`Event` argument.

        Returns:
            A :class:`Subscription` token that must be retained by the caller
            for later use with :meth:`unsubscribe`.
        """
        callback_id = str(uuid.uuid4())
        entry = (callback_id, callback)
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(entry)
        return Subscription(event_type=event_type, callback_id=callback_id)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Remove a previously registered subscription.

        This method is idempotent — calling it with a
        :class:`Subscription` that has already been removed (or was
        never registered) has no effect.

        Args:
            subscription: The :class:`Subscription` token returned by
                :meth:`subscribe`.
        """
        with self._lock:
            entries = self._subscribers.get(subscription.event_type)
            if entries is None:
                return
            self._subscribers[subscription.event_type] = [
                (cid, cb)
                for (cid, cb) in entries
                if cid != subscription.callback_id
            ]

    def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers (fire-and-forget).

        The method returns immediately after dispatching.  Exceptions
        raised by individual subscribers are caught and discarded so
        that a failing subscriber does not block others.

        Args:
            event: The event instance to publish.
        """
        callbacks: list[Callable[[Event], None]] = []
        with self._lock:
            for ev_type, entries in self._subscribers.items():
                if isinstance(event, ev_type):
                    callbacks.extend(cb for (_cid, cb) in entries)
        # Invoke callbacks outside the lock to avoid deadlocks if a
        # subscriber itself calls back into the bus.
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass  # fire-and-forget — swallow subscriber errors

    def publish_and_wait(self, event: Event, timeout: float = 5.0) -> None:
        """Publish an event and wait for all subscribers to complete.

        Unlike :meth:`publish`, this method propagates exceptions raised
        by subscribers so callers can observe failures.

        Args:
            event: The event instance to publish.
            timeout: Maximum seconds to allow for subscriber execution.
                (Reserved for future use; currently all subscribers are
                called synchronously within this timeout window.)

        Raises:
            TimeoutError: Subscribers did not complete within *timeout*.
                (Currently not raised — reserved for future asynchronous
                implementations.)
        """
        callbacks: list[Callable[[Event], None]] = []
        with self._lock:
            for ev_type, entries in self._subscribers.items():
                if isinstance(event, ev_type):
                    callbacks.extend(cb for (_cid, cb) in entries)
        # In the current synchronous implementation all subscribers are
        # invoked inline.  A future thread-based or asyncio-based version
        # would enforce the timeout here.
        _deadline = time.monotonic() + timeout  # noqa: F841
        for cb in callbacks:
            cb(event)


# ---------------------------------------------------------------------------
#  Scientific Knowledge Retrieval Interfaces
# ---------------------------------------------------------------------------


class IIntentDomainClassifier(abc.ABC):
    """Classifies a user query into a scientific domain and intent."""

    @abc.abstractmethod
    async def classify(self, query: str) -> "IntentDomainResult":
        """Classify *query* into a domain + intent.

        Args:
            query: Free-text user query.

        Returns:
            An :class:`IntentDomainResult` with the best-guess domain
            and intent, or ``unknown`` if nothing matched.
        """
        ...


class IProvider(abc.ABC):
    """Abstract interface for a scientific data provider."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Short, stable provider identifier (e.g. ``'pubchem'``)."""

    @property
    @abc.abstractmethod
    def supported_domains(self) -> frozenset["ScientificDomain"]:
        """Set of domains this provider can handle."""

    @abc.abstractmethod
    async def fetch(self, context: "RetrievalContext") -> "RawProviderResult":
        """Fetch raw data for the given retrieval context.

        Args:
            context: Fully resolved context with domains and query.

        Returns:
            Raw provider data wrapped in a :class:`RawProviderResult`.

        Raises:
            ProviderConnectionError: Network / connectivity failure.
            ProviderTimeoutError: Request exceeded the timeout.
            ProviderRateLimitedError: API rate limit was hit.
        """
        ...


class INormalizer(abc.ABC):
    """Converts raw provider responses into :class:`ScientificEntity` lists."""

    @abc.abstractmethod
    async def normalize(self, raw: "RawProviderResult") -> list["ScientificEntity"]:
        """Normalise a single raw provider result.

        Args:
            raw: Raw data from a provider.

        Returns:
            A list of normalised entities (may be empty).

        Raises:
            NormalizationError: The raw data could not be parsed.
        """
        ...


class IEntityResolver(abc.ABC):
    """Resolves entity aliases, assigns canonical IDs, and merges
    cross-provider duplicates."""

    @abc.abstractmethod
    async def resolve(
        self, entities: list["ScientificEntity"]
    ) -> list["ScientificEntity"]:
        """Resolve a list of entities to their canonical forms.

        1. Checks each entity name / alias against a synonym registry.
        2. Groups entities by canonical ID.
        3. Merges properties, aliases, relationships, and provenance.

        Args:
            entities: Entities from one or more providers (post-normalisation).

        Returns:
            Deduplicated list of resolved, merged entities.
        """
        ...


class ISciLabProcessor(abc.ABC):
    """Processes normalised entities through the SciLab pipeline
    (parse → rank → deduplicate → summarise → context)."""

    @abc.abstractmethod
    async def process(
        self, entities: list["ScientificEntity"], context: "RetrievalContext"
    ) -> "SciLabResult":
        """Run the full SciLab processing pipeline.

        Args:
            entities: Normalised (and optionally resolved) entities.
            context: The original retrieval context.

        Returns:
            A :class:`SciLabResult` with summary, ranked entities, and context.
        """
        ...


class ICacheBackend(abc.ABC):
    """Abstract interface for a cache storage backend."""

    @abc.abstractmethod
    async def get(self, key: str) -> "CacheEntry | None":
        """Retrieve a cache entry by key.

        Returns:
            The :class:`CacheEntry` if found and not expired, else *None*.
        """
        ...

    @abc.abstractmethod
    async def set(self, key: str, value: Any, policy: "CachePolicy") -> None:
        """Store a value under *key* with the given *policy*."""
        ...

    @abc.abstractmethod
    async def delete(self, key: str) -> bool:
        """Remove the entry for *key*.

        Returns:
            True if an entry was removed.
        """
        ...

    @abc.abstractmethod
    async def clear(self) -> None:
        """Remove all entries from this backend."""
        ...

    @abc.abstractmethod
    async def evict_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            The number of entries evicted.
        """
        ...


class IRetrievalManager(abc.ABC):
    """Top-level orchestrator for the scientific knowledge retrieval pipeline."""

    @abc.abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        conversation_id: str | None = None,
        options: dict | None = None,
    ) -> "SciLabResult":
        """Execute a full retrieval pipeline for *query*.

        Args:
            query: Free-text user query.
            conversation_id: Optional conversation ID for caching.
            options: Free-form options dict.

        Returns:
            A :class:`SciLabResult` with the processed results.
        """
        ...

    @abc.abstractmethod
    async def get_data(self, request: "GetDataRequest") -> "GetDataResponse":
        """Fetch data for a specific entity from a specific provider.

        Args:
            request: A :class:`GetDataRequest` specifying provider, entity, etc.

        Returns:
            A :class:`GetDataResponse` with the result.
        """
        ...


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Data types
    "BrowserConfig",
    "NavigationResult",
    "NavigationEvent",
    "DocumentHandle",
    "CommandResult",
    "ExportResult",
    # Browser errors
    "BrowserError",
    "BrowserLaunchError",
    "BrowserNotRunning",
    "BrowserShutdownError",
    "BrowserTimeout",
    "NavigationTimeout",
    "SelectorTimeout",
    "ElementNotFound",
    "ElementNotInteractable",
    "ScriptExecutionError",
    "BrowserCrashError",
    "ExportError",
    # CAD errors
    "CommandError",
    "CommandNotFound",
    "InvalidArguments",
    "DocumentNotOpen",
    "NothingToUndo",
    "NothingToRedo",
    "DocumentLoadError",
    "DocumentSaveError",
    # Browser interfaces
    "IBrowserProvider",
    "IBrowserInstance",
    "IBrowserContext",
    # CAD interfaces
    "IDocumentManager",
    "ICommandExecutor",
    "IExportProvider",
    # Events
    "Event",
    "DocumentEvent",
    "DocumentCreated",
    "DocumentModified",
    "DocumentSaved",
    "DocumentClosed",
    "ObjectSelected",
    "BrowserEvent",
    "BrowserLaunched",
    "BrowserCrashed",
    "BrowserContextCreated",
    "NavigationCompleted",
    # Event bus
    "Subscription",
    "EventBus",
    # SciRetrieval interfaces
    "IIntentDomainClassifier",
    "IProvider",
    "INormalizer",
    "IEntityResolver",
    "ISciLabProcessor",
    "ICacheBackend",
    "IRetrievalManager",
]
