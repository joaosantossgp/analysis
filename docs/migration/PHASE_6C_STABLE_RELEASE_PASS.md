# Phase 6C Stable Release / Final Product Pass

## Current Runtime
The desktop application is built with a lightweight, local-first runtime containing no Node or Next.js servers in production:
*   **Backend / Processing Core:** Python with standard library utilities.
*   **Database:** SQLite (`cvm_financials.db`).
*   **Webview Host:** pywebview hosting Microsoft Edge WebView2.
*   **Frontend UI:** Static Vite SPA (React + TypeScript).
*   **Packaging:** PyInstaller (producing `CVMAnalytics.exe` and its `_internal/` dependency tree).
*   **User Data Location:** `%USERPROFILE%\Documents\CVMAnalytics` (database, exports, and logs).

## Latest Release
*   **Tag:** `v0.17.0`
*   **Release URL:** https://github.com/joaosantossgp/analisys/releases/tag/v0.17.0
*   **Status:** Validated, finalized, and recommended for stable release.

## GitHub Download Validation
The published release assets for version `v0.17.0` were retrieved from GitHub and audited:
*   **Release ZIP:** `CVMAnalytics-windows-v0.17.0.zip`
*   **SHA-256 Sidecar:** `CVMAnalytics-windows-v0.17.0.zip.sha256`
*   **SHA-256 Verification:** `6a8717972c3b5d0f4ce44c8955a04ea866bf6e669aa6e368e04ce84e3fd5a3ae` (matches sidecar exactly).
*   **Root Layout Structure:** Verified a clean flat root:
    *   `CVMAnalytics.exe` (Main entry executable, 19.58 MB)
    *   `_internal/` (All runtime dependencies, DLLs, and site-packages)
*   **Absence of Legacy Runtimes:**
    *   Confirmed `_internal/node.exe` is **absent**.
    *   Confirmed `_internal/web_standalone/` is **absent**.
*   **Presence of Vite Assets:**
    *   Confirmed `_internal/desktop-web/` containing static Vite SPA assets is **present**.
*   **Diagnostic CLI Execution:**
    *   Executed: `.\CVMAnalytics.exe --diagnose-runtime --non-interactive | Out-String`
    *   Verified exit code: `0` (clean exit).
    *   Verified stdout output containing system diagnostics, file system checks, and dependency validations.
    *   Confirmed zero GUI popups or blocking native Windows `MessageBox` prompts were generated under `--non-interactive` mode.
    *   Confirmed diagnostic log was successfully written to the Documents directory.

## Functional Smoke
The following core capabilities were smoke-tested using the validated `v0.17.0` binary:
1.  **Companies Directory:** Search filtering, pagination, and Sector filtering operate smoothly.
2.  **Company Detail:** Unified `EntityHeader` displays company information correctly.
3.  **Financial Statements:** Expandable BPA, BPP, DRE, and DFC tabular layouts load database records correctly.
4.  **KPIs / Charts:** Standarized cell format scaling (`mn`, `x`, `bps`) renders correctly. Trend charts load with null-handling gaps and clean mouse-hover tooltips.
5.  **Update Base:** Database health diagnostics, row metrics, and the refresh dispatch run cleanly.
6.  **Sectors / Sub-sectors:** Sector listings, sector details, and sub-sector detail pages (incorporating ROE/margin tables) populate correctly.
7.  **Excel Export:** Full-workbook exports and statement-only exports write successfully to `Documents/CVMAnalytics/output/`.
8.  **Status / Diagnostics:** Diagnostics dashboard, version/mode flags, SQLite row counts, recent logs view, and directory probes are verified.
9.  **Software Update Status:** Polling GitHub release endpoint reports version parity without issues.

## Updater Validation
*   **Discovery:** The app correctly parses the latest release JSON metadata from GitHub's Releases API.
*   **Sidecar Verification:** The ZIP signature and SHA-256 sidecars map exactly to expectations.
*   **Helper Script Alignment:** `desktop/update_helper.ps1` maintains standard allowlist constraints: only files matching the binary (`CVMAnalytics.exe`) and dependency folder (`_internal/`) are overwritten.
*   **Rollback Safety:** Rollbacks to `%LOCALAPPDATA%\CVMAnalytics\update_rollback\<timestamp>\` function correctly before any overwrite.
*   **User Data Preservation:** The updater does not touch `%USERPROFILE%\Documents\CVMAnalytics`.

## README / Docs Review
*   **Project README.md:** Updated to state that the static Vite SPA is the authoritative, only packaged UI runtime. References to legacy Next fallback modes (`--legacy`) have been updated to note they are unsupported and gracefully proceed directly into the Vite UI.
*   **apps/desktop-web/README.md:** Standardized to reference the stable `v0.17.0` release. Deleted legacy `v0.15.0` transitional references.
*   **Docs Consistency:** Checked `docs/migration/README.md` and `docs/migration/NEXT_AGENT_HANDOFF.md`, and updated the migration tables to mark Phase 6 as complete.

## GitHub About Review
Applied direct repository metadata updates using the `gh` command-line tool:
*   **Description:** `"Local-first Windows desktop financial data tool for Brazilian public companies, built with Python, SQLite, pywebview, and Vite."`
*   **Topics:** Added the topic `vite` to the repository topics list, maintaining other tags like `python`, `sqlite`, `pywebview`, `brazilian-market`, `cvm`, `equity-research`, and `desktop-app`.

## Release Notes Review
Reviewed and validated the published `v0.17.0` release notes on GitHub:
*   Includes detailed descriptions of the stable Node-free architecture.
*   Clearly documents user data safety under `%USERPROFILE%\Documents\CVMAnalytics`.
*   Records Excel export features (full + per-statement), diagnostics improvements (non-blocking CLI), standardized KPI formatting, and vertical number alignments.

## Stable Release Decision
*   **Decision:** Accept `v0.17.0` as the official stable release.
*   **Rationale:** All Phase 6A/6B hardening fixes are fully packaged in this build. No regressions or blocking runtime issues were identified during download validation or functional smoke testing. Rebuilding a new version (`v0.18.0` or `v1.0.0`) is unnecessary and unjustified.

## Remaining Non-Blocking Items
*   **Code Signing:** The packaged executable is currently unsigned. Users will receive standard Windows Defender SmartScreen warning prompts on fresh downloads. (Expected for local, open-source utilities).
*   **Antivirus False Positives:** Standard warning regarding potential heuristics-based AV flags on PyInstaller-packaged executables.

## Recommendation
Declare Phase 6 complete and promote `v0.17.0` as the stable production-ready release of CVMAnalytics. No further development or packaging iterations are required for the current migration scope.
