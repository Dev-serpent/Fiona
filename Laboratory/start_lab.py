"""One-command launcher for the Fiona IoT Laboratory.

Creates a GNS3 project, deploys simulated IoT devices, connects them to
the MQTT broker, and optionally seeds the HomeBackend device registry.

Usage:
    python -m Laboratory --gns3-host <host> --gns3-port <port> [--auto-start]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config
from GNS3Automation.errors import GNS3Error
from GNS3Automation.project import ProjectManager
from GNS3Automation.topology import TopologyBuilder

from Laboratory.topology import FIONA_LAB_NAME, build_lab_topology

logger = logging.getLogger(__name__)


async def discover_devices(
    topology: list[dict[str, Any]],
    api_url: str,
) -> list[dict[str, Any]]:
    """Register topology devices with the HomeBackend REST API.

    Args:
        topology: List of node payload dicts (from ``build_lab_topology``).
        api_url: Base URL of the HomeBackend service (e.g. ``http://localhost:8080``).

    Returns:
        List of device info dicts that were sent.
    """
    import aiohttp

    device_map = []
    for node in topology:
        name: str = node.get("name", "")
        dev_type = _infer_device_type(name, node)
        if dev_type is None:
            continue
        device_map.append({
            "device_id": name.replace("_", "-"),
            "name": name,
            "device_type": dev_type,
            "room": _infer_room(name),
            "metadata": {
                "gns3_node": name,
                "mqtt_host": "mqtt-broker",
                "simulated": True,
            },
        })

    backend_url = api_url.rstrip("/")
    async with aiohttp.ClientSession() as session:
        logger.info("Registering %d devices with HomeBackend at %s",
                     len(device_map), backend_url)
        for dev in device_map:
            try:
                async with session.post(
                    f"{backend_url}/api/devices",
                    json=dev,
                ) as resp:
                    if resp.status in (200, 201):
                        logger.info("  Registered %s (%s)",
                                     dev["device_id"], dev["device_type"])
                    else:
                        body = await resp.text()
                        logger.warning("  Failed to register %s: %s %s",
                                       dev["device_id"], resp.status, body)
            except (aiohttp.ClientError, ConnectionError, OSError) as exc:
                logger.error("  Connection error registering %s: %s",
                             dev["device_id"], exc)

    return device_map


def _infer_device_type(name: str, node: dict) -> str | None:
    """Map a node name to a SmartHome device type string."""
    name_lower = name.lower()
    if "light" in name_lower:
        return "light"
    if "switch" in name_lower:
        return "switch"
    if "plug" in name_lower:
        return "plug"
    if "motion" in name_lower:
        return "motion_sensor"
    if "temp" in name_lower or "temperature" in name_lower:
        return "temperature_sensor"
    if "humidity" in name_lower:
        return "humidity_sensor"
    if "door" in name_lower:
        return "door_sensor"
    if "thermostat" in name_lower:
        return "thermostat"
    if "broker" in name_lower or "mqtt" in name_lower:
        return None  # Infrastructure node
    return None


def _infer_room(name: str) -> str:
    """Infer the room label from a node name."""
    known_rooms = [
        "living-room", "bedroom", "kitchen", "garage",
        "hallway", "outdoor", "basement", "front",
        "bathroom", "office", "dining",
    ]
    name_lower = name.lower().replace("_", "-")
    for room in known_rooms:
        if room in name_lower:
            return room.replace("-", " ").title()
    return "Unknown"


async def start_lab(
    gns3_host: str = "127.0.0.1",
    gns3_port: int = 3080,
    auto_start: bool = False,
    discover: bool = False,
) -> dict[str, Any]:
    """Create and start the Fiona IoT Laboratory in GNS3.

    Args:
        gns3_host: GNS3 server hostname.
        gns3_port: GNS3 server port.
        auto_start: If True, start all nodes after creation.
        discover: If True, register devices with HomeBackend API.

    Returns:
        A summary dict with ``project_id``, ``project_name``,
        ``node_count``, ``auto_started``, ``devices_discovered``.

    Raises:
        GNS3Error: If any GNS3 API operation fails.
    """
    config = GNS3Config(host=gns3_host, port=gns3_port, protocol="http")
    logger.info("Connecting to GNS3 server at %s", config.base_url)

    async with GNS3Client(config) as client:
        project_mgr = ProjectManager(client)

        # ── Step 1: Create or reuse the Fiona lab project ──────────────
        try:
            existing = await project_mgr.list()
            lab = None
            for proj in existing:
                if proj.name == FIONA_LAB_NAME:
                    lab = proj
                    logger.info("Found existing project '%s' (%s)",
                                 FIONA_LAB_NAME, lab.project_id)
                    break

            if lab is None:
                lab = await project_mgr.create(name=FIONA_LAB_NAME)
                logger.info("Created project '%s' (%s)",
                             FIONA_LAB_NAME, lab.project_id)
        except GNS3Error as exc:
            logger.error("Failed to create project: %s", exc)
            raise

        # ── Step 2: Build topology (add nodes one by one) ─────────────
        topology_payloads = build_lab_topology()
        topology_builder = TopologyBuilder(client, project_id=lab.project_id)

        nodes = []
        for payload in topology_payloads:
            try:
                node = await topology_builder.add_node(**payload)
                nodes.append(node)
                logger.info("  Added node: %s", node.name)
            except GNS3Error as exc:
                logger.warning("  Failed to add node %s: %s",
                               payload.get("name", "?"), exc)

        if not nodes:
            logger.warning("No nodes were added; listing existing nodes")
            nodes = await topology_builder.list_nodes()

        # ── Step 3: Create links (all device nodes → MQTT broker) ─────
        broker_node_id: str | None = None
        other_nodes: list[Any] = []

        for node in nodes:
            name_lower = node.name.lower() if hasattr(node, "name") else ""
            node_id = node.node_id if hasattr(node, "node_id") else ""
            if "broker" in name_lower or "mqtt" in name_lower:
                broker_node_id = node_id
            else:
                other_nodes.append(node)

        if broker_node_id and other_nodes:
            linked = 0
            for node in other_nodes:
                node_id = node.node_id if hasattr(node, "node_id") else ""
                if node_id:
                    try:
                        await topology_builder.add_link(
                            node_a_id=broker_node_id,
                            node_b_id=node_id,
                        )
                        linked += 1
                    except GNS3Error as exc:
                        logger.warning("  Link %s → %s: %s",
                                       broker_node_id, node_id, exc)
            logger.info("Created %d network links", linked)
        else:
            logger.warning("Could not identify broker node; "
                           "skipping link creation")

        # ── Step 4: Start nodes (optional) ─────────────────────────────
        if auto_start:
            started = 0
            for node in nodes:
                node_id = node.node_id if hasattr(node, "node_id") else ""
                if node_id:
                    try:
                        await topology_builder.start_node(node_id)
                        started += 1
                    except GNS3Error as exc:
                        logger.warning("  Could not start node: %s", exc)
            logger.info("Started %d nodes", started)

        # ── Step 5: Discover devices (optional) ────────────────────────
        discovered: list[dict[str, Any]] = []
        if discover:
            discovered = await discover_devices(
                topology_payloads,
                api_url="http://localhost:8080",
            )
            logger.info("Discovered %d devices", len(discovered))

        summary = {
            "project_id": lab.project_id,
            "project_name": FIONA_LAB_NAME,
            "node_count": len(nodes),
            "auto_started": auto_start,
            "devices_discovered": len(discovered),
        }
        logger.info("Lab setup complete: %s", json.dumps(summary, indent=2))
        return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Fiona IoT Laboratory \u2014 GNS3 lab launcher",
    )
    parser.add_argument(
        "--gns3-host", default="127.0.0.1",
        help="GNS3 server hostname (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--gns3-port", type=int, default=3080,
        help="GNS3 server port (default: 3080)",
    )
    parser.add_argument(
        "--auto-start", action="store_true",
        help="Start all nodes after creating the topology",
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Register devices with the HomeBackend API",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the laboratory launcher CLI."""
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        summary = asyncio.run(
            start_lab(
                gns3_host=args.gns3_host,
                gns3_port=args.gns3_port,
                auto_start=args.auto_start,
                discover=args.discover,
            ),
        )
        print(f"\n\u2705 Lab '{summary['project_name']}' ready!")
        print(f"   Project ID: {summary['project_id']}")
        print(f"   Nodes:      {summary['node_count']}")
        print(f"   Auto-start: {summary['auto_started']}")
        if summary["devices_discovered"]:
            print(f"   Discovered: {summary['devices_discovered']} devices")
        return 0
    except (GNS3Error, ConnectionError, TimeoutError) as exc:
        logger.error("Lab setup failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130


if __name__ == "__main__":
    sys.exit(main())
