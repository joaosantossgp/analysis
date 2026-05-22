# Next Agent Handoff — Desktop Runtime Migration

This is the **primary entry point** for any AI agent or human contributor picking up the migration. Read this first.

> [!IMPORTANT]
> Before implementing or reviewing any Vite UI screen in `apps/desktop-web`, read and follow: [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](file:///c:/Users/jadaojoao/Documents/Projetos/analisys/docs/skills/CVMANALYTICS_VITE_UI_SKILL.md).

---

## TL;DR

- **What we are doing:** rebuilding the desktop app's UI runtime from `Next.js standalone + bundled Node + pywebview` to `static Vite SPA + pywebview` while keeping Python authoritative and user data safe.
- **Where we are:** Phase 4 shipped as `v0.14.0`, with a hotfix `v0.14.1` that adds a startup GICS backfill. The default UI is the Vite SPA; `CVMAnalytics.exe --legacy` keeps the previous Next/Node UI reachable from the same bundle. `v0.13.0` (Phase 3I) was the last release where Next was the default. Phase 3J was an audit-only readiness pass between 3I and 4.
- **What is released:** `v0.14.1` on GitHub is the current target. Default startup loads Vite with no `node.exe` process; `--legacy` spawns the bundled `node.exe` and the Next standalone server; `--vite` is preserved as an alias of the default. The bundle now also ships `_internal/data/import/gics_mapping.csv` and runs an idempotent startup backfill that fills `companies.gics_sector / gics_sector_slug / gics_sub_industry` for rows seeded before GICS columns were populated. No legacy code was deleted; the bundle still ships `web_standalone/`, `node.exe`, FastAPI deps, and `apps/web/`. The updater allowlist, MOTW strip, preflight, persistent-data root, and flat-root ZIP contract are all unchanged from `v0.13.0`.
- **What is next:** soak `v0.14.0` (Vite default) on real machines for 1–2 weeks. Watch for issues unique to default-Vite startup. After a clean soak, propose Phase 5 (mandatory legacy deletion) and wait for explicit user approval before touching `apps/web/`, `apps/api/`, `desktop/node_portable/`, or removing Node/FastAPI from the bundle.
- **Hard rule:** do not delete `apps/web/`, `apps/api/`, `desktop/node_portable/`, FastAPI deps, the `web_standalone` data entry, or the `--legacy` branch in `desktop/app.py` until the user explicitly approves Phase 5.

---

## Phase history

| Phase | Goal | Status | Tag / commits |
|---|---|---|---|
| **Phase 0** | User-data safety net + safe updater + release pipeline | **Released** as `v0.3.4` after 4 hotfixes (`v0.3.0`..`v0.3.4`). | See `PHASE_0_RELEASE_CHECKPOINT.md` |
| **Phase 1** | Parallel Vite + React + TS SPA shell (`apps/desktop-web/`) | Done. Health screen + bridge adapter. Not packaged. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 1.5** | Companies directory screen + TanStack Query | Done. Real search + pagination. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 1.6** | Dynamic routing + company detail | Done. HashRouter + 3 routes + KPI table. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 2** | Opt-in `--vite` runtime in packaged exe | **Released as `v0.4.0`.** Both UIs ship; default = Next; `--vite` = Vite with zero Node. | See `PHASE_2_VITE_RUNTIME.md` |
| **Phase 3A** | Parity matrix + one missing Vite screen | **Released as `v0.5.0`.** Financial statements are implemented in Vite. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3B** | Update Base / Refresh Data Vite parity slice | **Accepted (v0.6.1).** Real DB diagnostics, row-count panel, post-job delta warning, app-updater vs data-updater wording. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3C.0** | Persistent Documents data root + WAL-safe LocalAppData migration | **Released as `v0.7.0`.** Default runtime data root is `%USERPROFILE%\Documents\CVMAnalytics`. Migration sources: LocalAppData first, then install-dir. `CVMANALYTICS_DATA_DIR` env var overrides. Originals never deleted. | See `PHASE_3_PLAN.md` |
| **Phase 3C.1** | Indicators (KPIs) Vite parity slice | **Released as `v0.7.0`.** New route `/empresas/:cdCvm/indicadores` with year multi-select, KPI summary cards, annual + quarterly tables, unit-aware formatting. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3D** | Sectors + company directory filters | **Released as `v0.8.0`.** Companies directory gains sector filter, URL-driven search/sector/page persistence, chips with per-filter clear, reset action, dense table columns (CVM / ticker / sub-industry / years / rows / coverage dot). New routes `/setores` (GICS sectors and sub-industries) and `/setores/:slug` (sector detail with year selector and in-sector company filter). | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3E** | Excel export from Vite | **Released as `v0.9.0`.** Reusable `ExportCompanyButton` wired into `/empresas/:cdCvm`, `/empresas/:cdCvm/demonstrativos`, and `/empresas/:cdCvm/indicadores`. Calls new bridge `export_company_excel`, writes the existing `build_company_excel_export` workbook into `Documents/CVMAnalytics/output/`. Idle/running/success/error/unsupported states surface destination path, file name, file size; collision-safe `(N)` suffix. `get_output_dir` exposes the destination path before any export runs. Legacy `save_company_excel` (writes to `~/Downloads`) untouched so Next continues to behave identically. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3F** | Single-company refresh controls | **Released as `v0.10.0`.** Vite company detail now has `CompanyRefreshPanel`, using `request_refresh({cd_cvm})` and `get_refresh_status({cd_cvm})` through a typed facade. Surfaces real backend status/freshness/progress fields, polls active statuses every 2s, and invalidates company info/year/KPI/statement/directory queries after terminal status. No Python bridge method, schema, updater, migration, or pipeline changes. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3G** | App status / updater / diagnostics UI | **Released as `v0.11.0`.** New Vite `/status` route adds a compact diagnostics dashboard: app version, runtime mode, bridge state, packaged flag, local data/db/output/log/cache paths, SQLite row counts, latest report year, GitHub latest-release check, compact recovery/update/refresh log rows, and runtime probes for .NET/WebView2/pythonnet/SQLite. Adds narrow bridge methods `get_app_status` and `open_status_path`; existing updater apply/staging methods are unchanged and not exposed as a Vite install action. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3H** | Navigation Polish + KPI Chart Panels + Sub-sector Detail | **Released as `v0.12.0`.** Added breadcrumbs, page headers, unified EntityHeader. Lightweight custom SVG trend charts with null-gap handling. New GICS sub-sector detail route `/setores/:sectorSlug/:subSectorSlug` backed by bridge `get_sub_sector_detail`. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3I** | Excel statement export scope + software updater prompt/apply/restart UI | **Released as `v0.13.0`.** Added statement-scoped exports (DRE/BPA/BPP/DFC) to Documents output folder. Software updater prompt, progress bar, extraction staging, and out-of-process helper execution. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 3J** | Default switch readiness audit | Done. Audit-only phase. No code changes. Confirmed all P0 parity closed and identified the runtime + docs changes required for Phase 4. | See `PHASE_3_PARITY_MATRIX.md` |
| **Phase 4** | Vite default + Next/Node fallback (`--legacy`) | **Released as `v0.14.0`.** Default startup loads the Vite SPA with no Node process. `--legacy` spawns the bundled `node.exe` and the Next standalone server. `--vite` kept as an explicit alias of the default. No legacy code deleted; updater allowlist and user-data contract unchanged. | See `PHASE_3_PLAN.md` |
| **Phase 5** | Delete legacy: Next, Node, FastAPI, apps/web, apps/api | **Not started.** Gated on a clean soak of `v0.14.0` and explicit user approval. Was previously called "Phase 3". | See `PHASE_3_PLAN.md` |
| **Phase 6** | Polish, code signing, AV/UPX review | Not started. Was previously called "Phase 4". | — |

---

## Hard constraints (do not violate)

- **Do not delete** `apps/web/`, `apps/api/`, `desktop/node_portable/`, or any `_internal/web_standalone/` reference.
- **Do not remove** Node from `desktop/app.spec` data entries.
- **Do not remove** FastAPI dependencies from `requirements.txt`.
- **Do not remove** the `--legacy` branch in `desktop/app.py::main()` — it is the user's only fallback to the previous Next/Node UI.
- **Do not modify** `desktop/bridge.py` method signatures (the Vite SPA mirrors them in `apps/desktop-web/src/lib/bridge/types.ts`).
- **Do not modify** `desktop/update_helper.ps1` user-data deny-list (`data`, `output`, `logs`, `cache`, `tmp`, `backup`, `versions`, `update_rollback`).
- **Do not modify** `desktop/app.py::_migrate_legacy_db_once` or `_wal_safe_copy_sqlite` — they protect user DBs.
- **Do not change** the default branch in `desktop/app.py::main()` away from Vite. The Vite default was approved and shipped in `v0.14.0`; reverting it requires explicit user approval.
- **Do not** introduce telemetry, Sentry, or external crash reporting in the desktop runtime.
- **Do not** rewrite git history.
- **Do not** force-push.

---

## Current architecture (high level)

```
┌─────────────────────────────────────────────────────────┐
│              CVMAnalytics.exe (frozen Python)           │
│                                                          │
│  desktop/app.py main()                                   │
│   ├─ default / --vite mode  (Phase 4 default)             │
│   │   ├─ http.server.ThreadingHTTPServer serving         │
│   │   │   _internal/desktop-web/  (Vite SPA dist)        │
│   │   └─ pywebview window  → http://127.0.0.1:<port>     │
│   │                                                       │
│   ├─ --legacy mode  (Next/Node fallback)                  │
│   │   ├─ subprocess: node.exe _internal/web_standalone/  │
│   │   │   server.js (Next.js standalone)                 │
│   │   └─ pywebview window  → http://127.0.0.1:<port>     │
│   │                                                       │
│   ├─ --dev mode → spawn `next dev` from apps/web/         │
│   ├─ --diagnose-runtime → write log + exit                │
│   │                                                       │
│   └─ Common to all modes:                                 │
│       • _configure_bundled_data_paths()                   │
│       • _strip_motw_from_bundle()                         │
│       • _migrate_legacy_db_once()                         │
│       • _ensure_db_initialized()                          │
│       • _preflight_pywebview_backend()                    │
│       • CVMBridge()  ← js_api injected as                 │
│         window.pywebview.api                              │
└─────────────────────────────────────────────────────────┘
```

Runtime user data: `%USERPROFILE%\Documents\CVMAnalytics\` by default (db, output, logs, cache, backup, recovery.log). Updater staging/rollback remains under `%LOCALAPPDATA%\CVMAnalytics\`.

Full architecture map in `ARCHITECTURE.md`.

---

## Critical files reference

| Path | Purpose | Touchable? |
|---|---|---|
| `desktop/app.py` | All runtime modes + safety preflights + LOCALAPPDATA migrator | Yes, carefully |
| `desktop/bridge.py` | `CVMBridge` — Python API exposed as `window.pywebview.api` | Add methods only; never rename existing |
| `desktop/update_helper.ps1` | Allowlist-based updater swap + rollback snapshot | Only updater behavior changes |
| `desktop/updater.py` | GitHub Releases polling + zip download + SHA-256 + staging | Yes |
| `desktop/app.spec` | PyInstaller bundle definition | Yes, but never remove pythonnet/runtime/* |
| `desktop/build_desktop.ps1` | Build orchestrator | Yes |
| `src/settings.py` | Path resolution from env vars (SQLITE_PATH etc.) | Read-only contract; do not change env names |
| `src/database.py` | `init_db_tables` (SQLAlchemy `create_all`) | Read-only contract |
| `apps/web/**` | Legacy Next.js UI — default runtime | DO NOT TOUCH UNTIL PHASE 3 |
| `apps/api/**` | Legacy FastAPI — not used in desktop runtime | DO NOT TOUCH UNTIL PHASE 3 |
| `apps/desktop-web/**` | Vite SPA (new) | Yes, primary work area |
| `.github/workflows/release-desktop.yml` | CI: builds + publishes Windows bundle on tag push | Yes |
| `scripts/phase1_pywebview_smoke.py` | Dev runner with `--manual` / `--timeout` | Yes |
| `scripts/test_motw_*.ps1` | MOTW reproduction harnesses | Yes |
| `scripts/test_ci_v034_full.ps1` | Full Phase 0 contract validation against published asset | Yes |

---

## Immediate next task

`v0.14.0` shipped the Vite default + `--legacy` fallback. The next item is the soak window before any deletion work.

1. Monitor real-world `v0.14.0` use for 1–2 weeks. Watch for failure modes that only appear when Vite is the default startup: loopback HTTP server bind failures, WebView2 cold-start regressions, AV/SmartScreen reaction to the changed launch path, missing `--legacy` discoverability for users who hit Vite-only bugs.
2. Keep `PHASE_3_PARITY_MATRIX.md` current. If a real-world bug surfaces, record it there and fix on the Vite side rather than re-defaulting to Next.
3. Keep `/status` focused on diagnostics; do not turn it into a broad settings system unless the user asks.
4. After a clean soak, propose Phase 5 (legacy deletion) and wait for explicit user approval before touching `apps/web/`, `apps/api/`, `desktop/node_portable/`, FastAPI dependencies, or the `--legacy` branch in `desktop/app.py`.

Do NOT start Phase 5 deletion until `v0.14.0` has soaked cleanly and the user explicitly approves deletion.

---

## How to verify everything

See `SMOKE_RECIPES.md` for the full list of smoke commands. Quick start:

```bash
# Phase 0 contract (LOCALAPPDATA, MOTW, updater allowlist, fresh-install schema)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/test_ci_v034_full.ps1

# Phase 1.6 interactive (Vite dev + pywebview + real bridge, keep open)
python scripts/phase1_pywebview_smoke.py --manual

# Phase 2 packaged --vite mode (after .\desktop\build_desktop.ps1)
.\dist\CVMAnalytics\CVMAnalytics.exe --vite
```

---

## How to ship a release

After tagging `vX.Y.Z` and pushing:

1. CI workflow `release-desktop.yml` builds Windows bundle on `windows-latest`.
2. Bundles run `desktop/build_desktop.ps1 -Version X.Y.Z` (which builds Next + Vite + PyInstaller).
3. CI archives the bundle with **flat root** layout (`CVMAnalytics.exe` + `_internal/` at top), verified by the post-archive step in the workflow.
4. CI publishes the zip + `.sha256` to the GitHub Release.
5. The auto-updater in users' running apps will pick up the new release on next launch and download it via SHA-256-verified flow.
6. `update_helper.ps1` allowlist swaps `CVMAnalytics.exe` + `_internal/` only; never touches `data/`, `output/`, `logs/`, `cache/`.

If the bundle layout drifts (e.g. CVMAnalytics/ wrapper instead of flat root), the workflow `Compress-Archive` step will fail and the release will not be published. See `PHASE_0_RELEASE_CHECKPOINT.md` for the v0.3.4 hotfix that locked this in.

Phase 2 is not considered release-validated until the published GitHub ZIP and SHA-256 sidecar are downloaded, the flat root is inspected, both launch modes are tested from the extracted asset, and the updater sandbox confirms user-data preservation.

---

## What was intentionally NOT done (and why)

| Decision | Reason |
|---|---|
| Did NOT delete `apps/web/` | Still the source for the `--legacy` Next standalone bundle. Delete only after Phase 5. |
| Did NOT delete `apps/api/` | Provides HTTP contract for hosted-mode dev and the legacy bundle. Audit before removing. |
| Did NOT remove Node bundling | `--legacy` still requires the bundled `node.exe`. Node removal is Phase 5. |
| DID switch default to Vite in `v0.14.0` | All P0 parity gaps closed at `v0.13.0`. `--legacy` keeps Next as a fallback. |
| Did NOT add Sentry / crash reporting | User explicitly declined telemetry. |
| Did NOT migrate to Tauri / Electron | User scoped this to pywebview + WebView2. |
| Did NOT change SQLite to DuckDB / Parquet | Out of scope. User confirmed SQLite stays. |
| Did NOT switch from HashRouter to BrowserRouter | HashRouter works in `file://`, `http://`, and pywebview's `http_server`. Switch only if Phase 3 standardises on http_server. |

---

## Glossary

- **Runtime data contract:** runtime user data lives in `%USERPROFILE%\Documents\CVMAnalytics\` by default (db, output, logs, cache, backup, etc.). `CVMANALYTICS_DATA_DIR` can override it. Updater staging and rollback remain under `%LOCALAPPDATA%\CVMAnalytics\`.
- **MOTW (Mark-of-the-Web):** Windows zone-of-origin marker. Extraction via Explorer "Extract All" propagates it to inner files; .NET Framework's `loadFromRemoteSources` policy then refuses to load `Python.Runtime.dll`. v0.3.3 strips MOTW from bundled binaries at startup.
- **Bridge adapter:** the Vite SPA's single chokepoint for `window.pywebview.api` calls. Located at `apps/desktop-web/src/lib/bridge/adapter.ts`. Components never touch the global directly.
- **Updater allowlist:** the only two top-level entries the helper may overwrite during an update: `CVMAnalytics.exe` and `_internal/`. All other paths (especially user-data dirs) are denied.
- **Flat root contract:** the release zip must have `CVMAnalytics.exe` and `_internal/` at the archive root, NOT inside a `CVMAnalytics/` wrapper. v0.3.4 fixed CI to enforce this.
- **Preflight:** `_preflight_pywebview_backend()` in `desktop/app.py`. Checks `.NET Framework 4.8+`, `WebView2 Runtime`, and `Python.Runtime.deps.json` before `import clr`. Shows precise MessageBox + `--diagnose-runtime` pointer if any prereq is missing.
- **Diagnostic mode:** `CVMAnalytics.exe --diagnose-runtime` writes `%LOCALAPPDATA%\CVMAnalytics\diagnostics-<utc>.log` and opens it in Notepad. Use for user bug reports.
