"""Pre-defined GNS3 topology for the Fiona IoT Laboratory.

Defines the set of IoT simulation nodes, their positions, and the
connections between them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Lab constants ────────────────────────────────────────────────────────

FIONA_LAB_NAME = "Fiona IoT Lab"

# Docker images used in the lab
IMAGE_MOSQUITTO = "eclipse-mosquitto:2"
IMAGE_ALPINE = "alpine:latest"


# ── Topology node descriptors ────────────────────────────────────────────

@dataclass
class LabNode:
    """Describes a node in the sample topology."""

    name: str
    node_type: str = "docker"
    image: str = IMAGE_ALPINE
    template: str = ""
    x: float = 0.0
    y: float = 0.0
    start_command: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    console_type: str = "telnet"


# ── Pre-built topology ───────────────────────────────────────────────────

SAMPLE_TOPOLOGY: list[LabNode] = [
    # ── Network infrastructure ────────────────────────────────────────────
    LabNode(
        name="mqtt-broker",
        image=IMAGE_MOSQUITTO,
        x=300.0, y=50.0,
        console_type="none",
        properties={"adapters": 2},
    ),
    # ── IoT devices ───────────────────────────────────────────────────────
    LabNode(
        name="living-room-light",
        image=IMAGE_ALPINE,
        x=50.0, y=200.0,
        start_command="python3 /sim/light_sim.py --name living-room-light",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="bedroom-light",
        image=IMAGE_ALPINE,
        x=200.0, y=200.0,
        start_command="python3 /sim/light_sim.py --name bedroom-light",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="kitchen-switch",
        image=IMAGE_ALPINE,
        x=350.0, y=200.0,
        start_command="python3 /sim/switch_sim.py --name kitchen-switch",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="garage-plug",
        image=IMAGE_ALPINE,
        x=500.0, y=200.0,
        start_command="python3 /sim/switch_sim.py --name garage-plug --type plug",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="hallway-motion",
        image=IMAGE_ALPINE,
        x=50.0, y=350.0,
        start_command="python3 /sim/sensor_sim.py --name hallway-motion --type motion",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="outdoor-temp",
        image=IMAGE_ALPINE,
        x=200.0, y=350.0,
        start_command="python3 /sim/sensor_sim.py --name outdoor-temp --type temperature",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="basement-humidity",
        image=IMAGE_ALPINE,
        x=350.0, y=350.0,
        start_command="python3 /sim/sensor_sim.py --name basement-humidity --type humidity",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="front-door",
        image=IMAGE_ALPINE,
        x=500.0, y=350.0,
        start_command="python3 /sim/sensor_sim.py --name front-door --type door",
        properties={"adapters": 1, "console_auto_start": False},
    ),
    LabNode(
        name="living-room-thermostat",
        image=IMAGE_ALPINE,
        x=150.0, y=500.0,
        start_command="python3 /sim/sensor_sim.py --name living-room-thermostat --type thermostat",
        properties={"adapters": 1, "console_auto_start": False},
    ),
]


def build_lab_topology(
    mqtt_host: str = "mqtt-broker",
) -> list[dict[str, Any]]:
    """Build a GNS3 topology payload from the sample topology.

    Args:
        mqtt_host: The name of the MQTT broker node (for links).

    Returns:
        A list of node creation payloads suitable for
        :meth:`GNS3Automation.topology.TopologyBuilder.add_node`.
    """
    payloads: list[dict[str, Any]] = []
    for node in SAMPLE_TOPOLOGY:
        props = dict(node.properties)
        props["image"] = node.image
        if node.start_command:
            props["start_command"] = node.start_command
        if node.console_type:
            props["console_type"] = node.console_type

        payloads.append({
            "name": node.name,
            "node_type": node.node_type,
            "x": node.x,
            "y": node.y,
            "properties": props,
        })

    return payloads
