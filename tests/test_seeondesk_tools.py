"""Tests for SeeOnDesk/tools.py — Agent-callable perception tools."""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest.mock import MagicMock, patch

from SeeOnDesk.tools import (
    CheckOcrTool,
    ReadScreenTextTool,
    WatchRegionTool,
    register_desk_tools,
)
from fiona.tools.models import ToolContext, ToolResult


def _make_context() -> ToolContext:
    return ToolContext(logger=logging.getLogger("test"))


def _make_registry():
    """Create a minimal mock registry that mimics ToolRegistry."""
    registry = MagicMock()
    registry.registered_tools = []

    def _register(tool, source="internal"):
        registry.registered_tools.append((tool, source))

    registry.register = _register
    return registry


# ---------------------------------------------------------------------------
# ReadScreenTextTool
# ---------------------------------------------------------------------------


class ReadScreenTextToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = ReadScreenTextTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "read_screen_text")

    def test_spec_has_description(self) -> None:
        self.assertTrue(len(self.tool.spec.description) > 20)

    def test_spec_has_input_schema(self) -> None:
        schema = self.tool.spec.input_schema
        self.assertIn("properties", schema)
        self.assertIn("region", schema["properties"])
        self.assertIn("window_id", schema["properties"])

    def test_spec_category(self) -> None:
        from fiona.tools.models import ToolCategory

        self.assertEqual(self.tool.spec.category, ToolCategory.SYSTEM)

    def test_requires_region_or_window_id(self) -> None:
        result = asyncio.run(self.tool.run(self.ctx))
        self.assertFalse(result.success)
        self.assertIn("region", (result.error or "").lower())

    def test_region_success(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=True,
                text="Hello world",
                confidence=95.0,
                language="eng",
                boxes=[{"x": 0, "y": 0, "w": 50, "h": 20, "text": "Hello", "conf": 95.0}],
            )
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50")
            )

        self.assertTrue(result.success)
        self.assertEqual(result.content, "Hello world")
        self.assertEqual(result.metadata["confidence"], 95.0)

    def test_region_without_region_no_parse(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=True,
                text="test",
                confidence=90.0,
                language="eng",
                boxes=[],
            )
            # No region arg — tool should pass None as region
            result = asyncio.run(self.tool.run(self.ctx))

        self.assertFalse(result.success)
        self.assertIn("region", (result.error or "").lower())

    def test_window_id_success(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_window_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=True,
                text="Window content",
                confidence=88.0,
                language="eng",
                boxes=[],
            )
            result = asyncio.run(
                self.tool.run(self.ctx, window_id="abc123", region="0,0,200,100")
            )

        self.assertTrue(result.success)
        self.assertEqual(result.content, "Window content")
        mock_read.assert_called_once_with(
            "abc123", region=(0, 0, 200, 100), lang="eng"
        )

    def test_ocr_failure_returns_error(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=False,
                text="",
                confidence=0.0,
                language="eng",
                boxes=[],
                error="OCR engine failed",
            )
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50")
            )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_no_text_detected(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=True,
                text="   ",
                confidence=0.0,
                language="eng",
                boxes=[],
            )
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50")
            )

        self.assertTrue(result.success)
        self.assertIn("no text detected", result.content.lower())

    def test_value_error_handled(self) -> None:
        result = asyncio.run(
            self.tool.run(self.ctx, region="invalid_region")
        )
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_generic_exception_handled(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.side_effect = RuntimeError("unexpected crash")
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50")
            )

        self.assertFalse(result.success)
        self.assertIn("unexpected", (result.error or "").lower())

    def test_lang_param_passed(self) -> None:
        with (
            patch("SeeOnDesk.tools.read_screen_region") as mock_read,
        ):
            mock_read.return_value = MagicMock(
                success=True,
                text="bonjour",
                confidence=90.0,
                language="fra",
                boxes=[],
            )
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50", lang="fra")
            )

        self.assertTrue(result.success)
        mock_read.assert_called_once_with(
            region=(0, 0, 100, 50), lang="fra"
        )


# ---------------------------------------------------------------------------
# WatchRegionTool
# ---------------------------------------------------------------------------


class WatchRegionToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = WatchRegionTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "watch_region")

    def test_spec_has_input_schema(self) -> None:
        schema = self.tool.spec.input_schema
        self.assertIn("region", schema["required"])
        self.assertIn("duration_seconds", schema["properties"])

    def test_missing_region_returns_error(self) -> None:
        result = asyncio.run(self.tool.run(self.ctx))
        self.assertFalse(result.success)
        self.assertIn("region", (result.error or "").lower())

    def test_invalid_duration(self) -> None:
        result = asyncio.run(
            self.tool.run(self.ctx, region="0,0,100,50", duration_seconds=0)
        )
        self.assertFalse(result.success)
        self.assertIn("positive", (result.error or "").lower())

    def test_invalid_region_string(self) -> None:
        result = asyncio.run(
            self.tool.run(self.ctx, region="bad")
        )
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_no_changes_detected(self) -> None:
        with (
            patch("SeeOnDesk.tools.RegionMonitor") as mock_monitor_cls,
            patch("asyncio.sleep"),  # fast-forward time
        ):
            mock_monitor = MagicMock()
            mock_monitor_cls.return_value = mock_monitor
            mock_monitor.watch_region.return_value = "test_watch_id"

            # ocr_func returns same text every time → no changes
            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50", duration_seconds=1)
            )

        self.assertTrue(result.success)
        self.assertIn("No text changes", result.content)

    def test_changes_detected(self) -> None:
        with (
            patch("SeeOnDesk.tools.RegionMonitor") as mock_monitor_cls,
            patch("asyncio.sleep"),
        ):
            # Simulate changes by collecting via the on_change callback
            actual_on_change = None

            def fake_watch(config, on_change):
                nonlocal actual_on_change
                actual_on_change = on_change
                return "watch_1"

            mock_monitor = MagicMock()
            mock_monitor.watch_region = fake_watch
            mock_monitor_cls.return_value = mock_monitor

            # Fire the callback immediately
            if actual_on_change is not None:
                actual_on_change(
                    MagicMock(
                        diff_type="appeared",
                        old_text="",
                        new_text="Hello",
                        timestamp="2026-07-02T12:00:00",
                    )
                )
            else:
                # Fire it after watch_region is called
                original_watch = fake_watch

                def delayed_watch(config, on_change):
                    wid = original_watch(config, on_change)
                    on_change(
                        MagicMock(
                            diff_type="appeared",
                            old_text="",
                            new_text="Hello",
                            timestamp="2026-07-02T12:00:00",
                        )
                    )
                    return wid

                mock_monitor.watch_region = delayed_watch

            result = asyncio.run(
                self.tool.run(self.ctx, region="0,0,100,50", duration_seconds=1)
            )

            self.assertTrue(result.success)
            self.assertIn("Detected", result.content)
            self.assertIn("1 text change", result.content)

    def test_cancellation(self) -> None:
        with (
            patch("SeeOnDesk.tools.RegionMonitor") as mock_monitor_cls,
        ):
            import threading

            mock_monitor = MagicMock()
            mock_monitor_cls.return_value = mock_monitor
            mock_monitor.watch_region.return_value = "watch_cancel"

            cancel_token = threading.Event()
            cancel_token.set()  # Already cancelled

            ctx = ToolContext(
                logger=self.ctx.logger,
                cancellation_token=cancel_token,
            )

            result = asyncio.run(
                self.tool.run(ctx, region="0,0,100,50", duration_seconds=10)
            )

            self.assertTrue(result.success)
            # Should have stopped early (no changes)
            mock_monitor.unwatch_region.assert_called_once_with("watch_cancel")


# ---------------------------------------------------------------------------
# CheckOcrTool
# ---------------------------------------------------------------------------


class CheckOcrToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = CheckOcrTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "check_ocr")

    def test_spec_no_required_params(self) -> None:
        schema = self.tool.spec.input_schema
        self.assertEqual(schema["required"], [])

    def test_available(self) -> None:
        with (
            patch("SeeOnDesk.tools.tesseract_available", return_value=True),
            patch("SeeOnDesk.tools.list_supported_languages", return_value=["eng", "osd"]),
        ):
            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("True", result.content)
        self.assertIn("eng", result.content)
        self.assertEqual(result.metadata["available"], True)
        self.assertEqual(result.metadata["languages"], ["eng", "osd"])

    def test_not_available(self) -> None:
        with (
            patch("SeeOnDesk.tools.tesseract_available", return_value=False),
        ):
            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("False", result.content)
        self.assertEqual(result.metadata["available"], False)
        self.assertEqual(result.metadata["languages"], [])

    def test_available_no_languages(self) -> None:
        with (
            patch("SeeOnDesk.tools.tesseract_available", return_value=True),
            patch("SeeOnDesk.tools.list_supported_languages", return_value=[]),
        ):
            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("none detected", result.content.lower())


# ---------------------------------------------------------------------------
# register_desk_tools
# ---------------------------------------------------------------------------


class RegisterDeskToolsTests(unittest.TestCase):
    def test_registers_three_tools(self) -> None:
        registry = _make_registry()
        register_desk_tools(registry)
        self.assertEqual(len(registry.registered_tools), 3)

    def test_registers_with_desk_source(self) -> None:
        registry = _make_registry()
        register_desk_tools(registry)
        for tool, source in registry.registered_tools:
            self.assertEqual(source, "desk")

    def test_registers_correct_tool_types(self) -> None:
        registry = _make_registry()
        register_desk_tools(registry)
        names = [tool.spec.name for tool, _ in registry.registered_tools]
        self.assertIn("read_screen_text", names)
        self.assertIn("watch_region", names)
        self.assertIn("check_ocr", names)


if __name__ == "__main__":
    unittest.main()
