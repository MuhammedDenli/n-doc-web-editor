# web/core (`ndoc_core`)

Deterministic Python core shared by the FastAPI backend and the MCP server.
All security and validation rules live here; adapters stay thin. Stdlib only.
Every function takes a `Repo` (the n-doc checkout) as first argument; errors
are `CoreError` subclasses with a stable `code`.

| Module | Purpose |
|---|---|
| `repo` | `Repo(root, host_root=None)`, inter-process locks (state in `.git/ndoc-web/`), `find_repo_root` (`NDOC_REPO` or nearest checkout) |
| `files` | path guard (`resolve_path`), `read_file` → text + SHA-256, atomic `write_file(expected_hash=…)`, `write_many` (all-or-nothing), `replace_text` (unique match), `search`, `list_files` |
| `docs` | documents from `PDF_DIRS`/`MWE_DIRS`, `\input` tree, `document_files`, `pdf_path` |
| `build` | allow-listed `make` targets in `ndesign/n-doc:<version>`, one build at a time, timeout kills the container, log tail + error lines + updated PDFs |
| `checks` | brace/env sanity, reference macros vs `common/db` (`\sfrlink`, `\tdslink`, …), `check_sfr_consistency.sh` wrapper, PDF "is undefined"/"To Do" scan; adapter entry points `run_checks`, `check_after_write`, `check_db`; `reference_keys` (valid keys per macro kind, for completion) |
| `pdf` | `pdftotext` page texts, `search_pdf` by document name (wrap-insensitive, `stale` flag) |
| `csvdata` | `common/db` schema (Lua + `create_tables.sql`, composite FKs, `bundles.NAME` alias), `list_tables`/`read_table`/`lookup`, line-preserving `insert_row`/`update_row`/`delete_row` that refuse new key violations, `rename_key` (cascades to referencing rows, lists `.tex` references), `validate_db` (new violations vs `HEAD` are errors) |
| `git` | status, diff, log, branch create/switch, commit of explicit paths, `show_file`; no reset/force/push; `main`/`master` protected |

Path policy: no absolute paths, `..`, hidden entries or `web/`; symlink targets
must pass the same policy. Writable: `.tex .csv .bib .md .txt`, not in
`scripts/ lua/ engine/ config/` nor at the top level.

```
uv sync
uv run pytest -q            # unit tests (fake docker)
uv run pytest -q -m docker  # real container builds
```
