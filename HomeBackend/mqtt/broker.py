"""Mosquitto MQTT broker configuration generator.

Provides a :func:`generate_mosquitto_config` helper that writes a
``mosquitto.conf`` file with sensible defaults for the Fiona Smart Home
platform.  The generated configuration enables persistence, sets resource
limits, and optionally configures password-file authentication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MOSQUITTO_CONF_TEMPLATE = """# Mosquitto configuration for Fiona Smart Home
# Auto-generated — do not edit manually

# ── Listeners ──────────────────────────────────────────────────────────────
listener {port} 0.0.0.0

# ── Authentication ─────────────────────────────────────────────────────────
allow_anonymous {allow_anonymous}
{password_file_line}

# ── Persistence ────────────────────────────────────────────────────────────
persistence true
persistence_location /var/lib/mosquitto/
autosave_interval 300

# ── Performance ────────────────────────────────────────────────────────────
max_inflight_messages 20
max_queued_messages 1000
message_size_limit 65535

# ── Logging ────────────────────────────────────────────────────────────────
log_dest file /var/log/mosquitto/mosquitto.log
log_type all
connection_messages true

# ── Admin ──────────────────────────────────────────────────────────────────
sys_interval 10
"""


@dataclass
class BrokerConfig:
    """Configuration parameters for the Mosquitto MQTT broker.

    Attributes:
        port:           TCP port for MQTT (default: 1883).
        allow_anonymous: Allow unauthenticated connections.
        password_file:  Path to a Mosquitto password file (optional).  When
                        set, a ``password_file`` directive is added to the
                        generated config.
    """

    port: int = 1883
    allow_anonymous: bool = True
    password_file: Optional[str] = None


def generate_mosquitto_config(config: BrokerConfig, output_path: str) -> Path:
    """Generate a ``mosquitto.conf`` file and write it to *output_path*.

    Args:
        config:      Broker configuration parameters.
        output_path: Filesystem path for the generated configuration file.
                     Parent directories are created if they do not exist.

    Returns:
        The :class:`~pathlib.Path` of the written file.

    Example::

        from HomeBackend.mqtt.broker import BrokerConfig, generate_mosquitto_config

        cfg = BrokerConfig(port=1883, allow_anonymous=False,
                           password_file="/etc/mosquitto/passwd")
        path = generate_mosquitto_config(cfg, "/etc/mosquitto/mosquitto.conf")
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    password_line = ""
    if config.password_file:
        password_line = f"password_file {config.password_file}"

    content = MOSQUITTO_CONF_TEMPLATE.format(
        port=config.port,
        allow_anonymous=str(config.allow_anonymous).lower(),
        password_file_line=password_line,
    )

    path.write_text(content)
    logger.info("Wrote Mosquitto config to %s", path)
    return path
