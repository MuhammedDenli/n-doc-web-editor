"""Guarded file access inside the n-doc repository.

* ``resolve_path`` is the single path guard: every other module that touches a
  user/agent supplied path goes through it.
* Reads return the content together with its SHA-256; writes take that hash back
  (``expected_hash``) and refuse to overwrite a file that changed in between.
* Writes are atomic (temp file + ``os.replace``) and serialized by an
  inter-process lock, so the API and the MCP server can run side by side.
* Content is written byte-exactly as given: no newline or encoding conversion.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from .errors import (
    AmbiguousMatchError,
    FileExistsInRepoError,
    FileNotFoundInRepoError,
    FileTooLargeError,
    InvalidContentError,
    InvalidPatternError,
    PathNotAllowedError,
    StaleWriteError,
    TextNotFoundError,
)
from .repo import Repo

MAX_FILE_BYTES = 2 * 1024 * 1024

READ_EXTENSIONS = frozenset(
    {".tex", ".csv", ".bib", ".sty", ".cls", ".md", ".adoc", ".txt", ".lua", ".sql", ".xdy"}
)
WRITE_EXTENSIONS = frozenset({".tex", ".csv", ".bib", ".md", ".txt"})

# Top-level directories that are never exposed (the web layer itself) or never
# writable (build machinery and scripts that run on the host or in the build).
DENY_READ_TOP = frozenset({"web", "deliverables", "node_modules"})
DENY_WRITE_TOP = DENY_READ_TOP | {"engine", "config", "scripts", "lua"}

WRITE_LOCK = "write"

Mode = Literal["read", "write"]


@dataclass(frozen=True)
class FileContent:
    path: str
    text: str
    sha256: str
    size: int


@dataclass(frozen=True)
class WriteResult:
    path: str
    sha256: str
    size: int
    created: bool
    replacements: int | None = None  # set by replace_text


@dataclass(frozen=True)
class SearchMatch:
    path: str
    line: int
    col: int
    text: str


@dataclass
class SearchResult:
    matches: list[SearchMatch]
    truncated: bool


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    writable: bool


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_relpath(rel: str) -> PurePosixPath:
    """Syntactic checks on a repo-relative POSIX path (no filesystem access)."""
    if not isinstance(rel, str) or not rel.strip():
        raise PathNotAllowedError("empty path", path=rel)
    if "\x00" in rel or "\\" in rel:
        raise PathNotAllowedError("invalid character in path", path=rel)
    p = PurePosixPath(rel)
    if p.is_absolute():
        raise PathNotAllowedError("absolute paths are not allowed", path=rel)
    parts = [part for part in p.parts if part not in ("", ".")]
    if not parts:
        raise PathNotAllowedError("empty path", path=rel)
    for part in parts:
        if part == "..":
            raise PathNotAllowedError("'..' is not allowed", path=rel)
        if part.startswith("."):
            raise PathNotAllowedError("hidden files and directories are not allowed", path=rel)
    return PurePosixPath(*parts)


def resolve_path(repo: Repo, rel: str, mode: Mode = "read") -> Path:
    """Map a repo-relative path to an absolute one, enforcing the access policy.

    Symlinks are resolved and the *target* must satisfy the same policy, so a
    link cannot be used to escape the repository or reach a denied area.
    """
    norm = normalize_relpath(rel)
    _check_policy(norm, mode, rel)
    resolved = (repo.root / norm).resolve(strict=False)
    try:
        real_rel = resolved.relative_to(repo.root)
    except ValueError:
        raise PathNotAllowedError("path escapes the repository", path=rel) from None
    if real_rel != Path(norm):
        _check_policy(normalize_relpath(real_rel.as_posix()), mode, rel)
    return resolved


def _check_policy(norm: PurePosixPath, mode: Mode, original: str) -> None:
    top = norm.parts[0]
    deny_top = DENY_WRITE_TOP if mode == "write" else DENY_READ_TOP
    if top in deny_top or (len(norm.parts) == 1 and mode == "write"):
        raise PathNotAllowedError(f"{mode} access to this location is not allowed", path=original)
    allowed = WRITE_EXTENSIONS if mode == "write" else READ_EXTENSIONS
    if norm.suffix.lower() not in allowed:
        raise PathNotAllowedError(
            f"file type '{norm.suffix}' is not allowed for {mode}", path=original
        )


def is_allowed(repo: Repo, rel: str, mode: Mode = "read") -> bool:
    try:
        resolve_path(repo, rel, mode)
    except PathNotAllowedError:
        return False
    return True


def read_file(repo: Repo, rel: str) -> FileContent:
    path = resolve_path(repo, rel, "read")
    data = _read_bytes(path, rel)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidContentError("file is not valid UTF-8", path=rel) from exc
    return FileContent(path=_rel(repo, path), text=text, sha256=sha256_bytes(data), size=len(data))


def file_hash(repo: Repo, rel: str) -> str | None:
    """Current SHA-256 of a file, or None if it does not exist."""
    path = resolve_path(repo, rel, "read")
    if not path.exists():
        return None
    return sha256_bytes(_read_bytes(path, rel))


def write_file(
    repo: Repo,
    rel: str,
    text: str,
    *,
    expected_hash: str | None,
    create: bool = False,
) -> WriteResult:
    """Atomically write ``text`` (UTF-8, byte-exact).

    * Existing file: ``expected_hash`` must equal its current SHA-256.
    * New file: pass ``create=True`` and ``expected_hash=None``; the parent
      directory must already exist.
    """
    path = resolve_path(repo, rel, "write")
    data = _encode(text, rel)
    with repo.lock(WRITE_LOCK):
        exists = path.exists()
        if exists:
            if not path.is_file():
                raise PathNotAllowedError("not a regular file", path=rel)
            if create:
                raise FileExistsInRepoError("file already exists", path=rel)
            current = sha256_bytes(_read_bytes(path, rel))
            if expected_hash != current:
                raise StaleWriteError(
                    "file changed since it was read", path=rel, current_hash=current
                )
        else:
            if not create:
                raise FileNotFoundInRepoError("file does not exist", path=rel)
            if not path.parent.is_dir():
                raise FileNotFoundInRepoError("parent directory does not exist", path=rel)
        _atomic_write(path, data)
    return WriteResult(
        path=_rel(repo, path), sha256=sha256_bytes(data), size=len(data), created=not exists
    )


def replace_text(
    repo: Repo,
    rel: str,
    old: str,
    new: str,
    *,
    expected_hash: str | None = None,
    replace_all: bool = False,
) -> WriteResult:
    """Replace ``old`` by ``new`` in an existing file, atomically.

    ``old`` must occur exactly once unless ``replace_all`` is set, so an edit
    based on an outdated view of the file fails instead of hitting the wrong
    place. ``expected_hash``, if given, must match the current content.
    """
    path = resolve_path(repo, rel, "write")
    if not isinstance(old, str) or not old:
        raise InvalidContentError("text to replace must not be empty", path=rel)
    if old == new:
        raise InvalidContentError("replacement is identical to the original text", path=rel)
    with repo.lock(WRITE_LOCK):
        if path.exists() and not path.is_file():
            raise PathNotAllowedError("not a regular file", path=rel)
        data = _read_bytes(path, rel)
        current = sha256_bytes(data)
        if expected_hash is not None and expected_hash != current:
            raise StaleWriteError("file changed since it was read", path=rel, current_hash=current)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidContentError("file is not valid UTF-8", path=rel) from exc
        count = text.count(old)
        if count == 0:
            raise TextNotFoundError("text to replace not found", path=rel)
        if count > 1 and not replace_all:
            raise AmbiguousMatchError(
                f"text to replace occurs {count} times; add context or set replace_all",
                path=rel,
                occurrences=count,
            )
        out = _encode(text.replace(old, new), rel)
        _atomic_write(path, out)
    return WriteResult(
        path=_rel(repo, path),
        sha256=sha256_bytes(out),
        size=len(out),
        created=False,
        replacements=count,
    )


MAX_PATTERN_LEN = 500


def compile_pattern(pattern: str, *, regex: bool, ignore_case: bool) -> re.Pattern[str]:
    """Validate and compile a user/agent supplied search pattern."""
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_PATTERN_LEN:
        raise InvalidPatternError(
            f"pattern must be 1..{MAX_PATTERN_LEN} characters", pattern=pattern
        )
    flags = re.IGNORECASE if ignore_case else 0
    try:
        return re.compile(pattern if regex else re.escape(pattern), flags)
    except re.error as exc:
        raise InvalidPatternError(f"invalid regular expression: {exc}", pattern=pattern) from None


def search(
    repo: Repo,
    pattern: str,
    *,
    rel_dir: str = "",
    regex: bool = False,
    ignore_case: bool = False,
    max_results: int = 200,
) -> SearchResult:
    """Line-based search over the readable files below ``rel_dir``."""
    rx = compile_pattern(pattern, regex=regex, ignore_case=ignore_case)
    limit = max(1, min(int(max_results), 1000))
    matches: list[SearchMatch] = []
    for entry in list_files(repo, rel_dir):
        if entry.size > MAX_FILE_BYTES:
            continue
        try:
            text = (repo.root / entry.path).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            m = rx.search(line)
            if m:
                if len(matches) >= limit:
                    return SearchResult(matches=matches, truncated=True)
                matches.append(
                    SearchMatch(path=entry.path, line=lineno, col=m.start() + 1, text=line[:300])
                )
    return SearchResult(matches=matches, truncated=False)


def list_files(repo: Repo, rel_dir: str = "") -> list[FileEntry]:
    """Readable files below ``rel_dir`` (recursive, sorted)."""
    base = repo.root
    if rel_dir not in ("", "."):
        norm = normalize_relpath(rel_dir)
        if norm.parts[0] in DENY_READ_TOP:
            raise PathNotAllowedError("read access to this location is not allowed", path=rel_dir)
        base = (repo.root / norm).resolve()
        if not base.is_relative_to(repo.root) or not base.is_dir():
            raise FileNotFoundInRepoError("directory does not exist", path=rel_dir)
    entries: list[FileEntry] = []
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dirpath = Path(dirpath).relative_to(repo.root)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if not d.startswith(".") and not (rel_dirpath == Path(".") and d in DENY_READ_TOP)
        )
        for name in filenames:
            rel = (rel_dirpath / name).as_posix()
            if not is_allowed(repo, rel, "read"):
                continue
            st = (Path(dirpath) / name).stat()
            entries.append(
                FileEntry(path=rel, size=st.st_size, writable=is_allowed(repo, rel, "write"))
            )
    return sorted(entries, key=lambda e: e.path)


def _read_bytes(path: Path, rel: str) -> bytes:
    if not path.exists():
        raise FileNotFoundInRepoError("file does not exist", path=rel)
    if not path.is_file():
        raise PathNotAllowedError("not a regular file", path=rel)
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise FileTooLargeError("file is too large", path=rel, size=size, limit=MAX_FILE_BYTES)
    return path.read_bytes()


def _encode(text: str, rel: str) -> bytes:
    if not isinstance(text, str):
        raise InvalidContentError("content must be text", path=rel)
    if "\x00" in text:
        raise InvalidContentError("content contains NUL bytes", path=rel)
    try:
        data = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidContentError("content is not encodable as UTF-8", path=rel) from exc
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLargeError(
            "content is too large", path=rel, size=len(data), limit=MAX_FILE_BYTES
        )
    return data


def _atomic_write(path: Path, data: bytes) -> None:
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _rel(repo: Repo, path: Path) -> str:
    return path.relative_to(repo.root).as_posix()
