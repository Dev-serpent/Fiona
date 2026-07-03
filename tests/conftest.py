"""Shared fixtures for integration tests.

Provides pre-configured GNS3 API mocks via ``aioresponses`` so that
cross-package workflows can be tested without a live GNS3 server.
"""
from __future__ import annotations

from typing import Any

import pytest

from GNS3Automation.config import GNS3Config

PROJECT_ID = "proj-integration-test"


@pytest.fixture
def gns3_config() -> GNS3Config:
    """GNS3 config pointing at a local server (mocked in tests)."""
    return GNS3Config(host="127.0.0.1", port=3080, protocol="http")


@pytest.fixture
def base_url(gns3_config: GNS3Config) -> str:
    return gns3_config.base_url


@pytest.fixture
def project_id() -> str:
    return PROJECT_ID


@pytest.fixture
def project_payload(project_id: str) -> dict[str, Any]:
    """Standard payload returned by the GNS3 API when creating/listing a project."""
    return {
        "project_id": project_id,
        "name": "Fiona IoT Lab",
        "auto_start": False,
        "auto_close": True,
        "status": "opened",
        "path": "/tmp/gns3/projects/fiona-lab",
    }


@pytest.fixture
def sample_node_payloads() -> list[dict[str, Any]]:
    """Return a list of 10 node payloads as GNS3 API would return them."""
    return [
        {
            "node_id": f"node-{i:03d}",
            "name": name,
            "node_type": "docker",
            "status": "started",
            "console": None,
            "console_type": "telnet",
            "project_id": PROJECT_ID,
            "compute_id": "local",
        }
        for i, name in enumerate([
            "mqtt-broker",
            "living-room-light",
            "bedroom-light",
            "kitchen-switch",
            "garage-plug",
            "hallway-motion",
            "outdoor-temp",
            "basement-humidity",
            "front-door",
            "living-room-thermostat",
        ])
    ]


@pytest.fixture
def link_payload() -> dict[str, Any]:
    """Standard payload returned when creating a link."""
    return {
        "link_id": "link-001",
        "nodes": [
            {"node_id": "node-000", "adapter_number": 0, "port_number": 0},
            {"node_id": "node-001", "adapter_number": 0, "port_number": 0},
        ],
        "project_id": PROJECT_ID,
    }
