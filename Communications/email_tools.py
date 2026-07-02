"""Agent-callable email tools for Fiona's agent tool system.

Provides :class:`ReadInboxTool`, :class:`SendEmailTool`,
:class:`SearchEmailTool`, and :class:`GetUnreadCountTool` as
:class:`ITool` implementations compatible with Fiona's central tool
system.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fiona.tools.interfaces import ITool
from fiona.tools.models import ToolCategory, ToolContext, ToolResult, ToolSpec

from Communications.email_client import EmailClient, EmailConfig, EmailMessage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


def _load_config() -> EmailConfig:
    """Load the email configuration from the user's config file.

    Looks for ``~/.config/fiona/email.json`` and returns an
    :class:`EmailConfig` populated from its contents.  If the file does
    not exist or is malformed, returns a default (unconfigured) config.
    """
    path = Path.home() / ".config" / "fiona" / "email.json"
    if not path.exists():
        return EmailConfig()
    try:
        from dataclasses import fields

        data = json.loads(path.read_text(encoding="utf-8"))
        valid = {f.name for f in fields(EmailConfig)}
        filtered = {k: v for k, v in data.items() if k in valid}
        return EmailConfig(**filtered)
    except (json.JSONDecodeError, TypeError, ValueError):
        return EmailConfig()


# ---------------------------------------------------------------------------
# Tool: ReadInboxTool
# ---------------------------------------------------------------------------


class ReadInboxTool(ITool):
    """Read the most recent emails from the user's inbox.

    Returns a formatted summary of each message including sender,
    subject, date, and a preview of the body.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="read_inbox",
            description=(
                "Read the most recent emails from the user's inbox. "
                "Returns a formatted summary of each message including "
                "sender, subject, date, and a preview of the body."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": (
                            "Maximum number of emails to fetch "
                            "(default 10)."
                        ),
                        "default": 10,
                    },
                    "folder": {
                        "type": "string",
                        "description": (
                            "Mailbox folder to read from "
                            "(default 'INBOX')."
                        ),
                        "default": "INBOX",
                    },
                },
                "required": [],
            },
            category=ToolCategory.AUTOMATION,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        max_results = int(kwargs.get("max_results", 10))
        folder = str(kwargs.get("folder", "INBOX"))

        config = _load_config()
        client = EmailClient(config)

        if not client.login():
            return ToolResult(
                success=False,
                content="",
                error=(
                    "Failed to log in to email server. "
                    "Check your credentials in "
                    "~/.config/fiona/email.json"
                ),
            )

        try:
            emails = client.fetch_inbox(limit=max_results, folder=folder)

            if not emails:
                return ToolResult(
                    success=True,
                    content="No emails found.",
                    metadata={"email_count": 0, "folder": folder},
                )

            lines: list[str] = [
                f"Inbox ({folder}) - "
                f"{len(emails)} most recent email(s):",
                "",
            ]
            for i, email in enumerate(emails, 1):
                preview = (
                    email.body[:150].replace("\n", " ")
                    if email.body
                    else "(no text content)"
                )
                lines.append(f"{i}. From: {email.sender}")
                lines.append(f"   Subject: {email.subject}")
                lines.append(f"   Date: {email.date}")
                lines.append(f"   Preview: {preview}")
                lines.append("")

            context.logger.info(
                "read_inbox: fetched %d emails from %s",
                len(emails),
                folder,
            )

            return ToolResult(
                success=True,
                content="\n".join(lines).strip(),
                metadata={
                    "email_count": len(emails),
                    "folder": folder,
                },
            )

        except Exception as exc:
            context.logger.error(
                "read_inbox error: %s", exc, exc_info=True
            )
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to read inbox: {exc}",
            )
        finally:
            client.logout()


# ---------------------------------------------------------------------------
# Tool: SendEmailTool
# ---------------------------------------------------------------------------


class SendEmailTool(ITool):
    """Send an email message to one or more recipients.

    Uses the :class:`EmailClient.send` method for delivery.  When a
    *cc* address is provided, a separate copy is sent to that address.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="send_email",
            description=(
                "Send an email message to one or more recipients. "
                "Provide the recipient email address, subject, and "
                "body text."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": (
                            "Recipient email address."
                        ),
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Plain-text email body content."
                        ),
                    },
                    "cc": {
                        "type": "string",
                        "description": (
                            "Optional CC recipient email address. "
                            "A separate copy is sent to this address."
                        ),
                    },
                },
                "required": ["to", "subject", "body"],
            },
            category=ToolCategory.AUTOMATION,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        to_addr = str(kwargs.get("to", ""))
        subject = str(kwargs.get("subject", ""))
        body = str(kwargs.get("body", ""))
        cc_raw = kwargs.get("cc")
        cc_addr = str(cc_raw).strip() if cc_raw is not None else None

        if not to_addr:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: 'to'.",
            )
        if not subject:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: 'subject'.",
            )
        if not body:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: 'body'.",
            )

        config = _load_config()
        client = EmailClient(config)

        if not client.login():
            return ToolResult(
                success=False,
                content="",
                error="Failed to log in to email server.",
            )

        try:
            sent_to = client.send(to_addr, subject, body)
            recipients = [to_addr]

            if cc_addr:
                sent_cc = client.send(cc_addr, subject, body)
                recipients.append(cc_addr)
            else:
                sent_cc = True

            if not sent_to or (cc_addr and not sent_cc):
                return ToolResult(
                    success=False,
                    content="",
                    error=(
                        "Failed to send email to one or more "
                        "recipients."
                    ),
                )

            recipients_str = ", ".join(recipients)
            context.logger.info(
                "send_email: sent '%s' to %s",
                subject,
                recipients_str,
            )

            return ToolResult(
                success=True,
                content=(
                    f"Email sent successfully to {recipients_str} "
                    f"with subject '{subject}'."
                ),
                metadata={
                    "to": to_addr,
                    "cc": cc_addr,
                    "subject": subject,
                },
            )

        except Exception as exc:
            context.logger.error(
                "send_email error: %s", exc, exc_info=True
            )
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to send email: {exc}",
            )
        finally:
            client.logout()


# ---------------------------------------------------------------------------
# Tool: SearchEmailTool
# ---------------------------------------------------------------------------


class SearchEmailTool(ITool):
    """Search emails using IMAP search criteria.

    Accepts standard IMAP search syntax such as
    ``"FROM user@example.com"``, ``"SINCE 01-Jan-2025"``,
    ``"SUBJECT meeting"``, or ``"TEXT important"``.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="search_email",
            description=(
                "Search emails using IMAP search criteria.  Returns "
                "matching messages with sender, subject, and date.  "
                "Example criteria: 'FROM user@example.com', "
                "'SINCE 01-Jan-2025', 'SUBJECT meeting', "
                "'TEXT important'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "IMAP search criteria string.  Examples: "
                            "'FROM user@example.com', "
                            "'SINCE 01-Jan-2025', "
                            "'SUBJECT meeting', "
                            "'TEXT important'."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            "Maximum number of matching emails to "
                            "return (default 10)."
                        ),
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
            category=ToolCategory.AUTOMATION,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        query = str(kwargs.get("query", ""))
        max_results = int(kwargs.get("max_results", 10))

        if not query:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: 'query'.",
            )

        config = _load_config()
        client = EmailClient(config)

        if not client.login():
            return ToolResult(
                success=False,
                content="",
                error="Failed to log in to email server.",
            )

        try:
            uid_list = client.search(query)
            if not uid_list:
                return ToolResult(
                    success=True,
                    content="No emails matched the search criteria.",
                    metadata={
                        "query": query,
                        "result_count": 0,
                    },
                )

            # UIDs are returned in ascending (oldest-first) order; take
            # the most recent *max_results* UIDs.
            uid_slice = uid_list[-max_results:]

            messages: list[EmailMessage] = []
            for uid in uid_slice:
                msg = client.fetch_email(uid)
                if msg is not None:
                    messages.append(msg)

            if not messages:
                return ToolResult(
                    success=True,
                    content=(
                        "No emails could be fetched for the search "
                        "results."
                    ),
                    metadata={
                        "query": query,
                        "result_count": 0,
                    },
                )

            lines: list[str] = [
                f"Search results for: {query}",
                f"Found {len(uid_list)} match(es), showing "
                f"{len(messages)} most recent:",
                "",
            ]
            for i, msg in enumerate(messages, 1):
                lines.append(f"{i}. From: {msg.sender}")
                lines.append(f"   Subject: {msg.subject}")
                lines.append(f"   Date: {msg.date}")
                lines.append("")

            context.logger.info(
                "search_email: %d match(es) for %r, returned %d",
                len(uid_list),
                query,
                len(messages),
            )

            return ToolResult(
                success=True,
                content="\n".join(lines).strip(),
                metadata={
                    "query": query,
                    "total_matches": len(uid_list),
                    "returned_count": len(messages),
                },
            )

        except Exception as exc:
            context.logger.error(
                "search_email error: %s", exc, exc_info=True
            )
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to search emails: {exc}",
            )
        finally:
            client.logout()


# ---------------------------------------------------------------------------
# Tool: GetUnreadCountTool
# ---------------------------------------------------------------------------


class GetUnreadCountTool(ITool):
    """Return the number of unread (unseen) emails in a specified folder.

    Uses the IMAP ``SEARCH UNSEEN`` command for an accurate count
    without fetching full message bodies.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_unread_count",
            description=(
                "Return the number of unread (unseen) emails in the "
                "specified folder."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": (
                            "Mailbox folder to check "
                            "(default 'INBOX')."
                        ),
                        "default": "INBOX",
                    },
                },
                "required": [],
            },
            category=ToolCategory.AUTOMATION,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        folder = str(kwargs.get("folder", "INBOX"))

        config = _load_config()
        client = EmailClient(config)

        if not client.login():
            return ToolResult(
                success=False,
                content="",
                error="Failed to log in to email server.",
            )

        try:
            # IMAP SEARCH UNSEEN is more efficient than fetching and
            # filtering full messages.
            unseen_uids = client.search("UNSEEN", folder=folder)
            unread_count = len(unseen_uids)

            context.logger.info(
                "get_unread_count: %d unread in %s",
                unread_count,
                folder,
            )

            return ToolResult(
                success=True,
                content=str(unread_count),
                metadata={
                    "unread_count": unread_count,
                    "folder": folder,
                },
            )

        except Exception as exc:
            context.logger.error(
                "get_unread_count error: %s", exc, exc_info=True
            )
            return ToolResult(
                success=False,
                content="",
                error=f"Failed to get unread count: {exc}",
            )
        finally:
            client.logout()


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_email_tools(registry: Any) -> None:
    """Register all email tools with *registry*.

    The *registry* must expose a ``register(tool, source)`` method
    compatible with :class:`Agent.tool_runtime.ToolRegistry`.

    Args:
        registry: A tool registry instance (e.g. ``ToolRegistry()``).
    """
    registry.register(ReadInboxTool(), source="email")
    registry.register(SendEmailTool(), source="email")
    registry.register(SearchEmailTool(), source="email")
    registry.register(GetUnreadCountTool(), source="email")
    logger.info("Registered 4 email tools")
