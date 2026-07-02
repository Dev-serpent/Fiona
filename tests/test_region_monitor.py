"""Tests for SeeOnDesk/region_monitor.py — Region-based text change detection."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock

from SeeOnDesk.region_monitor import RegionConfig, RegionMonitor, RegionTextChange
from SeeOnDesk.ocr import OcrResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SUCCESS_RESULT = OcrResult(
    text="Hello world",
    confidence=95.0,
    boxes=[],
    language="eng",
    error=None,
)

CHANGED_RESULT = OcrResult(
    text="Goodbye world",
    confidence=90.0,
    boxes=[],
    language="eng",
    error=None,
)

EMPTY_RESULT = OcrResult(text="", confidence=0.0, boxes=[], language="eng", error=None)

ERROR_RESULT = OcrResult(
    text="", confidence=0.0, boxes=[], language="eng", error="OCR failed"
)

LOW_CONF_RESULT = OcrResult(
    text="noise",
    confidence=30.0,
    boxes=[],
    language="eng",
    error=None,
)




class _FakeOcr:
    """Returns preset OcrResult values in sequence, then repeats the last one."""

    def __init__(self, *results: OcrResult):
        self._results = list(results) if results else [SUCCESS_RESULT]

    def __call__(self, *args, **kwargs):
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


def make_monitor(*ocr_results: OcrResult) -> RegionMonitor:
    """Create a RegionMonitor with a fake OCR that yields *ocr_results*."""
    return RegionMonitor(ocr_func=_FakeOcr(*ocr_results or (SUCCESS_RESULT,)))


# ---------------------------------------------------------------------------
# RegionConfig tests
# ---------------------------------------------------------------------------


class RegionConfigTests(unittest.TestCase):
    def test_default_values(self) -> None:
        cfg = RegionConfig(region=(0, 0, 100, 50))
        self.assertEqual(cfg.region, (0, 0, 100, 50))
        self.assertEqual(cfg.poll_interval, 1.0)
        self.assertEqual(cfg.lang, "eng")
        self.assertEqual(cfg.min_confidence, 0.0)
        self.assertEqual(cfg.change_threshold, "any")

    def test_explicit_values(self) -> None:
        cfg = RegionConfig(
            region=(10, 20, 300, 150),
            poll_interval=2.5,
            lang="fra",
            min_confidence=50.0,
            change_threshold="content",
        )
        self.assertEqual(cfg.region, (10, 20, 300, 150))
        self.assertEqual(cfg.poll_interval, 2.5)
        self.assertEqual(cfg.lang, "fra")
        self.assertEqual(cfg.min_confidence, 50.0)
        self.assertEqual(cfg.change_threshold, "content")


# ---------------------------------------------------------------------------
# RegionTextChange tests
# ---------------------------------------------------------------------------


class RegionTextChangeTests(unittest.TestCase):
    def test_all_fields_stored(self) -> None:
        change = RegionTextChange(
            watch_id="abc123",
            region=(0, 0, 100, 50),
            old_text="old",
            new_text="new",
            timestamp="2026-07-02T12:00:00",
            diff_type="changed",
        )
        self.assertEqual(change.watch_id, "abc123")
        self.assertEqual(change.region, (0, 0, 100, 50))
        self.assertEqual(change.old_text, "old")
        self.assertEqual(change.new_text, "new")
        self.assertEqual(change.diff_type, "changed")


# ---------------------------------------------------------------------------
# RegionMonitor tests
# ---------------------------------------------------------------------------


class RegionMonitorTests(unittest.TestCase):
    # --- Lifecycle ---

    def test_watch_region_returns_id(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        self.assertIsInstance(watch_id, str)
        self.assertEqual(len(watch_id), 12)
        monitor.stop_all()

    def test_watch_region_starts_polling(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.2)
        monitor.unwatch_region(watch_id)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0].diff_type, "appeared")
        monitor.stop_all()

    def test_is_watching(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        self.assertTrue(monitor.is_watching(watch_id))
        monitor.unwatch_region(watch_id)
        self.assertFalse(monitor.is_watching(watch_id))
        monitor.stop_all()

    def test_is_watching_unknown_id(self) -> None:
        monitor = make_monitor()
        self.assertFalse(monitor.is_watching("nonexistent"))
        monitor.stop_all()

    def test_unwatch_unknown_id(self) -> None:
        monitor = make_monitor()
        self.assertFalse(monitor.unwatch_region("nonexistent"))
        monitor.stop_all()

    def test_unwatch_known_id(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        self.assertTrue(monitor.unwatch_region(watch_id))
        self.assertFalse(monitor.is_watching(watch_id))
        monitor.stop_all()

    def test_double_unwatch(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        self.assertTrue(monitor.unwatch_region(watch_id))
        self.assertFalse(monitor.unwatch_region(watch_id))
        monitor.stop_all()

    def test_stop_all(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        id1 = monitor.watch_region(cfg, on_change=lambda _: None)
        id2 = monitor.watch_region(cfg, on_change=lambda _: None)
        monitor.stop_all()
        self.assertFalse(monitor.is_watching(id1))
        self.assertFalse(monitor.is_watching(id2))

    def test_stop_all_twice_is_safe(self) -> None:
        monitor = make_monitor()
        monitor.stop_all()
        monitor.stop_all()

    def test_list_watched_regions(self) -> None:
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        listings = monitor.list_watched_regions()
        self.assertEqual(len(listings), 1)
        self.assertEqual(listings[0]["watch_id"], watch_id)
        self.assertEqual(listings[0]["region"], (0, 0, 100, 50))
        monitor.stop_all()

    def test_list_empty_when_no_watches(self) -> None:
        monitor = make_monitor()
        self.assertEqual(monitor.list_watched_regions(), [])
        monitor.stop_all()

    def test_can_watch_after_stop_all(self) -> None:
        monitor = make_monitor()
        monitor.stop_all()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        watch_id = monitor.watch_region(cfg, on_change=lambda _: None)
        self.assertTrue(monitor.is_watching(watch_id))
        monitor.stop_all()

    # --- Diff type detection ---

    def test_appeared_event(self) -> None:
        """First OCR result should fire an 'appeared' event."""
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.2)
        monitor.unwatch_region(watch_id)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0].diff_type, "appeared")
        self.assertEqual(events[0].old_text, "")
        monitor.stop_all()

    def test_changed_event(self) -> None:
        """Different text on subsequent polls should fire a 'changed' event."""
        monitor = make_monitor(SUCCESS_RESULT, CHANGED_RESULT)
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.3)
        monitor.unwatch_region(watch_id)
        diff_types = [e.diff_type for e in events]
        self.assertIn("appeared", diff_types)
        self.assertIn("changed", diff_types)
        monitor.stop_all()

    def test_disappeared_event(self) -> None:
        """Text becoming empty should fire a 'disappeared' event."""
        monitor = make_monitor(SUCCESS_RESULT, EMPTY_RESULT)
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.3)
        monitor.unwatch_region(watch_id)
        diff_types = [e.diff_type for e in events]
        self.assertIn("appeared", diff_types)
        self.assertIn("disappeared", diff_types)
        monitor.stop_all()

    def test_unchanged_does_not_fire(self) -> None:
        """Same text on repeated polls should NOT fire callbacks."""
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.3)
        monitor.unwatch_region(watch_id)
        appeared_count = sum(1 for e in events if e.diff_type == "appeared")
        unchanged_count = sum(1 for e in events if e.diff_type == "unchanged")
        self.assertEqual(appeared_count, 1)
        self.assertEqual(unchanged_count, 0)
        monitor.stop_all()

    # --- Content threshold ---

    def test_content_threshold_ignores_whitespace(self) -> None:
        """change_threshold='content' should ignore whitespace-only diffs."""
        text = "Hello"
        padded = OcrResult(text=f"  {text}  ", confidence=90.0, boxes=[], language="eng", error=None)
        trimmed = OcrResult(text=text, confidence=90.0, boxes=[], language="eng", error=None)
        # Start with trimmed, then padded (same stripped content → unchanged)
        monitor = make_monitor(trimmed, padded)
        cfg = RegionConfig(
            region=(0, 0, 100, 50),
            poll_interval=0.05,
            change_threshold="content",
        )
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.3)
        monitor.unwatch_region(watch_id)
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0].diff_type, "appeared")
        # Padded result has same stripped content → "unchanged", not "changed"
        changed_count = sum(1 for e in events if e.diff_type == "changed")
        self.assertEqual(changed_count, 0)
        monitor.stop_all()

    # --- Min confidence filter ---

    def test_min_confidence_filters_low_conf(self) -> None:
        """Readings below min_confidence should be skipped entirely."""
        monitor = make_monitor(LOW_CONF_RESULT)
        cfg = RegionConfig(
            region=(0, 0, 100, 50),
            poll_interval=0.05,
            min_confidence=50.0,
        )
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.2)
        monitor.unwatch_region(watch_id)
        # Low confidence readings should be skipped entirely
        self.assertEqual(len(events), 0)
        monitor.stop_all()

    # --- OCR error handling ---

    def test_ocr_error_is_skipped(self) -> None:
        """OCR errors should not crash the monitor — just skip the cycle."""
        monitor = make_monitor(ERROR_RESULT, SUCCESS_RESULT)
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.3)
        monitor.unwatch_region(watch_id)
        # First call errors (skipped), second succeeds → "appeared"
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0].diff_type, "appeared")
        monitor.stop_all()

    # --- Custom ocr_func ---

    def test_custom_ocr_func_passes_region_and_lang(self) -> None:
        """Ensure the OCR function receives region and lang kwargs."""
        mock_ocr = MagicMock(return_value=SUCCESS_RESULT)
        monitor = RegionMonitor(ocr_func=mock_ocr)
        cfg = RegionConfig(
            region=(10, 20, 300, 150),
            poll_interval=0.05,
            lang="fra",
        )
        events: list[RegionTextChange] = []
        watch_id = monitor.watch_region(cfg, on_change=events.append)
        time.sleep(0.2)
        monitor.unwatch_region(watch_id)
        monitor.stop_all()
        self.assertGreaterEqual(len(events), 1)
        mock_ocr.assert_called()
        self.assertEqual(mock_ocr.call_args.kwargs["region"], (10, 20, 300, 150))
        self.assertEqual(mock_ocr.call_args.kwargs["lang"], "fra")

    # --- Callback exception isolation ---

    def test_callback_exception_does_not_crash(self) -> None:
        """A callback that raises should not crash the polling thread or monitor."""
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)

        def crashing_callback(change):
            raise RuntimeError("callback failed")

        watch_id = monitor.watch_region(cfg, on_change=crashing_callback)
        time.sleep(0.2)
        monitor.unwatch_region(watch_id)
        # The monitor should survive and be usable after
        self.assertFalse(monitor.is_watching(watch_id))
        monitor.stop_all()

    # --- Concurrent watches ---

    def test_multiple_watches_independent(self) -> None:
        """Multiple watches should run independently with separate OCR calls."""
        monitor = make_monitor()
        cfg1 = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        cfg2 = RegionConfig(region=(200, 200, 100, 50), poll_interval=0.05)
        events1: list[RegionTextChange] = []
        events2: list[RegionTextChange] = []
        id1 = monitor.watch_region(cfg1, on_change=events1.append)
        id2 = monitor.watch_region(cfg2, on_change=events2.append)
        time.sleep(0.2)
        monitor.unwatch_region(id1)
        monitor.unwatch_region(id2)
        self.assertGreaterEqual(len(events1), 1)
        self.assertGreaterEqual(len(events2), 1)
        monitor.stop_all()

    # --- Thread safety ---

    def test_concurrent_watch_unwatch(self) -> None:
        """Watch and unwatch from different threads should be thread-safe."""
        monitor = make_monitor()
        cfg = RegionConfig(region=(0, 0, 100, 50), poll_interval=0.05)
        ids: list[str] = []
        lock = threading.Lock()

        def watch_thread():
            wid = monitor.watch_region(cfg, on_change=lambda _: None)
            with lock:
                ids.append(wid)

        threads = [threading.Thread(target=watch_thread) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)

        self.assertEqual(len(ids), 5)
        for wid in ids:
            self.assertTrue(monitor.is_watching(wid))

        monitor.stop_all()
        for wid in ids:
            self.assertFalse(monitor.is_watching(wid))


if __name__ == "__main__":
    unittest.main()
