"""Screen monitoring with pixel-diff change detection for Fiona.

Provides a :class:`ScreenMonitor` that polls the screen at a configurable
interval and emits :class:`ScreenChange` events when pixel-level differences
are detected.  The pixel-diff engine (:func:`compute_diff`) uses numpy for
efficient array comparison.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from .vision import capture_screen

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ScreenChange dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScreenChange:
    """Describes a detected change between two consecutive screen captures.

    Attributes:
        timestamp: ISO 8601 timestamp of when the change was detected.
        bbox: Bounding box of the changed area ``(left, top, right, bottom)``,
            or ``None`` when no change was detected.
        pixel_count: Number of pixels that exceeded the difference threshold.
        total_pixels: Total number of pixels in the monitored region.
        change_ratio: Ratio of changed pixels to total (0.0–1.0).
        change_type: Classification -- ``"none"``, ``"minor"``,
            ``"significant"``, or ``"full"``.
        screenshot_before: Path to the "before" screenshot, if saved.
        screenshot_after: Path to the "after" screenshot, if saved.
        region: The monitored region ``(left, top, right, bottom)``, or
            ``None`` for full screen.
    """

    timestamp: str
    bbox: tuple[int, int, int, int] | None = None
    pixel_count: int = 0
    total_pixels: int = 0
    change_ratio: float = 0.0
    change_type: str = "none"
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    region: tuple[int, int, int, int] | None = None


# ---------------------------------------------------------------------------
# Pixel-diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    before: Image.Image,
    after: Image.Image,
    threshold: int = 30,
    save_dir: str | Path | None = None,
) -> ScreenChange:
    """Compare two PIL Images pixel-by-pixel and report differences.

    Converts both images to numpy arrays, computes the absolute difference
    per channel, and counts pixels where *any* channel exceeds *threshold*.

    Args:
        before: The earlier ("before") screenshot.
        after: The later ("after") screenshot.
        threshold: Per-channel intensity difference (0--255) above which a
            pixel is considered changed.  Default 30.
        save_dir: Optional directory path.  When provided, both *before* and
            *after* images are saved there with timestamped filenames.

    Returns:
        A :class:`ScreenChange` describing the differences.
    """
    # Ensure consistent image modes for numpy comparison
    if before.mode != "RGB":
        before = before.convert("RGB")
    if after.mode != "RGB":
        after = after.convert("RGB")

    # Handle size mismatch gracefully -- treat as a full change
    if before.size != after.size:
        logger.warning(
            "Image sizes differ: before=%s, after=%s. Reporting full change.",
            before.size,
            after.size,
        )
        max_w = max(before.width, after.width)
        max_h = max(before.height, after.height)
        total = max_w * max_h
        ts = datetime.now(timezone.utc).isoformat()
        result = ScreenChange(
            timestamp=ts,
            bbox=(0, 0, max_w, max_h),
            pixel_count=total,
            total_pixels=total,
            change_ratio=1.0,
            change_type="full",
        )
        _maybe_save_screenshots(before, after, save_dir, result)
        return result

    before_arr = np.array(before, dtype=np.int16)
    after_arr = np.array(after, dtype=np.int16)

    # Per-channel absolute difference
    diff = np.abs(before_arr - after_arr)

    # Pixels where any channel exceeds the threshold
    changed_mask = np.any(diff > threshold, axis=2)

    total_pixels = before_arr.shape[0] * before_arr.shape[1]
    pixel_count = int(np.sum(changed_mask))
    change_ratio = pixel_count / total_pixels if total_pixels > 0 else 0.0

    # Find bounding box of the changed region
    if pixel_count > 0:
        rows, cols = np.where(changed_mask)
        bbox = (
            int(cols.min()),
            int(rows.min()),
            int(cols.max()) + 1,
            int(rows.max()) + 1,
        )
    else:
        bbox = None

    # Classify change magnitude
    if change_ratio == 0.0:
        change_type = "none"
    elif change_ratio < 0.01:
        change_type = "minor"
    elif change_ratio < 0.30:
        change_type = "significant"
    else:
        change_type = "full"

    ts = datetime.now(timezone.utc).isoformat()

    result = ScreenChange(
        timestamp=ts,
        bbox=bbox,
        pixel_count=pixel_count,
        total_pixels=total_pixels,
        change_ratio=round(change_ratio, 6),
        change_type=change_type,
    )

    _maybe_save_screenshots(before, after, save_dir, result)

    return result


def _maybe_save_screenshots(
    before: Image.Image,
    after: Image.Image,
    save_dir: str | Path | None,
    result: ScreenChange,
) -> None:
    """If *save_dir* is provided, save before/after images and update *result*."""
    if save_dir is None:
        return

    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    # Build a filesystem-safe timestamp from the result's timestamp
    safe_ts = (
        result.timestamp.replace(":", "-")
        .replace("+", "_")
        .replace(" ", "_")
    )
    before_path = save_path / f"before_{safe_ts}.png"
    after_path = save_path / f"after_{safe_ts}.png"

    try:
        before.save(str(before_path))
        result.screenshot_before = str(before_path)
    except Exception as exc:
        logger.warning("Failed to save before screenshot: %s", exc)

    try:
        after.save(str(after_path))
        result.screenshot_after = str(after_path)
    except Exception as exc:
        logger.warning("Failed to save after screenshot: %s", exc)


# ---------------------------------------------------------------------------
# ScreenMonitor -- continuous polling with pixel-diff
# ---------------------------------------------------------------------------


class ScreenMonitor:
    """Continuously polls the screen and emits change events when pixel
    differences exceed a configurable threshold.

    The monitor runs a daemon thread that captures the screen at a fixed
    interval.  On each capture the new frame is compared against the
    previous frame using :func:`compute_diff`.

    Thread safety is provided via a :class:`threading.Lock` for shared
    state and a :class:`threading.Event` for clean shutdown.

    Usage::

        monitor = ScreenMonitor(poll_interval=0.5, threshold=30)

        def on_change(change: ScreenChange) -> None:
            print(f"Detected {change.change_type} change")

        monitor.on_change(on_change)
        monitor.start()
        ...
        monitor.stop()
    """

    def __init__(
        self,
        *,
        poll_interval: float = 0.5,
        region: tuple[int, int, int, int] | None = None,
        threshold: int = 30,
        save_screenshots: bool = False,
        save_dir: str | Path | None = None,
    ) -> None:
        self._poll_interval = poll_interval
        self._region = region
        self._threshold = threshold
        self._save_screenshots = save_screenshots
        self._save_dir = Path(save_dir) if save_dir is not None else None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[ScreenChange], None]] = []
        self._latest_change: ScreenChange | None = None
        self._capture_count: int = 0
        self._previous_image: Image.Image | None = None

        # Temporary directory for intermediate screen captures
        self._tmp_dir = Path(
            tempfile.mkdtemp(prefix="fiona_screen_monitor_")
        )
        self._capture_path = self._tmp_dir / "capture.png"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the polling thread.

        If the monitor is already running this is a no-op.
        """
        if self._thread is not None and self._thread.is_alive():
            logger.debug("ScreenMonitor is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="ScreenMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.debug("ScreenMonitor started")

    def stop(self) -> None:
        """Signal the polling thread to stop and wait for it to finish.

        After this call the monitor is no longer usable; call :meth:`start`
        again to begin a new session.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        # Clean up the temporary capture directory
        try:
            shutil.rmtree(str(self._tmp_dir), ignore_errors=True)
        except Exception as exc:
            logger.warning(
                "Failed to clean up temp dir %s: %s", self._tmp_dir, exc
            )

        logger.debug("ScreenMonitor stopped")

    def is_running(self) -> bool:
        """Return ``True`` if the polling thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def on_change(
        self, callback: Callable[[ScreenChange], None]
    ) -> None:
        """Register *callback* to be invoked on each screen change event.

        Callbacks receive a :class:`ScreenChange` instance.  Exceptions
        raised by a callback are caught and logged so that one faulty
        callback does not prevent others from being called.
        """
        self._callbacks.append(callback)

    def latest_change(self) -> ScreenChange | None:
        """Return the most recent :class:`ScreenChange`, or ``None``."""
        with self._lock:
            return self._latest_change

    def capture_count(self) -> int:
        """Return the total number of screen captures made so far."""
        with self._lock:
            return self._capture_count

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Main polling loop -- runs in a daemon thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception(
                    "Unhandled error in screen monitor poll loop"
                )

            # Block for the poll interval (or until stop is signalled)
            if self._stop_event.wait(self._poll_interval):
                break

    def _poll_once(self) -> None:
        """Perform a single capture-and-diff cycle."""
        # Capture screen to a temporary file
        if not capture_screen(self._capture_path):
            logger.warning("Screen capture failed, skipping frame")
            return

        try:
            # .copy() forces pixel data to be loaded immediately so the
            # temporary file can be safely overwritten next cycle
            current = Image.open(self._capture_path).copy()
        except Exception as exc:
            logger.warning(
                "Failed to open captured screenshot: %s", exc
            )
            return

        # Crop to monitored region if specified
        if self._region is not None:
            left, top, right, bottom = self._region
            current = current.crop((left, top, right, bottom))

        with self._lock:
            self._capture_count += 1
            previous = self._previous_image

        if previous is None:
            # First frame -- no "before" image to diff against; emit
            # a change record with change_type="none"
            change = ScreenChange(
                timestamp=datetime.now(timezone.utc).isoformat(),
                bbox=None,
                pixel_count=0,
                total_pixels=current.width * current.height,
                change_ratio=0.0,
                change_type="none",
                region=self._region,
            )
        else:
            # Determine whether to persist screenshots
            save_dir: Path | None = None
            if self._save_screenshots and self._save_dir is not None:
                save_dir = self._save_dir

            change = compute_diff(
                previous,
                current,
                threshold=self._threshold,
                save_dir=save_dir,
            )
            # Attach the monitored region for traceability
            change.region = self._region

        # Update shared state under lock
        with self._lock:
            self._latest_change = change
            self._previous_image = current

        # Notify callbacks outside the lock to avoid holding it during
        # user-defined code
        for callback in self._callbacks:
            try:
                callback(change)
            except Exception:
                logger.exception(
                    "Screen change callback %r raised an exception",
                    callback,
                )
