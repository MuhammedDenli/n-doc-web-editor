# web/frontend

Vite + React 18 + TypeScript (strict) UI for the n-doc web layer. Root rules
in `../../CLAUDE.md` apply; this branch never changes root files.

## Commands

- `. ~/.nvm/nvm.sh` if `node` is missing; `npm ci` once.
- `npm run dev` (proxies `/api` to `ndoc-api serve` on 127.0.0.1:8000),
  `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`.
- `npm run gen:api` writes `src/api/schema.d.ts` from `../contracts/openapi.json`
  (gitignored; `dev`, `build`, `typecheck` and `test` run it first).

## Rules

- API types come only from the generated schema (`Schemas[...]`, `paths`); never
  hand-write request/response types. A contract change lands in `web/contracts/`
  first (backend branch).
- All calls go through `api` (`src/api/client.ts`, openapi-fetch) and `unwrap`,
  which throws `ApiError {status, code, details}`. Switch on `code`, show
  `message`; do not re-implement server rules (FK checks, path guard, targets).
- Server state lives in TanStack Query (`src/api/queries.ts`); no global store.
- Stack: React Router 6, TanStack Query 5, Monaco (bundled locally, no CDN),
  plain CSS (`src/styles.css` variables), native `<dialog>`.
- Tests: Vitest + Testing Library + MSW (`src/test/`); Monaco is mocked in jsdom.
