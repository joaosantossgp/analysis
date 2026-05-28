# Release Process

What a release is, when one is required, and what can be validated in dev
without cutting one.

## What requires a release

A release is the packaged Windows artifact (`CVMAnalytics.exe`) that real users
download and auto-update into. Cut a release only when shipping changes that
must reach installed users:

- Python core / bridge behavior that changes shipped functionality
- packaging, PyInstaller spec (`desktop/app.spec`), or updater
  (`desktop/updater.py`, `desktop/update_helper.ps1`)
- the Vite UI bundle that users should receive

## What does NOT require a release

Normal UI and data-workflow validation needs no release. Use dev modes:

- UI/layout/styling → `npm run dev` or `npm run dev:mock` (browser, fixtures)
- realistic bridge + data → `python -m desktop.app --dev` (isolated `{repo}/data`)
- against real user data → `.\scripts\dev-desktop-release-data.ps1`

See [dev-runtime-and-data-paths.md](dev-runtime-and-data-paths.md). Do not build
or publish a release just to test a UI change or a data refresh.

## Versioning and tagging

- Single source of truth: `desktop/__version__.py` (`__version__`).
- The build injects this version into the packaged artifact
  (`desktop/build_desktop.ps1` step 2).
- The auto-updater compares the local version against the latest GitHub Release
  tag (`CVMAnalytics-windows-v<version>.zip` + `.sha256`).
- Release notes live under `docs/releases/v<version>.md`.

## Build (local)

```powershell
# from repo root
.\desktop\build_desktop.ps1
# -> dist\CVMAnalytics\CVMAnalytics.exe
```

The build runs the Vite build, injects the version, then runs
`pyinstaller desktop/app.spec`. The packaged folder ships only
`CVMAnalytics.exe` and `_internal/` — no user data, no dev database.

## Release checklist

1. `npm --prefix apps/desktop-web run typecheck` + `run build` pass.
2. `pytest tests -q` (and `pytest apps/api/tests -q` if the API changed) pass.
3. Bump `desktop/__version__.py`.
4. Add `docs/releases/v<version>.md`.
5. Build and smoke-test `dist/CVMAnalytics/CVMAnalytics.exe`.
6. Tag + publish the GitHub Release with the zip and its `.sha256`.

Do not bump the version or publish a release as part of routine dev/audit work.
