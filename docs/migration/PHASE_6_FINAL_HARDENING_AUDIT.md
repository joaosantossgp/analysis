# Phase 6 Final Hardening Audit

This audit evaluates the packaged Windows desktop runtime of CVMAnalytics for performance, package size, cold start, stability, auto-updater behavior, logs/error handling, UI/UX consistency, and CI workflows.

---

## Current Runtime

*   **Version:** `0.17.0` (as configured in the working directory `desktop/__version__.py`).
*   **Packaged Architecture:** Python core + SQLite + pywebview/WebView2 + static Vite/React/TS frontend + PyInstaller.
*   **Process Model:** Completely Node-free. Starts with a single parent `CVMAnalytics.exe` process which launches WebView2 runtime child processes. No Next.js server or `node.exe` is packaged or run.
*   **User Data Location:** `%USERPROFILE%\Documents\CVMAnalytics`
    *   Database: `db\cvm_financials.db`
    *   Excel exports: `output\`
    *   Logs: `logs\refresh_runs.jsonl`, `recovery.log`
*   **Source-only / Hosted Surfaces (not packaged):**
    *   `apps/web/` (hosted Next.js marketing/legacy web app)
    *   `apps/api/` (hosted FastAPI service for pipelines)
    *   `railway.toml` (hosted platform configuration)

---

## Package Size / Contents

### Size Measurements
*   **ZIP Archive (`CVMAnalytics-windows-v0.17.0.zip`):** 45.82 MB (48,044,068 bytes)
*   **Extracted Directory (Total):** 92.97 MB (97,487,763 bytes)
*   **`CVMAnalytics.exe` Executable:** 19.58 MB (20,533,901 bytes)
*   **`_internal/` Folder:** 73.39 MB (76,953,862 bytes)
*   **`_internal/desktop-web/` (static Vite UI):** 2.19 MB (2,295,776 bytes)

### Size Distribution (Largest folders in `_internal/`)
1.  `numpy.libs/`: 20.02 MB
2.  `pandas/`: 16.58 MB
3.  `numpy/`: 5.87 MB
4.  `pydantic_core/`: 5.16 MB
5.  `desktop-web/`: 2.19 MB
6.  `webview/`: 1.16 MB

> [!NOTE]
> The v0.17.0 ZIP package size is 45.82 MB, compared to v0.15.0 at 38.54 MB. The increase is due to Python library upgrades (numpy 2.4.4, pydantic 2.12.5) and the inclusion of the GICS sector mapping CSV (`_internal/data/import/gics_mapping.csv` ~233 KB).

### Contents Verification
*   **Absence of Standalone Node/Next:** Verified that `node.exe`, `web_standalone/`, and Next standalone build outputs are completely absent.
*   **Absence of local database files:** Checked that no SQLite database file (`.db`) is present inside the package directory.
*   **Absence of raw data dumps:** No input ZIP files or bulk raw data dumps are inside the folder.
*   **Presence of runtime prerequisites:** Verified that `_internal/update_helper.ps1`, `gics_mapping.csv`, `pythonnet` binary DLLs, and required Python library modules are packaged correctly.

---

## Startup / Process / Memory

### Startup Speed
*   **Time to parent `CVMAnalytics.exe` process alive:** ~60 ms.
*   **Time to first WebView2 process spawned and window visible:** ~1508 ms.

### Process Counts & Memory Usage (Steady State)
*   **Total processes spawned:** 7 (1 root `CVMAnalytics.exe` + 6 child `msedgewebview2.exe` helper processes).
*   **Node.exe process count:** 0 (completely absent).
*   **Memory consumption (steady-state):** ~532.72 MB total tree memory.
    *   `CVMAnalytics.exe`: 180.58 MB RAM.
    *   WebView2 child processes: 352.14 MB RAM (sum of all 6 helpers).
*   **CPU Idle behavior:** 0% CPU consumption when not interacting. No background polling loops or memory leaks detected during smoke tests.

---

## Functional Smoke

The following features were verified against the compiled binary:
*   **`CVMAnalytics.exe --diagnose-runtime`:** Executed successfully. Correctly performs probes for .NET runtime, WebView2 runtime, pythonnet, and SQLite. Generates a clean log (`diagnostics-<timestamp>.log`) in the Documents folder.
*   **Companies Directory:** Debounced search, pagination, and GICS sector filtering are fully functional.
*   **Sectors and Sub-sector Detail Routes:** Browsing GICS sectors (`/setores`), detailed sub-sector views (`/setores/:sectorSlug/:subSectorSlug`), and filtering companies by sub-sector work correctly.
*   **Company Detail:** Renders the unified EntityHeader, company metadata, annual KPIs table, and launches single-company refresh requests.
*   **Financial Statements:** Correctly renders BPA, BPP, DRE, and DFC tabular layouts with expandable rows.
*   **Excel Export:** Full-workbook exports and statement-scoped exports (e.g., DRE only) run successfully. Excel files are written to `Documents/CVMAnalytics/output/` with duplicate-handling suffixes.
*   **Base updating ("Atualizar Base"):** Shows active and queued refresh status, diagnostic row counts, logs, and delta warnings.
*   **Status Page:** Displays paths, SQLite row counts, GitHub update availability, and the latest recent logs correctly.

---

## Updater Audit

### GitHub Discovery
*   Queries `api.github.com/repos/joaosantossgp/analisys/releases/latest` correctly.
*   Discovers tag version `v0.16.0` and parses target ZIP name `CVMAnalytics-windows-v0.16.0.zip` and SHA-256 sidecar file.

### update_helper.ps1 Verification
*   **Safety Contract:** Swaps are strictly limited to the allowlist (`CVMAnalytics.exe` and `_internal`).
*   **Deny-list protection:** Direct protection forbids modifying or deleting user-data directories (`data`, `output`, `logs`, `cache`, `tmp`, `backup`, `versions`, `update_rollback`) if they reside in the app directory.
*   **Backup & Rollback:** Automatically copies current install files to `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<utc-timestamp>\` prior to swapping.
*   **Data Integrity:** User data residing in `Documents/CVMAnalytics` remains completely untouched.

---

## Logs / Error Handling

*   **Files checked:**
    *   `Documents/CVMAnalytics/logs/refresh_runs.jsonl` (stores structured refresh run details)
    *   `Documents/CVMAnalytics/recovery.log` (logs DB migrations, GICS backfill stats, and unsupported CLI flag usage warnings)
    *   `%LOCALAPPDATA%\CVMAnalytics\update_error.log` (logs update swaps and file movements)
*   **Cleanliness:** Log files are highly readable, clear of tracebacks, and avoid excessive noise.
*   **UI Integration:** Errors (such as missing databases or refresh timeouts) are caught in the React SPA. They show informative text with path pointers instead of exposing raw Python tracebacks to the user.

---

## UI / UX Audit

*   **Consistency:** Page headers, EntityHeaders, breadcrumbs, loading skeletons, and empty states conform to `docs/skills/CVMANALYTICS_VITE_UI_SKILL.md`.
*   **Table Readability:** Tabular columns align correctly. Numbers are aligned to the right, text is aligned to the left, and monospace typography is enforced via Tailwind's `font-mono`.
*   **Discovered Polish Issues:**
    1.  **Cell Formatting Inconsistency:** The `formatKpiCell` function in `CompanyDetailPage.tsx` does not match the more robust formatter in `CompanyKpisPage.tsx`. Large financial values (>= 1M) are not scaled to `mn` abbreviations, ratio types do not append the `x` suffix, and the `bps` format type is not handled. (P1)
    2.  **Explicit Monospace Numbers styling:** моноspace fields do not declare `font-variant-numeric: tabular-nums` in `index.css` or route styles, which is a best practice to ensure perfect vertical column alignment across various system fonts. (P2)

---

## Documentation Audit

*   **Authoritative READMEs:** Both `README.md` and `apps/desktop-web/README.md` accurately state the current runtime architecture (Vite, Python, SQLite, no Node), persistent directory location (`Documents/CVMAnalytics`), and how to launch the build.
*   **Handoffs:** `docs/migration/NEXT_AGENT_HANDOFF.md` and `docs/migration/README.md` have been updated to reflect the completion of Phase 5B and the source-only retention decision of Phase 5C.
*   **Hygiene:** Stale planning documents from previous development iterations are deleted. No obsolete references remain.

---

## CI / Workflow Audit

*   **`ci.yml` (Success):** Checks Python core compilation, compiles desktop entry points (`app.py`, `bridge.py`), runs python test suites, and validates React/Vite typecheck and production builds.
*   **`release-desktop.yml` (Success):** Builds the executable bundle, enforces the flat-root ZIP constraint required by the updater contract, hashes the archive with SHA-256, and uploads assets directly to GitHub Releases.
*   **`perf-guardrails.yml` (Success):** Restricted to manual runs (`workflow_dispatch`), preventing legacy Next.js bundle sizing from blocking the desktop release cycle.
*   **`pr-issue-guardrails.yml` (Success):** Correctly gates PRs. The lane/risk constraints are bypassed for interactive commits and only enforced when the `flow:autonomous` label is present.

---

## Issues Found

| Severity | Area | Issue | Recommended Fix |
| :--- | :--- | :--- | :--- |
| **P1** | UI / UX | `CompanyDetailPage.tsx`'s `formatKpiCell` lacks scaling abbreviations (`mn`), ratio suffixes (`x`), and `bps` format type support. | Replace the cell formatter logic in `CompanyDetailPage.tsx` with the standardized logic from `CompanyKpisPage.tsx`. |
| **P1** | CLI | `--diagnose-runtime` triggers a blocking native Windows MessageBoxW which hangs in non-interactive/headless environments. | Print the diagnostics report directly to stdout, and only show the MessageBox if stdout is a TTY and no `--non-interactive` or `--headless` flag is passed. |
| **P2** | UI / UX | Monospace cells do not declare `font-variant-numeric: tabular-nums` globally. | Add a global styling rule for `.font-mono` or `table` inside `apps/desktop-web/src/index.css` to enforce tabular-nums. |
| **P2** | CI / Workflows | `perf-guardrails.yml` is kept for hosted Next.js performance testing, but the description doesn't explicitly mark it as obsolete for the desktop app. | Add a comment to the workflow description stating that it is obsolete for the desktop executable runtime but kept for source-only hosted web audits. |

---

## Proposed Phase 6B Fix List

We recommend executing these specific fixes in Phase 6B:
1.  **Standardize KPI Formatting:** Sync `formatKpiCell` inside `CompanyDetailPage.tsx` to inherit the robust scaling, suffixes (`mn`, `x`, `bps`), and unit representations from `CompanyKpisPage.tsx`.
2.  **Add Non-Blocking `--diagnose-runtime` Fallback:** Modify `_run_diagnostic_mode()` and `_show_fatal_messagebox` in `desktop/app.py` to check if the session is non-interactive or redirected. Skip the Windows MessageBox if stdin/stdout are not connected to a console, printing the log output directly to the console instead.
3.  **Global Tabular Numbers Styling:** Update `apps/desktop-web/src/index.css` to define:
    ```css
    .font-mono {
      font-variant-numeric: tabular-nums;
    }
    ```
4.  **Polish Workflow Comments:** Update the header in `.github/workflows/perf-guardrails.yml` to clearly state that Next.js performance checks are legacy and have no impact on the shipped desktop executable.

---

## Release Readiness

*   **Status:** **ready for stable after minor fixes**
*   **Blockers:** None. No P0 blockers were identified. The current runtime is functional and ready for stable compilation once the P1 polish list is executed.

---

## Recommendation

Proceed immediately to **Phase 6B (Fixes)** to resolve the cell formatting, non-interactive CLI diagnostics, and tabular-nums styling issues.
