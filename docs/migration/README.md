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
| Phase 0 | User-data safety net | Released as v0.3.3 (hotfix #3); awaiting real user-machine confirmation | v0.3.3 strips Mark-of-the-Web from bundle DLLs at startup — root cause of the v0.3.0/v0.3.1/v0.3.2 startup crashes |
| Phase 1 | Parallel Vite SPA shell | Not started | Do not delete Next yet |
| Phase 2 | Wire Vite SPA into pywebview | Not started | Remove production Node only after prototype works |
| Phase 3 | Mandatory legacy deletion | Not started | Delete Next/FastAPI legacy only after parity |
| Phase 4 | Polish/performance | Not started | Startup, logging, AV/code-signing review |

See [PHASE_0_RELEASE_CHECKPOINT.md](PHASE_0_RELEASE_CHECKPOINT.md) for the v0.3.0 release record, validation list, and known hygiene issues.

## Current production status

The authoritative runtime remains the packaged Windows desktop executable.

## Critical constraints

- Preserve user DB.
- Preserve Python data pipeline behavior.
- Preserve Windows desktop packaging.
- Do not delete legacy runtime before parity.
- Do not keep obsolete legacy code after parity.
