"""Health check endpoints for Docker / orchestration probes."""
from __future__ import annotations

import logging

from aiohttp import web

from HomeBackend.database import DB_APP_KEY

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


@routes.get("/api/health")
async def health(_request: web.Request) -> web.Response:
    """Liveness probe — always returns 200 when the server is running."""
    return web.json_response({"status": "ok", "service": "homebackend"})


@routes.get("/api/health/ready")
async def readiness(request: web.Request) -> web.Response:
    """Readiness probe — checks that the database is connected."""
    db = request.app.get(DB_APP_KEY)
    if db is not None and db.is_connected:
        return web.json_response({"status": "ready"})
    return web.json_response({"status": "not_ready"}, status=503)
