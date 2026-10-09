import pytest


@pytest.mark.docker
def test_real_build_and_preview(app, editor):
    assert editor.post("/api/build/mwe_tds").status_code == 202
    app.state.builds.wait(900)
    status = editor.get("/api/build/latest").json()
    assert status["state"] == "succeeded", status
    assert status["pdf_checks"]["checked"] == ["mwe_tds/mwe_tds.pdf"]
    r = editor.get("/api/preview/mwe_tds")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
