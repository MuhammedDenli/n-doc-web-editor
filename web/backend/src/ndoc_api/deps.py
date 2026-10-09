"""Shared request dependencies and result conversion."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from fastapi import Request

from ndoc_core import Repo, checks

if TYPE_CHECKING:
    from .builds import BuildManager


def get_repo(request: Request) -> Repo:
    return request.app.state.repo


def get_builds(request: Request) -> BuildManager:
    return request.app.state.builds


def plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return obj


def report(rep: checks.CheckReport | None) -> dict[str, Any] | None:
    if rep is None:
        return None
    return {"ok": rep.ok, "issues": [plain(i) for i in rep.issues], "checked": rep.checked}
