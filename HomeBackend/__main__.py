"""Entrypoint for running the HomeBackend service with ``python -m HomeBackend``."""
from __future__ import annotations

from HomeBackend.config import load_server_config
from HomeBackend.server import HomeBackendServer


def main() -> None:
    """Load configuration and start the server."""
    config = load_server_config()
    server = HomeBackendServer(config)
    server.run()


if __name__ == "__main__":
    main()
