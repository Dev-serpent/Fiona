"""Device discovery — extract IoT device information from GNS3 topologies.

Provides utilities that map GNS3 nodes to SmartHome :class:`DeviceInfo`
objects so that a GNS3 lab topology can be automatically populated in
the :class:`DeviceRegistry`.
"""
from __future__ import annotations

import logging
from typing import Any

from GNS3Automation.models import GNS3Node
from SmartHome.models import DeviceInfo, DeviceProperties, DeviceType

logger = logging.getLogger(__name__)

# Mapping from GNS3 node name patterns to SmartHome DeviceType.
# The keys are matched as substrings (case-insensitive) against node names.
_NAME_PATTERNS: list[tuple[str, DeviceType]] = [
    ("light", DeviceType.LIGHT),
    ("lamp", DeviceType.LIGHT),
    ("bulb", DeviceType.LIGHT),
    ("switch", DeviceType.SWITCH),
    ("plug", DeviceType.PLUG),
    ("outlet", DeviceType.PLUG),
    ("motion", DeviceType.MOTION_SENSOR),
    ("pir", DeviceType.MOTION_SENSOR),
    ("temp", DeviceType.TEMPERATURE_SENSOR),
    ("thermometer", DeviceType.TEMPERATURE_SENSOR),
    ("humidity", DeviceType.HUMIDITY_SENSOR),
    ("door", DeviceType.DOOR_SENSOR),
    ("window", DeviceType.DOOR_SENSOR),
    ("contact", DeviceType.DOOR_SENSOR),
    ("thermostat", DeviceType.THERMOSTAT),
    ("hvac", DeviceType.THERMOSTAT),
]


def detect_device_type(node_name: str) -> DeviceType:
    """Infer a :class:`DeviceType` from a GNS3 node name.

    Matches known substrings.  Falls back to :attr:`DeviceType.SWITCH`.
    """
    lower = node_name.lower()
    for pattern, dtype in _NAME_PATTERNS:
        if pattern in lower:
            return dtype
    return DeviceType.SWITCH


def gns3_node_to_device_info(node: GNS3Node) -> DeviceInfo:
    """Convert a :class:`GNS3Node` to a :class:`DeviceInfo`.

    The resulting ``device_id`` is derived from the GNS3 ``node_id``.
    """
    dtype = detect_device_type(node.name)
    return DeviceInfo(
        device_id=node.node_id,
        device_type=dtype,
        properties=DeviceProperties(
            name=node.name,
            location=f"gns3://{node.project_id}/{node.node_id}",
            manufacturer="GNS3",
            model=node.node_type,
            firmware_version="simulated",
        ),
    )


def discover_devices_from_topology(
    nodes: list[GNS3Node],
) -> list[DeviceInfo]:
    """Convert an entire GNS3 node list into SmartHome :class:`DeviceInfo` objects.

    Args:
        nodes: List of :class:`GNS3Node` instances from a project.

    Returns:
        A list of :class:`DeviceInfo` objects suitable for registration
        with a :class:`DeviceRegistry`.
    """
    return [gns3_node_to_device_info(n) for n in nodes]
