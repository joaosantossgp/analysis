# Packaged storage scan UI validation - #480

Date: 2026-11-11 (America/Sao_Paulo). Scope: Settings > Storage scan feedback.
The refresh control now returns after worker completion, and worker failures
remain visible beside the preserved inventory. This is targeted validation,
not release publication or full application acceptance. Tracking: #480, goal #486.

## Root cause and change

`SettingsModule.tsx` combined current inventory status with the mutation's
initial `running` response, which never advanced. It also displayed query/start
errors without displaying worker failures. The inventory query cache now owns
current status; scan admission cancels older reads and seeds the new status
without replacing cached totals. Pending admission remains busy.

The worker error banner preserves the actual error and identifies the previous
inventory. Browser preview retains its unavailable-state explanation and does
not claim a worker failed when no desktop scan could run.

## Artifact identity

| Field | Observed value |
|---|---|
| Source commit | `a447d6258348df2fc19f31c91585fc677bb616b7` |
| Build | `desktop/build_desktop.ps1 -Version 0.30.0-rc.1 -SkipViteBuild`, following a successful Vite build |
| Runtime | Frozen pywebview/WebView2, `0.30.0-rc.1`, build `a447d62` |
| Build time | `2026-11-12T01:19:32Z` |
| Tooling | Python 3.11.15, PyInstaller 6.22.3, pywebview 6.2.1, pythonnet 3.2.1 |
| Bundle | 2,639 files; 308,680,390 bytes; no `.db`, `.sqlite`, or `.sqlite3` files |
| EXE SHA-256 | `d0a48a1cb9676761aa9f6fa0148d751fc56333d52c0fc976ea4ee6d40d1558c7` |
| Bundle manifest SHA-256 | `ecdff769a263ef552ba3d070c086c5e923c4160bf0e9a27eddd45349b5f115af` |

The later documentation commit does not change the tested runtime sources.
The executable requires its adjacent bundle files; no release/tag was published.

## Isolation and method

The canonical builder produced the real executable. The fixture was created
under this worktree's `tmp/packaged-storage-480/fixture`, without copying user
data. Every effective data/database/input/metadata/output/log/cache path was
checked by the harness before triggering a scan. A separate LOCALAPPDATA profile,
explicit database paths, cleared DATABASE_URL, disabled market auto-refresh,
unavailable loopback catalog/proxy, and localhost-only proxy bypass followed the
[previous packaged isolation procedure](2026-11-06-packaged-storage-validation.md).
These controls are not a packet-level network audit.

The harness's new `ui` mode clicks the actual refresh button and reads the real
bridge. A separate Windows file reader denies replacement of the inventory JSON;
no bridge or bundled implementation is mocked. Screenshots were inspected at
1264 x 781 and include the failure banner, preserved metrics, and enabled control.

The final executable reused the isolated fixture after the first validation run.
It recovered the earlier test process's stale lock. All five files in the user's
normal CVMAnalytics root retained their sizes, modification timestamps, and
SHA-256 values. Timestamp comparisons used ISO strings to avoid PowerShell's
automatic JSON DateTime conversion producing a false difference.

## Results

| Scenario | Result |
|---|---|
| Normal UI-triggered scan | Succeeded in 79 ms; refresh button enabled afterward |
| Persistent Windows reader lock | Failed in 709 ms with WinError 5; full worker error visible; prior JSON hash and displayed totals unchanged; refresh enabled |
| Retry after releasing lock | Succeeded in 83 ms; previous error cleared; refresh enabled |
| Transient reader lock | Same scan recovered after release; prior JSON preserved while blocked; no persistent error; refresh enabled |
| Unit regressions | Eight scan-feedback cases: success/partial/failure, worker error with cached values, retry, stale-read race, initial inventory guard, browser unavailability |

Regression verification against the old component reproduced seven behavioral
failures. The browser follow-up separately failed before its guard was added.
Final frontend verification: **121 tests across 28 files passed**, typecheck
passed, and Vite build passed. Both Settings suites passed **10 tests**.
The candidate-harness governance suite passed **27 tests**. Script syntax and
`git diff --check` passed. An independent Ponytail review accepted the final code.

## Reproduction and evidence

Launch the source above using the isolated environment from the prior validation
record, with a free loopback CDP port. For this run the port was 9248:

```powershell
node scripts/diagnostics/validate_packaged_storage.cjs `
  http://127.0.0.1:9248 tmp/packaged-storage-480 `
  a447d6258348df2fc19f31c91585fc677bb616b7 .venv/Scripts/python.exe ui
```

The harness verifies the frozen runtime, build identity and all effective paths.
It does not launch the app. Existing `exercise` and `restart` modes are retained.
Raw artifacts remain local in `tmp/packaged-storage-480/`: `storage-ui.json`,
four `storage-ui-*.png` screenshots, build logs, bundle manifest, launch/cleanup
records, and protected-data preservation records. They are not runtime assets.

Final `storage-ui.json` SHA-256:
`50711a495a39d6ef33b0cc067913ab4be3b9e11c0a480ef4fe8ef385f425246e`.

## Limits

The partial terminal state and browser fallback were tested through component
regressions; the real packaged scenarios exercised success and locked-file failure.
No financial data ingestion, Excel workflow, target 8 GB resource test, updater,
or release gate was performed. #483-#485 remain owned by their separate execution.
Full Python/API regression coverage remains a PR CI check; no Python production
code changed here.

The harness disconnected after validation. Recorded test processes did not exit
within the five-second cleanup window and were force-stopped after checking their
exact executable paths. CDP port 9248 was released. Graceful shutdown remains
unvalidated, consistent with the earlier #479 observation; this fix does not
claim to resolve process shutdown.
