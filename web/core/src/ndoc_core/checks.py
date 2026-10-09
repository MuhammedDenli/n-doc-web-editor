"""Static checks run before/after edits and builds.

* ``check_tex_syntax``: brace balance and ``\\begin``/``\\end`` matching.
* ``check_references``: n-doc reference macros (``\\sfrlink{X}``, ``\\tdslink{mod.a.b}``,
  ...) must resolve to a row in ``common/db`` — the same lookups the Lua layer
  does at build time, where a miss only shows up as red "X is undefined" text.
* ``check_sfr_consistency``: wraps ``scripts/check_sfr_consistency.sh``.
* ``check_pdf_sanity``: the ``scripts/sanity_check.sh`` scan, scoped to given PDFs.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from . import csvdata, docs, files, git, pdf
from .errors import ToolMissingError
from .repo import Repo
from .texutil import line_col, strip_comments

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    severity: Severity = "error"
    path: str | None = None
    line: int | None = None
    col: int | None = None


@dataclass
class CheckReport:
    issues: list[Issue] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def extend(self, other: CheckReport) -> CheckReport:
        self.issues.extend(other.issues)
        self.checked.extend(c for c in other.checked if c not in self.checked)
        return self


# --------------------------------------------------------------------------
# LaTeX syntax
# --------------------------------------------------------------------------

_VERBATIM_ENVS = (
    "verbatim",
    "verbatim*",
    "lstlisting",
    "minted",
    "comment",
    "luacode",
    "luacode*",
    "Verbatim",
)
_VERBATIM_RE = re.compile(
    r"\\begin\{(" + "|".join(re.escape(e) for e in _VERBATIM_ENVS) + r")\}.*?\\end\{\1\}",
    re.DOTALL,
)
_VERB_RE = re.compile(r"\\verb\*?(.).*?\1")
_TOKEN_RE = re.compile(r"\\\\|\\[{}]|\\(begin|end)\s*\{([^{}]*)\}|[{}]")
# Definitions may legitimately open an environment in one macro and close it in
# another; environment matching is skipped inside their arguments.
_DEF_RE = re.compile(
    r"\\(?:(?:re|provide)?new(command|environment)\*?|(?:e|g|x)?def(?![A-Za-z@])"
    r"|(?:New|Renew|Provide)Document(Command|Environment))"
)


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))


def _match_brace(src: str, start: int) -> int:
    """Index of the '}' closing the '{' at ``start``, or -1."""
    depth = 0
    i = start
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _definition_spans(src: str) -> list[tuple[int, int]]:
    """Spans of macro/environment definitions (name, parameters and bodies)."""
    spans = []
    for m in _DEF_RE.finditer(src):
        is_env = "nvironment" in m.group(0)
        groups_left = 3 if is_env else 2  # name + body (+ end code)
        i, end, named = m.end(), m.end(), False
        while i < len(src) and groups_left:
            c = src[i]
            if c.isspace():
                i += 1
            elif c == "\\" and not named:  # \newcommand\foo / \def\foo
                j = i + 1
                while j < len(src) and (src[j].isalpha() or src[j] == "@"):
                    j += 1
                i = end = max(j, i + 2)
                named, groups_left = True, groups_left - 1
            elif c == "#":
                i += 2
            elif c == "[":
                j = src.find("]", i)
                if j < 0:
                    break
                i = j + 1
            elif c == "{":
                j = _match_brace(src, i)
                if j < 0:
                    break
                i = end = j + 1
                named, groups_left = True, groups_left - 1
            else:
                break
        spans.append((m.start(), end))
    return spans


def check_tex_syntax(text: str, path: str | None = None) -> list[Issue]:
    src = strip_comments(text)
    src = _VERBATIM_RE.sub(_blank, src)
    src = _VERB_RE.sub(_blank, src)

    issues: list[Issue] = []
    braces: list[int] = []
    envs: list[tuple[str, int]] = []
    def_spans = _definition_spans(src)

    def issue(code: str, msg: str, offset: int) -> None:
        line, col = line_col(src, offset)
        issues.append(Issue(code=code, message=msg, path=path, line=line, col=col))

    for m in _TOKEN_RE.finditer(src):
        tok = m.group(0)
        if tok == "{":
            braces.append(m.start())
        elif tok == "}":
            if not braces:
                issue("unbalanced_brace", "closing '}' without matching '{'", m.start())
            else:
                braces.pop()
        elif m.group(1):
            # definitions may open an environment in one macro and close it in another
            if any(s <= m.start() < e for s, e in def_spans):
                continue
            kind, name = m.group(1), m.group(2).strip()
            if kind == "begin":
                envs.append((name, m.start()))
            elif not envs:
                issue("unbalanced_env", f"\\end{{{name}}} without \\begin{{{name}}}", m.start())
            elif envs[-1][0] != name:
                opened, at = envs[-1]
                line, _ = line_col(src, at)
                issue(
                    "env_mismatch",
                    f"\\end{{{name}}} closes \\begin{{{opened}}} opened on line {line}",
                    m.start(),
                )
                # recover: pop up to a matching begin if there is one
                names = [e[0] for e in envs]
                if name in names:
                    del envs[len(names) - 1 - names[::-1].index(name) :]
            else:
                envs.pop()
    for at in braces:
        issue("unbalanced_brace", "'{' is never closed", at)
    for name, at in envs:
        issue("unclosed_env", f"\\begin{{{name}}} is never closed", at)
    return issues


# --------------------------------------------------------------------------
# References
# --------------------------------------------------------------------------

# macro -> lookup kind; mirrors common/cc_core-macros.tex and lua/cc_core.lua
REFERENCE_MACROS: dict[str, str] = {
    **dict.fromkeys(("sfr", "sfrlink", "sfrplain", "sfrtext"), "sfr"),
    **dict.fromkeys(("tsfi", "tsfilink"), "tsfi"),
    **dict.fromkeys(
        ("secfunc", "secfuncplain", "secfunctext", "secfunclink", "secfuncheadline"), "sf"
    ),
    **dict.fromkeys(("obj", "objplain", "objtext", "objlink"), "obj"),
    **dict.fromkeys(("spd", "spdplain", "spdtext", "spdsource", "spdlink"), "spd"),
    **dict.fromkeys(("subjobj", "subjobjplain", "subjobjtext", "subjobjlink"), "subjobj"),
    **dict.fromkeys(("tds", "tdslink", "tdsplain", "tdsplaintext", "modulechapter"), "tds"),
    "error": "error",
}
# kind -> (csv file, key column); lookups are case-insensitive (COLLATE NOCASE)
_SIMPLE_TABLES: dict[str, tuple[str, str]] = {
    "sfr": ("sfr.csv", "label"),
    "tsfi": ("tsfi.csv", "label"),
    "sf": ("sf.csv", "label"),
    "obj": ("obj.csv", "label"),
    "spd": ("spd.csv", "label"),
    "subjobj": ("subjobj.csv", "label"),
    "error": ("errors.csv", "code"),
}
_REF_RE = re.compile(
    r"\\(" + "|".join(sorted(REFERENCE_MACROS, key=len, reverse=True)) + r")(?![A-Za-z@])"
    r"\*?\s*(?:\[[^\[\]{}]*\]\s*)?\{([^{}]*)\}"
)


@dataclass(frozen=True)
class Reference:
    macro: str
    kind: str
    key: str
    offset: int


@dataclass
class ReferenceIndex:
    """Keys from ``common/db`` used to resolve reference macros."""

    simple: dict[str, set[str]]
    subsystems: set[str]
    modules: set[tuple[str, str]]
    interfaces: set[tuple[str, str, str]]

    @classmethod
    def load(cls, repo: Repo) -> ReferenceIndex:
        def rows(name: str) -> list[dict[str, str]]:
            return csvdata.read_csv_rows(repo, f"{repo.db_dir}/{name}")

        simple = {
            kind: {row[col].strip().lower() for row in rows(name) if row.get(col)}
            for kind, (name, col) in _SIMPLE_TABLES.items()
        }
        subsystems = {r["label"] for r in rows("subsystems.csv")}
        modules = {(r["subsystem"], r["label"]) for r in rows("modules.csv")}
        interfaces = {(r["subsystem"], r["module"], r["label"]) for r in rows("interfaces.csv")}
        return cls(simple, subsystems, modules, interfaces)

    def resolves(self, kind: str, key: str) -> bool:
        if kind == "tds":
            return self._resolve_tds(key)
        return key.lower() in self.simple.get(kind, set())

    def _resolve_tds(self, key: str) -> bool:
        # sub.<s> | mod.<s>.<m> | int.<s>.<m>.<i>; case-sensitive like lua/cc_core.lua
        parts = key.split(".")
        typ, rest = parts[0], parts[1:]
        if typ == "sub" and len(rest) == 1:
            return rest[0] in self.subsystems
        if typ == "mod" and len(rest) == 2:
            return rest[0] in self.subsystems and tuple(rest) in self.modules
        if typ == "int" and len(rest) == 3:
            return (
                rest[0] in self.subsystems
                and (rest[0], rest[1]) in self.modules
                and tuple(rest) in self.interfaces
            )
        return False


def find_references(text: str) -> list[Reference]:
    src = strip_comments(text)
    refs = []
    for m in _REF_RE.finditer(src):
        key = m.group(2).strip()
        if not key or "#" in key or "\\" in key:
            continue  # macro definitions / computed arguments
        refs.append(
            Reference(
                macro=m.group(1), kind=REFERENCE_MACROS[m.group(1)], key=key, offset=m.start()
            )
        )
    return refs


def check_references(index: ReferenceIndex, text: str, path: str | None = None) -> list[Issue]:
    issues = []
    for ref in find_references(text):
        if not index.resolves(ref.kind, ref.key):
            line, col = line_col(text, ref.offset)
            issues.append(
                Issue(
                    code="undefined_reference",
                    message=f"\\{ref.macro}{{{ref.key}}}: '{ref.key}' not found in {ref.kind} data",
                    path=path,
                    line=line,
                    col=col,
                )
            )
    return issues


# --------------------------------------------------------------------------
# File / document level
# --------------------------------------------------------------------------


def check_text(
    repo: Repo, text: str, path: str | None = None, index: ReferenceIndex | None = None
) -> CheckReport:
    """Check unsaved content (e.g. before a write)."""
    index = index or ReferenceIndex.load(repo)
    issues = check_tex_syntax(text, path) + check_references(index, text, path)
    return CheckReport(issues=issues, checked=[path] if path else [])


def check_files(repo: Repo, paths: Iterable[str]) -> CheckReport:
    index = ReferenceIndex.load(repo)
    report = CheckReport()
    for rel in paths:
        if not rel.endswith(".tex"):
            continue
        content = files.read_file(repo, rel)
        report.extend(check_text(repo, content.text, content.path, index))
    return report


def check_document(repo: Repo, name: str) -> CheckReport:
    report = CheckReport()
    for node in docs.input_tree(repo, name).walk():
        if not node.exists and node.note != "dynamic":
            report.issues.append(
                Issue(
                    code="missing_input",
                    message=f"\\input target '{node.path}' not found"
                    + (f" ({node.note})" if node.note else ""),
                    severity="warning",
                    path=node.path,
                    line=node.line,
                )
            )
    return report.extend(check_files(repo, docs.document_files(repo, name)))


def check_all_documents(repo: Repo) -> CheckReport:
    report = CheckReport()
    for doc in docs.list_documents(repo):
        report.extend(check_document(repo, doc.name))
    # files shared by several documents are reported once
    report.issues = list(dict.fromkeys(report.issues))
    return report


# --------------------------------------------------------------------------
# Adapter entry points (shared by the MCP server and the HTTP API)
# --------------------------------------------------------------------------


def is_db_path(repo: Repo, rel: str) -> bool:
    return rel.startswith(f"{repo.db_dir}/") and rel.endswith(".csv")


def check_db(repo: Repo) -> CheckReport:
    """Key/FK validation (violations new since ``HEAD`` are errors) + SFR consistency."""
    return csvdata.validate_db(repo).extend(check_sfr_consistency(repo))


def check_after_write(repo: Repo, rel: str) -> CheckReport | None:
    """The checks to report after ``rel`` was written (None: nothing to check)."""
    if rel.endswith(".tex"):
        return check_files(repo, [rel])
    if is_db_path(repo, rel):
        return check_db(repo)
    return None


def changed_paths(repo: Repo) -> list[str]:
    """Readable files changed in the working tree (deleted ones excluded)."""
    return [
        f.path
        for f in git.status(repo).files
        if f.worktree != "D" and f.index != "D" and files.is_allowed(repo, f.path)
    ]


def run_checks(
    repo: Repo,
    *,
    paths: Iterable[str] | None = None,
    document: str | None = None,
    sfr_consistency: bool | None = None,
    pdfs: Iterable[str] | None = None,
) -> CheckReport:
    """Static checks of ``paths``, or a whole ``document``, or (neither) the
    changed files. ``sfr_consistency`` (default: when CSV data is in scope) adds
    :func:`check_db`; ``pdfs`` scans built PDFs."""
    report = CheckReport()
    if document:
        report.extend(check_document(repo, document))
    scope = list(paths) if paths is not None else ([] if document else changed_paths(repo))
    report.extend(check_files(repo, scope))
    if sfr_consistency is None:
        sfr_consistency = any(is_db_path(repo, p) for p in scope)
    if sfr_consistency:
        report.extend(check_db(repo))
    if pdfs:
        report.extend(check_pdf_sanity(repo, pdfs))
    return report


@dataclass(frozen=True)
class ReferenceKey:
    key: str
    name: str = ""


def reference_keys(repo: Repo) -> dict[str, list[ReferenceKey]]:
    """Valid keys per reference kind, for editor completion. ``tds`` keys are
    ``sub.<s>``, ``mod.<s>.<m>`` and ``int.<s>.<m>.<i>``."""

    def rows(name: str) -> list[dict[str, str]]:
        return csvdata.read_csv_rows(repo, f"{repo.db_dir}/{name}")

    out: dict[str, list[ReferenceKey]] = {}
    for kind, (name, col) in _SIMPLE_TABLES.items():
        keys: dict[str, ReferenceKey] = {}
        for r in rows(name):
            key = (r.get(col) or "").strip()
            if key:
                keys.setdefault(key, ReferenceKey(key, r.get("name") or r.get("msg") or ""))
        out[kind] = list(keys.values())
    tds = [ReferenceKey(f"sub.{r['label']}", r.get("name") or "") for r in rows("subsystems.csv")]
    tds += [
        ReferenceKey(f"mod.{r['subsystem']}.{r['label']}", r.get("name") or "")
        for r in rows("modules.csv")
    ]
    tds += [
        ReferenceKey(f"int.{r['subsystem']}.{r['module']}.{r['label']}", r.get("name") or "")
        for r in rows("interfaces.csv")
    ]
    index = ReferenceIndex.load(repo)  # drops keys of dangling rows (e.g. a missing module)
    out["tds"] = [k for k in dict.fromkeys(tds) if index.resolves("tds", k.key)]
    return out


# --------------------------------------------------------------------------
# Wrapped scripts
# --------------------------------------------------------------------------

SFR_SCRIPT = "scripts/check_sfr_consistency.sh"
_SANITY_PATTERNS = ("is undefined", "To Do")  # same as scripts/sanity_check.sh


def check_sfr_consistency(repo: Repo, *, timeout: float = 120) -> CheckReport:
    """Run ``scripts/check_sfr_consistency.sh`` and turn its output into issues."""
    proc = subprocess.run(
        ["bash", SFR_SCRIPT],
        cwd=repo.root,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        check=False,
    )
    return parse_sfr_consistency(proc.stdout, repo.db_dir)


def parse_sfr_consistency(output: str, db_dir: str = "common/db") -> CheckReport:
    report = CheckReport(checked=[SFR_SCRIPT])
    section, current = "forward", None
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("Reverse check"):
            section = "reverse"
        elif line.startswith("duplicate check"):
            section = "duplicate"
        elif line.startswith("checking "):
            current = line.removeprefix("checking ").strip()
        elif section == "duplicate" and line.endswith(".csv:"):
            current = line[:-1]
        elif line.endswith(" missing") and current:
            key = line.removesuffix(" missing")
            if section == "forward":
                msg = f"SFR '{key}' from sfr.csv has no entry in {current}"
            else:
                msg = f"'{key}' in {current} is not defined in sfr.csv"
            report.issues.append(
                Issue(code="sfr_inconsistent", message=msg, path=f"{db_dir}/{current}")
            )
        elif section == "duplicate" and current and (m := re.match(r"^(\d+)\s+(.+)$", line)):
            report.issues.append(
                Issue(
                    code="duplicate_row",
                    severity="warning",
                    message=f"row '{m.group(2)}' appears {m.group(1)} times",
                    path=f"{db_dir}/{current}",
                )
            )
    return report


def check_pdf_sanity(
    repo: Repo, pdfs: Iterable[str] | None = None, *, timeout: float = 120
) -> CheckReport:
    """Search built PDFs for unresolved references ("is undefined") and "To Do"."""
    if pdfs is None:
        pdfs = [d.pdf_file for d in docs.list_documents(repo) if d.pdf_exists]
    pdfs = list(pdfs)
    report = CheckReport(checked=pdfs)
    for rel in pdfs:
        path = (repo.root / rel).resolve()
        if not path.is_relative_to(repo.root) or path.suffix != ".pdf" or not path.is_file():
            report.issues.append(
                Issue(code="missing_pdf", severity="warning", message="PDF not found", path=rel)
            )
            continue
        try:
            pages = pdf.page_texts(path, layout=True, timeout=timeout)
        except ToolMissingError:
            report.issues.append(
                Issue(
                    code="tool_missing",
                    severity="warning",
                    message="pdftotext not installed; PDF sanity check skipped",
                )
            )
            return report
        for page, page_text in enumerate(pages, start=1):
            for line in page_text.splitlines():
                for pattern in _SANITY_PATTERNS:
                    if pattern in line:
                        report.issues.append(
                            Issue(
                                code="pdf_undefined" if pattern == "is undefined" else "pdf_todo",
                                severity="error" if pattern == "is undefined" else "warning",
                                message=f"page {page}: {line.strip()}",
                                path=rel,
                            )
                        )
    return report
