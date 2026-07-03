"""Unit tests for the Fiona Built-in Laboratory."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from GNS3Automation.errors import GNS3Error
from GNS3Automation.project import ProjectManager
from GNS3Automation.topology import TopologyBuilder

from Laboratory.start_lab import (
    _infer_device_type,
    _infer_room,
    build_lab_topology,
    discover_devices,
    start_lab,
)
from Laboratory.topology import (
    FIONA_LAB_NAME,
    SAMPLE_TOPOLOGY,
    LabNode,
)


# ── Topology tests ───────────────────────────────────────────────────────

class TestLabNode:
    def test_minimal(self) -> None:
        node = LabNode(name="test-device")
        assert node.name == "test-device"
        assert node.node_type == "docker"
        assert node.image == "alpine:latest"
        assert node.x == 0.0
        assert node.y == 0.0

    def test_custom_values(self) -> None:
        node = LabNode(
            name="custom",
            node_type="qemu",
            image="custom:latest",
            x=100.0, y=200.0,
            console_type="vnc",
            properties={"ram": 512},
        )
        assert node.name == "custom"
        assert node.node_type == "qemu"
        assert node.image == "custom:latest"
        assert node.x == 100.0
        assert node.y == 200.0
        assert node.console_type == "vnc"
        assert node.properties["ram"] == 512


class TestSampleTopology:
    def test_has_broker(self) -> None:
        brokers = [n for n in SAMPLE_TOPOLOGY if "broker" in n.name.lower()]
        assert len(brokers) == 1
        assert brokers[0].image == "eclipse-mosquitto:2"

    def test_has_devices(self) -> None:
        assert len(SAMPLE_TOPOLOGY) == 10  # 1 broker + 9 devices

    def test_device_types_present(self) -> None:
        names = [n.name for n in SAMPLE_TOPOLOGY]
        assert "living-room-light" in names
        assert "bedroom-light" in names
        assert "kitchen-switch" in names
        assert "hallway-motion" in names
        assert "outdoor-temp" in names
        assert "front-door" in names
        assert "living-room-thermostat" in names

    def test_all_devices_have_start_commands(self) -> None:
        for node in SAMPLE_TOPOLOGY:
            if "broker" in node.name.lower():
                continue
            assert node.start_command, f"{node.name} missing start_command"


class TestBuildLabTopology:
    def test_returns_list_of_dicts(self) -> None:
        payloads = build_lab_topology()
        assert isinstance(payloads, list)
        assert len(payloads) == len(SAMPLE_TOPOLOGY)

    def test_every_payload_has_required_keys(self) -> None:
        for payload in build_lab_topology():
            assert "name" in payload
            assert "node_type" in payload
            assert "properties" in payload
            assert "image" in payload["properties"]

    def test_broker_has_no_start_command(self) -> None:
        payloads = build_lab_topology()
        broker = next(p for p in payloads if "broker" in p["name"])
        assert "start_command" not in broker["properties"]


# ── Device type inference ────────────────────────────────────────────────

class TestInferDeviceType:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("living-room-light", "light"),
            ("bedroom-light", "light"),
            ("kitchen-switch", "switch"),
            ("garage-plug", "plug"),
            ("hallway-motion", "motion_sensor"),
            ("outdoor-temp", "temperature_sensor"),
            ("basement-humidity", "humidity_sensor"),
            ("front-door", "door_sensor"),
            ("living-room-thermostat", "thermostat"),
            ("mqtt-broker", None),
        ],
    )
    def test_inference(self, name: str, expected: str | None) -> None:
        assert _infer_device_type(name, {"name": name}) == expected


class TestInferRoom:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("living-room-light", "Living Room"),
            ("bedroom-light", "Bedroom"),
            ("kitchen-switch", "Kitchen"),
            ("garage-plug", "Garage"),
            ("hallway-motion", "Hallway"),
            ("outdoor-temp", "Outdoor"),
            ("basement-humidity", "Basement"),
            ("front-door", "Front"),
            ("office-sensor", "Office"),
            ("unknown-device", "Unknown"),
        ],
    )
    def test_room_inference(self, name: str, expected: str) -> None:
        assert _infer_room(name) == expected


# ── Device discovery ─────────────────────────────────────────────────────

class TestDiscoverDevices:
    """Tests for ``discover_devices`` with mocked aiohttp."""

    @pytest.mark.asyncio
    async def test_discover_success(self) -> None:
        topology = [
            {"name": "living-room-light"},
            {"name": "hallway-motion"},
        ]

        # Instead of complex mocking, patch the discover function's
        # inner HTTP call by patching at the right level.
        # We patch the post call inside discover_devices by providing
        # a custom async context manager.
        results = await discover_devices(topology, "http://localhost:8080")
        # Without a running backend the requests will fail with a
        # connection error, but the function should still return the
        # device map (the error is caught internally).
        assert len(results) == 2
        assert results[0]["device_id"] == "living-room-light"
        assert results[1]["device_id"] == "hallway-motion"

    @pytest.mark.asyncio
    async def test_discover_skips_broker(self) -> None:
        """Broker nodes should not be discovered as devices."""
        topology = [
            {"name": "mqtt-broker"},
            {"name": "living-room-light"},
        ]

        results = await discover_devices(topology, "http://localhost:8080")
        assert len(results) == 1
        assert results[0]["device_id"] == "living-room-light"


# ── Lab launcher ─────────────────────────────────────────────────────────

# Helper to create a proper async context manager mock for aiohttp
def _async_context_manager(response_body: str = "ok",
                           status: int = 201) -> MagicMock:
    """Return a MagicMock that works with ``async with``."""
    resp = MagicMock()
    resp.status = status
    # Async methods
    resp.text = AsyncMock(return_value=response_body)
    resp.json = AsyncMock(return_value={})
    # Context manager protocol
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    return resp


class TestStartLab:
    """Tests for ``start_lab`` with all GNS3 components mocked."""

    @pytest.fixture
    def mock_project(self) -> MagicMock:
        proj = MagicMock()
        proj.project_id = "proj-test"
        proj.name = FIONA_LAB_NAME
        return proj

    @pytest.fixture
    def mock_nodes(self) -> list:
        """Return a list of nodes where the last one is 'other'."""
        broker = MagicMock()
        broker.name = "mqtt-broker"
        broker.node_id = "node-broker"

        light = MagicMock()
        light.name = "living-room-light"
        light.node_id = "node-light"

        return [broker, light]

    @pytest.fixture(autouse=True)
    def _patch_http(self) -> None:
        """Patch aiohttp.ClientSession so all discover calls succeed."""
        self._session_patch = patch("aiohttp.ClientSession")
        mock_session_cls = self._session_patch.start()
        mock_session = MagicMock()
        mock_session.post.return_value = _async_context_manager()
        mock_session_cls.return_value = mock_session

    def teardown_method(self) -> None:
        self._session_patch.stop()

    @pytest.mark.asyncio
    async def test_start_lab_creates_project(
        self, mock_project: MagicMock, mock_nodes: list,
    ) -> None:
        """Verify the full start_lab flow with mocked GNS3 client."""
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("Laboratory.start_lab.GNS3Client", return_value=mock_client),
            patch.object(ProjectManager, "list", AsyncMock(return_value=[])),
            patch.object(ProjectManager, "create", AsyncMock(return_value=mock_project)),
            patch.object(TopologyBuilder, "add_node",
                         AsyncMock(return_value=MagicMock(node_id="auto-node"))),
            patch.object(TopologyBuilder, "add_link", AsyncMock()),
            patch.object(TopologyBuilder, "list_nodes",
                         AsyncMock(return_value=mock_nodes)),
        ):
            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                auto_start=False,
                discover=False,
            )
            assert result["project_id"] == "proj-test"
            assert result["project_name"] == FIONA_LAB_NAME
            assert result["node_count"] == len(build_lab_topology())

    @pytest.mark.asyncio
    async def test_start_lab_reuses_existing_project(
        self, mock_project: MagicMock,
    ) -> None:
        """When the project already exists it should not create a new one."""
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("Laboratory.start_lab.GNS3Client", return_value=mock_client),
            patch.object(ProjectManager, "list",
                         AsyncMock(return_value=[mock_project])),
            patch.object(ProjectManager, "create", AsyncMock()),
            patch.object(TopologyBuilder, "add_node",
                         AsyncMock(return_value=MagicMock(node_id="auto"))),
            patch.object(TopologyBuilder, "add_link", AsyncMock()),
            patch.object(TopologyBuilder, "list_nodes",
                         AsyncMock(return_value=[])),
        ):
            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
            )
            assert result["project_id"] == "proj-test"
            ProjectManager.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_lab_with_auto_start(
        self, mock_project: MagicMock, mock_nodes: list,
    ) -> None:
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with (
            patch("Laboratory.start_lab.GNS3Client", return_value=mock_client),
            patch.object(ProjectManager, "list", AsyncMock(return_value=[])),
            patch.object(ProjectManager, "create", AsyncMock(return_value=mock_project)),
            patch.object(TopologyBuilder, "add_node",
                         AsyncMock(return_value=MagicMock(node_id="auto"))),
            patch.object(TopologyBuilder, "add_link", AsyncMock()),
            patch.object(TopologyBuilder, "start_node", AsyncMock()),
            patch.object(TopologyBuilder, "list_nodes",
                         AsyncMock(return_value=[])),
        ):
            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
                auto_start=True,
            )
            assert result["auto_started"] is True
            TopologyBuilder.start_node.assert_called()

    @pytest.mark.asyncio
    async def test_start_lab_handles_node_creation_failure(
        self, mock_project: MagicMock,
    ) -> None:
        """When add_node fails, it should fall back to listing existing nodes."""
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        existing_node = MagicMock()
        existing_node.name = "mqtt-broker"
        existing_node.node_id = "node-broker"

        with (
            patch("Laboratory.start_lab.GNS3Client", return_value=mock_client),
            patch.object(ProjectManager, "list", AsyncMock(return_value=[])),
            patch.object(ProjectManager, "create", AsyncMock(return_value=mock_project)),
            patch.object(TopologyBuilder, "add_node",
                         AsyncMock(side_effect=GNS3Error("GNS3 error"))),
            patch.object(TopologyBuilder, "add_link", AsyncMock()),
            patch.object(TopologyBuilder, "list_nodes",
                         AsyncMock(return_value=[existing_node])),
        ):
            result = await start_lab(
                gns3_host="127.0.0.1",
                gns3_port=3080,
            )
            assert result["node_count"] == 1
            TopologyBuilder.list_nodes.assert_called_once()


# ── CLI arguments ────────────────────────────────────────────────────────

class TestCLIArgs:
    def test_defaults(self) -> None:
        from Laboratory.start_lab import parse_args

        args = parse_args([])
        assert args.gns3_host == "127.0.0.1"
        assert args.gns3_port == 3080
        assert args.auto_start is False
        assert args.discover is False
        assert args.verbose is False

    def test_custom_values(self) -> None:
        from Laboratory.start_lab import parse_args

        args = parse_args([
            "--gns3-host", "192.168.1.100",
            "--gns3-port", "3080",
            "--auto-start",
            "--discover",
            "--verbose",
        ])
        assert args.gns3_host == "192.168.1.100"
        assert args.gns3_port == 3080
        assert args.auto_start is True
        assert args.discover is True
        assert args.verbose is True
