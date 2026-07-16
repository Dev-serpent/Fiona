"""Tests for Agent.query_detector — QueryDetector (Milestone 6.5)."""

from __future__ import annotations

import unittest

from Agent.query_detector import QueryDetector, QueryOrTask


# ======================================================================
# QueryDetector unit tests
# ======================================================================

class TestQueryDetectorQueries(unittest.TestCase):
    """Inputs that SHOULD be classified as QUERY."""

    # -- Greetings -------------------------------------------------

    def test_hello(self) -> None:
        self.assertIs(QueryDetector.classify("hello"), QueryOrTask.QUERY)

    def test_hi(self) -> None:
        self.assertIs(QueryDetector.classify("hi"), QueryOrTask.QUERY)

    def test_hey_there(self) -> None:
        self.assertIs(QueryDetector.classify("hey there"), QueryOrTask.QUERY)

    def test_good_morning(self) -> None:
        self.assertIs(QueryDetector.classify("Good morning"), QueryOrTask.QUERY)

    def test_good_evening(self) -> None:
        self.assertIs(QueryDetector.classify("good evening!"), QueryOrTask.QUERY)

    def test_whats_up(self) -> None:
        self.assertIs(QueryDetector.classify("what's up"), QueryOrTask.QUERY)

    def test_howdy(self) -> None:
        self.assertIs(QueryDetector.classify("Howdy"), QueryOrTask.QUERY)

    def test_how_are_you(self) -> None:
        self.assertIs(QueryDetector.classify("how are you?"), QueryOrTask.QUERY)

    # -- Simple questions -------------------------------------------

    def test_what_is_fiona(self) -> None:
        self.assertIs(QueryDetector.classify("What is Fiona?"), QueryOrTask.QUERY)

    def test_who_are_you(self) -> None:
        self.assertIs(QueryDetector.classify("Who are you?"), QueryOrTask.QUERY)

    def test_how_does_it_work(self) -> None:
        self.assertIs(QueryDetector.classify("How does it work?"), QueryOrTask.QUERY)

    def test_what_can_you_do(self) -> None:
        self.assertIs(QueryDetector.classify("What can you do?"), QueryOrTask.QUERY)

    def test_is_it_working(self) -> None:
        self.assertIs(QueryDetector.classify("Is it working?"), QueryOrTask.QUERY)

    def test_can_you_help(self) -> None:
        self.assertIs(QueryDetector.classify("Can you help me?"), QueryOrTask.QUERY)

    def test_where_is_config(self) -> None:
        self.assertIs(QueryDetector.classify("Where is the config file?"), QueryOrTask.QUERY)

    # -- Short non-task messages ------------------------------------

    def test_short_no_action_verb(self) -> None:
        self.assertIs(QueryDetector.classify("That is great"), QueryOrTask.QUERY)

    def test_single_word(self) -> None:
        self.assertIs(QueryDetector.classify("Thanks"), QueryOrTask.QUERY)

    def test_chitchat(self) -> None:
        self.assertIs(QueryDetector.classify("I am fine"), QueryOrTask.QUERY)

    def test_affirmation(self) -> None:
        self.assertIs(QueryDetector.classify("ok"), QueryOrTask.QUERY)

    # -- Empty / whitespace -----------------------------------------

    def test_empty_string(self) -> None:
        self.assertIs(QueryDetector.classify(""), QueryOrTask.QUERY)

    def test_whitespace_only(self) -> None:
        self.assertIs(QueryDetector.classify("   "), QueryOrTask.QUERY)


class TestQueryDetectorTasks(unittest.TestCase):
    """Inputs that SHOULD be classified as TASK."""

    # -- System-control action verbs --------------------------------

    def test_open_gedit(self) -> None:
        self.assertIs(QueryDetector.classify("Open Gedit"), QueryOrTask.TASK)

    def test_open_browser(self) -> None:
        self.assertIs(QueryDetector.classify("Open the brave browser"), QueryOrTask.TASK)

    def test_launch_terminal(self) -> None:
        self.assertIs(QueryDetector.classify("Launch the terminal"), QueryOrTask.TASK)

    def test_start_service(self) -> None:
        self.assertIs(QueryDetector.classify("Start the web server"), QueryOrTask.TASK)

    def test_stop_process(self) -> None:
        self.assertIs(QueryDetector.classify("Stop the running process"), QueryOrTask.TASK)

    def test_close_window(self) -> None:
        self.assertIs(QueryDetector.classify("Close this window"), QueryOrTask.TASK)

    def test_show_desktop(self) -> None:
        self.assertIs(QueryDetector.classify("Show the desktop"), QueryOrTask.TASK)

    def test_type_text(self) -> None:
        self.assertIs(QueryDetector.classify("Type hello world"), QueryOrTask.TASK)

    def test_press_key(self) -> None:
        self.assertIs(QueryDetector.classify("Press Enter"), QueryOrTask.TASK)

    def test_click_button(self) -> None:
        self.assertIs(QueryDetector.classify("Click the submit button"), QueryOrTask.TASK)

    def test_switch_app(self) -> None:
        self.assertIs(QueryDetector.classify("Switch to Chrome"), QueryOrTask.TASK)

    def test_scroll_down(self) -> None:
        self.assertIs(QueryDetector.classify("Scroll down"), QueryOrTask.TASK)

    def test_select_text(self) -> None:
        self.assertIs(QueryDetector.classify("Select all the text"), QueryOrTask.TASK)

    def test_copy_paste(self) -> None:
        self.assertIs(QueryDetector.classify("Copy that and paste it"), QueryOrTask.TASK)

    def test_move_window(self) -> None:
        self.assertIs(QueryDetector.classify("Move the window to the left"), QueryOrTask.TASK)

    # -- Action verbs -----------------------------------------------

    def test_make_module(self) -> None:
        self.assertIs(
            QueryDetector.classify("Make a module that reads environment variables"),
            QueryOrTask.TASK,
        )

    def test_create_function(self) -> None:
        self.assertIs(
            QueryDetector.classify("Create a function to calculate fibonacci numbers"),
            QueryOrTask.TASK,
        )

    def test_build_api(self) -> None:
        self.assertIs(
            QueryDetector.classify("Build an API endpoint for user registration"),
            QueryOrTask.TASK,
        )

    def test_implement_feature(self) -> None:
        self.assertIs(
            QueryDetector.classify("Implement a caching layer for the database"),
            QueryOrTask.TASK,
        )

    def test_fix_bug(self) -> None:
        self.assertIs(
            QueryDetector.classify("Fix the memory leak in the data pipeline"),
            QueryOrTask.TASK,
        )

    def test_refactor_module(self) -> None:
        self.assertIs(
            QueryDetector.classify("Refactor the authentication module"),
            QueryOrTask.TASK,
        )

    def test_add_route(self) -> None:
        self.assertIs(
            QueryDetector.classify("Add a new route to the API for user profiles"),
            QueryOrTask.TASK,
        )

    def test_debug_crash(self) -> None:
        self.assertIs(
            QueryDetector.classify("Debug the crash when loading large files"),
            QueryOrTask.TASK,
        )

    def test_configure_service(self) -> None:
        self.assertIs(
            QueryDetector.classify("Configure nginx for the new deployment"),
            QueryOrTask.TASK,
        )

    def test_write_unit_tests(self) -> None:
        self.assertIs(
            QueryDetector.classify("Write unit tests for the payment processor"),
            QueryOrTask.TASK,
        )

    # -- Technical references without action verbs ------------------

    def test_technical_module_name(self) -> None:
        self.assertIs(
            QueryDetector.classify("Look at the authentication module"),
            QueryOrTask.TASK,
        )

    def test_technical_file_reference(self) -> None:
        self.assertIs(
            QueryDetector.classify("Check the main.py file for issues"),
            QueryOrTask.TASK,
        )

    def test_technical_api_reference(self) -> None:
        self.assertIs(
            QueryDetector.classify("Review the API endpoint design"),
            QueryOrTask.TASK,
        )

    def test_database_reference(self) -> None:
        self.assertIs(
            QueryDetector.classify("What's the database schema look like?"),
            QueryOrTask.TASK,
        )

    # -- Very long messages -----------------------------------------

    def test_very_long_message(self) -> None:
        """Messages over 300 chars with detailed context are tasks."""
        long_msg = (
            "I need help with the following tasks. First, we have a Python application "
            "that processes CSV files from multiple sources. The current implementation "
            "uses a single-threaded approach that is too slow. I would like to refactor "
            "this to use multiprocessing with a pool of workers. Additionally, we need to "
            "add error handling for malformed rows and a retry mechanism for network "
            "timeouts. Finally, the output should be written to both a summary file and "
            "a detailed log. Can you help me implement this?"
        )
        self.assertIs(QueryDetector.classify(long_msg), QueryOrTask.TASK)

    # -- Mixed: action verb + question framing ---------------------

    def test_question_with_action_verb(self) -> None:
        """Even when framed as a question, action verbs make it a task."""
        self.assertIs(
            QueryDetector.classify("Can you implement a new data pipeline?"),
            QueryOrTask.TASK,
        )


class TestQueryDetectorConservativeDefaults(unittest.TestCase):
    """When in doubt, the detector should err on the side of QUERY."""

    def test_medium_length_no_markers(self) -> None:
        """A medium-length message with no action verbs or refs is still a query."""
        msg = "I was wondering what the weather is like today"
        self.assertIs(QueryDetector.classify(msg), QueryOrTask.QUERY)

    def test_opinion_question(self) -> None:
        msg = "What do you think about functional programming?"
        self.assertIs(QueryDetector.classify(msg), QueryOrTask.QUERY)

    def test_follow_up_question(self) -> None:
        msg = "And what about the second option?"
        self.assertIs(QueryDetector.classify(msg), QueryOrTask.QUERY)

    def test_simple_request_for_info(self) -> None:
        msg = "Tell me about Fiona"
        self.assertIs(QueryDetector.classify(msg), QueryOrTask.QUERY)


class TestQueryDetectorForceForemanOverride(unittest.TestCase):
    """force_foreman=True in ForemanChatHandler bypasses detection."""

    def test_force_foreman_still_routes_hello_to_foreman(self) -> None:
        """force_foreman=True must override query detection — tested in
        ForemanChatHandler integration tests below."""
        # This is verified by integration tests in
        # ForemanChatHandlerQueryDetectionTests
        pass


# ======================================================================
# Integration: ForemanChatHandler + QueryDetector
# ======================================================================

class ForemanChatHandlerQueryDetectionTests(unittest.TestCase):
    """When foreman is enabled, QUERY messages should skip ForemanAgent
    and route through AgentChatHandler (simple LLM call) instead."""

    def setUp(self) -> None:
        import tempfile
        import threading
        import time
        from unittest.mock import MagicMock, patch

        # Reset the PersonalityRegistry singleton to prevent cross-test
        # state corruption from the singleton pattern.
        from Agent.personality import PersonalityRegistry
        PersonalityRegistry._reset_instance()

        from Agent import (
            CancellationToken,
            ChatStore,
            ForemanConfig,
            OllamaClient,
        )
        from PhiConnect.foreman_handler import ForemanChatHandler

        self.store = ChatStore(":memory:")
        self.simple_client = MagicMock(spec=OllamaClient)
        self.simple_client.ask.return_value = "Simple response"
        self.foreman_mock = MagicMock()
        self.foreman_mock.execute.return_value = "Foreman response"

        self.handler = ForemanChatHandler(
            chat_store=self.store,
            client=self.simple_client,
        )
        # Replace the internal foreman with a mock so we can verify calls
        self.handler._foreman = self.foreman_mock
        self.handler._simple_handler._client = self.simple_client
        self.session_id = self.handler.create_session(personality="general")
        self.handler.foreman_enabled = True

    def tearDown(self) -> None:
        self.store.close()

    def _run_send(self, message: str) -> tuple[list, list, bool]:
        import time
        from Agent import CancellationToken

        token = CancellationToken()
        messages: list[tuple[str, str]] = []
        errors: list[str] = []
        completed = [False]

        def on_msg(role: str, content: str) -> None:
            messages.append((role, content))

        def on_err(err: str) -> None:
            errors.append(err)

        def on_done() -> None:
            completed[0] = True

        self.handler.send_message(
            session_id=self.session_id,
            message=message,
            token=token,
            on_message=on_msg,
            on_error=on_err,
            on_complete=on_done,
        )

        deadline = time.time() + 5
        while not completed[0] and not errors and time.time() < deadline:
            time.sleep(0.01)

        return messages, errors, completed[0]

    # -- QUERY messages should skip Foreman -------------------------

    def test_greeting_skips_foreman(self) -> None:
        """'hello' is a query → foreman.execute not called."""
        self._run_send("hello")
        self.foreman_mock.execute.assert_not_called()

    def test_greeting_uses_simple_handler(self) -> None:
        """'hello' should be answered by the simple handler, not foreman."""
        self._run_send("hello")
        self.simple_client.ask.assert_called()

    def test_question_skips_foreman(self) -> None:
        """'What is Fiona?' is a query → foreman.execute not called."""
        self._run_send("What is Fiona?")
        self.foreman_mock.execute.assert_not_called()

    def test_greeting_no_system_message(self) -> None:
        """QUERY messages should NOT produce 'Planning...' system messages."""
        messages, _, completed = self._run_send("hello")
        self.assertTrue(completed)
        system_contents = [c for r, c in messages if r == "system"]
        self.assertEqual(system_contents, [])

    # -- TASK messages should still use Foreman ---------------------

    def test_action_verb_uses_foreman(self) -> None:
        """'Create a new module' is a task → foreman.execute IS called."""
        self._run_send("Create a new module that processes data")
        self.foreman_mock.execute.assert_called_once()

    def test_technical_ref_uses_foreman(self) -> None:
        """'Fix the API endpoint' is a task → foreman.execute IS called."""
        self._run_send("Fix the API endpoint for user login")
        self.foreman_mock.execute.assert_called_once()

    def test_long_message_uses_foreman(self) -> None:
        """Very long messages should use foreman."""
        long_msg = (
            "I need to build a complete data processing pipeline that "
            "reads from multiple sources, transforms the data, and writes "
            "it to a database. The pipeline needs to handle errors gracefully "
            "and support parallel processing for efficiency."
        )
        self._run_send(long_msg)
        self.foreman_mock.execute.assert_called_once()

    def test_task_shows_planning_message(self) -> None:
        """TASK messages should produce 'Planning...' system messages."""
        messages, _, completed = self._run_send("Create a module for logging")
        self.assertTrue(completed)
        system_contents = [c for r, c in messages if r == "system"]
        self.assertIn("Planning...", system_contents)

    # -- force_foreman=True bypasses detection ----------------------

    def test_force_foreman_overrides_query_detection(self) -> None:
        """Even 'hello' goes through foreman when force_foreman=True."""
        import time
        from Agent import CancellationToken

        token = CancellationToken()
        completed = [False]

        def on_msg(r: str, c: str) -> None:
            pass
        def on_err(e: str) -> None:
            pass
        def on_done() -> None:
            completed[0] = True

        self.handler.send_message(
            session_id=self.session_id,
            message="hello",
            token=token,
            force_foreman=True,
            on_message=on_msg,
            on_error=on_err,
            on_complete=on_done,
        )

        deadline = time.time() + 5
        while not completed[0] and time.time() < deadline:
            time.sleep(0.01)

        self.foreman_mock.execute.assert_called_once()

    # -- Conversational prompt for QUERY messages -------------------

    def test_greeting_uses_conversational_prompt(self) -> None:
        """QUERY messages should use the conversational system prompt,
        NOT the standard ReAct prompt."""
        self._run_send("hello")
        self.simple_client.ask.assert_called()
        # Verify the conversational prompt was used
        call_kwargs = self.simple_client.ask.call_args[1]
        system_used = call_kwargs.get("system_prompt", "")
        self.assertIn("Respond naturally and conversationally", system_used)
        self.assertNotIn("ONLY JSON", system_used)
        self.assertNotIn("MANDATORY TOOL USE", system_used)

    def test_task_still_uses_foreman(self) -> None:
        """TASK messages should still go through Foreman."""
        # Reset the foreman mock call count from previous tests
        self.foreman_mock.reset_mock()
        self._run_send("Create a new module for data processing")
        self.foreman_mock.execute.assert_called_once()
        call_kwargs = self.foreman_mock.execute.call_args[1]
        self.assertEqual(
            call_kwargs.get("goal"),
            "Create a new module for data processing",
        )
