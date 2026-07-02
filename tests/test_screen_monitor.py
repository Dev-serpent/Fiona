from __future__ import annotations

import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

import unittest

from SeeOnDesk.screen_monitor import (
    ScreenChange,
    ScreenMonitor,
    compute_diff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 50, 50
TOTAL_PIXELS = WIDTH * HEIGHT  # 2500


def _make_image(color: tuple[int, int, int] = (100, 100, 100)) -> Image.Image:
    """Return a solid-color RGB image of the standard test size."""
    return Image.new("RGB", (WIDTH, HEIGHT), color)


def _make_alternating_capture(
    color_a: tuple[int, int, int] = (100, 100, 100),
    color_b: tuple[int, int, int] = (200, 200, 200),
) -> callable:
    """Return a ``capture_screen`` side_effect that alternates between two images.

    Each call writes a valid PNG to the requested path.  The first call
    produces *color_a*, the second *color_b*, the third *color_a*, etc.
    """
    colors = [color_a, color_b]
    index = [0]

    def _capture(path: str | Path) -> bool:
        Image.new("RGB", (WIDTH, HEIGHT), color=colors[index[0] % 2]).save(path)
        index[0] += 1
        return True

    return _capture


def _make_static_capture(
    color: tuple[int, int, int] = (100, 100, 100),
) -> callable:
    """Return a ``capture_screen`` side_effect that always writes the same image."""
    return _make_alternating_capture(color_a=color, color_b=color)


# ===========================================================================
# ScreenChange dataclass
# ===========================================================================


class TestScreenChange(unittest.TestCase):
    """Default field values and manual construction."""

    def test_default_values(self) -> None:
        """Every optional field should default as documented."""
        sc = ScreenChange(timestamp="2026-01-01T00:00:00")
        self.assertEqual(sc.timestamp, "2026-01-01T00:00:00")
        self.assertIsNone(sc.bbox)
        self.assertEqual(sc.pixel_count, 0)
        self.assertEqual(sc.total_pixels, 0)
        self.assertEqual(sc.change_ratio, 0.0)
        self.assertEqual(sc.change_type, "none")
        self.assertIsNone(sc.screenshot_before)
        self.assertIsNone(sc.screenshot_after)
        self.assertIsNone(sc.region)

    def test_explicit_field_values(self) -> None:
        """All fields can be set via constructor."""
        sc = ScreenChange(
            timestamp="2026-06-15T12:30:00",
            bbox=(10, 20, 110, 220),
            pixel_count=500,
            total_pixels=10_000,
            change_ratio=0.05,
            change_type="significant",
            screenshot_before="/tmp/before.png",
            screenshot_after="/tmp/after.png",
            region=(0, 0, 1920, 1080),
        )
        self.assertEqual(sc.timestamp, "2026-06-15T12:30:00")
        self.assertEqual(sc.bbox, (10, 20, 110, 220))
        self.assertEqual(sc.pixel_count, 500)
        self.assertEqual(sc.total_pixels, 10_000)
        self.assertEqual(sc.change_ratio, 0.05)
        self.assertEqual(sc.change_type, "significant")
        self.assertEqual(sc.screenshot_before, "/tmp/before.png")
        self.assertEqual(sc.screenshot_after, "/tmp/after.png")
        self.assertEqual(sc.region, (0, 0, 1920, 1080))

    def test_change_type_classification_consistency(self) -> None:
        """Verify that ``change_type`` values match the ratio-based classification
        used by ``compute_diff``."""
        # classification rules from compute_diff:
        #   ratio == 0.0  -> "none"
        #   ratio < 0.01  -> "minor"
        #   ratio < 0.30  -> "significant"
        #   else          -> "full"

        cases: list[tuple[float, str]] = [
            (0.0, "none"),
            (0.001, "minor"),
            (0.009999, "minor"),
            (0.01, "significant"),  # exactly 0.01 is NOT "< 0.01"
            (0.05, "significant"),
            (0.299999, "significant"),
            (0.30, "full"),  # exactly 0.30 is NOT "< 0.30"
            (0.50, "full"),
            (1.0, "full"),
        ]
        for ratio, expected_type in cases:
            with self.subTest(ratio=ratio, expected=expected_type):
                sc = ScreenChange(
                    timestamp="now",
                    pixel_count=int(ratio * 10_000) if ratio > 0 else 0,
                    total_pixels=10_000,
                    change_ratio=ratio,
                    change_type=expected_type,
                )
                self.assertEqual(sc.change_type, expected_type)
                self.assertAlmostEqual(sc.change_ratio, ratio, places=6)

    def test_change_type_default_is_none(self) -> None:
        """A freshly constructed ScreenChange with no explicit change_type
        should have ``change_type == "none"``."""
        sc = ScreenChange(timestamp="now")
        self.assertEqual(sc.change_type, "none")


# ===========================================================================
# compute_diff
# ===========================================================================


class TestComputeDiff(unittest.TestCase):
    """Pixel-diff engine correctness."""

    def setUp(self) -> None:
        self.base_image = _make_image((128, 128, 128))

    # -- Identical images ---------------------------------------------------

    def test_identical_images(self) -> None:
        """Identical before/after -> change_type='none', pixel_count=0, bbox=None."""
        result = compute_diff(self.base_image, self.base_image)
        self.assertEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, 0)
        self.assertIsNone(result.bbox)
        self.assertEqual(result.total_pixels, TOTAL_PIXELS)
        self.assertEqual(result.change_ratio, 0.0)

    # -- Completely different images ----------------------------------------

    def test_completely_different_images(self) -> None:
        """All-white vs all-black -> change_type='full', pixel_count > 0."""
        before = _make_image((0, 0, 0))
        after = _make_image((255, 255, 255))
        result = compute_diff(before, after)
        self.assertEqual(result.change_type, "full")
        self.assertEqual(result.pixel_count, TOTAL_PIXELS)
        self.assertIsNotNone(result.bbox)
        self.assertEqual(result.bbox, (0, 0, WIDTH, HEIGHT))
        self.assertAlmostEqual(result.change_ratio, 1.0)

    # -- Single pixel change ------------------------------------------------

    def test_single_pixel_change(self) -> None:
        """Changing one pixel out of 2500 -> change_type='minor' (ratio < 0.01)."""
        before = _make_image((100, 100, 100))
        after = _make_image((100, 100, 100))
        after.putpixel((25, 25), (200, 200, 200))
        result = compute_diff(before, after)
        # 1 / 2500 = 0.0004 < 0.01
        self.assertEqual(result.change_type, "minor")
        self.assertEqual(result.pixel_count, 1)
        self.assertIsNotNone(result.bbox)
        self.assertLess(result.change_ratio, 0.01)
        # Bbox should be a single pixel
        self.assertEqual(result.bbox, (25, 25, 26, 26))

    # -- ~20 % pixels changed -----------------------------------------------

    def test_twenty_percent_pixels_changed(self) -> None:
        """A grid pattern that changes exactly 20 % of pixels -> 'significant'."""
        before_arr = np.full((HEIGHT, WIDTH, 3), 100, dtype=np.uint8)
        after_arr = before_arr.copy()

        # Change every 5th pixel (20 %)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if (y * WIDTH + x) % 5 == 0:
                    after_arr[y, x] = [200, 200, 200]

        before = Image.fromarray(before_arr, mode="RGB")
        after = Image.fromarray(after_arr, mode="RGB")

        result = compute_diff(before, after)
        self.assertEqual(result.change_type, "significant")
        self.assertEqual(result.pixel_count, TOTAL_PIXELS // 5)
        self.assertAlmostEqual(result.change_ratio, 0.2, places=4)

    # -- Size mismatch ------------------------------------------------------

    def test_size_mismatch_treated_as_full_change(self) -> None:
        """Different-sized images -> change_type='full' with a bbox covering the
        larger image's full extent."""
        small = _make_image((100, 100, 100))
        large = Image.new("RGB", (200, 150), (100, 100, 100))
        result = compute_diff(small, large)
        self.assertEqual(result.change_type, "full")
        self.assertEqual(result.pixel_count, 200 * 150)
        self.assertEqual(result.total_pixels, 200 * 150)
        self.assertEqual(result.bbox, (0, 0, 200, 150))
        self.assertAlmostEqual(result.change_ratio, 1.0)

    def test_size_mismatch_reversed(self) -> None:
        """Same as above with before and after swapped."""
        small = _make_image((100, 100, 100))
        large = Image.new("RGB", (200, 150), (100, 100, 100))
        result = compute_diff(large, small)
        self.assertEqual(result.change_type, "full")
        self.assertEqual(result.pixel_count, 200 * 150)
        self.assertEqual(result.total_pixels, 200 * 150)
        self.assertEqual(result.bbox, (0, 0, 200, 150))

    # -- Threshold filtering ------------------------------------------------

    def test_threshold_filters_below_threshold_differences(self) -> None:
        """Differences below the default threshold are treated as unchanged."""
        before = _make_image((100, 100, 100))
        # Each channel differs by 29 -- below the default threshold of 30
        after = _make_image((129, 129, 129))
        result = compute_diff(before, after, threshold=30)
        # np.any(diff > 30)  -- 29 is NOT > 30
        self.assertEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, 0)
        self.assertIsNone(result.bbox)

    def test_threshold_detects_at_threshold_exceeding_differences(self) -> None:
        """Differences that exceed the threshold are detected."""
        before = _make_image((100, 100, 100))
        # Each channel differs by 31 -- exceeds the default threshold of 30
        after = _make_image((131, 131, 131))
        result = compute_diff(before, after, threshold=30)
        self.assertNotEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, TOTAL_PIXELS)
        self.assertIsNotNone(result.bbox)

    def test_custom_threshold_ignores_differences_below_it(self) -> None:
        """A custom high threshold can make large per-pixel differences
        appear as no change."""
        before = _make_image((0, 0, 0))
        after = _make_image((100, 100, 100))  # diff = 100
        # threshold = 200 -> diff of 100 does NOT exceed 200
        result = compute_diff(before, after, threshold=200)
        self.assertEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, 0)

    # -- save_dir -----------------------------------------------------------

    def test_save_dir_saves_screenshot_files(self) -> None:
        """When save_dir is provided, before/after images are written to disk
        and paths are recorded in the result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            before = _make_image((0, 0, 0))
            after = _make_image((255, 255, 255))
            result = compute_diff(before, after, save_dir=tmpdir)

            self.assertIsNotNone(result.screenshot_before)
            self.assertIsNotNone(result.screenshot_after)
            self.assertTrue(Path(result.screenshot_before).exists())
            self.assertTrue(Path(result.screenshot_after).exists())

            # Both files should be PNGs
            self.assertEqual(Path(result.screenshot_before).suffix, ".png")
            self.assertEqual(Path(result.screenshot_after).suffix, ".png")

    def test_save_dir_none_does_not_save(self) -> None:
        """When save_dir is None, no screenshot paths are recorded."""
        before = _make_image((0, 0, 0))
        after = _make_image((255, 255, 255))
        result = compute_diff(before, after, save_dir=None)
        self.assertIsNone(result.screenshot_before)
        self.assertIsNone(result.screenshot_after)

    def test_save_dir_path_object(self) -> None:
        """save_dir accepts a ``pathlib.Path`` object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir)
            before = _make_image((0, 0, 0))
            after = _make_image((255, 255, 255))
            result = compute_diff(before, after, save_dir=save_path)
            self.assertIsNotNone(result.screenshot_before)
            self.assertTrue(Path(result.screenshot_before).exists())

    # -- Image mode conversion ----------------------------------------------

    def test_non_rgb_images_are_converted(self) -> None:
        """Images in modes other than RGB (e.g. 'L' grayscale) are converted
        before comparison."""
        before = Image.new("L", (WIDTH, HEIGHT), 100)
        after = Image.new("L", (WIDTH, HEIGHT), 200)
        result = compute_diff(before, after)
        self.assertEqual(result.change_type, "full")
        self.assertEqual(result.pixel_count, TOTAL_PIXELS)

    # -- Edge cases ---------------------------------------------------------

    def test_tiny_image(self) -> None:
        """A 1×1 image should not cause any problems."""
        before = Image.new("RGB", (1, 1), (0, 0, 0))
        after = Image.new("RGB", (1, 1), (255, 255, 255))
        result = compute_diff(before, after)
        self.assertEqual(result.change_type, "full")
        self.assertEqual(result.pixel_count, 1)

    def test_zero_pixel_image(self) -> None:
        """A 0×0 image (no pixels) should not cause a ZeroDivisionError."""
        before = Image.new("RGB", (0, 0))
        after = Image.new("RGB", (0, 0))
        result = compute_diff(before, after)
        self.assertEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, 0)
        self.assertEqual(result.total_pixels, 0)
        self.assertEqual(result.change_ratio, 0.0)

    def test_threshold_zero_detects_any_change(self) -> None:
        """threshold=0 means any non-zero per-channel diff is detected."""
        before = _make_image((100, 100, 100))
        after = _make_image((101, 100, 100))  # only red channel differs by 1
        result = compute_diff(before, after, threshold=0)
        self.assertNotEqual(result.change_type, "none")
        self.assertEqual(result.pixel_count, TOTAL_PIXELS)


# ===========================================================================
# ScreenMonitor
# ===========================================================================


class TestScreenMonitorBase(unittest.TestCase):
    """Base class with setUp / tearDown helpers for ScreenMonitor tests."""

    def setUp(self) -> None:
        self.monitor: ScreenMonitor | None = None

    def tearDown(self) -> None:
        if self.monitor is not None:
            try:
                self.monitor.stop()
            except Exception:
                pass


class TestScreenMonitorLifecycle(TestScreenMonitorBase):
    """Start / stop / is_running."""

    def setUp(self) -> None:
        super().setUp()
        self.monitor = ScreenMonitor(poll_interval=0.01, threshold=30)

    def test_start_stop_lifecycle(self) -> None:
        """Starting then stopping should transition running state correctly."""
        self.assertFalse(self.monitor.is_running())
        self.monitor.start()
        self.assertTrue(self.monitor.is_running())
        self.monitor.stop()
        self.assertFalse(self.monitor.is_running())

    def test_double_start_is_idempotent(self) -> None:
        """Calling start() when already running is a no-op (no crash)."""
        self.monitor.start()
        self.monitor.start()  # should not raise
        self.assertTrue(self.monitor.is_running())
        self.monitor.stop()

    def test_stop_without_start_does_not_raise(self) -> None:
        """Calling stop() on a monitor that was never started is safe."""
        m = ScreenMonitor()
        m.stop()  # should not raise

    def test_is_running_returns_correct_state(self) -> None:
        """is_running() matches the internal thread's liveness."""
        self.assertFalse(self.monitor.is_running())
        self.monitor.start()
        self.assertTrue(self.monitor.is_running())
        self.monitor.stop()
        self.assertFalse(self.monitor.is_running())


class TestScreenMonitorWithMockCapture(TestScreenMonitorBase):
    """Callback, latest_change, capture_count, and error handling.

    Uses a mocked ``capture_screen`` to avoid depending on a display.
    """

    def setUp(self) -> None:
        super().setUp()
        # Patch capture_screen where it is imported in screen_monitor
        self._capture_patcher = patch(
            "SeeOnDesk.screen_monitor.capture_screen", autospec=True
        )
        self.mock_capture = self._capture_patcher.start()
        self.addCleanup(self._capture_patcher.stop)

    def _make_monitor(self, **kwargs) -> ScreenMonitor:
        opts = dict(poll_interval=0.01, threshold=30)
        opts.update(kwargs)
        self.monitor = ScreenMonitor(**opts)
        return self.monitor

    # -- Callback -----------------------------------------------------------

    def test_on_change_callback_receives_event(self) -> None:
        """A registered callback should be invoked with a ScreenChange."""
        self.mock_capture.side_effect = _make_alternating_capture()
        monitor = self._make_monitor()

        event = threading.Event()
        received: list[ScreenChange] = []

        def cb(change: ScreenChange) -> None:
            received.append(change)
            event.set()

        monitor.on_change(cb)
        monitor.start()

        self.assertTrue(event.wait(timeout=3.0), "Callback was not invoked within timeout")
        monitor.stop()

        self.assertGreater(len(received), 0)
        for change in received:
            self.assertIsInstance(change, ScreenChange)
            self.assertIn(change.change_type, ("none", "minor", "significant", "full"))

    def test_multiple_callbacks_all_fire(self) -> None:
        """All registered callbacks should receive the same ScreenChange."""
        self.mock_capture.side_effect = _make_alternating_capture()
        monitor = self._make_monitor()

        event1 = threading.Event()
        event2 = threading.Event()
        results: list[list[ScreenChange]] = [[], []]

        def make_cb(idx: int, evt: threading.Event):
            def cb(change: ScreenChange) -> None:
                results[idx].append(change)
                evt.set()
            return cb

        monitor.on_change(make_cb(0, event1))
        monitor.on_change(make_cb(1, event2))
        monitor.start()

        self.assertTrue(event1.wait(timeout=3.0), "Callback 1 not invoked")
        self.assertTrue(event2.wait(timeout=3.0), "Callback 2 not invoked")
        monitor.stop()

        self.assertGreater(len(results[0]), 0)
        self.assertEqual(len(results[0]), len(results[1]))

        # Both callbacks should have seen the same events (same timestamp)
        for c1, c2 in zip(results[0], results[1]):
            self.assertEqual(c1.timestamp, c2.timestamp)

    def test_callback_exception_does_not_crash_monitor(self) -> None:
        """A callback that raises should be caught and not stop the loop."""
        self.mock_capture.side_effect = _make_alternating_capture()
        monitor = self._make_monitor()

        event = threading.Event()
        errors: list[Exception] = []

        def faulty_cb(change: ScreenChange) -> None:
            raise RuntimeError("deliberate failure")

        def good_cb(change: ScreenChange) -> None:
            event.set()

        monitor.on_change(faulty_cb)
        monitor.on_change(good_cb)
        monitor.start()

        self.assertTrue(event.wait(timeout=3.0), "Good callback was never invoked")
        monitor.stop()

    # -- latest_change ------------------------------------------------------

    def test_latest_change_returns_most_recent(self) -> None:
        """latest_change() should return the most recent ScreenChange after captures."""
        self.mock_capture.side_effect = _make_alternating_capture()
        monitor = self._make_monitor()

        event = threading.Event()

        def cb(change: ScreenChange) -> None:
            event.set()

        monitor.on_change(cb)
        monitor.start()
        self.assertTrue(event.wait(timeout=3.0))
        monitor.stop()

        latest = monitor.latest_change()
        self.assertIsNotNone(latest)
        self.assertIsInstance(latest, ScreenChange)

    def test_latest_change_is_none_before_any_capture(self) -> None:
        """Before the first poll, latest_change() should be None."""
        monitor = self._make_monitor()
        self.assertIsNone(monitor.latest_change())

    # -- capture_count ------------------------------------------------------

    def test_capture_count_increments(self) -> None:
        """capture_count() should increase after each successful capture."""
        self.mock_capture.side_effect = _make_static_capture()
        monitor = self._make_monitor()

        self.assertEqual(monitor.capture_count(), 0)

        event = threading.Event()
        monitor.on_change(lambda _: event.set())
        monitor.start()
        self.assertTrue(event.wait(timeout=3.0))
        monitor.stop()

        self.assertGreater(monitor.capture_count(), 0)

    def test_capture_count_reflects_multiple_cycles(self) -> None:
        """After several polling cycles, capture_count should reflect the total."""
        self.mock_capture.side_effect = _make_static_capture()
        monitor = self._make_monitor(poll_interval=0.005)

        # Let the monitor run for a short while
        monitor.start()
        time.sleep(0.05)  # ~10 cycles at 5 ms interval
        monitor.stop()

        self.assertGreaterEqual(monitor.capture_count(), 3)  # at least a few

    # -- Temp directory cleanup ---------------------------------------------

    def test_stop_cleans_up_temp_directory(self) -> None:
        """After stop(), the temporary directory created by the monitor
        should be removed."""
        self.mock_capture.side_effect = _make_static_capture()
        monitor = self._make_monitor()
        tmp_dir = monitor._tmp_dir  # access private attr for verification

        self.assertTrue(tmp_dir.exists(), "Temp dir should exist before stop")
        monitor.start()
        monitor.stop()
        self.assertFalse(tmp_dir.exists(), "Temp dir should be gone after stop")

    def test_temp_directory_has_unique_name(self) -> None:
        """Each monitor instance gets its own temp directory."""
        m1 = ScreenMonitor()
        m2 = ScreenMonitor()
        self.assertNotEqual(m1._tmp_dir, m2._tmp_dir)
        m1.stop()
        m2.stop()

    # -- Capture failure handling -------------------------------------------

    def test_capture_failure_does_not_crash(self) -> None:
        """When capture_screen returns False, the monitor should log a warning
        and continue without crashing."""
        self.mock_capture.return_value = False
        monitor = self._make_monitor()

        try:
            monitor.start()
            time.sleep(0.05)  # let a few cycles pass
        except Exception:
            self.fail("Monitor raised an unhandled exception on capture failure")
        finally:
            monitor.stop()

        self.assertEqual(monitor.capture_count(), 0)

    def test_capture_failure_then_recovery(self) -> None:
        """After failing, a subsequent successful capture should work normally."""
        call_count = [0]

        def _capture_with_failure(path: str | Path) -> bool:
            call_count[0] += 1
            if call_count[0] <= 2:
                return False  # first two calls fail
            Image.new("RGB", (WIDTH, HEIGHT), (100, 100, 100)).save(path)
            return True

        self.mock_capture.side_effect = _capture_with_failure
        monitor = self._make_monitor(poll_interval=0.01)

        event = threading.Event()
        monitor.on_change(lambda _: event.set())
        monitor.start()
        self.assertTrue(event.wait(timeout=3.0), "Callback never fired after recovery")
        monitor.stop()

        self.assertGreater(monitor.capture_count(), 0)

    # -- Region cropping ----------------------------------------------------

    def test_region_is_attached_to_change(self) -> None:
        """When a region is configured, it appears in the ScreenChange.region field."""
        self.mock_capture.side_effect = _make_static_capture()
        region = (10, 10, 40, 40)
        monitor = self._make_monitor(region=region)

        event = threading.Event()
        changes: list[ScreenChange] = []

        def cb(change: ScreenChange) -> None:
            changes.append(change)
            event.set()

        monitor.on_change(cb)
        monitor.start()
        self.assertTrue(event.wait(timeout=3.0))
        monitor.stop()

        for c in changes:
            self.assertEqual(c.region, region)

    def test_no_region_leaves_region_none(self) -> None:
        """Without a configured region, ScreenChange.region should be None
        (full-screen mode)."""
        self.mock_capture.side_effect = _make_static_capture()
        monitor = self._make_monitor(region=None)

        event = threading.Event()
        changes: list[ScreenChange] = []

        def cb(change: ScreenChange) -> None:
            changes.append(change)
            event.set()

        monitor.on_change(cb)
        monitor.start()
        self.assertTrue(event.wait(timeout=3.0))
        monitor.stop()

        for c in changes:
            self.assertIsNone(c.region)

    # -- save_screenshots flag ----------------------------------------------

    def test_save_screenshots_flag_persists_on_disk(self) -> None:
        """When save_screenshots=True and save_dir is set, screenshots are saved.

        The first capture does not call ``compute_diff`` (no previous frame),
        so we wait for a *second* callback to ensure a diff cycle has run.
        """
        self.mock_capture.side_effect = _make_alternating_capture()
        with tempfile.TemporaryDirectory() as tmpdir:
            monitor = self._make_monitor(
                save_screenshots=True,
                save_dir=tmpdir,
            )

            call_count: list[int] = [0]
            event = threading.Event()

            def cb(_change: ScreenChange) -> None:
                call_count[0] += 1
                if call_count[0] >= 2:
                    event.set()

            monitor.on_change(cb)
            monitor.start()
            self.assertTrue(event.wait(timeout=3.0))
            monitor.stop()

            # At least some screenshot files should exist in tmpdir
            files = list(Path(tmpdir).iterdir())
            self.assertGreater(len(files), 0)
            self.assertTrue(
                any(f.name.startswith("before_") for f in files),
                "Expected a 'before_' screenshot file",
            )
            self.assertTrue(
                any(f.name.startswith("after_") for f in files),
                "Expected an 'after_' screenshot file",
            )


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
