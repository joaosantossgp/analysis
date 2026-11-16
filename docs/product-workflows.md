# Product Workflows

## Purpose

CVMAnalytics is for analysts and investors who need a dense, auditable local
workspace for Brazilian public company financial data.

The product should preserve:

- local-first operation and offline access to already-downloaded data;
- explicit data sources and caveats;
- reproducible refreshes and source files;
- efficient reads, cache use, and controlled startup work;
- reliable Excel outputs;
- visible loading, empty, error, warning, and blocked states.

## Implemented Workflows

Verified from current routes, bridge methods, and source modules. See the
[active route inventory](architecture.md#active-routes) for route ownership and
compatibility behavior.

| Workflow | Implemented surface |
|---|---|
| Browse company catalog | `/empresas` using `get_companies`, filters, and local catalog/coverage status |
| Inspect company overview | `/empresas/:cdCvm` using company info, KPIs, export, refresh status |
| Review financial statements | `/empresas/:cdCvm/demonstrativos` for DRE/BPA/BPP/DFC matrices |
| Configure Excel model mapping | `/empresas/:cdCvm/model-mapping` and bridge Excel mapping methods |
| Export company workbook | Company command/export flow through `export_company_excel` |
| Refresh one company | Company page via `request_refresh` and `get_refresh_status` |
| Refresh database | Settings -> Updates (`/settings/updates`) |
| Audit local-data coverage gaps | Settings -> Health (`/settings/health`) and local-data Coverage (`/settings/coverage`) |
| Manage analyst coverage universes | Companies -> Coverage (`/empresas/coverage`), prioritization, work queue, and capacity |
| Inspect company coverage readiness | `/empresas/:cdCvm/coverage` for issuer-level Coverage Status |
| Inspect sectors/industries | `/setores` and sector/subsector detail routes |
| Review reusable indicators and energy analysis | `/indicators` with Indicator Library and Energy; the [module reference](reference/indicators-module.md#energy-sector) lists all five Energy subviews |
| Review company/asset mapping | Companies -> Assets & Mapping (`/empresas/assets`) |
| Inspect indicator source health | Settings -> Indicator Sources (`/settings/indicator-sources`), with specialist source status retained in Energy views |
| Inspect storage/runtime | Settings storage and diagnostics sections |
| Update the software | Status/diagnostics updater bridge and helper script |

News is retired from the active interface. Existing `/news/*` URLs show a
[retirement notice](../apps/desktop-web/src/App.tsx#L154), and saved Home News
widgets show the same state without querying news. The backend, saved settings
and downloaded News database remain preserved; they do not constitute an active
news-reading workflow. See [retired News UI](architecture.md#retired-news-ui) and
the retained [News source contract](data-sources.md#news-data).

## Planned Or Aspirational Context

Archived audits, plans, specs, and planning prompts under
`docs/archive/planning-2026/` are historical product context. They are not
proof of implementation.

When documenting planned workflows:

- label them as planned, proposed, or Needs validation;
- do not mix them into implemented feature lists;
- cite the route, bridge method, database table, or test before calling a
  workflow implemented;
- keep future methodology templates separate from active user instructions.

## Coverage Best Practices (v1)

Companies -> Coverage implements the Coverage Best Practices v1 workflow at
`/empresas/coverage`. Legacy `/coverage/*` links redirect there while preserving
the remaining path, query and hash
([route implementation](../apps/desktop-web/src/App.tsx#L189)). This analyst
workflow is distinct from company Coverage Status and Settings' local-data
coverage.

### Implemented Features (v1)
- **Coverage Universes**: Create, update, duplicate, and delete custom universes of Brazilian public companies.
- **Prioritization Grid**: Dense prioritization scoring based on market cap, liquidity, GICS tier, and status.
- **Work Queue**: Automatically derives and ranks tasks for data-quality, checklist items, and owner assignments.
- **Capacity Simulator**: Models analyst hours and workload distribution using GICS sector slug complexities.
- **Owner Responsibility**: Assign coverage owners to companies in a universe with audit-grade rationales.
- **Local News Workload Gaps**: Retain local news counts, mapping gaps and database-unavailable evidence; News task handoffs are unsupported after UI retirement.
- **Recommendation Package / Manager Decision**: Propose list actions and track manager review status (`draft`, `pending_review`, `approved`, `rejected`) in the decision history.
- **Audit-Grade Excel Export**: Comprehensive 7-sheet export with Summary, Priorities, Priority Factors, Work Queue, Capacity, Decision History, and Methodology.

The [Coverage service](../src/companies/coverage.py#L706) still reads local News
workload and [emits gap tasks](../src/companies/coverage.py#L1605). The
[handoff resolver](../apps/desktop-web/src/components/coverage/workQueueHandoffs.ts#L130)
marks `news_gap`, `news_mapping_unavailable` and `news_db_unavailable` unsupported;
the work queue preserves the evidence without offering an active News workflow.

### Planned features (v2 / Proposed)
- **Stock Correlation Matrix**: Statistical correlation of prices.
- **Peers & Value-Chain Graph**: Interactive supplier/customer networks and competitor flows.
- **ONS/ANEEL/CCEE Integration**: Auto-import energy regulator data feeds.
- **Analyst Authentication / Multi-user Auth**: Local-first analyst credentials.

## Coverage Universe Principles

Coverage workflows should help analysts decide what to refresh or analyze next.
They must distinguish:

- in-catalog companies with no local statement history;
- partial vs complete financial statement coverage;
- stale vs failed vs ignored companies;
- Top N market-cap universes based on unofficial/external ranking snapshots;
- official CVM statement availability vs ranking/liquidity context.

Market cap is useful for prioritization but is not a CVM financial statement.

## Analyst Workflow Standards

Good analyst workflows should expose:

- company, period, statement/account, and source;
- whether values are official reported, imported, calculated, or external;
- coverage and freshness status;
- errors/warnings instead of silent fallbacks;
- direct paths to refresh, inspect source, export, or mark an exception.

Avoid marketing language and avoid presenting dashboard visuals without source,
period, and caveat context.

## Minimalism Standard For Workflow Reviews

Minimalism is now a core product principle for CVMAnalytics. In workflow
reviews, minimalism means reducing friction and noise while preserving the
information analysts need to trust the result.

For each page or workflow, check:

- whether the first screen makes the primary analyst task obvious;
- whether essential information is visually prioritized over secondary context;
- whether repeated copy, redundant cards, duplicate controls, or generic
  dashboard framing can be removed;
- whether tables, filters, indicators, and charts follow patterns already used
  elsewhere in the app;
- whether source, period, unit, currency, consolidation, calculation method,
  freshness, and caveats remain accessible;
- whether empty, loading, error, stale, and partial states tell the analyst what
  happened and what action is available;
- whether the workflow moves naturally from selection to evidence, indicator,
  trend, interpretation, export, or next action.

Do not make a page cleaner by hiding data-quality issues, missing values,
unavailable source metadata, or local bridge failures.
