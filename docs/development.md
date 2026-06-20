# Development

## Prerequisites

- Python 3.11+
- Node.js 22+ for `apps/desktop-web`
- Windows for packaged desktop validation
- WebView2/.NET requirements for pywebview on Windows

Install dependencies:

```powershell
pip install -r requirements.txt
npm --prefix apps/desktop-web install
```

CI installs `requirements.txt`, `apps/api/requirements-dev.txt`, and runs
frontend checks with Node 22.

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
