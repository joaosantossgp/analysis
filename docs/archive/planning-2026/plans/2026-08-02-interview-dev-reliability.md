# Interview Dev Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Windows desktop development shutdown deterministic and prevent synthetic `CVM_<id>` names from reaching active company UI payloads.

**Architecture:** Keep process ownership in `desktop/app.py`: one private helper stops only the `Popen` tree created for Vite. Keep company data immutable: normalize display identity at the shared read-service boundary only when a name is exactly the synthetic placeholder for its own CVM code.

**Tech Stack:** Python 3.11, pytest, subprocess, SQLite, SQLAlchemy, pywebview, Vite.

## Global Constraints

- Default dev remains `python -m desktop.app --dev` with `%USERPROFILE%\Documents\CVMAnalytics`.
- Do not modify Documents databases, snapshots, caches, financial rows, or source lineage.
- Do not use mock bridge data.
- Preserve non-placeholder company names exactly.
- Do not change frontend API contracts or add dependencies.
- Commit directly to `main`; no pull request.
- Tests must be written and observed failing before the production fix.

---

### Task 1: Stop the Windows Vite process tree

**Files:**
- Modify: `desktop/app.py:958-999, 1231-1235`
- Modify: `tests/test_desktop_runtime_paths.py`

**Interfaces:**
- Produces private helper `_stop_vite_dev_server(proc: subprocess.Popen[bytes] | None) -> None`.
- Consumes `_start_vite_dev_server()` parent `Popen` handle.
- Windows command must be exactly `taskkill /PID <proc.pid> /T /F`.

- [ ] **Step 1: Write failing tests**

Add tests that create `Mock(pid=4242)` and patch `app.os.name` plus `app.subprocess.run`:

```python
def test_stop_vite_dev_server_kills_windows_process_tree(monkeypatch) -> None:
    proc = Mock(pid=4242)
    monkeypatch.setattr(app.os, "name", "nt", raising=False)
    with patch.object(app.subprocess, "run") as run:
        app._stop_vite_dev_server(proc)
    run.assert_called_once_with(
        ["taskkill", "/PID", "4242", "/T", "/F"],
        check=False,
        stdout=app.subprocess.DEVNULL,
        stderr=app.subprocess.DEVNULL,
    )
    proc.terminate.assert_not_called()
```

Add a non-Windows test asserting `terminate()`, `wait(timeout=5)`, and `kill()` only after `subprocess.TimeoutExpired`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
pytest tests/test_desktop_runtime_paths.py -q
```

Expected: tests fail because `_stop_vite_dev_server` does not exist.

- [ ] **Step 3: Implement minimal cleanup helper**

Add `_stop_vite_dev_server` adjacent to `_start_vite_dev_server`. It returns immediately for `None`. On Windows call `subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)`. On other systems call `terminate()`, `wait(timeout=5)`, then `kill()` on `TimeoutExpired`. Catch `OSError`/`subprocess.SubprocessError` so already-exited cleanup cannot mask desktop shutdown.

Replace both direct `proc.terminate()` calls: startup timeout in `_start_vite_dev_server` and `main()` `finally` cleanup.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
pytest tests/test_desktop_runtime_paths.py -q
```

Expected: all runtime-path and Vite-lifecycle tests pass.

- [ ] **Step 5: Commit**

```powershell
git add desktop/app.py tests/test_desktop_runtime_paths.py
git commit -m "fix(desktop): stop vite process tree on shutdown"
```

### Task 2: Normalize synthetic company display names

**Files:**
- Modify: `src/financials/read_service_query.py:224-236, 449-477, 766-793`
- Modify: `tests/test_company_market_cap_sort.py`

**Interfaces:**
- Produces private helper `_is_synthetic_company_name(value: object, cd_cvm: int) -> bool`.
- The helper returns true only for case-insensitive, trimmed exact `CVM_<cd_cvm>`.
- Catalog identity is display-only fallback for that synthetic value.

- [ ] **Step 1: Write failing tests**

Extend `_FakeCatalog.lookup_company` to return the entry matching `cd_cvm`. Add a test that seeds company `25658` as `CVM_25658`, supplies catalog entry `AGROGALAXY PARTICIPAÇÕES S.A. - EM RECUPERAÇÃO JUDICIAL`, writes a matching `AGXY3.SA` snapshot row, and asserts both results use catalog identity:

```python
page = svc.list_companies(search="AGXY3", page=1, page_size=10)
assert page.items[0].company_name == expected_name
assert svc.get_company_info(25658).company_name == expected_name
```

Add a second assertion with a non-placeholder stored name (`"AgroGalaxy Legacy S.A."`) proving it remains unchanged even when catalog has a different name.

- [ ] **Step 2: Verify RED**

Run:

```powershell
pytest tests/test_company_market_cap_sort.py -q
```

Expected: placeholder-name test fails because list/detail return `CVM_25658`; preservation test may already pass.

- [ ] **Step 3: Implement minimal read-time normalization**

Add `_is_synthetic_company_name` in `CVMReadService`. In `_enrich_company_identity_fallback`, do not early-return merely because ticker/CNPJ exist when `company_name` is synthetic. Resolve identity and replace only synthetic `company_name` with `identity.company_name` when nonblank. Keep existing ticker/CNPJ fallback behavior.

In `_list_companies_with_market_cap_sort`, normalize each `item` through the same identity fallback before snapshot market-cap enrichment so directory and command-search payloads share behavior with `get_company_info`.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
pytest tests/test_company_market_cap_sort.py tests/test_backend_perf_optimizations.py -q
```

Expected: targeted tests pass; no existing market-cap ordering or bridge payload regression.

- [ ] **Step 5: Commit**

```powershell
git add src/financials/read_service_query.py tests/test_company_market_cap_sort.py
git commit -m "fix(companies): resolve synthetic company display names"
```

### Task 3: Validate live shared-data development mode

**Files:**
- No production changes.

**Interfaces:**
- Validates Tasks 1 and 2 using normal `python -m desktop.app --dev` and the existing Documents root.

- [ ] **Step 1: Run full automated checks**

```powershell
pytest tests -q
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run build
```

- [ ] **Step 2: Run Windows lifecycle check**

Close any existing desktop dev window normally. Start `python -m desktop.app --dev`; close its window; confirm no listeners remain on 5173 or 5174. Start it again and confirm it binds 5173, not a fallback port. Stop it cleanly.

- [ ] **Step 3: Run shared-data smoke check**

Start `python -m desktop.app --dev` with no `CVM_DATA_DIR` or `CVMANALYTICS_DATA_DIR` override. In the desktop UI, confirm Diagnostics reports the Documents root and read-only shared dev mode; search `AGXY3`, open CVM 25658, and confirm AgroGalaxy is displayed. Open Petrobras and confirm annual plus quarterly statement periods remain available. Do not invoke refresh, reset, import, export, or update actions.

- [ ] **Step 4: Commit documentation only if needed**

Do not commit generated files, test data, `.superpowers/`, Documents data, or build output. If no documentation changes are required, make no commit.

## Plan self-review

- Spec coverage: Task 1 covers Windows lifecycle; Task 2 covers placeholder identity; Task 3 covers all specified automated and manual validation.
- Scope: no data mutation, coverage expansion, mart rebuild, provider change, packaging work, or frontend API change.
- Test-first: Tasks 1 and 2 explicitly require RED before production edits.
- Placeholder scan: no unresolved implementation placeholders.
