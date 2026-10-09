# web/backend (`ndoc_api`)

FastAPI adapter over `web/core`: authentication (admin/editor), REST endpoints
and (Phase 5) the server-side agent loop. Business rules (path guard, CSV keys,
build allowlist, …) stay in `ndoc_core`; a `CoreError` becomes an `ErrorBody`
with the status from `errors.STATUS_BY_CODE`. The contract is
`web/contracts/openapi.json` (see `web/contracts/api.md`).

| Module | Purpose |
|---|---|
| `models` | pydantic request/response models (= the contract) |
| `auth` | SQLite users + sessions, Argon2, session cookie + CSRF header, role dependencies |
| `builds` | `BuildManager`: one background build, live log tail, latest status |
| `routes/` | `auth`, `users`, `project`, `data`, `build` (thin, sync handlers) |
| `app` | `create_app(settings)` |
| `cli` | `ndoc-api serve`, `create-user`, `export-openapi` |

## Configuration (environment)

| Variable | Default | |
|---|---|---|
| `NDOC_REPO` | nearest checkout above the cwd | the n-doc repository |
| `NDOC_HOST_REPO` | – | repo path as seen by the Docker daemon (API in a container) |
| `NDOC_DATA_DIR` | `<repo>/web/web-data` | `users.sqlite` (git-ignored) |
| `NDOC_COOKIE_SECURE` | `false` | set `true` behind HTTPS |
| `NDOC_SESSION_HOURS` | `12` | sliding session lifetime |
| `NDOC_ADMIN_USER`, `NDOC_ADMIN_PASSWORD` | – | create this admin on start if there are no users |

## Development

```
uv sync
echo 'a long password' | uv run ndoc-api create-user admin --role admin
uv run ndoc-api serve --reload           # http://127.0.0.1:8000/api/docs
uv run pytest -q                         # TestClient against a fixture repo, fake docker
uv run pytest -q -m docker               # real mwe_tds build through the API
uv run ndoc-api export-openapi           # after changing models/routes (contract commit!)
```

Tests reuse the fixtures of `web/core/tests/conftest.py`.
