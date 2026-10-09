BODY = "mwe_tds/mwe_tds_body.tex"


def test_documents_and_tree(editor):
    names = [d["name"] for d in editor.get("/api/project/documents").json()]
    assert "adv_tds" in names and "mwe_tds" in names
    tree = editor.get("/api/project/documents/mwe_tds/tree").json()
    assert tree["path"] == "mwe_tds/mwe_tds.tex"
    paths = []

    def walk(n):
        paths.append(n["path"])
        for c in n["children"]:
            walk(c)

    walk(tree)
    assert BODY in paths
    r = editor.get("/api/project/documents/nope/tree")
    assert (r.status_code, r.json()["code"]) == (404, "unknown_document")


def test_read_and_save_returns_checks(editor, repo):
    f = editor.get(f"/api/project/files/{BODY}").json()
    new = f["text"] + "Neu: \\sfrlink{fcs_ckm.1}.\n"
    r = editor.put(
        f"/api/project/files/{BODY}", json={"content": new, "expected_sha256": f["sha256"]}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["checks"]["ok"] and out["sha256"] != f["sha256"]
    assert (repo.root / BODY).read_text() == new


def test_save_reports_broken_reference(editor):
    f = editor.get(f"/api/project/files/{BODY}").json()
    r = editor.put(
        f"/api/project/files/{BODY}",
        json={"content": f["text"] + "\\sfrlink{YOK}\n", "expected_sha256": f["sha256"]},
    )
    checks = r.json()["checks"]
    assert not checks["ok"]
    assert [i["code"] for i in checks["issues"]] == ["undefined_reference"]


def test_stale_save_is_a_conflict(editor, repo):
    f = editor.get(f"/api/project/files/{BODY}").json()
    (repo.root / BODY).write_text("changed elsewhere\n")
    r = editor.put(
        f"/api/project/files/{BODY}", json={"content": "mine", "expected_sha256": f["sha256"]}
    )
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "stale_write"
    assert body["details"]["current_hash"]


def test_path_guard(editor):
    for url in ("/api/project/files/web/backend/pyproject.toml", "/api/project/files/.git/config"):
        r = editor.get(url)
        assert (r.status_code, r.json()["code"]) == (403, "path_not_allowed"), url
    r = editor.get("/api/project/files/..%2F..%2Fetc/passwd")
    assert r.status_code in (403, 404)
    r = editor.put("/api/project/files/scripts/remove_document.sh", json={"content": "x"})
    assert r.status_code == 403


def test_search_and_references(editor):
    r = editor.get("/api/project/search", params={"pattern": "fcs_ckm.1", "dir": "mwe_tds"})
    assert any(m["path"] == BODY for m in r.json()["matches"])
    refs = editor.get("/api/project/references").json()
    assert refs["macros"]["sfrlink"] == "sfr"
    assert any(k["key"] == "mod.vpn.core" for k in refs["keys"]["tds"])


def test_checks_endpoint(editor, repo):
    (repo.root / BODY).write_text("\\tdslink{sub.nope} {\n")
    r = editor.post("/api/project/checks", json={})
    issues = r.json()["issues"]
    assert sorted(i["code"] for i in issues) == ["unbalanced_brace", "undefined_reference"]
