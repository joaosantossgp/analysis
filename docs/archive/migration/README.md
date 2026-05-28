# Desktop Runtime Migration

> [!IMPORTANT]
> Before implementing or reviewing any Vite UI screen in `apps/desktop-web`, read and follow: [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](../skills/CVMANALYTICS_VITE_UI_SKILL.md).

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
- protected user data under `%USERPROFILE%\Documents\CVMAnalytics`

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
| Phase 3G | App status / updater / diagnostics UI | Released as v0.11.0 | New Vite `/status` screen shows runtime version/mode, bridge status, local data paths, SQLite counts, GitHub release check status, compact logs, and runtime probes. Adds narrow bridge methods `get_app_status` and `open_status_path`; software update application remains intentionally unsupported in Vite. Default remains Next. |
| Phase 3H | Navigation Polish + KPI Chart Panels + Sub-sector Detail | Released as v0.12.0 | Consistent page headers, breadcrumbs, and unified EntityHeader across Vite. Custom SVG trend charts for KPIs (ROE, margins, leverage) with gap-handling. New `/setores/:sectorSlug/:subSectorSlug` route parity for GICS sub-sectors using bridge method `get_sub_sector_detail`. Default remains Next. |
| Phase 3I | Final P0 Parity: Excel statement export scope + software updater prompt/apply/restart UI | Released as v0.13.0 | Statement-scoped Excel exports (DRE/BPA/BPP/DFC) to Documents output folder. Software updater prompt, staging progress bar, confirmation checks, and out-of-process restart helper swap. |
| Phase 3J | Default switch readiness audit | Done | Audit-only phase. Confirmed all P0 parity gaps closed at v0.13.0 and identified the runtime changes required for Phase 4. |
| Phase 4 | Vite default + Next/Node fallback (`--legacy`) | Released as v0.14.0; hotfix v0.14.1 | Default startup loads the Vite SPA with no Node process. `CVMAnalytics.exe --legacy` launches the previous Next/Node UI from the same bundle. `--vite` kept as an explicit alias of the default. No legacy code deleted; updater allowlist, user-data root, MOTW strip, preflight, and ZIP flat-root contract all unchanged. `v0.14.1` adds a one-shot startup GICS backfill from the bundled `data/import/gics_mapping.csv`: fixes the Vite sectors/sector-filter screens for user DBs that had only CVM/B3 labels and no GICS classification. |
| Phase 5A | Legacy deletion audit + plan | Done | Audit-only phase. Output: [PHASE_5_LEGACY_DELETION_AUDIT.md](PHASE_5_LEGACY_DELETION_AUDIT.md). Found that `apps/web/` is also deployed to Vercel and `apps/api/` is the Railway-hosted FastAPI used by data-pipeline CI workflows — both are dual-use products, not pure desktop legacy. Phase 5B narrowed to desktop-bundle cleanup only. |
| Phase 5B | Desktop-side legacy deletion (`--legacy` flag, `web_standalone`, `node.exe`, `desktop/node_portable/`) | Released as v0.15.0 | Removed the packaged Next/Node runtime from the desktop bundle. `apps/web/`, `apps/api/`, `railway.toml`, and `landing/` stay in source and are not packaged. |
| Phase 5C | Source-only / hosted-surface cleanup decision | Done | Output: [PHASE_5C_SOURCE_LEGACY_CLEANUP.md](PHASE_5C_SOURCE_LEGACY_CLEANUP.md). Kept `apps/web/`, `apps/api/`, and `railway.toml` as documented source-only/hosted surfaces; removed default CI blockers for legacy Next/perf jobs. |
| Phase 6 | Stable Release / Final Product Pass | Released as v0.17.0 | Completed product hardening audit, standardized KPI cells display/styling, monospaced tabular fonts, non-blocking diagnostics mode, and final release validation. |

See [PHASE_0_RELEASE_CHECKPOINT.md](PHASE_0_RELEASE_CHECKPOINT.md) for the v0.3.0 release record, validation list, and known hygiene issues.

## Current production status

The authoritative runtime remains the packaged Windows desktop executable.

As of `v0.15.0` the packaged desktop app loads only the Vite SPA and does not spawn `node.exe`. The Next/Node UI is no longer packaged:

```powershell
.\CVMAnalytics.exe              # Vite default (no Node process)
.\CVMAnalytics.exe --vite       # alias of default Vite mode
.\CVMAnalytics.exe --legacy     # unsupported; warns, then continues into Vite
```

Phase 5B removed the desktop-side legacy package path: `desktop/node_portable/`, `_internal/node.exe`, `_internal/web_standalone/`, the Next build step, and the runtime branch that started the Next standalone server. Phase 5C kept `apps/web/` and `apps/api/` as documented source-only / hosted surfaces, outside the default desktop CI and outside the package.

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
- Default mode launches the Vite UI without starting `node.exe`.
- `--vite` mode also launches the Vite UI and does not start `node.exe` (alias).
- `--legacy` mode does not start Next/Node; it warns and continues into Vite.
- Updater staging and helper swap preserve user data. Active runtime data stays
  under `%USERPROFILE%\Documents\CVMAnalytics`; updater staging/rollback stays
  under `%LOCALAPPDATA%\CVMAnalytics`.
