"""aiohttp application factory for the HomeBackend service."""
from __future__ import annotations

import logging
from typing import Any, Optional

from aiohttp import web

from HomeBackend.config import ServerConfig, load_server_config
from HomeBackend.database import DB_APP_KEY, Database

logger = logging.getLogger(__name__)


class HomeBackendServer:
    """HomeBackend aiohttp server with REST API and WebSocket support.

    Usage::

        server = HomeBackendServer()
        server.run()          # blocks forever
        # or
        web.run_app(server.app)  # equivalent
    """

    def __init__(self, config: Optional[ServerConfig] = None) -> None:
        """Initialise the server with configuration.

        Args:
            config: Server configuration. Loaded from environment if omitted.
        """
        self.config = config or load_server_config()
        self.db = Database(self.config.database.db_path, self.config.database.wal_mode)
        self.app = web.Application()
        self.app[DB_APP_KEY] = self.db

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

        self._setup_middleware()
        self._setup_routes()
        self.app.on_startup.append(self._on_startup)
        self.app.on_shutdown.append(self._on_shutdown)

    # ── Middleware ─────────────────────────────────────────────────────────

    def _setup_middleware(self) -> None:
        """Add CORS, request logging, and error-handling middleware."""

        @web.middleware
        async def error_middleware(
            request: web.Request,
            handler: Any,
        ) -> web.StreamResponse:
            """Convert unhandled exceptions into JSON error responses."""
            try:
                return await handler(request)
            except web.HTTPException as exc:
                # Pass through aiohttp's built-in HTTP exceptions (404, 400, etc.)
                raise
            except Exception as exc:
                logger.exception("Unhandled error handling %s %s", request.method, request.path)
                return web.json_response(
                    {"error": "Internal server error", "detail": str(exc)},
                    status=500,
                )

        @web.middleware
        async def cors_middleware(
            request: web.Request,
            handler: Any,
        ) -> web.StreamResponse:
            """Add CORS headers to every response."""
            if request.method == "OPTIONS":
                # Handle CORS preflight
                response = web.Response(status=204)
            else:
                response = await handler(request)

            origin = self.config.cors_origins
            if origin == "*":
                origin = request.headers.get("Origin", "*")

            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Max-Age"] = "86400"
            return response

        @web.middleware
        async def logging_middleware(
            request: web.Request,
            handler: Any,
        ) -> web.StreamResponse:
            """Log every request."""
            logger.info("%s %s", request.method, request.path_qs)
            response = await handler(request)
            logger.debug("%s %s → %d", request.method, request.path, response.status)
            return response

        self.app.middlewares.append(logging_middleware)
        self.app.middlewares.append(cors_middleware)
        self.app.middlewares.append(error_middleware)

    # ── Routes ─────────────────────────────────────────────────────────────

    def _setup_routes(self) -> None:
        """Register REST and WebSocket routes."""
        from HomeBackend.routes.devices import routes as device_routes
        from HomeBackend.routes.rooms import routes as room_routes
        from HomeBackend.routes.health import routes as health_routes
        from HomeBackend.routes.scenes import routes as scene_routes
        from HomeBackend.routes.events import routes as event_routes
        from HomeBackend.websocket import ws_handler

        self.app.router.add_routes(device_routes)
        self.app.router.add_routes(room_routes)
        self.app.router.add_routes(health_routes)
        self.app.router.add_routes(scene_routes)
        self.app.router.add_routes(event_routes)
        self.app.router.add_get("/ws", ws_handler)

    # ── Lifecycle hooks ────────────────────────────────────────────────────

    async def _on_startup(self, app: web.Application) -> None:
        """Initialise the database and any background tasks."""
        self.db.connect()
        logger.info(
            "HomeBackend server started on %s:%d",
            self.config.host,
            self.config.port,
        )

    async def _on_shutdown(self, app: web.Application) -> None:
        """Clean shutdown — close database and connections."""
        self.db.close()
        logger.info("HomeBackend server shut down")

    # ── Runner ─────────────────────────────────────────────────────────────

    def run(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """Start the server and block until interrupted.

        Args:
            host: Override the configured host.
            port: Override the configured port.
        """
        web.run_app(
            self.app,
            host=host or self.config.host,
            port=port or self.config.port,
            print=lambda *args: logger.info(" ".join(str(a) for a in args)),
        )
