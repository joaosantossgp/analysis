# Next Agent Handoff — Desktop Runtime Migration

## Current state

Phase 0 has been implemented.

Do not start Phase 1 until Phase 0 packaged smoke tests are run.

## What was changed

- Runtime user data relocated to `%LOCALAPPDATA%\CVMAnalytics\` (db, output, logs, cache, backup, update_rollback, versions, recovery.log). Implemented in `desktop/app.py`.
- WAL-safe legacy DB migration via `sqlite3.Connection.backup()` on a read-only URI handle. Implemented in `desktop/app.py::_migrate_legacy_db_once` + `_wal_safe_copy_sqlite`.
- Fresh-install DB initialization via `_ensure_db_initialized` calling `src.database.init_db_tables`.
- Update helper rewritten with a strict two-entry allowlist (`CVMAnalytics.exe`, `_internal`) and a hard-deny list of user-data dir names. Pre-swap rollback snapshot under `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\`. Implemented in `desktop/update_helper.ps1`.
- `desktop/build_desktop.ps1` no longer copies the dev DB into `dist/CVMAnalytics/data/db/`.

## What was intentionally not changed

- Next.js still exists in `apps/web/`.
- FastAPI still exists in `apps/api/`.
- Node is still bundled (`desktop/node_portable/node.exe`).
- `desktop/app.spec` is unchanged.
- Vite app has not been created.
- No UI migration has started.
- No legacy deletion has happened.
- `desktop/updater.py` is unchanged; its zip layout still matches the helper allowlist (root-level `CVMAnalytics.exe` plus `_internal/`).
- `src/**` is unchanged.

## Immediate next task

Run Phase 0 packaged smoke tests as documented in `PHASE_0_USER_DATA_SAFETY.md` under "Required before release":

1. Build the desktop package.
2. Launch the packaged exe on a clean account (or after deleting `%LOCALAPPDATA%\CVMAnalytics`).
3. Confirm `%LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db` is created/used.
4. Confirm an existing install-dir DB migrates safely.
5. Confirm an existing LOCALAPPDATA DB is preserved on re-launch.
6. Confirm the real release ZIP layout matches `update_helper.ps1` allowlist.
7. Confirm the updater preserves user data end-to-end.
8. Confirm WebView2 launch is unaffected.

If smoke fails, fix in a follow-up patch on the same branch before touching Phase 1.

## Do not do yet

- Do not create the Vite app before Phase 0 packaged smoke passes.
- Do not delete `apps/web/`.
- Do not delete `apps/api/`.
- Do not delete `desktop/node_portable/`.
- Do not remove Node bundling from `desktop/app.spec`.
- Do not change the app UI.
- Do not start broad cleanup of HTTP routes, FastAPI, or Next-only features.

## Phase 1 preview

After Phase 0 smoke passes, create `apps/desktop-web/` as a parallel Vite SPA shell.

The first Vite prototype should prove:

- pywebview can load static Vite assets (recommend pywebview built-in `http_server=True` over `file://` to avoid WebView2 file-scheme quirks).
- The frontend can call the Python bridge via `window.pywebview.api`, gated on a `pywebviewready` event listener before `createRoot`.
- One real local data method works end-to-end (suggest `get_companies` with a 1-row page — minimal and exercises the DB).
- No production Next server is required for the prototype.

Keep `apps/web/` building in parallel until Phase 2 ships.

## Key risks

- User DB loss (mitigated by Phase 0; verify with smoke tests before any Phase 1 work).
- Updater deleting user data (mitigated by allowlist; verify against real release ZIP).
- PyInstaller bundle layout mismatch with helper allowlist (verify after any `desktop/app.spec` edit).
- WebView2 launch issues on user machines (WebView2 evergreen runtime assumed installed; consider bootstrap check in Phase 4).
- Accidental early deletion of Next/FastAPI (Phase 3 only, after parity).
- Bridge readiness timing in the Vite SPA (`window.pywebview.api` injected after DOMContentLoaded; bootstrap must wait).
- `os.environ.setdefault` semantics: env vars set by `_configure_bundled_data_paths` are not overridden if the user has set them externally. This is intentional for testing but means a stale env var on a user machine could bypass LOCALAPPDATA paths. Document if becomes an issue.

## Key references

- Architecture audit: this file's parent migration documents and the conversation that produced them.
- DB path resolution: `src/settings.py::build_settings`.
- Bridge API surface: `desktop/bridge.py::CVMBridge`.
- Bridge JS client: `apps/web/lib/desktop-bridge.ts`.
- HTTP/bridge dispatch chokepoint: `apps/web/lib/api.ts` (gate on `isDesktopMode()` / `isDesktopServerMode()`).
- Updater payload contract: `desktop/updater.py::download_and_stage` (extracts a release zip into `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, then invokes `update_helper.ps1 <staged> <current>`).
