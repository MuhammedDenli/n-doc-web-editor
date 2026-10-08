"""Reuse the core fixtures (a small real n-doc checkout in a temp git repo)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from mcp import Client

from ndoc_mcp.server import create_server

_spec = importlib.util.spec_from_file_location(
    "ndoc_core_fixtures", Path(__file__).resolve().parents[2] / "core" / "tests" / "conftest.py"
)
assert _spec and _spec.loader
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)

template_repo = _core.template_repo
repo_root = _core.repo_root
repo = _core.repo
git = _core.git


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(repo):
    async with Client(create_server(repo), raise_exceptions=False) as c:
        yield c
