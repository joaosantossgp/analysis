# Phase 3A - Functional Parity Matrix

Status: Phase 3A started after `v0.4.0` validated the experimental `--vite`
runtime from a downloaded GitHub Release artifact.

Scope of this document:

- Compare the current Next UI (`apps/web`) with the Vite SPA (`apps/desktop-web`).
- Identify P0 gaps before Vite can become the default desktop runtime.
- Record the first missing screen ported in Phase 3A: company financial
  statements.
- Keep legacy deletion out of scope. Phase 3 deletion still requires explicit
  approval after parity, a default-Vite soak release, and updater safety checks.

## Parity Table

| Feature / Route | Current Next implementation | Current Vite status | Data / bridge methods needed | Priority | Complexity | Risk | Recommended action |
|---|---|---|---|---|---|---|---|
| Home / dashboard (`/`) | Marketing-style home with company search hero, trust strip, and feature grid. Desktop mode uses `HomeDesktopLoader`. | Vite root is the company directory, not a home dashboard. | `get_companies`, `get_company_suggestions`, `get_populares`, `get_em_destaque`, `get_health` if home stats are restored. | P1 | Medium | Low | Defer. Directory-first startup is acceptable for the experimental runtime; polish later. |
| Company directory (`/empresas`) | Search, sector filter, pagination, card/list modes, loading/error states, desktop bridge loader. | Implemented as Vite root with debounced search and pagination. Sector filters and card/list mode are missing. | Existing `get_companies`; optional `get_company_filters`. | P0 | Medium | Medium | Add sector filters and view parity before default switch. |
| Company detail overview (`/empresas/[cd_cvm]?aba=visao-geral`) | Header, company metadata, year selector, annual KPI overview, freshness/download controls, request-refresh controls. | Implemented route `/empresas/:cdCvm` with header and annual KPI table. Missing freshness/download/request-refresh controls and richer KPI cards/charts. | Existing `get_company_info`, `get_company_years`, `get_company_kpis`, `get_refresh_status`, `request_refresh`. | P0 | Medium | Medium | Complete controls after statements and export. |
| Financial statements (`/empresas/[cd_cvm]?aba=demonstracoes&stmt=...`) | Statement tab with DRE/BPA/BPP/DFC selector, row filter, sticky account column, compact money formatting, empty/error states. | Implemented in Phase 3A as `/empresas/:cdCvm/demonstrativos?stmt=DRE`. Uses DRE/BPA/BPP/DFC selector, row filter, loading/error/empty states, real data table. | Existing `get_company_statement`, plus existing company info/year methods. | P0 | Medium | Medium | Done for first parity slice. Later add manual year selection if needed. |
| KPIs / indicators | Annual and quarterly KPI bundle available; Next overview uses KPI cards/tables and chart panels. | Partial: annual KPI table only. No quarterly view or chart panel. | Existing `get_company_kpis`. | P0 | Medium | Medium | Add complete annual/quarterly indicator screen after export or sectors. |
| Sectors directory (`/setores`) | GICS sector/sub-sector directory with counts, snapshots, company previews, empty/error states. | Missing. | Existing `get_sectors`. | P0 | Medium | Medium | Port after company-level essentials. |
| Sector detail (`/setores/[slug]`, `/setores/[slug]/[sub_slug]`) | Year selector, aggregate KPIs, yearly overview, company table, breadcrumbs. | Missing. | Existing `get_sector_detail`, `get_sub_sector_detail`. | P0 | Medium | Medium | Port with sectors directory as one coherent slice. |
| Update base / refresh data (`/atualizar-base`) | Administrative refresh dashboard: base health, scopes, filters, job progress, history, cancel flow. | Missing. | Existing `get_base_health`, `request_refresh`, `cancel_refresh`, `get_refresh_status`, company suggestions/filter methods. | P0 | High | High | Port after read-only screens; keep write actions narrow and heavily smoke-tested. |
| Single-company refresh controls | Next company detail can request a period refresh and show progress. | Missing. | Existing `request_refresh`, `get_refresh_status`. | P0 | Medium | High | Port before Vite default; write path but already bridged. |
| Excel export / save flows | Next has Excel export/download button and desktop bridge save/download path. | Missing. | Existing `save_company_excel`, `download_company_excel`. | P0 | Medium | Medium | Recommended next narrow slice: add export action to company detail/statements. |
| Auto-updater UI | Next shows floating update prompt through `check_update` / `apply_update`; local snooze only. | Missing. | Existing `check_update`, `apply_update`, `snooze_update`, `get_update_progress`. | P0 | Medium | High | Required before default switch so users keep in-app update prompts. |
| Health / status (`/health`) | API/desktop health indicator and route-level problem states. | Implemented as `/health` with bridge health payload. | Existing `get_health`. | P1 | Low | Low | Done enough; polish copy after P0 features. |
| Settings / about | No dedicated production settings route found; status is mostly health/update prompt. | No dedicated settings/about route. | `get_health`, updater methods if added. | P2 | Low | Low | Defer unless user asks. |
| Search behavior | Home suggestions, company directory search, company suggestions in update-base. | Directory search only. | Existing `get_companies`, `get_company_suggestions`. | P0 | Medium | Medium | Add suggestions where needed with update/export flows. |
| Filter/sort behavior | Directory sector filter, update-base status/range filters, statements row filter. | Directory search only; statements row filter added in Phase 3A. | Existing filter methods. | P0 | Medium | Medium | Add per-screen filters as each route is ported. |
| Navigation patterns | Site header, route tabs, URL search params for tabs/years/statements, breadcrumbs. | Simple nav plus company links. Statements route uses query param `stmt`. | No new data. | P0 | Medium | Low | Add cohesive Vite navigation before default switch. |
| Loading/error/empty states | Route loading/error files, skeletons, `ApiUnavailableState`, empty cards. | Basic states for health, directory, detail; statements has loading/error/empty/filter-empty. | No new data. | P0 | Medium | Medium | Standardize reusable Vite state components after more screens exist. |
| Modals/dialogs/actions | Update confirmation modal, update prompt modal, refresh actions, export action feedback. | Missing. | Refresh and updater bridge methods. | P0 | Medium | High | Port action surfaces one at a time; avoid broad modal framework work. |
| Browser/dev fallback | Next falls back to HTTP/API routes outside desktop mode. | Vite API facades return clear browser-mode banners when pywebview bridge is unavailable. | No new data. | P1 | Low | Low | Keep pattern. |

## Already Done In Vite

- Static Vite SPA bundled and launchable with `CVMAnalytics.exe --vite`.
- Bridge readiness and typed adapter.
- Health route.
- Company directory with search and pagination.
- Company detail route with header and annual KPI table.
- Phase 3A: company financial statements screen at
  `/empresas/:cdCvm/demonstrativos?stmt=DRE`.

## Remaining P0 Before Vite Can Become Default

- Company directory sector filters and navigation polish.
- Company detail controls for refresh, freshness, and export.
- Complete KPI/indicator parity beyond the annual table.
- Sectors directory and sector detail routes.
- Update-base refresh dashboard, including guarded write actions.
- Auto-updater prompt/progress UI.
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

## Recommended Next Screen

Recommended next narrow slice: Excel export/save action on company detail and
the statements screen.

Reason: it is P0, high-value, already backed by existing bridge methods
(`save_company_excel`, `download_company_excel`), and much lower risk than the
write-heavy update-base dashboard.
