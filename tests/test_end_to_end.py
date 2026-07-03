"""End-to-end integration tests for the full Fiona lab workflow.

Tests the complete flow from GNS3 project creation through node/link
management to device discovery, using HTTP-level mocking via
``aioresponses``.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from aioresponses import aioresponses

from Laboratory.start_lab import start_lab
from Laboratory.topology import FIONA_LAB_NAME, build_lab_topology


class TestFullLabWorkflow:
    """Validates the complete GNS3 lab creation lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lab_creation(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """Happy path: create a new project, add 10 nodes, wire 9 links."""
        with aioresponses() as mock_http:
            # ── Step 1: List projects (empty → new project) ──────────
            mock_http.get(f"{base_url}/projects", payload=[])

            # ── Step 2: Create project ──────────────────────────────
            mock_http.post(f"{base_url}/projects",
                           payload=project_payload,
                           status=201)

            # ── Step 3: Add 10 nodes ─────────────────────────────────
            # Each add_node() call does POST /projects/{id}/nodes
            for node_payload in sample_node_payloads:
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes",
                    payload=node_payload,
                    status=201,
                )

            # ── Step 4: Create 9 links (all devices → broker) ───────
            for _ in range(9):
                mock_http.post(
                    f"{base_url}/projects/{project_id}/links",
                    payload=link_payload,
                    status=201,
                )

            # ── Execute ─────────────────────────────────────────────
            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                auto_start=False,
                discover=False,
            )

            # ── Assertions ──────────────────────────────────────────
            assert result["project_id"] == project_id
            assert result["project_name"] == FIONA_LAB_NAME
            assert result["node_count"] == len(sample_node_payloads)
            assert result["auto_started"] is False
            assert result["devices_discovered"] == 0

    @pytest.mark.asyncio
    async def test_existing_project_is_reused(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """When the project already exists, reuse it without re-creating."""
        with aioresponses() as mock_http:
            # ── Step 1: List projects (returns existing) ────────────
            mock_http.get(f"{base_url}/projects",
                          payload=[project_payload])

            # ── Step 2: Never called (project exists) ──────────────
            # Deliberately NOT mocking POST /projects — test should
            # not hit it.

            # ── Step 3: Add 10 nodes ─────────────────────────────────
            for node_payload in sample_node_payloads:
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes",
                    payload=node_payload,
                    status=201,
                )

            # ── Step 4: Create 9 links ───────────────────────────────
            for _ in range(9):
                mock_http.post(
                    f"{base_url}/projects/{project_id}/links",
                    payload=link_payload,
                    status=201,
                )

            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
            )

            assert result["project_id"] == project_id
            assert result["node_count"] == len(sample_node_payloads)

    @pytest.mark.asyncio
    async def test_auto_start_starts_all_nodes(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """With ``--auto-start``, every node should receive a start command."""
        node_count = len(sample_node_payloads)

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
                # Each node will be started
                mock_http.post(
                    f"{base_url}/projects/{project_id}/nodes/"
                    f"{node_payload['node_id']}/start",
                    payload=None,
                    status=204,
                )

            for _ in range(9):
                mock_http.post(
                    f"{base_url}/projects/{project_id}/links",
                    payload=link_payload,
                    status=201,
                )

            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                auto_start=True,
            )

            assert result["auto_started"] is True
            assert result["node_count"] == node_count

    @pytest.mark.asyncio
    async def test_lab_with_device_discovery(
        self,
        base_url: str,
        project_id: str,
        project_payload: dict[str, Any],
        sample_node_payloads: list[dict[str, Any]],
        link_payload: dict[str, Any],
    ) -> None:
        """With ``--discover``, devices should be registered with HomeBackend."""
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

            # Mock the HomeBackend API for device registration
            # (9 devices — broker is infrastructure, not registered)
            for _ in range(9):
                mock_http.post(
                    "http://localhost:8080/api/devices",
                    payload={},
                    status=201,
                )

            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                discover=True,
            )

            assert result["devices_discovered"] == 9
            assert result["node_count"] == 10


class TestCrossPackageContracts:
    """Verify contracts between SmartHome, GNS3Automation, and Laboratory."""

    def test_build_lab_topology_infers_known_devices(self) -> None:
        """Every node in the sample topology should map to a known device type.

        This validates the contract between ``Laboratory.topology`` and
        the device type inference in ``start_lab.py``.
        """
        from Laboratory.start_lab import _infer_device_type

        payloads = build_lab_topology()
        device_count = 0
        for p in payloads:
            dtype = _infer_device_type(p["name"], p)
            if dtype is not None:
                device_count += 1
            elif "broker" in p["name"].lower():
                pass  # expected
            else:
                pytest.fail(f"Node {p['name']} did not map to a device type")

        # 9 devices, 1 broker
        assert device_count == 9

    def test_gns3_discovery_to_smarthome_device_types(self) -> None:
        """GNS3-discovered device types should match SmartHome DeviceType enum.

        This validates the contract between ``GNS3Automation.discovery``
        and ``SmartHome.models.DeviceType``.
        """
        from SmartHome.models import DeviceType
        from GNS3Automation.discovery import detect_device_type

        # Map of GNS3-detected strings → DeviceType members
        type_map = {
            "light": DeviceType.LIGHT,
            "switch": DeviceType.SWITCH,
            "plug": DeviceType.PLUG,
            "motion_sensor": DeviceType.MOTION_SENSOR,
            "temperature_sensor": DeviceType.TEMPERATURE_SENSOR,
            "humidity_sensor": DeviceType.HUMIDITY_SENSOR,
            "door_sensor": DeviceType.DOOR_SENSOR,
            "thermostat": DeviceType.THERMOSTAT,
        }

        for type_str, expected_enum in type_map.items():
            detected = detect_device_type(type_str)
            assert detected == expected_enum, (
                f"Type '{type_str}' mapped to {detected}, expected {expected_enum}"
            )
