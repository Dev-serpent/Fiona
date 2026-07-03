"""Failure simulation tests for the Fiona lab.

Tests graceful degradation and error handling when GNS3 or backend
components are unavailable or return errors.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aioresponses import aioresponses

from GNS3Automation.errors import GNS3Error, GNS3ProjectError
from Laboratory.start_lab import start_lab
from Laboratory.topology import FIONA_LAB_NAME

# Suppress logging noise during failure tests


class TestGNS3Unreachable:
    """When the GNS3 server cannot be reached."""

    @pytest.mark.asyncio
    async def test_connection_refused(self) -> None:
        """GNS3 server down → GNS3Error."""
        with aioresponses() as mock_http:
            # Any request raises a connection error
            mock_http.get(
                "http://127.0.0.1:3080/v2/projects",
                exception=ConnectionError("Connection refused"),
            )
            with pytest.raises(GNS3Error):
                await start_lab(gns3_host="127.0.0.1", gns3_port=3080)

    @pytest.mark.asyncio
    async def test_project_list_returns_500(self) -> None:
        """Server returns 500 on project list → GNS3Error."""
        with aioresponses() as mock_http:
            mock_http.get(
                "http://127.0.0.1:3080/v2/projects",
                status=500,
                body="Internal Server Error",
            )
            # The 500 will be wrapped in GNS3ConnectionError by _request
            with pytest.raises(GNS3Error):
                await start_lab(gns3_host="127.0.0.1", gns3_port=3080)

    @pytest.mark.asyncio
    async def test_gns3_timeout(self) -> None:
        """GNS3 request times out."""
        with aioresponses() as mock_http:
            mock_http.get(
                "http://127.0.0.1:3080/v2/projects",
                exception=TimeoutError("Timed out"),
            )
            with pytest.raises(GNS3Error):
                await start_lab(gns3_host="127.0.0.1", gns3_port=3080)


class TestPartialFailures:
    """Scenarios where some operations fail but the lab should still work."""

    @pytest.mark.asyncio
    async def test_project_creation_fails(
        self,
        base_url: str,
        project_payload: dict[str, Any],
    ) -> None:
        """Project creation fails → error is raised."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           status=500,
                           body="Server error")

            with pytest.raises(GNS3Error):
                await start_lab(gns3_host="127.0.0.1", gns3_port=3080)

    @pytest.mark.asyncio
    async def test_some_nodes_fail_to_create(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """If some nodes fail to create, fall back to listing existing nodes."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload, status=201)

            # First node (broker) succeeds
            mock_http.post(
                f"{base_url}/projects/{project_id}/nodes",
                payload=sample_node_payloads[0],
                status=201,
            )
            # All subsequent node creations fail
            mock_http.post(
                f"{base_url}/projects/{project_id}/nodes",
                status=500,
                body="Node creation failed",
                repeat=True,
            )

            # List nodes returns existing nodes
            mock_http.get(
                f"{base_url}/projects/{project_id}/nodes",
                payload=[sample_node_payloads[0]],
            )

            # Links — just mock to avoid cascading failures
            mock_http.post(
                f"{base_url}/projects/{project_id}/links",
                payload=link_payload,
                status=201,
                repeat=True,
            )

            result = await start_lab(gns3_host="127.0.0.1", gns3_port=3080)
            # Should have fallen back to listing existing nodes
            assert result["node_count"] >= 1
            assert result["project_id"] == project_id

    @pytest.mark.asyncio
    async def test_all_nodes_fail_then_list_returns_some(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """All node creation fails, fallback list returns 1 node."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload, status=201)

            # All node creations fail
            mock_http.post(
                f"{base_url}/projects/{project_id}/nodes",
                status=500,
                body="Node creation failed",
                repeat=True,
            )

            # List nodes returns a single existing node
            mock_http.get(
                f"{base_url}/projects/{project_id}/nodes",
                payload=[sample_node_payloads[0]],
            )

            mock_http.post(
                f"{base_url}/projects/{project_id}/links",
                payload=link_payload,
                status=201,
                repeat=True,
            )

            result = await start_lab(gns3_host="127.0.0.1", gns3_port=3080)
            assert result["node_count"] == 1

    @pytest.mark.asyncio
    async def test_link_creation_fails_gracefully(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """Links failing should log a warning but not crash the lab."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload, status=201)

            for node_payload in sample_node_payloads:
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes",
                    payload=node_payload,
                    status=201,
                )

            # All link creations fail
            mock_http.post(
                f"{base_url}/projects/{project_id}/links",
                status=500,
                body="Link creation failed",
                repeat=True,
            )

            result = await start_lab(gns3_host="127.0.0.1", gns3_port=3080)
            # Lab should still be created, just without full connectivity
            assert result["project_id"] == project_id
            assert result["node_count"] == len(sample_node_payloads)


class TestHomeBackendUnavailable:
    """Device discovery when the HomeBackend API is down."""

    @pytest.mark.asyncio
    async def test_discover_with_backend_down(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """Device discovery should not crash the lab when backend is unreachable."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload, status=201)

            for node_payload in sample_node_payloads:
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes",
                    payload=node_payload,
                    status=201,
                )

            for _ in range(9):
                mock_http.post(
                    f"{base_url}/projects/{project_id}/links",
                    payload=link_payload,
                    status=201,
                )

            # HomeBackend is unreachable — aiohttp will raise
            mock_http.post(
                "http://localhost:8080/api/devices",
                exception=ConnectionError("Connection refused"),
                repeat=True,
            )

            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                discover=True,
            )

            # Lab should still succeed, but device count is 9 (identified)
            assert result["devices_discovered"] == 9
            assert result["node_count"] == 10

    @pytest.mark.asyncio
    async def test_discover_with_backend_500(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """Backend returning 500 should be logged, not crash."""
        with aioresponses() as mock_http:
            mock_http.get(f"{base_url}/projects", payload=[])
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload, status=201)

            for node_payload in sample_node_payloads:
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes",
                    payload=node_payload,
                    status=201,
                )

            for _ in range(9):
                mock_http.post(
                    f"{base_url}/projects/{project_id}/links",
                    payload=link_payload,
                    status=201,
                )

            # Backend returns 500 for all registrations
            mock_http.post(
                "http://localhost:8080/api/devices",
                status=500,
                body="Server error",
                repeat=True,
            )

            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                discover=True,
            )

            # Devices were identified but registration failed; lab still succeeds
            assert result["devices_discovered"] == 9
