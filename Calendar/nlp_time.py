"""Natural language date/time parsing for the Calendar module.

Parses English phrases like "tomorrow at 3pm", "next monday", "in 2 hours",
"today at 5", "friday next week" into Python datetime objects.

Uses ``dateparser`` if available, with a pure-Python fallback.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try import dateparser (optional, heavy)
# ---------------------------------------------------------------------------

try:
    import dateparser  # type: ignore[import-untyped]

    _HAS_DATEPARSER = True
except ImportError:
    _HAS_DATEPARSER = False

# ---------------------------------------------------------------------------
# Pure-Python fallback parser
# ---------------------------------------------------------------------------

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAY_ABBR = {d[:3]: d for d in _DAY_NAMES}
_DAY_NAMES_LC = [d.lower() for d in _DAY_NAMES]

_RELATIVE_DAYS = {
    "today": 0,
    "tonight": 0,
    "tomorrow": 1,
    "tmr": 1,
    "tmrw": 1,
    "day after tomorrow": 2,
    "next day": 1,
    "yesterday": -1,
}

_TIME_PATTERNS = [
    # "at 3pm", "at 3:30pm", "at 15:30"
    re.compile(r"(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE),
    # "3 o'clock", "3 oclock"
    re.compile(r"(\d{1,2})\s*o'?clock\s*(am|pm)?", re.IGNORECASE),
]

_RELATIVE_DELTA = re.compile(
    r"in\s+"
    r"(?:an?\s+)?"
    r"(\d+)?\s*"
    r"(second|minute|hour|day|week|month|year|sec|min|h|d|w|mo|yr)s?"
    r"(?:\s+(?:and\s+)?(\d+)\s*(second|minute|hour|day|week|month|year|sec|min|h|d|w|mo|yr)s?)?",
    re.IGNORECASE,
)

_WEEKDAY_NEXT = re.compile(r"(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.IGNORECASE)
_WEEKDAY_THIS = re.compile(r"this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.IGNORECASE)
_WEEKDAY_LAST = re.compile(r"last\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.IGNORECASE)
_WEEKDAY_NEXT_WEEK = re.compile(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+next\s+week", re.IGNORECASE)

_MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
_MONTH_ABBR = {m[:3]: i + 1 for i, m in enumerate(_MONTH_NAMES)}
_MONTH_NAMES_LC = [m.lower() for m in _MONTH_NAMES]

_DATE_PATTERNS = [
    # "Dec 25", "December 25", "dec 25th"
    re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december|"
               r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
               r"\s+(\d{1,2})(?:st|nd|rd|th)?",
               re.IGNORECASE),
    # "25 Dec", "25th December", "25 dec"
    re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|"
               r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
               re.IGNORECASE),
    # "2024-12-25" (ISO)
    re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})"),
    # "12/25" or "12/25/2024"
    re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"),
]


def _time_of_day(text: str) -> tuple[int, int, bool]:
    """Try to extract a time from text. Returns (hour, minute, found)."""
    for pattern in _TIME_PATTERNS:
        m = pattern.search(text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            ampm = m.group(3).lower() if m.group(3) else None
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            return hour, minute, True
    return 0, 0, False


def _resolve_weekday(target_day: str, direction: str = "next") -> datetime:
    """Return the next/this/last occurrence of a weekday from today."""
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    target = _DAY_NAMES_LC.index(target_day.lower())
    current = now.weekday()  # Monday=0

    if direction == "this":
        days_ahead = target - current
    elif direction == "last":
        days_ahead = target - current - 7
    else:  # "next"
        days_ahead = target - current
        if days_ahead <= 0:
            days_ahead += 7

    return now + timedelta(days=days_ahead)


def _parse_date_part(text: str, now: datetime) -> datetime | None:
    """Extract date part (just the date) from text, or None."""
    lower = text.lower().strip()

    # Relative days
    for phrase, delta in sorted(_RELATIVE_DAYS.items(), key=lambda x: -len(x[0])):
        if lower.startswith(phrase) or lower == phrase:
            result = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=delta)
            # Handle "tonight" → 8pm
            if phrase == "tonight":
                result = result.replace(hour=20)
            return result

    # "Monday next week"
    m = _WEEKDAY_NEXT_WEEK.search(lower)
    if m:
        d = _resolve_weekday(m.group(1), "next")
        return d + timedelta(weeks=1)

    # "next Monday"
    m = _WEEKDAY_NEXT.search(lower)
    if m:
        return _resolve_weekday(m.group(1), "next")

    # "this Monday"
    m = _WEEKDAY_THIS.search(lower)
    if m:
        return _resolve_weekday(m.group(1), "this")

    # "last Monday"
    m = _WEEKDAY_LAST.search(lower)
    if m:
        return _resolve_weekday(m.group(1), "last")

    # "Dec 25", "25 Dec", etc.
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                # "Dec 25" or "25 Dec"
                a, b = groups[0], groups[1]
                if a.lower() in _MONTH_NAMES_LC or a.lower() in _MONTH_ABBR:
                    month = _MONTH_ABBR.get(a.lower()[:3], 1)
                    day = int(b)
                else:
                    month = _MONTH_ABBR.get(b.lower()[:3], 1)
                    day = int(a)
                year = now.year
                try:
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    return None
            elif len(groups) == 3:
                if pattern == _DATE_PATTERNS[2]:  # ISO "2024-12-25"
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                else:  # "12/25" or "12/25/2024"
                    month, day = int(groups[0]), int(groups[1])
                    if groups[2]:
                        year = int(groups[2])
                        if year < 100:
                            year += 2000
                    else:
                        year = now.year
                try:
                    return datetime(year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    return None

    return None


def _parse_delta(text: str, now: datetime) -> datetime | None:
    """Parse relative time like "in 2 hours", "in 30 minutes"."""
    m = _RELATIVE_DELTA.search(text.lower())
    if not m:
        return None

    def _to_seconds(val: int, unit: str) -> int:
        unit = unit.lower()[:3]
        multipliers = {
            "sec": 1,
            "min": 60,
            "hou": 3600,
            "day": 86400,
            "wee": 604800,
            "mon": 2592000,  # ~30 days
            "yea": 31536000,  # ~365 days
        }
        return val * multipliers.get(unit, 1)

    total_seconds = 0

    val1 = int(m.group(1)) if m.group(1) else 1
    unit1 = m.group(2)
    total_seconds += _to_seconds(val1, unit1)

    if m.group(3) and m.group(4):
        val2 = int(m.group(3))
        unit2 = m.group(4)
        total_seconds += _to_seconds(val2, unit2)

    return now + timedelta(seconds=total_seconds)


def _apply_time(base: datetime, text: str) -> datetime:
    """Apply a time-of-day to a date result."""
    hour, minute, found = _time_of_day(text)
    if found:
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_datetime(text: str) -> dict[str, Any]:
    """Parse a natural language datetime string.

    Returns a dict with:
        - ``dt``: resolved ``datetime`` (or None on failure)
        - ``precision``: ``"datetime"``, ``"date"``, or ``None``
        - ``original``: the input string
        - ``error``: error message if parsing failed

    Examples::

        >>> parse_datetime("tomorrow at 3pm")
        {"dt": datetime(2026, 7, 2, 15, 0, ...), "precision": "datetime", ...}

        >>> parse_datetime("in 30 minutes")
        {"dt": datetime(2026, 7, 1, 14, 30, ...), "precision": "datetime", ...}

        >>> parse_datetime("next monday")
        {"dt": datetime(2026, 7, 6, 0, 0, ...), "precision": "date", ...}
    """
    result: dict[str, Any] = {"dt": None, "precision": None, "original": text, "error": None}

    if not text or not text.strip():
        result["error"] = "Empty input"
        return result

    text = text.strip()

    # Try dateparser first (handles many edge cases)
    if _HAS_DATEPARSER:
        try:
            settings = {
                "TIMEZONE": "UTC",
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            }
            parsed = dateparser.parse(text, settings=settings)
            if parsed:
                result["dt"] = parsed
                # Determine precision
                has_time = _time_of_day(text)[2] or any(
                    kw in text.lower() for kw in ["today", "tonight"]
                )
                result["precision"] = "datetime" if has_time else "date"
                return result
        except Exception as e:
            logger.debug("dateparser failed: %s", e)

    # Fallback: pure Python parsing
    now = datetime.now(timezone.utc)

    # 1. Try relative delta ("in 2 hours 30 minutes")
    dt = _parse_delta(text, now)
    if dt:
        result["dt"] = dt
        result["precision"] = "datetime"
        return result

    # 2. Try date part parsing
    date_part = _parse_date_part(text, now)
    if date_part:
        # Apply time if present
        hour, minute, has_time = _time_of_day(text)
        if has_time:
            result["dt"] = date_part.replace(hour=hour, minute=minute)
            result["precision"] = "datetime"
        else:
            result["dt"] = date_part
            result["precision"] = "date"
        return result

    # 3. Try "at <time>" only (implies today)
    hour, minute, found = _time_of_day(text)
    if found:
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dt < now:
            dt += timedelta(days=1)  # "at 3pm" after 3pm → tomorrow
        result["dt"] = dt
        result["precision"] = "datetime"
        return result

    result["error"] = f"Could not parse: {text!r}"
    logger.warning("Failed to parse datetime: %s", text)
    return result


def parse_duration(text: str) -> timedelta | None:
    """Parse a natural language duration (e.g. "1 hour", "30 min", "2 days").

    Accepts both "in 2 hours" and "2 hours". Returns a ``timedelta`` or None.
    """
    if not text:
        return None

    # Normalize: ensure "in" prefix so the regex works for bare durations
    normalized = text.lower().strip()
    if not normalized.startswith("in "):
        normalized = "in " + normalized

    m = _RELATIVE_DELTA.search(normalized)
    if not m:
        return None

    def _to_seconds(val: int, unit: str) -> int:
        unit = unit.lower()[:3]
        multipliers = {
            "sec": 1,
            "min": 60,
            "hou": 3600,
            "day": 86400,
            "wee": 604800,
            "mon": 2592000,
            "yea": 31536000,
        }
        return val * multipliers.get(unit, 1)

    total = 0
    val1 = int(m.group(1)) if m.group(1) else 1
    unit1 = m.group(2)
    total += _to_seconds(val1, unit1)

    if m.group(3) and m.group(4):
        val2 = int(m.group(3))
        unit2 = m.group(4)
        total += _to_seconds(val2, unit2)

    return timedelta(seconds=total)
