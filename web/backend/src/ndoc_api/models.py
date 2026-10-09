"""Request/response models: the HTTP contract (exported to web/contracts/openapi.json).

They mirror the ``ndoc_core`` dataclasses; routes return ``dataclasses.asdict``
results and FastAPI validates them against these models.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "editor"]
Severity = Literal["error", "warning"]
BuildState = Literal["idle", "running", "succeeded", "failed"]


class ErrorBody(BaseModel):
    """Every error response. ``code`` is stable (core error codes plus
    ``unauthenticated``, ``forbidden``, ``csrf_failed``, ``invalid_credentials``,
    ``too_many_attempts``, ``invalid_request``, ``last_admin``)."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class Health(BaseModel):
    status: Literal["ok"] = "ok"


# ---------------------------------------------------------------- auth/users


class LoginRequest(BaseModel):
    username: str
    password: str


class User(BaseModel):
    username: str
    role: Role
    disabled: bool = False


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: Role = "editor"


class UserUpdate(BaseModel):
    role: Role | None = None
    password: str | None = None
    disabled: bool | None = None


# ------------------------------------------------------------------- checks


class Issue(BaseModel):
    code: str
    message: str
    severity: Severity = "error"
    path: str | None = None
    line: int | None = None
    col: int | None = None


class CheckReport(BaseModel):
    ok: bool
    issues: list[Issue]
    checked: list[str]


class ChecksRequest(BaseModel):
    """Scope: ``paths``, or a whole ``document``, or (neither) the files changed
    in the working tree. ``sfr_consistency`` defaults to "when CSV data is in
    scope"; ``pdfs`` scans built PDFs."""

    paths: list[str] | None = None
    document: str | None = None
    sfr_consistency: bool | None = None
    pdfs: list[str] | None = None


# ------------------------------------------------------------------ project


class Document(BaseModel):
    name: str
    kind: Literal["pdf", "mwe"]
    main_file: str
    pdf_file: str
    pdf_exists: bool


class InputNode(BaseModel):
    path: str
    exists: bool
    children: list[InputNode] = Field(default_factory=list)
    line: int | None = None
    note: str | None = None


class FileEntry(BaseModel):
    path: str
    size: int
    writable: bool


class FileContent(BaseModel):
    path: str
    text: str
    sha256: str
    size: int


class FileWrite(BaseModel):
    """Existing file: ``expected_sha256`` (from the read) must match. New file:
    ``create=true`` (the directory must exist)."""

    content: str
    expected_sha256: str | None = None
    create: bool = False


class WriteResult(BaseModel):
    path: str
    sha256: str
    size: int
    created: bool
    checks: CheckReport | None = None


class SearchMatch(BaseModel):
    path: str
    line: int
    col: int
    text: str


class SearchResult(BaseModel):
    matches: list[SearchMatch]
    truncated: bool


class ReferenceKey(BaseModel):
    key: str
    name: str = ""


class References(BaseModel):
    """Editor completion: reference macro -> kind, kind -> valid keys."""

    macros: dict[str, str]
    keys: dict[str, list[ReferenceKey]]


# --------------------------------------------------------------------- data


class ForeignKey(BaseModel):
    columns: list[str]
    ref_table: str
    ref_columns: list[str]


class TableInfo(BaseModel):
    name: str
    path: str
    columns: list[str]
    primary_key: list[str]
    foreign_keys: list[ForeignKey]
    row_count: int
    trailing_newline: bool


class Row(BaseModel):
    line: int
    values: dict[str, str]


class TableData(BaseModel):
    table: str
    path: str
    columns: list[str]
    primary_key: list[str]
    sha256: str
    rows: list[Row]
    total: int
    truncated: bool


class LookupOption(BaseModel):
    value: str
    name: str
    key: dict[str, str]


class RowInsert(BaseModel):
    values: dict[str, str]
    expected_sha256: str | None = None


class RowUpdate(BaseModel):
    """``match``: the primary key (or the whole row for tables without one)."""

    match: dict[str, str]
    values: dict[str, str]
    expected_sha256: str | None = None


class RowDelete(BaseModel):
    match: dict[str, str]
    expected_sha256: str | None = None


class RowChange(BaseModel):
    table: str
    path: str
    sha256: str
    line: int | None
    row: dict[str, str]
    checks: CheckReport


class RenameKeyRequest(BaseModel):
    match: dict[str, str]
    new_key: dict[str, str]
    expected_sha256: str | None = None


class FileChange(BaseModel):
    path: str
    sha256: str
    rows_changed: int


class TexReference(BaseModel):
    path: str
    line: int
    col: int
    macro: str
    key: str
    replacement: str


class RenameResult(BaseModel):
    table: str
    old_key: dict[str, str]
    new_key: dict[str, str]
    files: list[FileChange]
    tex_references: list[TexReference]
    checks: CheckReport


# -------------------------------------------------------------------- build


class BuildStatus(BaseModel):
    """The latest build of this server. ``log_tail`` grows while running;
    ``error`` is set when the build could not run (e.g. Docker missing)."""

    state: BuildState
    target: str | None = None
    started_at: float | None = None
    elapsed_s: float | None = None
    returncode: int | None = None
    timed_out: bool = False
    log_tail: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    pdfs: list[str] = Field(default_factory=list)
    pdf_checks: CheckReport | None = None
    error: ErrorBody | None = None
