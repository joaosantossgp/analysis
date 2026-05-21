# Phase 1 — Parallel Vite SPA Shell

Covers Phase 1, Phase 1.5, and Phase 1.6. Released as code on `main` but not as a tagged binary release. Default desktop runtime still uses Next + Node (Phase 0 `v0.3.4` behaviour). The Vite SPA in `apps/desktop-web/` exists in parallel.

---

## Goals

1. Prove that a static Vite + React + TypeScript app can drive the existing Python bridge.
2. Prove that the bridge adapter pattern scales beyond one method.
3. Prove that dynamic routing + parallel async loads work inside pywebview.
4. Do all of the above without touching the released runtime, `apps/web/`, `apps/api/`, packaging, the updater, or the data pipeline.

---

## Phase 1 — Shell + health screen (commit `f01efcd`)

### What was added
- `apps/desktop-web/` — Vite 6 + React 19 + TypeScript 5 + Tailwind v4 (`@tailwindcss/vite` plugin).
- `index.html`, `vite.config.ts` (`base: "./"`, alias `@ → src`, dev server `127.0.0.1:5173`), `tsconfig.json` (strict).
- Bridge adapter at `src/lib/bridge/adapter.ts`:
  - `isBridgeAvailable()` — `typeof window.pywebview?.api !== "undefined"`.
  - `getBridgeMode()` — returns `"desktop"` or `"browser"`.
  - `whenBridgeReady(timeoutMs=5000)` — resolves on `pywebviewready` event or timeout.
  - `callBridge<K>(method, params)` — typed forward to `window.pywebview.api[method]`.
  - `BridgeError` — standard error class.
- Bridge types at `src/lib/bridge/types.ts` mirroring `desktop/bridge.py`.
- API facade at `src/lib/api/health.ts` calling `get_health`.
- Component `src/components/HealthCard.tsx` rendering status / version / database dialect / warning / error counts.
- Browser-mode fallback banner when `window.pywebview.api` is absent.

### End-to-end smoke script: `scripts/phase1_pywebview_smoke.py`
Launches `vite dev` + a pywebview window with the real `CVMBridge()` instance attached via `js_api`. The window auto-closes after a configurable timeout. A background "bridge tap" thread calls `bridge.ping`, `bridge.get_health`, etc. independently of React, so we can verify the Python side without needing browser DevTools.

### Validation
- `npm run typecheck` clean.
- `npm run build` 199 KB JS / 62 KB gzip in 878 ms.
- pywebview smoke confirmed: window opens against `http://127.0.0.1:5173/`, bridge ping returns, auto-closes.

---

## Phase 1.5 — Companies directory (commit `2b09f8e`)

### What was added
- `@tanstack/react-query` 5.62 with a desktop-tuned `QueryClient` (`staleTime: 60_000`, `gcTime: 300_000`, `refetchOnWindowFocus: false`, `retry: 1`).
- `src/lib/query.ts` exporting the shared client.
- `src/main.tsx` wraps the app in `QueryClientProvider`.
- Expanded `CompanyDirectoryItem` to all 16 fields returned by `desktop/bridge.py::get_companies`:
  ```
  cd_cvm, company_name, ticker_b3, setor_analitico, setor_cvm,
  sector_name, sector_slug, anos_disponiveis, total_rows,
  has_financial_data, coverage_rank, gics_sector,
  gics_sector_slug, gics_industry_group, gics_industry,
  gics_sub_industry
  ```
- `src/lib/api/companies.ts` — `fetchCompanies({search, sector_slug, page, page_size})` facade.
- `src/components/CompaniesTable.tsx`:
  - Debounced search (250 ms).
  - Paginated table (20 rows/page, server-side `page_size` clamp to 100).
  - States: loading / refreshing (via `keepPreviousData`) / error / empty (search-active vs no-data) / browser-mode banner.
  - Top-tab nav between Health and Companies (later replaced by router in Phase 1.6).

### Bridge contract verified
```
get_companies({page:1, page_size:3}) → {
  items[…],
  pagination: {page, page_size, total_items: 671, total_pages: 224, has_next, has_previous},
  applied_filters: {search, sector},
  _bridge_ms: <number>
}
```

### Validation
- `npm run typecheck` clean.
- `npm run build` 240 KB JS / 74 KB gzip in 1.01 s.
- Smoke: `bridge.get_companies` total=671, first=PETROBRAS.

---

## Phase 1.6 — Dynamic routing + company detail (commit `bb95ff9`)

### What was added
- `react-router-dom@7.1.0` with `HashRouter`.
  - Why HashRouter: works under `file://`, `http://127.0.0.1:<port>`, AND pywebview's `http_server=True` without server-side rewrites. Phase 2 / future can switch to `BrowserRouter` once `http_server` is the only mode.
- Routes:
  - `/` → CompaniesPage
  - `/empresas/:cdCvm` → CompanyDetailPage
  - `/health` → HealthPage
- `src/routes/CompaniesPage.tsx`, `src/routes/CompanyDetailPage.tsx`, `src/routes/HealthPage.tsx` — thin wrappers that match the route tree to existing components.
- `CompaniesTable` row name → `<Link to={`/empresas/${cd_cvm}`}>`.
- App.tsx nav switched from `useState`-tabbed view to `NavLink` tabs.

### New facade and types
- `src/lib/api/companyDetail.ts` with three functions:
  - `fetchCompanyInfo(cdCvm)` → `CompanyInfo` or `desktop-not-found`.
  - `fetchCompanyYears(cdCvm)` → `{years: number[]}`.
  - `fetchCompanyKpis(cdCvm, years)` → `KPIBundle`.
- `BridgeApi` extended with `get_company_info`, `get_company_years`, `get_company_kpis`.
- `CompanyInfo`, `CompanyYearsResult`, `KPIBundle`, `TabularData`, `TabularRow` interfaces.

### CompanyDetailPage UI
- Header card: name, ticker, CVM code, CNPJ, sector, GICS sub-industry, latest readable year, years readable, `has_local_financial_reports`, `read_availability_message` banner.
- Annual KPI table:
  - Pulls the 5 most recent years.
  - Columns: KPI name, categoria, per-year values, `DELTA_YOY_PCT` (rendered as `ΔYoY`).
  - Format-aware cell rendering driven by the row's `FORMAT_TYPE`:
    - `pct` → `XX.X%`
    - `money` → pt-BR locale, 0 decimals
    - `ratio` → 2 decimals
    - default → pt-BR locale, 2 decimals
- States: loading / browser-mode / error / not-found (with `catalog_lookup_pending` variant) / empty (no years vs no rows) / invalid CVM code.
- Back link to `/`.

### Bridge contract verified for PETROBRAS (cd_cvm=9512)
```
get_company_info(9512) → 22 keys, name=PETROBRAS, latest_readable_year=2025
get_company_years(9512) → {years: [2021, 2022, 2023, 2024, 2025]}
get_company_kpis(9512, [2023, 2024, 2025]) → annual: 22 rows × 13 columns
```

### Validation
- `npm run typecheck` clean.
- `npm run build` 285 KB JS / 89 KB gzip in 1.25 s.
- Smoke: all 3 detail methods returned the expected shape.
- Manual sign-off received: the user opened `python scripts/phase1_pywebview_smoke.py --manual`, clicked a company row, the detail page rendered with header card + KPI table, and the back link returned to the directory.

---

## Phase 1 dev runner (`scripts/phase1_pywebview_smoke.py`)

Added in Phase 1, enhanced incrementally through 1.5/1.6 and again with CLI flags.

CLI:
```
python scripts/phase1_pywebview_smoke.py            # 12s auto-close (default)
python scripts/phase1_pywebview_smoke.py --timeout 30
python scripts/phase1_pywebview_smoke.py --manual   # stays open until you close
python scripts/phase1_pywebview_smoke.py --no-auto-close  # alias
```

Background bridge-tap independent of React verifies: `ping`, `get_health`, `get_companies`, `get_company_info`, `get_company_years`, `get_company_kpis`.

---

## What was intentionally NOT changed in Phase 1.x

- `desktop/app.py` — zero edits during Phase 1.x.
- `desktop/app.spec` — zero edits during Phase 1.x.
- `desktop/build_desktop.ps1` — zero edits during Phase 1.x.
- `desktop/bridge.py` — zero edits. All Vite work reused existing methods.
- `src/**` — zero edits. No new Python service code.
- `apps/web/` — zero edits.
- `apps/api/` — zero edits.
- Updater, MOTW strip, LOCALAPPDATA migrator — untouched.
- Released `v0.3.4` runtime — unchanged.

Phase 2 is the first step that touches `desktop/app.py` / `app.spec` / `build_desktop.ps1`. See `PHASE_2_VITE_RUNTIME.md`.

---

## Commits

| Phase | Commit | Title |
|---|---|---|
| 1 | `f01efcd` | `feat(desktop-web): Phase 1 parallel Vite SPA shell` |
| 1 | `d2006e0` | `docs(migration): mark Phase 1 in progress` |
| 1.5 | `2b09f8e` | `feat(desktop-web): Phase 1.5 — companies directory screen via bridge` |
| 1.6 | `bb95ff9` | `feat(desktop-web): Phase 1.6 — dynamic routing + company detail prototype` |
| 1 dev | `2b58c6e` | `chore(smoke): manual mode + bridge indicator for phase1 dev runner` |
