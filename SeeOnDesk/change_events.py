"""Unified change event system for Fiona's desktop perception layer.

Wraps :class:`SeeOnDesk.screen_monitor.ScreenMonitor` and
:class:`SeeOnDesk.region_monitor.RegionMonitor` outputs into a single
pub/sub event stream via :class:`EventEmitter`.

Typical usage::

    emitter = EventEmitter()

    # Subscribe to screen changes
    emitter.subscribe("screen_changed", on_screen_change)

    # Hook up adapters to existing monitors
    monitor = ScreenMonitor(...)
    monitor.on_change(make_screen_change_adapter(emitter))

    region_monitor = RegionMonitor(...)
    region_monitor.watch_region(
        config,
        on_change=make_region_change_adapter(emitter),
    )
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable

from .region_monitor import RegionTextChange
from .screen_monitor import ScreenChange

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EventType constants
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    """Categorisation of change events emitted by the perception layer."""

    TEXT_CHANGED = "text_changed"          # Region text changed
    SCREEN_CHANGED = "screen_changed"      # Screen pixel diff detected
    POPUP_DETECTED = "popup_detected"      # Small centred change (potential popup)
    REGION_UPDATED = "region_updated"      # Region text updated (even if unchanged)
    NEW_UI_STATE = "new_ui_state"          # Full screen transition
    MONITOR_STARTED = "monitor_started"    # Monitor lifecycle event
    MONITOR_STOPPED = "monitor_stopped"    # Monitor lifecycle event


# ---------------------------------------------------------------------------
# ChangeEvent dataclass
# ---------------------------------------------------------------------------


@dataclass
class ChangeEvent:
    """A single change event dispatched through the :class:`EventEmitter`.

    Attributes:
        event_type: One of :class:`EventType` values.
        source: Human-readable origin identifier, e.g. ``"screen_monitor"``
            or ``"region_monitor:watch_abc123"``.
        timestamp: ISO 8601 timestamp of when the event was detected.
        data: Event-specific payload dictionary.  Contents vary by
            *event_type* (see adapter docstrings for details).
        confidence: Detection confidence in the range 0.0--1.0 (default 1.0).
    """

    event_type: str
    source: str
    timestamp: str
    data: dict = field(default_factory=dict)
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Internal subscription record
# ---------------------------------------------------------------------------


class _Subscription:
    """Internal record for a single subscriber registration."""

    __slots__ = ("subscription_id", "event_type", "callback")

    def __init__(
        self,
        subscription_id: str,
        event_type: str,
        callback: Callable[[ChangeEvent], None],
    ) -> None:
        self.subscription_id = subscription_id
        self.event_type = event_type
        self.callback = callback


# ---------------------------------------------------------------------------
# EventEmitter — thread-safe pub/sub event bus
# ---------------------------------------------------------------------------


class EventEmitter:
    """Thread-safe publish/subscribe event bus for change events.

    Subscribers register a callback for a specific :class:`EventType` (or
    ``"*"`` to receive all events).  Events are dispatched synchronously
    when :meth:`emit` is called; a faulty callback does not prevent
    delivery to other subscribers.

    Usage::

        emitter = EventEmitter()
        sid = emitter.subscribe("screen_changed", my_callback)
        ...
        emitter.unsubscribe(sid)
        emitter.clear()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, _Subscription] = {}

    def subscribe(
        self,
        event_type: str,
        callback: Callable[[ChangeEvent], None],
    ) -> str:
        """Register *callback* for events matching *event_type*.

        Args:
            event_type: An :class:`EventType` value (as a string) or
                ``"*"`` to receive all events.
            callback: A callable accepting a single :class:`ChangeEvent`
                argument.

        Returns:
            A subscription ID (UUID hex string) that can be passed to
            :meth:`unsubscribe`.
        """
        subscription_id = uuid.uuid4().hex
        sub = _Subscription(
            subscription_id=subscription_id,
            event_type=event_type,
            callback=callback,
        )
        with self._lock:
            self._subscribers[subscription_id] = sub
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove the subscription identified by *subscription_id*.

        Args:
            subscription_id: The ID returned by :meth:`subscribe`.

        Returns:
            ``True`` if the subscription was found and removed, ``False``
            if *subscription_id* was not registered.
        """
        with self._lock:
            if subscription_id in self._subscribers:
                del self._subscribers[subscription_id]
                return True
            return False

    def emit(self, event: ChangeEvent) -> None:
        """Dispatch *event* to all matching subscribers.

        Callbacks are invoked synchronously inside this method.  If a
        callback raises an exception it is caught and logged so that other
        subscribers still receive the event.

        Args:
            event: The :class:`ChangeEvent` to dispatch.
        """
        # Snapshot the subscriber list under the lock so we don't hold it
        # while calling user code.
        with self._lock:
            matching = [
                sub
                for sub in self._subscribers.values()
                if sub.event_type in ("*", event.event_type)
            ]

        for sub in matching:
            try:
                sub.callback(event)
            except Exception:
                logger.exception(
                    "Subscriber %r for event_type=%r raised an exception",
                    sub.subscription_id,
                    sub.event_type,
                )

    def clear(self) -> None:
        """Remove all subscribers."""
        with self._lock:
            self._subscribers.clear()


# ---------------------------------------------------------------------------
# Adapter: ScreenMonitor -> EventEmitter
# ---------------------------------------------------------------------------


def make_screen_change_adapter(
    emitter: EventEmitter,
    source: str = "screen_monitor",
) -> Callable[[ScreenChange], None]:
    """Return a callback suitable for :meth:`ScreenMonitor.on_change`.

    The returned callback translates :class:`ScreenChange` events into
    :class:`ChangeEvent` instances and emits them through *emitter*.

    Event mapping:

    ========================== ==============================
    ``ScreenChange.change_type``  Emitted :class:`EventType`
    ========================== ==============================
    ``"full"``                   ``EventType.NEW_UI_STATE``
    ``"significant"``            ``EventType.SCREEN_CHANGED``
    ``"minor"``                  ``EventType.SCREEN_CHANGED``
    ``"none"``                   *no event emitted*
    ========================== ==============================

    If the changed bounding box is small (area < 20% of monitored area)
    **and** centred (its centre lies within 20%--80% of the monitored
    area in each dimension), an additional ``EventType.POPUP_DETECTED``
    event is also emitted.

    The ``data`` payload contains the following keys from the original
    :class:`ScreenChange`: ``bbox``, ``pixel_count``, ``total_pixels``,
    ``change_ratio``, ``change_type``, ``screenshot_before``,
    ``screenshot_after``, and ``region``.

    Args:
        emitter: The :class:`EventEmitter` to dispatch into.
        source: Source string used as ``ChangeEvent.source``.

    Returns:
        A callable that accepts a :class:`ScreenChange` and emits
        corresponding :class:`ChangeEvent` instances.
    """
    _validate_emitter(emitter)

    def _adapter(change: ScreenChange) -> None:
        if change.change_type == "none":
            return

        if change.change_type == "full":
            event_type = EventType.NEW_UI_STATE
        else:
            event_type = EventType.SCREEN_CHANGED

        data = {
            "bbox": change.bbox,
            "pixel_count": change.pixel_count,
            "total_pixels": change.total_pixels,
            "change_ratio": change.change_ratio,
            "change_type": change.change_type,
            "screenshot_before": change.screenshot_before,
            "screenshot_after": change.screenshot_after,
            "region": change.region,
        }

        timestamp = change.timestamp or datetime.now(timezone.utc).isoformat()

        emitter.emit(
            ChangeEvent(
                event_type=event_type,
                source=source,
                timestamp=timestamp,
                data=data,
            )
        )

        # Additional popup detection for small centred bounding boxes
        if _is_potential_popup(change):
            emitter.emit(
                ChangeEvent(
                    event_type=EventType.POPUP_DETECTED,
                    source=source,
                    timestamp=timestamp,
                    data=data,
                )
            )

    return _adapter


# ---------------------------------------------------------------------------
# Adapter: RegionMonitor -> EventEmitter
# ---------------------------------------------------------------------------


def make_region_change_adapter(
    emitter: EventEmitter,
    source_prefix: str = "region_monitor",
) -> Callable[[RegionTextChange], None]:
    """Return a callback suitable for :meth:`RegionMonitor.watch_region`.

    The returned callback translates :class:`RegionTextChange` events into
    :class:`ChangeEvent` instances and emits them through *emitter*.

    Event mapping:

    ============================= ==============================
    ``RegionTextChange.diff_type``   Emitted :class:`EventType`
    ============================= ==============================
    ``"appeared"``                   ``EventType.TEXT_CHANGED``
    ``"changed"``                    ``EventType.TEXT_CHANGED``
    ``"disappeared"``                ``EventType.TEXT_CHANGED``
    ``"unchanged"``                  ``EventType.REGION_UPDATED``
    ============================= ==============================

    The ``data`` payload contains the keys ``watch_id``, ``region``,
    ``old_text``, ``new_text``, and ``diff_type`` from the original
    :class:`RegionTextChange`.

    The ``source`` field in emitted events is set to
    ``"<source_prefix>:<watch_id>"`` so subscribers can distinguish
    events from different watched regions.

    Args:
        emitter: The :class:`EventEmitter` to dispatch into.
        source_prefix: Prefix for the ``ChangeEvent.source`` field
            (default ``"region_monitor"``).

    Returns:
        A callable that accepts a :class:`RegionTextChange` and emits
        corresponding :class:`ChangeEvent` instances.
    """
    _validate_emitter(emitter)

    def _adapter(change: RegionTextChange) -> None:
        if change.diff_type == "unchanged":
            event_type = EventType.REGION_UPDATED
        else:
            event_type = EventType.TEXT_CHANGED

        data = {
            "watch_id": change.watch_id,
            "region": change.region,
            "old_text": change.old_text,
            "new_text": change.new_text,
            "diff_type": change.diff_type,
        }

        source = f"{source_prefix}:{change.watch_id}"
        timestamp = change.timestamp or datetime.now(timezone.utc).isoformat()

        emitter.emit(
            ChangeEvent(
                event_type=event_type,
                source=source,
                timestamp=timestamp,
                data=data,
            )
        )

    return _adapter


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_potential_popup(change: ScreenChange) -> bool:
    """Return ``True`` if *change* looks like a popup (small + centred).

    A change is considered a potential popup when:

    * Its bounding box is not ``None``.
    * The bounding box covers less than 20% of the monitored area.
    * The centre of the bounding box lies between 20% and 80% of each
      dimension of the monitored region (or screen).
    """
    bbox = change.bbox
    if bbox is None:
        return False

    bbox_left, bbox_top, bbox_right, bbox_bottom = bbox
    bbox_width = bbox_right - bbox_left
    bbox_height = bbox_bottom - bbox_top
    bbox_area = bbox_width * bbox_height

    if bbox_area <= 0:
        return False

    # Determine the dimensions of the monitored area
    dims = _get_monitored_dimensions(change)
    if dims is None:
        return False

    mon_width, mon_height = dims
    monitored_area = mon_width * mon_height
    if monitored_area <= 0:
        return False

    # Small check: bbox area < 20% of monitored area
    if bbox_area / monitored_area >= 0.20:
        return False

    # Centred check: bbox centre is within 20%--80% of each dimension
    centre_x = bbox_left + bbox_width / 2
    centre_y = bbox_top + bbox_height / 2

    if not (0.20 * mon_width <= centre_x <= 0.80 * mon_width):
        return False
    if not (0.20 * mon_height <= centre_y <= 0.80 * mon_height):
        return False

    return True


# Module-level cache for screen dimensions to avoid repeated subprocess calls.
_SCREEN_DIMENSION_CACHE: tuple[int, int] | None = None


def _get_monitored_dimensions(
    change: ScreenChange,
) -> tuple[int, int] | None:
    """Return ``(width, height)`` of the area being monitored.

    If ``change.region`` is set (a ``(left, top, right, bottom)`` tuple),
    dimensions are computed from it directly.  Otherwise the function
    attempts to detect the screen resolution from the system (``xrandr``)
    and caches the result.
    """
    if change.region is not None:
        reg_left, reg_top, reg_right, reg_bottom = change.region
        return (reg_right - reg_left, reg_bottom - reg_top)

    return _get_screen_dimensions()


def _get_screen_dimensions() -> tuple[int, int] | None:
    """Return the physical screen resolution via ``xrandr``.

    Results are cached after the first successful call to avoid repeated
    subprocess overhead.
    """
    global _SCREEN_DIMENSION_CACHE

    if _SCREEN_DIMENSION_CACHE is not None:
        return _SCREEN_DIMENSION_CACHE

    try:
        import subprocess

        result = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None

        # Parse the line listing the current screen mode (contains '*')
        for line in result.stdout.splitlines():
            if "*" in line:
                parts = line.split()
                for part in parts:
                    if "x" in part and part.replace("x", "").isdigit():
                        width_str, height_str = part.split("x")
                        dims = (int(width_str), int(height_str))
                        _SCREEN_DIMENSION_CACHE = dims
                        return dims
    except Exception:
        logger.debug("Could not query screen size via xrandr")
        return None

    return None


def _validate_emitter(emitter: object) -> None:
    """Raise ``TypeError`` if *emitter* is not an :class:`EventEmitter`."""
    if not isinstance(emitter, EventEmitter):
        raise TypeError(
            f"Expected an EventEmitter instance, got {type(emitter).__name__}"
        )
