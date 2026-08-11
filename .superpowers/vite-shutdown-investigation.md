# Vite dev-server shutdown investigation

## Scope and evidence

- Investigated only; no application source was changed.
- Current implementation: `desktop/app.py:958-999` starts Vite with `subprocess.Popen(["npm.cmd", "run", "dev", ...])` on Windows. The `package.json` `dev` script is simply `vite`.
- `main()` retains that `Popen` handle in `server_proc` (`desktop/app.py:1171-1175`) and, after `webview.start()` returns when the window closes, calls only `server_proc.terminate()` (`desktop/app.py:1229-1234`). It neither waits for nor kills a process tree.
- The startup-timeout branch has the same parent-only `proc.terminate()` (`desktop/app.py:993-998`).
- There are no tests for `_start_vite_dev_server`, its shutdown path, or `main()`'s Vite lifecycle. `tests/test_desktop_runtime_paths.py` tests data-path setup only. `scripts/diagnostics/phase1_pywebview_smoke.py:179-233` duplicates the same `npm.cmd` plus parent-only terminate pattern.

## Root cause

On Windows, the stored PID is the `npm.cmd`/command-shell process. `npm run dev` launches Node/Vite as descendant processes. `Popen.terminate()` terminates only the direct process; it does not terminate descendants. Therefore the Vite `node.exe` listener survives after pywebview closes, retains its selected port (normally 5173), and becomes orphaned. The next desktop launch may select 5174+ because `_first_free_vite_dev_port()` treats the orphan listener as occupied.

The shutdown `finally` does run, so this is not a missed pywebview-close callback; it is insufficient Windows subprocess cleanup. The startup failure branch has the same defect if Vite spawns but the readiness check times out.

## Minimal fix (proposed, not implemented)

Add one small private helper in `desktop/app.py`, e.g. `_stop_vite_dev_server(proc)`, and call it from both cleanup sites instead of direct `terminate()`:

- Windows: run `taskkill /PID <proc.pid> /T /F` with output suppressed. `/T` kills the still-attached npm/Node/Vite process tree; it must run *instead of* first terminating the npm parent, otherwise the Vite child can already have been orphaned.
- Non-Windows: retain the current graceful `terminate()`, `wait(timeout=...)`, then `kill()` fallback pattern.
- Make cleanup idempotent and tolerate an already-exited process; do not target a port or generic `node.exe`, only the Popen-owned process tree.

`CREATE_NEW_PROCESS_GROUP` alone is not the preferred minimal repair: it does not by itself terminate a child tree, and signal forwarding through `npm.cmd`/npm is less deterministic than `taskkill /T`.

The diagnostic smoke script is a separate caller with the same leak. It should be aligned in a follow-up or use the shared helper only if that does not create an undesirable scripts-to-runtime dependency.

## Exact reproduction / validation plan

Manual Windows regression (use an isolated data root):

1. In PowerShell, first check that 5173-5199 are free:
   `Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5173..5199 }`
2. Set an isolated root and launch the desktop dev shell:
   `$env:CVMANALYTICS_DATA_DIR = Join-Path $env:TEMP 'CVMAnalytics-vite-shutdown-test'`
   `python -m desktop.app --dev`
3. After the window loads, close it through the normal window close control (not Ctrl+C).
4. Poll for up to 5 seconds:
   `Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5173..5199 }`
   Expected after the fix: no rows. Before the fix: a `node.exe` listener remains, usually on 5173.
5. If a row remains during reproduction, inspect its command line to prove it is Vite and then clean up its tree:
   `$pid = <OwningProcess>; Get-CimInstance Win32_Process -Filter "ProcessId=$pid" | Select-Object ProcessId,ParentProcessId,CommandLine`
   `taskkill /PID $pid /T /F`
6. Relaunch `python -m desktop.app --dev`; expected: it binds 5173 again, rather than silently moving to a higher port.

Automated regression test to add:

- Unit-test the new stop helper with a fake `Popen` PID on Windows, asserting one `taskkill /PID <pid> /T /F` invocation and that normal cleanup does not call parent-only `terminate()` first. Test the non-Windows terminate/wait/kill fallback separately.
- Add a Windows-only integration test that invokes `_start_vite_dev_server()`, captures the port from its returned URL, verifies `_port_open(port)`, calls the helper, then polls `_port_open(port)` until false. Its fixture must call the helper in `finally` to avoid test pollution. This exercises the real `npm.cmd -> Node -> Vite` tree, which a mock cannot prove.
- Run `pytest tests/test_desktop_runtime_paths.py <new Vite lifecycle test>` and the manual close-window check above. No desktop-web typecheck is needed if the fix remains Python-only.

## Files implicated

- `desktop/app.py` — root cause and primary fix location.
- `tests/test_desktop_runtime_paths.py` or a focused new `tests/test_desktop_vite_lifecycle.py` — missing coverage.
- `scripts/diagnostics/phase1_pywebview_smoke.py` — same cleanup antipattern; follow-up scope.
