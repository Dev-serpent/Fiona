"""Tests for Communications/email_client.py — EmailClient, EmailConfig, EmailMessage.

All tests use ``unittest.mock.patch`` to mock ``imaplib`` and ``smtplib`` so
no real network calls are ever made.
"""

from __future__ import annotations

import email
import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import unittest
from unittest.mock import MagicMock, patch

from Communications.email_client import EmailClient, EmailConfig, EmailMessage


# ---------------------------------------------------------------------------
# Helpers — build raw email bytes for parsing tests
# ---------------------------------------------------------------------------


def _make_text_email(
    subject: str = "Test Subject",
    sender: str = "alice@example.com",
    recipient: str = "bob@example.com",
    body: str = "Hello, world!",
    date: str = "Thu, 02 Jul 2026 12:00:00 +0000",
) -> bytes:
    """Return ``bytes`` of a simple plain-text email."""
    msg = email.mime.text.MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = date
    return msg.as_bytes()


def _make_multipart_alternative(
    body_text: str = "plain version",
    body_html: str = "<p>html version</p>",
) -> bytes:
    """Return ``bytes`` of a ``multipart/alternative`` email (text + HTML)."""
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = "HTML Test"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg.attach(email.mime.text.MIMEText(body_text, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(body_html, "html", "utf-8"))
    return msg.as_bytes()


def _make_multipart_with_attachment() -> bytes:
    """Return ``bytes`` of a ``multipart/mixed`` email with one attachment."""
    msg = email.mime.multipart.MIMEMultipart("mixed")
    msg["Subject"] = "Attachment Test"
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"

    msg.attach(email.mime.text.MIMEText("See attached file.", "plain", "utf-8"))

    att = email.mime.base.MIMEBase("application", "octet-stream")
    att.set_payload(b"fake binary data")
    email.encoders.encode_base64(att)
    att.add_header("Content-Disposition", "attachment", filename="report.pdf")
    msg.attach(att)

    return msg.as_bytes()


# ---------------------------------------------------------------------------
# Login / Logout / is_logged_in
# ---------------------------------------------------------------------------


class EmailClientLoginTests(unittest.TestCase):
    """Login/logout lifecycle tests."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="user@test.com", password="secret")
        self.client = EmailClient(self.config)

    # -- login ---------------------------------------------------------------

    def test_login_success(self) -> None:
        """Verify successful IMAP + SMTP authentication."""
        with (
            patch("Communications.email_client.imaplib") as mock_imaplib,
            patch("Communications.email_client.smtplib") as mock_smtplib,
        ):
            mock_imap = MagicMock()
            mock_imaplib.IMAP4_SSL.return_value = mock_imap
            mock_smtp = MagicMock()
            mock_smtplib.SMTP.return_value = mock_smtp

            result = self.client.login()

        self.assertTrue(result)
        mock_imaplib.IMAP4_SSL.assert_called_once_with("imap.gmail.com", 993)
        mock_imap.login.assert_called_once_with("user@test.com", "secret")

        mock_smtplib.SMTP.assert_called_once_with(
            "smtp.gmail.com", 587, timeout=30
        )
        mock_smtp.ehlo_or_helo_if_needed.assert_called()
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@test.com", "secret")

    def test_login_failure_imap(self) -> None:
        """IMAP login raises → login() returns False, cleanup occurs."""
        with (
            patch("Communications.email_client.imaplib") as mock_imaplib,
            patch("Communications.email_client.smtplib") as mock_smtplib,
        ):
            mock_imap = MagicMock()
            mock_imaplib.IMAP4_SSL.return_value = mock_imap
            mock_imap.login.side_effect = Exception("IMAP auth failed")
            mock_smtp = MagicMock()
            mock_smtplib.SMTP.return_value = mock_smtp

            result = self.client.login()

        self.assertFalse(result)
        mock_imap.login.assert_called_once()
        # SMTP path should never be reached
        mock_smtp.login.assert_not_called()
        # Cleanup — IMAP logout called
        mock_imap.logout.assert_called_once()

    def test_login_failure_smtp(self) -> None:
        """SMTP login raises → login() returns False, both connections torn down."""
        with (
            patch("Communications.email_client.imaplib") as mock_imaplib,
            patch("Communications.email_client.smtplib") as mock_smtplib,
        ):
            mock_imap = MagicMock()
            mock_imaplib.IMAP4_SSL.return_value = mock_imap
            mock_smtp = MagicMock()
            mock_smtplib.SMTP.return_value = mock_smtp
            mock_smtp.login.side_effect = Exception("SMTP auth failed")

            result = self.client.login()

        self.assertFalse(result)
        mock_imap.login.assert_called_once()
        mock_smtp.login.assert_called_once()
        # Both connections cleaned up
        mock_imap.logout.assert_called_once()
        mock_smtp.quit.assert_called_once()

    # -- is_logged_in --------------------------------------------------------

    def test_is_logged_in_true(self) -> None:
        """After successful login, is_logged_in() is True."""
        with (
            patch("Communications.email_client.imaplib") as mock_imaplib,
            patch("Communications.email_client.smtplib") as mock_smtplib,
        ):
            mock_imaplib.IMAP4_SSL.return_value = MagicMock()
            mock_smtplib.SMTP.return_value = MagicMock()
            self.client.login()

        self.assertTrue(self.client.is_logged_in())

    def test_is_logged_in_false(self) -> None:
        """Before login and after login+logout, is_logged_in() is False."""
        # Before login
        self.assertFalse(self.client.is_logged_in())

        # After login + logout
        self.client._imap = MagicMock()
        self.client._smtp = MagicMock()
        self.client.logout()
        self.assertFalse(self.client.is_logged_in())

    # -- logout --------------------------------------------------------------

    def test_logout_cleanup(self) -> None:
        """logout() calls IMAP logout() and SMTP quit(), then clears refs."""
        mock_imap = MagicMock()
        mock_smtp = MagicMock()
        self.client._imap = mock_imap
        self.client._smtp = mock_smtp

        self.client.logout()

        mock_imap.logout.assert_called_once()
        mock_smtp.quit.assert_called_once()
        self.assertIsNone(self.client._imap)
        self.assertIsNone(self.client._smtp)

    def test_logout_handles_errors(self) -> None:
        """If IMAP logout raises, SMTP quit is still called and no exception propagates."""
        mock_imap = MagicMock()
        mock_imap.logout.side_effect = Exception("IMAP logout error")
        mock_smtp = MagicMock()
        self.client._imap = mock_imap
        self.client._smtp = mock_smtp

        # Must not raise
        self.client.logout()

        mock_imap.logout.assert_called_once()
        mock_smtp.quit.assert_called_once()
        self.assertIsNone(self.client._imap)
        self.assertIsNone(self.client._smtp)


# ---------------------------------------------------------------------------
# Fetch operations
# ---------------------------------------------------------------------------


class EmailClientFetchTests(unittest.TestCase):
    """Tests for fetch_inbox() and fetch_email()."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="u@t.com", password="p")
        self.client = EmailClient(self.config)

    def _attach_imap(self) -> MagicMock:
        """Set ``_imap`` to a fresh MagicMock and return it."""
        mock_imap = MagicMock()
        self.client._imap = mock_imap
        return mock_imap

    # -- fetch_inbox ---------------------------------------------------------

    def test_fetch_inbox_empty(self) -> None:
        """IMAP search returns no data → fetch_inbox() returns [].

        Two code paths lead here: status != "OK", or data/data[0] is falsy.
        """
        mock_imap = self._attach_imap()
        mock_imap.select.return_value = ("OK", [b""])
        # search returns ("OK", [None]) → data[0] is None → falsy
        mock_imap.uid.return_value = ("OK", [None])

        result = self.client.fetch_inbox()

        self.assertEqual(result, [])

    def test_fetch_inbox_success(self) -> None:
        """Search returns UIDs, fetch returns raw email → list of EmailMessage."""
        mock_imap = self._attach_imap()
        mock_imap.select.return_value = ("OK", [b""])
        raw_email = _make_text_email()

        def uid_side_effect(command: str, *args: object) -> tuple:
            if command == "search":
                return ("OK", [b"1 2"])
            if command == "fetch":
                uid = args[0]
                if uid == b"1":
                    return ("OK", [(b"\\Seen", raw_email)])
                elif uid == b"2":
                    return ("OK", [(b"", raw_email)])
            return ("BAD", None)

        mock_imap.uid.side_effect = uid_side_effect

        result = self.client.fetch_inbox(limit=10)

        self.assertEqual(len(result), 2)

        # First message — flagged as \\Seen
        msg1 = result[0]
        self.assertEqual(msg1.uid, "1")
        self.assertEqual(msg1.subject, "Test Subject")
        self.assertEqual(msg1.sender, "alice@example.com")
        self.assertEqual(msg1.recipients, ["bob@example.com"])
        self.assertEqual(msg1.body, "Hello, world!")
        self.assertIsNone(msg1.html_body)
        self.assertEqual(msg1.attachments, [])
        self.assertTrue(msg1.seen)
        self.assertIn("\\Seen", msg1.flags)

        # Second message — not seen
        msg2 = result[1]
        self.assertEqual(msg2.uid, "2")
        self.assertFalse(msg2.seen)
        self.assertEqual(msg2.flags, [])

    # -- fetch_email ---------------------------------------------------------

    def test_fetch_email_found(self) -> None:
        """Single UID fetch returns a valid EmailMessage."""
        mock_imap = self._attach_imap()
        mock_imap.select.return_value = ("OK", [b""])
        raw_email = _make_text_email()

        def uid_side_effect(command: str, *args: object) -> tuple:
            if command == "fetch":
                return ("OK", [(b"\\Seen", raw_email)])
            return ("OK", [b""])

        mock_imap.uid.side_effect = uid_side_effect

        result = self.client.fetch_email("42")

        self.assertIsNotNone(result)
        assert result is not None  # narrow type for static analysis
        self.assertEqual(result.uid, "42")
        self.assertEqual(result.subject, "Test Subject")
        self.assertEqual(result.body, "Hello, world!")

    def test_fetch_email_not_found(self) -> None:
        """Fetch returns no data → fetch_email() returns None."""
        mock_imap = self._attach_imap()
        mock_imap.select.return_value = ("OK", [b""])

        def uid_side_effect(command: str, *args: object) -> tuple:
            if command == "fetch":
                return ("BAD", None)
            return ("OK", [b""])

        mock_imap.uid.side_effect = uid_side_effect

        result = self.client.fetch_email("99")

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


class EmailClientSendTests(unittest.TestCase):
    """Tests for send()."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="sender@test.com", password="p")
        self.client = EmailClient(self.config)

    def test_send_success(self) -> None:
        """SMTP accepts the message → send() returns True."""
        self.client._smtp = MagicMock()

        result = self.client.send("recip@test.com", "Hello", "Body text")

        self.assertTrue(result)
        self.client._smtp.sendmail.assert_called_once()
        args, _ = self.client._smtp.sendmail.call_args
        self.assertEqual(args[0], "sender@test.com")
        self.assertEqual(args[1], ["recip@test.com"])

    def test_send_failure(self) -> None:
        """SMTP raises → send() returns False."""
        mock_smtp = MagicMock()
        self.client._smtp = mock_smtp
        mock_smtp.sendmail.side_effect = Exception("Send failed")

        result = self.client.send("recip@test.com", "Hello", "Body")

        self.assertFalse(result)
        mock_smtp.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class EmailClientSearchTests(unittest.TestCase):
    """Tests for search()."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="u@t.com", password="p")
        self.client = EmailClient(self.config)

    def test_search_results(self) -> None:
        """IMAP search returns UIDs → search() returns list[str]."""
        self.client._imap = MagicMock()
        mock_imap = self.client._imap
        mock_imap.select.return_value = ("OK", [b""])
        mock_imap.uid.return_value = ("OK", [b"10 20 30"])

        result = self.client.search("FROM test@example.com")

        self.assertEqual(result, ["10", "20", "30"])
        mock_imap.uid.assert_called_once_with(
            "search", None, "FROM test@example.com"
        )

    def test_search_empty(self) -> None:
        """IMAP search returns empty data → search() returns []."""
        self.client._imap = MagicMock()
        mock_imap = self.client._imap
        mock_imap.select.return_value = ("OK", [b""])
        mock_imap.uid.return_value = ("OK", [b""])

        result = self.client.search("SINCE 01-Jan-2025")

        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Mark Seen
# ---------------------------------------------------------------------------


class EmailClientMarkSeenTests(unittest.TestCase):
    """Tests for mark_seen()."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="u@t.com", password="p")
        self.client = EmailClient(self.config)

    def test_mark_seen_success(self) -> None:
        """IMAP store returns OK → mark_seen() returns True."""
        self.client._imap = MagicMock()
        mock_imap = self.client._imap
        mock_imap.select.return_value = ("OK", [b""])
        mock_imap.uid.return_value = ("OK", [b"Success"])

        result = self.client.mark_seen("42")

        self.assertTrue(result)
        mock_imap.uid.assert_called_once_with(
            "store", b"42", "+FLAGS", "(\\Seen)"
        )

    def test_mark_seen_failure(self) -> None:
        """IMAP store returns non-OK → mark_seen() returns False."""
        self.client._imap = MagicMock()
        mock_imap = self.client._imap
        mock_imap.select.return_value = ("OK", [b""])
        mock_imap.uid.return_value = ("NO", [b"Failure"])

        result = self.client.mark_seen("99")

        self.assertFalse(result)

    def test_mark_seen_exception_returns_false(self) -> None:
        """IMAP store raises → mark_seen() returns False."""
        self.client._imap = MagicMock()
        mock_imap = self.client._imap
        mock_imap.select.return_value = ("OK", [b""])
        mock_imap.uid.side_effect = Exception("Store error")

        result = self.client.mark_seen("55")

        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Email message parsing
# ---------------------------------------------------------------------------


class EmailMessageParsingTests(unittest.TestCase):
    """Tests for _parse_message() — verifies EmailMessage data extraction."""

    def setUp(self) -> None:
        self.config = EmailConfig(username="u@t.com", password="p")
        self.client = EmailClient(self.config)

    def test_email_message_parsing(self) -> None:
        """All EmailMessage fields are correctly populated from raw email."""
        raw = _make_text_email(
            subject="Hello World",
            sender="alice@example.com",
            recipient="bob@example.com, carol@example.com",
            body="This is the body.",
            date="Wed, 01 Jan 2025 10:00:00 +0000",
        )
        msg = email.message_from_bytes(raw)
        parsed = self.client._parse_message(
            uid="123", msg=msg, folder="INBOX", flags_raw=b"\\Seen"
        )

        self.assertEqual(parsed.uid, "123")
        self.assertEqual(parsed.subject, "Hello World")
        self.assertEqual(parsed.sender, "alice@example.com")
        self.assertEqual(parsed.recipients, ["bob@example.com", "carol@example.com"])
        self.assertEqual(parsed.date, "Wed, 01 Jan 2025 10:00:00 +0000")
        self.assertEqual(parsed.body, "This is the body.")
        self.assertIsNone(parsed.html_body)
        self.assertEqual(parsed.attachments, [])
        self.assertTrue(parsed.seen)
        self.assertEqual(parsed.flags, ["\\Seen"])

    def test_email_message_with_attachments(self) -> None:
        """Multipart email with attachment → attachment metadata captured."""
        raw = _make_multipart_with_attachment()
        msg = email.message_from_bytes(raw)
        parsed = self.client._parse_message(
            uid="42", msg=msg, folder="INBOX", flags_raw=b""
        )

        self.assertEqual(parsed.subject, "Attachment Test")
        self.assertIn("See attached file.", parsed.body)
        self.assertEqual(len(parsed.attachments), 1)
        self.assertEqual(parsed.attachments[0]["filename"], "report.pdf")
        self.assertEqual(
            parsed.attachments[0]["content_type"], "application/octet-stream"
        )

    def test_email_message_html_body(self) -> None:
        """Multipart/alternative → both plain text body and html_body extracted."""
        raw = _make_multipart_alternative(
            body_text="Plain text version",
            body_html="<html><body><p>HTML version</p></body></html>",
        )
        msg = email.message_from_bytes(raw)
        parsed = self.client._parse_message(
            uid="7", msg=msg, folder="INBOX", flags_raw=b""
        )

        self.assertEqual(parsed.body, "Plain text version")
        self.assertEqual(
            parsed.html_body, "<html><body><p>HTML version</p></body></html>"
        )
        self.assertEqual(parsed.attachments, [])


if __name__ == "__main__":
    unittest.main()
