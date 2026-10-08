# web/core (`ndoc_core`)

Deterministic Python core shared by the FastAPI backend and the MCP server.
All security and validation rules live here; adapters stay thin. Stdlib only.
Every function takes a `Repo` (the n-doc checkout) as first argument; errors
are `CoreError` subclasses with a stable `code`.

| Module | Purpose |
|---|---|
| `repo` | `Repo(root, host_root=None)`, inter-process locks (state in `.git/ndoc-web/`) |
| `files` | path guard (`resolve_path`), `read_file` → text + SHA-256, atomic `write_file(expected_hash=…)`, `replace_text` (unique match), `search`, `list_files` |
| `docs` | documents from `PDF_DIRS`/`MWE_DIRS`, `\input` tree, `document_files`, `pdf_path` |
| `build` | allow-listed `make` targets in `ndesign/n-doc:<version>`, one build at a time, timeout kills the container, log tail + error lines + updated PDFs |
| `checks` | brace/env sanity, reference macros vs `common/db` (`\sfrlink`, `\tdslink`, …), `check_sfr_consistency.sh` wrapper, PDF "is undefined"/"To Do" scan |
| `git` | status, diff, log, branch create/switch, commit of explicit paths; no reset/force/push; `main`/`master` protected |

Path policy: no absolute paths, `..`, hidden entries or `web/`; symlink targets
must pass the same policy. Writable: `.tex .csv .bib .md .txt`, not in
`scripts/ lua/ engine/ config/` nor at the top level.

```
uv sync
uv run pytest -q            # unit tests (fake docker)
uv run pytest -q -m docker  # real container builds
```
