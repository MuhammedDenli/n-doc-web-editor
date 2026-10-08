"""Non-destructive Git operations on the n-doc repository.

There is deliberately no reset, force, clean, rebase or push here (push and PRs
come later behind a provider interface). Commits name their paths explicitly,
pass the file path guard, and are refused on protected branches.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field

from . import files
from .errors import (
    DirtyWorktreeError,
    GitError,
    InvalidBranchNameError,
    ProtectedBranchError,
)
from .repo import Repo

PROTECTED_BRANCHES = frozenset({"main", "master"})
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$")
MAX_DIFF_BYTES = 1024 * 1024
GIT_LOCK = "git"


@dataclass(frozen=True)
class FileStatus:
    path: str
    index: str  # porcelain X
    worktree: str  # porcelain Y
    orig_path: str | None = None

    @property
    def untracked(self) -> bool:
        return self.index == "?"


@dataclass
class GitStatus:
    branch: str | None
    upstream: str | None
    ahead: int
    behind: int
    files: list[FileStatus] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.files


@dataclass(frozen=True)
class Commit:
    sha: str
    author: str
    date: str
    subject: str


def _git(
    repo: Repo, *args: str, check: bool = True, input_text: str | None = None, timeout: float = 60
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "LC_ALL": "C",
    }
    proc = subprocess.run(
        ["git", "-C", str(repo.root), *args],
        capture_output=True,
        text=True,
        env=env,
        input=input_text,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise GitError(
            f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}",
            returncode=proc.returncode,
        )
    return proc


def status(repo: Repo) -> GitStatus:
    out = _git(repo, "status", "--porcelain=v1", "--branch", "-z", "--untracked-files=all").stdout
    entries = out.split("\0")
    branch = upstream = None
    ahead = behind = 0
    result: list[FileStatus] = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        if entry.startswith("## "):
            branch, upstream, ahead, behind = _parse_branch_line(entry[3:])
            continue
        x, y, path = entry[0], entry[1], entry[3:]
        orig = None
        if x in "RC":
            orig = entries[i]
            i += 1
        result.append(FileStatus(path=path, index=x, worktree=y, orig_path=orig))
    return GitStatus(branch=branch, upstream=upstream, ahead=ahead, behind=behind, files=result)


def _parse_branch_line(line: str) -> tuple[str | None, str | None, int, int]:
    ahead = behind = 0
    m = re.search(r" \[(.*)\]$", line)
    if m:
        line = line[: m.start()]
        for part in m.group(1).split(", "):
            if part.startswith("ahead "):
                ahead = int(part[6:])
            elif part.startswith("behind "):
                behind = int(part[7:])
    if line.startswith("No commits yet on "):
        return line.removeprefix("No commits yet on "), None, 0, 0
    if line.startswith("HEAD (no branch)"):
        return None, None, 0, 0
    branch, _, upstream = line.partition("...")
    return branch, upstream or None, ahead, behind


def current_branch(repo: Repo) -> str | None:
    return status(repo).branch


def list_branches(repo: Repo) -> list[str]:
    out = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout
    return sorted(line for line in out.splitlines() if line)


def diff(
    repo: Repo, paths: list[str] | None = None, *, staged: bool = False, base: str | None = None
) -> str:
    """Unified diff of the working tree (or index / against ``base``)."""
    args = ["diff", "--no-color", "--no-ext-diff"]
    if staged:
        args.append("--cached")
    if base is not None:
        args.append(_validate_rev(repo, base))
    args.append("--")
    args.extend(_guard_paths(repo, paths or []))
    out = _git(repo, *args).stdout
    if len(out.encode()) > MAX_DIFF_BYTES:
        out = out.encode()[:MAX_DIFF_BYTES].decode(errors="ignore") + "\n[... diff truncated ...]\n"
    return out


def log(repo: Repo, limit: int = 20, path: str | None = None) -> list[Commit]:
    args = ["log", f"-n{max(1, min(int(limit), 200))}", "--format=%H%x1f%an%x1f%aI%x1f%s"]
    if path:
        args += ["--", *_guard_paths(repo, [path])]
    proc = _git(repo, *args, check=False)
    if proc.returncode != 0:  # e.g. no commits yet
        return []
    commits = []
    for line in proc.stdout.splitlines():
        sha, author, date, subject = line.split("\x1f", 3)
        commits.append(Commit(sha=sha, author=author, date=date, subject=subject))
    return commits


def show_file(repo: Repo, rev: str, rel: str) -> str | None:
    """Content of ``rel`` at revision ``rev``, or None if it does not exist there."""
    rev = _validate_rev(repo, rev)
    (path,) = _guard_paths(repo, [rel])
    proc = _git(repo, "show", f"{rev}:{path}", check=False)
    return proc.stdout if proc.returncode == 0 else None


def validate_branch_name(repo: Repo, name: str) -> str:
    if (
        not isinstance(name, str)
        or not BRANCH_RE.match(name)
        or ".." in name
        or name.endswith((".lock", "/", "."))
        or "//" in name
    ):
        raise InvalidBranchNameError(f"invalid branch name '{name}'", branch=name)
    if _git(repo, "check-ref-format", "--branch", name, check=False).returncode != 0:
        raise InvalidBranchNameError(f"invalid branch name '{name}'", branch=name)
    return name


def create_branch(repo: Repo, name: str, *, start: str | None = None, checkout: bool = True) -> str:
    validate_branch_name(repo, name)
    if name in PROTECTED_BRANCHES:
        raise ProtectedBranchError(f"'{name}' is protected", branch=name)
    with repo.lock(GIT_LOCK):
        args = ["switch", "-c", name] if checkout else ["branch", name]
        if start is not None:
            args.append(_validate_rev(repo, start))
        _git(repo, *args)
    return name


def switch_branch(repo: Repo, name: str) -> str:
    """Switch to an existing branch; only with a clean working tree."""
    validate_branch_name(repo, name)
    if name not in list_branches(repo):
        raise GitError(f"branch '{name}' does not exist", branch=name)
    with repo.lock(GIT_LOCK):
        st = status(repo)
        if any(not f.untracked for f in st.files):
            raise DirtyWorktreeError(
                "working tree has uncommitted changes",
                files=[f.path for f in st.files if not f.untracked],
            )
        _git(repo, "switch", name)
    return name


def commit(repo: Repo, message: str, paths: list[str], *, author: str | None = None) -> str:
    """Stage exactly ``paths`` and commit them. Returns the new commit SHA.

    Only these paths end up in the commit, even if other changes are staged.
    """
    message = (message or "").strip()
    if not message:
        raise GitError("commit message must not be empty")
    if "\x00" in message:
        raise GitError("invalid commit message")
    if not paths:
        raise GitError("no paths given to commit")
    if author is not None and not re.fullmatch(r"[^<>\n]+ <[^<>\s]+@[^<>\s]+>", author):
        raise GitError("author must look like 'Name <email>'", author=author)
    rels = _guard_paths(repo, paths, mode="write", allow_deleted=True)
    with repo.lock(GIT_LOCK):
        branch = current_branch(repo)
        if branch is None:
            raise GitError("not on a branch (detached HEAD)")
        if branch in PROTECTED_BRANCHES:
            raise ProtectedBranchError(
                f"refusing to commit on protected branch '{branch}'", branch=branch
            )
        _git(repo, "add", "--all", "--", *rels)
        args = ["commit", "-F", "-", "--only"]
        if author:
            args += ["--author", author]
        _git(repo, *args, "--", *rels, input_text=message + "\n")
        return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _validate_rev(repo: Repo, rev: str) -> str:
    if not isinstance(rev, str) or rev.startswith("-") or not re.fullmatch(r"[\w./~^@{}-]+", rev):
        raise GitError(f"invalid revision '{rev}'", rev=rev)
    _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    return rev


def _guard_paths(
    repo: Repo, paths: list[str], *, mode: files.Mode = "read", allow_deleted: bool = False
) -> list[str]:
    rels = []
    for p in paths:
        resolved = files.resolve_path(repo, p, mode)
        if not allow_deleted and not resolved.exists() and mode == "write":
            raise GitError(f"path does not exist: {p}", path=p)
        rels.append(resolved.relative_to(repo.root).as_posix())
    return rels
