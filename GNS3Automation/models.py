"""Data models for GNS3 resources."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid4().hex


# ── Project ──────────────────────────────────────────────────────────────


@dataclass
class GNS3Project:
    """Represents a GNS3 project."""

    project_id: str = ""
    name: str = "fiona-lab"
    project_type: str = "default"
    path: str = ""
    status: str = "closed"  # closed | opened
    created_at: str = field(default_factory=_now)
    auto_start: bool = False
    auto_close: bool = True
    variables: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GNS3Project:
        """Create from a GNS3 v2 API response dict."""
        return cls(
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
            project_type=data.get("project_type", "default"),
            path=data.get("path", ""),
            status=data.get("status", "closed"),
            created_at=data.get("created_at", _now()),
            auto_start=data.get("auto_start", False),
            auto_close=data.get("auto_close", True),
            variables=data.get("variables", {}),
        )


# ── Node ─────────────────────────────────────────────────────────────────


@dataclass
class GNS3Node:
    """Represents a node in a GNS3 topology."""

    node_id: str = ""
    project_id: str = ""
    name: str = "node"
    node_type: str = "docker"  # docker | qemu | vpcs | hub | ...
    template: str = ""
    compute_id: str = "local"
    console: Optional[int] = None
    console_type: str = "telnet"
    status: str = "stopped"
    properties: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    width: float = 80.0
    height: float = 80.0
    symbol: str = ":/symbols/docker_guest.svg"
    port_name_format: str = "eth{port}"
    port_segment_size: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GNS3Node:
        """Create from a GNS3 v2 API response dict."""
        return cls(
            node_id=data.get("node_id", ""),
            project_id=data.get("project_id", ""),
            name=data.get("name", "node"),
            node_type=data.get("node_type", "docker"),
            template=data.get("template", ""),
            compute_id=data.get("compute_id", "local"),
            console=data.get("console"),
            console_type=data.get("console_type", "telnet"),
            status=data.get("status", "stopped"),
            properties=data.get("properties", {}),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
            width=data.get("width", 80.0),
            height=data.get("height", 80.0),
            symbol=data.get("symbol", ":/symbols/docker_guest.svg"),
            port_name_format=data.get("port_name_format", "eth{port}"),
            port_segment_size=data.get("port_segment_size", 0),
        )


# ── Link ─────────────────────────────────────────────────────────────────


@dataclass
class GNS3Link:
    """Represents a link between two GNS3 nodes."""

    link_id: str = ""
    project_id: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    link_style: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GNS3Link:
        """Create from a GNS3 v2 API response dict."""
        return cls(
            link_id=data.get("link_id", ""),
            project_id=data.get("project_id", ""),
            nodes=data.get("nodes", []),
            properties=data.get("properties", {}),
            link_style=data.get("link_style", ""),
        )


# ── Template ─────────────────────────────────────────────────────────────


@dataclass
class GNS3Template:
    """Represents a GNS3 node template."""

    template_id: str = ""
    name: str = ""
    node_type: str = "docker"
    compute_id: str = "local"
    default_name_format: str = "{name}-{0}"
    symbol: str = ":/symbols/docker_guest.svg"
    category: str = "guest"
    properties: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GNS3Template:
        """Create from a GNS3 v2 API response dict."""
        return cls(
            template_id=data.get("template_id", ""),
            name=data.get("name", ""),
            node_type=data.get("node_type", "docker"),
            compute_id=data.get("compute_id", "local"),
            default_name_format=data.get("default_name_format", "{name}-{0}"),
            symbol=data.get("symbol", ":/symbols/docker_guest.svg"),
            category=data.get("category", "guest"),
            properties=data.get("properties", {}),
        )


# ── Link endpoint helper ─────────────────────────────────────────────────


def make_link_endpoint(
    node_id: str,
    port_number: int = 0,
    adapter_number: int = 0,
) -> dict[str, Any]:
    """Create a link endpoint dict for a given node and port."""
    return {
        "node_id": node_id,
        "port_number": port_number,
        "adapter_number": adapter_number,
    }
