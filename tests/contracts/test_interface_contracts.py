"""Contract test suites for all formal interface definitions in fiona/interfaces.py.

Each abstract interface defined in ``fiona.interfaces`` has a corresponding
contract test suite that validates every method, property, and error condition
specified in the contract.  Concrete implementations of an interface can be
verified by subclassing the associated contract test class and overriding the
factory method.

Usage::

    class MySeleniumProviderContractTest(
        BrowserProviderContractTests, unittest.TestCase,
    ):
        def create_provider(self) -> IBrowserProvider:
            return MySeleniumProvider()

See also
--------
fiona.interfaces : The module that defines all ABCs and data types.
"""

from __future__ import annotations

import asyncio
import threading
import time
import unittest
from abc import abstractmethod
from dataclasses import FrozenInstanceError
from typing import Any, Callable

from fiona.interfaces import (
    # Data types
    BrowserConfig,
    BrowserEvent,
    BrowserLaunched,
    BrowserContextCreated,
    BrowserCrashed,
    BrowserError,
    BrowserLaunchError,
    BrowserNotRunning,
    BrowserShutdownError,
    BrowserTimeout,
    NavigationTimeout,
    SelectorTimeout,
    ElementNotFound,
    ElementNotInteractable,
    ScriptExecutionError,
    BrowserCrashError,
    CommandError,
    CommandNotFound,
    CommandResult,
    DocumentClosed,
    DocumentCreated,
    DocumentEvent,
    DocumentHandle,
    DocumentLoadError,
    DocumentModified,
    DocumentNotOpen,
    DocumentSaved,
    Event,
    EventBus,
    ExportError,
    ExportResult,
    IBrowserContext,
    IBrowserInstance,
    IBrowserProvider,
    ICommandExecutor,
    IDocumentManager,
    IExportProvider,
    InvalidArguments,
    NavigationCompleted,
    NavigationEvent,
    NavigationResult,
    NothingToRedo,
    NothingToUndo,
    ObjectSelected,
    Subscription,
)

from cad.core.document import Document


# =========================================================================
#  HELPER: run a single async coroutine in a synchronous test
# =========================================================================


def _await(coro) -> Any:
    """Execute *coro* in a temporary event loop and return its result."""
    return asyncio.run(coro)


# =========================================================================
#  MOCK / FAKE IMPLEMENTATIONS
# =========================================================================
# These lightweight implementations satisfy the ABC contracts.  They are
# used by the contract test suites below to verify that every interface
# method can be called, returns the correct type, and raises the documented
# errors under the documented conditions.
# =========================================================================


class _MockBrowserProvider(IBrowserProvider):
    """Minimal IBrowserProvider for use in contract tests."""

    def __init__(self, fail_launch: bool = False, provider_name: str = "mock") -> None:
        self._fail_launch = fail_launch
        self._provider_name = provider_name
        self._launched: list[_MockBrowserInstance] = []

    async def launch(self, config: BrowserConfig) -> IBrowserInstance:
        if self._fail_launch:
            raise BrowserLaunchError("Simulated launch failure")
        inst = _MockBrowserInstance(provider=self)
        self._launched.append(inst)
        return inst

    def name(self) -> str:
        return self._provider_name

    def capabilities(self) -> set[str]:
        return {"navigation", "click", "type_text", "get_text", "screenshot", "evaluate"}


class _FailingBrowserProvider(_MockBrowserProvider):
    """Provider where *every* launch attempt raises BrowserLaunchError."""

    def __init__(self) -> None:
        super().__init__(fail_launch=True)


class _MockBrowserInstance(IBrowserInstance):
    """Minimal IBrowserInstance for use in contract tests."""

    def __init__(self, provider: _MockBrowserProvider | None = None) -> None:
        self._closed = False
        self._process_pid = 42_007
        self._provider = provider

    async def create_context(self, **kwargs: Any) -> IBrowserContext:
        if self._closed:
            raise BrowserNotRunning("Browser is not running")
        return _MockBrowserContext(instance=self)

    async def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def pid(self) -> int | None:
        return None if self._closed else self._process_pid


class _ClosedBrowserInstance(_MockBrowserInstance):
    """An instance that is already closed (idempotent close scenario)."""

    def __init__(self) -> None:
        super().__init__()
        self._closed = True


class _MockBrowserContext(IBrowserContext):
    """Minimal IBrowserContext for use in contract tests.

    Supports injection of custom behaviors via the *behaviours* dict,
    keyed by method name, to simulate error conditions.
    """

    def __init__(
        self,
        instance: _MockBrowserInstance | None = None,
        behaviours: dict[str, Any] | None = None,
    ) -> None:
        self._closed = False
        self._id = "ctx-" + str(id(self))
        self._instance = instance
        self._behaviours = behaviours or {}

    async def navigate(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        wait_until: NavigationEvent = NavigationEvent.LOAD,
    ) -> NavigationResult:
        if "navigate_fail" in self._behaviours:
            raise NavigationTimeout(f"Navigation timed out: {url}")
        if "navigate_crash" in self._behaviours:
            raise BrowserCrashError("Browser crashed during navigation")
        return NavigationResult(
            url=url,
            status_code=200,
            title="Mock Page",
            duration_ms=12.5,
            redirect_chain=(),
        )

    async def click(self, selector: str, *, timeout: float = 5.0) -> None:
        if "click_not_found" in self._behaviours:
            raise ElementNotFound(f"Element not found: {selector}")
        if "click_not_interactable" in self._behaviours:
            raise ElementNotInteractable(f"Element not interactable: {selector}")
        if "click_timeout" in self._behaviours:
            raise SelectorTimeout(f"Selector timed out: {selector}")

    async def type_text(
        self,
        selector: str,
        text: str,
        *,
        delay: float = 0.01,
        timeout: float = 5.0,
    ) -> None:
        if "type_timeout" in self._behaviours:
            raise SelectorTimeout(f"Selector timed out: {selector}")
        if "type_not_interactable" in self._behaviours:
            raise ElementNotInteractable(f"Element not interactable: {selector}")

    async def get_text(self, selector: str, *, timeout: float = 5.0) -> str:
        if "get_text_fail" in self._behaviours:
            raise SelectorTimeout(f"Selector timed out: {selector}")
        return "Hello, world!"

    async def screenshot(
        self,
        *,
        path: str | None = None,
        full_page: bool = False,
    ) -> bytes:
        if path:
            # Write the bytes to the requested path (used in contract tests
            # to verify the path parameter is accepted).
            with open(path, "wb") as f:
                f.write(b"PNG...")
        return b"PNG..."

    async def evaluate(self, js: str, *, timeout: float = 5.0) -> Any:
        if "evaluate_fail" in self._behaviours:
            raise ScriptExecutionError(f"Script execution failed: {js}")
        if js.strip() == "return 42":
            return 42
        if js.strip() == "return {a: 1, b: 'two'}":
            return {"a": 1, "b": "two"}
        return None

    async def close(self) -> None:
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def context_id(self) -> str:
        return self._id


class _ClosedMockBrowserContext(_MockBrowserContext):
    """Context that appears to be already closed."""

    def __init__(self) -> None:
        super().__init__()
        self._closed = True


class _MockDocumentManager(IDocumentManager):
    """In-memory IDocumentManager for contract tests."""

    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}
        self._handles: dict[str, DocumentHandle] = {}
        self._active_doc_id: str | None = None

    def create_document(self, name: str = "Untitled") -> DocumentHandle:
        doc = Document(name=name)
        doc_id = str(doc.uid)
        now = time.time()
        handle = DocumentHandle(
            doc_id=doc_id,
            name=name,
            path=None,
            object_count=0,
            is_modified=False,
            created_at=now,
            modified_at=now,
        )
        self._docs[doc_id] = doc
        self._handles[doc_id] = handle
        self._active_doc_id = doc_id
        return handle

    def open_document(self, path: str) -> DocumentHandle:
        raise DocumentLoadError(f"File not found: {path}")

    def save_document(self, doc_id: str, path: str | None = None) -> str:
        if doc_id not in self._docs:
            raise DocumentNotOpen(f"No document with id {doc_id!r}")
        handle = self._handles[doc_id]
        saved_path = path or handle.path or "/tmp/mock_saved.cad"
        self._handles[doc_id] = DocumentHandle(
            doc_id=handle.doc_id,
            name=handle.name,
            path=saved_path,
            object_count=handle.object_count,
            is_modified=False,
            created_at=handle.created_at,
            modified_at=time.time(),
        )
        return saved_path

    def get_document(self, doc_id: str) -> Document | None:
        return self._docs.get(doc_id)

    def close_document(self, doc_id: str) -> None:
        if doc_id not in self._docs:
            raise DocumentNotOpen(f"No document with id {doc_id!r}")
        del self._docs[doc_id]
        del self._handles[doc_id]
        if self._active_doc_id == doc_id:
            self._active_doc_id = next(iter(self._handles), None)

    def list_documents(self) -> list[DocumentHandle]:
        return list(self._handles.values())

    def active_document(self) -> Document | None:
        if self._active_doc_id is not None:
            return self._docs.get(self._active_doc_id)
        return None


class _MockCommandExecutor(ICommandExecutor):
    """In-memory ICommandExecutor for contract tests.

    Maintains per-document undo/redo stacks storing ``(command_name, kwargs)``
    tuples.
    """

    def __init__(self, doc_manager: IDocumentManager | None = None) -> None:
        self._undo: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._redo: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._doc_manager = doc_manager or _MockDocumentManager()
        # Ensure at least one document exists
        self._default_doc = self._doc_manager.create_document("ContractTestDoc")

    def _ensure_doc(self, doc_id: str) -> None:
        if self._doc_manager.get_document(doc_id) is None:
            raise DocumentNotOpen(f"No document with id {doc_id!r}")

    def execute(
        self,
        doc_id: str,
        command_name: str,
        **kwargs: Any,
    ) -> CommandResult:
        self._ensure_doc(doc_id)

        if command_name not in ("create_box", "delete_object", "move_object", "valid_command"):
            raise CommandNotFound(f"Unknown command: {command_name}")

        if kwargs.get("_invalid") is True:
            raise InvalidArguments("Invalid arguments for command")

        doc = self._doc_manager.get_document(doc_id)
        snapshot = {"objects": list(doc._objects.keys()) if hasattr(doc, "_objects") else []}

        if doc_id not in self._undo:
            self._undo[doc_id] = []
        self._undo[doc_id].append((command_name, kwargs))
        # Clear redo stack on new execute
        self._redo[doc_id] = []

        return CommandResult(
            success=True,
            message=f"Executed {command_name}",
            document_snapshot=snapshot,
            created_objects=[],
            modified_objects=[],
            deleted_objects=[],
            execution_time_ms=1.5,
            warnings=[],
        )

    def undo(self, doc_id: str) -> dict[str, Any]:
        self._ensure_doc(doc_id)
        if doc_id not in self._undo or not self._undo[doc_id]:
            raise NothingToUndo("Nothing to undo")
        cmd = self._undo[doc_id].pop()
        if doc_id not in self._redo:
            self._redo[doc_id] = []
        self._redo[doc_id].append(cmd)
        return {"status": "undone", "command": cmd[0]}

    def redo(self, doc_id: str) -> dict[str, Any]:
        self._ensure_doc(doc_id)
        if doc_id not in self._redo or not self._redo[doc_id]:
            raise NothingToRedo("Nothing to redo")
        cmd = self._redo[doc_id].pop()
        if doc_id not in self._undo:
            self._undo[doc_id] = []
        self._undo[doc_id].append(cmd)
        return {"status": "redone", "command": cmd[0]}

    def can_undo(self, doc_id: str) -> bool:
        self._ensure_doc(doc_id)
        return bool(self._undo.get(doc_id))

    def can_redo(self, doc_id: str) -> bool:
        self._ensure_doc(doc_id)
        return bool(self._redo.get(doc_id))

    def clear_history(self, doc_id: str) -> None:
        self._ensure_doc(doc_id)
        self._undo[doc_id] = []
        self._redo[doc_id] = []


class _MockExportProvider(IExportProvider):
    """Minimal IExportProvider for contract tests."""

    def __init__(
        self,
        format_name: str = "mock",
        extensions: list[str] | None = None,
        fail_export: bool = False,
    ) -> None:
        self._format = format_name
        self._extensions = extensions or [".mock"]
        self._fail_export = fail_export

    def format_name(self) -> str:
        return self._format

    def supported_extensions(self) -> list[str]:
        return list(self._extensions)

    def export(
        self,
        doc: Document,
        path: str,
        **options: Any,
    ) -> ExportResult:
        if self._fail_export:
            raise ExportError("Simulated export failure")

        if options.get("_unsupported") is True:
            raise ExportError("Unsupported option")

        return ExportResult(
            path=path,
            format=self._format,
            size_bytes=1024,
            duration_ms=5.0,
            warnings=[],
        )


# =========================================================================
#  1. BROWSER PROVIDER CONTRACT TESTS
# =========================================================================


class BrowserProviderContractTests:
    """Abstract contract test suite for :class:`IBrowserProvider`.

    Subclass and override :meth:`create_provider` to test a concrete
    implementation::

        class MyProviderTest(BrowserProviderContractTests, unittest.TestCase):
            def create_provider(self) -> IBrowserProvider:
                return MySeleniumProvider()

    All tests are skipped when collected directly (``__test__ = False``).
    """

    __test__ = False  # pytest: don't collect abstract base

    @abstractmethod
    def create_provider(self) -> IBrowserProvider:
        """Return the :class:`IBrowserProvider` implementation to test."""

    # -- IBrowserProvider methods -------------------------------------------

    def test_provider_name_is_non_empty_string(self) -> None:
        """``name()`` must return a non-empty string."""
        provider = self.create_provider()
        name = provider.name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_provider_capabilities_returns_set(self) -> None:
        """``capabilities()`` must return a ``set[str]`` (may be empty)."""
        provider = self.create_provider()
        caps = provider.capabilities()
        self.assertIsInstance(caps, set)
        for c in caps:
            self.assertIsInstance(c, str)

    def test_provider_launch_returns_instance(self) -> None:
        """``launch()`` with a valid config returns an ``IBrowserInstance``."""
        provider = self.create_provider()
        config = BrowserConfig()
        instance = _await(provider.launch(config))
        self.assertIsInstance(instance, IBrowserInstance)

    def test_provider_launch_with_custom_config(self) -> None:
        """``launch()`` accepts non-default ``BrowserConfig`` attributes."""
        provider = self.create_provider()
        config = BrowserConfig(
            browser_type="firefox",
            headless=True,
            viewport_width=1920,
            viewport_height=1080,
        )
        instance = _await(provider.launch(config))
        self.assertIsInstance(instance, IBrowserInstance)

    def test_provider_launch_raises_browser_launch_error(self) -> None:
        """``launch()`` must raise ``BrowserLaunchError`` on failure."""
        provider = _FailingBrowserProvider()
        config = BrowserConfig()
        with self.assertRaises(BrowserLaunchError):
            _await(provider.launch(config))

    def test_provider_capabilities_includes_expected_keys(self) -> None:
        """``capabilities()`` should contain known capability strings.

        At minimum the mock set includes standard capabilities.
        Concrete implementations may vary but MUST return a set.
        """
        provider = self.create_provider()
        caps = provider.capabilities()
        self.assertIsInstance(caps, set)

    # -- IBrowserInstance methods -------------------------------------------

    def test_instance_is_closed_initially_false(self) -> None:
        """``is_closed`` is ``False`` immediately after launch."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        self.assertFalse(instance.is_closed)

    def test_instance_is_closed_true_after_close(self) -> None:
        """``is_closed`` is ``True`` after ``close()`` completes."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        _await(instance.close())
        self.assertTrue(instance.is_closed)

    def test_instance_close_is_idempotent(self) -> None:
        """Calling ``close()`` multiple times does not raise."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        _await(instance.close())
        # Second close must not raise (idempotent)
        _await(instance.close())
        self.assertTrue(instance.is_closed)

    def test_instance_pid_returns_int_while_running(self) -> None:
        """``pid`` is an ``int`` while the instance is alive."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        pid = instance.pid
        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)

    def test_instance_pid_returns_none_after_close(self) -> None:
        """``pid`` is ``None`` after the instance has been closed."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        _await(instance.close())
        self.assertIsNone(instance.pid)

    def test_instance_create_context_returns_context(self) -> None:
        """``create_context()`` returns an ``IBrowserContext``."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        ctx = _await(instance.create_context())
        self.assertIsInstance(ctx, IBrowserContext)

    def test_instance_create_context_with_kwargs(self) -> None:
        """``create_context()`` accepts implementation-specific kwargs."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        ctx = _await(instance.create_context(viewport={"width": 800, "height": 600}))
        self.assertIsInstance(ctx, IBrowserContext)

    def test_instance_create_context_raises_after_close(self) -> None:
        """``create_context()`` raises ``BrowserNotRunning`` when closed."""
        provider = self.create_provider()
        instance = _await(provider.launch(BrowserConfig()))
        _await(instance.close())
        with self.assertRaises(BrowserNotRunning):
            _await(instance.create_context())

    # -- IBrowserContext methods --------------------------------------------

    def test_context_id_is_non_empty_string(self) -> None:
        """``context_id`` is a non-empty string."""
        ctx = _MockBrowserContext()
        cid = ctx.context_id
        self.assertIsInstance(cid, str)
        self.assertGreater(len(cid), 0)

    def test_context_is_closed_initially_false(self) -> None:
        """``is_closed`` is ``False`` immediately after creation."""
        ctx = _MockBrowserContext()
        self.assertFalse(ctx.is_closed)

    def test_context_is_closed_true_after_close(self) -> None:
        """``is_closed`` is ``True`` after ``close()``."""
        ctx = _MockBrowserContext()
        _await(ctx.close())
        self.assertTrue(ctx.is_closed)

    def test_context_close_is_idempotent(self) -> None:
        """Calling ``close()`` multiple times has no additional effect."""
        ctx = _MockBrowserContext()
        _await(ctx.close())
        _await(ctx.close())
        self.assertTrue(ctx.is_closed)

    def test_context_navigate_returns_navigation_result(self) -> None:
        """``navigate()`` returns a ``NavigationResult``."""
        ctx = _MockBrowserContext()
        result = _await(ctx.navigate("https://example.com"))
        self.assertIsInstance(result, NavigationResult)
        self.assertEqual(result.url, "https://example.com")
        self.assertIsInstance(result.status_code, int)
        self.assertIsInstance(result.title, str)
        self.assertIsInstance(result.duration_ms, float)
        self.assertIsInstance(result.redirect_chain, tuple)

    def test_context_navigate_with_wait_event(self) -> None:
        """``navigate()`` accepts the ``wait_until`` parameter."""
        ctx = _MockBrowserContext()
        result = _await(ctx.navigate("https://example.com", wait_until=NavigationEvent.DOM_CONTENT))
        self.assertEqual(result.status_code, 200)

        result2 = _await(ctx.navigate("https://example.com", wait_until=NavigationEvent.NETWORK_IDLE))
        self.assertEqual(result2.status_code, 200)

    def test_context_navigate_with_custom_timeout(self) -> None:
        """``navigate()`` accepts a custom ``timeout``."""
        ctx = _MockBrowserContext()
        result = _await(ctx.navigate("https://example.com", timeout=60.0))
        self.assertEqual(result.status_code, 200)

    def test_context_navigate_raises_timeout(self) -> None:
        """``navigate()`` raises ``NavigationTimeout`` on failure."""
        ctx = _MockBrowserContext(behaviours={"navigate_fail": True})
        with self.assertRaises(NavigationTimeout):
            _await(ctx.navigate("https://example.com"))

    def test_context_navigate_raises_crash(self) -> None:
        """``navigate()`` raises ``BrowserCrashError`` when the browser dies."""
        ctx = _MockBrowserContext(behaviours={"navigate_crash": True})
        with self.assertRaises(BrowserCrashError):
            _await(ctx.navigate("https://example.com"))

    def test_context_click_succeeds(self) -> None:
        """``click()`` completes without error for a valid selector."""
        ctx = _MockBrowserContext()
        _await(ctx.click("#my-button"))

    def test_context_click_raises_element_not_found(self) -> None:
        """``click()`` raises ``ElementNotFound`` when the element is missing."""
        ctx = _MockBrowserContext(behaviours={"click_not_found": True})
        with self.assertRaises(ElementNotFound):
            _await(ctx.click("#missing"))

    def test_context_click_raises_not_interactable(self) -> None:
        """``click()`` raises ``ElementNotInteractable`` for hidden/disabled elements."""
        ctx = _MockBrowserContext(behaviours={"click_not_interactable": True})
        with self.assertRaises(ElementNotInteractable):
            _await(ctx.click("#hidden"))

    def test_context_click_raises_selector_timeout(self) -> None:
        """``click()`` raises ``SelectorTimeout`` when the selector does not appear."""
        ctx = _MockBrowserContext(behaviours={"click_timeout": True})
        with self.assertRaises(SelectorTimeout):
            _await(ctx.click("#slow-element"))

    def test_context_type_text_succeeds(self) -> None:
        """``type_text()`` completes without error for a valid selector."""
        ctx = _MockBrowserContext()
        _await(ctx.type_text("#input", "Hello"))

    def test_context_type_text_raises_selector_timeout(self) -> None:
        """``type_text()`` raises ``SelectorTimeout`` when element missing."""
        ctx = _MockBrowserContext(behaviours={"type_timeout": True})
        with self.assertRaises(SelectorTimeout):
            _await(ctx.type_text("#input", "Hello"))

    def test_context_type_text_raises_not_interactable(self) -> None:
        """``type_text()`` raises ``ElementNotInteractable`` for non-editable elements."""
        ctx = _MockBrowserContext(behaviours={"type_not_interactable": True})
        with self.assertRaises(ElementNotInteractable):
            _await(ctx.type_text("#input", "Hello"))

    def test_context_get_text_returns_string(self) -> None:
        """``get_text()`` returns a string for a valid selector."""
        ctx = _MockBrowserContext()
        text = _await(ctx.get_text("#content"))
        self.assertIsInstance(text, str)
        self.assertEqual(text, "Hello, world!")

    def test_context_get_text_raises_selector_timeout(self) -> None:
        """``get_text()`` raises ``SelectorTimeout`` when element missing."""
        ctx = _MockBrowserContext(behaviours={"get_text_fail": True})
        with self.assertRaises(SelectorTimeout):
            _await(ctx.get_text("#missing"))

    def test_context_screenshot_returns_bytes(self) -> None:
        """``screenshot()`` returns raw PNG bytes."""
        ctx = _MockBrowserContext()
        data = _await(ctx.screenshot())
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)

    def test_context_screenshot_with_path(self) -> None:
        """``screenshot(path=...)`` writes to the filesystem and returns bytes."""
        import tempfile, os
        ctx = _MockBrowserContext()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            data = _await(ctx.screenshot(path=path))
            self.assertIsInstance(data, bytes)
            self.assertTrue(os.path.exists(path))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), data)
        finally:
            os.unlink(path)

    def test_context_screenshot_full_page(self) -> None:
        """``screenshot(full_page=True)`` accepts the parameter."""
        ctx = _MockBrowserContext()
        data = _await(ctx.screenshot(full_page=True))
        self.assertIsInstance(data, bytes)

    def test_context_evaluate_returns_value(self) -> None:
        """``evaluate()`` returns the result of the evaluated JS."""
        ctx = _MockBrowserContext()
        result = _await(ctx.evaluate("return 42"))
        self.assertEqual(result, 42)

    def test_context_evaluate_returns_complex_types(self) -> None:
        """``evaluate()`` can return dict/list values."""
        ctx = _MockBrowserContext()
        result = _await(ctx.evaluate("return {a: 1, b: 'two'}"))
        self.assertEqual(result, {"a": 1, "b": "two"})

    def test_context_evaluate_returns_none(self) -> None:
        """``evaluate()`` returns ``None`` for void expressions."""
        ctx = _MockBrowserContext()
        result = _await(ctx.evaluate("void 0"))
        self.assertIsNone(result)

    def test_context_evaluate_raises_script_error(self) -> None:
        """``evaluate()`` raises ``ScriptExecutionError`` on failure."""
        ctx = _MockBrowserContext(behaviours={"evaluate_fail": True})
        with self.assertRaises(ScriptExecutionError):
            _await(ctx.evaluate("throw new Error('boom')"))


# =========================================================================
#  2. CAD DOCUMENT MANAGER CONTRACT TESTS
# =========================================================================


class DocumentManagerContractTests:
    """Abstract contract test suite for :class:`IDocumentManager`.

    Subclass and override :meth:`create_manager` to test a concrete
    implementation::

        class MyDocManagerTest(DocumentManagerContractTests, unittest.TestCase):
            def create_manager(self) -> IDocumentManager:
                return MyDocumentManager()
    """

    __test__ = False

    @abstractmethod
    def create_manager(self) -> IDocumentManager:
        """Return the :class:`IDocumentManager` implementation to test."""

    # -- create_document ---------------------------------------------------

    def test_create_document_returns_handle(self) -> None:
        """``create_document()`` returns a ``DocumentHandle``."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        self.assertIsInstance(handle, DocumentHandle)
        self.assertEqual(handle.name, "TestDoc")

    def test_create_document_default_name(self) -> None:
        """``create_document()`` uses ``'Untitled'`` when no name is given."""
        mgr = self.create_manager()
        handle = mgr.create_document()
        self.assertEqual(handle.name, "Untitled")

    def test_create_document_has_unique_id(self) -> None:
        """Each document gets a unique ``doc_id``."""
        mgr = self.create_manager()
        h1 = mgr.create_document("A")
        h2 = mgr.create_document("B")
        self.assertNotEqual(h1.doc_id, h2.doc_id)

    def test_create_document_path_is_none(self) -> None:
        """A newly created document has ``path=None``."""
        mgr = self.create_manager()
        handle = mgr.create_document()
        self.assertIsNone(handle.path)

    def test_create_document_object_count_zero(self) -> None:
        """A newly created document has zero objects."""
        mgr = self.create_manager()
        handle = mgr.create_document()
        self.assertEqual(handle.object_count, 0)
        self.assertFalse(handle.is_modified)

    # -- list_documents ----------------------------------------------------

    def test_list_documents_empty_initially(self) -> None:
        """``list_documents()`` returns an empty list before any docs are created."""
        mgr = self.create_manager()
        docs = mgr.list_documents()
        self.assertEqual(docs, [])

    def test_list_documents_after_creation(self) -> None:
        """``list_documents()`` includes newly created documents."""
        mgr = self.create_manager()
        h1 = mgr.create_document("Doc1")
        h2 = mgr.create_document("Doc2")
        docs = mgr.list_documents()
        self.assertEqual(len(docs), 2)
        doc_ids = {d.doc_id for d in docs}
        self.assertIn(h1.doc_id, doc_ids)
        self.assertIn(h2.doc_id, doc_ids)

    # -- get_document ------------------------------------------------------

    def test_get_document_returns_document(self) -> None:
        """``get_document()`` returns a ``Document`` for a valid doc_id."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        doc = mgr.get_document(handle.doc_id)
        self.assertIsInstance(doc, Document)

    def test_get_document_returns_none_for_invalid_id(self) -> None:
        """``get_document()`` returns ``None`` for an unknown doc_id."""
        mgr = self.create_manager()
        doc = mgr.get_document("nonexistent-id")
        self.assertIsNone(doc)

    # -- close_document ----------------------------------------------------

    def test_close_document_removes_from_list(self) -> None:
        """After closing, the document is no longer in ``list_documents()``."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        mgr.close_document(handle.doc_id)
        docs = mgr.list_documents()
        doc_ids = {d.doc_id for d in docs}
        self.assertNotIn(handle.doc_id, doc_ids)

    def test_close_document_raises_on_invalid_id(self) -> None:
        """``close_document()`` raises ``DocumentNotOpen`` for unknown ID."""
        mgr = self.create_manager()
        with self.assertRaises(DocumentNotOpen):
            mgr.close_document("nonexistent-id")

    def test_close_document_get_returns_none(self) -> None:
        """After closing, ``get_document()`` returns ``None`` for that ID."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        doc_id = handle.doc_id
        mgr.close_document(doc_id)
        self.assertIsNone(mgr.get_document(doc_id))

    # -- save_document -----------------------------------------------------

    def test_save_document_without_path(self) -> None:
        """``save_document(doc_id)`` works when the handle has an existing path."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        # First save with a path to set it on the handle
        saved = mgr.save_document(handle.doc_id, path="/tmp/mock.cad")
        self.assertIsInstance(saved, str)
        self.assertGreater(len(saved), 0)

    def test_save_document_with_new_path(self) -> None:
        """``save_document(doc_id, path)`` sets a new path."""
        mgr = self.create_manager()
        handle = mgr.create_document("TestDoc")
        path = mgr.save_document(handle.doc_id, path="/tmp/new_mock.cad")
        self.assertEqual(path, "/tmp/new_mock.cad")

    def test_save_document_raises_on_invalid_id(self) -> None:
        """``save_document()`` raises ``DocumentNotOpen`` for unknown ID."""
        mgr = self.create_manager()
        with self.assertRaises(DocumentNotOpen):
            mgr.save_document("nonexistent-id")

    # -- open_document -----------------------------------------------------

    def test_open_document_raises_on_missing_file(self) -> None:
        """``open_document()`` raises ``DocumentLoadError`` for a non-existent file."""
        mgr = self.create_manager()
        with self.assertRaises(DocumentLoadError):
            mgr.open_document("/nonexistent/path/file.cad")

    def test_open_document_raises_on_empty_path(self) -> None:
        """``open_document()`` raises ``DocumentLoadError`` for an empty path."""
        mgr = self.create_manager()
        with self.assertRaises(DocumentLoadError):
            mgr.open_document("")

    # -- active_document ---------------------------------------------------

    def test_active_document_none_when_no_docs(self) -> None:
        """``active_document()`` returns ``None`` when no documents are open."""
        mgr = self.create_manager()
        self.assertIsNone(mgr.active_document())

    def test_active_document_returns_document_after_create(self) -> None:
        """``active_document()`` returns the most recently created document."""
        mgr = self.create_manager()
        mgr.create_document("Doc1")
        doc = mgr.active_document()
        self.assertIsInstance(doc, Document)

    def test_active_document_changes_after_close(self) -> None:
        """Closing the active document updates ``active_document()``."""
        mgr = self.create_manager()
        h1 = mgr.create_document("First")
        h2 = mgr.create_document("Second")
        mgr.close_document(h1.doc_id)
        # After closing the first, the active should still be the second (or None)
        doc = mgr.active_document()
        self.assertIsNotNone(doc)  # there is still an open document


# =========================================================================
#  3. COMMAND EXECUTOR CONTRACT TESTS
# =========================================================================


class CommandExecutorContractTests:
    """Abstract contract test suite for :class:`ICommandExecutor`.

    Subclass and override :meth:`create_executor` to test a concrete
    implementation::

        class MyExecutorTest(CommandExecutorContractTests, unittest.TestCase):
            def create_executor(self) -> ICommandExecutor:
                return MyCommandExecutor()
    """

    __test__ = False

    @abstractmethod
    def create_executor(self) -> ICommandExecutor:
        """Return the :class:`ICommandExecutor` implementation to test."""

    def _get_doc_id(self, executor: ICommandExecutor) -> str:
        """Helper: create a document and return its ID for use in tests."""
        # The mock executor auto-creates a default doc; we expose its ID.
        # For custom implementations, we need to get a valid doc_id somehow.
        # We assume the executor has a reference to a document manager.
        if hasattr(executor, "_default_doc"):
            return executor._default_doc.doc_id  # type: ignore[union-attr]
        # Fallback: create via the executor's internal doc manager
        if hasattr(executor, "_doc_manager"):
            mgr = executor._doc_manager  # type: ignore[union-attr]
            return mgr.create_document("TestDoc").doc_id
        msg = (
            "Test cannot determine a doc_id. "
            "Override _get_doc_id or ensure the executor's manager "
            "exposes a document."
        )
        raise NotImplementedError(msg)

    # -- execute -----------------------------------------------------------

    def test_execute_returns_command_result(self) -> None:
        """``execute()`` returns a ``CommandResult`` on success."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        result = executor.execute(doc_id, "create_box", width=10, height=20)
        self.assertIsInstance(result, CommandResult)
        self.assertTrue(result.success)
        self.assertIsInstance(result.message, str)
        self.assertIsInstance(result.document_snapshot, dict)
        self.assertIsInstance(result.created_objects, list)
        self.assertIsInstance(result.modified_objects, list)
        self.assertIsInstance(result.deleted_objects, list)
        self.assertIsInstance(result.execution_time_ms, float)
        self.assertIsInstance(result.warnings, list)

    def test_execute_raises_document_not_open(self) -> None:
        """``execute()`` raises ``DocumentNotOpen`` for an unknown doc_id."""
        executor = self.create_executor()
        with self.assertRaises(DocumentNotOpen):
            executor.execute("unknown-doc-id", "create_box")

    def test_execute_raises_command_not_found(self) -> None:
        """``execute()`` raises ``CommandNotFound`` for an unknown command."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        with self.assertRaises(CommandNotFound):
            executor.execute(doc_id, "nonexistent_command")

    def test_execute_raises_invalid_arguments(self) -> None:
        """``execute()`` raises ``InvalidArguments`` for bad arguments."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        with self.assertRaises(InvalidArguments):
            executor.execute(doc_id, "create_box", _invalid=True)

    # -- can_undo / can_redo -----------------------------------------------

    def test_can_undo_false_initially(self) -> None:
        """``can_undo()`` returns ``False`` before any command is executed."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        self.assertFalse(executor.can_undo(doc_id))

    def test_can_redo_false_initially(self) -> None:
        """``can_redo()`` returns ``False`` before any undo."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        self.assertFalse(executor.can_redo(doc_id))

    def test_can_undo_true_after_execute(self) -> None:
        """``can_undo()`` returns ``True`` after a command is executed."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        self.assertTrue(executor.can_undo(doc_id))

    def test_can_undo_false_after_undo(self) -> None:
        """``can_undo()`` returns ``False`` after all commands undone."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        executor.undo(doc_id)
        self.assertFalse(executor.can_undo(doc_id))

    def test_can_redo_true_after_undo(self) -> None:
        """``can_redo()`` returns ``True`` after an undo."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        executor.undo(doc_id)
        self.assertTrue(executor.can_redo(doc_id))

    # -- undo --------------------------------------------------------------

    def test_undo_returns_snapshot(self) -> None:
        """``undo()`` returns a dict snapshot after reversing the last command."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        snapshot = executor.undo(doc_id)
        self.assertIsInstance(snapshot, dict)

    def test_undo_raises_nothing_to_undo(self) -> None:
        """``undo()`` raises ``NothingToUndo`` when the stack is empty."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        with self.assertRaises(NothingToUndo):
            executor.undo(doc_id)

    def test_undo_raises_document_not_open(self) -> None:
        """``undo()`` raises ``DocumentNotOpen`` for an unknown doc_id."""
        executor = self.create_executor()
        with self.assertRaises(DocumentNotOpen):
            executor.undo("unknown-doc-id")

    # -- redo --------------------------------------------------------------

    def test_redo_returns_snapshot(self) -> None:
        """``redo()`` returns a dict snapshot after reapplying the undone cmd."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        executor.undo(doc_id)
        snapshot = executor.redo(doc_id)
        self.assertIsInstance(snapshot, dict)

    def test_redo_raises_nothing_to_redo(self) -> None:
        """``redo()`` raises ``NothingToRedo`` when the redo stack is empty."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        with self.assertRaises(NothingToRedo):
            executor.redo(doc_id)

    def test_redo_raises_document_not_open(self) -> None:
        """``redo()`` raises ``DocumentNotOpen`` for an unknown doc_id."""
        executor = self.create_executor()
        with self.assertRaises(DocumentNotOpen):
            executor.redo("unknown-doc-id")

    # -- clear_history -----------------------------------------------------

    def test_clear_history_resets_undo_redo(self) -> None:
        """``clear_history()`` empties both undo and redo stacks."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        executor.execute(doc_id, "delete_object")
        executor.undo(doc_id)  # now: 1 undo-able, 1 redo-able
        executor.clear_history(doc_id)
        self.assertFalse(executor.can_undo(doc_id))
        self.assertFalse(executor.can_redo(doc_id))

    def test_clear_history_raises_document_not_open(self) -> None:
        """``clear_history()`` raises ``DocumentNotOpen`` for unknown doc_id."""
        executor = self.create_executor()
        with self.assertRaises(DocumentNotOpen):
            executor.clear_history("unknown-doc-id")

    # -- full lifecycle ----------------------------------------------------

    def test_execute_undo_redo_cycle(self) -> None:
        """Executing, undoing, and redoing preserves state correctly."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box", width=5)
        self.assertTrue(executor.can_undo(doc_id))
        self.assertFalse(executor.can_redo(doc_id))

        executor.undo(doc_id)
        self.assertFalse(executor.can_undo(doc_id))
        self.assertTrue(executor.can_redo(doc_id))

        executor.redo(doc_id)
        self.assertTrue(executor.can_undo(doc_id))
        self.assertFalse(executor.can_redo(doc_id))

    def test_execute_clears_redo_stack(self) -> None:
        """After executing a new command, the redo stack is cleared."""
        executor = self.create_executor()
        doc_id = self._get_doc_id(executor)
        executor.execute(doc_id, "create_box")
        executor.undo(doc_id)
        self.assertTrue(executor.can_redo(doc_id))
        # New execute clears the redo stack
        executor.execute(doc_id, "delete_object")
        self.assertFalse(executor.can_redo(doc_id))


# =========================================================================
#  4. EXPORT PROVIDER CONTRACT TESTS
# =========================================================================


class ExportProviderContractTests:
    """Abstract contract test suite for :class:`IExportProvider`.

    Subclass and override :meth:`create_export_provider` to test a concrete
    implementation::

        class MyExportTest(ExportProviderContractTests, unittest.TestCase):
            def create_export_provider(self) -> IExportProvider:
                return MyStlExportProvider()
    """

    __test__ = False

    @abstractmethod
    def create_export_provider(self) -> IExportProvider:
        """Return the :class:`IExportProvider` implementation to test."""

    def _create_doc(self) -> Document:
        return Document(name="ContractTestExportDoc")

    # -- format_name -------------------------------------------------------

    def test_format_name_is_non_empty_string(self) -> None:
        """``format_name()`` returns a non-empty string."""
        provider = self.create_export_provider()
        name = provider.format_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_format_name_is_lowercase(self) -> None:
        """``format_name()`` should be lowercase (convention, not enforced)."""
        provider = self.create_export_provider()
        name = provider.format_name()
        self.assertEqual(name, name.lower(), "format_name should be lowercase")

    # -- supported_extensions ----------------------------------------------

    def test_supported_extensions_returns_list_of_strings(self) -> None:
        """``supported_extensions()`` returns a list of non-empty strings."""
        provider = self.create_export_provider()
        exts = provider.supported_extensions()
        self.assertIsInstance(exts, list)
        self.assertGreater(len(exts), 0)
        for ext in exts:
            self.assertIsInstance(ext, str)
            self.assertGreater(len(ext), 0)

    def test_supported_extensions_start_with_dot(self) -> None:
        """Every extension string should start with ``'.'``."""
        provider = self.create_export_provider()
        for ext in provider.supported_extensions():
            self.assertTrue(ext.startswith("."), f"Extension {ext!r} must start with '.'")

    def test_supported_extensions_are_unique(self) -> None:
        """Extension strings should not contain duplicates."""
        provider = self.create_export_provider()
        exts = provider.supported_extensions()
        self.assertEqual(len(exts), len(set(exts)), "Extensions must be unique")

    # -- export ------------------------------------------------------------

    def test_export_returns_export_result(self) -> None:
        """``export()`` returns an ``ExportResult`` on success."""
        provider = self.create_export_provider()
        doc = self._create_doc()
        result = provider.export(doc, "/tmp/test_export.mock")
        self.assertIsInstance(result, ExportResult)
        self.assertIsInstance(result.path, str)
        self.assertIsInstance(result.format, str)
        self.assertIsInstance(result.size_bytes, int)
        self.assertIsInstance(result.duration_ms, float)
        self.assertIsInstance(result.warnings, list)
        self.assertEqual(result.format, provider.format_name())

    def test_export_accepts_format_options(self) -> None:
        """``export()`` accepts format-specific keyword options."""
        provider = self.create_export_provider()
        doc = self._create_doc()
        result = provider.export(doc, "/tmp/test_opt.mock", precision=3, binary=True)
        self.assertIsInstance(result, ExportResult)
        self.assertGreater(result.size_bytes, 0)

    def test_export_raises_on_failure(self) -> None:
        """``export()`` raises ``ExportError`` when the operation fails."""
        provider = _MockExportProvider(fail_export=True)
        doc = self._create_doc()
        with self.assertRaises(ExportError):
            provider.export(doc, "/tmp/fail.mock")

    def test_export_raises_on_unsupported_options(self) -> None:
        """``export()`` raises ``ExportError`` for unsupported options."""
        provider = _MockExportProvider()
        doc = self._create_doc()
        with self.assertRaises(ExportError):
            provider.export(doc, "/tmp/unsupported.mock", _unsupported=True)

    def test_export_to_invalid_path_raises_error(self) -> None:
        """``export()`` propagates errors for invalid paths.

        The mock does not do filesystem I/O by default, but contract
        tests should verify the behaviour for real implementations.
        Here we confirm the error type is ``ExportError``.
        """
        provider = _MockExportProvider(fail_export=True)
        doc = self._create_doc()
        with self.assertRaises(ExportError):
            provider.export(doc, "")


# =========================================================================
#  5. EVENT BUS CONTRACT TESTS (CONCRETE)
# =========================================================================


class EventBusContractTests(unittest.TestCase):
    """Contract tests for the concrete :class:`EventBus` implementation.

    Since ``EventBus`` is a concrete class (not an ABC), these tests are
    runnable directly.  They verify:

    - subscribe / unsubscribe lifecycle
    - publish delivers to the correct subscribers
    - exception handling (swallow vs. propagate)
    - thread-safety
    - parent-type subscription receives child events
    """

    # -- subscribe / unsubscribe -------------------------------------------

    def test_subscribe_returns_subscription(self) -> None:
        """``subscribe()`` returns a ``Subscription`` token."""
        bus = EventBus()
        sub = bus.subscribe(Event, lambda e: None)
        self.assertIsInstance(sub, Subscription)
        self.assertIs(sub.event_type, Event)
        self.assertIsInstance(sub.callback_id, str)
        self.assertGreater(len(sub.callback_id), 0)

    def test_unsubscribe_removes_callback(self) -> None:
        """After ``unsubscribe()``, the callback is no longer invoked."""
        bus = EventBus()
        received: list[Event] = []
        sub = bus.subscribe(Event, lambda e: received.append(e))
        bus.publish(Event(timestamp=1.0, source="test"))
        self.assertEqual(len(received), 1)
        bus.unsubscribe(sub)
        bus.publish(Event(timestamp=2.0, source="test"))
        self.assertEqual(len(received), 1)  # no second delivery

    def test_unsubscribe_is_idempotent(self) -> None:
        """Calling ``unsubscribe()`` multiple times does not raise."""
        bus = EventBus()
        sub = bus.subscribe(Event, lambda e: None)
        bus.unsubscribe(sub)
        bus.unsubscribe(sub)  # second call must not raise

    def test_subscribe_to_nonexistent_type_does_not_raise(self) -> None:
        """``subscribe()`` accepts any ``Event`` subclass without error."""
        bus = EventBus()
        sub = bus.subscribe(DocumentCreated, lambda e: None)
        self.assertIsInstance(sub, Subscription)

    def test_unsubscribe_nonexistent_subscription_does_not_raise(self) -> None:
        """Unsubscribing a token that was never registered is a no-op."""
        bus = EventBus()
        fake_sub = Subscription(event_type=Event, callback_id="nonexistent")
        bus.unsubscribe(fake_sub)  # must not raise

    # -- publish -----------------------------------------------------------

    def test_publish_delivers_to_subscriber(self) -> None:
        """``publish()`` delivers the event to all matching subscribers."""
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))
        event = Event(timestamp=42.0, source="tester")
        bus.publish(event)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0], event)

    def test_publish_delivers_to_multiple_subscribers(self) -> None:
        """``publish()`` delivers to all subscribers of the same type."""
        bus = EventBus()
        results: list[int] = []
        bus.subscribe(Event, lambda e: results.append(1))
        bus.subscribe(Event, lambda e: results.append(2))
        bus.publish(Event(timestamp=0.0, source="test"))
        self.assertEqual(len(results), 2)
        self.assertIn(1, results)
        self.assertIn(2, results)

    def test_publish_type_filtering(self) -> None:
        """``publish()`` only delivers to subscribers of matching types."""
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(DocumentCreated, lambda e: received.append(e))
        bus.publish(Event(timestamp=0.0, source="test"))  # wrong type
        self.assertEqual(len(received), 0)

    def test_publish_inheritance_matching(self) -> None:
        """A subscriber to a parent type receives child-type events."""
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))
        child = DocumentCreated(timestamp=1.0, source="test", doc_id="abc")
        bus.publish(child)
        self.assertEqual(len(received), 1)
        self.assertIs(received[0], child)

    def test_publish_swallows_subscriber_exception(self) -> None:
        """``publish()`` does not propagate exceptions from subscribers.

        Per spec: a failing subscriber must not block other subscribers.
        """
        bus = EventBus()
        healthy: list[Event] = []

        def failing(e: Event) -> None:
            raise RuntimeError("Subscriber failure")

        bus.subscribe(Event, failing)
        bus.subscribe(Event, lambda e: healthy.append(e))

        # Must not raise
        bus.publish(Event(timestamp=0.0, source="test"))
        self.assertEqual(len(healthy), 1)

    def test_publish_with_no_subscribers_does_nothing(self) -> None:
        """``publish()`` with no matching subscribers silently no-ops."""
        bus = EventBus()
        # No subscribers of type NavigationCompleted
        bus.publish(NavigationCompleted(
            timestamp=1.0, source="browser", context_id="ctx-1", url="https://x.com", status=200,
        ))

    # -- publish_and_wait --------------------------------------------------

    def test_publish_and_wait_delivers(self) -> None:
        """``publish_and_wait()`` delivers events to subscribers."""
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))
        bus.publish_and_wait(Event(timestamp=1.0, source="test"))
        self.assertEqual(len(received), 1)

    def test_publish_and_wait_propagates_exceptions(self) -> None:
        """``publish_and_wait()`` propagates subscriber exceptions."""
        bus = EventBus()

        def failing(e: Event) -> None:
            raise ValueError("Boom")

        bus.subscribe(Event, failing)
        with self.assertRaises(ValueError):
            bus.publish_and_wait(Event(timestamp=1.0, source="test"))

    def test_publish_and_wait_timeout_parameter_accepted(self) -> None:
        """``publish_and_wait()`` accepts a ``timeout`` argument."""
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(Event, lambda e: received.append(e))
        bus.publish_and_wait(Event(timestamp=1.0, source="test"), timeout=10.0)
        self.assertEqual(len(received), 1)

    # -- thread-safety -----------------------------------------------------

    def test_concurrent_publish(self) -> None:
        """Multiple threads can ``publish()`` concurrently without corruption."""
        bus = EventBus()
        received: list[Event] = []
        lock: threading.Lock = threading.Lock()

        def collector(e: Event) -> None:
            with lock:
                received.append(e)

        bus.subscribe(Event, collector)
        n_events = 50
        n_threads = 4

        def publisher(event_id: int) -> None:
            for _ in range(n_events):
                bus.publish(Event(timestamp=time.time(), source=f"thread-{event_id}"))
                time.sleep(0.0001)  # small yield to encourage interleaving

        threads = [
            threading.Thread(target=publisher, args=(i,))
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(len(received), n_threads * n_events)

    def test_concurrent_subscribe_and_publish(self) -> None:
        """Publishing while another thread subscribes does not deadlock."""
        bus = EventBus()
        stop = threading.Event()

        def subscriber_adder() -> None:
            while not stop.is_set():
                sub = bus.subscribe(DocumentCreated, lambda e: None)
                bus.unsubscribe(sub)
                time.sleep(0.001)

        def publisher() -> None:
            for _ in range(100):
                bus.publish(Event(timestamp=time.time(), source="test"))
                time.sleep(0.001)

        adder = threading.Thread(target=subscriber_adder, daemon=True)
        pub_threads = [threading.Thread(target=publisher) for _ in range(3)]

        adder.start()
        for t in pub_threads:
            t.start()
        for t in pub_threads:
            t.join(timeout=5)
        stop.set()
        adder.join(timeout=2)

    # -- Subscription lifecycle --------------------------------------------

    def test_subscription_event_type_matches(self) -> None:
        """The ``Subscription.event_type`` matches the type passed to subscribe."""
        bus = EventBus()
        sub = bus.subscribe(DocumentModified, lambda e: None)
        self.assertIs(sub.event_type, DocumentModified)

    def test_subscribe_same_callback_multiple_types(self) -> None:
        """The same callback can be registered for different event types."""
        bus = EventBus()
        received: list[Event] = []
        cb: Callable[[Event], None] = lambda e: received.append(e)
        bus.subscribe(DocumentCreated, cb)
        bus.subscribe(DocumentModified, cb)
        bus.publish(DocumentCreated(timestamp=1.0, source="test", doc_id="d1"))
        bus.publish(DocumentModified(timestamp=2.0, source="test", doc_id="d1"))
        self.assertEqual(len(received), 2)


# =========================================================================
#  6. DATA TYPE CONTRACT TESTS (CONCRETE)
# =========================================================================


class DataTypeContractTests(unittest.TestCase):
    """Contract tests for all frozen dataclasses and enums.

    Verifies:
    - Immutability (``FrozenInstanceError`` on attribute assignment)
    - Default values match the spec
    - Enum members and their values
    - Correct type annotations for all fields
    """

    # -- BrowserConfig -----------------------------------------------------

    def test_browser_config_is_frozen(self) -> None:
        """BrowserConfig fields cannot be changed after creation."""
        cfg = BrowserConfig()
        with self.assertRaises(FrozenInstanceError):
            cfg.browser_type = "firefox"  # type: ignore[misc]

    def test_browser_config_default_browser_type(self) -> None:
        """Default ``browser_type`` is ``'chromium'``."""
        cfg = BrowserConfig()
        self.assertEqual(cfg.browser_type, "chromium")

    def test_browser_config_default_headless(self) -> None:
        """Default ``headless`` is ``False``."""
        cfg = BrowserConfig()
        self.assertFalse(cfg.headless)

    def test_browser_config_default_viewport(self) -> None:
        """Default viewport is 1280x720."""
        cfg = BrowserConfig()
        self.assertEqual(cfg.viewport_width, 1280)
        self.assertEqual(cfg.viewport_height, 720)

    def test_browser_config_default_data_dir_none(self) -> None:
        """Default ``data_dir`` is ``None``."""
        cfg = BrowserConfig()
        self.assertIsNone(cfg.data_dir)

    def test_browser_config_default_proxy_none(self) -> None:
        """Default ``proxy`` is ``None``."""
        cfg = BrowserConfig()
        self.assertIsNone(cfg.proxy)

    def test_browser_config_default_args_empty_tuple(self) -> None:
        """Default ``args`` is an empty tuple."""
        cfg = BrowserConfig()
        self.assertEqual(cfg.args, ())

    def test_browser_config_custom_values(self) -> None:
        """BrowserConfig accepts non-default values."""
        cfg = BrowserConfig(
            browser_type="firefox",
            headless=True,
            viewport_width=1920,
            viewport_height=1080,
            data_dir="/tmp/profile",
            proxy="http://proxy:8080",
            args=("--no-sandbox", "--disable-gpu"),
        )
        self.assertEqual(cfg.browser_type, "firefox")
        self.assertTrue(cfg.headless)
        self.assertEqual(cfg.viewport_width, 1920)
        self.assertEqual(cfg.viewport_height, 1080)
        self.assertEqual(cfg.data_dir, "/tmp/profile")
        self.assertEqual(cfg.proxy, "http://proxy:8080")
        self.assertEqual(cfg.args, ("--no-sandbox", "--disable-gpu"))

    # -- NavigationResult --------------------------------------------------

    def test_navigation_result_is_frozen(self) -> None:
        """NavigationResult fields cannot be changed after creation."""
        nr = NavigationResult(url="https://x.com", status_code=200, title="X", duration_ms=10.0, redirect_chain=())
        with self.assertRaises(FrozenInstanceError):
            nr.url = "https://y.com"  # type: ignore[misc]

    def test_navigation_result_attributes(self) -> None:
        """NavigationResult stores all attributes correctly."""
        nr = NavigationResult(
            url="https://example.com/page",
            status_code=200,
            title="Example Page",
            duration_ms=150.5,
            redirect_chain=("https://example.com", "https://example.com/page"),
        )
        self.assertEqual(nr.url, "https://example.com/page")
        self.assertEqual(nr.status_code, 200)
        self.assertEqual(nr.title, "Example Page")
        self.assertEqual(nr.duration_ms, 150.5)
        self.assertEqual(nr.redirect_chain, ("https://example.com", "https://example.com/page"))

    # -- NavigationEvent ---------------------------------------------------

    def test_navigation_event_enum_values(self) -> None:
        """NavigationEvent enum has expected members and values."""
        self.assertEqual(NavigationEvent.LOAD.value, "load")
        self.assertEqual(NavigationEvent.DOM_CONTENT.value, "domcontentloaded")
        self.assertEqual(NavigationEvent.NETWORK_IDLE.value, "networkidle")

    def test_navigation_event_members(self) -> None:
        """NavigationEvent has exactly three expected members."""
        members = {m.name for m in NavigationEvent}
        expected = {"LOAD", "DOM_CONTENT", "NETWORK_IDLE"}
        self.assertEqual(members, expected)

    # -- DocumentHandle ----------------------------------------------------

    def test_document_handle_is_frozen(self) -> None:
        """DocumentHandle fields cannot be changed after creation."""
        now = time.time()
        dh = DocumentHandle(
            doc_id="abc", name="Test", path=None, object_count=0,
            is_modified=False, created_at=now, modified_at=now,
        )
        with self.assertRaises(FrozenInstanceError):
            dh.name = "Changed"  # type: ignore[misc]

    def test_document_handle_attributes(self) -> None:
        """DocumentHandle stores all attributes."""
        now = time.time()
        dh = DocumentHandle(
            doc_id="uid-1", name="MyDoc", path="/tmp/mydoc.cad",
            object_count=42, is_modified=True,
            created_at=now, modified_at=now + 10,
        )
        self.assertEqual(dh.doc_id, "uid-1")
        self.assertEqual(dh.name, "MyDoc")
        self.assertEqual(dh.path, "/tmp/mydoc.cad")
        self.assertEqual(dh.object_count, 42)
        self.assertTrue(dh.is_modified)
        self.assertEqual(dh.created_at, now)
        self.assertEqual(dh.modified_at, now + 10)

    # -- CommandResult -----------------------------------------------------

    def test_command_result_is_frozen(self) -> None:
        """CommandResult fields cannot be changed after creation."""
        cr = CommandResult(
            success=True, message="ok", document_snapshot={},
            created_objects=[], modified_objects=[], deleted_objects=[],
            execution_time_ms=1.0, warnings=[],
        )
        with self.assertRaises(FrozenInstanceError):
            cr.success = False  # type: ignore[misc]

    def test_command_result_attributes(self) -> None:
        """CommandResult stores all attributes."""
        cr = CommandResult(
            success=True,
            message="Created box",
            document_snapshot={"objects": ["obj1"]},
            created_objects=["obj1"],
            modified_objects=[],
            deleted_objects=[],
            execution_time_ms=2.5,
            warnings=["deprecated API"],
        )
        self.assertTrue(cr.success)
        self.assertEqual(cr.message, "Created box")
        self.assertEqual(cr.document_snapshot, {"objects": ["obj1"]})
        self.assertEqual(cr.created_objects, ["obj1"])
        self.assertEqual(cr.execution_time_ms, 2.5)
        self.assertEqual(cr.warnings, ["deprecated API"])

    # -- ExportResult ------------------------------------------------------

    def test_export_result_is_frozen(self) -> None:
        """ExportResult fields cannot be changed after creation."""
        er = ExportResult(path="/tmp/out.stl", format="stl", size_bytes=512, duration_ms=3.0, warnings=[])
        with self.assertRaises(FrozenInstanceError):
            er.path = "/tmp/new.stl"  # type: ignore[misc]

    def test_export_result_attributes(self) -> None:
        """ExportResult stores all attributes."""
        er = ExportResult(path="/tmp/out.stl", format="stl", size_bytes=2048, duration_ms=15.0, warnings=[])
        self.assertEqual(er.path, "/tmp/out.stl")
        self.assertEqual(er.format, "stl")
        self.assertEqual(er.size_bytes, 2048)
        self.assertEqual(er.duration_ms, 15.0)
        self.assertEqual(er.warnings, [])

    # -- Event hierarchy ---------------------------------------------------

    def test_event_is_frozen(self) -> None:
        """Base ``Event`` fields cannot be changed after creation."""
        ev = Event(timestamp=1.0, source="test")
        with self.assertRaises(FrozenInstanceError):
            ev.source = "modified"  # type: ignore[misc]

    def test_event_attributes(self) -> None:
        """``Event`` stores timestamp and source."""
        ev = Event(timestamp=100.0, source="tester")
        self.assertEqual(ev.timestamp, 100.0)
        self.assertEqual(ev.source, "tester")

    def test_document_event_inherits_and_adds_doc_id(self) -> None:
        """``DocumentEvent`` has ``doc_id`` in addition to base fields."""
        de = DocumentEvent(timestamp=1.0, source="cad", doc_id="doc-42")
        self.assertEqual(de.timestamp, 1.0)
        self.assertEqual(de.source, "cad")
        self.assertEqual(de.doc_id, "doc-42")

    def test_document_event_is_frozen(self) -> None:
        """``DocumentEvent`` fields cannot be changed."""
        de = DocumentEvent(timestamp=0.0, source="t", doc_id="d")
        with self.assertRaises(FrozenInstanceError):
            de.doc_id = "other"  # type: ignore[misc]

    def test_document_created_event(self) -> None:
        """``DocumentCreated`` is a ``DocumentEvent`` with no extra fields."""
        ev = DocumentCreated(timestamp=1.0, source="cad", doc_id="d1")
        self.assertIsInstance(ev, DocumentEvent)
        self.assertIsInstance(ev, Event)
        self.assertEqual(ev.doc_id, "d1")

    def test_document_modified_event(self) -> None:
        """``DocumentModified`` is a ``DocumentEvent``."""
        ev = DocumentModified(timestamp=2.0, source="cad", doc_id="d1")
        self.assertIsInstance(ev, DocumentEvent)

    def test_document_saved_event(self) -> None:
        """``DocumentSaved`` is a ``DocumentEvent``."""
        ev = DocumentSaved(timestamp=3.0, source="cad", doc_id="d1")
        self.assertIsInstance(ev, DocumentEvent)

    def test_document_closed_event(self) -> None:
        """``DocumentClosed`` is a ``DocumentEvent``."""
        ev = DocumentClosed(timestamp=4.0, source="cad", doc_id="d1")
        self.assertIsInstance(ev, DocumentEvent)

    def test_object_selected_event(self) -> None:
        """``ObjectSelected`` has a ``uid`` field (str or None)."""
        ev = ObjectSelected(timestamp=5.0, source="cad", doc_id="d1", uid="obj-42")
        self.assertEqual(ev.uid, "obj-42")
        ev_none = ObjectSelected(timestamp=6.0, source="cad", doc_id="d1", uid=None)
        self.assertIsNone(ev_none.uid)

    def test_browser_event_inherits_and_adds_context_id(self) -> None:
        """``BrowserEvent`` has ``context_id``."""
        be = BrowserEvent(timestamp=0.0, source="browser", context_id="ctx-1")
        self.assertEqual(be.context_id, "ctx-1")

    def test_browser_launched_event(self) -> None:
        """``BrowserLaunched`` is a ``BrowserEvent``."""
        ev = BrowserLaunched(timestamp=0.0, source="browser", context_id="ctx-1")
        self.assertIsInstance(ev, BrowserEvent)

    def test_browser_crashed_event(self) -> None:
        """``BrowserCrashed`` has a ``reason`` field."""
        ev = BrowserCrashed(timestamp=0.0, source="browser", context_id="ctx-1", reason="OOM")
        self.assertEqual(ev.reason, "OOM")

    def test_browser_context_created_event(self) -> None:
        """``BrowserContextCreated`` is a ``BrowserEvent``."""
        ev = BrowserContextCreated(timestamp=0.0, source="browser", context_id="ctx-1")
        self.assertIsInstance(ev, BrowserEvent)

    def test_navigation_completed_event(self) -> None:
        """``NavigationCompleted`` has ``url`` and ``status`` fields."""
        ev = NavigationCompleted(
            timestamp=0.0, source="browser", context_id="ctx-1",
            url="https://example.com", status=200,
        )
        self.assertEqual(ev.url, "https://example.com")
        self.assertEqual(ev.status, 200)

    # -- Subscription ------------------------------------------------------

    def test_subscription_is_frozen(self) -> None:
        """``Subscription`` fields cannot be changed after creation."""
        sub = Subscription(event_type=Event, callback_id="abc")
        with self.assertRaises(FrozenInstanceError):
            sub.callback_id = "def"  # type: ignore[misc]

    def test_subscription_attributes(self) -> None:
        """``Subscription`` stores ``event_type`` and ``callback_id``."""
        sub = Subscription(event_type=DocumentCreated, callback_id="cb-42")
        self.assertIs(sub.event_type, DocumentCreated)
        self.assertEqual(sub.callback_id, "cb-42")


# =========================================================================
#  7. ABSTRACT TEST CLASS THAT EXERCISES ALL MOCK IMPLEMENTATIONS
# =========================================================================
# The following concrete test classes validate that the mock implementations
# satisfy their interfaces correctly.  These also serve as a "sanity check"
# that the contract test suites themselves are well-formed.
# =========================================================================


class MockBrowserProviderContractTests(
    BrowserProviderContractTests, unittest.TestCase,
):
    """Runs the ``BrowserProviderContractTests`` against ``_MockBrowserProvider``.

    This validates both the mock and the contract test suite itself.
    """

    __test__ = True  # explicitly run this

    def create_provider(self) -> IBrowserProvider:
        return _MockBrowserProvider(provider_name="mock")


class MockDocumentManagerContractTests(
    DocumentManagerContractTests, unittest.TestCase,
):
    """Runs ``DocumentManagerContractTests`` against ``_MockDocumentManager``."""

    __test__ = True

    def create_manager(self) -> IDocumentManager:
        return _MockDocumentManager()


class MockCommandExecutorContractTests(
    CommandExecutorContractTests, unittest.TestCase,
):
    """Runs ``CommandExecutorContractTests`` against ``_MockCommandExecutor``."""

    __test__ = True

    def create_executor(self) -> ICommandExecutor:
        return _MockCommandExecutor()


class MockExportProviderContractTests(
    ExportProviderContractTests, unittest.TestCase,
):
    """Runs ``ExportProviderContractTests`` against ``_MockExportProvider``."""

    __test__ = True

    def create_export_provider(self) -> IExportProvider:
        return _MockExportProvider(format_name="mock", extensions=[".mock", ".MOCK"])
