"""``ndoc-check <file>...``: core checks for files edited outside the MCP tools.

Used by the Claude Code PostToolUse hook after a native Write/Edit. Files that
are not n-doc content (outside the repo, denied by the path policy, not .tex or
CSV data) are ignored. CSV edits also run the key/foreign key check; only
violations that are not already at HEAD count as errors. Errors go to stderr
with exit code 2, which Claude Code feeds back to the model; warnings alone
exit 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ndoc_core import CoreError, Repo, checks, files

from .server import find_repo_root


def _relative(repo: Repo, arg: str) -> str | None:
    path = Path(arg)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        rel = path.resolve().relative_to(repo.root).as_posix()
    except ValueError:
        return None
    return rel if files.is_allowed(repo, rel, "write") else None


def run(argv: list[str]) -> int:
    repo = Repo(find_repo_root())
    rels = [r for r in (_relative(repo, a) for a in argv) if r]
    tex = [r for r in rels if r.endswith(".tex")]
    csv = any(checks.is_db_path(repo, r) for r in rels)
    if not tex and not csv:
        return 0
    try:
        report = checks.check_files(repo, tex)
        if csv:
            report.extend(checks.check_db(repo))
    except CoreError as exc:
        print(f"ndoc-check: {exc.code}: {exc.message}", file=sys.stderr)
        return 2
    errors = [i for i in report.issues if i.severity == "error"]
    if not errors:
        return 0
    print(f"n-doc checks found {len(errors)} error(s):", file=sys.stderr)
    for i in errors:
        where = ":".join(str(x) for x in (i.path, i.line, i.col) if x is not None)
        print(f"  {where}: [{i.code}] {i.message}", file=sys.stderr)
    return 2


def main() -> None:
    sys.exit(run(sys.argv[1:]))
