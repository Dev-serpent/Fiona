"""GNS3 project lifecycle manager."""
from __future__ import annotations

import logging
from typing import Any, Optional

from GNS3Automation.client import GNS3Client
from GNS3Automation.errors import GNS3NotFoundError, GNS3ProjectError
from GNS3Automation.models import GNS3Project

logger = logging.getLogger(__name__)


class ProjectManager:
    """Manages GNS3 project lifecycle (CRUD, open/close).

    Usage::

        async with GNS3Client(config) as client:
            mgr = ProjectManager(client)
            project = await mgr.create("my-lab")
            await mgr.open(project.project_id)
            # ... work with nodes ...
            await mgr.close(project.project_id)
    """

    def __init__(self, client: GNS3Client) -> None:
        self._client = client

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def create(
        self,
        name: str,
        auto_start: bool = False,
        auto_close: bool = True,
        variables: dict[str, str] | None = None,
    ) -> GNS3Project:
        """Create a new GNS3 project.

        Args:
            name: Project name.
            auto_start: Automatically start the project on server startup.
            auto_close: Automatically close the project on server shutdown.
            variables: Optional dictionary of project variables.

        Returns:
            A :class:`GNS3Project` instance.

        Raises:
            GNS3ProjectError: If creation fails.
        """
        payload: dict[str, Any] = {
            "name": name,
            "auto_start": auto_start,
            "auto_close": auto_close,
        }
        if variables:
            payload["variables"] = variables

        try:
            data = await self._client.create_project(payload)
            project = GNS3Project.from_api(data)
            logger.info("GNS3 project created: %s (%s)", project.name, project.project_id)
            return project
        except Exception as exc:
            raise GNS3ProjectError(
                f"Failed to create GNS3 project {name!r}: {exc}"
            ) from exc

    async def get(self, project_id: str) -> Optional[GNS3Project]:
        """Retrieve a project by ID.

        Returns:
            A :class:`GNS3Project` or ``None`` if not found.
        """
        try:
            data = await self._client.get_project(project_id)
            return GNS3Project.from_api(data)
        except GNS3NotFoundError:
            return None
        except Exception as exc:
            raise GNS3ProjectError(
                f"Failed to get project {project_id}: {exc}"
            ) from exc

    async def list(self) -> list[GNS3Project]:
        """List all projects on the GNS3 server."""
        try:
            data_list = await self._client.list_projects()
            return [GNS3Project.from_api(d) for d in data_list]
        except Exception as exc:
            raise GNS3ProjectError(f"Failed to list projects: {exc}") from exc

    async def delete(self, project_id: str) -> bool:
        """Delete a project by ID.

        Returns:
            ``True`` if deleted, ``False`` if not found.
        """
        try:
            await self._client.delete_project(project_id)
            logger.info("GNS3 project deleted: %s", project_id)
            return True
        except GNS3NotFoundError:
            return False
        except Exception as exc:
            raise GNS3ProjectError(
                f"Failed to delete project {project_id}: {exc}"
            ) from exc

    # ── Open / Close ─────────────────────────────────────────────────────

    async def open(self, project_id: str) -> GNS3Project:
        """Open (start) a project.

        Raises:
            GNS3ProjectError: If the project cannot be opened.
        """
        try:
            data = await self._client.open_project(project_id)
            project = GNS3Project.from_api(data)
            logger.info("GNS3 project opened: %s", project_id)
            return project
        except Exception as exc:
            raise GNS3ProjectError(
                f"Failed to open project {project_id}: {exc}"
            ) from exc

    async def close(self, project_id: str) -> GNS3Project:
        """Close (stop) a project.

        Raises:
            GNS3ProjectError: If the project cannot be closed.
        """
        try:
            data = await self._client.close_project(project_id)
            project = GNS3Project.from_api(data)
            logger.info("GNS3 project closed: %s", project_id)
            return project
        except Exception as exc:
            raise GNS3ProjectError(
                f"Failed to close project {project_id}: {exc}"
            ) from exc
