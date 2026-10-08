"""MCP server: thin adapter exposing ``ndoc_core`` as agent tools.

All validation (path guard, build allowlist, protected branches, stale writes)
happens in the core; this module only maps arguments and results and turns a
``CoreError`` into a tool error carrying its stable ``code``.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from ndoc_core import CoreError, Repo, build, checks, csvdata, docs, files, git, pdf

INSTRUCTIONS = """\
Tools for editing an n-doc repository: Common Criteria documents written in LaTeX,
with shared data in common/db/*.csv. Paths are repo-relative POSIX paths.

Workflow for a change:
1. git_status; if on main/master or a shared branch, git_create_branch first
   (e.g. "agent/<topic>"). Commits on main/master are refused.
2. Find the place: list_documents, document_tree, search, read_file.
3. Change with edit_file (unique text match, preferred) or write_file (whole file,
   pass expected_sha256 from read_file). Both return check results for .tex files.
4. run_checks, then run_build for the affected document (e.g. "tds", "mwe_tds");
   pdf_search confirms the change reached the PDF.
5. git_diff to review, then git_commit with the explicit list of changed paths.

n-doc rules:
- Keep LaTeX escapes exactly as they are (O.TLS\\_Crypto, SF.Net\\-work).
  Never "fix" text inside macro arguments.
- Reference macros (\\sfrlink{...}, \\tdslink{mod.<subsystem>.<module>},
  \\tsfilink, \\secitem, ...) must resolve to rows in common/db; run_checks
  reports unresolved ones. Do not invent labels: search the CSV first.
- Change common/db/*.csv with the csv_* tools (csv_tables, csv_read, csv_lookup,
  csv_insert, csv_update, csv_delete): they keep every other byte of the file and
  refuse duplicate keys and unresolved foreign keys. A referenced row cannot be
  deleted or have its key changed; csv_rename_key renames a key together with all
  referencing CSV rows and lists the .tex references (with their replacement) to
  update afterwards with edit_file. Use edit_file on CSV only as a last resort.
- Build targets: all delivery st fsp tds arc ate ref db mwe clean, or a document
  directory name (ase, adv_tds, mwe_tds, ...). The ST alias is "st", its directory "ase".
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)

_F = TypeVar("_F", bound=Callable[..., Any])

SUCCESS_TAIL_LINES = 15


def _plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return obj


def _core_errors(fn: _F) -> _F:
    """Report CoreError as a tool error the model can act on (JSON with ``code``)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except CoreError as exc:
            raise ToolError(json.dumps(exc.to_dict(), default=str, ensure_ascii=False)) from exc

    return wrapper  # type: ignore[return-value]


def _report(report: checks.CheckReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "issues": [dataclasses.asdict(i) for i in report.issues],
        "checked": report.checked,
    }


def _checks_after_write(repo: Repo, path: str) -> dict[str, Any] | None:
    if path.endswith(".tex"):
        return _report(checks.check_files(repo, [path]))
    if path.startswith(f"{repo.db_dir}/") and path.endswith(".csv"):
        return _db_report(repo)
    return None


def _db_checks(repo: Repo) -> checks.CheckReport:
    return csvdata.validate_db(repo).extend(checks.check_sfr_consistency(repo))


def _db_report(repo: Repo) -> dict[str, Any]:
    return _report(_db_checks(repo))


def _changed_paths(repo: Repo) -> list[str]:
    return [
        f.path
        for f in git.status(repo).files
        if f.worktree != "D" and f.index != "D" and files.is_allowed(repo, f.path)
    ]


def create_server(repo: Repo) -> MCPServer:
    mcp = MCPServer(name="ndoc", instructions=INSTRUCTIONS)

    def tool(annotations: ToolAnnotations) -> Callable[[_F], _F]:
        def register(fn: _F) -> _F:
            mcp.tool(annotations=annotations)(_core_errors(fn))
            return fn

        return register

    # ------------------------------------------------------------------ docs

    @tool(READ_ONLY)
    def list_documents(include_mwe: bool = True) -> list[dict[str, Any]]:
        """List the n-doc documents (PDF_DIRS, plus mwe_* test documents) with
        their main .tex file and PDF path."""
        return [_plain(d) for d in docs.list_documents(repo, include_mwe=include_mwe)]

    @tool(READ_ONLY)
    def document_tree(document: str) -> dict[str, Any]:
        """The \\input tree of a document starting at its main file. Nodes have
        path, exists, line (of the \\input in the parent), note and children."""
        return _plain(docs.input_tree(repo, document))

    # ----------------------------------------------------------------- files

    @tool(READ_ONLY)
    def list_files(directory: str = "") -> list[dict[str, Any]]:
        """Readable files below a directory (recursive), with size and whether
        the agent may write them."""
        return [_plain(e) for e in files.list_files(repo, directory)]

    @tool(READ_ONLY)
    def search(
        pattern: str,
        directory: str = "",
        regex: bool = False,
        ignore_case: bool = False,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Search lines of readable files (plain text by default, Python regex
        with regex=true). Returns path, line, col and the line text."""
        return _plain(
            files.search(
                repo,
                pattern,
                rel_dir=directory,
                regex=regex,
                ignore_case=ignore_case,
                max_results=max_results,
            )
        )

    @tool(READ_ONLY)
    def read_file(path: str) -> dict[str, Any]:
        """Read a text file. Returns its content and sha256; pass the sha256 as
        expected_sha256 to write_file/edit_file."""
        return _plain(files.read_file(repo, path))

    @tool(WRITES)
    def edit_file(
        path: str,
        old_text: str,
        new_text: str,
        expected_sha256: str | None = None,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        """Replace old_text by new_text in an existing file. old_text must occur
        exactly once (include surrounding lines to make it unique) unless
        replace_all is true. Everything outside the match is kept byte-exactly.
        Returns the new sha256 and check results."""
        result = _plain(
            files.replace_text(
                repo,
                path,
                old_text,
                new_text,
                expected_hash=expected_sha256,
                replace_all=replace_all,
            )
        )
        result["checks"] = _checks_after_write(repo, result["path"])
        return result

    @tool(WRITES)
    def write_file(
        path: str, content: str, expected_sha256: str | None = None, create: bool = False
    ) -> dict[str, Any]:
        """Write a whole file. Existing file: expected_sha256 (from read_file) is
        required and must match. New file: create=true; the directory must exist.
        Returns the new sha256 and check results."""
        result = _plain(
            files.write_file(repo, path, content, expected_hash=expected_sha256, create=create)
        )
        result["checks"] = _checks_after_write(repo, result["path"])
        return result

    # ---------------------------------------------------------------- checks

    @tool(READ_ONLY)
    def run_checks(
        paths: list[str] | None = None,
        document: str | None = None,
        sfr_consistency: bool | None = None,
        pdfs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Static checks: LaTeX brace/environment balance and n-doc reference
        macros against common/db. Scope: the given paths, or a whole document,
        or (default) the files changed in the working tree. sfr_consistency runs
        scripts/check_sfr_consistency.sh (default: when CSV data changed). pdfs
        scans built PDFs for "is undefined" / "To Do"."""
        report = checks.CheckReport()
        if document:
            report.extend(checks.check_document(repo, document))
        scope = paths if paths is not None else ([] if document else _changed_paths(repo))
        report.extend(checks.check_files(repo, scope))
        if sfr_consistency is None:
            sfr_consistency = any(
                p.startswith(f"{repo.db_dir}/") and p.endswith(".csv") for p in scope
            )
        if sfr_consistency:
            report.extend(_db_checks(repo))
        if pdfs:
            report.extend(checks.check_pdf_sanity(repo, pdfs))
        return _report(report)

    # ------------------------------------------------------------------- csv

    @tool(READ_ONLY)
    def csv_tables() -> list[dict[str, Any]]:
        """Tables in common/db: CSV path, columns (header order), primary key,
        foreign keys (composite ones included) and row count."""
        return [_plain(t) for t in csvdata.list_tables(repo)]

    @tool(READ_ONLY)
    def csv_read(
        table: str, where: dict[str, str] | None = None, limit: int = 200
    ) -> dict[str, Any]:
        """Rows of a table (e.g. "modules"), optionally only those whose columns
        equal the values in where. Each row has its file line number. Returns
        sha256 for expected_sha256."""
        return _plain(csvdata.read_table(repo, table, where, limit))

    @tool(READ_ONLY)
    def csv_lookup(table: str, column: str, prefix: str = "", limit: int = 50) -> list[dict]:
        """Allowed values for table.column: for a foreign key column the
        referenced rows (value, name, full key), else the existing values."""
        return [_plain(o) for o in csvdata.lookup(repo, table, column, prefix, limit)]

    @tool(WRITES)
    def csv_insert(
        table: str, values: dict[str, str], expected_sha256: str | None = None
    ) -> dict[str, Any]:
        """Append a row (columns left out are empty). Values are stored exactly
        as given, LaTeX escapes included. Refused on duplicate primary key or
        unresolved foreign key. Returns the row, its line and check results."""
        out = _plain(csvdata.insert_row(repo, table, values, expected_hash=expected_sha256))
        out["checks"] = _db_report(repo)
        return out

    @tool(WRITES)
    def csv_update(
        table: str,
        match: dict[str, str],
        values: dict[str, str],
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Change columns of the one row whose columns equal match (the primary
        key, or the whole row for tables without one). Only that line of the file
        changes. A key that other rows reference cannot change: use csv_rename_key."""
        out = _plain(csvdata.update_row(repo, table, match, values, expected_hash=expected_sha256))
        out["checks"] = _db_report(repo)
        return out

    @tool(WRITES)
    def csv_delete(
        table: str, match: dict[str, str], expected_sha256: str | None = None
    ) -> dict[str, Any]:
        """Delete the one row matching match. Refused while rows of other tables
        reference it (the error lists them in referenced_by)."""
        out = _plain(csvdata.delete_row(repo, table, match, expected_hash=expected_sha256))
        out["checks"] = _db_report(repo)
        return out

    @tool(WRITES)
    def csv_rename_key(
        table: str,
        match: dict[str, str],
        new_key: dict[str, str],
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Rename the primary key of one row (e.g. modules {subsystem: vpn,
        label: core} -> {label: engine}) and every CSV row referencing it, in one
        atomic write. .tex files are not changed: tex_references lists each
        reference macro using the old key with its replacement key."""
        out = _plain(csvdata.rename_key(repo, table, match, new_key, expected_hash=expected_sha256))
        out["checks"] = _db_report(repo)
        return out

    # ----------------------------------------------------------------- build

    @tool(WRITES)
    def run_build(target: str) -> dict[str, Any]:
        """Build with make in the n-doc container (can take minutes). Targets:
        all delivery st fsp tds arc ate ref db mwe clean cleanmwe hooks, or a
        document directory. Returns ok, error lines, a log tail and the PDFs that
        were produced, plus a scan of those PDFs for unresolved references."""
        result = build.build(repo, target)
        out = _plain(result)
        if result.ok:
            out["log_tail"] = "\n".join(result.log_tail.splitlines()[-SUCCESS_TAIL_LINES:])
        if result.pdfs:
            out["pdf_checks"] = _report(checks.check_pdf_sanity(repo, result.pdfs))
        return out

    @tool(READ_ONLY)
    def list_build_targets() -> list[str]:
        """All make targets run_build accepts."""
        return build.allowed_targets(repo)

    @tool(READ_ONLY)
    def pdf_search(
        document: str,
        pattern: str,
        regex: bool = False,
        ignore_case: bool = False,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search the built PDF of a document (e.g. "adv_tds") for text, to confirm
        a change reached the output. Line breaks and repeated spaces are ignored,
        so a sentence is found even when the PDF wraps it. Returns page numbers
        with snippets; stale=true means a source file is newer than the PDF
        (run_build first)."""
        return _plain(
            pdf.search_pdf(
                repo,
                document,
                pattern,
                regex=regex,
                ignore_case=ignore_case,
                max_results=max_results,
            )
        )

    # ------------------------------------------------------------------- git

    @tool(READ_ONLY)
    def git_status() -> dict[str, Any]:
        """Current branch, upstream, ahead/behind and changed files (porcelain
        index/worktree codes, '?' = untracked)."""
        st = git.status(repo)
        return {**_plain(st), "clean": st.clean}

    @tool(READ_ONLY)
    def git_diff(
        paths: list[str] | None = None, staged: bool = False, base: str | None = None
    ) -> str:
        """Unified diff of the working tree (staged=true: the index; base: against
        that revision). Untracked files are not included."""
        return git.diff(repo, paths, staged=staged, base=base) or "(no changes)"

    @tool(READ_ONLY)
    def git_log(limit: int = 10, path: str | None = None) -> list[dict[str, Any]]:
        """Recent commits, optionally only those touching a path."""
        return [_plain(c) for c in git.log(repo, limit, path)]

    @tool(WRITES)
    def git_create_branch(name: str, start: str | None = None) -> dict[str, Any]:
        """Create a branch (from start, default HEAD) and switch to it. Working
        tree changes are carried over."""
        return {"branch": git.create_branch(repo, name, start=start)}

    @tool(WRITES)
    def git_switch_branch(name: str) -> dict[str, Any]:
        """Switch to an existing branch; requires no uncommitted changes."""
        return {"branch": git.switch_branch(repo, name)}

    @tool(WRITES)
    def git_commit(message: str, paths: list[str]) -> dict[str, Any]:
        """Commit exactly the given paths (changes, new and deleted files) with
        message. Refused on main/master. Nothing is pushed."""
        sha = git.commit(repo, message, paths)
        return {"sha": sha, "branch": git.current_branch(repo)}

    return mcp


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
    raise SystemExit(f"ndoc-mcp: no n-doc checkout found above {here}; set NDOC_REPO")


def main() -> None:
    host = os.environ.get("NDOC_HOST_REPO")
    repo = Repo(root=find_repo_root(), host_root=Path(host) if host else None)
    create_server(repo).run("stdio")


if __name__ == "__main__":
    main()
