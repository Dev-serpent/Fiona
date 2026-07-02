"""Browser automation subsystem for Fiona.

Uses Selenium via :class:`BrowserAutomation._selenium_provider.SeleniumBrowserProvider`
with the interface contracts defined in :mod:`fiona.interfaces`.
"""

from __future__ import annotations

from typing import Any

from ._errors import (
    BrowserCrashError,
    BrowserError,
    BrowserLaunchError,
    BrowserNotRunning,
    BrowserShutdownError,
    BrowserTimeout,
    ElementNotFound,
    ElementNotInteractable,
    NavigationTimeout,
    ScriptExecutionError,
    SelectorTimeout,
)
from ._manager import BrowserManager, BrowserManagerState

# ---------------------------------------------------------------------------
# Default instance (module-level convenience)
# ---------------------------------------------------------------------------

_default_manager: BrowserManager | None = None


def _ensure_manager() -> BrowserManager:
    """Return (or create) the module-level default :class:`BrowserManager`."""
    global _default_manager  # noqa: PLW0603
    if _default_manager is None:
        _default_manager = BrowserManager()
    return _default_manager


def get_browser_manager() -> BrowserManager:
    """Return the module-level default :class:`BrowserManager`.

    Creates one on first call.  Use this for CLI and integration access.
    """
    return _ensure_manager()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _ensure_context(manager: BrowserManager) -> None:
    """Ensure a default context exists on *manager*, creating one if needed.

    If the browser is running and no context exists, a new default context
    is created automatically.  If the browser is not running,
    :class:`BrowserNotRunning` is raised.
    """
    if manager.has_context:
        return
    if manager.state not in (
        BrowserManagerState.RUNNING,
        BrowserManagerState.DEGRADED,
    ):
        raise BrowserNotRunning(
            f"Cannot ensure context: browser is {manager.state.value}"
        )
    await manager.create_context()


# ---------------------------------------------------------------------------
# Convenience functions that use the default BrowserManager
# ---------------------------------------------------------------------------


def browser_status() -> BrowserManagerState:
    """Return the current state of the default :class:`BrowserManager`.

    See :meth:`BrowserManager.state`.
    """
    return _ensure_manager().state


async def create_context(**kwargs: Any) -> Any:
    """Create a context from the default manager.

    Equivalent to ``BrowserManager.create_context(**kwargs)``.
    """
    manager = _ensure_manager()
    return await manager.create_context(**kwargs)


async def navigate(url: str, *, timeout: float = 30.0, wait_until: str = "load") -> Any:
    """Navigate the default context to *url*.

    Equivalent to calling ``navigate`` on the default manager's context.
    """
    manager = _ensure_manager()
    await _ensure_context(manager)
    return await manager.navigate(url, timeout=timeout, wait_until=wait_until)


async def click_element(selector: str, *, timeout: float = 5.0) -> None:
    """Click an element in the default context."""
    manager = _ensure_manager()
    await _ensure_context(manager)
    await manager.click_element(selector, timeout=timeout)


async def type_text(selector: str, text: str, *, delay: float = 0.01, timeout: float = 5.0) -> None:
    """Type *text* into an element in the default context."""
    manager = _ensure_manager()
    await _ensure_context(manager)
    await manager.type_text(selector, text, delay=delay, timeout=timeout)


async def get_text_content(selector: str, *, timeout: float = 5.0) -> str:
    """Retrieve text content from an element in the default context."""
    manager = _ensure_manager()
    await _ensure_context(manager)
    return await manager.get_text_content(selector, timeout=timeout)


async def capture_screenshot(*, path: str | None = None, full_page: bool = False) -> bytes:
    """Capture a screenshot from the default context."""
    manager = _ensure_manager()
    await _ensure_context(manager)
    return await manager.capture_screenshot(path=path, full_page=full_page)


async def evaluate_script(js: str, *, timeout: float = 5.0) -> Any:
    """Evaluate JavaScript in the default context."""
    manager = _ensure_manager()
    await _ensure_context(manager)
    return await manager.evaluate_script(js, timeout=timeout)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Manager
    "BrowserManager",
    "BrowserManagerState",
    "get_browser_manager",
    # Convenience
    "browser_status",
    "create_context",
    "navigate",
    "click_element",
    "type_text",
    "get_text_content",
    "capture_screenshot",
    "evaluate_script",
    # Errors
    "BrowserCrashError",
    "BrowserError",
    "BrowserLaunchError",
    "BrowserNotRunning",
    "BrowserShutdownError",
    "BrowserTimeout",
    "ElementNotFound",
    "ElementNotInteractable",
    "NavigationTimeout",
    "ScriptExecutionError",
    "SelectorTimeout",
]
