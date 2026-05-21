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
│    • Next.js standalone server     – UI on 127.0.0.1:<random>  │
│    • Bundled node.exe              – runs the standalone       │
│                                                                │
│  User-writable data lives outside the install dir:             │
│    %LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db            │
└────────────────────────────────────────────────────────────────┘
```

- **Python (`src/`)** owns the data pipeline, SQLite access, KPI engine, refresh worker, and Excel export.
- **pywebview** hosts WebView2 and exposes Python callables to JavaScript as `window.pywebview.api`.
- **Next.js 16** under `apps/web/` builds to a standalone server that runs locally and renders the UI.
- **FastAPI (`apps/api/`)** is the HTTP contract for an optional dev workflow. It is not started in the packaged desktop runtime.

A migration to a static Vite + React frontend and removal of the bundled Node runtime is planned. See `docs/migration/`.

## Runtime Model

- Local-first. Authoritative runtime is the Windows desktop app.
- The desktop app launches Python, which spawns the Next.js standalone server, which serves the UI to WebView2 inside the pywebview window.
- All data calls in desktop mode go through `window.pywebview.api` directly to Python — no HTTP roundtrip.

## User Data Location

```
%LOCALAPPDATA%\CVMAnalytics\
  db\
    cvm_financials.db            ← active runtime database
  output\                        ← Excel exports
  logs\                          ← refresh / app logs
  cache\
  backup\                        ← legacy DB snapshots on first migration
  update_rollback\               ← pre-update snapshots of swapped bundle files
  versions\                      ← staged update bundles
  recovery.log
```

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

Dev-mode database lives at `data/db/cvm_financials.db` (repo-relative). The LOCALAPPDATA contract only applies to the packaged executable.

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
| Phase 1 | Parallel Vite SPA shell | Not started |
| Phase 2 | Wire Vite SPA into pywebview, remove Node | Not started |
| Phase 3 | Delete legacy Next/FastAPI/Node | Not started |
| Phase 4 | Polish, code signing, AV review | Not started |

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

- Phase 1: parallel Vite + React + TanStack Router SPA under `apps/desktop-web/`, in addition to the current Next.js UI.
- Phase 2: wire the SPA into pywebview, remove the bundled `node.exe` and `_internal/web_standalone/`.
- Phase 3: delete `apps/api/` and the legacy `apps/web/` once the Vite UI reaches parity.
- Phase 4: code signing, AV/UPX review, startup logging improvements.

## Known Limitations

- Windows-only. macOS and Linux are not supported targets.
- Requires Microsoft Edge WebView2 runtime (preinstalled on Windows 11; usually present on recent Windows 10).
- First boot of the packaged app spawns a Node.js child process for the embedded Next standalone server. Node is bundled but will be removed in Phase 2.
- The dev database under `data/db/cvm_financials.db` is for developer use only. End users do not need it; the packaged app provisions its own DB under `%LOCALAPPDATA%`.
- No telemetry. No crash reporting service is wired into the local desktop app.

## License

See repository LICENSE file if present. Otherwise treat as all-rights-reserved by the author.
