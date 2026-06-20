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
