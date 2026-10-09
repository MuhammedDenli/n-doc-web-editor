"""Server configuration from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ndoc_core.repo import find_repo_root


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """``repo_root``: the n-doc checkout (``NDOC_REPO``, else discovered from the
    cwd). ``host_root``: the same path as seen by the Docker daemon
    (``NDOC_HOST_REPO``). ``data_dir`` holds ``users.sqlite``; it defaults to
    ``<repo>/web/web-data`` (git-ignored and outside the file API)."""

    repo_root: Path
    host_root: Path | None = None
    data_dir: Path | None = None
    cookie_secure: bool = False
    session_hours: float = 12.0
    admin_user: str | None = None
    admin_password: str | None = None

    @property
    def users_db(self) -> Path:
        return (self.data_dir or self.repo_root / "web" / "web-data") / "users.sqlite"

    @classmethod
    def from_env(cls) -> Settings:
        host = os.environ.get("NDOC_HOST_REPO")
        data = os.environ.get("NDOC_DATA_DIR")
        return cls(
            repo_root=find_repo_root(),
            host_root=Path(host) if host else None,
            data_dir=Path(data) if data else None,
            cookie_secure=_flag("NDOC_COOKIE_SECURE", False),
            session_hours=float(os.environ.get("NDOC_SESSION_HOURS", "12")),
            admin_user=os.environ.get("NDOC_ADMIN_USER") or None,
            admin_password=os.environ.get("NDOC_ADMIN_PASSWORD") or None,
        )
