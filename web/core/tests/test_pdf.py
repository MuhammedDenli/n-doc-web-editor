import os
import shutil

import pytest

from ndoc_core import pdf
from ndoc_core.errors import (
    FileNotFoundInRepoError,
    InvalidPatternError,
    ToolMissingError,
    UnknownDocumentError,
)

PDF = "mwe_tds/mwe_tds.pdf"
PAGES = [
    "Title page\nMauveVPN Client\n",
    "Module core implements the\nTLS protocol. Only TLS 1.2 and\n1.3 are accepted.\n",
    "Appendix: TLS again.\n",
]


@pytest.fixture
def built(repo, monkeypatch):
    """A 'built' mwe_tds PDF, newer than its sources, with fake page texts."""
    path = repo.root / PDF
    path.write_bytes(b"%PDF-1.5\n")
    newest = max((repo.root / "mwe_tds").rglob("*.tex"), key=lambda p: p.stat().st_mtime)
    t = newest.stat().st_mtime + 10
    os.utime(path, (t, t))
    monkeypatch.setattr(pdf, "page_texts", lambda *a, **k: PAGES)
    return path


def test_finds_sentence_wrapped_across_lines(repo, built):
    res = pdf.search_pdf(repo, "mwe_tds", "Only TLS 1.2 and 1.3 are accepted.")
    assert res.pdf == PDF and res.pages == 3 and not res.stale
    assert [m.page for m in res.matches] == [2]
    assert "TLS protocol. Only TLS 1.2 and 1.3 are accepted." in res.matches[0].snippet


def test_regex_case_and_limit(repo, built):
    assert pdf.search_pdf(repo, "mwe_tds", "tls").matches == []
    res = pdf.search_pdf(repo, "mwe_tds", "tls", ignore_case=True)
    assert [m.page for m in res.matches] == [2, 2, 3]
    res = pdf.search_pdf(repo, "mwe_tds", r"TLS\s+\w", regex=True, max_results=1)
    assert len(res.matches) == 1 and res.truncated


def test_stale_when_source_is_newer(repo, built):
    extra = repo.root / "mwe_tds/mwe_tds_extra.tex"
    t = built.stat().st_mtime + 10
    os.utime(extra, (t, t))
    assert pdf.search_pdf(repo, "mwe_tds", "TLS").stale


def test_missing_pdf_and_unknown_document(repo):
    (repo.root / PDF).unlink(missing_ok=True)
    with pytest.raises(FileNotFoundInRepoError):
        pdf.search_pdf(repo, "mwe_tds", "x")
    with pytest.raises(UnknownDocumentError):
        pdf.search_pdf(repo, "../etc", "x")


@pytest.mark.parametrize("bad", ["", "(", "x" * 501])
def test_invalid_pattern(repo, built, bad):
    with pytest.raises(InvalidPatternError):
        pdf.search_pdf(repo, "mwe_tds", bad, regex=True)


def test_tool_missing(repo, monkeypatch):
    monkeypatch.setattr(pdf.shutil, "which", lambda _: None)
    with pytest.raises(ToolMissingError):
        pdf.page_texts(repo.root / PDF)


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_real_pdf_wrapped_sentence(real_repo):
    if not (real_repo.root / PDF).is_file():
        pytest.skip("mwe_tds.pdf not built")
    res = pdf.search_pdf(real_repo, "mwe_tds", "einen Rahmen dar, in dem Funktionen")
    assert len(res.matches) == 1
