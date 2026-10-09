# n-doc web layer

A web and agent layer on top of n-doc. It lets engineers edit documents,
manage the shared CSV data, build PDFs and open pull requests without
breaking the existing LaTeX/CSV/build semantics.

## Architecture (hybrid)

```
 Web (React)                         Agent
 Monaco · CSV grid · PDF             local: Claude Code + MCP
 Diff/PR · Agent panel · Review      server: Claude API (MCP tools only)
        │ REST (FastAPI)                    │ MCP
        ▼                                   ▼
 ┌──────────────────── web/core (Python) ────────────────────┐
 │ files · docs · csvdata · build · checks · review · git     │
 └────────────────────────────────────────────────────────────┘
                           n-doc repo
```

- `.tex` and `common/db/*.csv` remain the source of truth.
- The core enforces all safety rules (path guard, build target allowlist,
  FK validation, safe add/remove document).
- Without an LLM key the web UI works fully; only the agent panel is disabled.

## Layout

| Path | Purpose |
|---|---|
| `core/` | Shared Python core |
| `backend/` | FastAPI adapter + auth |
| `mcp/` | MCP server for agents |
| `frontend/` | React UI |
| `contracts/` | API contract (`openapi.json`, `api.md`) |

## Setup

Requirements: Docker (for the `ndesign/n-doc` build image), Python 3.12+ with
[uv](https://docs.astral.sh/uv/), Node 22 LTS (e.g. via nvm). A single
`docker compose up` follows in Phase 7; until then, for local development:

```
cd web/backend && uv sync
echo 'a long password' | uv run ndoc-api create-user admin --role admin
uv run ndoc-api serve                     # API on 127.0.0.1:8000, docs at /api/docs

cd web/frontend && npm ci && npm run dev  # UI on http://localhost:5173 (proxies /api)
```

The API contract is `contracts/openapi.json` (see `contracts/api.md`).
