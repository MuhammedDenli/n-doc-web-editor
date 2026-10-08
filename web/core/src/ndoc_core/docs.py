"""Document discovery (root ``Makefile``) and the ``\\input`` tree of a document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from . import files
from .errors import CoreError, PathNotAllowedError, UnknownDocumentError
from .repo import Repo
from .texutil import strip_comments

_VAR_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*:?=\s*(.*?)\s*$")
_REF_RE = re.compile(r"\$\(([A-Z][A-Z0-9_]*)\)")
_INPUT_RE = re.compile(r"\\(input|include)\s*\{([^{}]*)\}")

DOC_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

Kind = Literal["pdf", "mwe"]


@dataclass(frozen=True)
class Document:
    name: str
    kind: Kind
    main_file: str
    pdf_file: str
    pdf_exists: bool


@dataclass
class InputNode:
    path: str
    exists: bool
    children: list[InputNode] = field(default_factory=list)
    line: int | None = None  # line of the \input in the parent
    note: str | None = None  # "cycle", "not allowed", "dynamic"

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


def makefile_vars(repo: Repo) -> dict[str, str]:
    """Simple ``NAME := value`` assignments of the root Makefile, refs expanded."""
    raw: dict[str, str] = {}
    for line in (repo.root / "Makefile").read_text(encoding="utf-8").splitlines():
        m = _VAR_RE.match(line.split("#", 1)[0])
        if m:
            raw[m.group(1)] = m.group(2)

    def expand(value: str, depth: int = 0) -> str:
        if depth > 10:
            raise CoreError("Makefile variable expansion too deep")
        return _REF_RE.sub(lambda m: expand(raw.get(m.group(1), ""), depth + 1), value)

    return {k: expand(v) for k, v in raw.items()}


def list_documents(repo: Repo, *, include_mwe: bool = True) -> list[Document]:
    variables = makefile_vars(repo)
    result: list[Document] = []
    kinds: list[tuple[str, Kind]] = [("PDF_DIRS", "pdf")]
    if include_mwe:
        kinds.append(("MWE_DIRS", "mwe"))
    for var, kind in kinds:
        for name in variables.get(var, "").split():
            if not DOC_NAME_RE.match(name):
                continue
            pdf = f"{name}/{name}.pdf"
            result.append(
                Document(
                    name=name,
                    kind=kind,
                    main_file=f"{name}/{name}.tex",
                    pdf_file=pdf,
                    pdf_exists=(repo.root / pdf).is_file(),
                )
            )
    return result


def get_document(repo: Repo, name: str) -> Document:
    for doc in list_documents(repo):
        if doc.name == name:
            return doc
    raise UnknownDocumentError(f"unknown document '{name}'", document=name)


def pdf_path(repo: Repo, name: str) -> Path | None:
    """Absolute path of the built PDF of a known document, if it exists."""
    doc = get_document(repo, name)
    path = repo.root / doc.pdf_file
    return path if path.is_file() else None


def input_tree(repo: Repo, name: str) -> InputNode:
    """Follow ``\\input``/``\\include`` from the document's main file.

    LaTeX runs inside the document directory (``make -C <dir>``), so relative
    paths resolve against it; ``.tex`` is appended when there is no extension.
    """
    doc = get_document(repo, name)
    doc_dir = PurePosixPath(doc.name)
    return _build_node(repo, doc.main_file, doc_dir, stack=())


def document_files(repo: Repo, name: str) -> list[str]:
    """All existing files reachable from the document, main file first."""
    seen: list[str] = []
    for node in input_tree(repo, name).walk():
        if node.exists and node.path not in seen:
            seen.append(node.path)
    return seen


def _build_node(
    repo: Repo, rel: str, doc_dir: PurePosixPath, stack: tuple[str, ...], line: int | None = None
) -> InputNode:
    if rel in stack:
        return InputNode(path=rel, exists=True, line=line, note="cycle")
    try:
        path = files.resolve_path(repo, rel, "read")
    except PathNotAllowedError:
        return InputNode(path=rel, exists=False, line=line, note="not allowed")
    if not path.is_file():
        return InputNode(path=rel, exists=False, line=line)
    node = InputNode(path=rel, exists=True, line=line)
    text = strip_comments(files.read_file(repo, rel).text)
    for target, target_line in _inputs(text):
        if "#" in target or "\\" in target:
            node.children.append(
                InputNode(path=target, exists=False, line=target_line, note="dynamic")
            )
            continue
        child_rel = _resolve_input(doc_dir, target)
        if child_rel is None:
            node.children.append(
                InputNode(path=target, exists=False, line=target_line, note="not allowed")
            )
            continue
        node.children.append(_build_node(repo, child_rel, doc_dir, (*stack, rel), target_line))
    return node


def _inputs(text: str):
    for m in _INPUT_RE.finditer(text):
        yield m.group(2).strip(), text.count("\n", 0, m.start()) + 1


def _resolve_input(doc_dir: PurePosixPath, target: str) -> str | None:
    p = PurePosixPath(target)
    if not p.suffix:
        p = p.with_suffix(".tex")
    parts: list[str] = list(doc_dir.parts)
    for part in p.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts) if parts else None
