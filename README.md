# CVMAnalytics

## Overview

CVMAnalytics is a local-first Windows desktop application for collecting, organizing, and analyzing Brazilian public company financial data. The app combines a Python data pipeline, a local SQLite database, and a packaged desktop UI through pywebview.

The authoritative runtime is the packaged Windows desktop executable. The Vercel landing page exists as a marketing surface only — it is not the product.

## Who This Is For

- Equity researchers and analysts who follow Brazilian publicly traded companies (CVM-regulated).
- Developers and finance students who want a local, scriptable view of historical financial statements without a cloud account.
- Power users who prefer keeping their data and queries on their own machine.

## Key Features

- Downloads and standardizes historical CVM filings (DFP / ITR) for B3-listed companies.
- Persists everything in a local SQLite database for offline use.
- Desktop UI with company directory, sector views, KPI dashboards, and statement matrices.
- Excel export for any company's financial history.
- Background refresh queue with per-company status, retries, and freshness signals.
- Auto-updater that downloads new releases from GitHub and applies them without overwriting user data.

## Current Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      CVMAnalytics.exe                          │
│                                                                │
│  PyInstaller bundle:                                           │
│    • Python core (src/)            – pipeline, DB, KPIs        │
│    • pywebview window              – WebView2 / Edge Chromium  │
│    • desktop/bridge.py             – window.pywebview.api      │
│    • Vite static SPA               – default UI, no Node       │
│    • Next.js standalone server     – legacy fallback (--legacy)│
│    • Bundled node.exe              – spawned only for --legacy │
│                                                                │
│  User-writable data lives outside the install dir:             │
│    %USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db   │
└────────────────────────────────────────────────────────────────┘
```

- **Python (`src/`)** owns the data pipeline, SQLite access, KPI engine, refresh worker, and Excel export.
- **pywebview** hosts WebView2 and exposes Python callables to JavaScript as `window.pywebview.api`.
- **Vite + React + TypeScript** under `apps/desktop-web/` builds to a static SPA served from a local loopback HTTP server. This is the default UI as of `v0.14.0`.
- **Next.js 16** under `apps/web/` still builds to a standalone server and remains packaged as a legacy fallback reachable through `CVMAnalytics.exe --legacy`. It is not deleted.
- **FastAPI (`apps/api/`)** is the HTTP contract for an optional dev workflow. It is not started in the packaged desktop runtime and remains packaged for the legacy path.

The Phase 3 sequence ported every P0 production screen into Vite (statements, KPIs, sectors, Excel export, refresh, status/updater). Phase 4 (`v0.14.0`) made Vite the default while keeping Next/Node/FastAPI intact behind `--legacy`. Legacy deletion is gated on a soak window plus explicit approval. See `docs/migration/`.

## Runtime Model

- Local-first. Authoritative runtime is the Windows desktop app.
- Default runtime: the desktop app launches Python, serves the Vite SPA over a loopback HTTP server, and loads it inside the pywebview window. No `node.exe` process is spawned.
- Legacy runtime (`--legacy`): the desktop app spawns the bundled `node.exe`, which runs the Next.js standalone server, which serves the legacy UI to WebView2. Behavior is identical to releases up to and including `v0.13.0`.
- All data calls in either mode go through `window.pywebview.api` directly to Python — no HTTP roundtrip to a separate backend.

### Launch Modes

```
CVMAnalytics.exe              Vite default (no Node process)
CVMAnalytics.exe --vite       alias of default Vite mode
CVMAnalytics.exe --legacy     Next/Node fallback (spawns bundled node.exe)
CVMAnalytics.exe --dev        legacy Next.js dev server (developer only)
CVMAnalytics.exe --debug      open DevTools in the active mode
CVMAnalytics.exe --diagnose-runtime   write diagnostics log and exit
```

## User Data Location

Active runtime data root (Phase 3C and later):

```
%USERPROFILE%\Documents\CVMAnalytics\
  db\
    cvm_financials.db            ← active runtime database
  output\                        ← Excel exports
  logs\                          ← refresh / app logs
  cache\
  backup\                        ← legacy DB snapshots from migration
  recovery.log
```

Resolution priority for the active root:

1. `CVMANALYTICS_DATA_DIR` environment variable (operator override).
2. `%USERPROFILE%\Documents\CVMAnalytics` (Phase 3C default).
3. `%LOCALAPPDATA%\CVMAnalytics` (pre-Phase-3C fallback if `USERPROFILE`
   is unset, e.g. service accounts).

Updater-internal staging is kept separately under
`%LOCALAPPDATA%\CVMAnalytics\` (`versions/`, `update_rollback/`). These
paths are deny-listed by the updater allowlist and are unrelated to the
runtime data root above.

Legacy migration: on first launch under v0.7.0+, if the Documents data
root has no database, the app does a WAL-safe `sqlite3 .backup` copy
from the first existing legacy source (LocalAppData, then install-dir).
Legacy originals are never moved or deleted, and Documents DB is never
overwritten if it already exists.

User data is never written under the install directory. The updater can never overwrite these paths.

## Development Setup

```bash
# Python deps
pip install -r requirements.txt
pip install -r apps/api/requirements-dev.txt

# Web deps (only needed when running the dev UI)
cd apps/web && npm install && cd ../..

# Initialize the dev DB (repo-relative path used in dev mode)
python scripts/setup_db.py
python scripts/setup_companies_table.py

# Validate environment
python scripts/runtime_doctor.py --require-canonical

# Run the desktop app in dev mode against the Next dev server
python -m desktop.app --dev
```

Dev-mode database lives at `data/db/cvm_financials.db` (repo-relative). The Documents data-root contract only applies to the packaged executable.

Headless and HTTP alternatives:

```bash
# CLI refresh for a single company
python main.py --companies PETROBRAS --start_year 2021 --end_year 2025

# Optional local FastAPI
uvicorn apps.api.app.main:app --reload
# → Swagger at http://127.0.0.1:8000/docs

# Web dev server only
cd apps/web && npm run dev
```

## Desktop Build

```powershell
# From the repo root
.\desktop\build_desktop.ps1

# Or, after a successful prior next build:
.\desktop\build_desktop.ps1 -SkipNextBuild

# Result
.\dist\CVMAnalytics\CVMAnalytics.exe
```

The build script:

1. Runs `next build` with `output: "standalone"` (skippable with `-SkipNextBuild`).
2. Copies `public/` and `.next/static/` into the standalone tree (Next.js does not do this automatically).
3. Copies the system `node.exe` into `desktop/node_portable/`.
4. Injects the version into `desktop/__version__.py`.
5. Runs `pyinstaller desktop/app.spec` to produce `dist/CVMAnalytics/`.

The packaged folder contains only `CVMAnalytics.exe` and `_internal/`. No user data and no dev database are bundled.

## Update Flow

- The app polls GitHub Releases on startup.
- A newer tag triggers an in-app prompt.
- The updater downloads `CVMAnalytics-windows-v<version>.zip` (and its `.sha256`) into `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, validates the checksum, and extracts.
- `desktop/update_helper.ps1` swaps only allowlisted entries (`CVMAnalytics.exe` and `_internal\`) over the current install. A pre-swap snapshot is written to `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\`.
- The helper never touches `data\`, `output\`, `logs\`, `cache\`, or any `*.db` / `*.db-wal` / `*.db-shm` under the install directory.

## Migration Status

The repository is in the middle of a multi-phase simplification of the desktop runtime.

| Phase | Goal | Status |
|---|---|---|
| Phase 0 | User-data safety net | **Released** |
| Phase 1 | Parallel Vite SPA shell | Done |
| Phase 2 | Wire Vite SPA into pywebview | **Released as opt-in `--vite` (`v0.4.0`)** |
| Phase 3A–3I | Incremental Vite parity slices | **Released through `v0.13.0`**: statements, Update Base, Documents data root, KPIs, KPI charts, sectors, sub-sector detail, Excel export (full + per-statement), single-company refresh, status/diagnostics, software updater UI |
| Phase 3J | Default switch readiness audit | Done |
| Phase 4 | Vite default + Next/Node fallback (`--legacy`) | **Released as `v0.14.0`.** Default startup now loads the Vite SPA with no Node process. Legacy Next/Node UI remains packaged and reachable via `--legacy`. No legacy code deleted. |
| Phase 5 (was "Phase 3") | Delete legacy Next/FastAPI/Node/`apps/web`/`apps/api`/`node_portable` | Not started; gated on a soak window for the `v0.14.0` default flip and explicit user approval |
| Phase 6 | Polish, code signing, AV review | Not started |

See:

- [docs/migration/README.md](docs/migration/README.md) — phase tracker
- [docs/migration/PHASE_0_USER_DATA_SAFETY.md](docs/migration/PHASE_0_USER_DATA_SAFETY.md) — Phase 0 spec and validation
- [docs/migration/NEXT_AGENT_HANDOFF.md](docs/migration/NEXT_AGENT_HANDOFF.md) — handoff for the next contributor

## Repository Structure

```
desktop/         pywebview wrapper, PyInstaller spec, updater, build script
apps/web/        Next.js 16 standalone UI (bundled into the .exe)
apps/api/        Optional FastAPI read-only service for dev/local HTTP
src/             Python core: scraper, KPI engine, refresh/read services
main.py          CLI entry point for headless refresh
scripts/         Setup, batches, diagnostics, validation helpers
landing/         Marketing landing page
data/            Dev-mode SQLite DB + raw inputs (gitignored)
docs/            Active documentation, migration docs, ADRs
tests/           Pytest suite
```

## Roadmap

- Soak `v0.14.0` (Vite default + `--legacy` fallback) on real machines for 1–2 weeks. Collect any failure modes that only appear when Vite is the default startup.
- After a clean soak, propose Phase 5: delete `apps/web/`, `apps/api/`, `desktop/node_portable/`, the `web_standalone` data entry, and the `--legacy` branch — only with explicit user approval.
- Phase 6: code signing, AV/UPX review, startup logging improvements.

## Known Limitations

- Windows-only. macOS and Linux are not supported targets.
- Requires Microsoft Edge WebView2 runtime (preinstalled on Windows 11; usually present on recent Windows 10).
- As of `v0.14.0` the default startup is the Vite SPA and does not spawn a Node.js child process. `CVMAnalytics.exe --legacy` still spawns the bundled `node.exe` for the Next.js standalone fallback. Node removal is deferred until the Vite default soak is complete and legacy deletion is approved.
- The dev database under `data/db/cvm_financials.db` is for developer use only. End users do not need it; the packaged app provisions its own DB under `%USERPROFILE%\Documents\CVMAnalytics` (with WAL-safe migration from legacy `%LOCALAPPDATA%` if present).
- No telemetry. No crash reporting service is wired into the local desktop app.

## License

See repository LICENSE file if present. Otherwise treat as all-rights-reserved by the author.
