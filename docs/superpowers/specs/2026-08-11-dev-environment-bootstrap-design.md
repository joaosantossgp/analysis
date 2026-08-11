# Development Environment Bootstrap Design

## Goal

Make `python -m desktop.app --dev` provision the repository-local development
environment on a fresh Windows machine once Python and Node.js are available.
Developers must not install Python packages individually.

## Context and Findings

The active desktop shell is `desktop/app.py`; it hosts the Vite application in
`apps/desktop-web` through pywebview.  The root `requirements.txt` is the
canonical desktop/core Python manifest and already declares `pywebview`.
`scripts/setup/bootstrap_windows.ps1` can create `.venv` and install that
manifest, but it is not called by the documented desktop command.  `app.py`
imports `webview` before it can select `.venv`, which is why a fresh global
Python interpreter raises `ModuleNotFoundError`.

Production uses PyInstaller (`desktop/app.spec` and
`desktop/build_desktop.ps1`).  The frozen application must not run the
development bootstrap: PyInstaller owns its embedded Python runtime and
dependency bundle.

## Design

Create a standard-library-only `desktop/dev_bootstrap.py` module.  Before
`desktop.app` imports third-party runtime modules, it will call the bootstrap
only for source-mode execution.  The bootstrap will:

1. Require Python 3.11+ and create `.venv` with the invoking interpreter when
   it does not exist.
2. Compute a SHA-256 fingerprint of `requirements.txt` and store successful
   provisioning metadata under `.venv/.cvmanalytics-dev-bootstrap.json`.
3. Run `<venv>\\Scripts\\python.exe -m pip install -r requirements.txt` only
   when the environment is new, its interpreter differs, its manifest
   fingerprint changes, or the developer explicitly requests repair.
4. Re-execute `python -m desktop.app ...` with the virtual-environment
   interpreter before `webview` or bridge code is imported.
5. For `--dev`, validate Node.js 22+ and run `npm ci` only when the Vite
   lockfile fingerprint differs from a stamp in `apps/desktop-web/node_modules`.
6. Raise explicit bootstrap errors with the attempted command, its exit code,
   and a recovery command.  It will never select packages dynamically from an
   `ImportError`.

`--rebuild-dev-environment` will force recreation of `.venv`; `--repair-dev-
environment` will retain the environment but re-synchronize declared Python
and frontend dependencies.  These flags are source-mode-only and removed from
the re-executed application arguments.

## Constraints

- Python 3.11+ and Node.js 22+ remain development prerequisites.
- `.venv` is the isolated environment; global site packages are not used for
  runtime dependencies.
- Root `requirements.txt` remains the canonical desktop/core dependency
  manifest.  `numpy` becomes explicit because active source imports it
  directly rather than only through pandas transitively.
- Frontend installation remains controlled by the committed `package-lock.json`
  through `npm ci`.
- Frozen/PyInstaller execution and its dependency bundle are unchanged.

## Testing

Unit tests will exercise first-run provisioning, unchanged-manifest fast paths,
repair/rebuild requests, subprocess failure messages, and re-execution target
selection without accessing the real network.  Manual validation will create a
temporary copy/sandbox environment, invoke only the normal dev command through
the bootstrap path, then restart it to confirm no pip/npm synchronization is
repeated.  Packaging validation will build and inspect the PyInstaller output
when local prerequisites permit.
