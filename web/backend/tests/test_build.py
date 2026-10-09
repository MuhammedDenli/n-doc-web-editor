import pytest


def _wait(client, app):
    app.state.builds.wait(30)
    return client.get("/api/build/latest").json()


def test_targets(editor):
    targets = editor.get("/api/build/targets").json()
    assert "tds" in targets and "mwe_tds" in targets


def test_build_and_preview(app, editor, fake_docker):
    assert editor.get("/api/build/latest").json()["state"] == "idle"
    assert editor.get("/api/preview/mwe_tds").status_code == 404
    r = editor.post("/api/build/mwe_tds")
    assert r.status_code == 202
    assert r.json()["state"] == "running" and r.json()["target"] == "mwe_tds"
    status = _wait(editor, app)
    assert status["state"] == "succeeded", status
    assert status["pdfs"] == ["mwe_tds/mwe_tds.pdf"]
    assert any("building mwe_tds" in line for line in status["log_tail"])
    r = editor.get("/api/preview/mwe_tds")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["cache-control"] == "no-store"


def test_failed_build(app, editor, fake_docker, monkeypatch):
    monkeypatch.setenv("FAKE_DOCKER_FAIL", "1")
    editor.post("/api/build/mwe_tds")
    status = _wait(editor, app)
    assert status["state"] == "failed"
    assert any("Emergency stop" in e for e in status["errors"])


def test_second_build_is_busy(app, editor, fake_docker, monkeypatch):
    monkeypatch.setenv("FAKE_DOCKER_SLEEP", "2")
    assert editor.post("/api/build/mwe_tds").status_code == 202
    r = editor.post("/api/build/tds")
    assert (r.status_code, r.json()["code"]) == (409, "build_busy")
    running = editor.get("/api/build/latest").json()
    assert running["state"] == "running" and running["elapsed_s"] >= 0


@pytest.mark.parametrize("bad", ["foo", "tds;ls", "TDS"])
def test_disallowed_target(editor, bad):
    r = editor.post(f"/api/build/{bad}")
    assert (r.status_code, r.json()["code"]) == (422, "build_target_not_allowed")


def test_unknown_document_preview(editor):
    assert editor.get("/api/preview/nope").json()["code"] == "unknown_document"
