import pytest
from fastapi.testclient import TestClient

from ndoc_api.auth import CSRF_HEADER, MAX_FAILURES, SESSION_COOKIE

from .conftest import PASSWORD, login


def test_health_needs_no_login(anon):
    assert anon.get("/api/health").json() == {"status": "ok"}


def test_login_sets_cookies_and_me(anon):
    r = anon.post("/api/auth/login", json={"username": "ed", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json() == {"username": "ed", "role": "editor", "disabled": False}
    cookies = r.headers.get_list("set-cookie")
    session = next(c for c in cookies if c.startswith(SESSION_COOKIE))
    assert "HttpOnly" in session and "SameSite=strict" in session and "Path=/api" in session
    assert anon.get("/api/auth/me").json()["username"] == "ed"


@pytest.mark.parametrize(("user", "pw"), [("ed", "wrong password"), ("nobody", PASSWORD)])
def test_login_rejected(anon, user, pw):
    r = anon.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_credentials"


def test_login_throttled(anon):
    for _ in range(MAX_FAILURES):
        anon.post("/api/auth/login", json={"username": "ed", "password": "nope nope"})
    r = anon.post("/api/auth/login", json={"username": "ed", "password": PASSWORD})
    assert r.status_code == 429
    assert r.json()["code"] == "too_many_attempts"


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("get", "/api/auth/me", None),
        ("get", "/api/project/documents", None),
        ("get", "/api/project/files/mwe_tds/mwe_tds_body.tex", None),
        ("put", "/api/project/files/mwe_tds/mwe_tds_body.tex", {"content": "x"}),
        ("post", "/api/data/sfr", {"values": {}}),
        ("post", "/api/build/tds", None),
        ("get", "/api/preview/mwe_tds", None),
        ("get", "/api/users", None),
    ],
)
def test_endpoints_need_a_session(anon, method, url, body):
    r = anon.request(method, url, json=body)
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


def test_unsafe_requests_need_csrf(editor):
    del editor.headers[CSRF_HEADER]
    r = editor.post("/api/build/mwe_tds")
    assert (r.status_code, r.json()["code"]) == (403, "csrf_failed")
    editor.headers[CSRF_HEADER] = "forged"
    r = editor.put("/api/project/files/mwe_tds/mwe_tds_extra.tex", json={"content": "x"})
    assert (r.status_code, r.json()["code"]) == (403, "csrf_failed")
    assert editor.get("/api/auth/me").status_code == 200


def test_logout_ends_session(editor):
    assert editor.post("/api/auth/logout").status_code == 204
    assert editor.get("/api/auth/me").status_code == 401


def test_change_password_ends_other_sessions(app, editor):
    with TestClient(app) as other:
        login(other, "ed")
        r = editor.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": "new password 1"},
        )
        assert r.status_code == 204
        assert editor.get("/api/auth/me").status_code == 200
        assert other.get("/api/auth/me").status_code == 401


def test_editor_cannot_manage_users(editor):
    r = editor.get("/api/users")
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")


def test_admin_user_crud(admin):
    r = admin.post(
        "/api/users", json={"username": "new", "password": "long enough", "role": "editor"}
    )
    assert r.status_code == 201
    assert (
        admin.post("/api/users", json={"username": "new", "password": "long enough"}).status_code
        == 409
    )
    assert admin.post("/api/users", json={"username": "x", "password": "short"}).status_code == 422
    assert admin.patch("/api/users/new", json={"role": "admin"}).json()["role"] == "admin"
    assert admin.delete("/api/users/new").status_code == 204
    assert admin.delete("/api/users/new").status_code == 404
    assert [u["username"] for u in admin.get("/api/users").json()] == ["admin", "ed"]


def test_disabled_user_is_logged_out(app, admin):
    with TestClient(app) as ed:
        login(ed, "ed")
        assert admin.patch("/api/users/ed", json={"disabled": True}).status_code == 200
        assert ed.get("/api/auth/me").status_code == 401
        r = ed.post("/api/auth/login", json={"username": "ed", "password": PASSWORD})
        assert r.status_code == 401


def test_last_admin_is_protected(admin):
    for r in (
        admin.patch("/api/users/admin", json={"role": "editor"}),
        admin.patch("/api/users/admin", json={"disabled": True}),
        admin.delete("/api/users/admin"),
    ):
        assert (r.status_code, r.json()["code"]) == (409, "last_admin")
