# Packaged Windows storage validation — #479

Date: 2026-11-06. Scope: the Windows snapshot replacement fix in #478.
**Persistence passed in the actual executable. UI completion/error reporting
has separate gaps tracked in [#480](https://github.com/joaosantossgp/analysis/issues/480).**
This is targeted local validation, not release acceptance or publication.

## Artifact identity

| Field | Observed value |
|---|---|
| Source commit | `898c1ef6c824ecda6dd31a809c1d5b794e782c3a` (tracked-clean before build) |
| Build command | `desktop/build_desktop.ps1 -Version 0.30.0-rc.1`, with `.venv/Scripts` first on PATH |
| Runtime | `0.30.0-rc.1`, build `898c1ef`, built `2026-11-06T14:16:54Z` |
| Shell | Frozen Python, Vite, pywebview/WebView2; bridge ready |
| Host/tooling | Windows build 26200; Python 3.14.7; PyInstaller 6.22.3; Node 24.19.0 |
| Executable | `dist/CVMAnalytics/CVMAnalytics.exe`, 22,876,208 bytes |
| EXE SHA-256 | `116764887f5a3a35924b4c5a3e120f07b8a2964a3679103ebafa5940aad5599b` |
| Bundle | 2,645 files, 316,682,254 bytes; no `.db`, `.sqlite` or `.sqlite3` files |
| Bundle manifest SHA-256 | `f74fdf88142a1cb391e23a1fffee000ee955dc24500416e477b3d3a568e8e236` |

The executable requires its adjacent bundle files. The manifest records each
relative path, size and hash. Later diagnostic/documentation commits are not
the source of this tested artifact. No release tag or uploaded artifact was made.

## Isolation and method

The test started with a fresh, empty `tmp/packaged-storage-479/fixture`, without
copying production data. Both data-root variables and explicit database, input,
metadata, output, reports, logs, cache, energy/news database, energy raw-data and
onboarding paths pointed inside that fixture. `LOCALAPPDATA` used a separate
test profile. `DATABASE_URL` was cleared in the child process.

HTTP/HTTPS/ALL proxy variables and WebView2's proxy pointed at the unavailable
loopback endpoint `127.0.0.1:9`; only localhost bypassed it. The catalog URL also
pointed there and market-cap auto-refresh was disabled. This exercised cached
reads with those network paths unavailable; it was not a network packet audit.

The canonical build and real EXE were used, without patching bundled Python or
mocking the bridge. The existing `validate_packaged_ui.cjs --readiness-only`
check confirmed version, build and readiness. The focused harness
[`validate_packaged_storage.cjs`](../../scripts/diagnostics/validate_packaged_storage.cjs)
checked the frozen runtime and effective paths before scanning. A separate
Python process opened the JSON snapshot with a real Windows read handle that
denies replacement. This produced WinError 5 in the packaged writer.

## Results

| Scenario | Result |
|---|---|
| 20 consecutive explicit bridge scans | All succeeded; each persisted the matching scan ID |
| Transient reader lock | Old JSON remained unchanged while blocked; releasing the reader allowed the same scan to succeed |
| Lock held beyond retry budget | Worker failed with WinError 5 after 684 ms; old snapshot hash stayed unchanged and cached data remained readable |
| New scan after releasing persistent lock | Succeeded and persisted its own scan ID |
| Restart with network paths unavailable | Same snapshot hash and timestamp; worker scan status `idle`, with no hidden rescan |
| Settings after persistent failure | Cached totals remained visible, but the worker error was not displayed: #480 |
| UI-triggered successful scan | Bridge succeeded in 84 ms; after 2.2 seconds button still disabled as `Scanning...`: #480 |

The snapshot verified immediately after restart had SHA-256
`0adb29fd801141b7a4219bc1cbff95fe3d717cbf8741e3762c9358c5684053c4`.
The later UI-button probe intentionally created another snapshot.

Closing the first window did not terminate its process within 15 seconds.
The restart therefore followed a forced stop of the verified test PID; the
new process recovered the stale local lock. Graceful shutdown is **not validated**.
Final cleanup stopped only the recorded test process and confirmed CDP port
9237 was no longer listening.

## Reproduction

Build the source above with the canonical builder. Before launching, create a
fresh evidence directory and configure the child process as follows (`$f` is
its absolute `fixture` directory; `$e` is its absolute parent):

```powershell
$childEnv = @{
  CVMANALYTICS_DATA_DIR=$f; CVM_DATA_DIR=$f
  CVM_DB_DIR="$f/db"; SQLITE_PATH="$f/db/cvm_financials.db"
  CVM_INPUT_DIR="$f/input"; CVM_METADATA_DIR="$f/metadata"
  CVM_OUTPUT_DIR="$f/output"; CVM_REPORTS_DIR="$f/output/reports"
  CVM_LOG_DIR="$f/logs"; CVM_CACHE_DIR="$f/cache"
  CVM_ENERGY_KPI_DB="$f/db/energy_kpis.db"; CVM_NEWS_DB="$f/db/news.db"
  CVM_ENERGY_KPI_RAW_DIR="$f/raw/energy"
  CVM_ONBOARDING_STATE_PATH="$f/onboarding_state.json"
  LOCALAPPDATA="$e/localappdata"; DATABASE_URL=''
  HTTP_PROXY='http://127.0.0.1:9'; HTTPS_PROXY='http://127.0.0.1:9'
  ALL_PROXY='http://127.0.0.1:9'; NO_PROXY='127.0.0.1,localhost'
  CVM_CATALOG_URL='http://127.0.0.1:9/cad.csv'; CVM_MARKET_CAP_AUTO_REFRESH='0'
  WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9237 --remote-allow-origins=* --proxy-server=http://127.0.0.1:9 --proxy-bypass-list=127.0.0.1;localhost'
}
$app = Start-Process ./dist/CVMAnalytics/CVMAnalytics.exe -Environment $childEnv -WindowStyle Hidden -PassThru
$source = '898c1ef6c824ecda6dd31a809c1d5b794e782c3a'
node scripts/diagnostics/validate_packaged_storage.cjs http://127.0.0.1:9237 $e $source .venv/Scripts/python.exe exercise
```

Use PowerShell 7 with `Start-Process -Environment`, ensure port 9237 is free,
and retain the launched PID/path for cleanup. Stop that process, relaunch the
same EXE with the same environment, then run the harness with `restart` instead
of `exercise`. Do not perform a new scan between these two checks. The harness
is scoped to version `0.30.0-rc.1`; it requires Windows and installed frontend
Playwright dependencies. It does not launch or stop the application itself.

## Evidence and limits

Local checks: `node --check scripts/diagnostics/validate_packaged_storage.cjs`,
`git diff --check`, the actual packaged exercise/restart runs above, and the
four CI governance modules (44 tests passed). No Python application or UI
source was edited; full application suites run in PR CI.

Raw evidence remains local under `tmp/packaged-storage-479/`: runtime/path
payloads, launch/restart/cleanup records, bundle manifest, logs, and screenshots
`storage-locked.png`, `storage-recovered.png`, `ui-refresh.png`. Build output is
`tmp/packaged-storage-build.log`. These files are not committed or published.

| Local evidence file | SHA-256 |
|---|---|
| `storage-exercise.json` | `faab436a654a203d20879d3b5bd0867735fb634e973384e51f2bc9fdc90bab64` |
| `storage-restart.json` | `42a3cb3cf52e4a0bc0dc9cce6a30fa0a84324031d838af930f4b246e00fd94f2` |
| `ui-refresh.json` | `09f376f67f81b064f59b2de0999dbdc935a2d9a3e39e3ab8bee1be5d03cb49ff` |
| `readiness/ui-results.json` | `80cddcfd81b5b0a0408673eb56683413de3e88a8044bdccd5564593f705d1fc2` |

Not covered: real portfolio volumes, financial data ingestion, update/install
flows, Excel exports, other Windows versions, default Documents-path operation,
or complete release acceptance. The UI gaps and shutdown observation do not
invalidate the persistence checks, but prevent claiming the whole application
passed. No application code was changed for this validation.
