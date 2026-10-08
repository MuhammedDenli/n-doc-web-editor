"""Build tests use a fake ``docker`` on PATH; the real build is marked ``docker``."""

import os
import stat
from pathlib import Path

import pytest

from ndoc_core import build, checks
from ndoc_core.errors import BuildBusyError, BuildTargetNotAllowedError
from ndoc_core.repo import Repo

FAKE_DOCKER = r"""#!/bin/bash
echo "$*" >> "$FAKE_DOCKER_LOG"
[ "$1" = kill ] && exit 0
target="${@: -1}"
echo "building $target"
if [ "$target" = hooks ]; then : > .git/gitHeadInfo.gin; fi
if [ -n "$FAKE_DOCKER_SLEEP" ]; then exec sleep "$FAKE_DOCKER_SLEEP"; fi
if [ -n "$FAKE_DOCKER_FAIL" ]; then
  echo "./mwe_tds_body.tex:3: Undefined control sequence."
  echo "! Emergency stop."
  echo "make: *** [Makefile:12: mwe_tds] Error 2"
  exit 2
fi
for d in mwe_tds adv_tds; do
  if [ "$target" = "$d" ] || { [ "$target" = tds ] && [ "$d" = adv_tds ]; }; then
    : > "$d/$d.pdf"
  fi
done
exit 0
"""


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "docker"
    exe.write_text(FAKE_DOCKER)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "docker.log"
    log.touch()
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.delenv("NDOC_ENGINE_VERSION", raising=False)
    return log


@pytest.fixture
def hooked_repo(repo):
    (repo.root / ".git/gitHeadInfo.gin").write_text("")
    return repo


def test_allowed_targets(repo):
    targets = build.allowed_targets(repo)
    for t in ("tds", "st", "mwe", "delivery", "clean", "cleanmwe", "hooks", "ase", "mwe_tds"):
        assert t in targets


@pytest.mark.parametrize(
    "bad", ["", "foo", "tds; rm -rf /", "../tds", "-j", "clean all", "--eval=x", "TDS", None]
)
def test_disallowed_targets(repo, bad):
    with pytest.raises(BuildTargetNotAllowedError):
        build.validate_target(repo, bad)


def test_target_dirs(repo):
    assert build.target_dirs(repo, "st") == ["ase"]
    assert build.target_dirs(repo, "tds") == ["adv_tds"]
    assert build.target_dirs(repo, "mwe_tds") == ["mwe_tds"]
    assert "mwe_st" in build.target_dirs(repo, "mwe")
    assert build.target_dirs(repo, "clean") == []


def test_engine_version_from_workflow(repo, monkeypatch):
    monkeypatch.delenv("NDOC_ENGINE_VERSION", raising=False)
    assert build.engine_version(repo) == "4.12.0"


def test_docker_command_shape(repo, monkeypatch):
    monkeypatch.delenv("NDOC_ENGINE_VERSION", raising=False)
    cmd = build.docker_command(repo, "tds", container="c1", jobs=2)
    assert cmd[:3] == ["docker", "run", "--rm"]
    assert f"{repo.root}:/data" in cmd
    assert f"{os.getuid()}:{os.getgid()}" in cmd
    assert cmd[-4:] == ["ndesign/n-doc:4.12.0", "make", "-j2", "tds"]


def test_docker_command_uses_host_root(repo_root, monkeypatch):
    monkeypatch.delenv("NDOC_ENGINE_VERSION", raising=False)
    r = Repo(repo_root, host_root=Path("/host/ndoc"))
    assert "/host/ndoc:/data" in build.docker_command(r, "tds", container="c")


def test_successful_build_reports_pdf(hooked_repo, fake_docker):
    lines: list[str] = []
    result = build.build(hooked_repo, "mwe_tds", on_output=lines.append)
    assert result.ok and result.returncode == 0 and not result.timed_out
    assert result.pdfs == ["mwe_tds/mwe_tds.pdf"]
    assert "building mwe_tds" in result.log_tail
    assert lines == ["building mwe_tds"]
    assert Path(result.log_file).is_file()
    assert Path(result.log_file).is_relative_to(hooked_repo.state_dir)


def test_alias_target_maps_to_document_pdf(hooked_repo, fake_docker):
    assert build.build(hooked_repo, "tds").pdfs == ["adv_tds/adv_tds.pdf"]


def test_failed_build_extracts_errors(hooked_repo, fake_docker, monkeypatch):
    monkeypatch.setenv("FAKE_DOCKER_FAIL", "1")
    result = build.build(hooked_repo, "mwe_tds")
    assert not result.ok and result.returncode == 2
    assert result.pdfs == []
    assert result.errors == [
        "./mwe_tds_body.tex:3: Undefined control sequence.",
        "! Emergency stop.",
        "make: *** [Makefile:12: mwe_tds] Error 2",
    ]


def test_hooks_run_first_when_git_info_missing(repo, fake_docker):
    assert not (repo.root / ".git/gitHeadInfo.gin").exists()
    assert build.build(repo, "mwe_tds").ok
    runs = [line.split()[-1] for line in fake_docker.read_text().splitlines()]
    assert runs == ["hooks", "mwe_tds"]
    # second build: hooks no longer needed
    build.build(repo, "mwe_tds")
    runs = [line.split()[-1] for line in fake_docker.read_text().splitlines()]
    assert runs == ["hooks", "mwe_tds", "mwe_tds"]


def test_timeout_kills_container(hooked_repo, fake_docker, monkeypatch):
    monkeypatch.setenv("FAKE_DOCKER_SLEEP", "30")
    result = build.build(hooked_repo, "mwe_tds", timeout=1)
    assert result.timed_out and not result.ok
    assert result.duration_s < 15
    calls = fake_docker.read_text().splitlines()
    container = calls[0].split("--name ")[1].split()[0]
    assert f"kill {container}" in calls


def test_only_one_build_at_a_time(hooked_repo, fake_docker):
    with hooked_repo.try_lock(build.BUILD_LOCK) as acquired:
        assert acquired
        with pytest.raises(BuildBusyError):
            build.build(hooked_repo, "mwe_tds")
    assert build.build(hooked_repo, "mwe_tds").ok


@pytest.mark.docker
def test_real_build_mwe_tds(repo):
    """Real container build of the fixture's mwe_tds (pytest -m docker)."""
    result = build.build(repo, "mwe_tds", timeout=900)
    assert result.ok, result.log_tail
    assert result.pdfs == ["mwe_tds/mwe_tds.pdf"]


@pytest.mark.docker
def test_real_build_broken_reference_matches_static_check(repo):
    """A bad \\sfrlink found by checks shows up as "is undefined" in the built PDF."""
    body = repo.root / "mwe_tds/mwe_tds_body.tex"
    body.write_text(body.read_text() + "Kaputt: \\sfrlink{fzz_yok.1}\n", encoding="utf-8")
    static = checks.check_document(repo, "mwe_tds")
    assert [i.code for i in static.issues] == ["undefined_reference"]

    result = build.build(repo, "mwe_tds", timeout=900)
    assert result.ok, result.log_tail  # LaTeX itself does not fail on it
    sanity = checks.check_pdf_sanity(repo, result.pdfs)
    assert any("fzz" in i.message and i.code == "pdf_undefined" for i in sanity.issues)
