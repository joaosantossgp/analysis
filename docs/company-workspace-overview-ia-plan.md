# Company Workspace Overview IA Plan

Purpose: define the first practical information-architecture pass for the
Company Overview screen. This is a planning document only; it does not authorize
feature implementation, new routes, schema changes, or bridge changes.

## Product Intent

The Company Overview should answer three analyst questions quickly:

```text
Is this company ready for analysis?
What evidence is available?
What should I inspect next?
```

It should be minimalist, practical, and direct. Less is more useful when it
removes repeated labels, decorative containers, ambiguous actions, and low-value
helper text. Less is not useful when it hides source, period, unit, method,
data quality, or the next analytical action.

## Current Evidence

Verified current surfaces:

- `apps/desktop-web/src/routes/CompanyDetailPage.tsx` renders the Overview route
  at `/empresas/:cdCvm`.
- The current Overview is composed of `EntityHeader`, `CompanyCommandBar`,
  `MarketHistoryPanel`, and a compact financial indicator panel.
- `CompanyCommandBar` already exposes update, history download, export, export
  details, refresh status, latest period, years available, and model update
  metadata.
- `EntityHeader` already exposes company identity, CVM id, CNPJ, B3 ticker,
  CVM/GICS sector metadata, local data status, latest period, available years,
  and mapped energy/utility connections where available.
- Existing Company sub-navigation is Overview, Financial Statements, Model
  Mapping, and Coverage Status.

## IA Decision

Do not add a new Company route first.

Do not add a standalone readiness band. A first implementation attempt showed
that a separate "Analysis readiness" panel mostly duplicated data already shown
in `EntityHeader`, `CompanyCommandBar`, and the evidence panels. It added visual
weight without adding analytical function.

Treat this as a general product error: redundant summary panels are not
minimalism. They are noise unless they add a new decision, a new action, or a
source/method drill-down that is not available in the surrounding UI.

The first Company Workspace change should improve the usefulness of existing
surfaces instead of creating another summary layer.

## Target Overview Hierarchy

1. Company identity and source status

   Keep `EntityHeader` as the identity anchor. It should remain the place for
   company name, ticker, CVM id, CNPJ, sectors, latest period, local data status,
   available years, and mapped operating connections.

2. Existing status and action surfaces

   Keep readiness information where it already belongs:

   - company identity, sectors, ticker, local data, latest period, and years in
     `EntityHeader`;
   - refresh, export, history download, and local data status in
     `CompanyCommandBar`;
   - market-data availability inside `MarketHistoryPanel`;
   - company indicator availability inside the indicator panel.

   Avoid repeating the same value in a new Overview card unless the new UI adds
   a decision, action, or source drill-down that does not already exist.

3. Primary actions

   Keep the first action set small:

   - Update data;
   - Inspect statements;
   - Review Excel mapping;
   - Export workbook.

   These actions match the current workflow better than adding future modules
   such as Valuation, Thesis, or Critical Factors before they exist.

4. Evidence preview

   Keep the current two evidence panels:

   - market history;
   - financial indicators.

   The panels should clarify what is being previewed, the period/unit when
   available, and where the analyst can inspect underlying data.

5. Secondary actions

   Keep lower-priority actions visible but quieter:

   - download selected history;
   - export details;
   - open coverage status;
   - view underlying indicator data.

## Workspace Boundaries

The Overview is not the whole Company Workspace.

| Area | Overview role | Dedicated surface |
| --- | --- | --- |
| Identity | summarize | `EntityHeader` |
| Statements | show readiness and link | Financial Statements |
| Market data | preview | Market History panel / export |
| Indicators | preview company financial indicators | Compact indicator panel |
| Coverage | show status if available | Coverage Status |
| Excel | export and mapping entry point | Model Mapping / export flow |
| Critical Factors | future only | not shown until designed |
| Valuation | future only | not shown until models/peers exist |
| Thesis | future only | not shown until factors/model/valuation exist |

## Copy Rules

- Use "Excel mapping" or "Model export mapping" for the current mapping surface.
  Do not imply a full forecasting model exists.
- Use "Financial Statements" for official CVM statement review.
- Use "Company indicators" for company-level metrics. Do not place these inside
  the general Indicator Library.
- Avoid "Valuation", "Thesis", "Recommendation", and "Critical Factors" labels
  in the live Company UI until those workflows are implemented.
- Use explicit data states: available, missing, stale, unavailable, updating,
  failed.

## Minimalist Layout Rule

The first viewport should not become a dashboard wall.

Recommended order:

1. Identity header.
2. Command bar for update, history, and export.
3. Two evidence previews.
4. Drill-down affordances inside each evidence panel, only where they add
   analytical value.

Avoid nested cards, decorative sections, large onboarding text, and duplicate
status messages. Status belongs closest to the action or evidence it affects.

## Data And Audit Rules

Every readiness item must be explainable from existing data:

```text
visible status -> field/state used -> source surface -> timestamp/period when available
```

Do not silently combine official CVM data, B3/market data, Yahoo/yfinance data,
or calculated metrics without a visible label where the distinction matters.

## First Implementation Slice When Authorized

When implementation is explicitly authorized, keep the first slice narrow:

- remove duplicated status text where it exists across header, command bar, and
  panels;
- make one existing panel more useful by adding a real decision aid, such as a
  latest-value/change summary or clearer source/action drill-down;
- use existing `CompanyInfo`, years, refresh, export, market, and KPI states;
- keep `CompanyCommandBar` behavior intact unless simplifying repeated copy or
  grouping actions is required;
- do not add new data calls unless a missing readiness state cannot be derived
  safely from existing calls.

## Do Not Build In This Slice

- no new Company tabs;
- no Critical Factors UI;
- no Valuation UI;
- no Thesis UI;
- no forecast model UI;
- no new database fields;
- no new import pipeline;
- no changes to the legacy or archived app.

## Acceptance Criteria

The Overview IA is aligned when:

- an analyst can see company identity, data readiness, and next actions without
  scanning multiple unrelated panels;
- existing capabilities are not overstated;
- official, external, calculated, and missing data states remain clear;
- Excel export remains a central output;
- Company-specific metrics stay in the Company Workspace, not the general
  Indicator Library;
- future analyst workflows are not presented as implemented features.

## Validation Plan For Future UI Work

After any future TS/TSX change to this screen:

- run `npm --prefix apps/desktop-web run typecheck`;
- manually check a company with local data;
- manually check a company without local data;
- check refresh loading, success, stalled, and error states when possible;
- check export unavailable and export success states when possible;
- verify the layout at narrow and desktop widths.

## Open Questions Before Implementation

- Which existing field should be the canonical source for statement readiness?
- Can coverage status be displayed on Overview without adding a slow or fragile
  fetch?
- Should the sub-navigation label remain "Model Mapping", or should only the
  page copy clarify that this is Excel mapping rather than a full model?
