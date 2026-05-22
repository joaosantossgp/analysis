# Desktop Runtime Migration

## Goal

Simplify the production desktop runtime from:

- Python data pipeline
- SQLite
- Next.js standalone server
- bundled Node runtime
- pywebview
- PyInstaller

To:

- Python authoritative runtime
- pywebview/WebView2 desktop shell
- static Vite + React + TypeScript frontend loaded by pywebview
- no production Next standalone server
- no production Node runtime
- protected user data under `%LOCALAPPDATA%\CVMAnalytics`

## Non-goals

- Do not migrate to Electron.
- Do not migrate to Tauri for this migration.
- Do not move away from SQLite unless a separate audit proves it is needed.
- Do not create a hosted SaaS architecture.
- Do not add telemetry/Sentry to the local desktop app.

## Phase status

| Phase | Name | Status | Notes |
|---|---|---|---|
| Phase 0 | User-data safety net | Released as v0.3.4 (hotfix #4); stable | v0.3.4 fixes CI zip layout to be updater-compatible (flat root). Full contract pass: fresh install + MOTW + updater staging + helper swap + user-data preservation. |
| Phase 1 | Parallel Vite SPA shell | Done | apps/desktop-web/ with react-router HashRouter, TanStack Query, 3 screens (companies / company detail / health) |
| Phase 2 | Wire Vite SPA into pywebview | Experimental (opt-in `--vite` flag) | Packaged exe ships both Next standalone and Vite static SPA; default = Next, `--vite` = Vite with zero Node processes. GitHub-downloaded release artifact validation is mandatory before calling a release good. No removals yet. |
| Phase 3A | Functional parity matrix + first missing Vite screen | Released as v0.5.0 | Parity matrix lives in `PHASE_3_PARITY_MATRIX.md`; company financial statements are implemented in `apps/desktop-web`. No deletion, no default switch. |
| Phase 3B | Update Base / Refresh Data parity slice | Released as v0.6.0 | Vite route `/atualizar-base` uses the existing desktop refresh bridge methods for base health, guarded refresh start, optional CVM-code targeting, polling, logs, cancel, and empty-DB guidance. Default remains Next. |
| Phase 3C | Persistent Documents data root + Vite Indicadores | Released as v0.7.0 | Default runtime data root is `%USERPROFILE%\Documents\CVMAnalytics` (WAL-safe migration from `%LOCALAPPDATA%`); new `/empresas/:cdCvm/indicadores` route with year multi-select and KPI cards. Default remains Next. |
| Phase 3D | Sectors + company directory filters | Released as v0.8.0 | Vite directory gains GICS sector filter, URL-driven chips, CVM-code search, dense table; new `/setores` and `/setores/:slug` routes for sector browsing and per-sector company tables. No invented aggregate metrics. Default remains Next. |
| Phase 3E | Excel export from Vite | Released as v0.9.0 | Full company workbook export from company detail, statements, and indicadores screens. Writes to `Documents/CVMAnalytics/output/` via new narrow bridge methods (`export_company_excel`, `get_output_dir`). Collision-safe naming, status surface in UI. Default remains Next. |
| Phase 3F | Single-company refresh controls | Released as v0.10.0 | Vite company detail can start a company-specific refresh, poll existing backend status/freshness fields, and refresh company data after terminal status. No new Python bridge method or schema change. Default remains Next. |
| Phase 3 | Mandatory legacy deletion | Not started | Delete Next/FastAPI legacy only after parity, a default-Vite soak release, and explicit user approval. |
| Phase 4 | Polish/performance | Not started | Startup, logging, AV/code-signing review |

See [PHASE_0_RELEASE_CHECKPOINT.md](PHASE_0_RELEASE_CHECKPOINT.md) for the v0.3.0 release record, validation list, and known hygiene issues.

## Current production status

The authoritative runtime remains the packaged Windows desktop executable.

Default startup still uses the legacy Next.js standalone server and bundled Node runtime. The Vite path is explicit and experimental:

```powershell
.\CVMAnalytics.exe          # default Next/Node UI
.\CVMAnalytics.exe --vite   # experimental Vite SPA, no Node process expected
```

## Critical constraints

- Preserve user DB.
- Preserve Python data pipeline behavior.
- Preserve Windows desktop packaging.
- Do not delete legacy runtime before parity.
- Do not keep obsolete legacy code after parity.

## Phase 3 parity source

Use [PHASE_3_PARITY_MATRIX.md](PHASE_3_PARITY_MATRIX.md) as the active
screen-by-screen parity source. It records what is already implemented in Vite,
what remains before Vite can become default, and what must remain true before
legacy deletion can even be considered.

## Release validation rule

For Phase 2 and later runtime changes, local `dist/` validation is not enough. Validate the exact GitHub Release ZIP a user would download:

- SHA-256 sidecar matches.
- ZIP root is flat: `CVMAnalytics.exe` plus `_internal/`.
- Default mode still launches the Next/Node UI.
- `--vite` mode launches the Vite UI without starting `node.exe`.
- Updater staging and helper swap preserve `%LOCALAPPDATA%\CVMAnalytics` user data.
