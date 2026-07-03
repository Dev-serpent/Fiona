"""GNS3-specific exception classes."""
from __future__ import annotations


class GNS3Error(Exception):
    """Base error for all GNS3 automation errors."""


class GNS3ConnectionError(GNS3Error):
    """Raised when connecting to the GNS3 server fails."""


class GNS3ProjectError(GNS3Error):
    """Raised when a project operation fails."""


class GNS3NodeError(GNS3Error):
    """Raised when a node operation fails."""


class GNS3LinkError(GNS3Error):
    """Raised when a link operation fails."""


class GNS3NotFoundError(GNS3Error):
    """Raised when a requested resource is not found on the server."""


class GNS3TemplateError(GNS3Error):
    """Raised when a template operation fails."""
