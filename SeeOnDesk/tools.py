"""Agent-callable tools for Tier 2 (Perception) desktop capabilities.

Provides OCR-based screen reading, region watching, and OCR availability
checking as :class:`ITool` implementations compatible with Fiona's central
tool system.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fiona.tools.interfaces import ITool
from fiona.tools.models import ToolCategory, ToolContext, ToolResult, ToolSpec

from SeeOnDesk.ocr import (
    OcrResult,
    list_supported_languages,
    parse_region_string,
    read_screen_region,
    read_window_region,
    tesseract_available,
)
from SeeOnDesk.region_monitor import RegionConfig, RegionMonitor, RegionTextChange

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool: ReadScreenTextTool
# ---------------------------------------------------------------------------


class ReadScreenTextTool(ITool):
    """Reads text from a screen region or a specific window using OCR.

    Provide either a *region* (``"x,y,w,h"``) to read a portion of the
    screen, or a *window_id* to capture and read text from a specific
    desktop window.  If both are provided when *window_id* is given, the
    *region* is interpreted as a sub-region within that window.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="read_screen_text",
            description=(
                "Read text from a screen region or a specific window using "
                "OCR. Provide either a 'region' (x,y,w,h) to read a portion "
                "of the screen, or a 'window_id' to read text from a specific "
                "desktop window."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": (
                            "Screen region as 'x,y,w,h' "
                            "(left, top, width, height). When used with "
                            "window_id, this is a sub-region within the window."
                        ),
                    },
                    "window_id": {
                        "type": "string",
                        "description": (
                            "X11/Wayland window ID to capture. If omitted, "
                            "the full screen (or region thereof) is used."
                        ),
                    },
                    "lang": {
                        "type": "string",
                        "description": (
                            "Tesseract language code(s), e.g. 'eng', 'fra', "
                            "or 'eng+fra' for multiple languages."
                        ),
                        "default": "eng",
                    },
                },
                "required": [],
            },
            category=ToolCategory.SYSTEM,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        region_str = kwargs.get("region")
        window_id = kwargs.get("window_id")
        lang = str(kwargs.get("lang", "eng"))

        # At least one of region or window_id must be provided
        if not region_str and not window_id:
            return ToolResult(
                success=False,
                content="",
                error=(
                    "Either 'region' or 'window_id' must be provided."
                ),
            )

        try:
            result: OcrResult

            if window_id:
                region = None
                if region_str:
                    region = parse_region_string(str(region_str))
                result = read_window_region(
                    str(window_id),
                    region=region,
                    lang=lang,
                )
            else:
                region = parse_region_string(str(region_str))
                result = read_screen_region(
                    region=region,
                    lang=lang,
                )

            if not result.success:
                return ToolResult(
                    success=False,
                    content="",
                    error=result.error or "OCR operation returned no result.",
                )

            text = result.text.strip()
            context.logger.info(
                "read_screen_text: extracted %d characters "
                "(confidence=%.1f)",
                len(result.text),
                result.confidence,
            )

            return ToolResult(
                success=True,
                content=text if text else "(no text detected in region)",
                metadata={
                    "confidence": result.confidence,
                    "language": result.language,
                    "char_count": len(result.text),
                    "box_count": len(result.boxes),
                },
            )

        except ValueError as exc:
            return ToolResult(
                success=False,
                content="",
                error=str(exc),
            )
        except Exception as exc:
            context.logger.error(
                "read_screen_text error: %s", exc, exc_info=True
            )
            return ToolResult(
                success=False,
                content="",
                error=f"Unexpected error reading screen text: {exc}",
            )


# ---------------------------------------------------------------------------
# Tool: WatchRegionTool
# ---------------------------------------------------------------------------


class WatchRegionTool(ITool):
    """Watches a screen region for text changes over a period.

    Uses :class:`SeeOnDesk.region_monitor.RegionMonitor` internally to
    poll OCR at regular intervals and collect text changes.  The watch
    runs for *duration_seconds* (or until the cancellation token is
    signalled) and returns all detected changes.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="watch_region",
            description=(
                "Watch a screen region for text changes over a duration. "
                "Starts a region monitor that polls OCR at regular intervals "
                "and collects any text changes detected within the given "
                "timeframe."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": (
                            "Screen region to watch as 'x,y,w,h' "
                            "(left, top, width, height)."
                        ),
                    },
                    "lang": {
                        "type": "string",
                        "description": (
                            "Tesseract language code (default 'eng')."
                        ),
                        "default": "eng",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "description": (
                            "Number of seconds to watch the region for "
                            "text changes."
                        ),
                        "default": 10,
                    },
                },
                "required": ["region"],
            },
            category=ToolCategory.SYSTEM,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        region_str = kwargs.get("region")
        lang = str(kwargs.get("lang", "eng"))
        duration = int(kwargs.get("duration_seconds", 10))

        if not region_str:
            return ToolResult(
                success=False,
                content="",
                error="Missing required argument: 'region'",
            )

        if duration <= 0:
            return ToolResult(
                success=False,
                content="",
                error="duration_seconds must be a positive integer",
            )

        try:
            region = parse_region_string(str(region_str))
        except ValueError as exc:
            return ToolResult(
                success=False,
                content="",
                error=str(exc),
            )

        # Thread-safe collector for text changes
        collected_changes: list[dict[str, Any]] = []
        collected_lock = threading.Lock()

        def on_change(change: RegionTextChange) -> None:
            entry: dict[str, Any] = {
                "diff_type": change.diff_type,
                "old_text": change.old_text,
                "new_text": change.new_text,
                "timestamp": change.timestamp,
            }
            with collected_lock:
                collected_changes.append(entry)

        config = RegionConfig(
            region=region,
            poll_interval=1.0,
            lang=lang,
        )

        monitor = RegionMonitor()
        watch_id = monitor.watch_region(config, on_change=on_change)

        context.logger.info(
            "watch_region: watching %s for %d seconds (watch_id=%s)",
            region_str,
            duration,
            watch_id,
        )

        try:
            # Wait for the duration, checking cancellation periodically
            check_interval = 0.5
            elapsed = 0.0
            while elapsed < duration:
                if context.cancellation_token is not None and context.cancellation_token.is_set():
                    context.logger.info(
                        "watch_region: cancelled after %.1f seconds",
                        elapsed,
                    )
                    break
                await asyncio.sleep(check_interval)
                elapsed += check_interval
        finally:
            monitor.unwatch_region(watch_id)

        with collected_lock:
            final_changes = list(collected_changes)

        change_count = len(final_changes)
        actual_duration = min(elapsed, float(duration))
        context.logger.info(
            "watch_region: collected %d change(s) in %.1f seconds",
            change_count,
            actual_duration,
        )

        if not final_changes:
            return ToolResult(
                success=True,
                content="No text changes detected in the watched region.",
                metadata={
                    "region": region_str,
                    "duration_seconds": duration,
                    "change_count": 0,
                },
            )

        lines: list[str] = [
            f"Detected {change_count} text change(s) "
            f"over {actual_duration:.1f}s:"
        ]
        for i, ch in enumerate(final_changes, 1):
            lines.append(
                f"  {i}. [{ch['diff_type']}] at {ch['timestamp']}"
            )
            if ch["old_text"]:
                lines.append(f"     Was: {ch['old_text'][:200]}")
            if ch["new_text"]:
                lines.append(f"     Now: {ch['new_text'][:200]}")

        return ToolResult(
            success=True,
            content="\n".join(lines),
            metadata={
                "region": region_str,
                "duration_seconds": duration,
                "actual_watch_seconds": actual_duration,
                "change_count": change_count,
            },
            artifacts=final_changes,
        )


# ---------------------------------------------------------------------------
# Tool: CheckOcrTool
# ---------------------------------------------------------------------------


class CheckOcrTool(ITool):
    """Checks whether Tesseract OCR is available and lists supported
    languages.

    Takes no arguments — purely a diagnostic/readiness tool.
    """

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="check_ocr",
            description=(
                "Check whether Tesseract OCR is available on this system "
                "and list the installed language packs."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
            category=ToolCategory.SYSTEM,
        )

    async def run(
        self, context: ToolContext, **kwargs: object
    ) -> ToolResult:
        available = tesseract_available()
        languages = list_supported_languages() if available else []

        lines = [
            f"Tesseract OCR available: {available}",
        ]
        if available:
            if languages:
                lines.append(
                    f"Supported languages ({len(languages)}): "
                    f"{', '.join(sorted(languages))}"
                )
            else:
                lines.append(
                    "Supported languages: (none detected — "
                    "install language packs)"
                )
        else:
            lines.append(
                "Install tesseract-ocr and pytesseract to enable OCR "
                "desktop text reading."
            )

        return ToolResult(
            success=True,
            content="\n".join(lines),
            metadata={
                "available": available,
                "language_count": len(languages),
                "languages": languages,
            },
        )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def register_desk_tools(registry: Any) -> None:
    """Register all SeeOnDesk perception tools with *registry*.

    The *registry* must expose a ``register(tool, source)`` method
    compatible with :class:`Agent.tool_runtime.ToolRegistry`.

    Args:
        registry: A tool registry instance (e.g. ``ToolRegistry()``).
    """
    registry.register(ReadScreenTextTool(), source="desk")
    registry.register(WatchRegionTool(), source="desk")
    registry.register(CheckOcrTool(), source="desk")
    logger.info("Registered 3 SeeOnDesk perception tools")
