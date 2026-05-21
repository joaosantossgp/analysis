# apps/desktop-web — Vite SPA desktop runtime prototype

## Status

**Phase 2 experimental runtime.** This package exists in parallel to `apps/web/` (Next.js). It does **not** replace the default production UI yet. The default desktop executable still starts the Next.js standalone server through bundled Node; passing `--vite` starts this Vite SPA instead.

Three screens with dynamic routing prove the architecture:

- **Companies directory** (`/`) — `CVMBridge.get_companies(...)` with debounced search, pagination, loading/error/empty states. Powered by TanStack Query.
- **Company detail** (`/empresas/:cdCvm`) — dynamic route. Fetches `get_company_info`, `get_company_years`, and `get_company_kpis` in parallel. Header card + annual KPI table with format-aware cells (pct/money/ratio).
- **Runtime health** (`/health`) — `CVMBridge.get_health()` rendering status, version, dialect.

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
            └── health.ts      # facade consumed by components
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
- `%LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db` is read/written exactly as in default mode.
- **No `node.exe` process is launched.** Verified end-to-end against the packaged exe.

The current default still launches the Next standalone server via the bundled `node.exe`. Removing Node and `web_standalone/` is deferred to Phase 3 (only after parity).

## What this does NOT do yet

- Does not become the default desktop runtime.
- Does not remove Next.js, FastAPI, `web_standalone/`, or bundled `node.exe`.
- Does not cover every production screen yet: sectors, update-base, Excel export, and updater UI remain on the legacy Next path.
- Uses TanStack Query for the companies screen (added in Phase 1.5).
- Does not call FastAPI. Bridge-only.
