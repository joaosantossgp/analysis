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
│    • Vite static SPA               – only packaged UI runtime  │
│                                                                │
│  User-writable data lives outside the install dir:             │
│    %USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db   │
└────────────────────────────────────────────────────────────────┘
```

- **Python (`src/`)** owns the data pipeline, SQLite access, KPI engine, refresh worker, and Excel export.
- **pywebview** hosts WebView2 and exposes Python callables to JavaScript as `window.pywebview.api`.
- **Vite + React + TypeScript** under `apps/desktop-web/` builds to a static SPA served from a local loopback HTTP server. This is the only packaged desktop UI runtime.
- **Next.js 16** under `apps/web/` remains in source as a source-only legacy / hosted web app. It is not packaged into the desktop app.
- **FastAPI (`apps/api/`)** remains in source for the hosted Railway API and API tests. It is not started or packaged by the desktop runtime.

The Phase 3 sequence ported every P0 production screen into Vite (statements, KPIs, sectors, Excel export, refresh, status/updater). Phase 4 (`v0.14.0`) made Vite the default. Phase 5B (`v0.15.0`) removed the desktop-packaged Next/Node runtime. Phase 5C kept source-only/hosted surfaces. Phase 6 (`v0.17.0`) completed the final product hardening audit, standardized KPI/monospaced styling, and finalized the stable release pass. See `docs/migration/`.

## Runtime Model

- Local-first. Authoritative runtime is the Windows desktop app.
- Default runtime: the desktop app launches Python, serves the Vite SPA over a loopback HTTP server, and loads it inside the pywebview window. No `node.exe` process is spawned.
- `--legacy` is no longer supported in the packaged app. It shows a short warning and continues into the Vite UI.
- All desktop data calls go through `window.pywebview.api` directly to Python — no HTTP roundtrip to a separate backend.

### Launch Modes

```
CVMAnalytics.exe              Vite default (no Node process)
CVMAnalytics.exe --vite       alias of default Vite mode
CVMAnalytics.exe --legacy     unsupported; warns, then continues into Vite
CVMAnalytics.exe --dev        packaged build ignores dev flag; source mode uses Vite dev server
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

# Vite desktop UI deps (only needed when running/building the dev UI)
cd apps/desktop-web && npm install && cd ../..

# Initialize the dev DB (repo-relative path used in dev mode)
python scripts/setup_db.py
python scripts/setup_companies_table.py

# Validate environment
python scripts/runtime_doctor.py --require-canonical

# Run the desktop app in dev mode against the Vite dev server
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

# Vite UI dev server only
cd apps/desktop-web && npm run dev
```

## Desktop Build

```powershell
# From the repo root
.\desktop\build_desktop.ps1

# Or, after a successful prior Vite build:
.\desktop\build_desktop.ps1 -SkipViteBuild

# Result
.\dist\CVMAnalytics\CVMAnalytics.exe
```

The build script:

1. Runs the Vite build in `apps/desktop-web/`.
2. Injects the version into `desktop/__version__.py`.
3. Runs `pyinstaller desktop/app.spec` to produce `dist/CVMAnalytics/`.

The packaged folder contains only `CVMAnalytics.exe` and `_internal/`. No user data and no dev database are bundled.

## Update Flow

- The app polls GitHub Releases on startup.
- A newer tag triggers an in-app prompt.
- The updater downloads `CVMAnalytics-windows-v<version>.zip` (and its `.sha256`) into `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, validates the checksum, and extracts.
- `desktop/update_helper.ps1` swaps only allowlisted entries (`CVMAnalytics.exe` and `_internal\`) over the current install. A pre-swap snapshot is written to `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\`.
- The helper never touches `data\`, `output\`, `logs\`, `cache\`, or any `*.db` / `*.db-wal` / `*.db-shm` under the install directory.

## Migration Status

The desktop runtime migration is complete as of v0.17.0. All phases are released. The table below is kept as historical reference.

| Phase | Goal | Status |
|---|---|---|
| Phase 0 | User-data safety net | **Released** |
| Phase 1 | Parallel Vite SPA shell | Done |
| Phase 2 | Wire Vite SPA into pywebview | **Released as opt-in `--vite` (`v0.4.0`)** |
| Phase 3A–3I | Incremental Vite parity slices | **Released through `v0.13.0`**: statements, Update Base, Documents data root, KPIs, KPI charts, sectors, sub-sector detail, Excel export (full + per-statement), single-company refresh, status/diagnostics, software updater UI |
| Phase 3J | Default switch readiness audit | Done |
| Phase 4 | Vite default + Next/Node fallback (`--legacy`) | **Released as `v0.14.0`, hotfix `v0.14.1`.** Default startup loads the Vite SPA with no Node process. |
| Phase 5A | Legacy deletion audit | Done. Found `apps/web/` and `apps/api/` are source-only / hosted products, not desktop package dependencies. |
| Phase 5B | Remove desktop-packaged Next/Node runtime | **Released as `v0.15.0`.** The desktop package no longer ships `node.exe`, `web_standalone/`, or the Next standalone runtime. |
| Phase 5C | Source-only / hosted-surface cleanup decision | Done. Kept `apps/web/`, `apps/api/`, and `railway.toml` documented as non-packaged surfaces; removed default CI blockers for legacy Next/perf jobs. |
| Phase 6 | Stable Release / Final Product Pass | **Released (v0.17.0)** |

See:

- [docs/migration/README.md](docs/migration/README.md) — phase tracker
- [docs/migration/PHASE_0_USER_DATA_SAFETY.md](docs/migration/PHASE_0_USER_DATA_SAFETY.md) — Phase 0 spec and validation
- [docs/migration/NEXT_AGENT_HANDOFF.md](docs/migration/NEXT_AGENT_HANDOFF.md) — detailed phase history (historical; migration complete as of v0.17.0)

## Repository Structure

```
desktop/          pywebview shell, PyInstaller spec, updater, build script
apps/desktop-web/ Vite static SPA packaged into the .exe  ← only packaged UI
apps/web/         Source-only hosted Next.js 16 UI, not packaged
apps/api/         Hosted Railway FastAPI + API tests, not packaged
src/              Python core: scraper, KPI engine, refresh/read services
main.py           CLI entry point for headless refresh
scripts/          Setup, batches, diagnostics, validation helpers
landing/          Marketing landing page
data/             Dev-mode SQLite DB + raw inputs (gitignored)
docs/             Active documentation, migration docs, ADRs
tests/            pytest suite
config/           canonical_accounts.csv — CVM account mapping (referenced by src/)
```

See [docs/reference/repository-map.md](docs/reference/repository-map.md) for a full folder, workflow, and documentation status map.

## Contributor Orientation

**"I want to change the desktop UI"** → `apps/desktop-web/src/`. Read `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md` first. Run `python -m desktop.app --dev` to see changes live. Components call Python exclusively through `lib/bridge/adapter.ts` — never call `window.pywebview.api` directly.

**"I want to change data or financial logic"** → `src/`. The Python core owns the pipeline, KPI engine, DB access, refresh worker, and Excel export. Read `docs/CONTEXT.md` before touching financial calculations or column conventions.

**"I want to change packaging or the updater"** → `desktop/`. The PyInstaller spec is `desktop/app.spec`. Build script is `desktop/build_desktop.ps1`. Auto-updater is `desktop/updater.py` + `desktop/update_helper.ps1`. Do not change these without re-running the full release pipeline — a wrong path in the spec produces a broken EXE with no obvious build-time error.

**"I want to change the hosted API or Next.js web surface"** → `apps/api/` (FastAPI, Railway) and `apps/web/` (Next.js 16). These surfaces are not packaged into `CVMAnalytics.exe` and do not affect the desktop runtime. Read `docs/reference/interface-map.md` before modifying any API contract.

**"Which docs are current vs historical?"** → `docs/reference/repository-map.md` for a full map. Short answer: `docs/reference/` and `docs/decisions/` are active. `docs/migration/` is completed history. `docs/reference/sitemap.md` and `docs/reference/interface-map.md` describe the hosted web surface, not the desktop.

**What not to touch casually:**
- `desktop/app.spec` — PyInstaller spec; a wrong entry produces a broken EXE
- `desktop/build_desktop.ps1` — build pipeline; test end-to-end before merging
- `.github/workflows/release-desktop.yml` — changes affect artifacts downloaded by real users
- `src/settings.py` — user data paths; wrong changes break the live DB location
- `config/canonical_accounts.csv` — referenced by `src/settings.py` and 8+ scripts; moving requires coordinated multi-file update

## Roadmap

- `apps/web/` and `apps/api/` remain as documented source-only / hosted surfaces. Deletion requires a separate retirement decision.
- Known deferred items: code signing (SmartScreen warning on download), AV/UPX review.

## Known Limitations

- Windows-only. macOS and Linux are not supported targets.
- Requires Microsoft Edge WebView2 runtime (preinstalled on Windows 11; usually present on recent Windows 10).
- The packaged desktop app is Vite-only and does not spawn a Node.js child process. `CVMAnalytics.exe --legacy` is unsupported and continues into Vite after a warning.
- The dev database under `data/db/cvm_financials.db` is for developer use only. End users do not need it; the packaged app provisions its own DB under `%USERPROFILE%\Documents\CVMAnalytics` (with WAL-safe migration from legacy `%LOCALAPPDATA%` if present).
- No telemetry. No crash reporting service is wired into the local desktop app.

## License

See repository LICENSE file if present. Otherwise treat as all-rights-reserved by the author.
