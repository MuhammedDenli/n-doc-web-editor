import pytest

from ndoc_core import files
from ndoc_core.errors import (
    AmbiguousMatchError,
    FileNotFoundInRepoError,
    InvalidContentError,
    InvalidPatternError,
    PathNotAllowedError,
    StaleWriteError,
    TextNotFoundError,
)

EXTRA = "mwe_tds/mwe_tds_extra.tex"
BODY = "mwe_tds/mwe_tds_body.tex"


def test_replace_text_unique(repo):
    before = files.read_file(repo, EXTRA)
    res = files.replace_text(repo, EXTRA, "Extra", "More", expected_hash=before.sha256)
    assert res.replacements == 1
    assert (repo.root / EXTRA).read_bytes() == b"More text.\n"
    assert res.sha256 == files.read_file(repo, EXTRA).sha256


def test_replace_text_keeps_bytes_outside_match(repo):
    path = repo.root / EXTRA
    path.write_bytes(b"a\r\nb x\r\nc")
    files.replace_text(repo, EXTRA, "x", "y")
    assert path.read_bytes() == b"a\r\nb y\r\nc"


def test_replace_text_ambiguous(repo):
    (repo.root / EXTRA).write_text("x x\n", encoding="utf-8")
    with pytest.raises(AmbiguousMatchError) as exc:
        files.replace_text(repo, EXTRA, "x", "y")
    assert exc.value.details["occurrences"] == 2
    res = files.replace_text(repo, EXTRA, "x", "y", replace_all=True)
    assert res.replacements == 2
    assert (repo.root / EXTRA).read_text(encoding="utf-8") == "y y\n"


def test_replace_text_not_found(repo):
    with pytest.raises(TextNotFoundError):
        files.replace_text(repo, EXTRA, "nope", "y")


def test_replace_text_stale(repo):
    with pytest.raises(StaleWriteError):
        files.replace_text(repo, EXTRA, "Extra", "y", expected_hash="0" * 64)
    assert (repo.root / EXTRA).read_text(encoding="utf-8") == "Extra text.\n"


@pytest.mark.parametrize(("old", "new"), [("", "x"), ("Extra", "Extra")])
def test_replace_text_invalid(repo, old, new):
    with pytest.raises(InvalidContentError):
        files.replace_text(repo, EXTRA, old, new)


def test_replace_text_guarded(repo):
    with pytest.raises(PathNotAllowedError):
        files.replace_text(repo, "scripts/check_sfr_consistency.sh", "a", "b")
    with pytest.raises(FileNotFoundInRepoError):
        files.replace_text(repo, "mwe_tds/missing.tex", "a", "b")


def test_search_plain_and_regex(repo):
    res = files.search(repo, r"\sfrlink{fcs_ckm.1}", rel_dir="mwe_tds")
    assert [(m.path, m.line) for m in res.matches] == [(BODY, 2)]
    assert res.matches[0].col == res.matches[0].text.index("\\sfrlink") + 1
    res = files.search(repo, r"\\tdslink\[fq\]\{mod\.", regex=True, rel_dir="mwe_tds")
    assert [m.path for m in res.matches] == [BODY]


def test_search_ignore_case_and_limit(repo):
    assert files.search(repo, "EXTRA TEXT", rel_dir="mwe_tds").matches == []
    res = files.search(repo, "EXTRA TEXT", rel_dir="mwe_tds", ignore_case=True)
    assert [m.path for m in res.matches] == [EXTRA]
    res = files.search(repo, "e", rel_dir="mwe_tds", max_results=1)
    assert len(res.matches) == 1 and res.truncated


def test_search_respects_path_policy(repo):
    with pytest.raises(PathNotAllowedError):
        files.search(repo, "x", rel_dir="web")
    assert all(not m.path.startswith(".git") for m in files.search(repo, "main").matches)


@pytest.mark.parametrize("bad", ["", "(", "x" * 501])
def test_search_invalid_pattern(repo, bad):
    with pytest.raises(InvalidPatternError):
        files.search(repo, bad, regex=True)


def test_write_many_checks_all_hashes_first(repo):
    a, b = files.read_file(repo, EXTRA), files.read_file(repo, BODY)
    with pytest.raises(StaleWriteError):
        files.write_many(repo, {EXTRA: ("new\n", a.sha256), BODY: ("new\n", "0" * 64)})
    assert files.read_file(repo, EXTRA).text == a.text
    res = files.write_many(repo, {EXTRA: ("x\n", a.sha256), BODY: ("y\n", b.sha256)})
    assert [r.path for r in res] == [EXTRA, BODY]
    assert (repo.root / BODY).read_text(encoding="utf-8") == "y\n"
