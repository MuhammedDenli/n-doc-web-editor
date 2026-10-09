"""CSV data in ``common/db``: schema, rows, lookups and validated row edits."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ndoc_core import Repo, checks, csvdata

from ..auth import current_user, require_editor
from ..deps import get_repo, plain, report
from ..errors import responses
from ..models import (
    LookupOption,
    RenameKeyRequest,
    RenameResult,
    RowChange,
    RowDelete,
    RowInsert,
    RowUpdate,
    TableData,
    TableInfo,
)

router = APIRouter(
    prefix="/api/data",
    tags=["data"],
    dependencies=[Depends(current_user)],
    responses=responses(401, 422),
)

_WRITE = {"dependencies": [Depends(require_editor)], "responses": responses(403, 404, 409)}


def _with_checks(repo: Repo, result: object) -> dict[str, Any]:
    out = plain(result)
    out["checks"] = report(checks.check_db(repo))
    return out


@router.get("/tables", response_model=list[TableInfo])
def list_tables(repo: Repo = Depends(get_repo)) -> list[dict[str, Any]]:  # noqa: B008
    """Tables with CSV path, columns (header order), primary key and foreign
    keys (composite ones included)."""
    return [plain(t) for t in csvdata.list_tables(repo)]


@router.get("/{table}", response_model=TableData, responses=responses(404))
def read_table(
    table: str,
    limit: int | None = Query(None, ge=0),
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """All rows (with their file line) and the file's ``sha256``."""
    return plain(csvdata.read_table(repo, table, None, limit))


@router.get("/{table}/lookup", response_model=list[LookupOption], responses=responses(404))
def lookup(
    table: str,
    column: str,
    prefix: str = "",
    limit: int = Query(50, ge=1, le=1000),
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> list[dict[str, Any]]:
    """Allowed values of ``table.column``: for a foreign key column the
    referenced rows (``key`` holds the full, possibly composite key)."""
    return [plain(o) for o in csvdata.lookup(repo, table, column, prefix, limit)]


@router.post("/{table}", status_code=201, response_model=RowChange, **_WRITE)
def insert_row(
    table: str,
    body: RowInsert,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """Append a row. 409 ``duplicate_key``, 422 ``foreign_key_violation``."""
    return _with_checks(
        repo, csvdata.insert_row(repo, table, body.values, expected_hash=body.expected_sha256)
    )


@router.put("/{table}", response_model=RowChange, **_WRITE)
def update_row(
    table: str,
    body: RowUpdate,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """Change columns of the one row matching ``match``. A key other rows
    reference cannot change (409 ``row_referenced``): use rename-key."""
    return _with_checks(
        repo,
        csvdata.update_row(
            repo, table, body.match, body.values, expected_hash=body.expected_sha256
        ),
    )


@router.delete("/{table}", response_model=RowChange, **_WRITE)
def delete_row(
    table: str,
    body: RowDelete,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """Delete the one row matching ``match``. 409 ``row_referenced`` (details
    ``referenced_by``) while other rows reference it."""
    return _with_checks(
        repo, csvdata.delete_row(repo, table, body.match, expected_hash=body.expected_sha256)
    )


@router.post("/{table}/rename-key", response_model=RenameResult, **_WRITE)
def rename_key(
    table: str,
    body: RenameKeyRequest,
    repo: Repo = Depends(get_repo),  # noqa: B008
) -> dict[str, Any]:
    """Rename a row's key and every CSV row referencing it in one atomic write;
    ``tex_references`` lists the .tex references to update."""
    return _with_checks(
        repo,
        csvdata.rename_key(
            repo, table, body.match, body.new_key, expected_hash=body.expected_sha256
        ),
    )
