"""Reuse the core fixtures (a small real n-doc checkout in a temp git repo)."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ndoc_api.app import create_app
from ndoc_api.auth import CSRF_COOKIE, CSRF_HEADER
from ndoc_api.settings import Settings

_CORE_TESTS = Path(__file__).resolve().parents[2] / "core" / "tests"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _CORE_TESTS / file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_core = _load("ndoc_core_fixtures", "conftest.py")
template_repo = _core.template_repo
repo_root = _core.repo_root
repo = _core.repo
git = _core.git
FAKE_DOCKER = _load("ndoc_core_build_tests", "test_build.py").FAKE_DOCKER

PASSWORD = "correct horse"


@pytest.fixture
def app(repo, tmp_path):
    application = create_app(Settings(repo_root=repo.root, data_dir=tmp_path / "data"))
    store = application.state.users
    store.create_user("admin", PASSWORD, "admin")
    store.create_user("ed", PASSWORD, "editor")
    yield application
    application.state.builds.wait(30)


@pytest.fixture
def anon(app):
    with TestClient(app) as c:
        yield c


def login(client: TestClient, username: str) -> TestClient:
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
    return client


@pytest.fixture
def editor(app):
    with TestClient(app) as c:
        yield login(c, "ed")


@pytest.fixture
def admin(app):
    with TestClient(app) as c:
        yield login(c, "admin")


@pytest.fixture
def fake_docker(tmp_path, monkeypatch, repo):
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
    (repo.root / ".git/gitHeadInfo.gin").write_text("")
    return log
