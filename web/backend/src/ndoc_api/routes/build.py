"""Builds (one at a time, in the background) and PDF preview."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ndoc_core import Repo, build, docs
from ndoc_core.errors import FileNotFoundInRepoError

from ..auth import current_user, require_editor
from ..builds import BuildManager
from ..deps import get_builds, get_repo
from ..errors import responses
from ..models import BuildStatus

router = APIRouter(
    tags=["build"], dependencies=[Depends(current_user)], responses=responses(401, 422)
)


@router.get("/api/build/targets", response_model=list[str])
def list_build_targets(repo: Repo = Depends(get_repo)) -> list[str]:  # noqa: B008
    """Every target ``POST /api/build/{target}`` accepts (aliases such as
    ``tds``, ``st``, ``delivery`` and document directories)."""
    return build.allowed_targets(repo)


@router.post(
    "/api/build/{target}",
    status_code=202,
    response_model=BuildStatus,
    responses=responses(403, 409, 422),
    dependencies=[Depends(require_editor)],
)
def start_build(target: str, builds: BuildManager = Depends(get_builds)) -> dict[str, Any]:  # noqa: B008
    """Start a build in the background; poll ``GET /api/build/latest``.
    409 ``build_busy`` while another build runs."""
    return builds.start(target)


@router.get("/api/build/latest", response_model=BuildStatus)
def latest_build(builds: BuildManager = Depends(get_builds)) -> dict[str, Any]:  # noqa: B008
    """State of the latest build; ``log_tail`` grows while it runs."""
    return builds.status()


@router.get(
    "/api/preview/{document}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The PDF"},
        **responses(404),
    },
)
def preview(document: str, repo: Repo = Depends(get_repo)) -> FileResponse:  # noqa: B008
    """The built PDF of a document (inline). 404 ``not_found`` if not built yet."""
    path = docs.pdf_path(repo, document)
    if path is None:
        raise FileNotFoundInRepoError("the document has not been built yet", document=document)
    return FileResponse(
        path,
        media_type="application/pdf",
        content_disposition_type="inline",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )
