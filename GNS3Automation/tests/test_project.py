"""Tests for GNS3 project manager."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config
from GNS3Automation.errors import GNS3ProjectError
from GNS3Automation.project import ProjectManager


@pytest.fixture
def config() -> GNS3Config:
    return GNS3Config(host="127.0.0.1", port=3080)


@pytest.fixture
def base_url(config: GNS3Config) -> str:
    return config.base_url


@pytest.mark.asyncio
class TestProjectManager:
    async def test_create(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects",
                    payload={
                        "project_id": "p1",
                        "name": "my-lab",
                        "status": "closed",
                    },
                    status=201,
                )
                project = await mgr.create("my-lab")
                assert project.project_id == "p1"
                assert project.name == "my-lab"

    async def test_get(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/p1",
                    payload={"project_id": "p1", "name": "test", "status": "opened"},
                )
                project = await mgr.get("p1")
                assert project is not None
                assert project.name == "test"

    async def test_get_not_found(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.get(f"{base_url}/projects/nope", status=404, body="{}")
                project = await mgr.get("nope")
                assert project is None

    async def test_list(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects",
                    payload=[
                        {"project_id": "p1", "name": "lab-1"},
                        {"project_id": "p2", "name": "lab-2"},
                    ],
                )
                projects = await mgr.list()
                assert len(projects) == 2

    async def test_delete(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.delete(f"{base_url}/projects/p1", status=204)
                result = await mgr.delete("p1")
                assert result is True

    async def test_delete_not_found(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.delete(f"{base_url}/projects/nope", status=404, body="{}")
                result = await mgr.delete("nope")
                assert result is False

    async def test_open(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/open",
                    payload={"project_id": "p1", "status": "opened"},
                )
                project = await mgr.open("p1")
                assert project.status == "opened"

    async def test_close(self, config: GNS3Config, base_url: str) -> None:
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/close",
                    payload={"project_id": "p1", "status": "closed"},
                )
                project = await mgr.close("p1")
                assert project.status == "closed"

    async def test_create_failure_raises(self, config: GNS3Config) -> None:
        """A network failure during create raises GNS3ProjectError."""
        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            with aioresponses() as mocked:
                # No mock = connection refused
                with pytest.raises(GNS3ProjectError, match="Failed to create"):
                    await mgr.create("broken-lab")
