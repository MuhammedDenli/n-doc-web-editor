"""Fixtures: a small, real n-doc checkout copied from this repository.

The template holds the tracked files of the root Makefile, the build workflow
(engine version), ``common/`` (macros + CSV data), ``adv_tds`` and ``mwe_tds``,
committed on branch ``work`` (``main`` exists too, for protection tests).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ndoc_core.repo import Repo

REAL_ROOT = Path(__file__).resolve().parents[3]

FIXTURE_PATHS = [
    "Makefile",
    "Makefile.rules",
    "Makefile.plantuml.rules",
    ".gitignore",
    ".github/workflows/build_n-doc_template.yml",
    "common",
    "adv_tds",
    "mwe_tds",
    "lua",
    "config/hooks",
    "scripts",
]

MWE_TDS_BODY = r"""\chapter{Body}
Das Modul \tdslink[fq]{mod.vpn.core} setzt \sfrlink{fcs_ckm.1} um.
\input{mwe_tds_extra}
"""


def git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env
    ).stdout


@pytest.fixture(scope="session")
def template_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("template") / "ndoc"
    root.mkdir()
    tracked = subprocess.run(
        ["git", "-C", str(REAL_ROOT), "ls-files", "-z", "--", *FIXTURE_PATHS],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    for rel in filter(None, tracked):
        src, dst = REAL_ROOT / rel, root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (root / "mwe_tds" / "mwe_tds_body.tex").write_text(MWE_TDS_BODY, encoding="utf-8")
    (root / "mwe_tds" / "mwe_tds_extra.tex").write_text("Extra text.\n", encoding="utf-8")

    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test User")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A", "-f")
    git(root, "commit", "-q", "-m", "fixture")
    git(root, "switch", "-q", "-c", "work")
    return root


@pytest.fixture
def repo_root(template_repo: Path, tmp_path: Path) -> Path:
    root = tmp_path / "ndoc"
    shutil.copytree(template_repo, root, symlinks=True)
    return root


@pytest.fixture
def repo(repo_root: Path) -> Repo:
    return Repo(repo_root)


@pytest.fixture
def real_repo(tmp_path: Path) -> Repo:
    """The actual checkout, read-only use; state goes to a temp dir."""
    return Repo(REAL_ROOT, state_dir=tmp_path / "state")
