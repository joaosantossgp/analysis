# Development

## Prerequisites

- Python 3.11+
- Node.js 22+ for `apps/desktop-web`
- Windows for packaged desktop validation
- WebView2/.NET requirements for pywebview on Windows

## Normal Desktop Development Setup

After installing Python and Node.js, run one command from the repository root:

```powershell
python -m desktop.app --dev
```

On the first run, the launcher creates `.venv` with the Python interpreter that
started it, installs the root `requirements.txt` manifest, validates Node.js
22+, and runs `npm ci` in `apps/desktop-web`. On later runs it compares stored
SHA-256 fingerprints of `requirements.txt` and `package-lock.json`; pip/npm do
not run again unless the corresponding manifest changed.

The environment is isolated at `.venv`; the app does not install runtime
packages into the developer's global Python installation. The root
`requirements.txt` is the canonical desktop/core Python manifest. CI installs
that manifest, `apps/api/requirements-dev.txt`, and uses Node 22.

If provisioning fails, the launcher prints the failed command, exit code, and
output. Resolve the named Python, Node, npm, permission, or network issue, then
run one of these commands:

```powershell
# Reinstall declared Python and frontend dependencies in the existing .venv.
python -m desktop.app --repair-dev-environment --dev

# Delete and recreate only the repository-local .venv, then synchronize again.
python -m desktop.app --rebuild-dev-environment --dev
```

The issue -> branch -> PR workflow, including parallel work, is in `AGENTS.md`
("Workflow").

## Tests, scripts and API setup without opening the UI

The desktop launcher prepares its own environment but does not activate it in
other terminals. Use the project interpreter explicitly for every command below.
From a fresh clone or worktree:

```powershell
# Create once; skip this command when .venv already exists.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Required for Python tests too: core tests import the HTTP adapter.
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
```

On non-Windows hosts, use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe`. Commands run from the repository root. For isolated
fixture tests, remove any inherited production `DATABASE_URL`, `SQLITE_PATH` or
`CVM_*` path overrides from the test process; do not point tests at user data.
Do not clear these settings globally or change the user's configured database.

## Isolated Worktree Bootstrap

Parallel issues run in separate git worktrees (one per session; use the host app's managed worktree tools when available, otherwise `git worktree add`). From a fresh worktree, prepare the
frontend dependencies:

```powershell
.\scripts\setup\bootstrap_worktree.ps1
```

The bootstrap prints the worktree it is preparing, requires Node.js 22+ and
Python 3.11+, and verifies the local Vite executable. If
`apps/desktop-web/node_modules/.bin/vite.cmd` is missing, it runs `npm ci` in
that worktree's `apps/desktop-web` directory. It does not copy or version
`node_modules`, change lockfiles, create a virtual environment, or install
Python packages. Run the normal Python setup separately when the task needs it.

## Active Development Modes

### Real Desktop Dev

```powershell
python -m desktop.app --dev
```

This starts a new Vite dev server on `127.0.0.1`, using the first free port from
`5173` through `5199`, then opens pywebview with the real Python bridge. The
launcher removes inherited `VITE_MOCK_BRIDGE` from the Vite process environment;
it does not reuse an existing preview server. See
[`_start_vite_dev_server()`](../desktop/app.py#L999).

With no path overrides or release-data opt-in, desktop dev uses:

```text
<repo>\data\dev-runtime
```

This data persists across launches and accepts updates. The packaged app defaults
to `%USERPROFILE%\Documents\CVMAnalytics`. See [Data Paths](#data-paths) for
overrides and output/log locations.

### Custom Data Dev

```powershell
$env:CVM_DATA_DIR = "$PWD\data\dev-sandbox"
python -m desktop.app --dev
```

`CVM_DATA_DIR` takes precedence over the default dev root and release-data
selection. Other path overrides remain effective; confirm the database path in
Settings -> Diagnostics before resets or fixture work.

### Dev With Installed-App Data

Use a shell without `CVM_DATA_DIR` or conflicting database/path overrides:

```powershell
.\scripts\release\dev-desktop-release-data.ps1
```

The script sets `CVMANALYTICS_USE_RELEASE_DATA=1`. The launcher selects
`CVMANALYTICS_DATA_DIR` when set, otherwise `%USERPROFILE%\Documents\CVMAnalytics`.
Check Settings -> Diagnostics to confirm the effective paths.

Guarded bridge writes, including updates and resets, are blocked in this mode
unless `CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1` is set and no concurrent lock
conflict is detected. This guard does not make the database connection read-only;
startup initialization can still write metadata. See
[write policy](../desktop/bridge_api/status.py#L1067) and
[startup initialization](../desktop/app.py#L1204).

### Desktop Flags

| Flag | Effect |
|---|---|
| `--dev` | Starts its own Vite server on the first free loopback port in `5173`–`5199` |
| `--debug` | Opens DevTools in the active mode |
| (none) | Serves `apps/desktop-web/dist` or `_internal/desktop-web` |
| `--repair-dev-environment` | Reinstalls declared dependencies in `.venv` (use with `--dev`) |
| `--rebuild-dev-environment` | Recreates `.venv` (use with `--dev`) |

Bridge sanity check with `--debug`, from the DevTools console:

```javascript
await window.pywebview.api.ping()
// => {pong: true, ts: 1234567890.0}

await window.pywebview.api.get_companies({page: 1, page_size: 5})
// => {items: [...], pagination: {...}}
```

### Packaged Mode

```powershell
.\desktop\build_desktop.ps1
.\dist\CVMAnalytics\CVMAnalytics.exe
```

The packaged app serves the static Vite build; the Python bridge answers reads
directly, so FastAPI is not needed.

### Browser Preview

```powershell
npm --prefix apps/desktop-web run dev
```

This has no pywebview bridge. It is useful for layout work only.

### Mock Bridge Preview

```powershell
npm --prefix apps/desktop-web run dev:mock
```

This uses fixture data from `apps/desktop-web/src/lib/bridge/mock.ts`. Do not use
mock mode to validate real database behavior.

### HTTP API Adapter

The container runs one Uvicorn worker because batch refresh jobs and cancellation
signals are process-local. Do not deploy multiple API workers or replicas until
job ownership and status are shared. Restarting the process loses its batch-job
registry; persisted financial data is unaffected. Concurrent submissions within
the process reuse the active job. CI runs both `tests/` and `apps/api/tests/`.

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.app.main:app --reload
```

Swagger is at `http://127.0.0.1:8000/docs` and OpenAPI at
`http://127.0.0.1:8000/openapi.json`. Main endpoints: `/health`, `/companies`,
`/companies/filters`, `/companies/{cd_cvm}`, `/companies/{cd_cvm}/years`,
`/companies/{cd_cvm}/statements`, `/companies/{cd_cvm}/kpis`,
`/refresh-status`, `/base-health`. See `docs/reference/v2-api-contract.md`.

## Database Setup

On a new machine or after a migration:

```powershell
.\.venv\Scripts\python.exe scripts/setup/setup_db.py
.\.venv\Scripts\python.exe scripts/setup/setup_companies_table.py
```

Optional ticker expansion preview:

```powershell
.\.venv\Scripts\python.exe scripts/data/expand_tickers.py --dry-run
```

## Refreshing Data Outside The App

The normal path is Settings -> Updates in the desktop app. For headless work:

```powershell
# one-off CLI refresh
.\.venv\Scripts\python.exe main.py --companies PETROBRAS --start_year 2021 --end_year 2025 --type consolidated --skip_complete

# batch refresh
.\.venv\Scripts\python.exe scripts/data/batch_completo.py --dry-run
.\.venv\Scripts\python.exe scripts/data/atualizar_todos.py --anos 2024 2025

# safe Update Base smoke (default mode=missing, limit=1; live only with --confirm-live)
.\.venv\Scripts\python.exe scripts/diagnostics/update_base_smoke.py --dry-run --mode missing --limit 1
```

Log defaults depend on the entry point: `main.py` uses the core settings default
`<repo>/src/output/logs`, while the batch scripts above explicitly resolve the
repository root and use `<repo>/output/logs`. The smoke command's dry run prints
its evidence. `CVM_OUTPUT_DIR` and `CVM_LOG_DIR` can override these paths. See
[Data Paths](#data-paths), `docs/database-updates.md` and
`docs/governance/on-demand-release-evidence.md`.

## Common Checks

Frontend:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Python:

```powershell
.\.venv\Scripts\python.exe -m py_compile desktop/app.py desktop/bridge.py
.\.venv\Scripts\python.exe -m pytest tests -q
```

API adapter when touched:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
```

Pre-PR check (fast CI contract mirror plus changed-area checks before `git push`):

```powershell
.\.venv\Scripts\python.exe scripts/diagnostics/pre_pr_check.py
.\.venv\Scripts\python.exe scripts/diagnostics/pre_pr_check.py --full-python
```

Runtime diagnostics:

```powershell
# minimal
.\.venv\Scripts\python.exe scripts/diagnostics/runtime_doctor.py --require-canonical

# full
.\.venv\Scripts\python.exe scripts/diagnostics/runtime_doctor.py --require-db --table financial_reports --table companies --require-canonical
.\.venv\Scripts\python.exe scripts/data/canonicalize_data_layout.py
.\.venv\Scripts\python.exe scripts/diagnostics/db_portability_smoke.py --write-check

# PostgreSQL, without exporting a variable
.\.venv\Scripts\python.exe scripts/diagnostics/runtime_doctor.py --database-url postgresql://user:pass@host:5432/db --require-db --table financial_reports --table companies
.\.venv\Scripts\python.exe scripts/diagnostics/db_portability_smoke.py --database-url postgresql://user:pass@host:5432/db --write-check
```

Workbook QA (manual; run only after generating an XLSX through `main.py` or
the desktop export; not part of setup or CI):

```powershell
.\.venv\Scripts\python.exe scripts/qa/quick_verify.py --xlsx output/reports/PETROBRAS_financials.xlsx
.\.venv\Scripts\python.exe scripts/qa/verify_consolidation.py --xlsx output/reports/PETROBRAS_financials.xlsx
.\.venv\Scripts\python.exe scripts/qa/verify_line_id_base.py --xlsx output/reports/PETROBRAS_financials.xlsx

# historical regression for an old four-bug campaign; not part of the normal flow
.\.venv\Scripts\python.exe scripts/qa/final_verification.py --xlsx output/reports/PETROBRAS_financials.xlsx
```

All workbook QA scripts share `scripts/qa/workbook_paths.py` for XLSX path
resolution.

Desktop package build:

```powershell
.\desktop\build_desktop.ps1
```

## Data Paths

The desktop launcher sets path defaults in
[`desktop/app.py:141`](../desktop/app.py#L141), and core settings resolve them in
[`src/platform/settings.py:147`](../src/platform/settings.py#L147).

Without an explicit `CVM_DATA_DIR`, the source desktop launcher sets the dev or
release-data root plus `{data}/output` and `{data}/logs`. The packaged launcher
also supplies these output/log defaults. Existing per-path overrides are retained.

With an explicit `CVM_DATA_DIR`, source desktop skips that default injection.
The desktop's core settings currently default output to `<repo>/src/output` and
logs to `<repo>/src/output/logs`, unless overridden: the default settings root is
the `src` directory ([implementation](../src/platform/settings.py#L30)).
This also applies to `scripts/release/dev-desktop.ps1`, which sets `CVM_DATA_DIR`
explicitly and clears release-data mode. Selecting a data root alone does not
redirect every output path.

The launcher also supplies `SQLITE_PATH` independently of `CVM_DB_DIR`. To move
the main SQLite file, set `SQLITE_PATH` explicitly; it takes precedence over the
database-directory fallback.

Important environment variables:

| Variable | Purpose |
|---|---|
| `CVM_DATA_DIR` | Root data directory for dev/all core paths |
| `CVMANALYTICS_DATA_DIR` | Release data-root override, also used by explicit release-data dev |
| `CVMANALYTICS_USE_RELEASE_DATA` | Opt into release-data dev; defaults to unset, and `CVM_DATA_DIR` still takes precedence |
| `CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES` | Allow guarded bridge writes in release-data dev when there is no lock conflict |
| `SQLITE_PATH` | Main SQLite file override |
| `CVM_DB_DIR` | Database directory override |
| `CVM_OUTPUT_DIR` | Output directory override |
| `CVM_LOG_DIR` | Log directory override |
| `CVM_CACHE_DIR` | Cache directory override |
| `VITE_MOCK_BRIDGE` | Browser mock-preview flag; inherited value removed from desktop-launched Vite |

See [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md) for detailed
lock/write-mode behavior.

## Common Setup Problems

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` when opening the desktop app | Run `python -m desktop.app --repair-dev-environment --dev`; do not install modules individually. |
| `python` is not recognized | Install Python 3.11+ and enable adding it to `PATH`. |
| `runtime_doctor.py` fails with `venv-broken` | Run `python -m desktop.app --rebuild-dev-environment --dev`. |
| Desktop app opens with no companies | Run `setup_db.py` and `setup_companies_table.py`, then refresh data. |
| API returns `503` | Check the database, required tables, and `runtime_doctor.py`. |
| PowerShell permission error | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Vite UI did not open in the desktop app | Run `npm --prefix apps/desktop-web run build` or use `python -m desktop.app --dev`. |

For runtime, data, updater, and export problems, see
[troubleshooting.md](troubleshooting.md).

## Before Editing

- UI work: inspect `apps/desktop-web`, read
  [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](skills/CVMANALYTICS_VITE_UI_SKILL.md),
  and run the frontend typecheck after TS/TSX edits.
- Data/modeling/API work: read [docs/CONTEXT.md](CONTEXT.md).
- Packaging/updater work: read [docs/build-release.md](build-release.md) and
  inspect `desktop/app.spec`, `desktop/build_desktop.ps1`, `desktop/updater.py`,
  and `desktop/update_helper.ps1`.
- Docs-only work: do not change application behavior.
