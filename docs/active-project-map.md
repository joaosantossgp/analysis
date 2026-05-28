# Active Project Map

This is the short source-of-truth map for CVMAnalytics. If another document
conflicts with this file, inspect the active code paths below before changing
anything.

## Active App

- Frontend: `apps/desktop-web` (Vite + React + TypeScript).
- Desktop shell: `desktop/app.py` (pywebview window and launch modes).
- Bridge: `desktop/bridge.py` exposed to React as `window.pywebview.api`.
- Python core/data layer: `src/` (`read_service`, `query_layer`, database,
  refresh, scraper, KPI/export logic).
- Desktop services: `desktop/services.py` for bridge-facing business logic.
- HTTP API adapter: `apps/api` (FastAPI for API tests/dev-hosted HTTP access,
  not the desktop frontend).

## Active Commands

```powershell
# local no-release desktop dev
python -m desktop.app --dev

# Vite checks
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build

# Python checks
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
pytest apps/api/tests -q

# desktop package build
.\desktop\build_desktop.ps1
```

`python -m desktop.app --dev` starts or reuses the Vite dev server at
`127.0.0.1:5173` and opens the pywebview shell with the real Python bridge.

## Removed Legacy Paths

- `apps/web` was the old Next.js app and has been removed from the active tree.
- `apps/web/next.config.ts`, `apps/web/app/**`, `apps/web/components/**`, and
  `apps/web/tests/**` are not active development targets.
- Legacy Next-specific performance guardrails and web-route docs were removed
  from active docs/scripts.

## AI Agent Warning

- Do not create or modify Next.js routes, pages, layouts, API routes, or
  components.
- Do not infer architecture from `archive/`, `docs/archive/migration/`, release notes,
  or old ADR context. Those paths can contain historical references.
- Inspect `apps/desktop-web`, `desktop/`, `src/`, and `apps/api` before changing
  UI/runtime/backend behavior.
- If a file appears legacy or unused, report it instead of modifying it.
