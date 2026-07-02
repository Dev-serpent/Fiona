"""Tests for SeeOnDesk/change_events.py — unified change event system."""

from __future__ import annotations

import concurrent.futures
import threading
import unittest
import uuid

from SeeOnDesk.change_events import (
    ChangeEvent,
    EventEmitter,
    EventType,
    _Subscription,
    _is_potential_popup,
    make_region_change_adapter,
    make_screen_change_adapter,
)
from SeeOnDesk.region_monitor import RegionTextChange
from SeeOnDesk.screen_monitor import ScreenChange


# ===========================================================================
#  EventType tests
# ===========================================================================


class EventTypeTests(unittest.TestCase):
    """All 7 EventType constants exist and are proper strings."""

    EXPECTED = {
        "TEXT_CHANGED": "text_changed",
        "SCREEN_CHANGED": "screen_changed",
        "POPUP_DETECTED": "popup_detected",
        "REGION_UPDATED": "region_updated",
        "NEW_UI_STATE": "new_ui_state",
        "MONITOR_STARTED": "monitor_started",
        "MONITOR_STOPPED": "monitor_stopped",
    }

    def test_all_constants_defined(self) -> None:
        """All seven expected constants exist on EventType."""
        for name in self.EXPECTED:
            self.assertTrue(
                hasattr(EventType, name),
                f"EventType missing constant {name}",
            )

    def test_exactly_seven_members(self) -> None:
        """EventType has exactly 7 members."""
        self.assertEqual(len(EventType), 7)

    def test_members_are_strings(self) -> None:
        """Every member isinstance of str (StrEnum)."""
        for member in EventType:
            self.assertIsInstance(member.value, str)
            self.assertIsInstance(member, str)

    def test_member_values_match_expected(self) -> None:
        """Each member's .value matches the documented string."""
        for name, expected_value in self.EXPECTED.items():
            member = getattr(EventType, name)
            self.assertEqual(member.value, expected_value)

    def test_members_are_comparable_to_strings(self) -> None:
        """StrEnum members compare equal to their string value."""
        self.assertEqual(EventType.TEXT_CHANGED, "text_changed")
        self.assertEqual(EventType.NEW_UI_STATE, "new_ui_state")


# ===========================================================================
#  ChangeEvent tests
# ===========================================================================


class ChangeEventTests(unittest.TestCase):
    """ChangeEvent dataclass field behaviour."""

    def test_default_confidence(self) -> None:
        """confidence defaults to 1.0."""
        event = ChangeEvent(
            event_type=EventType.SCREEN_CHANGED,
            source="test",
            timestamp="2024-01-01T00:00:00",
        )
        self.assertEqual(event.confidence, 1.0)

    def test_default_data_is_empty_dict(self) -> None:
        """data defaults to an empty dict."""
        event = ChangeEvent(
            event_type=EventType.SCREEN_CHANGED,
            source="test",
            timestamp="2024-01-01T00:00:00",
        )
        self.assertEqual(event.data, {})

    def test_default_data_is_fresh_per_instance(self) -> None:
        """Each instance gets its own default dict."""
        e1 = ChangeEvent(event_type="a", source="s", timestamp="t")
        e2 = ChangeEvent(event_type="b", source="s", timestamp="t")
        e1.data["key"] = "val"
        self.assertNotIn("key", e2.data)

    def test_all_fields_set_explicitly(self) -> None:
        """All constructor arguments are stored correctly."""
        event = ChangeEvent(
            event_type=EventType.NEW_UI_STATE,
            source="screen_monitor",
            timestamp="2024-06-15T12:30:00+00:00",
            data={"bbox": (0, 0, 100, 100)},
            confidence=0.85,
        )
        self.assertEqual(event.event_type, EventType.NEW_UI_STATE)
        self.assertEqual(event.source, "screen_monitor")
        self.assertEqual(event.timestamp, "2024-06-15T12:30:00+00:00")
        self.assertEqual(event.data, {"bbox": (0, 0, 100, 100)})
        self.assertEqual(event.confidence, 0.85)

    def test_confidence_accepts_zero(self) -> None:
        """confidence can be 0.0."""
        event = ChangeEvent(
            event_type="x", source="s", timestamp="t", confidence=0.0
        )
        self.assertEqual(event.confidence, 0.0)

    def test_confidence_accepts_one(self) -> None:
        """confidence can be 1.0."""
        event = ChangeEvent(
            event_type="x", source="s", timestamp="t", confidence=1.0
        )
        self.assertEqual(event.confidence, 1.0)


# ===========================================================================
#  EventEmitter tests
# ===========================================================================


class EventEmitterSubscribeTests(unittest.TestCase):
    """Subscription behaviour."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []

    def _collect(self, event: ChangeEvent) -> None:
        self.received.append(event)

    def test_subscribe_returns_non_empty_string(self) -> None:
        sid = self.emitter.subscribe("foo", self._collect)
        self.assertIsInstance(sid, str)
        self.assertGreater(len(sid), 0)

    def test_subscribe_returns_uuid_hex(self) -> None:
        sid = self.emitter.subscribe("foo", self._collect)
        # UUID hex is a 32-character hex string
        self.assertEqual(len(sid), 32)
        # Should be valid hex
        int(sid, 16)

    def test_subscribe_returns_unique_ids(self) -> None:
        s1 = self.emitter.subscribe("a", self._collect)
        s2 = self.emitter.subscribe("a", self._collect)
        s3 = self.emitter.subscribe("b", self._collect)
        self.assertEqual(len({s1, s2, s3}), 3)

    def test_subscribe_allows_multiple_callbacks_same_type(self) -> None:
        received2: list[ChangeEvent] = []

        def collect2(event: ChangeEvent) -> None:
            received2.append(event)

        self.emitter.subscribe("t", self._collect)
        self.emitter.subscribe("t", collect2)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(len(received2), 1)


class EventEmitterEmitTests(unittest.TestCase):
    """Event dispatch behaviour."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []

    def _collect(self, event: ChangeEvent) -> None:
        self.received.append(event)

    def test_emit_sends_to_matching_subscriber(self) -> None:
        self.emitter.subscribe("my_event", self._collect)
        event = ChangeEvent(event_type="my_event", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 1)
        self.assertIs(self.received[0], event)

    def test_emit_does_not_send_to_non_matching(self) -> None:
        self.emitter.subscribe("other", self._collect)
        event = ChangeEvent(event_type="my_event", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 0)

    def test_emit_wildcard_receives_all(self) -> None:
        self.emitter.subscribe("*", self._collect)
        e1 = ChangeEvent(event_type="a", source="s", timestamp="t")
        e2 = ChangeEvent(event_type="b", source="s", timestamp="t")
        self.emitter.emit(e1)
        self.emitter.emit(e2)
        self.assertEqual(len(self.received), 2)
        self.assertIs(self.received[0], e1)
        self.assertIs(self.received[1], e2)

    def test_wildcard_and_specific_both_receive(self) -> None:
        wild_received: list[ChangeEvent] = []

        def collect_wild(event: ChangeEvent) -> None:
            wild_received.append(event)

        self.emitter.subscribe("*", collect_wild)
        self.emitter.subscribe("my_event", self._collect)
        event = ChangeEvent(event_type="my_event", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(wild_received), 1)
        self.assertEqual(len(self.received), 1)

    def test_emit_with_wildcard_event_type_matches_wildcard_only(self) -> None:
        """An event whose event_type is literally '*' matches '*' subscribers."""
        wild_received: list[ChangeEvent] = []

        def collect_wild(event: ChangeEvent) -> None:
            wild_received.append(event)

        specific_received: list[ChangeEvent] = []

        def collect_specific(event: ChangeEvent) -> None:
            specific_received.append(event)

        self.emitter.subscribe("*", collect_wild)
        self.emitter.subscribe("literal_star", collect_specific)
        event = ChangeEvent(event_type="*", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(wild_received), 1)
        self.assertEqual(len(specific_received), 0)


class EventEmitterUnsubscribeTests(unittest.TestCase):
    """Unsubscribe behaviour."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []

    def _collect(self, event: ChangeEvent) -> None:
        self.received.append(event)

    def test_unsubscribe_valid_returns_true(self) -> None:
        sid = self.emitter.subscribe("t", self._collect)
        self.assertTrue(self.emitter.unsubscribe(sid))

    def test_unsubscribe_invalid_returns_false(self) -> None:
        self.assertFalse(self.emitter.unsubscribe("no-such-id"))

    def test_unsubscribe_unknown_id_returns_false(self) -> None:
        sid = self.emitter.subscribe("t", self._collect)
        self.assertTrue(self.emitter.unsubscribe(sid))
        self.assertFalse(self.emitter.unsubscribe(sid))

    def test_emit_after_unsubscribe_does_not_send(self) -> None:
        sid = self.emitter.subscribe("t", self._collect)
        self.emitter.unsubscribe(sid)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 0)

    def test_unsubscribe_only_removes_one_subscriber(self) -> None:
        received2: list[ChangeEvent] = []

        def collect2(event: ChangeEvent) -> None:
            received2.append(event)

        sid1 = self.emitter.subscribe("t", self._collect)
        sid2 = self.emitter.subscribe("t", collect2)
        self.emitter.unsubscribe(sid1)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 0)
        self.assertEqual(len(received2), 1)


class EventEmitterClearTests(unittest.TestCase):
    """Clear behaviour."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []

    def _collect(self, event: ChangeEvent) -> None:
        self.received.append(event)

    def test_clear_removes_all_subscribers(self) -> None:
        self.emitter.subscribe("a", self._collect)
        self.emitter.subscribe("b", self._collect)
        self.emitter.subscribe("*", self._collect)
        self.emitter.clear()
        event = ChangeEvent(event_type="a", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 0)

    def test_clear_allows_resubscribe(self) -> None:
        self.emitter.subscribe("t", self._collect)
        self.emitter.clear()
        sid = self.emitter.subscribe("t", self._collect)
        self.assertTrue(sid)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 1)

    def test_clear_on_empty_emitter_does_not_error(self) -> None:
        self.emitter.clear()  # should not raise


class EventEmitterExceptionIsolationTests(unittest.TestCase):
    """Exception in one callback must not affect others."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []

    def _collect(self, event: ChangeEvent) -> None:
        self.received.append(event)

    def test_exception_in_one_callback_does_not_block_others(self) -> None:
        def failing(event: ChangeEvent) -> None:
            raise RuntimeError("callback failure")

        def passing(event: ChangeEvent) -> None:
            self.received.append(event)

        self.emitter.subscribe("t", failing)
        self.emitter.subscribe("t", passing)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")
        # Should not raise
        self.emitter.emit(event)
        self.assertEqual(len(self.received), 1)

    def test_exception_in_first_callback_allows_second(self) -> None:
        """Order: first callback raises, second still runs."""
        order: list[str] = []

        def first(event: ChangeEvent) -> None:
            order.append("first")
            raise ValueError("boom")

        def second(event: ChangeEvent) -> None:
            order.append("second")

        self.emitter.subscribe("t", first)
        self.emitter.subscribe("t", second)
        self.emitter.emit(ChangeEvent(event_type="t", source="s", timestamp="t"))
        self.assertEqual(order, ["first", "second"])

    def test_exception_in_wildcard_callback_isolated(self) -> None:
        wild_errors: list[str] = []

        def wild_failing(event: ChangeEvent) -> None:
            wild_errors.append("wild")
            raise RuntimeError("wild fail")

        self.emitter.subscribe("*", wild_failing)
        self.emitter.subscribe("t", self._collect)
        self.emitter.emit(ChangeEvent(event_type="t", source="s", timestamp="t"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(wild_errors, ["wild"])


class EventEmitterThreadSafetyTests(unittest.TestCase):
    """Concurrent operations must not corrupt internal state."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self._lock = threading.Lock()

    def _collect(self, event: ChangeEvent) -> None:
        with self._lock:
            self.received.append(event)

    def test_concurrent_subscribe_and_emit(self) -> None:
        """Many threads subscribe and emit simultaneously without error."""
        n_threads = 20
        errors: list[Exception] = []
        errors_lock = threading.Lock()

        def subscribe_and_emit(ident: int) -> None:
            try:
                sid = self.emitter.subscribe(
                    "t", lambda e: None
                )
                self.emitter.emit(
                    ChangeEvent(
                        event_type="t",
                        source=str(ident),
                        timestamp="t",
                    )
                )
                self.emitter.unsubscribe(sid)
            except Exception as exc:
                with errors_lock:
                    errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as pool:
            futures = [
                pool.submit(subscribe_and_emit, i) for i in range(n_threads)
            ]
            concurrent.futures.wait(futures)

        if errors:
            self.fail(f"Thread safety test raised {len(errors)} errors: {errors[0]}")

    def test_concurrent_emit_does_not_lose_events(self) -> None:
        """Many concurrent emits on the same type deliver all events."""
        n_events = 50
        counter = {"count": 0}
        counter_lock = threading.Lock()

        def count(event: ChangeEvent) -> None:
            with counter_lock:
                counter["count"] += 1

        self.emitter.subscribe("t", count)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")

        def emit_one() -> None:
            self.emitter.emit(event)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(emit_one) for _ in range(n_events)]
            concurrent.futures.wait(futures)

        self.assertEqual(counter["count"], n_events)

    def test_clear_during_emit_does_not_crash(self) -> None:
        """Calling clear() while emits are in flight."""
        barrier = threading.Barrier(2, timeout=5)

        def slow_callback(event: ChangeEvent) -> None:
            barrier.wait()  # sync so clear() runs during emit

        self.emitter.subscribe("t", slow_callback)
        event = ChangeEvent(event_type="t", source="s", timestamp="t")

        def emit_and_catch() -> None:
            try:
                self.emitter.emit(event)
            except Exception:
                pass

        def clear_emitter() -> None:
            barrier.wait()
            self.emitter.clear()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(emit_and_catch)
            f2 = pool.submit(clear_emitter)
            concurrent.futures.wait([f1, f2])


# ===========================================================================
#  _Subscription internal record
# ===========================================================================


class SubscriptionInternalTests(unittest.TestCase):
    """_Subscription is a simple data holder."""

    def test_fields_are_stored(self) -> None:
        sub = _Subscription(
            subscription_id="abc",
            event_type="my_type",
            callback=lambda e: None,
        )
        self.assertEqual(sub.subscription_id, "abc")
        self.assertEqual(sub.event_type, "my_type")
        self.assertTrue(callable(sub.callback))


# ===========================================================================
#  Adapter: ScreenChange -> EventEmitter
# ===========================================================================


# A monitored region size for popup calculations
_MONITORED_REGION = (0, 0, 800, 600)  # 480 000 pixels


def _make_screen_change(
    *,
    change_type: str = "none",
    timestamp: str | None = "2024-01-01T00:00:00",
    bbox: tuple[int, int, int, int] | None = None,
    pixel_count: int = 0,
    total_pixels: int = 0,
    change_ratio: float = 0.0,
    region: tuple[int, int, int, int] | None = _MONITORED_REGION,
) -> ScreenChange:
    return ScreenChange(
        timestamp=timestamp,
        bbox=bbox,
        pixel_count=pixel_count,
        total_pixels=total_pixels,
        change_ratio=change_ratio,
        change_type=change_type,
        screenshot_before=None,
        screenshot_after=None,
        region=region,
    )


class ScreenChangeAdapterEventTypeTests(unittest.TestCase):
    """Mapping of ScreenChange.change_type -> EventType."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.adapter = make_screen_change_adapter(self.emitter, source="test_monitor")
        self.emitter.subscribe("*", self.received.append)

    def test_none_change_emits_no_event(self) -> None:
        self.adapter(_make_screen_change(change_type="none"))
        self.assertEqual(len(self.received), 0)

    def test_full_change_emits_new_ui_state(self) -> None:
        self.adapter(_make_screen_change(change_type="full"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.NEW_UI_STATE)

    def test_significant_change_emits_screen_changed(self) -> None:
        self.adapter(_make_screen_change(change_type="significant"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.SCREEN_CHANGED)

    def test_minor_change_emits_screen_changed(self) -> None:
        self.adapter(_make_screen_change(change_type="minor"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.SCREEN_CHANGED)

    def test_source_is_passed_through(self) -> None:
        self.adapter(_make_screen_change(change_type="minor"))
        self.assertEqual(self.received[0].source, "test_monitor")

    def test_custom_source(self) -> None:
        adapter = make_screen_change_adapter(self.emitter, source="custom_src")
        adapter(_make_screen_change(change_type="minor"))
        self.assertEqual(self.received[0].source, "custom_src")


class ScreenChangeAdapterPopupDetectionTests(unittest.TestCase):
    """Popup detection logic for small centred bounding boxes."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.adapter = make_screen_change_adapter(self.emitter)
        self.emitter.subscribe("*", self.received.append)

    # -- scenarios that SHOULD trigger popup --

    def test_popup_detected_for_small_centred_bbox(self) -> None:
        """Bbox area < 20% and centred → POPUP_DETECTED emitted."""
        # area = 100x80 = 8000, total = 800*600 = 480000, ratio = 0.0167 < 0.20
        # centre_x = 350 (43.75%), centre_y = 260 (43.33%) — both in 20-80%
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(300, 220, 400, 300),
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_detected_accompanies_primary_event(self) -> None:
        """Popup event is separate from the primary change event."""
        self.adapter(
            _make_screen_change(
                change_type="significant",
                bbox=(300, 220, 400, 300),
            )
        )
        self.assertEqual(len(self.received), 2)
        self.assertEqual(self.received[0].event_type, EventType.SCREEN_CHANGED)
        self.assertEqual(self.received[1].event_type, EventType.POPUP_DETECTED)

    # -- scenarios that should NOT trigger popup --

    def test_popup_not_detected_when_bbox_none(self) -> None:
        """Bbox is None → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=None,
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_when_bbox_area_zero(self) -> None:
        """Bbox with zero area → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(100, 100, 100, 200),  # zero width
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_when_bbox_area_equals_twenty_percent(self) -> None:
        """Bbox area exactly 20% → not small enough (must be < 20%)."""
        # 20% of 480000 = 96000 → 346x277 ≈ 95842, 347x277 ≈ 96119
        # 347*278 = 96466. Let's use 347x277 = 96119 > 96000, that's > 20%
        # Actually we need >= 20%, so not popup.
        # 480000 * 0.20 = 96000. So bbox 310x310 = 96100 > 96000
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(0, 0, 310, 310),  # area = 96100
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_when_monitored_area_zero(self) -> None:
        """When region has zero size → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(10, 10, 50, 50),
                region=(0, 0, 0, 100),  # zero width
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_off_centre_left(self) -> None:
        """Centre_x < 20% → no popup."""
        # bbox covers left 5%-15% → centre_x = 10%
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(40, 200, 120, 300),  # centre_x = 80 = 10% of 800
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_off_centre_right(self) -> None:
        """Centre_x > 80% → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(680, 200, 760, 300),  # centre_x = 720 = 90%
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_off_centre_top(self) -> None:
        """Centre_y < 20% → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(300, 20, 400, 100),  # centre_y = 60 = 10%
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)

    def test_popup_not_detected_off_centre_bottom(self) -> None:
        """Centre_y > 80% → no popup."""
        self.adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(300, 520, 400, 580),  # centre_y = 550 = 91.7%
            )
        )
        event_types = {e.event_type for e in self.received}
        self.assertNotIn(EventType.POPUP_DETECTED, event_types)


class ScreenChangeAdapterDataPayloadTests(unittest.TestCase):
    """Data payload contents for screen change events."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.emitter.subscribe("*", self.received.append)
        self.adapter = make_screen_change_adapter(self.emitter)

    def test_data_contains_expected_keys(self) -> None:
        bbox = (100, 100, 300, 400)
        self.adapter(
            _make_screen_change(
                change_type="significant",
                bbox=bbox,
                pixel_count=5000,
                total_pixels=480000,
                change_ratio=0.0104,
            )
        )
        data = self.received[0].data
        self.assertEqual(data["bbox"], bbox)
        self.assertEqual(data["pixel_count"], 5000)
        self.assertEqual(data["total_pixels"], 480000)
        self.assertEqual(data["change_ratio"], 0.0104)
        self.assertEqual(data["change_type"], "significant")
        self.assertIsNone(data["screenshot_before"])
        self.assertIsNone(data["screenshot_after"])
        self.assertEqual(data["region"], _MONITORED_REGION)

    def test_timestamp_from_change_object(self) -> None:
        ts = "2024-12-25T10:00:00.000000+00:00"
        self.adapter(
            _make_screen_change(change_type="minor", timestamp=ts)
        )
        self.assertEqual(self.received[0].timestamp, ts)


class ScreenChangeAdapterValidationTests(unittest.TestCase):
    """Adapter factory validates its emitter argument."""

    def test_raises_type_error_for_non_emitter(self) -> None:
        with self.assertRaises(TypeError):
            make_screen_change_adapter(emitter="not_an_emitter")  # type: ignore[arg-type]

    def test_raises_type_error_for_none(self) -> None:
        with self.assertRaises(TypeError):
            make_screen_change_adapter(emitter=None)  # type: ignore[arg-type]

    def test_accepts_event_emitter(self) -> None:
        emitter = EventEmitter()
        adapter = make_screen_change_adapter(emitter)
        self.assertTrue(callable(adapter))


# ===========================================================================
#  _is_potential_popup standalone tests
# ===========================================================================


class IsPotentialPopupTests(unittest.TestCase):
    """Direct unit tests for the _is_potential_popup helper."""

    def test_none_bbox_returns_false(self) -> None:
        sc = _make_screen_change(bbox=None)
        self.assertFalse(_is_potential_popup(sc))

    def test_zero_area_bbox_returns_false(self) -> None:
        sc = _make_screen_change(bbox=(10, 10, 10, 100))  # zero width
        self.assertFalse(_is_potential_popup(sc))

    def test_large_bbox_returns_false(self) -> None:
        # area = 500*400 = 200000 / 480000 = 41.7% > 20%
        sc = _make_screen_change(bbox=(0, 0, 500, 400))
        self.assertFalse(_is_potential_popup(sc))

    def test_no_monitored_dimensions_returns_false(self) -> None:
        sc = _make_screen_change(bbox=(100, 100, 200, 200), region=None)
        self.assertFalse(_is_potential_popup(sc))

    def test_small_centred_returns_true(self) -> None:
        """All conditions satisfied."""
        sc = _make_screen_change(
            bbox=(300, 200, 400, 300),  # 100x100 = 10000 / 480000 = 2%
            region=(0, 0, 800, 600),
        )
        self.assertTrue(_is_potential_popup(sc))

    def test_off_centre_left_returns_false(self) -> None:
        sc = _make_screen_change(
            bbox=(0, 200, 100, 300),  # centre_x = 50 = 6.25%
            region=(0, 0, 800, 600),
        )
        self.assertFalse(_is_potential_popup(sc))


# ===========================================================================
#  Adapter: RegionTextChange -> EventEmitter
# ===========================================================================


def _make_region_text_change(
    *,
    diff_type: str = "changed",
    watch_id: str = "watch_abc",
    old_text: str = "",
    new_text: str = "hello",
    timestamp: str | None = "2024-01-01T00:00:00",
    region: tuple[int, int, int, int] = (0, 0, 100, 50),
) -> RegionTextChange:
    return RegionTextChange(
        watch_id=watch_id,
        region=region,
        old_text=old_text,
        new_text=new_text,
        timestamp=timestamp,
        diff_type=diff_type,
    )


class RegionChangeAdapterEventTypeTests(unittest.TestCase):
    """Mapping of RegionTextChange.diff_type -> EventType."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.emitter.subscribe("*", self.received.append)
        self.adapter = make_region_change_adapter(self.emitter)

    def test_appeared_emits_text_changed(self) -> None:
        self.adapter(_make_region_text_change(diff_type="appeared"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.TEXT_CHANGED)

    def test_changed_emits_text_changed(self) -> None:
        self.adapter(_make_region_text_change(diff_type="changed"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.TEXT_CHANGED)

    def test_disappeared_emits_text_changed(self) -> None:
        self.adapter(_make_region_text_change(diff_type="disappeared"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.TEXT_CHANGED)

    def test_unchanged_emits_region_updated(self) -> None:
        self.adapter(_make_region_text_change(diff_type="unchanged"))
        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].event_type, EventType.REGION_UPDATED)


class RegionChangeAdapterSourceTests(unittest.TestCase):
    """Source field formatting for region change events."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.emitter.subscribe("*", self.received.append)

    def test_source_uses_watch_id(self) -> None:
        adapter = make_region_change_adapter(self.emitter)
        adapter(_make_region_text_change(watch_id="watch_xyz"))
        self.assertEqual(self.received[0].source, "region_monitor:watch_xyz")

    def test_custom_source_prefix(self) -> None:
        adapter = make_region_change_adapter(
            self.emitter, source_prefix="my_monitor"
        )
        adapter(_make_region_text_change(watch_id="w1"))
        self.assertEqual(self.received[0].source, "my_monitor:w1")

    def test_emits_single_event(self) -> None:
        adapter = make_region_change_adapter(self.emitter)
        adapter(_make_region_text_change(diff_type="changed"))
        self.assertEqual(len(self.received), 1)


class RegionChangeAdapterDataPayloadTests(unittest.TestCase):
    """Data payload for region change events."""

    def setUp(self) -> None:
        self.emitter = EventEmitter()
        self.received: list[ChangeEvent] = []
        self.emitter.subscribe("*", self.received.append)
        self.adapter = make_region_change_adapter(self.emitter)

    def test_data_contains_expected_keys(self) -> None:
        region = (10, 20, 100, 50)
        self.adapter(
            _make_region_text_change(
                diff_type="changed",
                watch_id="w1",
                region=region,
                old_text="old",
                new_text="new",
            )
        )
        data = self.received[0].data
        self.assertEqual(data["watch_id"], "w1")
        self.assertEqual(data["region"], region)
        self.assertEqual(data["old_text"], "old")
        self.assertEqual(data["new_text"], "new")
        self.assertEqual(data["diff_type"], "changed")

    def test_timestamp_from_change_object(self) -> None:
        ts = "2024-06-15T12:00:00+00:00"
        self.adapter(
            _make_region_text_change(diff_type="appeared", timestamp=ts)
        )
        self.assertEqual(self.received[0].timestamp, ts)


class RegionChangeAdapterValidationTests(unittest.TestCase):
    """Adapter factory validates its emitter argument."""

    def test_raises_type_error_for_non_emitter(self) -> None:
        with self.assertRaises(TypeError):
            make_region_change_adapter(emitter="bad")  # type: ignore[arg-type]

    def test_raises_type_error_for_none(self) -> None:
        with self.assertRaises(TypeError):
            make_region_change_adapter(emitter=None)  # type: ignore[arg-type]

    def test_accepts_event_emitter(self) -> None:
        adapter = make_region_change_adapter(EventEmitter())
        self.assertTrue(callable(adapter))


# ===========================================================================
#  Smoke test: integration-style
# ===========================================================================


class IntegrationSmokeTests(unittest.TestCase):
    """End-to-end wiring of adapters and emitter."""

    def test_screen_adapter_feeds_emitter(self) -> None:
        emitter = EventEmitter()
        received: list[ChangeEvent] = []
        emitter.subscribe(EventType.SCREEN_CHANGED, received.append)
        emitter.subscribe(EventType.POPUP_DETECTED, received.append)

        adapter = make_screen_change_adapter(emitter)
        adapter(
            _make_screen_change(
                change_type="minor",
                bbox=(300, 200, 400, 300),  # small + centred
            )
        )

        self.assertEqual(len(received), 2)
        self.assertEqual(received[0].event_type, EventType.SCREEN_CHANGED)
        self.assertEqual(received[1].event_type, EventType.POPUP_DETECTED)

    def test_region_adapter_feeds_emitter(self) -> None:
        emitter = EventEmitter()
        received: list[ChangeEvent] = []
        emitter.subscribe(EventType.TEXT_CHANGED, received.append)

        adapter = make_region_change_adapter(emitter)
        adapter(
            _make_region_text_change(
                diff_type="changed",
                watch_id="w_42",
                old_text="before",
                new_text="after",
            )
        )

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, EventType.TEXT_CHANGED)
        self.assertEqual(received[0].source, "region_monitor:w_42")
        self.assertEqual(received[0].data["old_text"], "before")
        self.assertEqual(received[0].data["new_text"], "after")


if __name__ == "__main__":
    unittest.main()
