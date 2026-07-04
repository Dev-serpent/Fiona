"""Manage the local ``git`` clone of ``public-apis/public-apis``."""

from __future__ import annotations

import subprocess
import threading
from datetime import datetime
from pathlib import Path


class PublicApisRepo:
    """Manages the local shallow clone of ``public-apis/public-apis``.

    The repository is stored at ``~/.cache/fiona/public-apis/`` and is
    refreshed on demand via ``git pull --ff-only``.
    """

    REPO_URL = "https://github.com/public-apis/public-apis.git"
    DEFAULT_CACHE_DIR = Path.home() / ".cache" / "fiona" / "public-apis"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or self.DEFAULT_CACHE_DIR
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def cache_dir(self) -> Path:
        """Path to the local working copy."""
        return self._cache_dir

    def ensure(self) -> Path:
        """Return the path to a local working copy, cloning or pulling as needed.

        This is the main entry point.  The first call clones the repository
        (shallow, ``--depth 1``).  Subsequent calls do a fast-forward pull.
        """
        with self._lock:
            if self._is_cloned():
                self._pull()
            else:
                self._clone()
            return self._cache_dir

    def clone(self) -> Path:
        """Force a fresh shallow clone, overwriting any existing directory."""
        with self._lock:
            self._clone()
            return self._cache_dir

    def refresh(self) -> Path:
        """Force a ``git pull --ff-only``, returning the working copy path."""
        with self._lock:
            self._pull()
            return self._cache_dir

    def last_refreshed(self) -> datetime | None:
        """Return the timestamp of the most recent pull/update.

        Returns ``None`` if the repository has not been cloned yet.
        """
        git_dir = self._cache_dir / ".git"
        if not git_dir.exists():
            return None

        try:
            result = subprocess.run(
                ["git", "-C", str(self._cache_dir), "log", "-1", "--format=%ct"],
                capture_output=True, text=True, check=True,
            )
            timestamp = int(result.stdout.strip())
            return datetime.fromtimestamp(timestamp)
        except (subprocess.CalledProcessError, ValueError, OSError):
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_cloned(self) -> bool:
        return (self._cache_dir / ".git").exists()

    def _clone(self) -> None:
        self._cache_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", self.REPO_URL, str(self._cache_dir)],
            check=True, capture_output=True,
        )

    def _pull(self) -> None:
        subprocess.run(
            ["git", "-C", str(self._cache_dir), "pull", "--ff-only"],
            check=False, capture_output=True,
        )
