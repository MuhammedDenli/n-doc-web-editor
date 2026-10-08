"""Text of built PDFs (``pdftotext``), e.g. to confirm an edit reached the PDF.

PDFs are addressed by document name only, so the path comes from ``docs`` and
never from the caller.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import docs, files
from .errors import FileNotFoundInRepoError, ToolMissingError
from .repo import Repo

SNIPPET_CONTEXT = 80
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PdfMatch:
    page: int
    snippet: str


@dataclass
class PdfSearchResult:
    document: str
    pdf: str
    pages: int
    stale: bool  # a source file of the document is newer than the PDF
    matches: list[PdfMatch] = field(default_factory=list)
    truncated: bool = False


def page_texts(path: Path, *, layout: bool = False, timeout: float = 120) -> list[str]:
    """Text per page (``pdftotext`` separates pages with form feeds)."""
    if shutil.which("pdftotext") is None:
        raise ToolMissingError("pdftotext is not installed", tool="pdftotext")
    cmd = ["pdftotext", *(["-layout"] if layout else []), str(path), "-"]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", timeout=timeout, check=False
    )
    pages = proc.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()  # pdftotext ends the last page with a form feed
    return pages


def is_stale(repo: Repo, document: str) -> bool:
    pdf = repo.root / docs.get_document(repo, document).pdf_file
    if not pdf.is_file():
        return True
    built = pdf.stat().st_mtime
    return any(
        (repo.root / rel).stat().st_mtime > built for rel in docs.document_files(repo, document)
    )


def search_pdf(
    repo: Repo,
    document: str,
    pattern: str,
    *,
    regex: bool = False,
    ignore_case: bool = False,
    max_results: int = 50,
) -> PdfSearchResult:
    """Search the built PDF of a document.

    Whitespace (including line breaks) is collapsed to single spaces in the page
    text and, for plain patterns, in the pattern too, so a sentence matches even
    when the PDF wraps it across lines.
    """
    doc = docs.get_document(repo, document)
    path = repo.root / doc.pdf_file
    if not path.is_file():
        raise FileNotFoundInRepoError(
            "PDF not built yet; run the build first", path=doc.pdf_file, document=document
        )
    if not regex and isinstance(pattern, str):
        pattern = _WS_RE.sub(" ", pattern).strip()
    rx = files.compile_pattern(pattern, regex=regex, ignore_case=ignore_case)
    limit = max(1, min(int(max_results), 500))
    pages = page_texts(path)
    result = PdfSearchResult(
        document=document, pdf=doc.pdf_file, pages=len(pages), stale=is_stale(repo, document)
    )
    for number, raw in enumerate(pages, start=1):
        text = _WS_RE.sub(" ", raw).strip()
        for m in rx.finditer(text):
            if len(result.matches) >= limit:
                result.truncated = True
                return result
            start, end = max(0, m.start() - SNIPPET_CONTEXT), m.end() + SNIPPET_CONTEXT
            result.matches.append(PdfMatch(page=number, snippet=text[start:end]))
            if m.end() == m.start():
                break  # empty regex match: one hit per page is enough
    return result
