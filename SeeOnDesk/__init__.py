"""Desktop awareness helpers for Fiona."""

from __future__ import annotations

from .desktop import (
    ActiveWindowInfo,
    DesktopSnapshot,
    active_window_info,
    all_windows_info,
    desktop_snapshot,
)
from .vision import analyze_screen, capture_screen, capture_window
from .process_tracker import ProcessTracker, ProcessInfo
from .workspace_watcher import WorkspaceWatcher, WorkspaceInfo, WorkspaceChange
from .action_discovery import discover_actions, DiscoveredAction
from .ocr import (
    OcrResult,
    list_supported_languages,
    parse_region_string,
    read_image,
    read_image_pil,
    read_screen_region,
    read_window_region,
    tesseract_available,
)
from .region_monitor import RegionConfig, RegionTextChange, RegionMonitor
from .screen_monitor import ScreenChange, ScreenMonitor, compute_diff
from .change_events import ChangeEvent, EventEmitter, EventType, make_screen_change_adapter, make_region_change_adapter

__all__ = [
    "ActiveWindowInfo",
    "DesktopSnapshot",
    "active_window_info",
    "all_windows_info",
    "desktop_snapshot",
    "analyze_screen",
    "capture_screen",
    "capture_window",
    "ProcessTracker",
    "ProcessInfo",
    "WorkspaceWatcher",
    "WorkspaceInfo",
    "WorkspaceChange",
    "discover_actions",
    "DiscoveredAction",
    "OcrResult",
    "list_supported_languages",
    "parse_region_string",
    "read_image",
    "read_image_pil",
    "read_screen_region",
    "read_window_region",
    "tesseract_available",
    "ScreenChange",
    "ScreenMonitor",
    "compute_diff",
    "RegionConfig",
    "RegionTextChange",
    "RegionMonitor",
    "ChangeEvent",
    "EventEmitter",
    "EventType",
    "make_screen_change_adapter",
    "make_region_change_adapter",
]
