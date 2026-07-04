"""Shared fixtures for GNS3 tests — real server when available, mock otherwise.

Environment variables:
    GNS3_HOST       GNS3 server hostname (default: 127.0.0.1)
    GNS3_PORT       GNS3 API port       (default: 3080)
    GNS3_PROTOCOL   http or https       (default: http)
    GNS3_REAL       Set to "1"/"true" to force real-server tests
                    (auto-detection also tries to ping the server)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

import aiohttp
import pytest

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config
from GNS3Automation.project import ProjectManager

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────


async def _probe_server(config: GNS3Config, timeout: float = 3.0) -> bool:
    """Return ``True`` if a real GNS3 server responds at the configured URL."""
    url = f"{config.base_url}/version"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                ok = resp.status == 200
                if ok:
                    data = await resp.json()
                    logger.info(
                        "Real GNS3 server detected at %s (v%s)",
                        config.base_url,
                        data.get("version", "?"),
                    )
                return ok
    except (OSError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
        logger.debug("No GNS3 server at %s: %s", config.base_url, exc)
        return False


async def _create_cleanup_project(
    client: GNS3Client,
    name: str = "test-gns3-auto",
) -> tuple[object, object]:
    """Create a temporary test project.

    Returns ``(project, project_manager)``.  Caller is responsible for
    deleting the project after the test.
    """
    mgr = ProjectManager(client)
    project = await mgr.create(name)
    return project, mgr


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def gns3_config() -> GNS3Config:
    """GNS3 connection configuration from environment variables.

    Override with ``GNS3_HOST``, ``GNS3_PORT``, ``GNS3_PROTOCOL``.
    """
    return GNS3Config(
        host=os.getenv("GNS3_HOST", "127.0.0.1"),
        port=int(os.getenv("GNS3_PORT", "3080")),
        protocol=os.getenv("GNS3_PROTOCOL", "http"),
    )


@pytest.fixture(scope="session")
def gns3_real_available(gns3_config: GNS3Config) -> bool:
    """Check whether a real GNS3 server is reachable.

    The check is performed once per test session.  Set
    ``GNS3_REAL=true`` to force real-server mode (the probe still runs
    to confirm availability).
    """
    force = os.getenv("GNS3_REAL", "").lower() in ("1", "true", "yes")
    available = asyncio.run(_probe_server(gns3_config))
    return force or available


@pytest.fixture
async def gns3_client(
    gns3_config: GNS3Config,
    gns3_real_available: bool,
) -> AsyncIterator[GNS3Client]:
    """Provide a ``GNS3Client`` connected to a real server when available.

    When no real server is reachable, this fixture raises
    ``pytest.skip()`` — tests that require a real server should use
    ``@pytest.mark.skipif(not gns3_real_available)`` or check the
    ``gns3_real_available`` fixture.

    Yields:
        A connected ``GNS3Client`` instance.
    """
    if not gns3_real_available:
        pytest.skip("No real GNS3 server available (set GNS3_REAL=1 or start a server)")

    client = GNS3Client(gns3_config)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


@pytest.fixture
async def test_project(
    gns3_client: GNS3Client,
) -> AsyncIterator[tuple[object, ProjectManager]]:
    """A temporary GNS3 project that is deleted after the test.

    Yields ``(project, project_manager)``.  Requires a real GNS3 server.
    """
    mgr = ProjectManager(gns3_client)
    project = await mgr.create("test-gns3-auto")
    try:
        yield project, mgr
    finally:
        try:
            await mgr.delete(project.project_id)
        except Exception:
            logger.warning("Failed to delete test project %s", project.project_id)
