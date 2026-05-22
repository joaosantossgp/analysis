# Phase 3 - Functional Parity Matrix

Status: Phase 3A shipped in `v0.5.0` (financial statements). Phase 3B
shipped in `v0.6.0` and was accepted in `v0.6.1` (Update Base + DB
diagnostics + post-job delta). Phase 3C shipped in `v0.7.0`: 3C.0
standardised the persistent runtime data root at
`%USERPROFILE%\Documents\CVMAnalytics` with WAL-safe migration from the
legacy `%LOCALAPPDATA%\CVMAnalytics` location, and 3C.1 added the Vite
Indicadores screen at `/empresas/:cdCvm/indicadores`. Phase 3D ships in
`v0.8.0`: Vite company directory gains sector filter + URL-driven
filter chips + result count + reset, and new routes `/setores` and
`/setores/:slug` provide GICS sector browsing and per-sector company
tables (no invented aggregate KPIs — only counts, coverage, and the
company list backed by `CVMBridge.get_sectors` /
`get_sector_detail`). Phase 3E ships in `v0.9.0`: full company
workbook Excel export available from company detail, financial
statements, and indicadores screens. Writes to the persistent
`Documents/CVMAnalytics/output/` folder via two new bridge methods
(`export_company_excel`, `get_output_dir`); the legacy
`save_company_excel` (which writes to `~/Downloads`) is left in
place for the Next UI. Phase 3F ships in `v0.10.0`: company detail
now has single-company refresh controls with status/freshness display,
polling, and success/error feedback, using existing
`request_refresh` / `get_refresh_status` bridge methods. The default
runtime is still Next/Node. Phase 3G ships in `v0.11.0`: Vite gains
`/status`, a compact app status / updater check / diagnostics screen
showing runtime version/mode, bridge status, local data paths, SQLite
counts, latest GitHub release status, compact logs, and runtime probes.
It adds narrow bridge methods `get_app_status` and `open_status_path`;
software update application remains intentionally unsupported in Vite.

Scope of this document:

- Compare the current Next UI (`apps/web`) with the Vite SPA (`apps/desktop-web`).
- Identify P0 gaps before Vite can become the default desktop runtime.
- Record incremental P0 parity slices ported into Vite.
- Keep legacy deletion out of scope. Phase 3 deletion still requires explicit
  approval after parity, a default-Vite soak release, and updater safety checks.

## Parity Table

| Feature / Route | Current Next implementation | Current Vite status | Data / bridge methods needed | Priority | Complexity | Risk | Recommended action |
|---|---|---|---|---|---|---|---|
| Home / dashboard (`/`) | Marketing-style home with company search hero, trust strip, and feature grid. Desktop mode uses `HomeDesktopLoader`. | Vite root is the company directory, not a home dashboard. | `get_companies`, `get_company_suggestions`, `get_populares`, `get_em_destaque`, `get_health` if home stats are restored. | P1 | Medium | Low | Defer. Directory-first startup is acceptable for the experimental runtime; polish later. |
| Company directory (`/empresas`) | Search, sector filter, pagination, card/list modes, loading/error states, desktop bridge loader. | **Phase 3D (v0.8.0)**: debounced search by name/ticker/CVM code, GICS sector filter, URL-driven `?search=&sector=&page=`, filter chips with per-filter clear, reset action, result count, empty/filtered-empty/error/loading/browser states, dense table with company / ticker / CVM / sector / sub-industry / years / rows / data dot. Card/list toggle still missing (Next-only). | Existing `get_companies`, new `get_company_filters` facade. | P0 | Medium | Medium | Card/list mode optional before default switch. |
| Company detail overview (`/empresas/[cd_cvm]?aba=visao-geral`) | Header, company metadata, year selector, annual KPI overview, freshness/download controls, request-refresh controls. | **Phase 3F (v0.10.0)**: implemented route `/empresas/:cdCvm` with header, annual KPI table, full-company Excel export, and single-company refresh panel. The panel surfaces backend freshness/status fields (`tracking_state`, `freshness_summary_*`, attempt timestamps, readable-year fields, progress/ETA when present), starts an on-demand company refresh, polls active jobs every 2s, and invalidates company queries when refresh finishes. Richer KPI cards/charts remain Next-only. | Existing `get_company_info`, `get_company_years`, `get_company_kpis`, `get_refresh_status`, `request_refresh`, `export_company_excel`, `get_output_dir`. | P0 | Medium | Medium | Detail controls done for this slice; KPI chart parity can follow. |
| Financial statements (`/empresas/[cd_cvm]?aba=demonstracoes&stmt=...`) | Statement tab with DRE/BPA/BPP/DFC selector, row filter, sticky account column, compact money formatting, empty/error states. | Implemented in Phase 3A as `/empresas/:cdCvm/demonstrativos?stmt=DRE`. Uses DRE/BPA/BPP/DFC selector, row filter, loading/error/empty states, real data table. | Existing `get_company_statement`, plus existing company info/year methods. | P0 | Medium | Medium | Done for first parity slice. Later add manual year selection if needed. |
| KPIs / indicators | Annual and quarterly KPI bundle available; Next overview uses KPI cards/tables and chart panels. | **Implemented in Phase 3C.1 (v0.7.0)** at `/empresas/:cdCvm/indicadores`: year multi-select with "Last 5" / "All" presets, KPI summary cards (Receita líquida, EBITDA, Lucro líquido, Margem líquida) for latest selected year, annual table + quarterly table with categoria/unidade columns, unit-aware formatting (R$ mn / % / x / bps), missing values rendered as em dash. | Existing `get_company_kpis`, `get_company_years`. | P0 | Medium | Medium | Done for parity slice. Add chart panels in a later iteration. |
| Sectors directory (`/setores`) | GICS sector/sub-sector directory with counts, snapshots, company previews, empty/error states. | **Phase 3D (v0.8.0)**: implemented at `/setores`. GICS sector vs sub-industry tab (`?visao=sub_sector`), company count + latest year columns, sub-industry count, link to filtered companies directory and to sector detail. No invented aggregate metrics — snapshot fields are present on the DTO but not surfaced unless future copy clarifies meaning. | Existing `get_sectors`. | P0 | Medium | Medium | Done for parity slice. |
| Sector detail (`/setores/[slug]`, `/setores/[slug]/[sub_slug]`) | Year selector, aggregate KPIs, yearly overview, company table, breadcrumbs. | **Phase 3D (v0.8.0)**: implemented at `/setores/:slug`. Breadcrumb, company count + base-year header, year selector (`?ano=`), in-sector company search (`?q=`), company table with name / ticker / CVM / sub-industry, links to company detail and to the directory filtered by sector. Sub-sector detail route (`/setores/[slug]/[sub_slug]`) not yet ported — Next still serves it. | Existing `get_sector_detail`; `get_sub_sector_detail` still on Next. | P0 | Medium | Medium | Sub-sector detail can be a follow-up slice. |
| Update base / refresh data (`/atualizar-base`) | Administrative refresh dashboard: base health, scopes, filters, job progress, history, cancel flow. | **Implemented (v0.6.1 accepted).** v0.7.0 adds the Documents data root and `data_root` field in the diagnostics panel. | Existing `get_base_health`, `request_refresh`, `cancel_refresh`, `get_refresh_status`; new `get_database_diagnostics`. | P0 | High | High | Done. Operator filters (sector / status) can be added later. |
| Single-company refresh controls | Next company detail can request a period refresh and show progress. | **Phase 3F (v0.10.0)**: Vite company detail uses the existing bridge `request_refresh({ cd_cvm })` single-company path and `get_refresh_status({ cd_cvm })` for polling. No new Python bridge methods, no schema changes, no direct SQLite reads from frontend. | Existing `request_refresh`, `get_refresh_status`; existing `RefreshStatusDTO` / `RefreshDispatchDTO`. | P0 | Medium | High | Done for parity slice; keep an eye on real-world stalled-job messaging. |
| Excel export / save flows | Next has Excel export/download button and desktop bridge save/download path (writes to `~/Downloads`). | **Phase 3E (v0.9.0)**: full company workbook export from `/empresas/:cdCvm`, `/empresas/:cdCvm/demonstrativos`, and `/empresas/:cdCvm/indicadores`. Reusable `ExportCompanyButton` with idle/running/success/error/unsupported states, shows destination path, file name, file size, and collision-safe suffix. Writes to `Documents/CVMAnalytics/output/`. Per-statement export not yet supported (backend emits one workbook per company). | New bridge `export_company_excel`, `get_output_dir`. Existing `build_company_excel_export`. | P0 | Medium | Medium | Done for parity slice. |
| Software update check UI | Next shows floating update prompt through `check_update` / `apply_update`; local snooze only. | **Phase 3G (v0.11.0) partial:** `/status` checks GitHub Releases, shows current/latest version, update-available/up-to-date/check-failed state, release link, checked-at timestamp, and clear offline/failure copy. It intentionally does **not** apply updates from Vite. | New `get_app_status` backed by `UpdateChecker.get_latest_release_status`; existing `check_update` / `apply_update` / `snooze_update` / `get_update_progress` unchanged. | P0 | Medium | High | Status/check done. If default switch requires an active update prompt, install/apply/progress parity is still a follow-up. |
| App status / diagnostics (`/status`) | No dedicated production settings/status page found; status is split between health and update prompt. | **Phase 3G (v0.11.0): implemented.** Compact dashboard with runtime card, local data paths, database card, software update card, recent warnings/logs, and runtime diagnostics. Validated from GitHub-downloaded Vite asset in browser fallback and through packaged `--vite` launch + direct bridge status call. | New `get_app_status`, new `open_status_path`; existing `get_database_diagnostics` extended with latest report year/period and refresh error count. | P0 | Medium | Medium | Done for diagnostics/check slice. Keep `/status` focused; do not turn it into broad settings. |
| Data path visibility | Next surfaces some data/update context but no compact local path inventory. | **Phase 3G (v0.11.0): implemented.** Shows data root, DB path, output, logs, and cache path, with copy buttons and safe symbolic folder-open actions in desktop mode. Browser preview shows unsupported/fallback states. | New `get_app_status`, `open_status_path`; existing `get_output_dir` still used by export flows. | P0 | Low | Low | Done. |
| Runtime diagnostics | CLI `--diagnose-runtime` writes a local log and opens Notepad. No Vite summary screen. | **Phase 3G (v0.11.0): implemented as summary.** Shows .NET Framework, WebView2, pythonnet, SQLite, DB path, data root, and compact errors/warnings. It does not dump environment details or full logs. | New `get_app_status` reuses existing runtime probe helpers from `desktop/app.py` and SQLite/pythonnet checks. | P0 | Medium | Medium | Done as compact UI summary; full `--diagnose-runtime` remains available. |
| Health / status (`/health`) | API/desktop health indicator and route-level problem states. | Implemented as `/health` with bridge health payload; `/status` now carries the richer diagnostics surface. | Existing `get_health`; new `get_app_status` for Phase 3G. | P1 | Low | Low | Done enough; keep `/health` as lightweight bridge health. |
| Settings / about | No dedicated production settings route found; status is mostly health/update prompt. | No dedicated settings/about route. | `get_health`, updater methods if added. | P2 | Low | Low | Defer unless user asks. |
| Search behavior | Home suggestions, company directory search, company suggestions in update-base. | Directory search only. | Existing `get_companies`, `get_company_suggestions`. | P0 | Medium | Medium | Add suggestions where needed with update/export flows. |
| Filter/sort behavior | Directory sector filter, update-base status/range filters, statements row filter. | Directory search only; statements row filter added in Phase 3A. | Existing filter methods. | P0 | Medium | Medium | Add per-screen filters as each route is ported. |
| Navigation patterns | Site header, route tabs, URL search params for tabs/years/statements, breadcrumbs. | Simple nav plus company links. Statements route uses query param `stmt`. | No new data. | P0 | Medium | Low | Add cohesive Vite navigation before default switch. |
| Loading/error/empty states | Route loading/error files, skeletons, `ApiUnavailableState`, empty cards. | Basic states for health, directory, detail; statements has loading/error/empty/filter-empty. | No new data. | P0 | Medium | Medium | Standardize reusable Vite state components after more screens exist. |
| Modals/dialogs/actions | Update confirmation modal, update prompt modal, refresh actions, export action feedback. | Refresh and export action feedback exist for the Vite company/detail flows. Updater prompt/confirmation remains missing. | Refresh, export, and updater bridge methods. | P0 | Medium | High | Port updater action surface next; avoid broad modal framework work. |
| Browser/dev fallback | Next falls back to HTTP/API routes outside desktop mode. | Vite API facades return clear browser-mode banners when pywebview bridge is unavailable. | No new data. | P1 | Low | Low | Keep pattern. |

## Already Done In Vite

- Static Vite SPA bundled and launchable with `CVMAnalytics.exe --vite`.
- Bridge readiness and typed adapter.
- Health route.
- Company directory with search and pagination.
- Company detail route with header and annual KPI table.
- Phase 3A: company financial statements screen at
  `/empresas/:cdCvm/demonstrativos?stmt=DRE`.
- Phase 3B: Update Base / Refresh Data screen at `/atualizar-base`, including
  guarded background refresh jobs, optional CVM-code targeting, and
  empty-runtime-DB guidance.
- Phase 3C.1: KPI/Indicadores route at `/empresas/:cdCvm/indicadores`.
- Phase 3D: company directory filters (search/sector/URL chips/reset), GICS
  sectors directory at `/setores`, sector detail at `/setores/:slug`.
- Phase 3E: full company workbook Excel export from company detail,
  statements, and indicadores screens, writing into
  `Documents/CVMAnalytics/output/` via new narrow bridge methods.
- Phase 3F: single-company refresh controls on `/empresas/:cdCvm`, with
  status/freshness display, 2s active polling, dispatch feedback, and
  query invalidation after terminal status.
- Phase 3G: app status / diagnostics screen at `/status`, with runtime
  version/mode, bridge state, local data paths, SQLite counts, GitHub
  release check, compact logs, and runtime probe summary.

## Remaining P0 Before Vite Can Become Default

- Complete KPI/indicator parity beyond the annual table (chart panels).
- Sub-sector detail route at `/setores/:slug/:sub_slug` (Phase 3D ported the
  top-level sector detail; sub-sector remains on Next).
- Per-statement Excel export (currently the backend only emits a full company
  workbook; Vite exposes that scope clearly but cannot scope to DRE/BPA/etc.
  without a backend addition).
- Update-base advanced filters/suggestions beyond the constrained Vite refresh
  action, if required before the default switch.
- Update prompt/apply/progress parity if the default-Vite switch requires the
  legacy floating software update prompt behavior; Phase 3G only implements
  non-destructive update status/check.
- GitHub-downloaded release validation after each runtime parity slice.

## Remaining Before Legacy Deletion

- All P0 features above are complete and validated in `--vite`.
- A release ships with Vite as the default while Next remains available as a
  fallback.
- That default-Vite release soaks on real machines.
- Phase 0 updater/user-data/MOTW contract is revalidated.
- User explicitly approves deleting Next, Node, FastAPI, and related bundle
  entries.

## Phase 3A Implemented Screen

Selected screen: company financial statements.

Why this screen:

- High user value: account-level DRE/BPA/BPP/DFC data is core to financial
  analysis.
- Existing bridge support: `get_company_statement` already exposes the required
  data.
- Narrow scope: read-only, no schema changes, no Python pipeline changes.
- Strong parity proof: exercises large tabular financial data, statement type
  switching, filtering, and value formatting inside Vite.

## Phase 3B Implemented Screen

Selected screen: Update Base / Refresh Data.

Why this screen:

- P0 parity: users with an empty `%LOCALAPPDATA%\CVMAnalytics` runtime DB need a
  Vite path to populate local data.
- Existing bridge support: `get_base_health`, `request_refresh`,
  `get_refresh_status`, and `cancel_refresh` already expose the required job
  lifecycle.
- Proves long-running local Python jobs in the Vite runtime without making Vite
  default or touching updater/user-data migration contracts.

## Phase 3D Implemented Screens

Selected screens: company directory filters + `/setores` + `/setores/:slug`.

Why these slices:

- High navigational value: sector filtering and sector browsing are core to
  analytical workflows in the legacy Next UI.
- Existing bridge support: `get_company_filters`, `get_sectors`, and
  `get_sector_detail` are already exposed by `CVMBridge` and backed by
  `CVMReadService` aggregation — no Python pipeline changes required.
- Narrow scope: read-only, no schema changes, no new bridge methods.
- Strong parity proof: exercises GICS classification, sector-scoped company
  queries, and URL-driven filter persistence inside Vite.

## Phase 3E Implemented Surface

Selected surface: full-company Excel export, available from company
detail, financial statements, and indicadores screens.

Why this slice:

- High user value: closes the most-requested export workflow without
  forcing users back to the Next UI.
- Existing backend: `CVMReadService.build_company_excel_export` already
  emits a complete `.xlsx` (DRE/BPA/BPP/DFC plus DVA/DMPL when present
  and the quarterly KPI bundle). No `excel_exporter.py` changes.
- Narrow new bridge surface: `export_company_excel` writes into
  `<settings.output_dir>/` (which resolves to
  `Documents/CVMAnalytics/output/` in packaged mode) and returns
  `{ok, file_path, file_name, output_dir, size_bytes, revealed,
  error?}`. `get_output_dir` exposes the destination path for the UI.
- Collision-safe: existing files are never overwritten; the bridge
  appends `(1)`, `(2)`, ... to the file stem.
- Persistent: exports land in the user-data root protected by the
  Phase 0 updater allowlist, so updates never delete them.

## Phase 3F Implemented Surface

Selected surface: single-company refresh controls on company detail.

Why this slice:

- High user value: a user can refresh the company they are already
  inspecting without moving back to the global Update Base screen.
- Existing backend: `CVMBridge.request_refresh` already routes
  `{cd_cvm}` with no batch signals to `CVMReadService.request_company_refresh`,
  and `get_refresh_status({cd_cvm})` already returns `RefreshStatusDTO`
  rows from `company_refresh_status`.
- Narrow frontend surface: one typed facade, one reusable panel, and the
  existing company detail route mount. No Python method, schema, updater,
  migration, or pipeline change was required.
- Real freshness only: the UI displays backend-provided status and freshness
  fields (`tracking_state`, `freshness_summary_*`, `read_availability_*`,
  attempt timestamps, progress fields, ETA fields) and does not fabricate
  data age metrics.
- Refresh-safe query behavior: active company refreshes poll every 2s and
  invalidate company info, years, KPIs, statements, and directory queries
  after the active status becomes terminal.

## Phase 3G Implemented Surface

Selected surface: app status / updater check / diagnostics UI.

Why this slice:

- Pre-default operational need: users need a Vite-native way to understand the
  local desktop state without using a terminal.
- Existing backend surface: Vite can reuse local settings paths, SQLite
  diagnostics, updater constants, and runtime probe helpers without changing
  the updater staging contract or data pipeline.
- Narrow bridge additions: `get_app_status` composes runtime status, paths,
  database counts, non-destructive GitHub release check, compact logs, and
  diagnostics. `open_status_path` accepts only symbolic path kinds and never
  opens arbitrary frontend-provided paths.
- Clear updater boundary: software update status/check is visible, but applying
  an update from Vite is intentionally not enabled. The screen explicitly
  distinguishes app releases from Atualizar Base data refresh.
- GitHub-downloaded validation: `v0.11.0` release ZIP was downloaded, SHA-256
  validated, flat root confirmed, default/Vite modes launched, and updater
  helper sandbox swap preserved user-data directories.

## Recommended Next Screen

Recommended next narrow slices: KPI chart parity, the sub-sector detail
route, per-statement Excel export scope if the backend is extended, and
an explicit update prompt/apply/progress decision before making Vite the
default. Do not delete legacy code or make Vite default yet.
