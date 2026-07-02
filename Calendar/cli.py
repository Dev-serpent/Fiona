"""CLI entry point for the Calendar subsystem.

Registered as ``fiona calendar`` in the umbrella CLI.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

from Calendar.event_store import EventStore, get_store
from Calendar.nlp_time import parse_datetime, parse_duration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pretty_json(data: Any) -> str:
    import json
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_start_time(args: argparse.Namespace) -> datetime | None:
    """Resolve start time from --at, --in, or --datetime."""
    if args.at:
        result = parse_datetime(args.at)
        if result["dt"]:
            return result["dt"]
        print(f"Could not parse --at: {result.get('error')}", file=sys.stderr)
        return None
    if args.dt:
        try:
            return datetime.fromisoformat(args.dt)
        except ValueError as e:
            print(f"Invalid --datetime: {e}", file=sys.stderr)
            return None
    # Default: now
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_add(store: EventStore, args: argparse.Namespace) -> None:
    """Add a new event."""
    start = _resolve_start_time(args)
    if not start:
        sys.exit(1)

    duration = None
    if args.duration:
        duration = parse_duration(args.duration)
    elif args.minutes:
        from datetime import timedelta
        duration = timedelta(minutes=args.minutes)

    end = None
    if args.end:
        try:
            end = datetime.fromisoformat(args.end)
        except ValueError as e:
            print(f"Invalid --end: {e}", file=sys.stderr)
            sys.exit(1)
    elif duration:
        end = start + duration

    if args.all_day:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = None

    try:
        event = store.create_event(
            title=args.title,
            start_time=start,
            end_time=end,
            description=args.description or "",
            all_day=args.all_day,
            location=args.location or "",
            recurrence=args.recurrence or "none",
            category=args.category or "default",
            color=args.color or "#4f8cff",
            reminders=args.reminders or [],
            tags=args.tags or [],
        )
        print(f"Created event: {event['title']} (id={event['id']})")
        print(f"  Start: {event['start_time']}")
        print(f"  End:   {event['end_time']}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list(store: EventStore, args: argparse.Namespace) -> None:
    """List events."""
    start = None
    end = None
    if args.today:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
    elif args.week:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + __import__("datetime").timedelta(days=7)
    elif args.upcoming:
        from datetime import timedelta
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=args.upcoming)

    events = store.list_events(start=start, end=end, category=args.category, limit=args.limit)

    if not events:
        print("No events found.")
        return

    print(f"Events ({len(events)}):")
    print("-" * 60)
    for ev in events:
        start_s = ev["start_time"][:16] if len(ev["start_time"]) > 16 else ev["start_time"]
        end_s = ev["end_time"][:16] if len(ev["end_time"]) > 16 else ev["end_time"]
        recur = f" [{ev['recurrence']}]" if ev["recurrence"] != "none" else ""
        print(f"  {start_s} → {end_s}  {ev['title']}{recur}  ({ev['id'][:8]}...)")


def cmd_get(store: EventStore, args: argparse.Namespace) -> None:
    """Show event details."""
    event = store.get_event(args.id)
    if not event:
        print(f"Event not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    print(_pretty_json(event))


def cmd_update(store: EventStore, args: argparse.Namespace) -> None:
    """Update an event."""
    kwargs: dict[str, Any] = {}
    if args.title:
        kwargs["title"] = args.title
    if args.description:
        kwargs["description"] = args.description
    if args.at:
        dt = parse_datetime(args.at)
        if dt["dt"]:
            kwargs["start_time"] = dt["dt"]
    if args.dt:
        try:
            kwargs["start_time"] = datetime.fromisoformat(args.dt)
        except ValueError as e:
            print(f"Invalid datetime: {e}", file=sys.stderr)
            sys.exit(1)
    if args.all_day is not None:
        kwargs["all_day"] = args.all_day
    if args.location:
        kwargs["location"] = args.location
    if args.category:
        kwargs["category"] = args.category
    if args.color:
        kwargs["color"] = args.color

    updated = store.update_event(args.id, **kwargs)
    if not updated:
        print(f"Event not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    print(f"Updated: {updated['title']}")


def cmd_delete(store: EventStore, args: argparse.Namespace) -> None:
    """Delete an event."""
    if store.delete_event(args.id):
        print(f"Deleted event: {args.id}")
    else:
        print(f"Event not found: {args.id}", file=sys.stderr)
        sys.exit(1)


def cmd_search(store: EventStore, args: argparse.Namespace) -> None:
    """Search events."""
    results = store.search_events(args.query, limit=args.limit)
    if not results:
        print("No matching events.")
        return
    print(f"Search results for {args.query!r} ({len(results)}):")
    for ev in results:
        print(f"  {ev['start_time'][:16]}  {ev['title']}")


def cmd_stats(store: EventStore, _args: argparse.Namespace) -> None:
    """Show calendar statistics."""
    stats = store.get_stats()
    print(_pretty_json(stats))


def cmd_remind(store: EventStore, args: argparse.Namespace) -> None:
    """Add a standalone reminder."""
    trigger = _resolve_start_time(args)
    if not trigger:
        sys.exit(1)
    reminder = store.create_standalone_reminder(
        title=args.title,
        trigger_at=trigger,
        recurrence=args.recurrence or "none",
    )
    print(f"Created reminder: {reminder['title']} at {reminder['trigger_at']}")


def cmd_reminders(store: EventStore, args: argparse.Namespace) -> None:
    """List reminders."""
    reminders = store.list_reminders(include_fired=args.all, limit=args.limit)
    if not reminders:
        print("No reminders.")
        return
    for r in reminders:
        fired = " [FIRED]" if r["fired"] else ""
        print(f"  {r['trigger_at'][:16]}  {r['title']}{fired}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser(subparsers: argparse._SubParsersAction | None = None) -> argparse.ArgumentParser:
    """Build the ``fiona calendar`` argument parser.

    If *subparsers* is given, registers as a subcommand; otherwise returns
    a standalone parser.
    """
    parser_kwargs: dict[str, Any] = dict(
        prog="fiona calendar",
        description="Calendar — events, reminders, and scheduling.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    if subparsers is not None:
        parser = subparsers.add_parser("calendar", **parser_kwargs)
    else:
        parser = argparse.ArgumentParser(**parser_kwargs)

    sub = parser.add_subparsers(dest="calendar_command", required=True)

    # ── add ──────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Create a new event.")
    p_add.add_argument("title", help="Event title")
    p_add.add_argument("--at", help="Natural language start time (e.g. 'tomorrow at 3pm')")
    p_add.add_argument("--datetime", "-dt", help="ISO 8601 start time (e.g. '2026-07-02T15:00:00')")
    p_add.add_argument("--duration", "-d", help="Duration (e.g. '1 hour 30 min')")
    p_add.add_argument("--minutes", "-m", type=int, help="Duration in minutes (simplified)")
    p_add.add_argument("--end", help="ISO 8601 end time")
    p_add.add_argument("--description", "-desc", help="Event description")
    p_add.add_argument("--all-day", action="store_true", help="All-day event")
    p_add.add_argument("--location", "-loc", help="Event location")
    p_add.add_argument("--recurrence", "-r", choices=("none", "daily", "weekly", "weekdays", "monthly", "yearly"), default="none")
    p_add.add_argument("--category", "-cat", default="default", help="Event category")
    p_add.add_argument("--color", default="#4f8cff", help="Event color hex")
    p_add.add_argument("--reminders", nargs="*", type=int, default=[], help="Minutes before to remind")
    p_add.add_argument("--tags", nargs="*", default=[], help="Event tags")

    # ── list ─────────────────────────────────────────────────────────
    p_list = sub.add_parser("list", help="List events.")
    p_list.add_argument("--today", action="store_true", help="Show today's events")
    p_list.add_argument("--week", action="store_true", help="Show this week's events")
    p_list.add_argument("--upcoming", "-u", type=int, nargs="?", const=7, help="Show upcoming N days (default 7)")
    p_list.add_argument("--category", "-cat", help="Filter by category")
    p_list.add_argument("--limit", "-l", type=int, default=50)

    # ── get ──────────────────────────────────────────────────────────
    p_get = sub.add_parser("get", help="Show event details by ID.")
    p_get.add_argument("id", help="Event ID")

    # ── update ───────────────────────────────────────────────────────
    p_upd = sub.add_parser("update", help="Update an event.")
    p_upd.add_argument("id", help="Event ID")
    p_upd.add_argument("--title", help="New title")
    p_upd.add_argument("--description", help="New description")
    p_upd.add_argument("--at", help="New start time (natural language)")
    p_upd.add_argument("--datetime", "-dt", help="New start time (ISO 8601)")
    p_upd.add_argument("--all-day", action="store_true", default=None)
    p_upd.add_argument("--location", help="New location")
    p_upd.add_argument("--category", help="New category")
    p_upd.add_argument("--color", help="New color")

    # ── delete ───────────────────────────────────────────────────────
    p_del = sub.add_parser("delete", help="Delete an event.")
    p_del.add_argument("id", help="Event ID")

    # ── search ───────────────────────────────────────────────────────
    p_src = sub.add_parser("search", help="Search events by title or description.")
    p_src.add_argument("query", help="Search term")
    p_src.add_argument("--limit", "-l", type=int, default=20)

    # ── stats ────────────────────────────────────────────────────────
    sub.add_parser("stats", help="Show calendar statistics.")

    # ── remind ────────────────────────────────────────────────────────
    p_rem = sub.add_parser("remind", help="Create a standalone reminder.")
    p_rem.add_argument("title", help="Reminder title")
    p_rem.add_argument("--at", help="Natural language trigger time")
    p_rem.add_argument("--datetime", "-dt", help="ISO 8601 trigger time")
    p_rem.add_argument("--recurrence", "-r", choices=("none", "daily", "weekly", "monthly", "yearly"), default="none")

    # ── reminders ────────────────────────────────────────────────────
    p_rems = sub.add_parser("reminders", help="List reminders.")
    p_rems.add_argument("--all", action="store_true", help="Include fired reminders")
    p_rems.add_argument("--limit", "-l", type=int, default=50)

    return parser


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``fiona calendar``."""
    parser = build_parser()
    args = parser.parse_args(argv)

    store = get_store()

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "get": cmd_get,
        "update": cmd_update,
        "delete": cmd_delete,
        "search": cmd_search,
        "stats": cmd_stats,
        "remind": cmd_remind,
        "reminders": cmd_reminders,
    }

    handler = commands.get(args.calendar_command)
    if handler:
        handler(store, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
