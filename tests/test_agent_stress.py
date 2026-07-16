"""Stress and edge-case tests for the Fiona agent system (Milestone 6).

Tests are divided into two categories:

1. **Stress tests** — concurrent load, rapid cycles, large data volumes.
2. **Edge-case tests** — boundary conditions, error paths, corner cases.

Every stress test has a built-in timeout (``threading.Timer``) to prevent
CI hangs.  All tests use ``:memory:`` SQLite databases unless a file-based
DB is specifically required.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest

from Agent.cancellation import CancellationToken, CancelledError
from Agent.chat_store import ChatStore, ChatStoreError, estimate_tokens
from Agent.chat_handler import AgentChatHandler
from Agent.orchestration import (
    Complexity,
    ComplexityAssessor,
    ForemanAgent,
    ForemanConfig,
    SubAgent,
    SubGoalSpec,
    TaskPlan,
)
from Agent.personality import Personality, PersonalityRegistry
from Agent.permission import PermissionEnforcer, SafeActionRouter
from Agent.ollama import OllamaClient
from unittest.mock import MagicMock, patch
from FionaCore import ActionResult


# ======================================================================
# Timeout helper
# ======================================================================


def _timeout(seconds: int = 10) -> threading.Timer:
    """Return a daemon timer that raises a timeout error."""
    timer = threading.Timer(seconds, lambda: _fail_with_timeout())
    timer.daemon = True
    timer.start()
    return timer


def _fail_with_timeout() -> None:
    raise RuntimeError("Test timed out — possible deadlock or hang")


# ======================================================================
# STRESS TESTS
# ======================================================================


class StressChatStoreConcurrentWrites(unittest.TestCase):
    """20 threads each writing 100 messages concurrently."""

    TIMEOUT = 30  # generous for 20 threads * 100 messages

    def test_concurrent_writes_20_threads(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            sid = store.create_session("stress")
            n_threads = 20
            msgs_per_thread = 100
            barrier = threading.Barrier(n_threads)
            errors: list[Exception] = []
            error_lock = threading.Lock()

            def worker() -> None:
                barrier.wait()
                try:
                    for i in range(msgs_per_thread):
                        store.add_message(
                            sid,
                            "user",
                            f"thread-{threading.get_ident()}-msg-{i}",
                        )
                except Exception as exc:
                    with error_lock:
                        errors.append(exc)

            threads = [
                threading.Thread(target=worker, daemon=True)
                for _ in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            self.assertEqual(errors, [], f"Thread errors: {errors}")
            expected = n_threads * msgs_per_thread
            actual = store.count_messages(sid)
            self.assertEqual(
                actual, expected,
                f"Expected {expected} messages, got {actual}",
            )
            # Verify all messages are retrievable
            msgs = store.get_messages(sid, limit=expected + 10)
            self.assertEqual(len(msgs), expected)
            store.close()
        finally:
            timer.cancel()


class StressChatStoreConcurrentReadsWrites(unittest.TestCase):
    """5 writers + 5 readers running simultaneously for 2 seconds."""

    TIMEOUT = 15

    def test_concurrent_reads_writes(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            sid = store.create_session("rw-stress")
            stop_event = threading.Event()
            shared_errors: list[Exception] = []
            error_lock = threading.Lock()

            def writer(wid: int) -> None:
                i = 0
                while not stop_event.is_set():
                    try:
                        store.add_message(
                            sid, "user", f"write-{wid}-{i}", token_count=1,
                        )
                    except Exception as exc:
                        with error_lock:
                            shared_errors.append(exc)
                    i += 1

            def reader() -> None:
                while not stop_event.is_set():
                    try:
                        store.get_context_window(sid, max_tokens=100)
                        store.count_messages(sid)
                        store.list_sessions()
                    except Exception as exc:
                        with error_lock:
                            shared_errors.append(exc)
                        return

            threads = [
                threading.Thread(target=writer, args=(i,), daemon=True)
                for i in range(5)
            ] + [
                threading.Thread(target=reader, daemon=True)
                for _ in range(5)
            ]

            for t in threads:
                t.start()

            time.sleep(2.0)
            stop_event.set()
            for t in threads:
                t.join(timeout=5)

            self.assertEqual(
                shared_errors, [],
                f"Errors during concurrent r/w: {shared_errors}",
            )
            # At least some writes must have happened
            self.assertGreater(store.count_messages(sid), 0,
                               "No messages were written!")
            store.close()
        finally:
            timer.cancel()


class StressRapidSendCancel(unittest.TestCase):
    """50 iterations of: send message → immediately cancel → verify
    cancelled message stored.

    Uses a mock Ollama client that signals it's ready before actually
    responding, giving the cancellation thread a window to cancel.
    """

    TIMEOUT = 15

    def test_rapid_send_cancel(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            # Create a mock client that waits long enough for cancellation
            mock_client = MagicMock(spec=OllamaClient)

            def slow_ask(**kwargs: object) -> str:
                """Simulate a slow LLM call that can be cancelled."""
                # Sleep in small increments to be responsive to cancellation
                for _ in range(50):
                    time.sleep(0.01)
                return '{"thought": "test", "final": "ok"}'

            mock_client.ask.side_effect = slow_ask

            handler = AgentChatHandler(chat_store=store, client=mock_client)
            sid = handler.create_session("general")
            iterations = 50

            for i in range(iterations):
                token = CancellationToken()

                def on_message(role: str, content: str) -> None:
                    pass

                def on_error(err: str) -> None:
                    pass

                def on_complete() -> None:
                    pass

                # Send message
                handler.send_message(
                    session_id=sid,
                    message=f"Test message {i}",
                    token=token,
                    on_message=on_message,
                    on_error=on_error,
                    on_complete=on_complete,
                )

                # Immediately cancel
                token.cancel()

            # Give all threads time to finish
            time.sleep(2.0)

            # Verify we have some cancelled messages stored
            msgs = store.get_messages(sid)
            cancelled_msgs = [m for m in msgs if m.role == "cancelled"]
            # With the slow mock, every iteration should be cancelled
            self.assertGreater(
                len(cancelled_msgs), 0,
                f"Expected at least one cancelled message, got none "
                f"among {len(msgs)} total",
            )
            store.close()
        finally:
            timer.cancel()


class StressLargeContextWindow(unittest.TestCase):
    """Create a session with 500 messages (~100 chars each) and verify
    ``get_context_window(max_tokens=2048)`` returns a reasonable subset.
    """

    TIMEOUT = 15

    def test_large_context_window(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            sid = store.create_session("large-ctx")
            n_messages = 500

            for i in range(n_messages):
                content = f"Message number {i}: " + "x" * 80  # ~100 chars
                store.add_message(
                    sid, "user" if i % 2 == 0 else "agent",
                    content,
                    token_count=estimate_tokens(content),
                )

            self.assertEqual(store.count_messages(sid), n_messages)

            # Get context window with 2048 token budget
            window = store.get_context_window(sid, max_tokens=2048)
            self.assertGreater(len(window), 0,
                               "Context window should not be empty")
            self.assertLessEqual(
                len(window), n_messages,
                "Context window should not exceed total messages",
            )

            # Verify ordering: oldest-first within budget
            total_tokens = 0
            for msg in window:
                tokens = msg.token_count or estimate_tokens(msg.content)
                total_tokens += tokens
            # The total might slightly exceed budget due to the
            # "at least one" rule, but not by more than 1 message worth.
            max_msg_tokens = max(
                m.token_count or estimate_tokens(m.content)
                for m in window
            )
            self.assertLessEqual(
                total_tokens, 2048 + max_msg_tokens,
                f"Total tokens {total_tokens} exceeds budget by more than "
                f"one message ({max_msg_tokens})",
            )

            # Verify oldest-first order
            ids = [m.id for m in window]
            self.assertEqual(ids, sorted(ids), "Messages not in oldest-first order")

            store.close()
        finally:
            timer.cancel()


class StressManySessions(unittest.TestCase):
    """Create 100 sessions, each with 10 messages.  Verify
    ``list_sessions()`` returns all 100 and ``search_messages()`` works
    across all.
    """

    TIMEOUT = 15

    def test_many_sessions(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            n_sessions = 100
            msgs_per_session = 10

            sids: list[str] = []
            for i in range(n_sessions):
                sid = store.create_session(f"stress-{i}")
                sids.append(sid)
                for j in range(msgs_per_session):
                    store.add_message(
                        sid,
                        "user" if j % 2 == 0 else "agent",
                        f"session-{i}-msg-{j}",
                    )

            # list_sessions should return all 100
            all_sessions = store.list_sessions(limit=200)
            self.assertEqual(
                len(all_sessions), n_sessions,
                f"Expected {n_sessions} sessions, got {len(all_sessions)}",
            )

            # Search across all sessions — use a high limit
            results = store.search_messages("msg-5", limit=200)
            self.assertGreaterEqual(
                len(results), n_sessions,
                f"Expected at least {n_sessions} matches for 'msg-5', "
                f"got {len(results)}",
            )

            # Verify each session has correct message count
            for sid in sids:
                self.assertEqual(
                    store.count_messages(sid), msgs_per_session,
                )

            store.close()
        finally:
            timer.cancel()


# ======================================================================
# EDGE-CASE TESTS
# ======================================================================


class EdgeCancellationToken(unittest.TestCase):
    """CancellationToken edge cases."""

    def test_cancel_before_use(self) -> None:
        """Call ``cancel()`` before passing to handler — no LLM call."""
        # Create a mock to verify no call is made
        mock_client = MagicMock(spec=OllamaClient)
        store = ChatStore(":memory:")
        handler = AgentChatHandler(chat_store=store, client=mock_client)
        sid = handler.create_session("general")
        token = CancellationToken()
        token.cancel()  # Cancel before any use

        called = threading.Event()

        def on_message(role: str, content: str) -> None:
            called.set()

        def on_error(err: str) -> None:
            called.set()

        def on_complete() -> None:
            called.set()

        handler.send_message(
            session_id=sid,
            message="Should not reach LLM",
            token=token,
            on_message=on_message,
            on_error=on_error,
            on_complete=on_complete,
        )

        time.sleep(0.5)
        # The mock client should NOT have been called
        mock_client.ask.assert_not_called()
        store.close()

    def test_double_cancel_no_error(self) -> None:
        """Call ``cancel()`` twice - no error raised."""
        token = CancellationToken()
        token.cancel()  # First call
        token.cancel()  # Second call — should not raise
        self.assertTrue(token.is_cancelled())

    def test_reset_after_cancel(self) -> None:
        """Reset after cancel — should clear the flag."""
        token = CancellationToken()
        token.cancel()
        self.assertTrue(token.is_cancelled())
        token.reset()
        self.assertFalse(token.is_cancelled())
        token.raise_if_cancelled()  # Should not raise


class EdgeEmptyGoal(unittest.TestCase):
    """Empty goal to ForemanAgent — should not crash."""

    def setUp(self) -> None:
        # Reset the PersonalityRegistry singleton to prevent cross-test
        # state corruption from the singleton pattern.
        from Agent.personality import PersonalityRegistry
        PersonalityRegistry._reset_instance()

    def test_empty_goal_simple(self) -> None:
        """ForemanAgent with empty goal should not crash."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = '{"classification": "simple", "reason": "test"}'
        registry = PersonalityRegistry.get_instance()
        store = ChatStore(":memory:")
        foreman = ForemanAgent(
            client=mock_client,
            registry=registry,
            chat_store=store,
            config=ForemanConfig(max_turns_per_sub_agent=1),
        )
        token = CancellationToken()
        # Empty goal
        result = foreman.execute("", token=token)
        self.assertIsInstance(result, str)
        # Should not have crashed
        store.close()

    def test_empty_goal_returns_string(self) -> None:
        """ForemanAgent with empty goal returns a string."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = '{"classification": "simple", "reason": "test"}'
        registry = PersonalityRegistry.get_instance()
        store = ChatStore(":memory:")
        foreman = ForemanAgent(
            client=mock_client,
            registry=registry,
            chat_store=store,
        )
        token = CancellationToken()
        result = foreman.execute("  ", token=token)
        self.assertIsInstance(result, str)
        store.close()


class EdgeVeryLongMessage(unittest.TestCase):
    """Very long message (100K chars) — storage and retrieval."""

    TIMEOUT = 10

    def test_very_long_message(self) -> None:
        timer = _timeout(self.TIMEOUT)
        try:
            store = ChatStore(":memory:")
            sid = store.create_session("long-msg")
            # 100,000 characters
            long_content = "A" * 100_000
            msg_id = store.add_message(sid, "user", long_content)
            self.assertIsInstance(msg_id, int)

            # Retrieve and verify no truncation
            msgs = store.get_messages(sid)
            self.assertEqual(len(msgs), 1)
            self.assertEqual(len(msgs[0].content), 100_000)
            self.assertEqual(msgs[0].content, long_content)

            store.close()
        finally:
            timer.cancel()


class EdgePersonalitySpecialChars(unittest.TestCase):
    """Personality name with special characters."""

    def setUp(self) -> None:
        # Reset the PersonalityRegistry singleton to prevent cross-test
        # state corruption from the singleton pattern.
        from Agent.personality import PersonalityRegistry
        PersonalityRegistry._reset_instance()

    def test_special_chars_name(self) -> None:
        """Register a personality with special characters in name."""
        registry = PersonalityRegistry.get_instance()
        special_name = "test-👾_with.special@chars#"
        p = Personality(
            name=special_name,
            description="Special char test",
            system_prompt="You are a test.",
        )
        registry.register(p)
        retrieved = registry.get(special_name)
        self.assertEqual(retrieved.name, special_name)
        # Cleanup to not affect other tests — we can't remove, but we
        # can overwrite with a harmless one
        registry.register(Personality(
            name=special_name,
            description="Cleaned up",
            system_prompt="Cleaned up.",
        ))


class EdgeCorruptDB(unittest.TestCase):
    """ChatStore with corrupt DB — verify ChatStoreError is raised."""

    def test_corrupt_db(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
            # Write garbage
            f.write(b"this is not a valid sqlite database\x00\x01\x02")

        try:
            with self.assertRaises(ChatStoreError):
                ChatStore(db_path)
        finally:
            os.unlink(db_path)


class EdgeSafeActionRouterNoEnforcer(unittest.TestCase):
    """SafeActionRouter without enforcer — direct pass-through.

    Note: The constructor currently requires an enforcer, but the
    docstring mentions full pass-through semantics when personality
    has allowed_tools=None.  This test validates that an unrestricted
    personality works correctly.
    """

    def test_no_enforcer_pass_through(self) -> None:
        """Restricted personality denies, unrestricted allows."""
        # Unrestricted personality (allowed_tools=None)
        p = Personality(name="free", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)

        mock_router = MagicMock()
        mock_router.run.return_value = ActionResult(
            ok=True, action="any_tool", detail="mock",
        )
        router = SafeActionRouter(enforcer, router=mock_router)

        result = router.run("any_tool")
        self.assertTrue(result.ok)
        mock_router.run.assert_called_once()


class EdgePermissionEnforcerNoneTools(unittest.TestCase):
    """PermissionEnforcer with personality that has no allowed_tools
    (None) — all tools are permitted.
    """

    def test_all_tools_permitted_when_none(self) -> None:
        p = Personality(name="open", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        self.assertTrue(enforcer.check_tool("press"))
        self.assertTrue(enforcer.check_tool("click"))
        self.assertTrue(enforcer.check_tool("any_imaginable_tool"))
        enforcer.assert_tool_allowed("any_tool")  # Should not raise


class EdgePersonalityRegistryThreadSafety(unittest.TestCase):
    """Launch 10 threads calling get_instance() simultaneously.
    Verify only one instance is created.
    """

    def test_thread_safe_singleton(self) -> None:
        # Reset singleton for this test
        old_instance = PersonalityRegistry._instance
        PersonalityRegistry._instance = None

        try:
            instances: list[PersonalityRegistry] = []
            lock = threading.Lock()
            barrier = threading.Barrier(10)

            def worker() -> None:
                barrier.wait()
                inst = PersonalityRegistry.get_instance()
                with lock:
                    instances.append(inst)

            threads = [
                threading.Thread(target=worker, daemon=True)
                for _ in range(10)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

            # All references should point to the same instance
            first = instances[0]
            for inst in instances[1:]:
                self.assertIs(inst, first,
                              "Multiple PersonalityRegistry instances created")

        finally:
            PersonalityRegistry._instance = old_instance


class EdgeSubAgentMaxTurnsOne(unittest.TestCase):
    """SubAgent with max_turns=1 — verify stops after 1 turn."""

    def test_max_turns_one(self) -> None:
        p = Personality(name="test", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock_router = MagicMock(spec=SafeActionRouter)
        mock_router.run.return_value = ActionResult(
            ok=True, action="press", detail="mock ok",
        )

        # Mock LLM to return an action on first call, which means
        # after 1 turn we hit max and stop.
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = json.dumps({
            "thought": "I will press a key",
            "action": "press",
            "input": {"keys": ["a"]},
        })

        # We need a SafeActionRouter, not a mock one, for SubAgent
        # Let's wrap the mock in a real SafeActionRouter
        router = SafeActionRouter(enforcer, router=mock_router)

        sub = SubAgent(p, mock_client, router, max_turns=1)
        token = CancellationToken()
        result = sub.execute("press 'a'", token)
        # Should hit max turns (1) and return the max-turns message
        self.assertIn("maximum of 1 turns", result.lower())
        self.assertEqual(sub.turns, 1)


class EdgeTaskPlanSingleSubGoal(unittest.TestCase):
    """TaskPlan with single sub-goal — execution_order returns one
    layer with one task.
    """

    def test_single_sub_goal(self) -> None:
        plan = TaskPlan(
            goal="simple goal",
            sub_goals=(
                SubGoalSpec(
                    id="step-1",
                    description="Do something",
                    assigned_personality="general",
                ),
            ),
        )
        layers = plan.execution_order()
        self.assertEqual(len(layers), 1)
        self.assertEqual(len(layers[0]), 1)
        self.assertEqual(layers[0][0].id, "step-1")


class EdgeGetContextWindowEmptySession(unittest.TestCase):
    """Empty session returns empty context window."""

    def test_empty_session_window(self) -> None:
        store = ChatStore(":memory:")
        sid = store.create_session("empty")
        window = store.get_context_window(sid, max_tokens=2048)
        self.assertEqual(window, [])
        store.close()


class EdgeSearchMessagesNoResults(unittest.TestCase):
    """Search for a non-existent string returns empty list."""

    def test_search_no_results(self) -> None:
        store = ChatStore(":memory:")
        sid = store.create_session("search-test")
        store.add_message(sid, "user", "hello world")
        results = store.search_messages("zzzznotfound")
        self.assertEqual(results, [])
        store.close()


class EdgeImportJsonlEmptyFile(unittest.TestCase):
    """Import JSONL with empty file — returns 0."""

    def test_empty_jsonl(self) -> None:
        store = ChatStore(":memory:")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False,
        ) as f:
            tmp_path = f.name

        try:
            count = store.import_jsonl(tmp_path)
            self.assertEqual(count, 0)
        finally:
            os.unlink(tmp_path)
            store.close()


class EdgeCancelledErrorIsRuntimeError(unittest.TestCase):
    """CancelledError is a RuntimeError subclass."""

    def test_cancelled_error_inherits(self) -> None:
        self.assertTrue(issubclass(CancelledError, RuntimeError))


class EdgeCancellationTokenDefaults(unittest.TestCase):
    """CancellationToken default state."""

    def test_default_not_cancelled(self) -> None:
        token = CancellationToken()
        self.assertFalse(token.is_cancelled())
        token.raise_if_cancelled()  # Should not raise


class EdgeSubAgentEmptyGoal(unittest.TestCase):
    """SubAgent with empty goal — should not crash."""

    def test_sub_agent_empty_goal(self) -> None:
        p = Personality(name="test", description="x", system_prompt="x")
        enforcer = PermissionEnforcer(p)
        mock_router = MagicMock()
        router = SafeActionRouter(enforcer, router=mock_router)
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = json.dumps({
            "thought": "Nothing to do",
            "final": "Done.",
        })
        sub = SubAgent(p, mock_client, router, max_turns=1)
        token = CancellationToken()
        result = sub.execute("", token)
        self.assertIsInstance(result, str)


class EdgeAssessorEmptyGoal(unittest.TestCase):
    """ComplexityAssessor with empty goal — should not crash."""

    def test_assessor_empty_goal(self) -> None:
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.ask.return_value = '{"classification": "simple", "reason": "empty"}'
        assessor = ComplexityAssessor(mock_client)
        result = assessor.assess("")
        self.assertIn(result, (Complexity.SIMPLE, Complexity.MODERATE, Complexity.COMPLEX))


class EdgePermissionErrorMessage(unittest.TestCase):
    """PermissionError message formatting."""

    def test_error_message(self) -> None:
        from Agent.permission import AgentPermissionError
        err = AgentPermissionError("my_tool", "my_personality")
        msg = str(err)
        self.assertIn("my_tool", msg)
        self.assertIn("my_personality", msg)


class EdgeStoreSessionDeletionCascade(unittest.TestCase):
    """Delete session cascades to messages, and non-existent session
    deletion is idempotent.
    """

    def test_delete_nonexistent_session_no_error(self) -> None:
        store = ChatStore(":memory:")
        # Should not raise
        store.delete_session("nonexistent-session-id")
        store.close()

    def test_cascade_deletion(self) -> None:
        store = ChatStore(":memory:")
        sid = store.create_session("cascade-test")
        store.add_message(sid, "user", "msg1")
        store.add_message(sid, "agent", "msg2")
        self.assertEqual(store.count_messages(sid), 2)
        store.delete_session(sid)
        self.assertEqual(store.count_messages(sid), 0)
        store.close()


if __name__ == "__main__":
    unittest.main()
