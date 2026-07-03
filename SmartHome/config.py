"""Configuration dataclasses with environment-variable loading.

All config objects have sensible defaults suitable for local development.
Production values are typically supplied via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# ── MQTT Configuration ───────────────────────────────────────────────────────

@dataclass
class MqttConfig:
    """MQTT broker connection parameters."""

    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    tls_enabled: bool = False
    ca_cert: str = ""
    client_id: str = "fiona-smarthome"
    topic_prefix: str = "fiona"
    qos: int = 1


def load_mqtt_config() -> MqttConfig:
    """Build an ``MqttConfig`` from environment variables prefixed with ``MQTT_``.

    Environment variables (case-insensitive):

    ========================  ===========
    Variable                  Field
    ========================  ===========
    ``MQTT_HOST``             host
    ``MQTT_PORT``             port
    ``MQTT_USERNAME``         username
    ``MQTT_PASSWORD``         password
    ``MQTT_TLS_ENABLED``      tls_enabled
    ``MQTT_CA_CERT``          ca_cert
    ``MQTT_CLIENT_ID``        client_id
    ``MQTT_TOPIC_PREFIX``     topic_prefix
    ``MQTT_QOS``              qos
    ========================  ===========
    """
    return MqttConfig(
        host=os.getenv("MQTT_HOST", "localhost"),
        port=int(os.getenv("MQTT_PORT", "1883")),
        username=os.getenv("MQTT_USERNAME", ""),
        password=os.getenv("MQTT_PASSWORD", ""),
        tls_enabled=os.getenv("MQTT_TLS_ENABLED", "").lower() in ("1", "true", "yes"),
        ca_cert=os.getenv("MQTT_CA_CERT", ""),
        client_id=os.getenv("MQTT_CLIENT_ID", "fiona-smarthome"),
        topic_prefix=os.getenv("MQTT_TOPIC_PREFIX", "fiona"),
        qos=int(os.getenv("MQTT_QOS", "1")),
    )


# ── HomeBackend Configuration ────────────────────────────────────────────────

@dataclass
class HomeBackendConfig:
    """Standalone smart-home simulation server settings."""

    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "~/.config/fiona/homebackend.db"
    log_level: str = "INFO"
    cors_origins: str = "*"


def load_homebackend_config() -> HomeBackendConfig:
    """Build a ``HomeBackendConfig`` from environment variables prefixed with ``HB_``.

    Environment variables (case-insensitive):

    ==================  ===========
    Variable            Field
    ==================  ===========
    ``HB_HOST``         host
    ``HB_PORT``         port
    ``HB_DB_PATH``      db_path
    ``HB_LOG_LEVEL``    log_level
    ``HB_CORS_ORIGINS`` cors_origins
    ==================  ===========
    """
    return HomeBackendConfig(
        host=os.getenv("HB_HOST", "0.0.0.0"),
        port=int(os.getenv("HB_PORT", "8080")),
        db_path=os.getenv("HB_DB_PATH", "~/.config/fiona/homebackend.db"),
        log_level=os.getenv("HB_LOG_LEVEL", "INFO"),
        cors_origins=os.getenv("HB_CORS_ORIGINS", "*"),
    )
