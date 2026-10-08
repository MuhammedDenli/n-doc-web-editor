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

_To be completed in Phase 7 (`docker compose up`)._
Requirements: Docker (for the `ndesign/n-doc` build image), Python 3.12+, Node LTS.
