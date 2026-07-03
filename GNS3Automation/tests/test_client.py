"""Tests for the GNS3 client (HTTP mocking with aioresponses)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aioresponses import aioresponses

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config
from GNS3Automation.errors import GNS3ConnectionError, GNS3NotFoundError


@pytest.fixture
def config() -> GNS3Config:
    return GNS3Config(host="127.0.0.1", port=3080)


@pytest.fixture
def base_url(config: GNS3Config) -> str:
    return config.base_url


@pytest.mark.asyncio
class TestGNS3Client:
    """Tests for the low-level GNS3 REST client."""

    async def test_ping_success(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(f"{base_url}/version", payload={"version": "2.2.49"})
                result = await client.ping()
                assert result is True

    async def test_ping_failure(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(f"{base_url}/version", exception=GNS3ConnectionError("fail"))
                # Actually aioresponses with exception=None doesn't work well here
                # Instead test connection refused
                result = await client.ping()
                assert result is False

    async def test_list_projects(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects",
                    payload=[{"project_id": "p1", "name": "test-lab"}],
                )
                projects = await client.list_projects()
                assert len(projects) == 1
                assert projects[0]["name"] == "test-lab"

    async def test_list_projects_empty(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(f"{base_url}/projects", payload=[])
                projects = await client.list_projects()
                assert projects == []

    async def test_create_project(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects",
                    payload={"project_id": "p-new", "name": "my-lab", "status": "closed"},
                    status=201,
                )
                result = await client.create_project({"name": "my-lab"})
                assert result["project_id"] == "p-new"

    async def test_get_project(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/p1",
                    payload={"project_id": "p1", "name": "test"},
                )
                result = await client.get_project("p1")
                assert result["project_id"] == "p1"

    async def test_get_project_not_found(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/nonexistent",
                    status=404,
                    body='{"message": "Not found"}',
                )
                with pytest.raises(GNS3NotFoundError):
                    await client.get_project("nonexistent")

    async def test_delete_project(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.delete(f"{base_url}/projects/p1", status=204)
                result = await client.delete_project("p1")
                assert result is None

    async def test_open_project(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/open",
                    payload={"project_id": "p1", "status": "opened"},
                )
                result = await client.open_project("p1")
                assert result["status"] == "opened"

    async def test_close_project(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/close",
                    payload={"project_id": "p1", "status": "closed"},
                )
                result = await client.close_project("p1")
                assert result["status"] == "closed"

    async def test_list_nodes(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/p1/nodes",
                    payload=[{"node_id": "n1", "name": "alpine-1"}],
                )
                nodes = await client.list_nodes("p1")
                assert len(nodes) == 1

    async def test_create_node(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/nodes",
                    payload={"node_id": "n1", "name": "alpine-1", "status": "stopped"},
                    status=201,
                )
                result = await client.create_node("p1", {"name": "alpine-1", "node_type": "docker"})
                assert result["node_id"] == "n1"

    async def test_start_node(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/nodes/n1/start",
                    payload={"node_id": "n1", "status": "started"},
                )
                result = await client.start_node("p1", "n1")
                assert result["status"] == "started"

    async def test_stop_node(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/nodes/n1/stop",
                    payload={"node_id": "n1", "status": "stopped"},
                )
                result = await client.stop_node("p1", "n1")
                assert result["status"] == "stopped"

    async def test_list_links(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/p1/links",
                    payload=[{"link_id": "l1"}],
                )
                links = await client.list_links("p1")
                assert len(links) == 1

    async def test_create_link(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/links",
                    payload={"link_id": "l1"},
                    status=201,
                )
                result = await client.create_link(
                    "p1", {"nodes": [{"node_id": "n1"}, {"node_id": "n2"}]}
                )
                assert result["link_id"] == "l1"

    async def test_list_templates(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/templates",
                    payload=[{"template_id": "t1", "name": "alpine"}],
                )
                templates = await client.list_templates()
                assert len(templates) == 1

    async def test_get_version(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(f"{base_url}/version", payload={"version": "2.2.49"})
                version = await client.get_version()
                assert version["version"] == "2.2.49"

    async def test_list_computes(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/compute",
                    payload=[{"compute_id": "local", "name": "local"}],
                )
                computes = await client.list_computes()
                assert len(computes) == 1

    async def test_connection_error(self, config: GNS3Config, base_url: str) -> None:
        """A network error raises GNS3ConnectionError."""
        import aiohttp
        async with GNS3Client(config) as client:
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects",
                    exception=aiohttp.ClientConnectionError("refused"),
                )
                with pytest.raises(GNS3ConnectionError):
                    await client.list_projects()

    async def test_not_connected_raises(self, config: GNS3Config) -> None:
        """Calling methods before connect() raises."""
        client = GNS3Client(config)
        with pytest.raises(GNS3ConnectionError, match="not connected"):
            await client.list_projects()
