"""Tests for Communications/email_tools.py — Agent-callable email tools."""

from __future__ import annotations

import asyncio
import logging
import unittest
from unittest.mock import MagicMock, patch

from Communications.email_client import EmailMessage
from Communications.email_tools import (
    GetUnreadCountTool,
    ReadInboxTool,
    SearchEmailTool,
    SendEmailTool,
    register_email_tools,
)
from fiona.tools.models import ToolCategory, ToolContext, ToolResult


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
# Helpers
# ---------------------------------------------------------------------------


def _make_email(uid: str, subject: str = "Test", sender: str = "a@b.com",
                body: str = "Body", seen: bool = False) -> EmailMessage:
    """Create a minimal EmailMessage for test use."""
    return EmailMessage(
        uid=uid,
        subject=subject,
        sender=sender,
        recipients=["recipient@example.com"],
        date="2026-07-01",
        body=body,
        html_body=None,
        attachments=[],
        seen=seen,
        flags=[],
    )


# ---------------------------------------------------------------------------
# ReadInboxTool
# ---------------------------------------------------------------------------


class ReadInboxToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = ReadInboxTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "read_inbox")

    def test_spec_has_description(self) -> None:
        self.assertTrue(len(self.tool.spec.description) > 20)

    def test_spec_has_input_schema(self) -> None:
        schema = self.tool.spec.input_schema
        self.assertIn("properties", schema)
        self.assertIn("max_results", schema["properties"])
        self.assertIn("folder", schema["properties"])

    def test_spec_category(self) -> None:
        self.assertEqual(self.tool.spec.category, ToolCategory.AUTOMATION)

    def test_default_params(self) -> None:
        """Call with no args — verify defaults (limit=10, folder='INBOX')."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.fetch_inbox.return_value = []

            asyncio.run(self.tool.run(self.ctx))

            client.fetch_inbox.assert_called_once_with(
                limit=10, folder="INBOX"
            )

    def test_custom_params(self) -> None:
        """Call with custom max_results and folder."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.fetch_inbox.return_value = []

            asyncio.run(
                self.tool.run(self.ctx, max_results=5, folder="WORK")
            )

            client.fetch_inbox.assert_called_once_with(
                limit=5, folder="WORK"
            )

    def test_returns_emails(self) -> None:
        """Mock fetch_inbox returns EmailMessages — verify formatted output."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.fetch_inbox.return_value = [
                _make_email("1", "Hello", "alice@example.com",
                            "Test body content here."),
                _make_email("2", "Re: Hello", "bob@example.com",
                            "Reply content.", seen=True),
            ]

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("alice@example.com", result.content)
        self.assertIn("Hello", result.content)
        self.assertIn("Test body content", result.content)
        self.assertIn("bob@example.com", result.content)
        self.assertIn("Reply content", result.content)
        self.assertEqual(result.metadata["email_count"], 2)
        self.assertEqual(result.metadata["folder"], "INBOX")
        self.assertIn("Inbox (INBOX)", result.content)

    def test_empty_inbox(self) -> None:
        """When fetch_inbox returns [], content says 'No emails found'."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.fetch_inbox.return_value = []

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("No emails found", result.content)
        self.assertEqual(result.metadata["email_count"], 0)

    def test_login_failure(self) -> None:
        """When login returns False, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = False

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("log in", (result.error or "").lower())

    def test_fetch_error_handled(self) -> None:
        """When fetch_inbox raises, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.fetch_inbox.side_effect = RuntimeError("Connection lost")

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertFalse(result.success)
        self.assertIn("Connection lost", (result.error or ""))


# ---------------------------------------------------------------------------
# SendEmailTool
# ---------------------------------------------------------------------------


class SendEmailToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = SendEmailTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "send_email")

    def test_required_params(self) -> None:
        """Schema has to, subject, body as required."""
        schema = self.tool.spec.input_schema
        self.assertIn("required", schema)
        self.assertIn("to", schema["required"])
        self.assertIn("subject", schema["required"])
        self.assertIn("body", schema["required"])

    def test_optional_cc(self) -> None:
        """Schema includes cc in properties but not in required."""
        schema = self.tool.spec.input_schema
        self.assertIn("cc", schema["properties"])
        self.assertNotIn("cc", schema["required"])

    def test_send_success(self) -> None:
        """When send returns True, result is success with sent message."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.send.return_value = True

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="alice@example.com",
                    subject="Hello",
                    body="Test message",
                )
            )

        self.assertTrue(result.success)
        self.assertIn("sent successfully", result.content.lower())
        self.assertIn("alice@example.com", result.content)
        self.assertIn("Hello", result.content)
        client.send.assert_called_once_with(
            "alice@example.com", "Hello", "Test message"
        )

    def test_send_with_cc(self) -> None:
        """When cc is provided, two send() calls are made."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.send.return_value = True

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="alice@example.com",
                    subject="Hello",
                    body="Test message",
                    cc="bob@example.com",
                )
            )

        self.assertTrue(result.success)
        self.assertIn("alice@example.com", result.content)
        self.assertIn("bob@example.com", result.content)
        self.assertEqual(client.send.call_count, 2)

    def test_send_failure(self) -> None:
        """When send returns False, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.send.return_value = False

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="alice@example.com",
                    subject="Hello",
                    body="Test message",
                )
            )

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)

    def test_login_failure(self) -> None:
        """When login returns False, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = False

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="alice@example.com",
                    subject="Hello",
                    body="Test message",
                )
            )

        self.assertFalse(result.success)
        self.assertIn("log in", (result.error or "").lower())

    def test_missing_to(self) -> None:
        """When to is empty, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="",
                    subject="Hello",
                    body="Test message",
                )
            )

        self.assertFalse(result.success)
        self.assertIn("to", (result.error or "").lower())

    def test_send_error_handled(self) -> None:
        """When send raises, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.send.side_effect = RuntimeError("SMTP error")

            result = asyncio.run(
                self.tool.run(
                    self.ctx,
                    to="alice@example.com",
                    subject="Hello",
                    body="Test message",
                )
            )

        self.assertFalse(result.success)
        self.assertIn("SMTP error", (result.error or ""))


# ---------------------------------------------------------------------------
# SearchEmailTool
# ---------------------------------------------------------------------------


class SearchEmailToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = SearchEmailTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "search_email")

    def test_required_query(self) -> None:
        """Schema has query as required."""
        schema = self.tool.spec.input_schema
        self.assertIn("required", schema)
        self.assertIn("query", schema["required"])
        self.assertNotIn("max_results", schema["required"])

    def test_search_results(self) -> None:
        """Mock search returns UIDs — verify formatted results."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = ["42", "99"]
            client.fetch_email.side_effect = [
                _make_email("42", "Meeting", "boss@example.com",
                            "Reminder about tomorrow"),
                _make_email("99", "Invoice", "billing@example.com",
                            "Your invoice is attached"),
            ]

            result = asyncio.run(
                self.tool.run(self.ctx, query="FROM boss@example.com")
            )

        self.assertTrue(result.success)
        self.assertIn("Search results for", result.content)
        self.assertIn("boss@example.com", result.content)
        self.assertIn("Meeting", result.content)
        self.assertIn("billing@example.com", result.content)
        self.assertIn("Invoice", result.content)
        self.assertEqual(result.metadata["total_matches"], 2)
        self.assertEqual(result.metadata["returned_count"], 2)
        self.assertEqual(result.metadata["query"], "FROM boss@example.com")

    def test_no_results(self) -> None:
        """When search returns [], content says no matches."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = []

            result = asyncio.run(
                self.tool.run(self.ctx, query="NONEXISTENT")
            )

        self.assertTrue(result.success)
        self.assertIn("No emails matched", result.content)
        self.assertEqual(result.metadata["result_count"], 0)

    def test_no_fetchable_messages(self) -> None:
        """When search returns UIDs but fetch_email returns None for all."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = ["1", "2"]
            client.fetch_email.return_value = None

            result = asyncio.run(
                self.tool.run(self.ctx, query="SINCE 01-Jan-2026")
            )

        self.assertTrue(result.success)
        self.assertIn("No emails could be fetched", result.content)

    def test_missing_query(self) -> None:
        """When query is empty, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True

            result = asyncio.run(self.tool.run(self.ctx, query=""))

        self.assertFalse(result.success)
        self.assertIn("query", (result.error or "").lower())

    def test_login_failure(self) -> None:
        """When login returns False, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = False

            result = asyncio.run(
                self.tool.run(self.ctx, query="SUBJECT test")
            )

        self.assertFalse(result.success)
        self.assertIn("log in", (result.error or "").lower())

    def test_search_error_handled(self) -> None:
        """When search raises, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.side_effect = RuntimeError("IMAP error")

            result = asyncio.run(
                self.tool.run(self.ctx, query="SUBJECT test")
            )

        self.assertFalse(result.success)
        self.assertIn("IMAP error", (result.error or ""))


# ---------------------------------------------------------------------------
# GetUnreadCountTool
# ---------------------------------------------------------------------------


class GetUnreadCountToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = GetUnreadCountTool()
        self.ctx = _make_context()

    def test_spec_name(self) -> None:
        self.assertEqual(self.tool.spec.name, "get_unread_count")

    def test_no_required_params(self) -> None:
        """Schema has no required parameters — folder is optional."""
        schema = self.tool.spec.input_schema
        self.assertEqual(schema["required"], [])
        self.assertIn("folder", schema["properties"])

    def test_counts_unread(self) -> None:
        """When search returns UIDs, content is the count."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = ["1", "2", "3"]

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertEqual(result.content, "3")
        self.assertEqual(result.metadata["unread_count"], 3)
        self.assertEqual(result.metadata["folder"], "INBOX")
        client.search.assert_called_once_with("UNSEEN", folder="INBOX")

    def test_custom_folder(self) -> None:
        """Custom folder passed through to search."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = ["1"]

            result = asyncio.run(
                self.tool.run(self.ctx, folder="WORK")
            )

        self.assertTrue(result.success)
        self.assertEqual(result.content, "1")
        self.assertEqual(result.metadata["folder"], "WORK")
        client.search.assert_called_once_with("UNSEEN", folder="WORK")

    def test_all_read(self) -> None:
        """When search returns [], content is '0'."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.return_value = []

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertTrue(result.success)
        self.assertIn("0", result.content)
        self.assertEqual(result.metadata["unread_count"], 0)

    def test_login_failure(self) -> None:
        """When login returns False, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = False

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertFalse(result.success)
        self.assertIn("log in", (result.error or "").lower())

    def test_search_error_handled(self) -> None:
        """When search raises, result has success=False."""
        with (
            patch("Communications.email_tools.EmailClient") as mock_cls,
            patch("Communications.email_tools._load_config") as mock_cfg,
        ):
            mock_cfg.return_value = MagicMock()
            client = MagicMock()
            mock_cls.return_value = client
            client.login.return_value = True
            client.search.side_effect = RuntimeError("IMAP connection lost")

            result = asyncio.run(self.tool.run(self.ctx))

        self.assertFalse(result.success)
        self.assertIn("IMAP connection lost", (result.error or ""))


# ---------------------------------------------------------------------------
# register_email_tools
# ---------------------------------------------------------------------------


class RegisterEmailToolsTests(unittest.TestCase):
    def test_registers_four_tools(self) -> None:
        registry = _make_registry()
        register_email_tools(registry)
        self.assertEqual(len(registry.registered_tools), 4)

    def test_registration_source(self) -> None:
        registry = _make_registry()
        register_email_tools(registry)
        for tool, source in registry.registered_tools:
            self.assertEqual(source, "email")

    def test_registration_types(self) -> None:
        registry = _make_registry()
        register_email_tools(registry)
        names = [tool.spec.name for tool, _ in registry.registered_tools]
        self.assertIn("read_inbox", names)
        self.assertIn("send_email", names)
        self.assertIn("search_email", names)
        self.assertIn("get_unread_count", names)

    def test_registration_order(self) -> None:
        """Tools are registered in the expected order."""
        registry = _make_registry()
        register_email_tools(registry)
        names = [tool.spec.name for tool, _ in registry.registered_tools]
        self.assertEqual(names[0], "read_inbox")
        self.assertEqual(names[1], "send_email")
        self.assertEqual(names[2], "search_email")
        self.assertEqual(names[3], "get_unread_count")


if __name__ == "__main__":
    unittest.main()
