# Current Product Gap Audit

Date: 2026-07-08

## Purpose

This audit maps the current CVMAnalytics product surface against the product
direction in `docs/PRODUCT_DIRECTION.md` and the step checklist in
`docs/PRODUCT_DEVELOPMENT_CHECKLIST.md`.

It is a product and documentation audit only. It does not authorize feature
implementation.

## Evidence Inspected

Canonical docs:

- `README.md`
- `AGENTS.md`
- `docs/PRODUCT_DIRECTION.md`
- `docs/PRODUCT_DEVELOPMENT_CHECKLIST.md`
- `docs/product-workflows.md`
- `docs/data-sources.md`
- `docs/excel-exports.md`
- `docs/reference/indicators-module.md`

Active UI/runtime evidence:

- `apps/desktop-web/src/App.tsx`
- `apps/desktop-web/src/components/shell/ModuleNav.tsx`
- `apps/desktop-web/src/components/shell/SubNav.tsx`
- `apps/desktop-web/src/routes/HomePage.tsx`
- `apps/desktop-web/src/routes/CompaniesPage.tsx`
- `apps/desktop-web/src/routes/CompanyDetailPage.tsx`
- `apps/desktop-web/src/routes/CompanyStatementsPage.tsx`
- `apps/desktop-web/src/routes/CompanyModelMappingPage.tsx`
- `apps/desktop-web/src/routes/CoveragePage.tsx`
- `apps/desktop-web/src/routes/CountryKpisPage.tsx`
- `apps/desktop-web/src/routes/SectorsPage.tsx`
- `apps/desktop-web/src/routes/SectorDetailPage.tsx`
- `apps/desktop-web/src/routes/SettingsModule.tsx`
- `apps/desktop-web/src/routes/NewsPage.tsx`
- `apps/desktop-web/src/lib/api/companies.ts`
- `apps/desktop-web/src/lib/api/exports.ts`

## Executive Finding

CVMAnalytics has strong raw material for an analyst workbench: local data,
company financials, coverage universes, sector navigation, energy indicators,
settings/diagnostics, news, and Excel exports.

The main gap is product connection. The implemented surfaces do not yet read as
one continuous analyst workflow:

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

The next product work should not start with valuation or thesis. The first
practical step is to make the existing Coverage, Sector, Company, Indicators,
Settings, and Export surfaces behave like a connected local analyst workbench.

## Workflow Gap Map

| Workflow step | Current verified surface | Status | Main gap | Next product action |
| --- | --- | --- | --- | --- |
| Foundation / reliability | Settings health, storage, sources/imports, updates, diagnostics; local data root and source rules documented | Strong but still distributed | Reliability evidence exists, but it is spread across Settings, docs, and module-specific states | Make Settings/Home explain local readiness and safe next actions in analyst language |
| Coverage Universe | `/coverage`, prioritization, work queue, capacity, manager decision package, coverage export | Strongest current workflow | Coverage is advanced, but its output is not yet clearly connected to Sector and Company next steps | Add clearer "why review next" handoff from coverage tasks to sector/company analysis |
| Sector Work | `/setores`, sector/subsector pages, Energy areas inside `/indicators` | Partial | Sector pages are mostly classification/navigation; sector drivers live separately in Indicators/Energy | Define a sector workbench model: drivers, source status, impacted companies, and next company drill-down |
| Company Work | `/empresas`, `/empresas/:cdCvm`, statements, KPIs, model mapping, company coverage, export | Partial but central | Company pages are analytical, but not yet organized around Sources, Events, Risks, Drivers, Critical Factors, Peers, Model, Valuation, and Thesis | Reframe company detail as the main company workspace while preserving current statements/export behavior |
| Information Hub | Source files, snapshots, data-source docs, Settings storage, News DB, statement rows, Excel metadata | Partial | Evidence exists but is not presented as a unified company/sector source hub | Start with source lineage and "where did this number come from" for existing company values and exports |
| Indicator Library | `/indicators`, documented default library boundaries, energy/sector/company-asset subareas | Partial with boundary risk | The module hosts several specialist workflows, so the default library can blur with company/asset indicators | Keep default Indicator Library strict: only reusable macro/sector/system/market indicators |
| Critical Factors | Not verified as an implemented workspace | Missing / future | No current company-level 3-7 factor model linking thesis, indicators, thresholds, and review status | Do not build yet; first prepare company workspace and source lineage |
| Forecasts / Models | Company model mapping and historical Excel workbook export | Early foundation | Current model work is export/mapping around historical data, not forecast assumptions or model versions | After company workspace cleanup, define first model versioning and assumptions contract |
| Valuation | No active valuation route/workspace verified | Missing / future | No DCF, comps, SOTP, target price, sensitivities, or valuation bridge | Defer until forecast/model workspace has traceable assumptions |
| Thesis / Recommendation | Coverage has manager decision/recommendation package; no investment-thesis workspace verified | Missing / future | Coverage recommendation is not the same as stock thesis/recommendation | Defer until critical factors, model, and valuation can support a traceable thesis |
| Audit-ready Export | Company workbook export, coverage export, market history/export facades, energy exports documented | Strong foundation | Export standards are strong, but future model/valuation/thesis exports are not defined | Keep export quality as a gate for every new analyst workflow |

## Cross-Cutting Gaps

### 1. The App Needs A Clear Analyst Handoff

Current modules are individually useful, but the next action after each screen is
not always obvious.

Examples:

- Coverage can identify tasks and priorities, but the next sector/company review
  path should be clearer.
- Sector pages classify companies, but sector driver context is not yet the
  obvious starting point before company analysis.
- Company pages show financial data, KPIs, market history, and exports, but the
  flow from evidence to drivers to model/thesis is not yet explicit.

Product requirement:

- Every major screen should answer: what should the analyst inspect next, and
  why?

### 2. Company Workspace Is The Next Structural Bottleneck

The company area already has the right base pieces:

- company identity;
- financial statements;
- financial indicators;
- market history;
- refresh status;
- model mapping;
- company coverage status;
- Excel export.

The gap is information architecture. Company analysis should eventually organize
around Overview, Financials, Sources, Events, Risks, Drivers, Critical Factors,
Peers, Model/Excel, Valuation, and Thesis. Current implementation should not be
rewritten wholesale; the next step should be a small IA pass that clarifies what
exists now and what is future.

### 3. Sector Work Is Too Shallow Relative To The Target Workflow

Sector pages currently appear closer to GICS directory and company navigation.
Energy depth exists, but much of it lives under Indicators.

Product requirement:

- Sector work should explain the sector before the analyst opens a company.
- Energy should become the first proof point: PLD, SIN, load, generation,
  storage, capacity, regulation, and impacted companies.

### 4. Indicator Boundaries Need Protection

The Indicator module is powerful, but it can become confusing if it absorbs
company, asset, model, and sector responsibilities.

Product rule to preserve:

- Indicator Library is for reusable macro/sector/system/market drivers.
- Company metrics belong in Company Workspace.
- Plant, parcel, distributor, and unit economics belong in specialist
  asset/sector workflows.
- Forecast assumptions and outputs belong in Model Workspace.

### 5. Critical Factors Are The Right Differentiator, But Too Early To Build

Critical factors should become the bridge from raw data to investment judgment.
However, they need reliable company workspace structure, source lineage, and
sector driver definitions first.

Do not start by building alerts or factor scoring. Start by defining:

- where factors live;
- how they link to source-backed indicators;
- what threshold and review metadata are required;
- how a factor affects model assumptions or thesis.

### 6. Valuation And Thesis Should Wait

Valuation and thesis features are high-leverage but depend on forecast
assumptions, peer/market data labels, scenario/versioning, and source lineage.

Building them before those foundations risks creating an impressive-looking but
unauditable workflow.

## Recommended Next Lanes

### Lane 1: Company Workspace IA Pass

Goal: make company analysis feel like the center of issuer work without changing
the data model first.

Scope:

- Audit current company detail, statements, model mapping, and coverage tabs.
- Decide the target company navigation labels.
- Mark which tabs are current, future, or hidden until implemented.
- Improve first-screen hierarchy around identity, local data status, latest
  period, source confidence, refresh/export, and next analysis action.

Why first:

- It uses existing surfaces.
- It supports the whole workflow.
- It creates a landing place for future critical factors, model, valuation, and
  thesis work.

### Lane 2: Coverage-To-Company Handoff

Goal: make coverage decisions lead naturally into analysis.

Scope:

- For each coverage task or priority reason, define the expected next action:
  refresh, inspect statements, review sector, inspect source, assign owner,
  export, or mark exception.
- Keep scoring caveats visible.
- Avoid adding generic task management.

Why second:

- Coverage is already strong.
- Better handoff converts coverage from an isolated module into the start of the
  analyst workflow.

### Lane 3: Sector Workbench Definition For Energy

Goal: define the first deep sector workbench around Energy/Utilities.

Scope:

- Choose the core sector drivers.
- Map each driver to current data availability, source status, and impacted
  company/asset paths.
- Keep missing ONS/ANEEL/CCEE/EPE concepts labeled as missing or partial.
- Define how sector context should lead into company critical factors later.

Why third:

- Energy already has the richest source foundation.
- It tests the product principle that sector work comes before company
  conclusions.

## Do Not Start Yet

Avoid starting these until the prior lanes are clearer:

- Critical Factors UI with alerting.
- Forecast scenario manager.
- DCF or peer valuation workspace.
- Thesis/recommendation builder.
- AI-generated investment summaries.

These are product-direction priorities, but they require stronger workflow,
source-lineage, and model foundations first.

## First Concrete Next Step

Start with a Company Workspace IA audit.

Deliverable:

```text
docs/company-workspace-gap-audit.md
```

Minimum questions:

- What does the current company page already do well?
- What must remain stable?
- Which current panels belong in Overview, Financials, Sources, Model/Excel, or
  Coverage?
- Which future areas should be named but not shown yet?
- What is the smallest UI/UX change that makes the company page feel like an
  analyst workspace instead of a collection of panels?

No implementation should begin until that audit defines the first narrow change.
