# Phase 0 Release Checkpoint — v0.3.0

## Release

- Tag: v0.3.0
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.0
- Artifact: CVMAnalytics-windows-v0.3.0.zip
- SHA-256: 683bc764f8474a85fff7e36ace7aa7d1cbade87815260c5e433dffb216987be6

## Status

Phase 0 is released. **v0.3.0 was superseded by v0.3.1 due to a packaging bug.**

### v0.3.1 hotfix

- Tag: v0.3.1
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.1
- Artifact: CVMAnalytics-windows-v0.3.1.zip
- SHA-256: f7c648336d67321780ee5add53a0f94daba394417943c5315a6fe4575bae6105

**Root cause of v0.3.0 failure:** `Python.Runtime.deps.json` was missing from `_internal/pythonnet/runtime/`. PyInstaller's default collector shipped only `Python.Runtime.dll`. Without the sibling `.deps.json`, the .NET CLR could not bind the assembly's framework references, so pywebview's WinForms backend crashed with `RuntimeError: Failed to resolve Python.Runtime.Loader.Initialize`. The bug was invisible on developer machines because the dev Python install provided the missing pieces on PATH.

**Fix:** `desktop/app.spec` now walks `pythonnet/runtime/` and ships every file (`dll`, `deps.json`, `xml`, `pdb`). UPX disabled entirely as belt-and-suspenders. Startup preflight (`_preflight_pywebview_backend`) catches `import clr` failures and shows a native MessageBox instead of a raw traceback.

**Validated against the published v0.3.1 asset:** `gh release download` → MOTW (ZoneId=3) → `Expand-Archive` → launch → process alive after 25s with 20 `msedgewebview2.exe` child processes.

### v0.3.2 hotfix #2

- Tag: v0.3.2
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.2
- Artifact: CVMAnalytics-windows-v0.3.2.zip
- SHA-256: cc01970b070507459be5f47bd63c0a5e82a6e9ed2ce13e667f993ee02f0432d7

**Why v0.3.1 was insufficient:** the original reporter's machine still failed with the same `Failed to resolve Python.Runtime.Loader.Initialize` error after installing v0.3.1. That error is pythonnet's generic wrapper for any CLR-initialization failure, not specifically a missing `.deps.json`. Without precise prerequisite detection, both v0.3.0 and v0.3.1 produced the same uninformative wrapper for distinct underlying causes.

**Fix in v0.3.2:**

- `_preflight_pywebview_backend()` now runs three precise checks before `import clr`:
  1. Bundle file presence (`Python.Runtime.dll`, `Python.Runtime.deps.json`).
  2. .NET Framework 4.8+ via `HKLM\...\NDP\v4\Full\Release >= 528040`.
  3. WebView2 Runtime via the Evergreen client registry key.
- Each check shows a precise MessageBox with the specific missing prerequisite and the official Microsoft download URL.
- New `--diagnose-runtime` flag runs all probes without starting pywebview, writes a full report to `%LOCALAPPDATA%\CVMAnalytics\diagnostics-<utc>.log`, and opens it in Notepad. Designed so the reporter can attach one log to a bug report.

**Validated against the published v0.3.2 asset:** real download via `gh release download v0.3.2`, MOTW applied, extracted, launched. Process alive after 25s with 20 `msedgewebview2.exe` child processes. Unit-tested missing-.NET-Framework branch returns the precise Portuguese MessageBox with the dotnet.microsoft.com URL. Phase 0 regressions (fresh init, WAL-safe legacy migration, LOCALAPPDATA preservation) all pass on the v0.3.2 build.

**Pending:** real confirmation from the original reporter's machine. If launch still fails, the `--diagnose-runtime` log will tell us precisely which prerequisite or runtime check is the blocker.

### v0.3.3 hotfix #3 — actual root cause

- Tag: v0.3.3
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.3
- Artifact: CVMAnalytics-windows-v0.3.3.zip
- SHA-256: 296d1d82c7a1fab4c62be8fc2d109e779e93b4e5a2c377396740d2b3170e24e1

**The v0.3.2 diagnostic log proved the actual root cause.** Reporter's machine had every prerequisite present (.NET Framework 4.8 Release=533509, WebView2 148.0, all bundle files intact) but `import clr` still failed at `clr_loader/netfx.py:49`. That can only happen if the .NET runtime itself rejected the assembly.

**Cause:** Windows Explorer's "Extract All" (the default on Windows 11) propagates Mark-of-the-Web (Zone.Identifier ADS, ZoneId=3) to every extracted file. .NET Framework's default `loadFromRemoteSources` policy refuses to execute managed assemblies flagged as Internet zone. `Assembly.LoadFile("...\\Python.Runtime.dll")` silently returns null → `clr_loader` raises the generic "Failed to resolve Python.Runtime.Loader.Initialize" error. The v0.3.0 deps.json fix and the v0.3.2 prereq checks were therefore both partial fixes for the wrong layer.

**Why this slipped past our packaged smoke tests:** PowerShell's `Expand-Archive` does NOT preserve MOTW on extracted files. Our test harnesses used `Expand-Archive`, so the bundle came out MOTW-free and `Assembly.LoadFile` worked. The bug only reproduces when the user extracts via Explorer.

**Fix in v0.3.3:** `desktop/app.py::_strip_motw_from_bundle()` walks the PyInstaller `_MEIPASS` at startup and removes the `:Zone.Identifier` alternate data stream from every .dll/.exe/.pyd/.node/.ps1 via Win32 `DeleteFileW`. Idempotent. Silent on failure. Never touches file contents.

**Reproduction:** `scripts/test_motw_explorer.ps1` stamps MOTW on all 115 binaries in the extracted bundle (simulating Explorer Extract All). Without v0.3.3 the launch fails identically to the reporter's crash. With v0.3.3 the launch survives 30s with 20 `msedgewebview2.exe` children.

**Validated on the v0.3.3 build:** the Explorer-MOTW reproduction passes; Phase 0 regressions (legacy WAL migration, LOCALAPPDATA preservation) pass; the diagnostic log section confirms MOTW streams are stripped at startup.

### v0.3.4 hotfix #4 — CI zip layout fix

- Tag: v0.3.4
- GitHub Release: https://github.com/joaosantossgp/analisys/releases/tag/v0.3.4
- Artifact: CVMAnalytics-windows-v0.3.4.zip (78,409,144 bytes)
- SHA-256: 496bf3f976bceac2ef02ac4584b5c6fc30017b30e801309c8e7cef6e694bfbd5

**Why v0.3.3 was insufficient:** the v0.3.3 startup fix worked, but the CI workflow's `Compress-Archive -Path dist\CVMAnalytics` wrapped the bundle in a `CVMAnalytics/` directory at the archive root. `desktop/update_helper.ps1` allowlist (`CVMAnalytics.exe`, `_internal`) only matches the flat root. Staging a v0.3.3 update would silently no-op — the helper would skip both entries because the actual files lived one level deeper. Manual fresh-install still worked because the user navigates into the wrapper directory.

**Fix in v0.3.4:** `.github/workflows/release-desktop.yml` now uses `Compress-Archive -Path dist\CVMAnalytics\*` (contents only), plus a post-archive verification step that fails the workflow if `CVMAnalytics.exe` and `_internal` are not both at the archive root.

**Validated on the published v0.3.4 asset (`scripts/test_ci_v034_full.ps1`):**

- Asset layout: roots = `['CVMAnalytics.exe', '_internal']` (flat, updater-compatible).
- Fresh install with MOTW applied to 155 binaries: process alive 30s, 19 `msedgewebview2.exe` children, LOCALAPPDATA DB created.
- Updater staging: zip extracted into staging dir produces the flat structure; helper finds both allowlist entries.
- Helper swap: exit code 0, old `_internal/OLD_MARKER.txt` removed, new content swapped in.
- User-data preservation: `data/db/cvm_financials.db`, `data/db/cvm_financials.db-wal`, and `output/report.xlsx` all preserved byte-for-byte after swap.
- Rollback snapshot: `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-ts>\` contains the pre-swap `CVMAnalytics.exe` + `_internal` only — no user data.

**Phase 0 status: stable.** The CI bundle is updater-compatible and the real download/extract/launch path works under MOTW.

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
