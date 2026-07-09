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

Verified from current routes, bridge methods, and source modules:

| Workflow | Implemented surface |
|---|---|
| Browse company catalog | `/empresas` using `get_companies`, filters, and local catalog/coverage status |
| Inspect company overview | `/empresas/:cdCvm` using company info, KPIs, export, refresh status |
| Review financial statements | `/empresas/:cdCvm/demonstrativos` for DRE/BPA/BPP/DFC matrices |
| Configure Excel model mapping | `/empresas/:cdCvm/model-mapping` and bridge Excel mapping methods |
| Export company workbook | Company command/export flow through `export_company_excel` |
| Refresh one company | Company page via `request_refresh` and `get_refresh_status` |
| Refresh database | Settings -> Updates (`/settings/updates`) |
| Audit coverage gaps | Settings -> Data Health/Coverage and coverage module routes |
| Manage coverage universes | `/coverage`, prioritization, and work queue routes |
| Inspect sectors/industries | `/setores` and sector/subsector detail routes |
| Review macro/energy indicators | `/indicators` and related energy KPI modules |
| Read collected news | `/news`, local News DB, registered sources |
| Inspect storage/runtime | Settings storage and diagnostics sections |
| Update the software | Status/diagnostics updater bridge and helper script |

## Planned Or Aspirational Context

Planning prompts and workflow notes under `docs/reference/coverage_*` and
`docs/plans/` are product context. They are not proof of implementation.

When documenting planned workflows:

- label them as planned, proposed, or Needs validation;
- do not mix them into implemented feature lists;
- cite the route, bridge method, database table, or test before calling a
  workflow implemented;
- keep future methodology templates separate from active user instructions.

## Coverage Best Practices (v1)

The CVMAnalytics Coverage module implements the Coverage Best Practices v1 workflow:

### Implemented Features (v1)
- **Coverage Universes**: Create, update, duplicate, and delete custom universes of Brazilian public companies.
- **Prioritization Grid**: Dense prioritization scoring based on market cap, liquidity, GICS tier, and status.
- **Work Queue**: Automatically derives and ranks tasks for data-quality, checklist items, and owner assignments.
- **Capacity Simulator**: Models analyst hours and workload distribution using GICS sector slug complexities.
- **Owner Responsibility**: Assign coverage owners to companies in a universe with audit-grade rationales.
- **Local News Workload Gaps**: Surface news coverage latency using the local news database.
- **Recommendation Package / Manager Decision**: Propose list actions and track manager review status (`draft`, `pending_review`, `approved`, `rejected`) in the decision history.
- **Audit-Grade Excel Export**: Comprehensive 7-sheet export with Summary, Priorities, Priority Factors, Work Queue, Capacity, Decision History, and Methodology.

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
