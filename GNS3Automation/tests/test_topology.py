"""Tests for topology builder and discovery."""
from __future__ import annotations

import pytest
from aioresponses import aioresponses

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config
from GNS3Automation.discovery import (
    detect_device_type,
    discover_devices_from_topology,
    gns3_node_to_device_info,
)
from GNS3Automation.models import GNS3Link, GNS3Node, GNS3Project, GNS3Template, make_link_endpoint
from GNS3Automation.templates import (
    alpine_node,
    docker_template,
    iot_sensor_node,
    mqtt_broker_node,
)
from GNS3Automation.topology import TopologyBuilder
from SmartHome.models import DeviceType


# ── Templates ────────────────────────────────────────────────────────────

class TestTemplates:
    def test_docker_template_defaults(self) -> None:
        t = docker_template("test", "alpine:latest")
        assert t["image"] == "alpine:latest"
        assert t["adapters"] == 1
        assert t["console_type"] == "telnet"

    def test_docker_template_with_env(self) -> None:
        t = docker_template("test", "python:3", extra_env={"FOO": "bar"})
        assert t["env"] == {"FOO": "bar"}

    def test_alpine_node(self) -> None:
        n = alpine_node("alpine-1")
        assert n["name"] == "alpine-1"
        assert n["node_type"] == "docker"

    def test_iot_sensor_node(self) -> None:
        n = iot_sensor_node("temp-1")
        assert n["name"] == "temp-1"
        assert n["properties"]["start_command"] == "python -m http.server 8080"

    def test_mqtt_broker_node(self) -> None:
        n = mqtt_broker_node()
        assert n["name"] == "mqtt-broker"
        assert n["properties"]["console_type"] == "none"


# ── Discovery ────────────────────────────────────────────────────────────

class TestDiscovery:
    def test_detect_light(self) -> None:
        assert detect_device_type("living-room-light") == DeviceType.LIGHT

    def test_detect_switch(self) -> None:
        assert detect_device_type("garage-switch") == DeviceType.SWITCH

    def test_detect_motion(self) -> None:
        assert detect_device_type("hallway-motion") == DeviceType.MOTION_SENSOR

    def test_detect_temperature(self) -> None:
        assert detect_device_type("outdoor-temp") == DeviceType.TEMPERATURE_SENSOR

    def test_detect_humidity(self) -> None:
        assert detect_device_type("basement-humidity") == DeviceType.HUMIDITY_SENSOR

    def test_detect_door(self) -> None:
        assert detect_device_type("front-door") == DeviceType.DOOR_SENSOR

    def test_detect_thermostat(self) -> None:
        assert detect_device_type("living-room-thermostat") == DeviceType.THERMOSTAT

    def test_detect_unknown_fallback(self) -> None:
        assert detect_device_type("weird-device-42") == DeviceType.SWITCH

    def test_gns3_node_to_device_info(self) -> None:
        node = GNS3Node(
            node_id="n1",
            project_id="p1",
            node_type="docker",
            name="living-light",
        )
        info = gns3_node_to_device_info(node)
        assert info.device_id == "n1"
        assert info.device_type == DeviceType.LIGHT
        assert info.properties.name == "living-light"
        assert info.properties.manufacturer == "GNS3"

    def test_discover_from_topology(self) -> None:
        nodes = [
            GNS3Node(node_id="n1", name="light-1", node_type="docker"),
            GNS3Node(node_id="n2", name="switch-1", node_type="docker"),
            GNS3Node(node_id="n3", name="temp-1", node_type="docker"),
        ]
        devices = discover_devices_from_topology(nodes)
        assert len(devices) == 3
        assert devices[0].device_type == DeviceType.LIGHT
        assert devices[1].device_type == DeviceType.SWITCH
        assert devices[2].device_type == DeviceType.TEMPERATURE_SENSOR


# ── Model helpers ────────────────────────────────────────────────────────

class TestModels:
    def test_make_link_endpoint(self) -> None:
        ep = make_link_endpoint("n1", port_number=1, adapter_number=0)
        assert ep["node_id"] == "n1"
        assert ep["port_number"] == 1
        assert ep["adapter_number"] == 0

    def test_gns3_node_from_api(self) -> None:
        data = {
            "node_id": "n1",
            "project_id": "p1",
            "name": "test-node",
            "node_type": "docker",
            "status": "stopped",
        }
        node = GNS3Node.from_api(data)
        assert node.node_id == "n1"
        assert node.status == "stopped"

    def test_gns3_link_from_api(self) -> None:
        data = {
            "link_id": "l1",
            "project_id": "p1",
            "nodes": [{"node_id": "n1"}, {"node_id": "n2"}],
        }
        link = GNS3Link.from_api(data)
        assert link.link_id == "l1"
        assert len(link.nodes) == 2

    def test_gns3_project_from_api(self) -> None:
        data = {
            "project_id": "p1",
            "name": "test-lab",
            "status": "opened",
        }
        project = GNS3Project.from_api(data)
        assert project.project_id == "p1"
        assert project.status == "opened"

    def test_gns3_template_from_api(self) -> None:
        data = {
            "template_id": "t1",
            "name": "alpine",
            "node_type": "docker",
        }
        template = GNS3Template.from_api(data)
        assert template.template_id == "t1"
        assert template.node_type == "docker"


# ── TopologyBuilder ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTopologyBuilder:
    async def test_add_node(self) -> None:
        config = GNS3Config(host="127.0.0.1")
        base_url = config.base_url
        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="p1")
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/nodes",
                    payload={
                        "node_id": "n1",
                        "name": "alpine-1",
                        "node_type": "docker",
                        "status": "stopped",
                    },
                    status=201,
                )
                node = await builder.add_node("alpine-1")
                assert node.node_id == "n1"
                assert node.name == "alpine-1"

    async def test_remove_node(self) -> None:
        config = GNS3Config(host="127.0.0.1")
        base_url = config.base_url
        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="p1")
            with aioresponses() as mocked:
                mocked.delete(f"{base_url}/projects/p1/nodes/n1", status=204)
                result = await builder.remove_node("n1")
                assert result is True

    async def test_add_link(self) -> None:
        config = GNS3Config(host="127.0.0.1")
        base_url = config.base_url
        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="p1")
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/links",
                    payload={
                        "link_id": "l1",
                        "nodes": [
                            {"node_id": "n1", "port_number": 0},
                            {"node_id": "n2", "port_number": 0},
                        ],
                    },
                    status=201,
                )
                link = await builder.add_link("n1", "n2")
                assert link.link_id == "l1"

    async def test_list_nodes(self) -> None:
        config = GNS3Config(host="127.0.0.1")
        base_url = config.base_url
        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="p1")
            with aioresponses() as mocked:
                mocked.get(
                    f"{base_url}/projects/p1/nodes",
                    payload=[{"node_id": "n1", "name": "alpine-1"}],
                )
                nodes = await builder.list_nodes()
                assert len(nodes) == 1
                assert nodes[0].node_id == "n1"

    async def test_start_node(self) -> None:
        config = GNS3Config(host="127.0.0.1")
        base_url = config.base_url
        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="p1")
            with aioresponses() as mocked:
                mocked.post(
                    f"{base_url}/projects/p1/nodes/n1/start",
                    payload={"node_id": "n1", "status": "started"},
                )
                await builder.start_node("n1")  # should not raise


# ═══════════════════════════════════════════════════════════════════════
# Real-server integration tests
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestTopologyBuilderReal:
    """Topology builder tests against a real GNS3 server."""

    async def test_add_and_remove_node_real(
        self, gns3_client: GNS3Client, test_project: tuple,
    ) -> None:
        """Add a Docker node, verify it, then remove it."""
        project, _ = test_project
        builder = TopologyBuilder(gns3_client, project.project_id)

        node = await builder.add_node(
            "test-real-node",
            node_type="docker",
            properties={"image": "alpine:latest"},
        )
        assert node.node_id
        assert node.name == "test-real-node"
        assert node.status == "stopped"

        # Verify it appears in the node list
        nodes = await builder.list_nodes()
        node_ids = {n.node_id for n in nodes}
        assert node.node_id in node_ids

        # Remove it
        removed = await builder.remove_node(node.node_id)
        assert removed is True

        # Verify it's gone
        nodes = await builder.list_nodes()
        node_ids = {n.node_id for n in nodes}
        assert node.node_id not in node_ids

    async def test_add_link_between_nodes_real(
        self, gns3_client: GNS3Client, test_project: tuple,
    ) -> None:
        """Create two nodes, link them, verify link exists."""
        project, _ = test_project
        builder = TopologyBuilder(gns3_client, project.project_id)

        node_a = await builder.add_node(
            "link-node-a",
            node_type="docker",
            properties={"image": "alpine:latest"},
        )
        node_b = await builder.add_node(
            "link-node-b",
            node_type="docker",
            properties={"image": "alpine:latest"},
        )

        try:
            link = await builder.add_link(node_a.node_id, node_b.node_id)
            assert link.link_id

            # Verify via list
            links = await builder.list_links()
            link_ids = {l.link_id for l in links}
            assert link.link_id in link_ids

            # Remove link
            removed = await builder.remove_link(link.link_id)
            assert removed is True
        finally:
            await builder.remove_node(node_a.node_id)
            await builder.remove_node(node_b.node_id)
