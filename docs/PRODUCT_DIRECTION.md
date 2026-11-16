# Product Direction

## One-Line Product Thesis

CVMAnalytics is a local-first financial analyst workbench for Brazilian
companies, designed to turn auditable data into sector understanding, company
analysis, forecasts, valuation, investment theses, and Excel-grade outputs.

The product is not "CVM data plus charts." It should support the professional
research workflow an analyst follows from coverage selection to communicated
recommendation.

## Delivery Direction (2026-11-13)

Evolve the existing application incrementally through small, independently useful
issues tied to concrete analyst workflows. Improve company and sector analysis,
local data reliability, performance and Excel handoff as demonstrated needs arise.
Preserve saved data, settings, lineage and visible failure states in each change.

Multi-window delivery and its dedicated planning cycle (#464 and #466) are
**not planned for now**, by owner decision. Their research remains available as
historical reference, not an active roadmap or prerequisite for ordinary app work.
Do not introduce docking, synchronization infrastructure, a new shell or an engine
migration in anticipation of that deferred goal. A future multi-window request
must start from a specific user need and a separately scoped issue; it does not
require committing to the former full workbench plan.

## Target User

The primary user is a financial market analyst covering Brazilian companies:
equity, credit, investment banking, buy-side, sell-side, corporate finance, or
an analytical investor with similar needs.

The product should optimize for:

- focused desktop work;
- local ownership of downloaded data;
- dense comparison across companies, sectors, periods, sources, and drivers;
- auditability and source traceability;
- fast reads from local storage;
- disciplined sector and company workflows;
- Excel handoff for professional models and review.

Do not optimize the core product for casual browsing, social sharing, mobile
consumption, generic dashboards, CRUD administration, or untraceable summaries.

## Core Workflow

The long-term product workflow is:

```text
Coverage Universe
-> Sector Work
-> Company Work
-> Critical Factors
-> Forecasts / Models
-> Valuation
-> Thesis / Recommendation
-> Audit-ready Export
```

Every major feature should support one or more steps in this workflow. If a
feature does not help an analyst select coverage, understand a sector, analyze a
company, monitor drivers, forecast, value, form a thesis, or export evidence, it
belongs outside the product or in a future research note until its role is clear.

## Product Principles

### Local-First

Already-downloaded data must remain usable offline. Refreshes, software updates,
news collection, market data updates, and external-source imports may require a
network, but normal analysis should not depend on hidden remote calls.

Runtime data belongs in the user's CVMAnalytics data root. Source files,
snapshots, logs, caches, databases, and generated outputs should remain local
artifacts unless a future feature explicitly changes that contract.

### Auditability

The app must preserve the path from output back to evidence:

```text
number -> formula/transformation -> source -> company/entity -> period -> unit -> timestamp
```

Every material value should identify whether it is official, external,
imported, calculated, estimated, unavailable, or planned.

### Performance

The product should feel like a local workstation. Expensive refreshes, imports,
large scans, and historical rebuilds should be explicit, scoped, and observable.
Read paths should use local databases, caches, or marts designed for the UI
grain.

### Minimalism With Density

Minimalism means removing noise, not removing evidence. The UI should be dense,
legible, and professional, with hierarchy that helps the analyst compare,
verify, and decide. It should not become a decorative dashboard.

Design decision: less is more useful when it reduces visible choices, repeated
labels, decorative containers, and low-value text. Less is not useful when it
removes the source, period, unit, method, caveat, or next action an analyst
needs to trust the result.

### Workspace Continuity

Analytical screens should preserve the user's working context when the user is
already inside an active analysis. A directory, library, table, or grid is an
index into evidence and action; it should avoid losing scroll position, filter
state, or comparison context merely to inspect one item.

The preferred pattern is:

```text
index or table
-> contextual detail panel
-> chart/table/source evidence
-> explicit next action or deeper workspace
```

Use side panels, drawers, or in-place drill-downs when they help the analyst
inspect an indicator, company, account, source, checklist item, or mapping row
without leaving the current task. These panels must remain bounded to the
workspace, preserve the source table, and support larger inspection through
resizing or fullscreen when the evidence requires it.

Navigation to a new route remains appropriate for deep workspaces such as
Financial Statements, Excel Mapping, Coverage, future Models, and Valuation.
It is also appropriate when a directory row opens the workspace itself: Companies
directory row activation should navigate to `/empresas/:cdCvm`, the deep-work
issuer workspace. Once inside that workspace, dense analytical lists should
preserve context whenever practical.

### Excel-Grade Output

Excel is a central product output, not an afterthought. Workbooks must be
auditable, structured, repair-free, and suitable for analyst review.

### Explicit Errors

Missing data, stale data, partial coverage, failed refreshes, invalid tickers,
unavailable sources, and bridge errors must be visible. Do not silently fallback
from official data to external data or from missing values to zeros.

## Main Workspaces

### Research Command Center

Role: entry point for what requires attention next.

Current verified direction:

- The active app has a Home route and local status/data surfaces.

Target direction:

- Show covered companies and sectors.
- Summarize what changed since the last review.
- Surface updated sources, stale analyses, stale models, and stale theses.
- Highlight moved critical factors and companies requiring attention.
- Provide an analyst task queue tied to coverage, data quality, events, and
  review dates.

Do not document coverage dashboards, stale thesis warnings, or factor alerts as
implemented until verified in active routes, bridge methods, and data storage.

### Universe Builder

Role: help the analyst choose what deserves attention.

Current verified direction:

- Companies owns Coverage at `/empresas/coverage`, with universes,
  prioritization, work queue and capacity. This is separate from issuer-level
  Coverage Status and Settings' local-data coverage.
- The [implemented Coverage workflow](product-workflows.md#coverage-best-practices-v1)
  records owner responsibility, manager decisions, export and retained local
  News workload evidence. News task handoffs are unsupported after UI retirement.

Target direction:

- Support watchlist, coverage universe, and screening universe concepts.
- Rank companies by market cap, liquidity, sector, relevance, and coverage
  status, while labeling unofficial market data correctly.
- Track statuses such as not started, watch, covered, high conviction, and
  stale.
- Show CVM sector, GICS sector, GICS subindustry, coverage status, and source
  timestamps.
- Eventually support conglomerate/subsidiary relationships, correlation or
  homogeneity checks, and news or event load estimation.

Company master data should converge on one source of truth for company name,
ticker, CNPJ, CVM identifier, CVM sector, GICS sector, GICS subindustry,
conglomerate flag, subsidiaries, market-data identifiers, source, and timestamp.

### Information Hub

Role: organize all relevant evidence locally before analysis.

Target direction:

- For each company and sector, organize CVM documents, B3 data, financial
  statements, filings, releases, external datasets, notes, links, source
  snapshots, IR references, events, assumptions, formulas, transformations, and
  timestamps.
- Provide source lineage for tables, charts, Excel exports, and model outputs.
- Consider an "Explain this number" interaction only when the underlying source
  and transformation metadata are available.

The hub should not become a generic file manager. It exists to support
traceable analysis.

### Sector Workbench

Role: help analysts understand the sector before judging individual companies.

Current verified direction:

- The active app has sector and subsector routes.
- Energy is the deepest current sector area in the Indicators module.
- Current docs and code reference ANEEL distribution, CCEE generation,
  ONS/CCEE/EPE/ANEEL SIN-related sources, ANP fuel distribution, and local
  energy marts.

Target direction:

- Support critical sector drivers, capacity and demand, pricing, input costs,
  regulation, historical cycles, market share, sector-level financial metrics,
  sector stock performance, and value-chain analysis.
- Link macro and sector indicators to likely company impact.

Energy/Utilities priority concepts include ONS, ANEEL, CCEE, EPE, SIN,
subsystems, PLD, load, generation by source, stored energy, capacity, plants,
parcels, generation history, availability, and regulatory events.

Do not claim broad sector-driver modeling or value-chain analysis is implemented
until verified in active code and docs.

### Indicator Library

Role: reusable macro, sector, system, market, and benchmark drivers.

Current verified direction:

- The active route is `/indicators`, with Indicator Library and Energy sections.
  Companies owns Assets & Mapping at `/empresas/assets`; indicator source health
  belongs to Settings at `/settings/indicator-sources`. See the
  [module ownership and compatibility contract](reference/indicators-module.md#product-shape).
- `docs/reference/indicators-module.md` defines the default Indicator Library
  as indicators that can open directly without selecting a company, distributor,
  plant, asset, parcel, ticker, fuel product, state, or economic group.

Product rule:

- Indicator Library = macro, sector, system, market, and benchmark indicators.
- Company Workspace = company financial and operational metrics.
- Asset/Plant Workspace = plant, parcel, unit economics, and operational
  asset-level metrics.
- Model Workspace = assumptions, scenarios, forecast outputs, and sensitivities.

Indicators that fit the library include inflation, rates, FX, GDP, industrial
production, commodities, yield curve, Ibovespa and sector indices, PLD, SIN
load, energy storage, generation by source, system capacity, aggregate
regulatory indicators, liquidity, and market indicators.

Indicators that should not live in the general library include company-specific
KPIs, anything requiring company selection, anything requiring plant/parcel/unit
selection, company-specific unit economics, and operational metrics tied to one
company or asset.

### Company Workspace

Role: main issuer-level analysis workspace.

Current verified direction:

- The active app has company directory, company overview, financial statements,
  model mapping, company coverage, and company workbook export surfaces.
- Current docs verify CVM statements, KPIs/checks, company refresh, and Excel
  export paths.

Target direction:

- Organize each company around Overview, Financials, Segments, Drivers,
  Critical Factors, Peers, Valuation, Model/Excel, Notes, Sources, Events, and
  Risks.
- Make company pages feel like an analysis workspace, not only a registry.
- Treat company identity as the workspace spine: name, ticker, CVM id, CNPJ,
  sectors, local data status, latest period, source readiness, and mapped
  operating connections should remain the anchor as the user moves across
  sub-tabs.
- Treat sub-tabs as workflow modes for the same issuer, not separate dashboard
  pages. Overview should answer readiness, available evidence, and next action;
  Financial Statements should preserve official account-level evidence;
  Coverage Status should explain company readiness and remaining work.
  Excel Mapping remains an action with a dedicated window, focused on
  export/model mapping until forecasting exists; see the
  [company workspace contract](DESIGN.md#company-workspace-pattern).
- Prefer contextual drill-downs from company tables and panels before creating
  new routes. Company indicator rows, market series, statement accounts,
  mapping lines, coverage checklist items, and source statuses should open
  useful detail without losing the current company context when practical.
- Treat the Companies directory as the entry point into issuer analysis: row
  activation should navigate to `/empresas/:cdCvm`, while contextual panels are
  preferred after the analyst is already working inside that issuer workspace.
- Keep company-specific metrics inside the Company Workspace. The general
  Indicator Library is for indicators that open without selecting an issuer or
  asset.

Company analysis must clearly separate consolidated vs individual, quarterly
isolated vs accumulated, reported vs calculated, official vs external, actual
vs estimated, BRL/thousand BRL/million BRL and other units, recurring vs
non-recurring items, and original filings vs restatements.

### Critical Factors Monitor

Role: core future differentiator for turning data into investment judgment.

Target direction:

- Each covered company should eventually have three to seven critical factors.
- Each factor should define factor name, investment thesis, linked indicator,
  data source, materiality threshold, last value, historical range, expected
  financial impact, confidence level, evidence, alert status, and last reviewed
  date.

Energy/Utilities examples:

| Critical factor | Indicator | Impact |
| --- | --- | --- |
| PLD | PLD by subsystem | Revenue or energy purchase cost |
| GSF | Monthly and accumulated GSF | Margin and cash flow |
| Hydrology | ENA / stored energy | Operating risk |
| Leverage | Net debt / EBITDA | Equity and credit risk |
| Tariff review | ANEEL calendar | Revenue and margin |
| Capex | Capex vs plan | FCF and balance sheet |
| Generation | Generation by source or plant | Operating performance |

This is product direction, not a verified implemented workspace.

### Model / Forecast Workspace

Role: convert history and drivers into explicit forecasts.

Current verified direction:

- The current financial Excel exporter supports historical financial workbooks,
  model mapping, formulas/checks, hidden raw sheets, README/metadata, and
  selected period scopes.
- Forecast/projected-period modeling is not documented as implemented in the
  active financial exporter.

Target direction:

- Start from official financial history.
- Support explicit adjustments and driver-based assumptions.
- Support base, bull, bear, and stress scenarios.
- Add checks for balance sheet, cash flow, debt, and reconciliation.
- Provide revenue, margin, EBITDA, FCF, and debt bridges where supported by the
  model.
- Support sensitivity tables, model versioning, and reconciliation between app
  and Excel.
- Add sector-specific model templates only after the source and calculation
  rules are documented.

Excel model rules:

- no merged cells;
- use Center Across Selection if visual spanning is needed;
- freeze panes logically;
- separate inputs, calculations, and outputs;
- keep formulas simple and traceable;
- standardize dates, units, and currencies;
- separate historical and forecast periods;
- preserve hierarchy and subtotals;
- include balance sheet, cash flow, debt, and source/data-quality checks;
- show negatives in parentheses;
- show zeros as `-`;
- generated files must open without repair.

### Valuation Workspace

Role: connect forecasts, peers, market data, and thesis to a target value.

Target direction:

- Support historical multiples, peer comps, DCF, SOTP, sensitivities, target
  price, upside/downside, valuation bridge, current vs historical vs peer vs
  implied multiples, and explicit premium/discount rationale.
- Keep official reported data, external market data, calculated forecasts, and
  estimates visibly labeled.

This is product direction. Do not claim valuation workflows are implemented
until active routes, bridge methods, data models, and exports exist.

### Thesis / Recommendation Builder

Role: help the analyst communicate a clear, actionable view.

Target direction:

- Support one-page thesis, recommendation, horizon, target price,
  upside/downside, key drivers, catalysts, risks, what would change the thesis,
  difference versus consensus, evidence, sources, exportable charts/tables, and
  eventually memo/report export.

The product should help the analyst answer:

- What matters?
- What changed?
- Why is the market wrong?
- What is priced in?
- What is the upside/downside?
- What would make us change our mind?

This is product direction. Do not claim thesis or recommendation workflows are
implemented until verified.

### Data Sources / Imports

Role: controlled intake, provenance, and health for official, external, and
user-provided data.

Current verified direction:

- Current docs define source classes for official reported, official external
  dataset, external/unofficial, user import, calculated, and estimated/planned.
- Current docs verify CVM financial statement ingestion, Yahoo/yfinance-backed
  market data paths, retained News backend/data, energy sources, runtime data
  roots, and source auditability requirements. News is retired from the active
  interface; its [source policies](data-sources.md#news-data) still apply.

Target direction:

- Continue to distinguish CVM/B3 official data from Yahoo/yfinance, Google
  News, and other external or aggregator sources.
- Preserve downloaded data and source snapshots where they support auditability.
- Avoid repeated external calls when local snapshots or caches should be used.
- Handle invalid tickers and unavailable sources explicitly.
- Add source badges, stale-data warnings, restatement warnings, missing-data
  warnings, official/external/calculated/estimated labels, and pre-export checks
  where the underlying metadata exists.

### Excel / Export

Role: audit-ready handoff for models, evidence, coverage decisions, and reports.

Current verified direction:

- Current docs verify company financial workbook export and coverage universe
  export.
- Other exports exist for market history, coverage, country KPIs, and
  distribution modules, but their workbook structures differ and must be audited
  separately before broad compliance claims.

Target direction:

- Exports should preserve methodology, source context, period policy,
  units/currency, calculation status, hidden/audit sheets where useful, and
  checks that prevent silent corruption.
- Exported charts, tables, models, and future reports should match the evidence
  and caveats visible in the app.

## Data Principles

Every product surface must preserve the distinctions below when they affect
interpretation:

- official CVM/B3 vs external/unofficial data;
- consolidated vs individual statements;
- DFP annual vs ITR quarterly;
- quarterly isolated vs accumulated values;
- reported vs calculated;
- actual vs estimated or forecast;
- imported vs downloaded;
- recurring vs non-recurring;
- original filing vs restatement;
- BRL, thousand BRL, million BRL, and other units/scales;
- source timestamp, generated timestamp, and as-of date;
- missing value vs zero value;
- unavailable vs unsupported vs failed.

Never mix official, external, calculated, and estimated values without labels.
Never silently fallback from official to external data.

## Current Known Capabilities

Use [Implemented Workflows](product-workflows.md#implemented-workflows) for
current analyst capabilities and the [active route inventory](architecture.md#active-routes)
for workspace ownership, redirects and retired surfaces. Source classes,
retained backend/data contracts and offline behavior live in
[Data Sources](data-sources.md); the [Indicators module reference](reference/indicators-module.md)
owns its specialist capabilities. These references distinguish active UI from
preserved backend code and future direction.

Before marking a workflow implemented, cite the active route, bridge/API method,
database table, source module, export path or test that proves the specific claim.

## Future Direction

The strategic product path is to deepen the workbench in this order:

1. Data and source foundation: establish source contracts, local storage,
   refresh behavior, bounded read models, source status, and auditability before
   expanding analyst workflow surfaces.
2. Coverage discipline: help analysts choose and maintain the right universe.
3. Sector understanding: add driver-based sector workbench behavior before
   company-specific conclusions.
4. Company workspace depth: make company pages the center of financial,
   operational, source, event, risk, and peer analysis.
5. Critical factors: connect each covered company to the few variables that
   drive the thesis only after those variables have source-backed or explicitly
   manual evidence.
6. Forecasts and models: convert drivers into assumptions, scenarios, checks,
   and Excel-aligned models.
7. Valuation: connect forecasts, peers, market data, and thesis to target value.
8. Thesis and recommendation: help the analyst communicate a clear view with
   evidence, risks, catalysts, and what would change the conclusion.
9. Audit-ready export: preserve the work in Excel and, eventually, report/memo
   formats without losing source lineage.

This is direction, not an implementation claim.

## Non-Goals

CVMAnalytics should not become:

- a generic SaaS dashboard;
- a CRUD-first administration app;
- a disconnected data viewer;
- a decorative chart gallery;
- a cloud-first research portal;
- a mobile-first app;
- an AI-summary tool without traceable inputs;
- a valuation engine that hides assumptions;
- a source aggregator that treats all data as equally reliable.

## Feature Admission Rules

A new feature should enter the product only when it answers:

- Which step of the core analyst workflow does it support?
- Which workspace owns it?
- What source class does it use?
- What is official, external, imported, calculated, estimated, unavailable, or
  planned?
- What persists locally, and where?
- What happens offline?
- What happens when the source is missing, stale, partial, invalid, or failed?
- What is the smallest useful first version?
- What export or handoff behavior is required?
- What validation proves it works?
- What caveat must remain visible to the user?

If these answers are unclear, write a short product note before writing code.

## Acceptance Criteria For Product Alignment

The product direction is aligned when a contributor can tell how each feature
supports the analyst path from universe selection to thesis/export, without
overstating implementation status.

Specifically, the direction is aligned when:

- the analyst workflow is explicit;
- existing capabilities are separated from future direction;
- Indicator Library excludes company-specific and asset/unit-specific metrics;
- company-specific metrics belong in Company Workspace;
- plant, parcel, and unit economics belong in asset/plant workspaces;
- source lineage and local-first behavior are central;
- Excel output standards remain part of product quality;
- errors and unavailable data are visible;
- the UI standard remains serious, dense, minimal, and audit-focused.

When in doubt, choose the option that improves local, auditable analyst work
with the least new surface area. Do not choose the option that merely makes the
app look broader.
