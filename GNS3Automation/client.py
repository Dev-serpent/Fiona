"""Async HTTP client for the GNS3 v2 REST API."""
from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import aiohttp

from GNS3Automation.config import GNS3Config
from GNS3Automation.errors import GNS3ConnectionError, GNS3NotFoundError

logger = logging.getLogger(__name__)


class GNS3Client:
    """Async HTTP client wrapping the GNS3 v2 REST API.

    Usage::

        async with GNS3Client(config) as client:
            projects = await client.list_projects()
    """

    def __init__(self, config: Optional[GNS3Config] = None) -> None:
        self._config = config or GNS3Config()
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers: dict[str, str] = {"Content-Type": "application/json"}

        # Basic auth
        if self._config.user:
            auth_str = f"{self._config.user}:{self._config.password}"
            encoded = base64.b64encode(auth_str.encode()).decode()
            self._headers["Authorization"] = f"Basic {encoded}"

    # ── Context manager ──────────────────────────────────────────────────

    async def __aenter__(self) -> GNS3Client:
        await self.connect()
        return self

    async def __aexit__(self, *exc_args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Open the underlying HTTP session."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=self._config.timeout),
            )

    async def disconnect(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ── Low-level request ────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Perform an HTTP request against the GNS3 API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path relative to the base URL (e.g. ``/projects``).

        Returns:
            Parsed JSON response body.

        Raises:
            GNS3ConnectionError: On connection failures.
            GNS3NotFoundError: On 404 responses.
            aiohttp.ClientResponse.raise_for_status: On other HTTP errors.
        """
        if self._session is None:
            raise GNS3ConnectionError("Client not connected; call connect() first")

        url = f"{self._config.base_url}{path}"
        ssl = self._config.verify_ssl

        try:
            async with self._session.request(
                method, url, ssl=ssl, **kwargs
            ) as resp:
                logger.debug("%s %s → %d", method, url, resp.status)

                if resp.status == 404:
                    msg = await resp.text()
                    raise GNS3NotFoundError(
                        f"GNS3 resource not found: {method} {path}: {msg}"
                    )

                resp.raise_for_status()

                # 204 No Content (e.g. DELETE)
                if resp.status == 204:
                    return None

                return await resp.json()
        except aiohttp.ClientError as exc:
            raise GNS3ConnectionError(
                f"GNS3 request failed: {method} {path}: {exc}"
            ) from exc

    # ── Projects ─────────────────────────────────────────────────────────

    async def list_projects(self) -> list[dict[str, Any]]:
        """GET /v2/projects"""
        result = await self._request("GET", "/projects")
        return result if isinstance(result, list) else []

    async def get_project(self, project_id: str) -> dict[str, Any]:
        """GET /v2/projects/{project_id}"""
        return await self._request("GET", f"/projects/{project_id}")

    async def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v2/projects"""
        return await self._request("POST", "/projects", json=payload)

    async def delete_project(self, project_id: str) -> None:
        """DELETE /v2/projects/{project_id}"""
        await self._request("DELETE", f"/projects/{project_id}")

    async def open_project(self, project_id: str) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/open"""
        return await self._request("POST", f"/projects/{project_id}/open")

    async def close_project(self, project_id: str) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/close"""
        return await self._request("POST", f"/projects/{project_id}/close")

    # ── Nodes ────────────────────────────────────────────────────────────

    async def list_nodes(self, project_id: str) -> list[dict[str, Any]]:
        """GET /v2/projects/{project_id}/nodes"""
        result = await self._request("GET", f"/projects/{project_id}/nodes")
        return result if isinstance(result, list) else []

    async def get_node(
        self, project_id: str, node_id: str
    ) -> dict[str, Any]:
        """GET /v2/projects/{project_id}/nodes/{node_id}"""
        return await self._request(
            "GET", f"/projects/{project_id}/nodes/{node_id}"
        )

    async def create_node(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/nodes"""
        return await self._request(
            "POST", f"/projects/{project_id}/nodes", json=payload
        )

    async def delete_node(
        self, project_id: str, node_id: str
    ) -> None:
        """DELETE /v2/projects/{project_id}/nodes/{node_id}"""
        await self._request(
            "DELETE", f"/projects/{project_id}/nodes/{node_id}"
        )

    async def start_node(
        self, project_id: str, node_id: str
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/nodes/{node_id}/start"""
        return await self._request(
            "POST", f"/projects/{project_id}/nodes/{node_id}/start"
        )

    async def stop_node(
        self, project_id: str, node_id: str
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/nodes/{node_id}/stop"""
        return await self._request(
            "POST", f"/projects/{project_id}/nodes/{node_id}/stop"
        )

    async def suspend_node(
        self, project_id: str, node_id: str
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/nodes/{node_id}/suspend"""
        return await self._request(
            "POST", f"/projects/{project_id}/nodes/{node_id}/suspend"
        )

    async def reload_node(
        self, project_id: str, node_id: str
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/nodes/{node_id}/reload"""
        return await self._request(
            "POST", f"/projects/{project_id}/nodes/{node_id}/reload"
        )

    # ── Links ────────────────────────────────────────────────────────────

    async def list_links(self, project_id: str) -> list[dict[str, Any]]:
        """GET /v2/projects/{project_id}/links"""
        result = await self._request("GET", f"/projects/{project_id}/links")
        return result if isinstance(result, list) else []

    async def create_link(
        self, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /v2/projects/{project_id}/links"""
        return await self._request(
            "POST", f"/projects/{project_id}/links", json=payload
        )

    async def delete_link(
        self, project_id: str, link_id: str
    ) -> None:
        """DELETE /v2/projects/{project_id}/links/{link_id}"""
        await self._request(
            "DELETE", f"/projects/{project_id}/links/{link_id}"
        )

    # ── Templates ────────────────────────────────────────────────────────

    async def list_templates(self) -> list[dict[str, Any]]:
        """GET /v2/templates"""
        result = await self._request("GET", "/templates")
        return result if isinstance(result, list) else []

    async def get_template(self, template_id: str) -> dict[str, Any]:
        """GET /v2/templates/{template_id}"""
        return await self._request("GET", f"/templates/{template_id}")

    # ── Compute ──────────────────────────────────────────────────────────

    async def list_computes(self) -> list[dict[str, Any]]:
        """GET /v2/compute"""
        result = await self._request("GET", "/compute")
        return result if isinstance(result, list) else []

    # ── Server info ──────────────────────────────────────────────────────

    async def get_version(self) -> dict[str, Any]:
        """GET /v2/version"""
        return await self._request("GET", "/version")

    async def ping(self) -> bool:
        """Quick connectivity check."""
        try:
            await self.get_version()
            return True
        except GNS3ConnectionError:
            return False
