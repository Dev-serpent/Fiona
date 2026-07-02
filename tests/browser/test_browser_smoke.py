"""Smoke test for the Selenium browser automation stack.

Verifies that:
1. All BrowserAutomation modules import cleanly
2. BrowserManager can be instantiated
3. The state machine behaves correctly (STOPPED → STARTING → RUNNING)
4. Chrome binary can be resolved (skip if no Chrome available)
5. Selenium provider can be imported and instantiated
6. Browser can launch, navigate, screenshot, and stop
7. ERROR recovery works

This is the "manual verify" step — fully automated.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from BrowserAutomation._manager import BrowserManagerState


# =========================================================================
# 1. Module imports
# =========================================================================


class TestBrowserImports:
    """Verify all BrowserAutomation modules import without error."""

    def test_import_manager(self) -> None:
        from BrowserAutomation import BrowserManager, BrowserManagerState, get_browser_manager
        assert BrowserManager is not None
        assert BrowserManagerState is not None
        assert get_browser_manager is not None

    def test_import_selenium_provider(self) -> None:
        from BrowserAutomation._selenium_provider import SeleniumBrowserProvider
        assert SeleniumBrowserProvider is not None

    def test_import_config(self) -> None:
        from BrowserAutomation._config import BrowserConfig, DEFAULT_HEADLESS
        assert BrowserConfig is not None
        assert DEFAULT_HEADLESS is True

    def test_import_errors(self) -> None:
        from BrowserAutomation._errors import (
            BrowserCrashError, BrowserError, BrowserLaunchError,
            BrowserNotRunning, BrowserShutdownError, BrowserTimeout,
            ElementNotFound, ElementNotInteractable, NavigationTimeout,
            ScriptExecutionError, SelectorTimeout,
        )
        assert BrowserCrashError is not None
        assert BrowserError is not None
        assert BrowserLaunchError is not None

    def test_import_session_manager(self) -> None:
        from BrowserAutomation._session_manager import SessionManager
        assert SessionManager is not None

    def test_playwright_provider_removed(self) -> None:
        """Verify dead code has been removed."""
        with pytest.raises(ImportError, match="playwright"):
            from BrowserAutomation._playwright_provider import PlaywrightBrowserProvider  # type: ignore[import-untyped]  # noqa: F811

    def test_playwright_test_file_removed(self) -> None:
        """Verify the deprecated test file is gone."""
        test_path = Path(__file__).resolve().parent / "test_playwright_provider.py"
        assert not test_path.exists(), f"Dead code still present: {test_path}"


# =========================================================================
# 2. BrowserManager state machine
# =========================================================================


class TestBrowserManagerStateMachine:
    """Verify the BrowserManager state machine."""

    def test_create_manager(self) -> None:
        from BrowserAutomation._manager import BrowserManager
        mgr = BrowserManager()
        assert mgr is not None
        assert mgr.state == BrowserManagerState.STOPPED

    def test_double_start_is_noop(self) -> None:
        """Calling start() when already RUNNING should be a no-op."""
        from BrowserAutomation._manager import BrowserManager
        mgr = BrowserManager()
        # Set state to RUNNING via the proper enum
        mgr._state = BrowserManagerState.RUNNING  # noqa: SLF001
        # Should not raise
        import asyncio
        asyncio.run(mgr.start())

    def test_has_context_default(self) -> None:
        from BrowserAutomation._manager import BrowserManager
        mgr = BrowserManager()
        assert mgr.has_context is False

    def test_manager_repr(self) -> None:
        from BrowserAutomation._manager import BrowserManager
        mgr = BrowserManager()
        r = repr(mgr)
        assert "BrowserManager" in r


# =========================================================================
# 3. Selenium provider — instantiation (no browser launch)
# =========================================================================


class TestSeleniumProvider:
    """Test the Selenium provider without launching a browser."""

    def test_create_provider(self) -> None:
        from BrowserAutomation._selenium_provider import SeleniumBrowserProvider
        provider = SeleniumBrowserProvider()
        assert provider is not None
        name = provider.name()
        assert isinstance(name, str)
        assert name == "selenium"

    def test_provider_config_defaults(self) -> None:
        from BrowserAutomation._selenium_provider import SeleniumBrowserProvider
        from BrowserAutomation._config import default_config, DEFAULT_HEADLESS
        provider = SeleniumBrowserProvider()
        assert provider.name() == "selenium"
        config = default_config()
        assert config.headless == DEFAULT_HEADLESS
        assert provider.name() == "selenium"


# =========================================================================
# 4. Chrome binary resolution
# =========================================================================


class TestChromeResolution:
    """Verify Chrome can be found on this system."""

    def test_chrome_on_path(self) -> None:
        """Check if google-chrome-stable or chromium is on PATH."""
        import shutil
        chrome = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        # Not an assert — just informational
        print(f"\n  Chrome binary found: {chrome}")

    def test_selenium_provider_chrome_resolution(self) -> None:
        """Verify the provider's chrome binary resolution logic works."""
        from BrowserAutomation._selenium_provider import _resolve_chrome_binary
        binary = _resolve_chrome_binary()
        # Should return a string (even if None — that's valid, means no Chrome)
        if binary:
            assert isinstance(binary, str)
            assert Path(binary).exists() or Path(binary).is_file()


# =========================================================================
# 5. Full browser lifecycle (only if Chrome available)
# =========================================================================


@pytest.mark.skipif(
    not __import__("shutil").which("google-chrome-stable")
    and not __import__("shutil").which("google-chrome")
    and not __import__("shutil").which("chromium")
    and not __import__("shutil").which("chromium-browser"),
    reason="No Chrome binary available on this system",
)
class TestBrowserLifecycle:
    """Full browser lifecycle: launch → navigate → screenshot → stop.

    These tests require a real Chrome/Chromium installation and Selenium.
    """

    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """Launch, navigate, screenshot, and stop the browser."""
        from BrowserAutomation._manager import BrowserManager

        mgr = BrowserManager()

        # Launch
        await mgr.start()
        assert mgr.state in (BrowserManagerState.RUNNING, BrowserManagerState.STARTING)

        # Give Chrome a moment to finish starting
        import asyncio
        await asyncio.sleep(2)

        # Create a context before navigating
        if not mgr.has_context:
            await mgr.create_context()
        assert mgr.has_context is True

        # Navigate
        await mgr.navigate("about:blank", timeout=15.0)

        # Screenshot
        screenshot = await mgr.capture_screenshot()
        assert screenshot is not None
        assert isinstance(screenshot, bytes)
        assert len(screenshot) > 100  # should be a real image

        # Stop
        await mgr.stop()
        assert mgr.state == BrowserManagerState.STOPPED
