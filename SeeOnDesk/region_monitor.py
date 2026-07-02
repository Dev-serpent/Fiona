"""Region-based text change monitoring for Fiona.

Provides a :class:`RegionMonitor` that watches screen regions via OCR and
emits :class:`RegionTextChange` events when the detected text changes.
Each watched region runs in its own daemon polling thread using a
:class:`threading.Event` for clean shutdown.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .ocr import OcrResult, read_screen_region

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RegionConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class RegionConfig:
    """Configuration for a single monitored screen region.

    Attributes:
        region: ``(left, top, width, height)`` bounding box of the screen
            region to watch.
        poll_interval: Seconds between OCR polls (default 1.0).
        lang: Tesseract language code (default ``"eng"``).
        min_confidence: Minimum OCR confidence (0.0–100.0) to consider a
            reading.  ``0.0`` accepts all results (default).
        change_threshold: How to determine a text change. ``"any"`` (default)
            fires on any string inequality; ``"content"`` ignores whitespace-
            only differences.
    """

    region: tuple[int, int, int, int]
    poll_interval: float = 1.0
    lang: str = "eng"
    min_confidence: float = 0.0
    change_threshold: str = "any"


# ---------------------------------------------------------------------------
# RegionTextChange dataclass
# ---------------------------------------------------------------------------


@dataclass
class RegionTextChange:
    """Describes a text change detected in a watched screen region.

    Attributes:
        watch_id: Unique identifier for the watch that produced this event.
        region: The ``(left, top, width, height)`` bounding box being watched.
        old_text: The previous text content before the change.
        new_text: The current text content after the change.
        timestamp: ISO 8601 timestamp of when the change was detected.
        diff_type: Classification -- ``"appeared"``, ``"changed"``,
            ``"disappeared"``, or ``"unchanged"``.
    """

    watch_id: str
    region: tuple[int, int, int, int]
    old_text: str
    new_text: str
    timestamp: str
    diff_type: str


# ---------------------------------------------------------------------------
# Internal watch state holder
# ---------------------------------------------------------------------------


class _RegionWatch:
    """Runtime state for a single region watch, including its polling thread.

    Each watch runs its own daemon thread that polls OCR at the configured
    interval and invokes the user-provided callback when text changes are
    detected.
    """

    def __init__(
        self,
        watch_id: str,
        config: RegionConfig,
        callback: Callable[[RegionTextChange], None],
        ocr_func: Callable[..., OcrResult],
    ) -> None:
        self.watch_id = watch_id
        self.config = config
        self.callback = callback
        self.ocr_func = ocr_func
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._poll_loop,
            name=f"RegionMonitor-{watch_id}",
            daemon=True,
        )
        self.previous_text: str = ""

    def start(self) -> None:
        """Launch the daemon polling thread."""
        self.thread.start()

    def stop(self) -> None:
        """Signal the polling thread to exit on its next iteration."""
        self.stop_event.set()

    def _poll_loop(self) -> None:
        """Main polling loop -- runs in a daemon thread.

        On each cycle the thread sleeps for *poll_interval* seconds (or
        until the stop event is signalled), performs OCR on the configured
        screen region, compares the result to the previous text, and fires
        the callback when a meaningful change is detected.
        """
        while not self.stop_event.is_set():
            # Block for the poll interval (or until stop is signalled)
            if self.stop_event.wait(self.config.poll_interval):
                break

            # Perform OCR on the configured screen region
            try:
                result = self.ocr_func(
                    region=self.config.region,
                    lang=self.config.lang,
                )
            except Exception:
                logger.exception(
                    "OCR call failed for watch %s, skipping cycle",
                    self.watch_id,
                )
                continue

            # Handle OCR errors gracefully
            if not result.success:
                logger.warning(
                    "OCR error for watch %s: %s",
                    self.watch_id,
                    result.error,
                )
                continue

            # Apply minimum confidence filter
            if result.confidence < self.config.min_confidence:
                logger.debug(
                    "OCR confidence %.1f below min_confidence %.1f "
                    "for watch %s, skipping cycle",
                    result.confidence,
                    self.config.min_confidence,
                    self.watch_id,
                )
                continue

            current_text = result.text

            # Determine effective texts for comparison based on threshold
            if self.config.change_threshold == "content":
                effective_old = self.previous_text.strip()
                effective_new = current_text.strip()
            else:
                effective_old = self.previous_text
                effective_new = current_text

            # Classify the type of change
            if not self.previous_text and current_text:
                diff_type = "appeared"
            elif self.previous_text and not current_text:
                diff_type = "disappeared"
            elif effective_old != effective_new:
                diff_type = "changed"
            else:
                diff_type = "unchanged"

            # Retain the raw previous text before updating
            old_text = self.previous_text
            self.previous_text = current_text

            # Only fire the callback for actual changes
            if diff_type != "unchanged":
                change = RegionTextChange(
                    watch_id=self.watch_id,
                    region=self.config.region,
                    old_text=old_text,
                    new_text=current_text,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    diff_type=diff_type,
                )
                try:
                    self.callback(change)
                except Exception:
                    logger.exception(
                        "Region change callback for watch %s "
                        "raised an exception",
                        self.watch_id,
                    )


# ---------------------------------------------------------------------------
# RegionMonitor -- manages lifecycle of watched regions
# ---------------------------------------------------------------------------


class RegionMonitor:
    """Manages lifecycle of watched screen regions with OCR-based text
    detection.

    Each watched region runs in its own daemon polling thread.  Thread
    safety for the watch registry is provided via a
    :class:`threading.Lock`.

    Usage::

        monitor = RegionMonitor()

        config = RegionConfig(
            region=(100, 200, 300, 150),
            poll_interval=2.0,
            lang="eng",
        )

        def on_text_change(change: RegionTextChange) -> None:
            print(f"[{change.diff_type}] {change.new_text!r}")

        watch_id = monitor.watch_region(config, on_change=on_text_change)
        ...
        monitor.unwatch_region(watch_id)
        monitor.stop_all()
    """

    def __init__(
        self,
        *,
        ocr_func: Callable[..., OcrResult] | None = None,
    ) -> None:
        """Initialise the monitor.

        Args:
            ocr_func: Optional override for the OCR function.  Defaults to
                :func:`SeeOnDesk.ocr.read_screen_region`.  The callable
                must accept ``region`` as a positional argument and ``lang``
                as a keyword argument, returning an :class:`OcrResult`.
        """
        self._ocr_func = ocr_func or read_screen_region
        self._lock = threading.Lock()
        self._watches: dict[str, _RegionWatch] = {}

    def watch_region(
        self,
        config: RegionConfig,
        on_change: Callable[[RegionTextChange], None],
    ) -> str:
        """Register a region watch and begin polling in a daemon thread.

        Args:
            config: The :class:`RegionConfig` describing the region and
                polling behaviour.
            on_change: A callback invoked with a :class:`RegionTextChange`
                whenever the text in the region changes.  Exceptions raised
                by the callback are caught and logged.

        Returns:
            A unique ``watch_id`` string that can be used to later stop
            this watch via :meth:`unwatch_region`.
        """
        watch_id = uuid.uuid4().hex[:12]
        watch = _RegionWatch(
            watch_id=watch_id,
            config=config,
            callback=on_change,
            ocr_func=self._ocr_func,
        )
        with self._lock:
            self._watches[watch_id] = watch
        watch.start()
        logger.debug(
            "Started watching region %s with watch_id=%s, "
            "lang=%s, interval=%.1f",
            config.region,
            watch_id,
            config.lang,
            config.poll_interval,
        )
        return watch_id

    def unwatch_region(self, watch_id: str) -> bool:
        """Stop monitoring a specific region and clean up its thread.

        Args:
            watch_id: The identifier returned by :meth:`watch_region`.

        Returns:
            ``True`` if the watch was found and stopped, ``False`` if
            *watch_id* was not registered.
        """
        with self._lock:
            watch = self._watches.pop(watch_id, None)
        if watch is None:
            return False

        watch.stop()
        # Avoid joining the calling thread if it happens to be the watch's
        # own polling thread (e.g. if unwatch_region is invoked from within
        # a callback).
        if watch.thread is not threading.current_thread():
            watch.thread.join(timeout=5.0)
        logger.debug("Stopped watching region %s", watch_id)
        return True

    def list_watched_regions(self) -> list[dict]:
        """Return metadata for all active region watches.

        Returns:
            A list of dictionaries, each containing the watch's current
            configuration and state.
        """
        with self._lock:
            return [
                {
                    "watch_id": watch.watch_id,
                    "region": watch.config.region,
                    "poll_interval": watch.config.poll_interval,
                    "lang": watch.config.lang,
                    "min_confidence": watch.config.min_confidence,
                    "change_threshold": watch.config.change_threshold,
                    "previous_text": watch.previous_text,
                }
                for watch in self._watches.values()
            ]

    def stop_all(self) -> None:
        """Stop all active region watches and clean up their threads.

        After this call the monitor can still be used to register new
        watches via :meth:`watch_region`.
        """
        with self._lock:
            watch_ids = list(self._watches.keys())
        for watch_id in watch_ids:
            self.unwatch_region(watch_id)
        logger.debug("All region watches stopped (%d total)", len(watch_ids))

    def is_watching(self, watch_id: str) -> bool:
        """Check whether a given watch is currently active.

        Args:
            watch_id: The identifier returned by :meth:`watch_region`.

        Returns:
            ``True`` if the watch is registered and polling.
        """
        with self._lock:
            return watch_id in self._watches
