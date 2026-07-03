"""Server configuration for the HomeBackend service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from SmartHome.config import HomeBackendConfig as BaseConfig


@dataclass
class DatabaseConfig:
    """SQLite database configuration."""

    db_path: str = "~/.config/fiona/homebackend.db"
    wal_mode: bool = True
    pool_size: int = 5
    timeout: float = 5.0


@dataclass
class WebSocketConfig:
    """WebSocket server configuration."""

    heartbeat_interval: int = 30
    max_message_size: int = 65536
    max_connections: int = 100


@dataclass
class ServerConfig:
    """Aggregate server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    cors_origins: str = "*"
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)


def load_server_config() -> ServerConfig:
    """Load config from environment variables (``HB_HOST``, ``HB_PORT``, etc.).

    Recognised environment variables (case-insensitive):

    =====================  ==========================
    Variable               Field
    =====================  ==========================
    ``HB_HOST``            host
    ``HB_PORT``            port
    ``HB_LOG_LEVEL``       log_level
    ``HB_CORS_ORIGINS``    cors_origins
    ``HB_DB_PATH``         database.db_path
    ``HB_DB_WAL``          database.wal_mode
    ``HB_DB_TIMEOUT``      database.timeout
    ``HB_WS_HEARTBEAT``    websocket.heartbeat_interval
    ``HB_WS_MAX_MSG_SIZE`` websocket.max_message_size
    ``HB_WS_MAX_CONN``     websocket.max_connections
    =====================  ==========================
    """
    return ServerConfig(
        host=os.getenv("HB_HOST", "0.0.0.0"),
        port=int(os.getenv("HB_PORT", "8080")),
        log_level=os.getenv("HB_LOG_LEVEL", "INFO"),
        cors_origins=os.getenv("HB_CORS_ORIGINS", "*"),
        database=DatabaseConfig(
            db_path=os.getenv("HB_DB_PATH", "~/.config/fiona/homebackend.db"),
            wal_mode=os.getenv("HB_DB_WAL", "true").lower() in ("1", "true", "yes"),
            timeout=float(os.getenv("HB_DB_TIMEOUT", "5.0")),
        ),
        websocket=WebSocketConfig(
            heartbeat_interval=int(os.getenv("HB_WS_HEARTBEAT", "30")),
            max_message_size=int(os.getenv("HB_WS_MAX_MSG_SIZE", "65536")),
            max_connections=int(os.getenv("HB_WS_MAX_CONN", "100")),
        ),
    )
