# Phase 0 Release Checkpoint — v0.3.0

## Release

- Tag: v0.3.0
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.0
- Artifact: CVMAnalytics-windows-v0.3.0.zip
- SHA-256: 683bc764f8474a85fff7e36ace7aa7d1cbade87815260c5e433dffb216987be6

## Status

Phase 0 is released.

## What Phase 0 solved

- User runtime DB moved to `%LOCALAPPDATA%\CVMAnalytics\db\cvm_financials.db`
- Legacy install-dir DB migration implemented
- WAL-safe SQLite backup migration implemented (via `sqlite3.Connection.backup()` on a read-only handle)
- Fresh install DB initialization implemented (`init_db_tables` called after migrator)
- Update helper hardened with allowlist + rollback snapshot
- Build no longer copies full dev DB into packaged app
- README and GitHub repository profile updated

## Validation completed

- Packaged build
- Fresh install smoke
- Legacy DB migration smoke (WAL-dirty rows preserved)
- Existing LOCALAPPDATA DB preservation smoke
- Update helper real-layout smoke (sandbox with planted user data)
- WebView2 launch smoke (21 webview2 child processes, Next standalone reachable)
- GitHub release discovery via real updater code
- Artifact download
- SHA-256 validation against the published `.sha256` file
- Release ZIP staging into `%LOCALAPPDATA%\CVMAnalytics\versions\0.3.0\`

## Validation still deferred

- Real helper swap from an actual installed v0.2.x app into v0.3.0
- Real user-machine post-update smoke
- Multi-machine Windows compatibility
- Antivirus / SmartScreen behavior on signed-vs-unsigned binary
- Code signing decision

## Current architecture after Phase 0

The app still uses:

- Python data pipeline
- SQLite
- pywebview / WebView2
- Next.js standalone server
- bundled Node runtime
- PyInstaller onedir

Vite has not been introduced yet.

Next.js, FastAPI, and Node have not been removed.

## Do not start Phase 1 until

- v0.3.0 has had a short soak period, or
- the user explicitly waives the soak period

## Next phase

Phase 1 should create a parallel Vite SPA shell under `apps/desktop-web/`.

Phase 1 must not delete the existing Next app.

See `NEXT_AGENT_HANDOFF.md` for the Phase 1 brief.

## Known repository hygiene issue

`desktop/__version__.py` is modified by the build process.

Inspection result:

- File is tracked in git (`git ls-files` confirms).
- Last committed value: `__version__ = "0.2.0-40-g9b08760"` (output of `git describe --tags --always` captured by some prior build).
- `desktop/build_desktop.ps1` overwrites this file on every build with the value of `git describe --tags --always` (or the `-Version` arg).
- After the v0.3.0 release build, the working tree contains `__version__ = "0.3.0"` while `HEAD` still has the older string.

The file is therefore neither pure source nor pure build artifact. The result is a permanently dirty working tree after every build, and a tag-time race where the commit being tagged does not contain the version string the artifact will ship with.

Current decision:

- Do not fix during Phase 0.
- Future cleanup should decide whether the version should be:
  1. committed source state, updated as part of the release commit;
  2. generated into a build-only path (e.g. `dist/_version.py`) and never tracked;
  3. reverted after release builds via a post-build hook;
  4. or replaced entirely by package metadata or tag-derived versioning resolved at runtime (e.g. `git describe` at startup in dev, `_MEIPASS` resource in bundled mode).

Do not gitignore a tracked version file without first confirming the intended versioning model. Removing it from tracking would lose the only place the bundled runtime can read its own version at PyInstaller-frozen time.
