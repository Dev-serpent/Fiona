"""Configuration for GNS3 automation."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GNS3Config:
    """GNS3 server connection configuration.

    Args:
        host: GNS3 server hostname or IP.
        port: GNS3 REST API port (default 3080).
        protocol: ``"http"`` or ``"https"``.
        user: Optional HTTP basic auth username.
        password: Optional HTTP basic auth password.
        timeout: Default request timeout in seconds.
        verify_ssl: Whether to verify SSL certificates.
    """

    host: str = "127.0.0.1"
    port: int = 3080
    protocol: str = "http"
    user: str = ""
    password: str = ""
    timeout: float = 30.0
    verify_ssl: bool = True

    @property
    def base_url(self) -> str:
        """The GNS3 REST API base URL."""
        return f"{self.protocol}://{self.host}:{self.port}/v2"


def load_gns3_config() -> GNS3Config:
    """Load GNS3 config from environment variables.

    Recognised variables (case-insensitive):

    ==================  ================
    Variable            Field
    ==================  ================
    ``GNS3_HOST``       host
    ``GNS3_PORT``       port
    ``GNS3_PROTOCOL``   protocol
    ``GNS3_USER``       user
    ``GNS3_PASSWORD``   password
    ``GNS3_TIMEOUT``    timeout
    ``GNS3_VERIFY_SSL`` verify_ssl
    ==================  ================
    """
    return GNS3Config(
        host=os.getenv("GNS3_HOST", "127.0.0.1"),
        port=int(os.getenv("GNS3_PORT", "3080")),
        protocol=os.getenv("GNS3_PROTOCOL", "http"),
        user=os.getenv("GNS3_USER", ""),
        password=os.getenv("GNS3_PASSWORD", ""),
        timeout=float(os.getenv("GNS3_TIMEOUT", "30.0")),
        verify_ssl=os.getenv("GNS3_VERIFY_SSL", "true").lower() in ("1", "true", "yes"),
    )
