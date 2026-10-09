# web/frontend

React + TypeScript (Vite) UI: document tree, Monaco source editor, common data
(CSV) grid, build panel with PDF preview and user admin. Git/PR and the agent
panel follow in later phases.

```
npm ci
npm run dev        # http://localhost:5173, /api proxied to 127.0.0.1:8000
npm run lint && npm run typecheck && npm test && npm run build
```

API types are generated from `../contracts/openapi.json` (`npm run gen:api`).
