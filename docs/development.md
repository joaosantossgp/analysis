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

## Isolated Worktree Bootstrap

For autonomous task worktrees, create the task workspace from `main`, then run
the bootstrap from that worktree:

```powershell
.\scripts\governance\worktree_create.ps1 -Issue <issue-number> -Slug <task-slug> -Lane ops-quality
Set-Location .\.claude\worktrees\ops-quality\<issue-number>-<task-slug>
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

This starts or reuses the Vite dev server at `127.0.0.1:5173`, opens pywebview,
and uses the real Python bridge.

By default, dev mode points at the same Documents data root as the packaged app:

```text
%USERPROFILE%\Documents\CVMAnalytics
```

Destructive bridge actions are blocked in dev+release-data mode unless
`CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1` is set.

### Isolated Data Dev

```powershell
$env:CVM_DATA_DIR = "$PWD\data"
python -m desktop.app --dev
```

Use this for destructive experiments, resets, or fixture work.

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

## Common Checks

Frontend:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

Python:

```powershell
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

API adapter when touched:

```powershell
pytest apps/api/tests -q
```

Runtime diagnostics:

```powershell
python scripts/diagnostics/runtime_doctor.py --require-canonical
```

Desktop package build:

```powershell
.\desktop\build_desktop.ps1
```

## Data Paths

Path resolution is centralized in `src/platform/settings.py` and desktop
packaged overrides in `desktop/app.py`.

Important environment variables:

| Variable | Purpose |
|---|---|
| `CVM_DATA_DIR` | Root data directory for dev/all core paths |
| `CVMANALYTICS_DATA_DIR` | Packaged app override |
| `SQLITE_PATH` | Main SQLite file override |
| `CVM_DB_DIR` | Database directory override |
| `CVM_OUTPUT_DIR` | Output directory override |
| `CVM_LOG_DIR` | Log directory override |
| `CVM_CACHE_DIR` | Cache directory override |
| `VITE_MOCK_BRIDGE` | Dev-only mock bridge flag |

See [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md) for detailed
lock/write-mode behavior.

## Before Editing

- UI work: inspect `apps/desktop-web`, read
  [docs/skills/CVMANALYTICS_VITE_UI_SKILL.md](skills/CVMANALYTICS_VITE_UI_SKILL.md),
  and run the frontend typecheck after TS/TSX edits.
- Data/modeling/API work: read [docs/CONTEXT.md](CONTEXT.md).
- Packaging/updater work: read [docs/build-release.md](build-release.md) and
  inspect `desktop/app.spec`, `desktop/build_desktop.ps1`, `desktop/updater.py`,
  and `desktop/update_helper.ps1`.
- Docs-only work: do not change application behavior.
