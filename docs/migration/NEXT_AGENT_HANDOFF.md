# Next Agent Handoff — Desktop Runtime Migration

This is the **primary entry point** for any AI agent or human contributor picking up the migration. Read this first.

---

## TL;DR

- **What we are doing:** rebuilding the desktop app's UI runtime from `Next.js standalone + bundled Node + pywebview` to `static Vite SPA + pywebview` while keeping Python authoritative and user data safe.
- **Where we are:** Phase 2 done. Both the Next standalone runtime and the new Vite SPA ship in the same packaged exe. The Next path is the default; pass `--vite` to opt into the Vite SPA.
- **What is released:** `v0.3.4` on GitHub. Pre-Phase-2. Stable. Users hit the Next path.
- **What is NOT released yet:** Phase 2 (the `--vite` flag) is on `main` but no release tag has been validated from a downloaded GitHub asset yet. The released `v0.3.4` does not have the `--vite` mode.
- **What is next:** screen-parity in Vite (sectors / update-base / Excel save flow) before Phase 3 (legacy deletion).
- **Hard rule:** do not delete `apps/web/`, `apps/api/`, `desktop/node_portable/`, FastAPI deps, or remove Node from `desktop/app.spec` until the user explicitly approves Phase 3.

---

## Phase history

| Phase | Goal | Status | Tag / commits |
|---|---|---|---|
| **Phase 0** | User-data safety net + safe updater + release pipeline | **Released** as `v0.3.4` after 4 hotfixes (`v0.3.0`..`v0.3.4`). | See `PHASE_0_RELEASE_CHECKPOINT.md` |
| **Phase 1** | Parallel Vite + React + TS SPA shell (`apps/desktop-web/`) | Done. Health screen + bridge adapter. Not packaged. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 1.5** | Companies directory screen + TanStack Query | Done. Real search + pagination. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 1.6** | Dynamic routing + company detail | Done. HashRouter + 3 routes + KPI table. | See `PHASE_1_VITE_SHELL.md` |
| **Phase 2** | Opt-in `--vite` runtime in packaged exe | **Done, not yet released.** Both UIs ship; default = Next; `--vite` = Vite with zero Node. | See `PHASE_2_VITE_RUNTIME.md` |
| **Phase 3** | Delete legacy: Next, Node, FastAPI, apps/web, apps/api | **Not started.** Gated on Vite screen parity. | See `PHASE_3_PLAN.md` |
| **Phase 4** | Polish, code signing, AV/UPX review | Not started. | — |

---

## Hard constraints (do not violate)

- **Do not delete** `apps/web/`, `apps/api/`, `desktop/node_portable/`, or any `_internal/web_standalone/` reference.
- **Do not remove** Node from `desktop/app.spec` data entries.
- **Do not remove** FastAPI dependencies from `requirements.txt`.
- **Do not modify** `desktop/bridge.py` method signatures (the Vite SPA mirrors them in `apps/desktop-web/src/lib/bridge/types.ts`).
- **Do not modify** `desktop/update_helper.ps1` user-data deny-list (`data`, `output`, `logs`, `cache`, `tmp`, `backup`, `versions`, `update_rollback`).
- **Do not modify** `desktop/app.py::_migrate_legacy_db_once` or `_wal_safe_copy_sqlite` — they protect user DBs.
- **Do not change** the default startup branch in `desktop/app.py::main()` to Vite until the user explicitly approves.
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
│   ├─ default mode (no flag)                              │
│   │   ├─ subprocess: node.exe _internal/web_standalone/  │
│   │   │   server.js (Next.js standalone)                 │
│   │   └─ pywebview window  → http://127.0.0.1:<port>     │
│   │                                                       │
│   ├─ --vite mode                                          │
│   │   ├─ http.server.ThreadingHTTPServer serving         │
│   │   │   _internal/desktop-web/  (Vite SPA dist)        │
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

User data: `%LOCALAPPDATA%\CVMAnalytics\` (db, output, logs, cache, backup, update_rollback, versions, recovery.log, diagnostics-*.log).

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

## Immediate next task (Phase 1.7 / 2.5)

Suggested before Phase 3:

1. **Manual click-through of packaged `--vite` mode** on a real user machine. Verify the company directory → search → company detail → back navigation flow works end-to-end in the packaged exe (already verified liveness + WebView2 children, not interactive clicks).
2. **Port remaining production screens** to `apps/desktop-web/`. The Next app has these the Vite SPA does not:
   - `/setores` (sectors list) — uses `get_sectors`
   - `/setores/[slug]` and `/setores/[slug]/[sub_slug]` — uses `get_sector_detail`, `get_sub_sector_detail`
   - `/atualizar-base` — uses `get_base_health`, `request_refresh`, `cancel_refresh`, `get_refresh_status`, batch refresh APIs
   - Excel save / download — uses `save_company_excel`, `download_company_excel`
   - Auto-updater UI prompt (the floating banner) — uses `check_update`, `apply_update`, `snooze_update`, `get_update_progress`
3. **Tag `v0.4.0` once Phase 2 is stable.** This is a runtime milestone rather than a small patch: the default path remains Next, but the packaged app gains an experimental Vite path with no Node process. The CI workflow will automatically include both UIs in the bundle because both data entries in `desktop/app.spec` are conditional on disk presence. Add a note to the release saying `--vite` is opt-in / experimental.

Do NOT start Phase 3 until at least items 1 and 2 are done.

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
| Did NOT delete `apps/web/` | Production default still uses it. Delete only after Vite reaches parity. |
| Did NOT delete `apps/api/` | Provides HTTP contract for hosted-mode dev. Audit before removing. |
| Did NOT remove Node bundling | Phase 2's `--vite` is opt-in. Default still needs Node. |
| Did NOT switch default to Vite | Vite SPA does not cover all production screens yet. |
| Did NOT add Sentry / crash reporting | User explicitly declined telemetry. |
| Did NOT migrate to Tauri / Electron | User scoped this to pywebview + WebView2. |
| Did NOT change SQLite to DuckDB / Parquet | Out of scope. User confirmed SQLite stays. |
| Did NOT fix `desktop/__version__.py` dirty-tree | Pre-existing build-process artifact. Documented but not touched. |
| Did NOT switch from HashRouter to BrowserRouter | HashRouter works in `file://`, `http://`, and pywebview's `http_server`. Switch only if Phase 3 standardises on http_server. |

---

## Glossary

- **LOCALAPPDATA contract:** runtime user data lives in `%LOCALAPPDATA%\CVMAnalytics\` (db, output, logs, cache, etc.). Set up by `_configure_bundled_data_paths()` in bundled mode. Dev mode uses repo-relative paths.
- **MOTW (Mark-of-the-Web):** Windows zone-of-origin marker. Extraction via Explorer "Extract All" propagates it to inner files; .NET Framework's `loadFromRemoteSources` policy then refuses to load `Python.Runtime.dll`. v0.3.3 strips MOTW from bundled binaries at startup.
- **Bridge adapter:** the Vite SPA's single chokepoint for `window.pywebview.api` calls. Located at `apps/desktop-web/src/lib/bridge/adapter.ts`. Components never touch the global directly.
- **Updater allowlist:** the only two top-level entries the helper may overwrite during an update: `CVMAnalytics.exe` and `_internal/`. All other paths (especially user-data dirs) are denied.
- **Flat root contract:** the release zip must have `CVMAnalytics.exe` and `_internal/` at the archive root, NOT inside a `CVMAnalytics/` wrapper. v0.3.4 fixed CI to enforce this.
- **Preflight:** `_preflight_pywebview_backend()` in `desktop/app.py`. Checks `.NET Framework 4.8+`, `WebView2 Runtime`, and `Python.Runtime.deps.json` before `import clr`. Shows precise MessageBox + `--diagnose-runtime` pointer if any prereq is missing.
- **Diagnostic mode:** `CVMAnalytics.exe --diagnose-runtime` writes `%LOCALAPPDATA%\CVMAnalytics\diagnostics-<utc>.log` and opens it in Notepad. Use for user bug reports.
