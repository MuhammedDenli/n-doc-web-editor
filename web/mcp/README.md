# web/mcp (`ndoc_mcp`)

MCP server exposing `web/core` functions as tools for Claude Code (local)
and for the server-side agent. The agent gets these tools only — no shell.
The adapter is thin: validation lives in `ndoc_core`, a `CoreError` becomes a
tool error whose text ends in `{"code": ..., "message": ..., ...}`.

| Tool | Core call | Notes |
|---|---|---|
| `list_documents`, `document_tree` | `docs` | `\input` tree with missing/cyclic nodes |
| `list_files`, `search`, `read_file` | `files` | `read_file` returns `sha256` |
| `edit_file` | `files.replace_text` | unique match unless `replace_all`; returns checks |
| `write_file` | `files.write_file` | needs `expected_sha256` (or `create`); returns checks |
| `run_checks` | `checks` | default scope: changed files; SFR consistency when CSV changed |
| `run_build`, `list_build_targets` | `build` | allow-listed targets; scans produced PDFs |
| `git_status`, `git_diff`, `git_log` | `git` | read-only |
| `git_create_branch`, `git_switch_branch`, `git_commit` | `git` | commits refused on `main`/`master`; no push |

The repository is `NDOC_REPO`, else the nearest ancestor of the working
directory with a `Makefile` and `web/`. `NDOC_HOST_REPO` is passed to the core
for builds through a host `docker.sock`.

## Claude Code

`/.mcp.json` registers the server as `ndoc` (`uv run --project web/mcp ndoc-mcp`);
`.claude/settings.json` enables it, pre-approves the read/edit/check/build
tools (branch and commit tools still ask) and runs `ndoc-check <file>` after a
native Write/Edit of a `.tex` or `common/db/*.csv` file: check errors are fed
back to the model (exit 2).

## Development

```
uv sync
uv run pytest -q            # in-process MCP client against a fixture repo
uv run pytest -q -m docker  # real build through run_build
```

Tests reuse the fixtures of `web/core/tests/conftest.py`.
