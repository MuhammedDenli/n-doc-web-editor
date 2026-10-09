"""The n-doc repository a core instance operates on."""

from __future__ import annotations

import fcntl
import hashlib
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .errors import CoreError, LockTimeoutError


@dataclass(frozen=True)
class Repo:
    """An n-doc checkout.

    ``root`` is the working tree. ``host_root`` is the same directory as seen by
    the Docker daemon; it differs only when the core itself runs in a container
    that talks to the host daemon through ``docker.sock``.
    """

    root: Path
    host_root: Path | None = None
    db_dir: str = "common/db"
    state_dir: Path = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        root = Path(self.root).resolve(strict=True)
        if not (root / "Makefile").is_file():
            raise CoreError(f"not an n-doc checkout (no Makefile): {root}")
        object.__setattr__(self, "root", root)
        if self.state_dir is None:
            object.__setattr__(self, "state_dir", _default_state_dir(root))
        Path(self.state_dir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> Repo:
        """Build a Repo from ``NDOC_REPO`` / ``NDOC_HOST_REPO`` (defaults: cwd)."""
        root = Path(os.environ.get("NDOC_REPO", os.getcwd()))
        host = os.environ.get("NDOC_HOST_REPO")
        return cls(root=root, host_root=Path(host) if host else None)

    @property
    def docker_root(self) -> Path:
        return self.host_root or self.root

    @contextmanager
    def lock(self, name: str, *, timeout: float = 10.0) -> Iterator[None]:
        """Inter-process exclusive lock (flock), shared by API and MCP processes."""
        with _flock(Path(self.state_dir) / f"{name}.lock", timeout) as acquired:
            if not acquired:
                raise LockTimeoutError(f"could not acquire lock '{name}'", lock=name)
            yield

    @contextmanager
    def try_lock(self, name: str) -> Iterator[bool]:
        """Non-blocking variant: yields False instead of waiting."""
        with _flock(Path(self.state_dir) / f"{name}.lock", 0) as acquired:
            yield acquired


def find_repo_root(start: Path | None = None) -> Path:
    """``NDOC_REPO`` if set, else the nearest ancestor of ``start`` (default cwd)
    that looks like this checkout (root ``Makefile`` and ``web/``)."""
    env = os.environ.get("NDOC_REPO")
    if env:
        return Path(env)
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "Makefile").is_file() and (candidate / "web").is_dir():
            return candidate
    raise CoreError(f"no n-doc checkout found above {here}; set NDOC_REPO")


def _default_state_dir(root: Path) -> Path:
    # Inside .git so it is never part of the working tree; worktrees (where
    # .git is a file) and plain copies fall back to a per-root temp dir.
    git_dir = root / ".git"
    if git_dir.is_dir():
        return git_dir / "ndoc-web"
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"ndoc-web-{digest}"


@contextmanager
def _flock(path: Path, timeout: float) -> Iterator[bool]:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.05)
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
