def test_tables_and_rows(editor):
    tables = {t["name"]: t for t in editor.get("/api/data/tables").json()}
    assert tables["modules"]["primary_key"] == ["subsystem", "label"]
    data = editor.get("/api/data/modules").json()
    assert data["columns"][:2] == ["subsystem", "label"] and data["sha256"]
    assert editor.get("/api/data/nope").json()["code"] == "unknown_table"


def test_lookup_composite_fk(editor):
    opts = editor.get("/api/data/interfaces/lookup", params={"column": "module"}).json()
    core = next(o for o in opts if o["value"] == "core")
    assert set(core["key"]) == {"subsystem", "module"}


def test_insert_update_delete(editor, repo):
    sha = editor.get("/api/data/tsfi").json()["sha256"]
    r = editor.post(
        "/api/data/tsfi",
        json={"values": {"label": "tsfi.new", "name": "New"}, "expected_sha256": sha},
    )
    assert r.status_code == 201, r.text
    assert r.json()["checks"]["checked"]
    r = editor.put(
        "/api/data/tsfi", json={"match": {"label": "tsfi.new"}, "values": {"name": "Renamed"}}
    )
    assert r.json()["row"]["name"] == "Renamed"
    r = editor.request("DELETE", "/api/data/tsfi", json={"match": {"label": "tsfi.new"}})
    assert r.status_code == 200
    assert "tsfi.new" not in (repo.root / "common/db/tsfi.csv").read_text()


def test_delete_referenced_row_refused(editor):
    r = editor.request("DELETE", "/api/data/sfr", json={"match": {"label": "fcs_ckm.1"}})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "row_referenced"
    assert body["details"]["referenced_by"]


def test_insert_with_broken_fk_refused(editor):
    r = editor.post(
        "/api/data/interfaces",
        json={"values": {"subsystem": "vpn", "module": "nope", "label": "x", "name": "X"}},
    )
    assert (r.status_code, r.json()["code"]) == (422, "foreign_key_violation")


def test_duplicate_and_stale(editor):
    r = editor.post("/api/data/sfr", json={"values": {"label": "fcs_ckm.1"}})
    assert (r.status_code, r.json()["code"]) == (409, "duplicate_key")
    r = editor.post(
        "/api/data/tsfi", json={"values": {"label": "t.x"}, "expected_sha256": "0" * 64}
    )
    assert (r.status_code, r.json()["code"]) == (409, "stale_write")


def test_rename_key(editor):
    r = editor.post(
        "/api/data/modules/rename-key",
        json={"match": {"subsystem": "vpn", "label": "core"}, "new_key": {"label": "engine"}},
    )
    assert r.status_code == 200, r.text
    refs = r.json()["tex_references"]
    assert any(t["replacement"] == "mod.vpn.engine" for t in refs)
