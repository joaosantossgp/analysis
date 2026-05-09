# Architecture Audit

Project recovery diagnostic for issue #328. This audit is based on repository inspection only. No application code was changed.

## 1. Framework and package manager

- Desktop product: Windows app built from `desktop/build_desktop.ps1`, launched by `desktop/app.py`, using pywebview and a bundled Next.js standalone server.
- Web UI: Next.js App Router in `apps/web/app`, React 19, TypeScript, Tailwind CSS 4, shadcn/Base UI style components. Package manager is npm, evidenced by `apps/web/package.json` and `apps/web/package-lock.json`.
- Backend API: FastAPI in `apps/api/app/main.py`, with routers under `apps/api/app/routes`.
- Core/data runtime: Python modules under `src`.
- Legacy/secondary UI: Streamlit dashboard under `dashboard`; PyQt desktop legacy files under `desktop/cvm_pyqt_app.py`, `desktop/ui.py`, and `desktop/controller.py`.
- Python dependency management is requirements-file based: `requirements.txt`, `apps/api/requirements.txt`, `apps/api/requirements-dev.txt`, and `apps/api/requirements-prod.txt`.

## 2. Folder structure

- `apps/web`: Next.js UI, local API proxy routes, React components, TypeScript client/server data loaders, tests.
- `apps/api`: FastAPI app, presenters, dependency wiring, routers, API tests.
- `src`: scraper, database access, read service, query layer, refresh jobs, GICS mapping, KPI engine, settings.
- `desktop`: pywebview desktop entrypoint, Python bridge, desktop refresh manager, packaging scripts, legacy PyQt code.
- `dashboard`: Streamlit app and tabs.
- `scripts`: operational setup, validation, refresh, smoke, and release scripts.
- `docs`: product, governance, architecture, release, and local operations docs.
- `.github`: workflows, guardrails, issue templates.
- `data`: local runtime data and SQLite location. This folder exists locally but should be treated carefully because runtime data can be large or environment-specific.

## 3. Main routes/pages

Actual Next.js pages found under `apps/web/app`:

- `/`: `apps/web/app/page.tsx`
- `/empresas`: `apps/web/app/empresas/page.tsx`
- `/empresas/[cd_cvm]`: `apps/web/app/empresas/[cd_cvm]/page.tsx`
- `/setores`: `apps/web/app/setores/page.tsx`
- `/setores/[slug]`: `apps/web/app/setores/[slug]/page.tsx`
- `/atualizar-base`: `apps/web/app/atualizar-base/page.tsx`
- `/portfolio`: `apps/web/app/portfolio/page.tsx`
- `/demo-analysis`: `apps/web/app/demo-analysis/page.tsx`
- `/design-system`: `apps/web/app/design-system/page.tsx`

Unclear: documentation still references `/comparar` in `docs/INTERFACE_MAP.md`, `docs/SITEMAP.MD`, `docs/DESKTOP_ONLY_GAP_MAP.md`, and `docs/V2_PHASE2_WEB_SLICE.md`, but no `apps/web/app/comparar/page.tsx` exists in the current tree.

## 4. API routes, server actions, or backend functions

Next.js local API/proxy routes:

- `apps/web/app/api/health/route.ts`
- `apps/web/app/api/base-health/route.ts`
- `apps/web/app/api/companies-directory/route.ts`
- `apps/web/app/api/company-search/route.ts`
- `apps/web/app/api/company-view/route.ts`
- `apps/web/app/api/companies/[cd_cvm]/excel/route.ts`
- `apps/web/app/api/refresh-status/[cd_cvm]/route.ts`
- `apps/web/app/api/request-refresh/[cd_cvm]/route.ts`
- `apps/web/app/api/refresh-batch/route.ts`
- `apps/web/app/api/refresh-jobs/route.ts`
- `apps/web/app/api/refresh-jobs/[job_id]/route.ts`
- `apps/web/app/api/refresh-jobs/[job_id]/cancel/route.ts`

FastAPI routers:

- `apps/api/app/routes/health.py`
- `apps/api/app/routes/companies.py`
- `apps/api/app/routes/sectors.py`
- `apps/api/app/routes/status.py`
- `apps/api/app/routes/analytics.py`
- `apps/api/app/routes/refresh.py`

Backend service entrypoints:

- `apps/api/app/main.py` creates the FastAPI app and wires `CVMReadService`.
- `src/read_service.py` is the main read/use-case service for companies, sectors, KPIs, statements, refresh state, base health, and Excel export.
- `desktop/bridge.py` exposes similar operations to the Next.js UI through `window.pywebview.api`.
- `desktop/services.py` contains desktop refresh and operational services.

No server actions were identified in the inspected routes. The app uses App Router pages plus route handlers and Python/FastAPI/bridge services.

## 5. Database access layer

- Connection/settings: `src/settings.py` resolves paths, `DATABASE_URL`, `SQLITE_PATH`, and local data/cache paths.
- SQLAlchemy engine factory: `src/db.py` and `src/database.py`.
- Schema initialization: `src/database.py` creates `financial_reports`, `qa_logs`, `companies`, and `company_views`; `src/refresh_jobs.py` creates `refresh_jobs` and `company_refresh_status`.
- Read queries: `src/query_layer.py`.
- Read orchestration and DTO construction: `src/read_service.py`.
- Write/ingest path: `src/database.py` through `CVMDatabase.insert_company_data`, called by scraper/refresh flows.

Default runtime is SQLite at `data/db/cvm_financials.db`, with optional PostgreSQL via `DATABASE_URL`. Desktop packaged mode sets `CVM_DATA_DIR`, `CVM_DB_DIR`, `SQLITE_PATH`, `CVM_OUTPUT_DIR`, and `CVM_LOG_DIR` in `desktop/app.py`.

## 6. Source of truth for the company universe

There is more than one source, depending on context:

- Remote CVM catalog: `src/company_catalog.py` uses `https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv`.
- Desktop active-universe workflow: `desktop/services.py` reads CVM catalog data and caches active universe data at `data/cache/active_universe_cache.json` via `src/settings.py`.
- Local searchable universe for the app: `companies` table in SQLite/PostgreSQL, queried by `src/query_layer.py` and wrapped by `src/read_service.py`.

Unclear: the product decision for recovery should define whether the user-facing universe is all active CVM companies, only companies present in local `companies`, or only companies with readable annual data.

## 7. Source of truth for company metadata

- Primary local metadata table: `companies`, created and migrated in `src/database.py`.
- Metadata read path: `src/query_layer.py` and `src/read_service.py`.
- Ingest upsert path: `src/database.py` updates `companies` during `insert_company_data`.
- Remote fallback metadata: `src/company_catalog.py`; `src/read_service.py` can use catalog fallback for unknown local companies.
- Supplemental ticker/static references: `src/ticker_map.py` and scripts such as `scripts/seed_catalog.py`, `scripts/setup_companies_table.py`, and `scripts/expand_tickers.py`.

Unclear: whether remote CVM fallback should be visible in all UI flows or only in search/detail handoff cases.

## 8. Source of truth for GICS sector and sub-sector

- GICS classification code: `src/gics_manual_mapping.py`.
- Sector slug/name normalization: `src/sector_taxonomy.py`.
- Stored GICS fields: `companies.gics_sector`, `companies.gics_sector_slug`, `companies.gics_industry_group`, `companies.gics_industry`, and `companies.gics_sub_industry`, created/migrated in `src/database.py`.
- Query/read usage: `src/query_layer.py` and `src/read_service.py`.
- Backfill/patch scripts: `scripts/backfill_company_gics.py` and `scripts/patch_database_sectors_v2.py`.

Risk: GICS appears both as computed mapping code and persisted database columns. Recovery should decide which is authoritative when they disagree.

## 9. Source of truth for historical/local data

- Financial statement facts: `financial_reports` table, created in `src/database.py`.
- Refresh state: `refresh_jobs` and `company_refresh_status` from `src/refresh_jobs.py`.
- Local DB path: `data/db/cvm_financials.db` by default, or `SQLITE_PATH`/`DATABASE_URL` via `src/settings.py`.
- Cache files: `data/cache/base_health_snapshot.json`, `data/cache/processed_presence_index.json`, and `data/cache/active_universe_cache.json` from `src/settings.py`.
- CVM raw source: DFP/ITR files under `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC`, configured in `src/settings.py`.

## 10. How the app detects whether a company has local data

The app uses multiple signals:

- Directory-level local data signal: `src/query_layer.py` left-joins `companies` to `financial_reports` and exposes `has_financial_data`, `total_rows`, and available years.
- Detail/readability signal: `src/query_layer.py` joins local financial data and `company_refresh_status`, then `src/read_service.py` exposes fields such as `has_readable_current_data`, `readable_years_count`, `latest_readable_year`, `read_availability_code`, and `read_availability_message`.
- Frontend handoff/readiness: `apps/web/lib/company-detail-handoff.ts` derives readable years from `CompanyInfo` plus `fetchCompanyYears`.
- Refresh card/state: `apps/web/lib/company-refresh-state.ts` uses refresh status fields including `has_readable_current_data`, `latest_readable_year`, and reason codes.

Risk: `has_financial_data` and `has_readable_current_data` are not the same concept. UI copy and gating should not treat them as interchangeable.

## 11. Data flow for `/empresa`

There is no `/empresa` route in the current Next.js tree. The actual company routes are `/empresas` and `/empresas/[cd_cvm]`.

Observed `/empresas/[cd_cvm]` flow:

1. Page: `apps/web/app/empresas/[cd_cvm]/page.tsx`.
2. Data client abstraction: `apps/web/lib/api.ts`.
3. Browser desktop mode: `apps/web/lib/api.ts` calls `apps/web/lib/desktop-bridge.ts`, which calls `desktop/bridge.py`.
4. Web/API mode: `apps/web/lib/api.ts` calls FastAPI endpoints under `apps/api/app/routes/companies.py`.
5. Shared backend service: `src/read_service.py`.
6. SQL read layer: `src/query_layer.py`.
7. Database tables: `companies`, `financial_reports`, `company_refresh_status`, `company_views`.
8. UI model helpers: `apps/web/lib/company-dashboard.ts`, `apps/web/lib/company-detail-handoff.ts`, `apps/web/lib/company-period-range.ts`, and components under `apps/web/components/company`.

Unclear: whether `/empresa` in the request means a desired singular route alias or the existing `/empresas/[cd_cvm]` detail page.

## 12. Data flow for `/setores`

Observed `/setores` flow:

1. Page: `apps/web/app/setores/page.tsx`.
2. Loader: `apps/web/lib/sectors-page-data.ts`.
3. API abstraction: `apps/web/lib/api.ts` via `fetchSectorDirectory`.
4. Desktop mode: `apps/web/lib/desktop-bridge.ts` -> `desktop/bridge.py` method `get_sectors`.
5. Web/API mode: FastAPI route `apps/api/app/routes/sectors.py` endpoint `/sectors`.
6. Shared service: `src/read_service.py` method `list_sectors`.
7. Query/data sources: `src/query_layer.py`, `companies`, `financial_reports`, GICS fields, KPI calculations from `src/kpi_engine.py`.

Observed `/setores/[slug]` flow:

1. Page: `apps/web/app/setores/[slug]/page.tsx`.
2. Loader: `apps/web/lib/sectors-page-data.ts`.
3. API abstraction: `fetchSectorDetail`.
4. Desktop bridge or FastAPI `/sectors/{sector_slug}`.
5. Shared service: `src/read_service.py` method `get_sector_detail`.

## 13. Data flow for Atualizar base

Observed `/atualizar-base` flow:

1. Page: `apps/web/app/atualizar-base/page.tsx`.
2. UI/controller component: `apps/web/components/update-base/update-base-page.tsx`.
3. API abstraction: `apps/web/lib/api.ts` functions for base health, batch refresh, job status, job list, and cancellation.
4. Desktop mode: `apps/web/lib/desktop-bridge.ts` calls `desktop/bridge.py`; batch refresh is handled by `DesktopRefreshJobManager` in `desktop/services.py`.
5. Web/API mode: Next route handlers under `apps/web/app/api/refresh-*` proxy to FastAPI `apps/api/app/routes/refresh.py` and `apps/api/app/routes/status.py`.
6. Shared selection logic: `src/read_service.py` function `resolve_refresh_batch_selection`.
7. API job manager: `apps/api/app/services/refresh_jobs.py`.
8. Core refresh runtime: `src/refresh_service.py`, `src/refresh_jobs.py`, `src/refresh_job_worker.py`, and scraper/database modules.

Risk: desktop and API have separate refresh job managers, while some selection logic is shared in `src/read_service.py`. This is a likely source of behavioral drift.

## 14. Whether the Compare tab/page still exists

No current Compare page was found in `apps/web/app`.

Evidence:

- `rg --files apps/web/app` lists no `apps/web/app/comparar/page.tsx`.
- `rg --files apps/web/components` lists no `apps/web/components/compare` directory.
- `rg --files apps/web/lib` lists no `compare-page-data.ts` or `compare-utils.ts`.

Stale references remain in `docs/INTERFACE_MAP.md`, `docs/SITEMAP.MD`, `docs/DESKTOP_ONLY_GAP_MAP.md`, `docs/V2_PHASE2_WEB_SLICE.md`, `docs/PRODUCT_PAGE_PROMPTS.md`, and `apps/web/app/not-found.tsx`.

## 15. Hardcoded values

Notable hardcoded values found:

- Desktop dev port and URL: `desktop/app.py` uses port `3000` and `http://127.0.0.1:3000`.
- Desktop window size and background: `desktop/app.py`.
- API default URL: `apps/web/lib/api.ts` defaults to `http://127.0.0.1:8000`.
- FastAPI CORS default origin: `apps/api/app/main.py` defaults to `http://localhost:3000`.
- Refresh start year default: `2010` appears in `src/read_service.py`, `desktop/services.py`, `apps/api/app/services/refresh_jobs.py`, API route defaults, and frontend tests.
- Top companies list: `POPULARES_CVM_IDS` in `src/read_service.py` is a static top-10 B3 market-cap ranking.
- KPI frontend catalog: `apps/web/lib/company-dashboard.ts` has `KPI_CATALOG`.
- KPI backend catalog/formulas: `src/kpi_engine.py` has `_KPI_CATALOG`.
- Dashboard copy still states "449 empresas" in `dashboard/app.py`; design/demo copy also references 449+ in `apps/web/app/design-system/page.tsx` and other docs.
- Trust strip fallback displays `"449"` in `apps/web/components/home/trust-strip.tsx`.

## 16. Mock data

Mock/test data is present and expected in tests:

- Python tests use mocks heavily, especially `tests/test_scraper.py`, `tests/test_cvm_pyqt_app.py`, and database/API tests.
- Web tests mock fetch/bridge behavior under `apps/web/tests`.
- Smoke DB seeding exists in `scripts/seed_web_smoke_db.py`.

Product/demo mock or placeholder areas found:

- `apps/web/app/demo-analysis/page.tsx` appears to be a demo page with local UI data.
- `apps/web/app/portfolio/page.tsx` contains placeholder portfolio data.
- `apps/web/components/area-chart-medium.tsx` contains example comparison text.
- `src/kpi_engine.py` marks some valuation KPIs as placeholders.

Unclear: whether `/demo-analysis`, `/portfolio`, and design-system/demo components are intended to ship in the desktop product.

## 17. Duplicated business logic

Likely duplicated or drift-prone logic:

- Refresh batch/job handling exists in both `desktop/services.py` and `apps/api/app/services/refresh_jobs.py`; selection logic is shared through `src/read_service.py`, but job lifecycle code is separate.
- Company local-data/readiness interpretation exists in backend DTO construction (`src/read_service.py`, `src/query_layer.py`) and frontend state helpers (`apps/web/lib/company-detail-handoff.ts`, `apps/web/lib/company-refresh-state.ts`).
- GICS sector normalization is computed in `src/gics_manual_mapping.py` but also stored in `companies` and consumed by multiple read paths.
- KPI catalog exists in backend formulas (`src/kpi_engine.py`) and frontend display catalog (`apps/web/lib/company-dashboard.ts`).
- Desktop bridge methods in `desktop/bridge.py` mirror FastAPI routes in `apps/api/app/routes`, with separate error handling and serialization.
- Update-base status/progress logic exists across `apps/web/components/update-base/update-base-page.tsx`, `apps/web/lib/update-base-admin.ts`, `desktop/services.py`, `apps/api/app/services/refresh_jobs.py`, and `src/refresh_jobs.py`.

## 18. Existing GitHub/local validation commands

Documented or configured validation commands:

- Python tests: `pytest tests -q`
- API tests: `pytest apps/api/tests -q`
- Combined coverage command in `README.md`: `pytest tests apps/api/tests -q --cov=src --cov=desktop --cov=dashboard --cov=apps/api/app --cov-report=xml:coverage.xml --cov-report=term`
- Runtime doctor: `python scripts/runtime_doctor.py --require-db --table financial_reports --table companies --require-canonical`
- DB portability: `python scripts/db_portability_smoke.py --write-check`
- Web lint: from `apps/web`, `npm run lint`
- Web typecheck: from `apps/web`, `npm run typecheck`
- Web unit tests: from `apps/web`, `npm run test:unit`
- Web build: from `apps/web`, `npm run build`
- Web e2e: from `apps/web`, `npm run test:e2e`
- Desktop build: `.\desktop\build_desktop.ps1`
- Update-base smoke: `python scripts/update_base_smoke.py --dry-run --mode missing --limit 1`

CI evidence:

- `.github/workflows/ci.yml` runs Python tests, coverage, seeds a web smoke DB, then runs web lint, typecheck, unit tests, build, and Playwright smoke.

## 19. Highest-risk files

- `src/read_service.py`: central business orchestration; large surface area for companies, sectors, refresh, health, KPIs, Excel.
- `src/query_layer.py`: SQL read behavior and local-data detection.
- `src/database.py`: schema, ingest writes, metadata upsert, idempotency.
- `src/refresh_jobs.py`: durable refresh state and status/readability synchronization.
- `desktop/services.py`: desktop refresh manager and active-universe/base-health logic.
- `desktop/bridge.py`: desktop UI/backend boundary and error serialization.
- `apps/web/lib/api.ts`: central frontend API/bridge abstraction and runtime mode switching.
- `apps/web/components/update-base/update-base-page.tsx`: large UI state surface for administrative refresh.
- `apps/web/app/empresas/[cd_cvm]/page.tsx`: main company detail route.
- `apps/web/app/setores/page.tsx` and `apps/web/app/setores/[slug]/page.tsx`: sector flows.
- `src/gics_manual_mapping.py` and `scripts/backfill_company_gics.py`: sector/sub-sector correctness.
- `apps/api/app/services/refresh_jobs.py`: API-mode job lifecycle; can drift from desktop behavior.

## 20. Recommended recovery sequence using small issues

1. Docs truth issue: reconcile stale route docs with current routes, especially `/comparar` references. Write-set: `docs/INTERFACE_MAP.md`, `docs/SITEMAP.MD`, `docs/DESKTOP_ONLY_GAP_MAP.md`, `apps/web/app/not-found.tsx` only if product confirms.
2. Product decision issue: define the company universe policy: all active CVM companies, local `companies`, or only readable companies.
3. Data-readiness contract issue: document and test the difference between `has_financial_data`, `has_readable_current_data`, available years, and refresh status.
4. GICS authority issue: decide whether stored DB GICS columns or computed mapping are authoritative, then add a validation script/test for mismatches.
5. Compare recovery issue: decide whether `/comparar` is removed, paused, or must be restored. Do not implement until decision is made.
6. Update-base behavior issue: write a contract for desktop batch refresh states and API batch refresh states before changing UI.
7. Hardcoded constants issue: centralize only the constants that are truly product/runtime policy, starting with `2010`, top companies, and displayed company count.
8. Validation baseline issue: run and record current `pytest`, web lint/typecheck/unit/build, runtime doctor, and update-base smoke before bug fixes.
9. Highest-risk bug-fix issues: fix one flow at a time after the above contracts are clear: `/empresas/[cd_cvm]`, `/setores`, then `/atualizar-base`.

## Human decisions required before implementation

- Decide whether the canonical product for this recovery remains desktop-only (`dist/CVMAnalytics/CVMAnalytics.exe`) or whether hosted FastAPI/Next.js behavior must be treated as equal priority.
- Decide what the user-facing company universe means: all active CVM companies, companies in the local `companies` table, companies with any `financial_reports`, or companies with readable annual data.
- Decide whether remote CVM catalog fallback should appear in normal search/detail UX or only as an explicit "not local yet" discovery path.
- Decide whether `companies` metadata or remote CVM catalog metadata wins when names, tickers, sectors, or status differ.
- Decide whether GICS values are authoritative from persisted DB columns, computed mapping in `src/gics_manual_mapping.py`, or a future curated metadata table.
- Decide whether `/comparar` should be restored, formally removed from docs/navigation, or kept as a paused roadmap item.
- Decide whether `/portfolio`, `/demo-analysis`, and `/design-system` are shipping product routes in the desktop app or internal/demo routes.
- Decide whether "Atualizar base" should be available to end users, hidden/admin-only, or treated as maintainer tooling.
- Decide whether batch refresh should support API/cloud mode, desktop mode only, or both with an explicit shared contract.
- Decide acceptable behavior for companies with partial data, no annual data, quarterly-only data, or stale successful data.
- Decide whether hardcoded top-10 popular companies are acceptable product policy or must come from market-data ranking.
- Decide whether valuation placeholder KPIs should remain visible, be hidden, or be implemented with market data.
- Decide whether local cache files under `data/cache` are operational state, reproducible inputs, or disposable cache.
- Decide risk tolerance for changing schema/readiness logic before a full DB backup and validation baseline.
