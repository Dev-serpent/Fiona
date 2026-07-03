"""Topology builder — high-level API for constructing GNS3 network topologies.

Provides a fluent interface for creating nodes, connecting them with links,
and managing the resulting topology within a GNS3 project.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from GNS3Automation.client import GNS3Client
from GNS3Automation.errors import GNS3LinkError, GNS3NodeError
from GNS3Automation.models import (
    GNS3Link,
    GNS3Node,
    make_link_endpoint,
)

logger = logging.getLogger(__name__)


class TopologyBuilder:
    """Builds and manages GNS3 topologies.

    Usage::

        async with GNS3Client(config) as client:
            builder = TopologyBuilder(client, project_id="...")
            node1 = await builder.add_node("router-1", node_type="docker", ...)
            node2 = await builder.add_node("router-2", node_type="docker", ...)
            link = await builder.add_link(node1.node_id, node2.node_id)
    """

    def __init__(self, client: GNS3Client, project_id: str) -> None:
        self._client = client
        self._project_id = project_id

    # ── Nodes ────────────────────────────────────────────────────────────

    async def add_node(
        self,
        name: str,
        node_type: str = "docker",
        template: str = "",
        compute_id: str = "local",
        x: float = 0.0,
        y: float = 0.0,
        properties: dict[str, Any] | None = None,
    ) -> GNS3Node:
        """Add a node to the topology.

        Args:
            name: Node name (must be unique within the project).
            node_type: Type of node (``"docker"``, ``"qemu"``, ``"vpcs"``, etc.).
            template: Name or ID of a GNS3 template to use.
            compute_id: Compute node ID (default ``"local"``).
            x: X position on the canvas.
            y: Y position on the canvas.
            properties: Additional node properties (e.g. Docker image).

        Returns:
            A :class:`GNS3Node` instance.

        Raises:
            GNS3NodeError: If creation fails.
        """
        payload: dict[str, Any] = {
            "name": name,
            "node_type": node_type,
            "compute_id": compute_id,
            "x": x,
            "y": y,
        }
        if template:
            payload["template"] = template
        if properties:
            payload["properties"] = properties

        try:
            data = await self._client.create_node(self._project_id, payload)
            node = GNS3Node.from_api(data)
            logger.info(
                "Node added: %s (%s) type=%s", node.name, node.node_id, node_type
            )
            return node
        except Exception as exc:
            raise GNS3NodeError(
                f"Failed to create node {name!r}: {exc}"
            ) from exc

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node from the topology.

        Returns:
            ``True`` if removed, ``False`` if not found.
        """
        try:
            await self._client.delete_node(self._project_id, node_id)
            logger.info("Node removed: %s", node_id)
            return True
        except Exception:
            return False

    async def start_node(self, node_id: str) -> None:
        """Start a node."""
        try:
            await self._client.start_node(self._project_id, node_id)
            logger.info("Node started: %s", node_id)
        except Exception as exc:
            raise GNS3NodeError(
                f"Failed to start node {node_id}: {exc}"
            ) from exc

    async def stop_node(self, node_id: str) -> None:
        """Stop a node."""
        try:
            await self._client.stop_node(self._project_id, node_id)
            logger.info("Node stopped: %s", node_id)
        except Exception as exc:
            raise GNS3NodeError(
                f"Failed to stop node {node_id}: {exc}"
            ) from exc

    async def list_nodes(self) -> list[GNS3Node]:
        """List all nodes in the topology."""
        try:
            data_list = await self._client.list_nodes(self._project_id)
            return [GNS3Node.from_api(d) for d in data_list]
        except Exception as exc:
            raise GNS3NodeError(f"Failed to list nodes: {exc}") from exc

    async def get_node(self, node_id: str) -> Optional[GNS3Node]:
        """Get a single node by ID."""
        try:
            data = await self._client.get_node(self._project_id, node_id)
            return GNS3Node.from_api(data)
        except Exception:
            return None

    # ── Links ────────────────────────────────────────────────────────────

    async def add_link(
        self,
        node_a_id: str,
        node_b_id: str,
        port_a: int = 0,
        port_b: int = 0,
        properties: dict[str, Any] | None = None,
    ) -> GNS3Link:
        """Connect two nodes with a link.

        Args:
            node_a_id: First node ID.
            node_b_id: Second node ID.
            port_a: Port number on the first node.
            port_b: Port number on the second node.
            properties: Optional link properties.

        Returns:
            A :class:`GNS3Link` instance.
        """
        payload: dict[str, Any] = {
            "nodes": [
                make_link_endpoint(node_a_id, port_number=port_a),
                make_link_endpoint(node_b_id, port_number=port_b),
            ]
        }
        if properties:
            payload["properties"] = properties

        try:
            data = await self._client.create_link(self._project_id, payload)
            link = GNS3Link.from_api(data)
            logger.info(
                "Link created: %s (%s ↔ %s)",
                link.link_id,
                node_a_id,
                node_b_id,
            )
            return link
        except Exception as exc:
            raise GNS3LinkError(
                f"Failed to create link between {node_a_id} and {node_b_id}: {exc}"
            ) from exc

    async def remove_link(self, link_id: str) -> bool:
        """Remove a link.

        Returns:
            ``True`` if removed, ``False`` if not found.
        """
        try:
            await self._client.delete_link(self._project_id, link_id)
            logger.info("Link removed: %s", link_id)
            return True
        except Exception:
            return False

    async def list_links(self) -> list[GNS3Link]:
        """List all links in the topology."""
        try:
            data_list = await self._client.list_links(self._project_id)
            return [GNS3Link.from_api(d) for d in data_list]
        except Exception as exc:
            raise GNS3LinkError(f"Failed to list links: {exc}") from exc
