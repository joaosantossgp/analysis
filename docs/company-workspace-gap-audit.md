# Company Workspace Gap Audit

Date: 2026-07-08

## Purpose

This audit maps the current Company workspace against the product direction in
`docs/PRODUCT_DIRECTION.md` and the next-step recommendation in
`docs/product-gap-audit.md`.

This is an information-architecture audit only. It does not authorize UI,
schema, bridge, ingestion, or export changes.

## Evidence Inspected

Company route and navigation evidence:

- `apps/desktop-web/src/App.tsx`
- `apps/desktop-web/src/components/shell/SubNav.tsx`
- `apps/desktop-web/src/routes/CompaniesPage.tsx`
- `apps/desktop-web/src/routes/CompanyDetailPage.tsx`
- `apps/desktop-web/src/routes/CompanyStatementsPage.tsx`
- `apps/desktop-web/src/routes/CompanyModelMappingPage.tsx`
- `apps/desktop-web/src/routes/CompanyCoveragePage.tsx`
- `apps/desktop-web/src/components/EntityHeader.tsx`
- `apps/desktop-web/src/components/CompanyCommandBar.tsx`
- `apps/desktop-web/src/lib/api/companyDetail.ts`
- `apps/desktop-web/src/lib/api/companies.ts`
- `apps/desktop-web/src/lib/api/exports.ts`

Product direction evidence:

- `docs/PRODUCT_DIRECTION.md`
- `docs/PRODUCT_DEVELOPMENT_CHECKLIST.md`
- `docs/product-gap-audit.md`
- `docs/product-workflows.md`
- `docs/excel-exports.md`
- `docs/data-sources.md`

## Current Company Workspace

Current company routes:

| Surface | Route | Current role |
| --- | --- | --- |
| Company directory | `/empresas` | Entry point through `CompaniesTable`. |
| Overview | `/empresas/:cdCvm` | Company identity, local data status, update/export command bar, market history, financial indicators. |
| Financial Statements | `/empresas/:cdCvm/demonstrativos` | DRE/BPA/BPP/DFC statement grid with account search and source footer. |
| Model Mapping | `/empresas/:cdCvm/model-mapping` | Excel Model sheet preview, mapping validation, source-line audit, saved mapping export. |
| Coverage Status | `/empresas/:cdCvm/coverage` | Company membership, tier, checklist, rationale, decision history for an active coverage universe. |

Current top-level Company subnav:

```text
Overview
Financial Statements
Model Mapping
Coverage Status
```

## What Already Works

### Identity And Local Status

`EntityHeader` gives the company workspace a strong base:

- company name and commercial name;
- B3 ticker and CVM identifier;
- CNPJ;
- CVM sector;
- GICS sector/subindustry when available;
- local financial data status;
- latest readable period;
- readable years count;
- financial/distribution/generation connection chips.

This supports the product direction well because it starts with identity,
classification, local readiness, and source coverage.

### Local Data Operations

`CompanyCommandBar` provides useful local-first operations:

- local data status;
- update data;
- selected-history download;
- refresh progress and diagnostics;
- Excel export;
- export details;
- browser-mode unavailable state;
- failed/stalled/no-data handling.

This is a strong foundation. It should remain stable.

### Financial Evidence

The statements page provides a clear evidence surface:

- statement selector for DRE/BPA/BPP/DFC;
- latest available years;
- searchable account rows;
- account code and source labels;
- rows/period counts;
- conflict exclusion status;
- source footer noting local CVM filings and R$ thousands.

This is one of the clearest implementations of "evidence first."

### Indicator And Market Context

The overview combines market history and financial indicators. The indicator
panel handles loading, no data, browser-only, unavailable, and selected-series
states. This gives the company page useful analytical density.

### Excel Model Export Mapping

The model mapping route is valuable, but its current role is specific:

- preview the Excel Model sheet;
- audit source lines;
- validate mapping;
- save mapping presets;
- export using the selected mapping.

This is not yet a forecast model workspace. It is an Excel export mapping and
audit workspace.

### Coverage Context

The company coverage route links a company to an active universe, tier,
rationale, checklist, and decision-history log. This is useful, but it feels
more like a coverage administration panel than a company-analysis status view.

## Main IA Gaps

### 1. The Current Navigation Names Are Accurate But Incomplete

The existing subnav describes implemented surfaces, but it does not express the
target analyst workflow:

```text
Identity -> Evidence -> Drivers -> Sources -> Model/Excel -> Coverage -> Future thesis
```

Current navigation lacks explicit homes for:

- Sources / lineage;
- Drivers;
- Risks / events;
- Peers;
- Critical Factors;
- Valuation;
- Thesis.

Those future areas should not be shown as active tabs yet, but the IA should
leave room for them.

### 2. Overview Is Doing Too Many Jobs

Overview currently combines:

- local data status;
- update/export actions;
- market history;
- financial indicators;
- implicit source state through header chips.

This is useful, but the screen does not yet clearly answer:

- What is the analyst supposed to review next?
- Is this company ready for analysis?
- What data is missing or stale?
- Which evidence supports the visible numbers?
- Should the user inspect statements, update data, check coverage, or export?

The first screen needs stronger task hierarchy, not more widgets.

### 3. Sources Are Present But Not A Workspace

Source context exists across:

- header local-data status;
- statement footer;
- model mapping raw lines and validation;
- export metadata;
- Settings/source docs;
- data-source documentation.

But the company workspace does not yet give users a simple source-readiness
view for the company.

Near-term opportunity:

- expose source readiness inside Overview using existing metadata;
- link users to Statements, Model Mapping, Coverage Status, or Settings when a
  source issue needs deeper inspection.

Do not build a generic source hub yet.

### 4. Model Mapping Name Can Overstate The Current Capability

`Model Mapping` is accurate for Excel export mapping, but the broader product
direction uses "Model / Forecast Workspace" for future forecasting, scenarios,
versioning, and valuation inputs.

Risk:

- Users and contributors may interpret `Model Mapping` as a full model builder.

Near-term rule:

- Keep the route, but describe the surface as `Model Export Builder` or
  `Excel Mapping` in product language until forecast modeling exists.

### 5. Coverage Status Is Too Administrative For The Company Workspace

The route provides useful coverage membership and checklist behavior, but it is
currently oriented around:

- selecting active workspace;
- setting tier;
- entering rationale;
- checking deliverables;
- audit history.

For company analysis, the useful question is:

- Why is this company in coverage, what remains incomplete, and what should be
  reviewed next?

Near-term rule:

- Keep administrative coverage controls, but add a future distinction between
  `Coverage Setup` and `Coverage Readiness`.

### 6. Future Analyst Areas Should Be Named In The IA Plan, Not The UI Yet

The target product direction includes:

- Drivers;
- Sources;
- Events;
- Risks;
- Critical Factors;
- Peers;
- Model / Forecast;
- Valuation;
- Thesis.

These are not verified active company workspaces. Do not add visible empty tabs
for them until the underlying data and behaviors exist.

## Target Company IA

Use this as the future company workspace map:

| Target area | Current status | Near-term treatment |
| --- | --- | --- |
| Overview | Implemented | Keep, but make it more decision-oriented. |
| Financials | Implemented through Statements + indicators | Keep Statements as the evidence surface; do not hide raw account detail. |
| Sources | Partial across statements, mapping, exports, Settings | Add source-readiness summary only when backed by existing metadata. |
| Drivers | Partial through indicators/market history | Do not create a new tab yet; clarify which visible indicators are company drivers. |
| Coverage | Implemented but administrative | Reframe as coverage readiness plus setup controls. |
| Model / Excel | Implemented as Excel mapping/export foundation | Keep current mapping/export behavior; avoid forecast claims. |
| Critical Factors | Missing / future | Do not show yet. Define requirements after Overview/Source readiness. |
| Peers | Missing / future | Do not show yet; depends on peer/source rules. |
| Valuation | Missing / future | Do not show yet; depends on forecast model. |
| Thesis | Missing / future | Do not show yet; depends on critical factors, model, and valuation. |

## Recommended First Change

The smallest useful next change is not a new route. It is an Overview IA pass.

Goal:

- Make `/empresas/:cdCvm` answer: "Is this company ready for analysis, what
  evidence is available, and what should I inspect next?"

Recommended first-screen structure:

1. Company identity and local data status.
2. Analyst readiness strip:
   - latest period;
   - years available;
   - statements available/missing;
   - market data availability;
   - coverage membership/status if available;
   - export readiness.
3. Primary next actions:
   - update data;
   - inspect statements;
   - review model export mapping;
   - open coverage status;
   - export workbook.
4. Evidence preview:
   - financial indicators;
   - market history;
   - source/period/method caveats close to each preview.

This keeps the page minimalist: fewer vague panels, clearer hierarchy, no
future tabs without working data.

## What Must Remain Stable

- Company directory route `/empresas`.
- Company overview route `/empresas/:cdCvm`.
- Statement route `/empresas/:cdCvm/demonstrativos`.
- Model mapping route `/empresas/:cdCvm/model-mapping`.
- Coverage status route `/empresas/:cdCvm/coverage`.
- Existing bridge facade path through `apps/desktop-web/src/lib/api/*`.
- Company refresh behavior through `CompanyCommandBar`.
- Company workbook export behavior.
- Statement source/account detail.
- Browser-only and desktop-bridge unavailable states.
- Existing loading, empty, error, stale, and unavailable states.

## What Not To Do Next

- Do not add empty tabs for Critical Factors, Valuation, Thesis, or Peers.
- Do not rename implementation routes before deciding compatibility behavior.
- Do not build forecast modeling inside the current mapping page.
- Do not hide statement detail to make Overview cleaner.
- Do not collapse coverage rationale/history into a decorative status badge.
- Do not add AI thesis summaries.

## Proposed Next Deliverable

Before implementation, write a narrow design plan:

```text
docs/company-workspace-overview-ia-plan.md
```

It should define:

- the exact Overview hierarchy;
- which existing fields power the readiness strip;
- which actions appear as primary vs secondary;
- how source/method caveats appear without clutter;
- what remains explicitly future;
- the smallest validation path in the Vite desktop app.

## Audit Conclusion

The Company workspace is the right next product lane. It already has enough
real functionality to become the center of the analyst workflow without a schema
or feature expansion. The immediate need is information architecture: make the
existing evidence, data status, refresh/export actions, statements, mapping, and
coverage context read as one coherent company analysis workspace.
