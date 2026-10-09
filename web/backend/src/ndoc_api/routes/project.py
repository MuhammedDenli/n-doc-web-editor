"""Documents, files, search, reference keys and checks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ndoc_core import Repo, checks, docs, files

from ..auth import current_user, require_editor
from ..deps import get_repo, plain, report
from ..errors import responses
from ..models import (
    CheckReport,
    ChecksRequest,
    Document,
    FileContent,
    FileEntry,
    FileWrite,
    InputNode,
    References,
    SearchResult,
    WriteResult,
)

router = APIRouter(
    prefix="/api/project",
    tags=["project"],
    dependencies=[Depends(current_user)],
    responses=responses(401, 422),
)


@router.get("/documents", response_model=list[Document])
def list_documents(
    include_mwe: bool = True,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> list[dict[str, Any]]:
    """The n-doc documents (``PDF_DIRS``, plus ``mwe_*`` test documents)."""
    return [plain(d) for d in docs.list_documents(repo, include_mwe=include_mwe)]


@router.get("/documents/{name}/tree", response_model=InputNode, responses=responses(404))
def document_tree(name: str, repo: Repo = Depends(get_repo)) -> dict[str, Any]:  # noqa: B008
    """The ``\\input`` tree of a document, starting at its main file."""
    return plain(docs.input_tree(repo, name))


@router.get("/files", response_model=list[FileEntry], responses=responses(403, 404))
def list_files(
    dir: str = "",  # noqa: A002 - public query parameter name
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> list[dict[str, Any]]:
    """Readable files below ``dir`` (recursive)."""
    return [plain(e) for e in files.list_files(repo, dir)]


@router.get("/files/{path:path}", response_model=FileContent, responses=responses(403, 404, 413))
def read_file(path: str, repo: Repo = Depends(get_repo)) -> dict[str, Any]:  # noqa: B008
    """A text file with its ``sha256`` (send it back as ``expected_sha256``)."""
    return plain(files.read_file(repo, path))


@router.put(
    "/files/{path:path}",
    response_model=WriteResult,
    responses=responses(403, 404, 409, 413),
    dependencies=[Depends(require_editor)],
)
def write_file(
    path: str,
    body: FileWrite,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """Write a whole file atomically. 409 ``stale_write`` (with ``current_hash``)
    when it changed since it was read. Returns the check results of the saved
    file (LaTeX syntax + references; key/FK checks for ``common/db`` CSV)."""
    result = plain(
        files.write_file(
            repo, path, body.content, expected_hash=body.expected_sha256, create=body.create
        )
    )
    result["checks"] = report(checks.check_after_write(repo, result["path"]))
    return result


@router.get("/search", response_model=SearchResult, responses=responses(403, 404))
def search(
    pattern: str = Query(min_length=1),
    dir: str = "",  # noqa: A002 - public query parameter name
    regex: bool = False,
    ignore_case: bool = False,
    max_results: int = Query(100, ge=1, le=1000),
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    return plain(
        files.search(
            repo,
            pattern,
            rel_dir=dir,
            regex=regex,
            ignore_case=ignore_case,
            max_results=max_results,
        )
    )


@router.get("/references", response_model=References)
def references(repo: Repo = Depends(get_repo)) -> dict[str, Any]:  # noqa: B008
    """Reference macros (``\\sfrlink`` -> ``sfr``, ...) and the valid keys per kind."""
    keys = checks.reference_keys(repo)
    return {
        "macros": dict(checks.REFERENCE_MACROS),
        "keys": {kind: [plain(k) for k in entries] for kind, entries in keys.items()},
    }


@router.post("/checks", response_model=CheckReport, responses=responses(403, 404))
def run_checks(body: ChecksRequest, repo: Repo = Depends(get_repo)) -> dict[str, Any]:  # noqa: B008
    """Static checks without changing anything (allowed for every role)."""
    return report(
        checks.run_checks(
            repo,
            paths=body.paths,
            document=body.document,
            sfr_consistency=body.sfr_consistency,
            pdfs=body.pdfs,
        )
    )
