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

## Tests (web/core)

- `cd web/core && uv sync` once; then `uv run pytest -q` (fast, no Docker).
- `uv run pytest -q -m docker`: real container builds of a fixture copy (~40 s).
- `uv run ruff check . && uv run ruff format .` (a PostToolUse hook formats
  edited `web/core/**/*.py` automatically).
- Fixtures copy tracked files of this checkout into a temp git repo
  (`tests/conftest.py`); tests never touch the real working tree, except the
  read-only baseline that all real documents pass the reference checks.
