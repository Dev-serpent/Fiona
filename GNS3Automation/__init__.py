"""GNS3 Automated Testing Framework — REST API-driven network automation.

Provides async Python bindings for the GNS3 v2 REST API, including
project management, topology building, Docker template helpers, and
device discovery for the Fiona Smart Home platform.
"""
from __future__ import annotations

from GNS3Automation.client import GNS3Client
from GNS3Automation.config import GNS3Config, load_gns3_config
from GNS3Automation.discovery import (
    detect_device_type,
    discover_devices_from_topology,
    gns3_node_to_device_info,
)
from GNS3Automation.errors import (
    GNS3ConnectionError,
    GNS3Error,
    GNS3LinkError,
    GNS3NodeError,
    GNS3NotFoundError,
    GNS3ProjectError,
    GNS3TemplateError,
)
from GNS3Automation.models import (
    GNS3Link,
    GNS3Node,
    GNS3Project,
    GNS3Template,
    make_link_endpoint,
)
from GNS3Automation.project import ProjectManager
from GNS3Automation.templates import (
    alpine_node,
    docker_template,
    iot_sensor_node,
    mqtt_broker_node,
)
from GNS3Automation.topology import TopologyBuilder

__all__ = [
    "GNS3Client",
    "GNS3Config",
    "GNS3ConnectionError",
    "GNS3Error",
    "GNS3Link",
    "GNS3LinkError",
    "GNS3Node",
    "GNS3NodeError",
    "GNS3NotFoundError",
    "GNS3Project",
    "GNS3ProjectError",
    "GNS3Template",
    "GNS3TemplateError",
    "ProjectManager",
    "TopologyBuilder",
    "alpine_node",
    "detect_device_type",
    "discover_devices_from_topology",
    "docker_template",
    "gns3_node_to_device_info",
    "iot_sensor_node",
    "load_gns3_config",
    "make_link_endpoint",
    "mqtt_broker_node",
]
