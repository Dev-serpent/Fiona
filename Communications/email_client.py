"""Email client module for Fiona — IMAP reading and SMTP sending via stdlib.

Provides EmailConfig, EmailMessage, and EmailClient for Tier 3 email
integration with zero external dependencies.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import smtplib
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import Message
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class EmailConfig:
    """Connection and behaviour configuration for EmailClient."""

    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    important_senders: list[str] = field(default_factory=list)
    check_interval: int = 60


@dataclass
class EmailMessage:
    """Decoded representation of a single email message."""

    uid: str
    subject: str
    sender: str
    recipients: list[str]
    date: str
    body: str
    html_body: str | None
    attachments: list[dict[str, str]]
    seen: bool
    flags: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decode_header_value(value: bytes | str | None) -> str:
    """Decode an email header value to a plain string.

    Handles encoded-word sequences (e.g. ``=?utf-8?B?…?=``) and falls
    back to latin-1 when the declared charset is unknown.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        decoded_parts = decode_header(value)
        return str(make_header(decoded_parts))
    except (LookupError, UnicodeError):
        # Fallback: strip encoded-word markers manually
        return _fallback_decode(value)


def _fallback_decode(value: str) -> str:
    """Strip encoded-word markers when ``decode_header`` fails."""
    result: list[str] = []
    for part in re.split(r"\?\s*=\s*=\?", value):
        # Remove leading =?charset?encoding? and trailing ?=
        part = re.sub(r"^=\?[^?]+\?[^?]+\?", "", part)
        part = re.sub(r"\?=$", "", part)
        result.append(part)
    cleaned = " ".join(result)
    try:
        return cleaned.encode("latin-1").decode("utf-8", errors="replace")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return cleaned


def _decode_text_payload(part: Message, default_charset: str = "utf-8") -> str:
    """Return the decoded text payload of a message part.

    Tries the part's charset first, then falls back to *default_charset*,
    and finally to a replacement-character-safe decode.
    """
    charset = part.get_content_charset() or default_charset
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        pass
    try:
        return payload.decode(default_charset, errors="replace")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_body(msg: Message) -> tuple[str, str | None, list[dict[str, str]]]:
    """Walk a *msg* tree and extract plain text, html, and attachments.

    Returns ``(plain_text, html_text, attachments)``.
    """
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, str]] = []

    for part in msg.walk():
        content_disposition = str(part.get("Content-Disposition", ""))
        content_type = part.get_content_type()
        is_attachment = "attachment" in content_disposition.lower()

        if part.get_content_maintype() == "multipart":
            continue

        if is_attachment:
            filename = part.get_filename()
            if filename:
                filename = _decode_header_value(filename)
            attachments.append(
                {
                    "filename": filename or "unnamed",
                    "content_type": content_type,
                }
            )
            continue

        if content_type == "text/plain":
            plain_parts.append(_decode_text_payload(part))
        elif content_type == "text/html":
            html_parts.append(_decode_text_payload(part))

    plain_text = "\n".join(plain_parts).strip()
    html_text = "\n".join(html_parts).strip() if html_parts else None
    return plain_text, html_text, attachments


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class EmailClient:
    """High-level email client backed by IMAP + SMTP (stdlib only)."""

    def __init__(self, config: EmailConfig) -> None:
        self._config = config
        self._imap: imaplib.IMAP4_SSL | None = None
        self._smtp: smtplib.SMTP | None = None

    # -- connection management -----------------------------------------------

    def login(self) -> bool:
        """Connect to IMAP and SMTP servers and authenticate.

        Returns ``True`` when both connections succeed.
        """
        try:
            self._login_imap()
            self._login_smtp()
            return True
        except Exception:
            logger.exception("EmailClient.login failed")
            self.logout()
            return False

    def _login_imap(self) -> None:
        """Open IMAP connection (SSL) and log in."""
        cfg = self._config
        self._imap = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        self._imap.login(cfg.username, cfg.password)
        logger.debug("IMAP logged in to %s:%d", cfg.imap_host, cfg.imap_port)

    def _login_smtp(self) -> None:
        """Open SMTP connection, upgrade to TLS, and log in."""
        cfg = self._config
        self._smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30)
        self._smtp.ehlo_or_helo_if_needed()
        if not self._smtp.has_extn("STARTTLS") and not cfg.use_ssl:
            logger.warning("SMTP server does not advertise STARTTLS")
        self._smtp.starttls()
        self._smtp.ehlo_or_helo_if_needed()
        self._smtp.login(cfg.username, cfg.password)
        logger.debug("SMTP logged in to %s:%d", cfg.smtp_host, cfg.smtp_port)

    def logout(self) -> None:
        """Close IMAP and SMTP connections gracefully."""
        imap_err: Optional[Exception] = None
        smtp_err: Optional[Exception] = None

        if self._imap is not None:
            try:
                self._imap.logout()
            except Exception as exc:
                imap_err = exc
                logger.debug("IMAP logout error: %s", exc)
            finally:
                self._imap = None

        if self._smtp is not None:
            try:
                self._smtp.quit()
            except Exception as exc:
                smtp_err = exc
                logger.debug("SMTP quit error: %s", exc)
            finally:
                self._smtp = None

        if imap_err or smtp_err:
            logger.warning("Non-fatal errors during logout (IMAP=%s, SMTP=%s)", imap_err, smtp_err)

    def is_logged_in(self) -> bool:
        """Check whether both IMAP and SMTP connections are alive."""
        return self._imap is not None and self._smtp is not None

    # -- IMAP helpers --------------------------------------------------------

    def _ensure_imap(self) -> imaplib.IMAP4_SSL:
        """Return the IMAP connection or raise ``ConnectionError``."""
        if self._imap is None:
            raise ConnectionError("Not connected to IMAP — call login() first")
        return self._imap

    def _ensure_smtp(self) -> smtplib.SMTP:
        """Return the SMTP connection or raise ``ConnectionError``."""
        if self._smtp is None:
            raise ConnectionError("Not connected to SMTP — call login() first")
        return self._smtp

    def _select_folder(self, folder: str = "INBOX") -> None:
        """Select a mailbox folder (readonly)."""
        imap = self._ensure_imap()
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            logger.warning("Failed to select folder '%s'", folder)

    # -- fetch operations ----------------------------------------------------

    def fetch_inbox(self, limit: int = 20, folder: str = "INBOX") -> list[EmailMessage]:
        """Fetch the most recent *limit* messages from *folder*.

        Returns a list of :class:`EmailMessage` objects (newest first).
        Returns an empty list on error.
        """
        try:
            imap = self._ensure_imap()
            self._select_folder(folder)

            status, data = imap.uid("search", None, "ALL")
            if status != "OK" or not data or not data[0]:
                return []

            uid_list = data[0].split()
            # UIDs are returned in ascending (oldest-first) order; reverse so
            # the most recent *limit* messages are returned.
            uid_slice = uid_list[-limit:]

            return self._fetch_uids(imap, uid_slice, folder)
        except Exception:
            logger.exception("fetch_inbox failed")
            return []

    def fetch_email(self, uid: str, folder: str = "INBOX") -> EmailMessage | None:
        """Fetch a single email by its UID.

        Returns ``None`` if the message cannot be found or an error occurs.
        """
        try:
            imap = self._ensure_imap()
            self._select_folder(folder)

            messages = self._fetch_uids(imap, [uid.encode()], folder)
            return messages[0] if messages else None
        except Exception:
            logger.exception("fetch_email failed for uid=%s", uid)
            return None

    def _fetch_uids(
        self, imap: imaplib.IMAP4_SSL, uid_list: list[bytes], folder: str
    ) -> list[EmailMessage]:
        """Fetch raw messages for the given UID byte-strings and parse them."""
        messages: list[EmailMessage] = []

        for uid_bytes in uid_list:
            uid_str = uid_bytes.decode()
            status, data = imap.uid("fetch", uid_bytes, "(FLAGS BODY.PEEK[])")
            if status != "OK" or not data or data[0] is None:
                logger.debug("UID fetch returned no data for %s", uid_str)
                continue

            # data[0] is (raw_bytes, flags_bytes) or just raw_bytes
            raw_email = data[0][1] if isinstance(data[0], tuple) else data[0]
            flags_raw = data[0][0] if isinstance(data[0], tuple) else b""

            try:
                msg = email.message_from_bytes(raw_email)
            except Exception:
                logger.exception("Failed to parse email UID %s", uid_str)
                continue

            parsed = self._parse_message(uid_str, msg, folder, flags_raw)
            messages.append(parsed)

        return messages

    def _parse_message(
        self, uid: str, msg: Message, folder: str, flags_raw: bytes
    ) -> EmailMessage:
        """Convert an ``email.message.Message`` into an ``EmailMessage``."""
        subject = _decode_header_value(msg["Subject"])
        sender = _decode_header_value(msg["From"])
        date = _decode_header_value(msg["Date"])

        # Recipients: To, Cc, Bcc
        recipients: list[str] = []
        for hdr in ("To", "Cc", "Bcc"):
            val = msg[hdr]
            if val:
                decoded = _decode_header_value(val)
                recipients.extend(
                    part.strip() for part in decoded.split(",") if part.strip()
                )

        body, html_body, attachments = _extract_body(msg)

        # Parse flags
        flags = flags_raw.decode().strip().split()
        seen = r"\Seen" in flags

        return EmailMessage(
            uid=uid,
            subject=subject,
            sender=sender,
            recipients=recipients,
            date=date,
            body=body,
            html_body=html_body,
            attachments=attachments,
            seen=seen,
            flags=flags,
        )

    # -- send ----------------------------------------------------------------

    def send(self, recipient: str, subject: str, body: str) -> bool:
        """Send an email via SMTP.

        Args:
            recipient: Destination email address.
            subject:   Email subject line.
            body:      Plain-text body content.

        Returns:
            ``True`` if the message was accepted by the server.
        """
        try:
            smtp = self._ensure_smtp()
            cfg = self._config

            text = f"From: {cfg.username}\r\nTo: {recipient}\r\nSubject: {subject}\r\n\r\n{body}"
            smtp.sendmail(cfg.username, [recipient], text.encode("utf-8"))
            logger.debug("Email sent to %s: %s", recipient, subject)
            return True
        except Exception:
            logger.exception("send failed to %s", recipient)
            return False

    # -- search --------------------------------------------------------------

    def search(self, criteria: str, folder: str = "INBOX") -> list[str]:
        """Search emails in *folder* using IMAP search *criteria*.

        The *criteria* string uses IMAP search syntax (e.g. ``"FROM user@example.com"``,
        ``"SINCE 01-Jan-2025"``). Returns a list of matching UID strings.
        Returns an empty list on error.
        """
        try:
            imap = self._ensure_imap()
            self._select_folder(folder)

            status, data = imap.uid("search", None, criteria)
            if status != "OK" or not data or not data[0]:
                return []

            return [uid.decode() for uid in data[0].split()]
        except Exception:
            logger.exception("search failed with criteria=%r", criteria)
            return []

    # -- flags ---------------------------------------------------------------

    def mark_seen(self, uid: str, folder: str = "INBOX") -> bool:
        """Mark an email as \\Seen (read).

        Returns ``True`` if the flag was applied successfully.
        """
        try:
            imap = self._ensure_imap()
            self._select_folder(folder)

            status, _ = imap.uid("store", uid.encode(), "+FLAGS", "(\\Seen)")
            return status == "OK"
        except Exception:
            logger.exception("mark_seen failed for uid=%s", uid)
            return False
