# web/frontend

React + TypeScript (Vite) UI for the n-doc web layer. Git/PR and the agent
panel follow in later phases.

```
npm ci
npm run dev        # http://localhost:5173, /api proxied to ndoc-api serve (127.0.0.1:8000)
npm run lint && npm run typecheck && npm test && npm run build
```

API types are generated from `../contracts/openapi.json` (`npm run gen:api`,
run automatically before `dev`, `build`, `typecheck` and `test`).

## Screens

| Area                         | What it does                                                                                                                                              | API                                                    |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Login                        | session cookies, lockout message                                                                                                                          | `/api/auth/*`                                          |
| Document tree (left)         | document picker, `\input` tree                                                                                                                            | `/api/project/documents[/{name}/tree]`                 |
| Editor                       | Monaco with n-doc LaTeX highlighting, reference-key completion, save (Ctrl+S) with check markers, conflict dialog on `stale_write`, unsaved-changes guard | `/api/project/files/{path}`, `/api/project/references` |
| Common data                  | CSV tables, add/edit with FK selects (composite keys), delete with `referenced_by`, rename key                                                            | `/api/data/*`                                          |
| Build (top bar, right panel) | build active document / delivery, live status and log, PDF preview                                                                                        | `/api/build/*`, `/api/preview/{document}`              |
| Users (admin)                | create, role, disable, password, delete                                                                                                                   | `/api/users`                                           |

## Layout

`src/api` (client, errors, TanStack Query hooks), `src/auth`, `src/shell`,
`src/docs`, `src/editor` (Monaco is lazy-loaded from `monacoSetup.ts`),
`src/data`, `src/build`, `src/users`, `src/test` (MSW handlers, fixtures).
