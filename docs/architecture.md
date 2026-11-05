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

## Active Routes

The current route table is in `apps/desktop-web/src/App.tsx`. Active top-level
areas include:

- `/` home summary;
- `/empresas` company directory;
- `/empresas/:cdCvm` company overview;
- `/empresas/:cdCvm/demonstrativos` financial statements;
- `/empresas/:cdCvm/model-mapping` Excel model mapping;
- `/empresas/:cdCvm/coverage` coverage status;
- `/setores` and sector/subsector detail routes;
- `/coverage`, `/coverage/prioritization`, `/coverage/work-queue`;
- `/news` and `/news/latest`;
- `/indicators`;
- `/settings` with health, storage, sources/imports, updates, coverage, and
  diagnostics sections;
- `/dev/data-ops` for development data operations.

Compatibility redirects:

- `/atualizar-base` -> `/settings/updates`;
- `/data-coverage` -> `/settings/coverage`;
- `/status` -> `/settings/diagnostics`;
- `/country-kpis` -> `/indicators`;
- `/empresas/:cdCvm/indicadores` -> `/empresas/:cdCvm`.

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
  evaluates native windows and Home docking. Goal #464 and planning #466 remain
  open; publishing the initial studies in #465 does not approve implementation.
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
