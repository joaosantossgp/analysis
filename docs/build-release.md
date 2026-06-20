# Build And Release

## Product Artifact

The shipped product is the Windows desktop bundle:

```text
dist/CVMAnalytics/CVMAnalytics.exe
dist/CVMAnalytics/_internal/
```

The bundle is produced by `desktop/build_desktop.ps1` and PyInstaller using
`desktop/app.spec`.

## Local Build

```powershell
.\desktop\build_desktop.ps1
```

What the build does:

1. Runs `npm run build` in `apps/desktop-web`.
2. Verifies `apps/desktop-web/dist/index.html` exists.
3. Resolves/injects version into `desktop/__version__.py`.
4. Writes build provenance to `desktop/_build_info.py`.
5. Runs `pyinstaller desktop/app.spec --noconfirm`.

`-SkipViteBuild` may be used only after a successful prior Vite build.

The desktop bundle includes the Vite static SPA, Python code/dependencies,
`update_helper.ps1`, and approved import assets such as canonical accounts and
GICS/ticker mapping CSVs. It must not bundle a user database.

## GitHub Release Workflow

`.github/workflows/release-desktop.yml` is the release pipeline. It:

- installs Python 3.11 dependencies;
- installs Node 22 dependencies for `apps/desktop-web`;
- runs `desktop/build_desktop.ps1 -Version <version>`;
- verifies bundled `desktop/__version__.py` matches the tag/input version;
- creates a flat-root ZIP from `dist\CVMAnalytics\*`;
- publishes:
  - `CVMAnalytics-windows-v<version>.zip`;
  - `CVMAnalytics-windows-v<version>.zip.sha256`;
  - `CVMAnalytics-windows.zip`;
  - `CVMAnalytics-windows.zip.sha256`.

Flat-root means the ZIP root contains `CVMAnalytics.exe` and `_internal/`
directly. A wrapper folder breaks the updater contract.

## Version Sources

- `desktop/__version__.py` is the runtime version source.
- `desktop/build_desktop.ps1` may derive a version from `git describe` for local
  builds unless `-Version` is supplied.
- The release workflow supplies the exact version and aborts if the bundled
  version differs.
- `desktop/_build_info.py` is generated build provenance and may show a
  post-tag describe string in local builds.

As of this audit, the repository contains tag `v0.28.0` and local
`desktop/__version__.py` is post-`v0.28.0`.

## Updater Contract

Verified implementation:

- `desktop/updater.py` checks GitHub Releases, compares versions, downloads the
  versioned ZIP and `.sha256`, validates checksum, extracts into
  `%LOCALAPPDATA%\CVMAnalytics\versions\<version>\`, and spawns the helper.
- `desktop/update_helper.ps1` swaps only allowlisted bundle entries:
  `CVMAnalytics.exe` and `_internal`.
- The helper snapshots overwritten files to
  `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\`.
- User data directories are denied by name and are not part of the bundle swap.

User data under `%USERPROFILE%\Documents\CVMAnalytics` must not be overwritten
by update/install flows.

## Release Validation

Before publishing:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python -m py_compile desktop/app.py desktop/bridge.py
pytest tests -q
```

Also run `pytest apps/api/tests -q` if `apps/api` or shared API contracts
changed.

Manual packaged validation:

- clean launch from `dist/CVMAnalytics/CVMAnalytics.exe`;
- app uses `%USERPROFILE%\Documents\CVMAnalytics`, not install-local data;
- Settings -> Diagnostics shows expected version/build/data paths;
- empty database state is understandable and non-crashing;
- offline read of already-downloaded data works;
- update check handles no-network and latest-version states explicitly;
- Excel export from the packaged app writes to output and opens without repair;
- install/update over a previous version preserves user data;
- update helper keeps ZIP root contract and rollback snapshot behavior.

## What Does Not Require A Release

Do not cut a release merely to test ordinary UI/docs/data workflow changes.
Use dev modes from [development.md](development.md).

Release only when installed users need the change or when packaging/updater
behavior changes.
