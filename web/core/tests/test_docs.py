import pytest

from ndoc_core import docs
from ndoc_core.errors import UnknownDocumentError


def test_makefile_vars_expand_references(repo):
    variables = docs.makefile_vars(repo)
    assert variables["ST_DIR"] == "ase"
    assert variables["PDF_DIRS"].split() == [
        "ate_cov",
        "adv_tds",
        "ase",
        "adv_fsp",
        "alc",
        "adv_arc",
        "reflist",
    ]
    assert "mwe_tds" in variables["MWE_DIRS"].split()


def test_list_documents(repo):
    by_name = {d.name: d for d in docs.list_documents(repo)}
    assert by_name["adv_tds"].kind == "pdf"
    assert by_name["adv_tds"].main_file == "adv_tds/adv_tds.tex"
    assert by_name["adv_tds"].pdf_file == "adv_tds/adv_tds.pdf"
    assert by_name["mwe_tds"].kind == "mwe"
    assert "mwe_tds" not in {d.name for d in docs.list_documents(repo, include_mwe=False)}


def test_unknown_document(repo):
    with pytest.raises(UnknownDocumentError):
        docs.get_document(repo, "../etc")


def test_input_tree_resolves_relative_and_extensionless(repo):
    tree = docs.input_tree(repo, "mwe_tds")
    assert tree.path == "mwe_tds/mwe_tds.tex"
    paths = [n.path for n in tree.walk()]
    assert "common/common-preamble.tex" in paths  # \input{../common/common-preamble}
    assert "adv_tds/internal_macros.tex" in paths
    assert "mwe_tds/mwe_tds_body.tex" in paths
    assert "mwe_tds/mwe_tds_extra.tex" in paths  # nested
    assert all(n.exists for n in tree.walk() if n.note is None)


def test_input_tree_reports_missing_and_ignores_comments(repo):
    body = repo.root / "mwe_tds/mwe_tds_body.tex"
    body.write_text("\\input{gone}\n% \\input{commented}\n", encoding="utf-8")
    nodes = {n.path: n for n in docs.input_tree(repo, "mwe_tds").walk()}
    assert nodes["mwe_tds/gone.tex"].exists is False
    assert nodes["mwe_tds/gone.tex"].line == 1
    assert "mwe_tds/commented.tex" not in nodes


def test_input_tree_detects_cycles_and_escapes(repo):
    (repo.root / "mwe_tds/mwe_tds_extra.tex").write_text(
        "\\input{mwe_tds_body}\n\\input{../../../etc/passwd}\n\\input{#1}\n", encoding="utf-8"
    )
    nodes = list(docs.input_tree(repo, "mwe_tds").walk())
    notes = {n.path: n.note for n in nodes if n.note}
    assert notes["mwe_tds/mwe_tds_body.tex"] == "cycle"
    assert notes["../../../etc/passwd"] == "not allowed"
    assert notes["#1"] == "dynamic"


def test_document_files_unique_and_main_first(repo):
    files_ = docs.document_files(repo, "adv_tds")
    assert files_[0] == "adv_tds/adv_tds.tex"
    assert len(files_) == len(set(files_))
    assert "adv_tds/module/vpn/core.tex" in files_


def test_pdf_path(repo):
    assert docs.pdf_path(repo, "mwe_tds") is None
    (repo.root / "mwe_tds/mwe_tds.pdf").write_bytes(b"%PDF-1.5")
    assert docs.pdf_path(repo, "mwe_tds") == repo.root / "mwe_tds/mwe_tds.pdf"
