# apps/desktop-web — Vite SPA desktop runtime prototype

## Status

**Phase 3F experimental runtime.** This package exists in parallel to `apps/web/` (Next.js). It does **not** replace the default production UI yet. The default desktop executable still starts the Next.js standalone server through bundled Node; passing `--vite` starts this Vite SPA instead.

Screens with dynamic routing prove the architecture:

- **Companies directory** (`/`) — Phase 3D dense table backed by `CVMBridge.get_companies` and `get_company_filters`. URL-driven `?search=&sector=&page=`, debounced search by name/ticker/CVM code, GICS sector dropdown, active-filter chips with per-filter clear, reset action, result count, dense columns (company / ticker / CVM / sector / sub-industry / years / rows / data dot), loading/error/empty/filtered-empty states. Powered by TanStack Query.
- **Sectors directory** (`/setores`) — Phase 3D. GICS hub view backed by `get_sectors`. Tab switcher between GICS sectors and GICS sub-industries (`?visao=sub_sector`), per-row company count and latest year, link to filtered companies directory and to sector detail. No invented aggregate metrics.
- **Sector detail** (`/setores/:slug`) — Phase 3D. Backed by `get_sector_detail`. Breadcrumb, company count + base-year header, year selector (`?ano=`), in-sector company filter (`?q=`), company table with links to company detail, link back to the directory filtered by sector.
- **Company detail** (`/empresas/:cdCvm`) — dynamic route. Fetches `get_company_info`, `get_company_years`, and `get_company_kpis` in parallel. Header card + annual KPI table with format-aware cells (pct/money/ratio). **Phase 3E**: full company workbook Excel export button (writes to `Documents/CVMAnalytics/output/` via `export_company_excel`). **Phase 3F**: single-company refresh panel using existing `request_refresh({ cd_cvm })` and `get_refresh_status({ cd_cvm })`, with real backend freshness/status fields, 2s active polling, dispatch feedback, and query invalidation after terminal status.
- **Indicadores (KPIs)** (`/empresas/:cdCvm/indicadores`) — Phase 3C.1. Year multi-select with "Last 5" / "All" presets, KPI summary cards for the latest selected year, annual + quarterly tables with unit-aware formatting (R$ mn / % / x / bps). Missing values render as em dash. Phase 3E adds the same full-workbook export action (KPIs are included in the workbook the backend builds).
- **Financial statements** (`/empresas/:cdCvm/demonstrativos?stmt=DRE`) — DRE/BPA/BPP/DFC matrix via `get_company_statement`, with real data, statement switching, row filtering, loading/error/empty states. Phase 3E adds the full-workbook export action; per-statement export is not yet supported by the backend.
- **Update Base** (`/atualizar-base`) — local database health, empty-DB guidance, real DB diagnostics panel (db_path, data_root, row counts via `get_database_diagnostics`), post-job row-count delta with explicit warning when a refresh inserts zero rows, guarded refresh start with optional CVM-code targeting, job polling, logs, history, cancel.
- **Runtime health** (`/health`) — `CVMBridge.get_health()` rendering status, version, dialect.

Persistent data root (Phase 3C.0): `%USERPROFILE%\Documents\CVMAnalytics` by default; override with `CVMANALYTICS_DATA_DIR`. On first launch the app does a WAL-safe `sqlite3.backup` from any legacy `%LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db` or `<install-dir>\data\db\cvm_financials.db` it finds. Legacy originals are never moved or deleted.

Router: `react-router-dom` v7 with `HashRouter` (portable across `file://`, `http://127.0.0.1:<port>`, and pywebview's `http_server=True`).

## Goal

Prove that a static Vite + React + TypeScript build can drive the existing Python bridge (`desktop/bridge.py::CVMBridge`) without an embedded Node runtime. Once the prototype reaches parity and soaks successfully, Phase 3 may replace `apps/web/` and remove the bundled `node.exe`.

## What is here

```
apps/desktop-web/
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── public/
└── src/
    ├── App.tsx
    ├── main.tsx
    ├── index.css
    ├── components/
    │   └── HealthCard.tsx
    └── lib/
        ├── bridge/
        │   ├── adapter.ts     # single chokepoint for window.pywebview.api
        │   └── types.ts       # typed mirror of Python bridge methods
        └── api/
            ├── health.ts
            ├── companyDetail.ts
            ├── companyRefresh.ts
            ├── companies.ts
            ├── statements.ts
            └── updateBase.ts
```

## Bridge pattern

Components MUST NOT touch `window.pywebview.api` directly. They go through:

```
UI component
  -> lib/api/<facade>.ts     (one file per domain area)
  -> lib/bridge/adapter.ts   (callBridge + whenBridgeReady)
  -> window.pywebview.api    (injected by pywebview at runtime)
  -> Python bridge (desktop/bridge.py)
  -> Python service/core (src/*)
```

`callBridge<K>(method, params)` is the only typed entry point. Adding a new bridge method is a two-step change: add the signature to `BridgeApi` in `lib/bridge/types.ts`, then add a facade under `lib/api/`.

## Dev — browser

```bash
cd apps/desktop-web
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`. The `HealthCard` will show a yellow "Browser-mode preview" banner because `window.pywebview.api` is not injected by a real browser. This is the expected dev-without-Python flow.

## Dev — inside pywebview

```bash
cd <repo root>
python -m desktop.app --vite
```

This serves the built static assets from `apps/desktop-web/dist/` over a loopback HTTP server and opens them inside pywebview with the real `CVMBridge()` attached. For live Vite dev-server testing, use `python scripts/phase1_pywebview_smoke.py --manual`.

## Build

```bash
cd apps/desktop-web
npm run build
```

Output is a static SPA at `apps/desktop-web/dist/`.

## Phase 2 — opt-in `--vite` launch mode

The packaged desktop executable now ships the Vite SPA alongside the Next standalone server. The default mode is unchanged (Next). Pass `--vite` to load this SPA instead:

```powershell
# packaged
.\dist\CVMAnalytics\CVMAnalytics.exe --vite

# dev (against apps/desktop-web/dist/)
python -m desktop.app --vite

# dev with live reload (Vite dev server + pywebview, interactive)
python scripts/phase1_pywebview_smoke.py --manual
```

In `--vite` mode:

- pywebview loads `_internal/desktop-web/index.html` over a local HTTP server bound to a free port (`http.server.ThreadingHTTPServer`). No `file://` origin issues with WebView2.
- The Python bridge is the same `CVMBridge()` the Next mode uses.
- `%USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db` is read/written exactly as in default mode unless `CVMANALYTICS_DATA_DIR` overrides it.
- **No `node.exe` process is launched.** Verified end-to-end against the packaged exe.

The current default still launches the Next standalone server via the bundled `node.exe`. Removing Node and `web_standalone/` is deferred to Phase 3 (only after parity).

## What this does NOT do yet

- Does not become the default desktop runtime.
- Does not remove Next.js, FastAPI, `web_standalone/`, or bundled `node.exe`.
- Does not cover every production screen yet: complete KPI/indicator chart parity, sub-sector detail route (`/setores/[slug]/[sub_slug]`), per-statement Excel export scope (backend currently emits one workbook per company), advanced update-base filters, and updater UI remain on the legacy Next path.
- Uses TanStack Query for directory, sectors, detail, refresh, and export status screens.
- Does not call FastAPI. Bridge-only.
