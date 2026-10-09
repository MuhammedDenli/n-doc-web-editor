# API contract

`openapi.json` in this directory is the single source of truth between
backend and frontend.

## Rules

1. Any API change lands first as a small, separate contract commit.
2. Backend and frontend implement the change afterwards.
3. Frontend types are generated from `openapi.json` (`openapi-typescript`),
   never written by hand.

`openapi.json` is exported from the FastAPI models (`web/backend/src/ndoc_api/models.py`
and the route signatures), so contract and implementation cannot drift:

```
cd web/backend
uv run ndoc-api export-openapi           # rewrite openapi.json
uv run ndoc-api export-openapi --check   # fail if it is out of date
```

A backend test (`tests/test_contract.py`) fails while the served spec differs from
this file. Change flow: edit models/route signatures → export → commit only
`web/contracts/` (`web/contracts: ...`) → implement backend and frontend.

## Conventions

- All paths start with `/api`. JSON in and out, except `GET /api/preview/{document}` (PDF).
- File paths are repo-relative POSIX paths (`adv_tds/module/tls/core.tex`) inside the
  URL path, e.g. `GET /api/project/files/adv_tds/adv_tds.tex`.
- Optimistic concurrency: reads return `sha256`; writes send it back as
  `expected_sha256`. A mismatch is `409 stale_write` with `details.current_hash`.
- Writes of `.tex` and `common/db` CSV return `checks` (`CheckReport`). Check errors
  do not block the save; the UI shows them.

## Authentication

- `POST /api/auth/login` sets two cookies:
  - `ndoc_session`: HttpOnly, `SameSite=Strict`, `Path=/api`.
  - `ndoc_csrf`: readable by JS, `Path=/`.
- Every request except `login` and `health` needs the session (else `401 unauthenticated`).
- Every non-GET request must also send `X-CSRF-Token: <ndoc_csrf>` (else `403 csrf_failed`).
- Roles: `editor` reads, writes files and CSV data, runs builds. `admin` can do the
  same and also manages users (`/api/users`, else `403 forbidden`).
- After 5 failed logins within 15 minutes, logins for that username return
  `429 too_many_attempts`.

## Errors

Every error body is `ErrorBody` `{code, message, details}`; clients switch on `code`.

| Status | Codes |
|---|---|
| 401 | `unauthenticated`, `invalid_credentials` |
| 403 | `forbidden`, `csrf_failed`, `path_not_allowed`, `protected_branch` |
| 404 | `not_found`, `unknown_document`, `unknown_table`, `row_not_found` |
| 409 | `stale_write`, `already_exists`, `duplicate_key`, `row_referenced` (`details.referenced_by`), `build_busy`, `lock_timeout`, `dirty_worktree`, `last_admin` |
| 413 | `file_too_large` |
| 422 | `invalid_request` (`details.errors`), `invalid_value`, `invalid_content`, `invalid_pattern`, `foreign_key_violation`, `text_not_found`, `ambiguous_match`, `build_target_not_allowed` |
| 429 | `too_many_attempts` (`details.retry_after_s`) |
| 503 | `tool_missing` |

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/health` | – | liveness |
| POST | `/api/auth/login` | – | start session → `User` |
| POST | `/api/auth/logout` | any | end session |
| GET | `/api/auth/me` | any | current `User` |
| POST | `/api/auth/password` | any | change own password (ends other sessions) |
| GET, POST | `/api/users` | admin | list / create users |
| PATCH, DELETE | `/api/users/{username}` | admin | role, password, disabled / delete |
| GET | `/api/project/documents` | any | documents (`PDF_DIRS` + `mwe_*`) |
| GET | `/api/project/documents/{name}/tree` | any | `\input` tree (`InputNode`) |
| GET | `/api/project/files?dir=` | any | readable files below `dir` |
| GET | `/api/project/files/{path}` | any | `FileContent` (text + `sha256`) |
| PUT | `/api/project/files/{path}` | editor | save (`FileWrite`) → `WriteResult` with `checks` |
| GET | `/api/project/search` | any | line search (`pattern`, `dir`, `regex`, `ignore_case`) |
| GET | `/api/project/references` | any | reference macros and valid keys (editor completion) |
| POST | `/api/project/checks` | any | static checks (paths / document / changed files) |
| GET | `/api/data/tables` | any | CSV tables: columns, primary key, foreign keys |
| GET | `/api/data/{table}` | any | rows with line numbers + `sha256` |
| GET | `/api/data/{table}/lookup?column=&prefix=` | any | FK select values (`key` = full composite key) |
| POST | `/api/data/{table}` | editor | insert row (`RowInsert`) |
| PUT | `/api/data/{table}` | editor | update one row (`RowUpdate`: `match` + `values`) |
| DELETE | `/api/data/{table}` | editor | delete one row (`RowDelete`, JSON body) |
| POST | `/api/data/{table}/rename-key` | editor | rename key + referencing rows → `tex_references` |
| GET | `/api/build/targets` | any | allowed make targets |
| POST | `/api/build/{target}` | editor | start build in background → `202 BuildStatus` (`409 build_busy`) |
| GET | `/api/build/latest` | any | `BuildStatus` (poll while `state == "running"`) |
| GET | `/api/preview/{document}` | any | built PDF, inline, `Cache-Control: no-store` |

Git, push/PR and add/remove document endpoints follow in Phase 6, the agent in Phase 5.
