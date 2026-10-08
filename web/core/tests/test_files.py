import os
import threading
from pathlib import Path

import pytest

from ndoc_core import files
from ndoc_core.errors import (
    FileExistsInRepoError,
    FileNotFoundInRepoError,
    FileTooLargeError,
    InvalidContentError,
    PathNotAllowedError,
    StaleWriteError,
)

BODY = "mwe_tds/mwe_tds_body.tex"


@pytest.mark.parametrize(
    "bad",
    [
        "../outside.tex",
        "common/../../outside.tex",
        "/etc/passwd",
        "",
        "   ",
        ".git/config",
        "common/.hidden.tex",
        "web/core/pyproject.toml",
        "web/README-web.md",
        "common\\notation.tex",
        "common/notation.tex\x00.csv",
        "common/db/createdb.sh",
        "mwe_tds/mwe_tds.pdf",
        "Makefile",
    ],
)
def test_read_rejects_unsafe_paths(repo, bad):
    with pytest.raises(PathNotAllowedError):
        files.resolve_path(repo, bad, "read")


@pytest.mark.parametrize(
    "bad",
    [
        "scripts/check_sfr_consistency.tex",
        "lua/x.tex",
        "engine/x.tex",
        "config/x.tex",
        "toplevel.tex",
        "common/db/create_tables.sql",
        "adv_tds/x.lua",
    ],
)
def test_write_rejects_protected_locations(repo, bad):
    with pytest.raises(PathNotAllowedError):
        files.resolve_path(repo, bad, "write")


def test_symlink_escaping_repo_is_rejected(repo, tmp_path):
    outside = tmp_path / "secret.tex"
    outside.write_text("secret")
    (repo.root / "common" / "link.tex").symlink_to(outside)
    with pytest.raises(PathNotAllowedError):
        files.read_file(repo, "common/link.tex")


def test_symlink_into_denied_area_is_rejected(repo):
    (repo.root / "web").mkdir()
    (repo.root / "web" / "x.tex").write_text("x")
    (repo.root / "common" / "link.tex").symlink_to(repo.root / "web" / "x.tex")
    with pytest.raises(PathNotAllowedError):
        files.read_file(repo, "common/link.tex")


def test_read_returns_text_and_hash(repo):
    content = files.read_file(repo, BODY)
    raw = (repo.root / BODY).read_bytes()
    assert content.text == raw.decode()
    assert content.sha256 == files.sha256_bytes(raw)
    assert content.path == BODY
    assert content.size == len(raw)


def test_read_normalizes_dot_segments(repo):
    assert files.read_file(repo, "./mwe_tds//mwe_tds_body.tex").path == BODY


def test_read_missing_file(repo):
    with pytest.raises(FileNotFoundInRepoError):
        files.read_file(repo, "common/nope.tex")


def test_read_rejects_non_utf8(repo):
    (repo.root / "common" / "latin1.tex").write_bytes("Gr\xfc\xdfe".encode("latin-1"))
    with pytest.raises(InvalidContentError):
        files.read_file(repo, "common/latin1.tex")


def test_write_with_matching_hash(repo):
    before = files.read_file(repo, BODY)
    result = files.write_file(repo, BODY, before.text + "Neu.\n", expected_hash=before.sha256)
    after = files.read_file(repo, BODY)
    assert after.text.endswith("Neu.\n")
    assert result.sha256 == after.sha256
    assert not result.created


def test_stale_write_is_rejected_and_file_untouched(repo):
    before = files.read_file(repo, BODY)
    (repo.root / BODY).write_text("changed elsewhere\n")
    with pytest.raises(StaleWriteError) as exc:
        files.write_file(repo, BODY, "mine\n", expected_hash=before.sha256)
    assert (repo.root / BODY).read_text() == "changed elsewhere\n"
    assert exc.value.details["current_hash"] == files.file_hash(repo, BODY)


def test_write_existing_without_hash_is_rejected(repo):
    with pytest.raises(StaleWriteError):
        files.write_file(repo, BODY, "x\n", expected_hash=None)


@pytest.mark.parametrize("rel", ["common/db/subjobj.csv", "common/db/sfr.csv"])
def test_unchanged_roundtrip_is_byte_exact(repo, rel):
    raw = (repo.root / rel).read_bytes()
    content = files.read_file(repo, rel)
    files.write_file(repo, rel, content.text, expected_hash=content.sha256)
    assert (repo.root / rel).read_bytes() == raw


def test_subjobj_csv_has_no_trailing_newline(repo):
    # guards the fixture assumption used above
    assert not (repo.root / "common/db/subjobj.csv").read_bytes().endswith(b"\n")


def test_write_preserves_crlf_and_escapes(repo):
    text = "a;O.TLS\\_Crypto;SF.Net\\-work\r\nb;c;d"
    files.write_file(repo, "common/new.csv", text, expected_hash=None, create=True)
    assert (repo.root / "common/new.csv").read_bytes() == text.encode()


def test_create_new_file(repo):
    result = files.write_file(repo, "mwe_tds/new.tex", "Hallo\n", expected_hash=None, create=True)
    assert result.created
    assert (repo.root / "mwe_tds/new.tex").read_text() == "Hallo\n"


def test_create_existing_file_is_rejected(repo):
    with pytest.raises(FileExistsInRepoError):
        files.write_file(repo, BODY, "x", expected_hash=None, create=True)


def test_create_in_missing_directory_is_rejected(repo):
    with pytest.raises(FileNotFoundInRepoError):
        files.write_file(repo, "nodir/new.tex", "x", expected_hash=None, create=True)


def test_write_missing_without_create_is_rejected(repo):
    with pytest.raises(FileNotFoundInRepoError):
        files.write_file(repo, "mwe_tds/none.tex", "x", expected_hash=None)


def test_write_rejects_nul_and_oversize(repo):
    with pytest.raises(InvalidContentError):
        files.write_file(repo, "mwe_tds/n.tex", "a\x00b", expected_hash=None, create=True)
    with pytest.raises(FileTooLargeError):
        files.write_file(
            repo, "mwe_tds/n.tex", "x" * (files.MAX_FILE_BYTES + 1), expected_hash=None, create=True
        )


def test_write_preserves_mode_and_leaves_no_temp_files(repo):
    path = repo.root / BODY
    os.chmod(path, 0o640)
    content = files.read_file(repo, BODY)
    files.write_file(repo, BODY, "neu\n", expected_hash=content.sha256)
    assert (path.stat().st_mode & 0o777) == 0o640
    assert [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_concurrent_writers_only_one_wins(repo):
    content = files.read_file(repo, BODY)
    results: list[str] = []

    def writer(tag: str) -> None:
        try:
            files.write_file(repo, BODY, f"{tag}\n", expected_hash=content.sha256)
            results.append("ok")
        except StaleWriteError:
            results.append("stale")

    threads = [threading.Thread(target=writer, args=(f"w{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok"] + ["stale"] * 7


def test_list_files_filters_denied_and_hidden(repo):
    (repo.root / "web").mkdir()
    (repo.root / "web" / "x.tex").write_text("x")
    paths = [e.path for e in files.list_files(repo)]
    assert BODY in paths
    assert "common/db/sfr.csv" in paths
    assert not any(p.startswith(("web/", ".git", ".github")) for p in paths)
    assert not any(Path(p).suffix == ".pdf" for p in paths)


def test_list_files_subdir_and_writable_flag(repo):
    entries = {e.path: e for e in files.list_files(repo, "common/db")}
    assert entries["common/db/sfr.csv"].writable
    assert not entries["common/db/create_tables.sql"].writable
    with pytest.raises(PathNotAllowedError):
        files.list_files(repo, "../")
