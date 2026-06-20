# apps/desktop-web

Vite + React + TypeScript desktop UI for CVMAnalytics.

## Status

This is the only frontend bundled into `CVMAnalytics.exe`. It is built by
`desktop/build_desktop.ps1`, bundled by `desktop/app.spec` as
`_internal/desktop-web`, and served by `desktop/app.py` inside pywebview.

The old Next.js `apps/web` app was removed from the active tree. Do not create
Next.js routes, pages, layouts, API routes, or components for desktop product
work.

## Bridge Contract

Components must call the Python bridge through frontend facades:

```text
route/component
  -> src/lib/api/<domain>.ts
  -> src/lib/bridge/adapter.ts
  -> window.pywebview.api
  -> desktop/bridge.py
  -> desktop/bridge_api/<domain>.py
```

Bridge types live in `src/lib/bridge/types.ts`. Mock fixture behavior lives in
`src/lib/bridge/mock.ts` and is dev-only.

## Routes

The canonical route table is `src/App.tsx`. Current areas include:

- `/` home summary;
- `/empresas`, `/empresas/:cdCvm`, company statements, model mapping, and
  coverage status;
- `/setores` and sector/subsector details;
- `/coverage`, prioritization, and work queue;
- `/news`;
- `/indicators`;
- `/settings` with health, storage, sources/imports, updates, coverage, and
  diagnostics;
- `/dev/data-ops`.

Compatibility redirects include `/atualizar-base`, `/data-coverage`,
`/status`, `/country-kpis`, and `/empresas/:cdCvm/indicadores`.

## Development

Install frontend dependencies:

```powershell
npm --prefix apps/desktop-web install
```

Real desktop dev with pywebview and the Python bridge:

```powershell
python -m desktop.app --dev
```

Browser preview without the real bridge:

```powershell
npm --prefix apps/desktop-web run dev
```

Browser preview with fixture bridge:

```powershell
npm --prefix apps/desktop-web run dev:mock
```

Checks:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

See [docs/development.md](../../docs/development.md) for data-path, lock, and
write-mode behavior.

## Source Of Truth

- Runtime architecture: [docs/architecture.md](../../docs/architecture.md)
- Data sources: [docs/data-sources.md](../../docs/data-sources.md)
- Excel exports: [docs/excel-exports.md](../../docs/excel-exports.md)
- UI implementation rules:
  [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](../../docs/skills/CVMANALYTICS_VITE_UI_SKILL.md)
