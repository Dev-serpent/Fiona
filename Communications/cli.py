"""CLI entry point for the Communications (Email) subsystem.

Registered as ``fiona email`` in the umbrella CLI.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from Communications.email_client import EmailClient, EmailConfig, EmailMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pretty_json(data: Any) -> str:
    import json
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _format_email_list_item(email: EmailMessage) -> str:
    """Format a single EmailMessage for list display."""
    uid = email.uid
    from_ = email.sender
    subject = email.subject or "(no subject)"
    date = email.date
    return f"UID: {uid}  From: {from_}  Subject: {subject}  Date: {date}"


def _format_email_detail(email: EmailMessage) -> str:
    """Format a single EmailMessage with full headers and body for read display."""
    lines: list[str] = []
    lines.append(f"UID:      {email.uid}")
    lines.append(f"From:     {email.sender}")
    lines.append(f"To:       {', '.join(email.recipients)}")
    lines.append(f"Subject:  {email.subject or '(no subject)'}")
    lines.append(f"Date:     {email.date}")
    lines.append("")
    lines.append("\u2500" * 60)
    lines.append(email.body or "(no body)")
    lines.append("\u2500" * 60)
    if email.attachments:
        lines.append("")
        lines.append("Attachments:")
        for att in email.attachments:
            lines.append(f"  - {att.get('filename', 'unnamed')} ({att.get('content_type', '?')})")
    lines.append("")
    lines.append(f"(seen={email.seen})")
    return "\n".join(lines)


def _get_config_path() -> str:
    """Return the XDG-style config path for email settings."""
    from pathlib import Path
    return str(Path.home() / ".config" / "fiona" / "email.json")


def _load_config() -> EmailConfig:
    """Read ``~/.config/fiona/email.json`` and return an ``EmailConfig``.

    Returns ``EmailConfig()`` with defaults if the file is missing or
    cannot be parsed.
    """
    from pathlib import Path
    import json

    path = Path(_get_config_path())
    if not path.exists():
        return EmailConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Only pass keys that are valid EmailConfig fields
        valid_keys = {f.name for f in __import__("dataclasses").fields(EmailConfig)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return EmailConfig(**filtered)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"Warning: could not parse config at {path}: {exc}", file=sys.stderr)
        return EmailConfig()


def _save_config(config: EmailConfig) -> None:
    """Write *config* to ``~/.config/fiona/email.json``."""
    from dataclasses import asdict
    from pathlib import Path
    import json

    path = Path(_get_config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(config)
    path.write_text(
        json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_list(args: argparse.Namespace) -> None:
    """List recent emails."""
    config = _load_config()
    client = EmailClient(config)

    if not client.login():
        print("Failed to connect — check your email config.", file=sys.stderr)
        sys.exit(1)

    try:
        emails = client.fetch_inbox(limit=args.limit, folder=args.folder)
        if not emails:
            print("No emails found.")
            return
        for i, email in enumerate(emails):
            if i > 0:
                print("---")
            print(_format_email_list_item(email))
        print(f"\nTotal: {len(emails)} email(s)")
    finally:
        client.logout()


def _cmd_read(args: argparse.Namespace) -> None:
    """Read a specific email by UID."""
    config = _load_config()
    client = EmailClient(config)

    if not client.login():
        print("Failed to connect — check your email config.", file=sys.stderr)
        sys.exit(1)

    try:
        email = client.fetch_email(args.uid)
        if not email:
            print(f"Email not found: {args.uid}", file=sys.stderr)
            sys.exit(1)
        print(_format_email_detail(email))
    finally:
        client.logout()


def _cmd_send(args: argparse.Namespace) -> None:
    """Send an email."""
    config = _load_config()
    client = EmailClient(config)

    if not client.login():
        print("Failed to connect — check your email config.", file=sys.stderr)
        sys.exit(1)

    try:
        success = client.send(
            recipient=args.recipient,
            subject=args.subject,
            body=args.body,
        )
        if success:
            print(f"Email sent to {args.recipient}.")
        else:
            print(f"Failed to send email to {args.recipient}.", file=sys.stderr)
            sys.exit(1)
    finally:
        client.logout()


def _cmd_search(args: argparse.Namespace) -> None:
    """Search emails."""
    config = _load_config()
    client = EmailClient(config)

    if not client.login():
        print("Failed to connect — check your email config.", file=sys.stderr)
        sys.exit(1)

    try:
        uids = client.search(args.criteria)
        if not uids:
            print("No matching emails found.")
            return
        # Newest first, limited to args.limit
        uids = uids[-args.limit:]

        emails: list[EmailMessage] = []
        for uid in uids:
            email = client.fetch_email(uid)
            if email is not None:
                emails.append(email)

        for i, email in enumerate(emails):
            if i > 0:
                print("---")
            print(_format_email_list_item(email))
        print(f"\nTotal: {len(emails)} matching email(s)")
    finally:
        client.logout()


def _cmd_config(args: argparse.Namespace) -> None:
    """Show or set email configuration."""
    from dataclasses import fields

    config_path = _get_config_path()

    if args.set:
        key, value_str = args.set

        # Validate that the key is a valid EmailConfig field
        field_map = {f.name: f.type for f in fields(EmailConfig)}
        if key not in field_map:
            available = ", ".join(sorted(field_map))
            print(
                f"Unknown config key '{key}'. Available keys: {available}",
                file=sys.stderr,
            )
            sys.exit(1)

        config = _load_config()

        # Coerce the string value to the field's declared type
        target_type = field_map[key]
        try:
            if target_type is int:
                value = int(value_str)
            elif target_type is bool:
                value = value_str.lower() in ("true", "1", "yes", "on")
            elif target_type in (list, list[str]):
                import json
                value = json.loads(value_str)
                if not isinstance(value, list):
                    raise ValueError(f"expected a JSON array, got {type(value).__name__}")
            else:
                value = value_str
        except (ValueError, json.JSONDecodeError) as exc:
            print(
                f"Cannot convert '{value_str}' to {target_type.__name__}: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        setattr(config, key, value)
        _save_config(config)
        print(f"Set {key}={value!r} in {config_path}")
        return

    if args.show:
        config = _load_config()
        from dataclasses import asdict
        print(_pretty_json(asdict(config)))
        return

    # Default: show brief status
    from pathlib import Path
    path = Path(config_path)
    if path.exists():
        print(f"Email config: {config_path}")
    else:
        print(
            f"No email config found at {config_path}. "
            "Use 'fiona email config --set KEY VALUE' to configure."
        )


def _cmd_watch(args: argparse.Namespace) -> None:
    """Start polling for new mail."""
    import time

    config = _load_config()
    client = EmailClient(config)

    if not client.login():
        print("Failed to connect — check your email config.", file=sys.stderr)
        sys.exit(1)

    interval = args.interval
    print(f"Watching for new mail every {interval}s (Ctrl+C to stop)...")

    # Track seen UIDs to detect new messages
    seen: set[str] = set()

    try:
        while True:
            emails = client.fetch_inbox(limit=20, folder="INBOX")
            for email in emails:
                uid = email.uid
                if uid and uid not in seen:
                    seen.add(uid)
                    print(f"\nNew email: {_format_email_list_item(email)}")
            if args.oneshot:
                print("Oneshot check complete.")
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped watching for new mail.")
    finally:
        client.logout()


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_COMMANDS: dict[str, Any] = {
    "list": _cmd_list,
    "read": _cmd_read,
    "send": _cmd_send,
    "search": _cmd_search,
    "config": _cmd_config,
    "watch": _cmd_watch,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build the ``fiona email`` argument parser.

    If *subparsers* is given, registers as a subcommand; otherwise returns
    a standalone parser.
    """
    parser_kwargs: dict[str, Any] = dict(
        prog="fiona email",
        description="Email — list, read, send, search, configure, and watch for new mail.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    if subparsers is not None:
        parser = subparsers.add_parser("email", **parser_kwargs)
    else:
        parser = argparse.ArgumentParser(**parser_kwargs)

    sub = parser.add_subparsers(dest="email_command", required=True)

    # ── list ───────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", help="List recent emails.")
    p_list.add_argument("--limit", "-l", type=int, default=10, help="Max emails to show (default: 10)")
    p_list.add_argument("--folder", "-f", type=str, default="INBOX", help="Mail folder (default: INBOX)")

    # ── read ───────────────────────────────────────────────────────────
    p_read = sub.add_parser("read", help="Read a specific email by UID.")
    p_read.add_argument("uid", help="Email UID to read")

    # ── send ───────────────────────────────────────────────────────────
    p_send = sub.add_parser("send", help="Send an email.")
    p_send.add_argument("recipient", help="Recipient email address")
    p_send.add_argument("subject", help="Email subject")
    p_send.add_argument("body", help="Email body text")

    # ── search ─────────────────────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search emails by criteria.")
    p_search.add_argument("criteria", help="Search query (e.g. 'from:user@example.com')")
    p_search.add_argument("--limit", "-l", type=int, default=10, help="Max results to show (default: 10)")

    # ── config ─────────────────────────────────────────────────────────
    p_config = sub.add_parser("config", help="Show or set email configuration.")
    p_config.add_argument("--show", action="store_true", help="Show current email config")
    p_config.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a config key-value pair")

    # ── watch ──────────────────────────────────────────────────────────
    p_watch = sub.add_parser("watch", help="Poll for new mail (background-style loop).")
    p_watch.add_argument("--interval", "-i", type=int, default=60, help="Poll interval in seconds (default: 60)")
    p_watch.add_argument("--oneshot", action="store_true", help="Check once and exit")

    return parser


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _run_email_command(args: argparse.Namespace) -> None:
    """Dispatch to the appropriate email command handler based on args."""
    handler = _COMMANDS.get(args.email_command)
    if handler is not None:
        handler(args)
    else:
        build_parser().print_help()
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``fiona email`` (standalone)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _run_email_command(args)


if __name__ == "__main__":
    main()
