import shutil

import pytest

from ndoc_core import checks

# ---------------------------------------------------------------- syntax


def codes(issues):
    return [i.code for i in issues]


@pytest.mark.parametrize(
    "text",
    [
        r"\section{A} \textbf{b}",
        r"\{ escaped braces \} and \\ newline",
        "% { unbalanced in comment\n\\begin{itemize}\\item x\\end{itemize}",
        r"100\% {ok}",
        "\\begin{verbatim}\n{ \\begin{x}\n\\end{verbatim}",
        r"\verb|{| and \verb+\end{x}+",
        r"\newcommand{\startlist}{\begin{itemize}}\newcommand{\stoplist}{\end{itemize}}",
        r"\newenvironment{box}[1]{\begin{center}#1}{\end{center}}",
        r"\def\foo#1{\begin{quote}#1}",
    ],
)
def test_syntax_ok(text):
    assert checks.check_tex_syntax(text) == []


def test_unclosed_brace_reports_position():
    issues = checks.check_tex_syntax("line one\n\\textbf{oops\n")
    assert codes(issues) == ["unbalanced_brace"]
    assert (issues[0].line, issues[0].col) == (2, 8)


def test_extra_closing_brace():
    assert codes(checks.check_tex_syntax("a}")) == ["unbalanced_brace"]


def test_env_mismatch_and_unclosed():
    issues = checks.check_tex_syntax(
        "\\begin{itemize}\n\\begin{enumerate}\n\\end{itemize}\n\\begin{table}"
    )
    assert codes(issues) == ["env_mismatch", "unclosed_env"]
    assert issues[0].line == 3
    assert "line 2" in issues[0].message


def test_end_without_begin():
    assert codes(checks.check_tex_syntax(r"\end{figure}")) == ["unbalanced_env"]


# ---------------------------------------------------------------- references


@pytest.fixture
def index(repo):
    return checks.ReferenceIndex.load(repo)


@pytest.mark.parametrize(
    "text",
    [
        r"\sfrlink{fcs_ckm.1}",
        r"\sfrlink{FCS_CKM.1}",  # COLLATE NOCASE
        r"\sfr[(2)]{fcs_ckm.1}",
        r"\tsfilink{ls.led}",
        r"\secfunclink{sf.networkservices}",
        r"\obj{o.admin}",
        r"\spdlink{t.wan.client}",
        r"\subjobj{s_admin}",
        r"\tdslink{sub.vpn}",
        r"\tdslink[fq]{mod.vpn.core}",
        r"\tdslink[fq]{int.vpn.core.connect}",
        r"\modulechapter{mod.vpn.cert}",
        r"\error{1}",
        r"\newcommand{\x}[1]{\sfrlink{#1}}",  # definition, not a reference
        "% \\sfrlink{YOK}",
        r"\sfrlinkextra{YOK}",  # different macro
    ],
)
def test_references_resolve(index, text):
    assert checks.check_references(index, text) == []


@pytest.mark.parametrize(
    "text",
    [
        r"\sfrlink{YOK}",
        r"\sfr{fcs_ckm.9}",
        r"\tsfilink{ls.nope}",
        r"\tdslink{sub.VPN}",  # tds lookups are case-sensitive
        r"\tdslink[fq]{mod.vpn.nope}",
        r"\tdslink[fq]{mod.tls.connect}",  # module of another subsystem
        r"\tdslink[fq]{int.vpn.core.nope}",
        r"\tdslink[fq]{int.vpn.cert.connect}",  # interface of another module
        r"\tdslink{vpn}",
        r"\obj{o.none}",
        r"\error{999}",
    ],
)
def test_undefined_reference_is_caught(index, text):
    issues = checks.check_references(index, "Text\n  " + text)
    assert codes(issues) == ["undefined_reference"]
    assert (issues[0].line, issues[0].col) == (2, 3)


def test_check_files_on_fixture_document(repo):
    report = checks.check_document(repo, "mwe_tds")
    assert report.ok, report.issues
    assert "mwe_tds/mwe_tds_body.tex" in report.checked


def test_broken_reference_in_document_fails(repo):
    body = repo.root / "mwe_tds/mwe_tds_body.tex"
    body.write_text(body.read_text() + "\\sfrlink{YOK}\n", encoding="utf-8")
    report = checks.check_document(repo, "mwe_tds")
    assert not report.ok
    [issue] = report.issues
    assert issue.path == "mwe_tds/mwe_tds_body.tex"
    assert issue.line == 4


def test_missing_input_is_a_warning(repo):
    (repo.root / "mwe_tds/mwe_tds_extra.tex").write_text("\\input{gone}\n")
    report = checks.check_document(repo, "mwe_tds")
    assert report.ok
    assert codes(report.issues) == ["missing_input"]


def test_check_text_uses_unsaved_content(repo):
    report = checks.check_text(repo, "\\tdslink{sub.nope} {", "mwe_tds/x.tex")
    assert sorted(codes(report.issues)) == ["unbalanced_brace", "undefined_reference"]


def test_real_repository_documents_are_clean(real_repo):
    """Baseline: every document of the checkout passes (no false positives)."""
    report = checks.check_all_documents(real_repo)
    errors = [i for i in report.issues if i.severity == "error"]
    assert errors == []
    assert len(report.checked) > 50


# ---------------------------------------------------------------- wrapped scripts

SFR_OUTPUT = """checking sfr_module.csv
fcs_new.1 missing
Please check sfr_module.csv for consistency

checking sfr_obj.csv
sfr_obj.csv OK

---------------------------------------------------
Reverse check:
checking sfr_tsfi.csv
fzz_old.1 missing
Please check sfr_tsfi.csv for consistency

---------------------------------------------------
duplicate check:
sfr.csv:
sfr_obj.csv:
      2 fpt_stm.1;o.timeservice
"""


def test_parse_sfr_consistency():
    report = checks.parse_sfr_consistency(SFR_OUTPUT)
    assert [(i.code, i.severity, i.path) for i in report.issues] == [
        ("sfr_inconsistent", "error", "common/db/sfr_module.csv"),
        ("sfr_inconsistent", "error", "common/db/sfr_tsfi.csv"),
        ("duplicate_row", "warning", "common/db/sfr_obj.csv"),
    ]
    assert "fcs_new.1" in report.issues[0].message
    assert "not defined in sfr.csv" in report.issues[1].message


def test_sfr_consistency_script_on_fixture(repo):
    report = checks.check_sfr_consistency(repo)
    assert report.ok, report.issues


def test_sfr_consistency_detects_new_unmapped_sfr(repo):
    sfr = repo.root / "common/db/sfr.csv"
    sfr.write_text(sfr.read_text() + "fzz_abc.1;FZZ\\_ABC.1;New;6.2.x\n")
    report = checks.check_sfr_consistency(repo)
    assert not report.ok
    assert {i.path for i in report.issues if i.code == "sfr_inconsistent"} >= {
        "common/db/sfr_module.csv",
        "common/db/sfr_tsfi.csv",
    }


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
def test_pdf_sanity_on_built_mwe(real_repo):
    pdf = real_repo.root / "mwe_tds/mwe_tds.pdf"
    if not pdf.is_file():
        pytest.skip("mwe_tds.pdf not built")
    report = checks.check_pdf_sanity(real_repo, ["mwe_tds/mwe_tds.pdf"])
    # mwe documents have no releases.csv entry -> "Dokumentversion mwe_tds is undefined"
    assert any(
        i.code == "pdf_undefined" and "mwe_tds is undefined" in i.message for i in report.issues
    )


def test_pdf_sanity_missing_pdf(repo):
    report = checks.check_pdf_sanity(repo, ["mwe_tds/mwe_tds.pdf", "../x.pdf"])
    assert codes(report.issues) in (["missing_pdf", "missing_pdf"], ["tool_missing"])
