# Product Development Checklist

Use this checklist to plan the next large product steps for CVMAnalytics. It is
not a promise that every item is implemented. It is a practical guide for
choosing, scoping, and validating work against the analyst workflow in
`docs/PRODUCT_DIRECTION.md`.

Core workflow:

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

## How To Use This Checklist

Before starting a large feature, answer the section for the workflow step it
touches. If the answers are weak, write a short product note before writing
code. If a feature spans multiple sections, split it into smaller releases.

Default order for big steps:

1. Make current data and workflows reliable.
2. Establish source contracts, local storage, refresh behavior, and read models
   for the next domain.
3. Improve coverage and universe decisions.
4. Deepen sector work before company conclusions.
5. Make company pages a real analysis workspace.
6. Add critical factors only after enough source-backed drivers exist.
7. Add forecasts and model versioning.
8. Add valuation.
9. Add thesis/recommendation outputs.
10. Strengthen Excel and audit exports at each stage.

Foundational reference: `docs/foundational-development-characteristics.md`.

## 0. Product Fit Gate

Every large change must answer:

- Which analyst workflow step does this improve?
- Which current workspace owns it?
- Is this a data reliability problem, workflow problem, modeling problem, or UI
  hierarchy problem?
- What is the smallest version that helps a real analyst?
- What current feature must remain stable?
- What evidence proves this is implemented: route, bridge/API method, database
  table, source module, export path, or test?
- What should be explicitly labeled as future direction?

Do not proceed if the feature only makes the product look broader.

## 1. Foundation: Reliability Before Expansion

Goal: make the existing local-first workbench trustworthy before adding new
analyst surfaces.

Checklist:

- Verify active runtime: Vite desktop UI, pywebview bridge, Python core, local
  SQLite, Documents data root.
- Keep local reads usable offline.
- Preserve source files, snapshots, caches, logs, and output paths.
- Make missing, stale, partial, failed, and unavailable states explicit.
- Avoid broad startup scans or hidden remote calls.
- Keep Settings health, storage, diagnostics, imports, and updates coherent.
- Validate Excel exports open without repair when export behavior changes.
- Do not introduce new source classes without source metadata and caveats.

Acceptance bar:

- A user can tell what data exists locally, what is missing, what is stale, and
  what action is safe to run next.

## 2. Coverage Universe

Goal: help the analyst choose and maintain the right set of companies.

Checklist:

- Separate watchlist, coverage universe, and screening universe concepts.
- Show coverage status, source coverage, freshness, and data-quality gaps.
- Keep market cap, liquidity, and price data labeled as external/unofficial
  when sourced from Yahoo/yfinance or snapshots.
- Preserve company identity fields: name, ticker, CNPJ, CVM id, CVM sector,
  GICS sector/subindustry, identifiers, source, timestamp.
- Support prioritization without hiding blocked or partial scores.
- Keep work queue actions tied to real coverage/data-quality reasons.
- Export coverage decisions with methodology and caveats.

Acceptance bar:

- An analyst can explain why a company is in the universe, what data is missing,
  and what should be reviewed next.

## 3. Sector Workbench

Goal: make sector context precede company conclusions.

Energy/Utilities readiness reference:
`docs/archive/planning-2026/audits/energy-utilities-source-driver-readiness-audit.md` (archived).

Checklist:

- Define the sector question before adding metrics.
- Separate sector-level drivers from company-specific or asset-specific metrics.
- Show source, unit, period, coverage, and caveats for every sector indicator.
- For Energy/Utilities, prioritize ONS, ANEEL, CCEE, EPE, SIN, PLD, load,
  generation, stored energy, capacity, plants/parcels, and regulatory events.
- Use local marts or bounded reads for large datasets.
- Link sector drivers to possible company impact without claiming causality
  unless modeled.
- Keep value-chain, market-share, pricing, demand, and regulation work labeled
  as future direction until implemented.

Acceptance bar:

- An analyst can understand the sector's main drivers and know which company
  analysis should come next.

## 4. Indicator Library Boundaries

Goal: keep the Indicator Library reusable and clean.

Checklist:

- Include macro, sector, system, market, benchmark, and aggregate regulatory
  indicators.
- Exclude anything that requires company, plant, parcel, asset, distributor,
  fuel product, state, ticker, or economic group selection.
- Put company metrics in Company Workspace.
- Put plant/parcel/unit economics in Asset/Plant workflows.
- Put assumptions, scenarios, and forecast outputs in Model Workspace.
- Do not invent units, formulas, coverage, source quality, or freshness.
- Keep unavailable metadata visibly unavailable.

Acceptance bar:

- A user can open an Indicator Library row without first choosing an entity.

## 5. Company Workspace

Goal: make company pages the main issuer-level analysis workspace.

Checklist:

- Preserve current company overview, statements, refresh, model mapping, and
  export behavior.
- Use `docs/archive/planning-2026/audits/company-workspace-overview-ia-plan.md` (archived) as the first implementation
  guide for the Overview IA pass.
- Separate overview, financials, drivers, sources, events, risks, model/Excel,
  and future valuation/thesis areas.
- Keep consolidated vs individual, annual vs quarterly, reported vs calculated,
  official vs external, actual vs estimated, and units/scales visible.
- Show source lineage for important values where metadata exists.
- Avoid turning company pages into a registry or generic dashboard.
- Add detail progressively: start with the analyst's next decision, then expose
  drill-down.

Acceptance bar:

- An analyst can move from company identity to statements, indicators, source
  quality, refresh/export action, and next analysis step without losing context.

## 6. Critical Factors Monitor

Goal: connect data to the few variables that drive the investment thesis.

Planning reference: `docs/archive/planning-2026/audits/critical-factors-monitor-audit-plan.md` (archived).

Checklist:

- Start with 3 to 7 factors per covered company.
- Each factor needs name, thesis link, source, linked indicator, threshold,
  latest value, history/range, expected impact, confidence, evidence, alert
  state, and last reviewed date.
- Keep factor alerts tied to real data, not generic notifications.
- Distinguish sector factors from company factors.
- Show stale review dates and unavailable sources.
- Do not add factor scoring before source quality and thresholds are clear.

Acceptance bar:

- An analyst can say what matters for the company, what moved, and whether it
  changes the thesis or model.

## 7. Model / Forecast Workspace

Goal: convert audited history and drivers into explicit assumptions and
forecast outputs.

Checklist:

- Start from official financial history.
- Separate actuals, adjustments, assumptions, calculations, checks, and outputs.
- Support base/bull/bear/stress only when scenario data can be stored and
  exported clearly.
- Add reconciliation checks for balance sheet, cash flow, debt, and source
  completeness.
- Keep model formulas traceable to source rows, assumptions, or transformations.
- Version models when forecasts can change over time.
- Reconcile app output with Excel output.

Acceptance bar:

- A model user can explain what changed from history to forecast and trace the
  calculation back to source or assumption.

## 8. Valuation Workspace

Goal: connect forecast, peers, market data, and thesis to target value.

Checklist:

- Keep valuation separate from official reported data.
- Label market prices, peer multiples, beta/rate inputs, and consensus data as
  external or estimated where applicable.
- Support one valuation method at a time before adding multiple methods.
- Tie DCF, multiples, SOTP, sensitivities, and target price to model versions.
- Show current vs historical vs peer vs implied multiples with clear sources.
- Make premium/discount rationale explicit.
- Export valuation tables with assumptions and caveats.

Acceptance bar:

- An analyst can see how the target value was produced and which assumptions
  would change it.

## 9. Thesis / Recommendation Builder

Goal: help the analyst communicate a clear view.

Checklist:

- Build from evidence already present in company, sector, model, valuation, and
  critical-factor workflows.
- Include recommendation, horizon, target price, upside/downside, drivers,
  catalysts, risks, source evidence, and what would change the view.
- Separate fact, assumption, estimate, and opinion.
- Do not generate broad AI summaries without traceable inputs and caveats.
- Keep report/memo export as future direction until templates and source
  lineage are implemented.

Acceptance bar:

- A reader can understand what matters, what changed, what is priced in, and
  why the recommendation follows from the evidence.

## 10. Excel / Export

Goal: preserve analyst work in audit-ready files.

Checklist:

- No merged cells.
- Use Center Across Selection if visual spanning is needed.
- Freeze panes logically.
- Separate inputs, calculations, outputs, raw data, metadata, and checks.
- Keep formulas simple and traceable.
- Show dates, units, currencies, and scale.
- Separate historical and forecast periods.
- Use hierarchy and subtotals.
- Include balance sheet, cash flow, debt, and source/data-quality checks where
  relevant.
- Show negatives in parentheses and zeros as `-`.
- Generated files must open without Excel repair.

Acceptance bar:

- The workbook can be reviewed, audited, and reused without needing the app open.

## 11. UI Review Gate

Goal: keep the product minimalist, practical, and direct.

Checklist:

- Start with the analyst task.
- Remove repeated labels, decorative containers, generic helper text, and
  duplicate controls.
- Keep source, period, unit, method, state, caveat, and next action when they
  affect trust.
- Prefer compact tables for exact comparison.
- Prefer charts only when trend, range, or composition is the point.
- Keep loading, empty, stale, partial, unavailable, and error states close to
  affected data.
- Do not make a screen cleaner by hiding auditability.

Acceptance bar:

- The screen has fewer distractions, but the analyst has enough detail to make
  or defer a decision.

## 12. Documentation Gate

For each change, update the applicable owner documents in the same PR or explain
why no documentation update is needed in the PR's **Documentation impact**
section. Keep each detailed fact in one owner document; other docs should link
to it and carry only the summary needed by their readers.

| Change | Owner and update boundary |
|---|---|
| Documentation entry points or repository layout | [README](../README.md#canonical-documentation) owns the canonical index; [repository map](reference/repository-map.md) owns folder/tooling orientation. Update links or summaries when their targets change. |
| Runtime boundaries, routes or redirects | [Architecture](architecture.md) owns the detailed runtime and route inventory; keep route summaries elsewhere linked to it. |
| Implemented analyst behavior | [Product workflows](product-workflows.md) owns the capability inventory. Update only with implementation evidence; separate planned behavior. |
| Reusable product or UI patterns | [Product](PRODUCT.md) owns product/UI principles; [Design](DESIGN.md) owns visual and interaction patterns. Update when those contracts change, not for every screen edit. |
| Product direction or workspace scope | [Product direction](PRODUCT_DIRECTION.md) changes only when direction or ownership changes. |
| Development setup, modes or data paths | [Development](development.md) owns setup and the command map; [dev runtime and data paths](dev-runtime-and-data-paths.md) owns detailed path, mode and write-guard behavior. |
| Financial rules or source behavior | [Context](CONTEXT.md) owns financial domain rules; [data sources](data-sources.md) owns source classes, provenance and storage rules, with source-specific contracts linked from there. |
| Workbook behavior | [Excel exports](excel-exports.md) owns workbook structure, semantics and validation. |
| Packaging, updater or publication | [Build and release](build-release.md) owns artifact/build/updater/publication contracts; [release process](release-process.md) summarizes the publication sequence. |
| Project state, operating rules or durable decisions | [Status](STATUS.md) owns current state; [AGENTS.md](../AGENTS.md) owns operating rules; [decision records](decisions/README.md) preserve decision context and explicit lifecycle status. |

During the existing change review:

1. Compare the changed behavior or contract with its owner docs. Cite an active
   route, bridge/API method, table, source module, export path or test for
   implementation claims; mark unverified claims **Needs validation**.
2. Update the owner first, then affected links and summaries. Mark superseded
   records explicitly and point to their replacement; preserve historical
   rationale without presenting it as current instructions.
3. Check that the PR names the updated docs or explains why none changed, and
   that implemented capability remains separate from future direction.

Acceptance bar:

- A future contributor can tell what exists, what is planned, and what must not
  be inferred.
