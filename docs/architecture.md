# Architecture

## Current Runtime

CVMAnalytics ships as a Windows desktop app built with PyInstaller and
pywebview. The active frontend is the Vite app in `apps/desktop-web`; the
desktop app serves the built static files and exposes Python methods to
JavaScript through `window.pywebview.api`.

Verified from:

- `desktop/build_desktop.ps1`: builds `apps/desktop-web`, injects version
  provenance, then runs PyInstaller.
- `desktop/app.spec`: bundles `apps/desktop-web/dist` as `desktop-web` and
  includes `desktop/update_helper.ps1` plus approved import CSVs.
- `desktop/app.py`: resolves launch mode, configures data paths, starts
  pywebview, and creates the window with `CVMBridge`.
- `apps/desktop-web/package.json`: Vite dev/build/typecheck scripts.
- `apps/desktop-web/src/App.tsx`: `HashRouter` route table.

## Boundaries

| Layer | Path | Responsibility |
|---|---|---|
| Desktop shell | `desktop/app.py` | Launch modes, pywebview window, runtime data path setup, lock handling, startup diagnostics |
| Bridge | `desktop/bridge.py`, `desktop/bridge_api/` | Public `window.pywebview.api` methods split by domain mixin |
| Bridge services | `desktop/services.py` | Bridge-facing business logic, refresh job orchestration, read-service access |
| Frontend | `apps/desktop-web/src` | React UI, routes, data facades, bridge adapter |
| Core data layer | `src/` | CVM ingestion, SQLite schema, read service, KPIs, Excel, source modules |
| HTTP API adapter | `apps/api` | Queries, exports and explicit refresh commands; single-worker deployment, not used by packaged desktop UI |
| Landing page | `apps/landing` | Static public download/marketing page; not product runtime |

## Bridge Pattern

Frontend components should not call `window.pywebview.api` directly.

```text
React route/component
  -> apps/desktop-web/src/lib/api/<domain>.ts
  -> apps/desktop-web/src/lib/bridge/adapter.ts
  -> window.pywebview.api
  -> desktop/bridge.py
  -> desktop/bridge_api/<domain>.py
  -> desktop/services.py and src/*
```

The typed frontend mirror is `apps/desktop-web/src/lib/bridge/types.ts`.

## Service and Coverage boundaries

`src/financials/read_service.py` keeps the public `CVMReadService` facade for
existing desktop/API consumers. Query, health/coverage and export implementations
remain in `read_service_query.py`, `read_service_coverage.py` and
`read_service_export.py`. Explicit refresh/catalog-bootstrap writes live in
`refresh_commands.py`; mapping preset/default/override writes live in
`mapping_commands.py`. The facade is not a read-only capability boundary:
repositories and query-cache initialization may still write local metadata.

`apps/desktop-web/src/routes/CoveragePage.tsx` owns universe selection,
navigation and composition inside Companies at `/empresas/coverage` and its
subsections. Components under `apps/desktop-web/src/components/coverage/` own
universe lifecycle, summary/recommendation, prioritization, work queue and
capacity. Existing query keys and API facades remain shared; component extraction
does not introduce new stores or change persistence.

The persistent `src/refresh/job_worker.py` worker gives each eligible job a
bounded annual source context, including standalone jobs. It may also admit the
next already-queued job when that job has no previous attempt and the same source
scope and year range. Its FIFO peek does not claim the second job. Each job
retains its own claim, heartbeat, planning, progress, persistence, completion and
retry lifecycle.
`src/financials/source_cache.py` retains only independently copied rows for those
companies, up to 128 MiB total; over-budget files are parsed without retention.
The scraper does not also retain full market frames while this context exists.
This limit covers retained source data, not total process memory.

An admitted second job must start within 60 seconds of cohort admission to reuse
the context. A standalone job releases its context immediately on completion;
paired jobs release it when their cohort completes. Idle, stop, error,
cancellation, retry, forced refresh or incompatible configuration also releases
the context. Retried and forced jobs do not use this context.
New jobs cannot extend an existing cohort.
The legacy service cancellation callback remains supported; this optimization
does not introduce a public cancellation API for persistent jobs.

## Active Routes

Verified on 2026-11-16 against [App.tsx:108](../apps/desktop-web/src/App.tsx#L108),
[ModuleNav.tsx:16](../apps/desktop-web/src/components/shell/ModuleNav.tsx#L16) and
[SubNav.tsx:16](../apps/desktop-web/src/components/shell/SubNav.tsx#L16).
The HashRouter paths below appear after `#` in the desktop URL. Primary
navigation contains Home, Companies, Sectors, Indicators and Settings.

| Workspace / surface | Current routes | Purpose |
|---|---|---|
| Home | `/` | Analyst Home and optional saved widgets |
| Companies directory | `/empresas` | Company selection |
| Company analysis | `/empresas/:cdCvm`, `/empresas/:cdCvm/demonstrativos`, `/empresas/:cdCvm/coverage` | Overview, Financial Statements and company Coverage Status |
| Company Excel mapping | `/empresas/:cdCvm/model-mapping` | Model mapping, also available in the dedicated Excel Mapping window |
| Companies Coverage | `/empresas/coverage`, `/empresas/coverage/prioritization`, `/empresas/coverage/work-queue`, `/empresas/coverage/capacity` | Universes, prioritization, work queue and capacity |
| Companies Assets & Mapping | `/empresas/assets` | Company/asset mapping tools |
| Sectors | `/setores`, `/setores/:slug`, `/setores/:sectorSlug/:subSectorSlug` | Sector directory and detail |
| Indicators | `/indicators` | Indicator Library and Energy sections |
| Settings data | `/settings`, `/settings/data` | Overview, History range and Data completeness |
| Settings sources | `/settings/sources`, `/settings/imports`, `/settings/indicator-sources` | Sources, imports and indicator source health |
| Settings system | `/settings/storage`, `/settings/app`, `/settings/diagnostics` | Storage, app settings and diagnostics |

The Companies directory, Coverage and Assets & Mapping surfaces offer those
three tabs. Company detail instead offers Directory, Overview, Financial
Statements and Coverage Status. Coverage's Prioritization, Work Queue and
Capacity tabs appear when a universe is selected; direct links to those sections
return to Coverage overview if the universe query succeeds without an active
universe ([selection guard](../apps/desktop-web/src/routes/CoveragePage.tsx#L77)).
Data completeness (`/settings/data`) is a local-data audit surface; it is separate
from the analyst Coverage workflow under Companies. The data update itself is owned
by the app shell ([database-updates.md](database-updates.md)). Excel Mapping remains a registered
route and dedicated window, rather than a company sub-navigation tab
([window routing](../apps/desktop-web/src/App.tsx#L85)).

Assets & Mapping and Indicator Sources are exported from
[CountryKpisPage.tsx:109](../apps/desktop-web/src/routes/CountryKpisPage.tsx#L109),
but their owning workspaces are Companies and Settings, respectively.

Developer surfaces are outside primary navigation: `/dev/data-ops` requires a
DEV build and `localStorage.cvm_dev_tools = "1"`
([page gate](../apps/desktop-web/src/routes/DevDataOpsPage.tsx#L14));
`/dev/design-system` is registered only in DEV builds
([route registration](../apps/desktop-web/src/App.tsx#L159)).

### Compatibility routes

| Previous URL | Current behavior |
|---|---|
| `/coverage/*` | Redirects to the matching `/empresas/coverage/*` path, including the base `/coverage` route; preserves suffix, query and fragment |
| `/indicators?section=entities` (also `section=discover`) | Redirects to `/empresas/assets` |
| `/indicators?section=health` | Redirects to `/settings/indicator-sources` |
| `/settings/updates`, `/settings/health`, `/settings/coverage`, `/atualizar-base`, `/company-universe`, `/data-coverage` | Redirect to `/settings/data` |
| `/status` | Redirects to `/settings/diagnostics` |
| `/country-kpis` | Redirects to `/indicators` |
| `/empresas/:cdCvm/indicadores` | Redirects to that company's overview at `/empresas/:cdCvm` |

The [Coverage redirect](../apps/desktop-web/src/App.tsx#L189) preserves the full
location. [Indicator section redirects](../apps/desktop-web/src/routes/CountryKpisPage.tsx#L121)
remove `section` and preserve other query parameters, but not the fragment.
The remaining fixed-path redirects do not forward query parameters or fragments.

### Retired News UI

`/news/*`, including `/news` and `/news/latest`, renders
[RetiredNewsPage](../apps/desktop-web/src/routes/RetiredNewsPage.tsx#L4): a retirement
notice with links to Home and Companies, without loading news. It is not an active
News workspace or a redirect to a news feed.

Saved Home `top-news` widgets render
[RetiredNewsCard](../apps/desktop-web/src/components/home/widgets/RetiredNewsCard.tsx#L5),
which preserves the saved configuration, offers removal and does not query news.
The widget is no longer offered for new layouts. News storage and backend code,
including [NewsBridgeMixin](../desktop/bridge.py#L26) and `src/news/`, remain;
retiring the UI did not delete downloaded data or saved settings.

## Local-First Model

The packaged app writes runtime data under
`%USERPROFILE%\Documents\CVMAnalytics` unless overridden. The install folder is
treated as application code/assets, not as mutable user data. Already-downloaded
data remains usable offline; refreshes, market-data updates, news collection,
and software update checks require network access.

SQLite databases, source files, caches, logs, and Excel outputs are local
artifacts. The bridge exposes explicit loading, empty, error, and blocked states
instead of silently falling back to remote services.

## Legacy And Historical Areas

See "Historical / Non-Canonical" in
[`docs/reference/repository-map.md`](reference/repository-map.md).

## Open Questions

- The [multi-window workbench research](research/2026-11-04-multi-window-workbench.md)
  evaluates native windows and Home docking. Goal #464 and planning #466 were
  closed as not planned for now on 2026-11-13. The research is preserved for
  reference; [incremental app delivery](PRODUCT_DIRECTION.md#delivery-direction-2026-11-13)
  is the current direction.
- The [multi-window local-storage research](research/local-multi-window-storage.md)
  evaluates shared data ownership, SQLite/Parquet, DuckDB and DuckLake for future
  scale. It is a recommendation requiring benchmarks, not an accepted migration
  or a replacement for ADR 0007.
- Packaged runtime behavior must still be validated from the built executable
  before each release; source inspection alone does not prove WebView2,
  PyInstaller, updater, or filesystem behavior on a clean machine.
- Some source modules expose optional/experimental data surfaces. Document them
  as optional unless their route, bridge method, and persistence path are
  verified.
