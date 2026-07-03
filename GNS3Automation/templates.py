"""Docker template helpers for GNS3.

Provides pre-built Docker node template configurations for common IoT
devices that can be spawned inside a GNS3 topology.
"""
from __future__ import annotations

from typing import Any


# ── Docker image constants ──────────────────────────────────────────────

IMAGE_ALPINE = "alpine:latest"
IMAGE_PYTHON = "python:3.11-slim"
IMAGE_MOSQUITTO = "eclipse-mosquitto:2"
IMAGE_NODE = "node:20-alpine"
IMAGE_NGINX = "nginx:alpine"


# ── Template builders ───────────────────────────────────────────────────

def docker_template(
    name: str,
    image: str,
    console_type: str = "telnet",
    extra_volumes: list[dict[str, str]] | None = None,
    extra_env: dict[str, str] | None = None,
    start_command: str = "",
    adapters: int = 1,
) -> dict[str, Any]:
    """Create a Docker node template payload for GNS3.

    Args:
        name: Template name.
        image: Docker image (e.g. ``"alpine:latest"``).
        console_type: Console type (``"telnet"``, ``"vnc"``, ``"none"``).
        extra_volumes: Additional volume binds.
        extra_env: Additional environment variables.
        start_command: Command to run on container start.
        adapters: Number of network adapters.

    Returns:
        A dictionary suitable for use as a GNS3 node ``properties`` or
        as a template definition.
    """
    props: dict[str, Any] = {
        "image": image,
        "adapters": adapters,
        "console_type": console_type,
    }
    if extra_volumes:
        props["volumes"] = extra_volumes
    if extra_env:
        props["env"] = extra_env
    if start_command:
        props["start_command"] = start_command
    return props


def alpine_node(name: str, **kwargs: Any) -> dict[str, Any]:
    """Create a generic Alpine Linux node."""
    return {
        "name": name,
        "node_type": "docker",
        "properties": docker_template(name, IMAGE_ALPINE, **kwargs),
    }


def iot_sensor_node(name: str, **kwargs: Any) -> dict[str, Any]:
    """Create an IoT sensor node (Python-based)."""
    return {
        "name": name,
        "node_type": "docker",
        "properties": docker_template(
            name,
            IMAGE_PYTHON,
            start_command="python -m http.server 8080",
            **kwargs,
        ),
    }


def mqtt_broker_node(name: str = "mqtt-broker", **kwargs: Any) -> dict[str, Any]:
    """Create an MQTT broker node using Eclipse Mosquitto."""
    return {
        "name": name,
        "node_type": "docker",
        "properties": docker_template(
            name,
            IMAGE_MOSQUITTO,
            console_type="none",
            **kwargs,
        ),
    }
