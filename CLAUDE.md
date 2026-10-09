# CLAUDE.md

Fork of n-design/n-doc (Common Criteria documents built from LaTeX + Lua + CSV)
with an added web/agent layer under `web/`. See `web/README-web.md` for the
architecture: a Python core (`web/core`) exposed via FastAPI and MCP, a slim
React UI, and a Claude agent. `.tex` and `common/db/*.csv` stay the source of truth.

## Rules

- Do not modify upstream n-doc files (everything outside `web/`, `CLAUDE.md`,
  `.claude/`). If unavoidable, put the change in its own commit prefixed `ndoc-core:`.
- Branches: `feature/web-mvp` (integration), `feature/web-backend-mvp`
  (core + backend + mcp), `feature/web-frontend-mvp`. Never push to `main`.
- API changes: update `web/contracts/` first in a separate commit, then implement.
- All safety/validation rules belong in `web/core`; adapters stay thin.
- Never run `scripts/remove_document.sh` directly: it does `rm -rf "$doc"`
  with no validation.

## Build

- `./runmake.sh <target>` runs `make` inside `ndesign/n-doc:<version>` (Docker).
  The version is read from `.github/workflows/build_n-doc_template.yml`.
- Targets: `all delivery st fsp tds arc ate ref db mwe clean`; directory names
  also work (`ase`, `adv_tds`, ...). Note: the ST alias is `st`, its directory is `ase`.
- Output: `<dir>/<dir>.pdf`; `delivery` copies them to `deliverables/`.
- Builds need a real git repo (`make hooks` writes `.git/hooks` and `.git/gitHeadInfo.gin`).
- `mwe_*` are small test documents that build fast. On a fresh clone run
  `./runmake.sh hooks` first: `mwe` does not depend on `hooks` and fails with
  `Undefined control sequence \THEDAY` (gitinfo2) without `.git/gitHeadInfo.gin`.
- After a failed build latexmk may report "Nothing to do" yet still fail;
  run `./runmake.sh cleanmwe` (or `clean`) and rebuild.

## n-doc gotchas

- Documents: `ase adv_tds adv_fsp adv_arc ate_cov alc reflist`, each `<dir>/<dir>.tex`;
  the list is `PDF_DIRS` in the root `Makefile`. Chapters are pulled in with
  `\input{...}` (relative, extension optional).
- CSV (`common/db/*.csv`): `;` delimiter, header row. Preserve LaTeX escapes
  (`O.TLS\_Crypto`, `\-`) and trailing-newline state byte-exactly
  (`subjobj.csv`, `sfr_subjobj.csv` have none). `common/test_db/` is a copy for tests.
- Schema: `common/db/create_tables.sql`. `modules` PK is `(subsystem,label)`;
  validate `interfaces` by the `(subsystem,module)` pair. `bundles.csv` header is
  `NAME` but the schema column is `bundle`. `subjobj`, `sfr_subjobj`, `releases`
  are defined in `lua/cc_core.lua` / `lua/documents.lua`, not in SQL.
- n-doc macros: `\tdslink \sfrlink \tsfilink \secitem \sfr` (references),
  `\hrefchapter \hrefsection \modulechapter \moduleprocess` (headings),
  `\cite \autocite \citepp`. Never "fix" escapes inside macro arguments.
- Consistency checks: `scripts/check_sfr_consistency.sh` (CSV),
  `scripts/sanity_check.sh` (scans built PDFs for "is undefined" / "To Do").

## Editing n-doc content (agent workflow)

For changes to documents or `common/db` data use the `ndoc` MCP tools
(`web/mcp`), not shell commands or ad-hoc scripts:

1. `git_status`; on `main` or a shared `feature/*` branch, `git_create_branch`
   (`agent/<topic>`) first.
2. Locate with `search`, `document_tree`, `read_file`; check labels in the CSV
   before using a reference macro.
3. Change `.tex` with `edit_file` (preferred) or `write_file`; both return check results.
   Change `common/db` with `csv_insert`/`csv_update`/`csv_delete` (`csv_tables`,
   `csv_read`, `csv_lookup` to inspect): they keep all other bytes and refuse
   duplicate keys and broken (composite) foreign keys. To rename a referenced key
   use `csv_rename_key`, then fix every entry of its `tex_references` with `edit_file`.
4. `run_checks`, then `run_build` for the affected document; `pdf_search`
   confirms the change is in the PDF (no shell `pdftotext`).
5. `git_diff` must show only the intended lines; then `git_commit` with explicit paths.

A native Write/Edit of `.tex` or `common/db/*.csv` triggers `ndoc-check` via a
hook; fix every error it reports.

## Tests (web/core)

- `cd web/core && uv sync` once; then `uv run pytest -q` (fast, no Docker).
- `uv run pytest -q -m docker`: real container builds of a fixture copy (~40 s).
- `uv run ruff check . && uv run ruff format .` (a PostToolUse hook formats
  edited `web/core` and `web/mcp` Python files automatically).
- `web/mcp` and `web/backend` work the same way (`cd web/<pkg> && uv sync`,
  `uv run pytest -q`, `-m docker`); their tests reuse the core fixtures.
- `web/backend` (FastAPI, `ndoc-api`): after changing `models.py` or route
  signatures run `uv run ndoc-api export-openapi` and commit `web/contracts/`
  first, alone; `tests/test_contract.py` fails while the contract is stale.
  Local server: `ndoc-api create-user <name> --role admin`, then `ndoc-api serve`.

## Frontend (web/frontend)

- Node 22 LTS via nvm (`~/.nvm`); if `node` is missing in a shell, run
  `. ~/.nvm/nvm.sh` first.
- Vite + React + TypeScript; API types are generated from
  `web/contracts/openapi.json` (`npm run gen:api`), never hand-written.
- `npm run dev` proxies `/api` to `ndoc-api serve` on 127.0.0.1:8000.
- `npm run lint`, `npm run typecheck`, `npm test` (Vitest + MSW), `npm run build`.
  Edited `.ts/.tsx/.css` files are formatted by a Prettier hook.
- The frontend branch does not change root files (`CLAUDE.md`, `.claude/`);
  those changes go through `feature/web-backend-mvp`.
- Fixtures copy tracked files of this checkout into a temp git repo
  (`tests/conftest.py`); tests never touch the real working tree, except the
  read-only baseline that all real documents pass the reference checks.
