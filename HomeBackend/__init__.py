"""HomeBackend — Standalone smart home simulation server."""
from __future__ import annotations

from HomeBackend.config import DatabaseConfig, ServerConfig, WebSocketConfig, load_server_config
from HomeBackend.database import Database

# App-key — defined before server import to avoid circular dependency.
DB_APP_KEY = "db"

from HomeBackend.server import HomeBackendServer  # noqa: E402
from HomeBackend.websocket import broadcast_event  # noqa: E402

__all__ = [
    "ServerConfig",
    "DatabaseConfig",
    "WebSocketConfig",
    "load_server_config",
    "Database",
    "DB_APP_KEY",
    "HomeBackendServer",
    "broadcast_event",
]
