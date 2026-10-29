# Critical Factors Monitor Audit And Plan

## Purpose

Define the next product lane for Critical Factors without implementing it yet.

Critical Factors should become the bridge between source-backed data and analyst
judgment. It should answer:

- what matters for this company;
- what changed;
- why it matters financially;
- whether the thesis, model, or valuation needs review.

This is not an alerts feature, valuation page, AI summary, or generic task list.

## Current Evidence

Verified from active docs and code:

- `docs/PRODUCT_DIRECTION.md` defines Critical Factors as future direction.
- `docs/PRODUCT_DEVELOPMENT_CHECKLIST.md` defines the expected factor fields and
  acceptance bar.
- `docs/company-workspace-gap-audit.md` marks Critical Factors as missing/future
  and says not to show the area until designed.
- `docs/company-workspace-overview-ia-plan.md` says not to expose Critical
  Factors labels in the live Company UI until the workflow exists.
- `apps/desktop-web/src/routes/CompanyDetailPage.tsx` has company financial
  indicators and market history, but not factor objects.
- `apps/desktop-web/src/routes/CompanyStatementsPage.tsx` and
  `apps/desktop-web/src/routes/CompanyModelMappingPage.tsx` now expose source,
  method, and Excel lineage context.
- `apps/desktop-web/src/components/indicators/explorer/IndicatorDetailPanel.tsx`
  exposes indicator metadata such as source, methodology, coverage, quality, and
  refresh state.
- `apps/desktop-web/src/routes/CompanyCoveragePage.tsx` manages coverage tier,
  checklists, and decision history, but it is administrative rather than a
  factor monitor.

No active route, bridge method, or database model was found for company-specific
critical factors.

## Product Gaps

### 1. No Factor Object

The product has indicators, statements, market data, coverage decisions, and
Excel mapping, but no object that says:

```text
factor -> linked data -> threshold -> financial impact -> thesis implication
```

Without that object, the analyst can inspect data but cannot formally track what
matters for a company.

### 2. Coverage Does Not Become Analysis

Coverage workflows can decide what companies deserve attention, but the handoff
to company analysis stops at checklists and rationale. There is no structured
place to convert a coverage rationale into the 3 to 7 drivers the analyst will
monitor.

### 3. Indicator Library Is Not Enough

The Indicator Library correctly holds macro, sector, system, market, and
benchmark indicators. Critical Factors should reference those indicators, but
they are company-specific judgments. They belong in the Company Workspace, not
inside the general Indicator Library.

### 4. Existing Placeholder Pattern Should Not Be Repeated

The Company Coverage page includes a "Valuation Factors & Peers" placeholder
that states the data is not available. This pattern should not be used for
Critical Factors. Empty future panels create noise and make the app feel
unfinished.

### 5. Alerts Are Too Early

Alerts require trusted thresholds, source freshness, linked indicators, review
dates, and user-confirmed materiality. Building alert UI before those foundations
would create false precision.

## Target Factor Definition

Each covered company should eventually have 3 to 7 factors.

Minimum fields:

| Field | Purpose |
| --- | --- |
| Factor name | Short analyst-facing name, such as PLD, leverage, tariff review, or volume. |
| Thesis link | Why this factor matters to the investment view. |
| Category | Sector, company, financial, market, regulatory, operational, or event. |
| Linked indicator | Source-backed indicator, financial metric, market series, event, or manual assumption. |
| Source class | Official CVM/B3, official external dataset, external/unofficial, calculated, or manual. |
| Materiality threshold | The condition that makes the factor worth review. |
| Latest value | Current observed value, if data-backed. |
| Historical range | Context for whether the latest value is normal, extreme, or unavailable. |
| Expected impact | Revenue, margin, EBITDA, FCF, leverage, valuation, or thesis impact. |
| Confidence | How reliable the link and source are. |
| Evidence | Notes, source references, filings, indicator links, or model links. |
| Status | Normal, watch, moved, breached, stale, source unavailable, or needs review. |
| Last reviewed | Analyst review timestamp. |

Do not add scoring until thresholds, confidence, and source quality have clear
rules.

## Workspace Boundary

Critical Factors belong in the Company Workspace.

Related surfaces:

| Surface | Role |
| --- | --- |
| Coverage | Decides whether the company deserves attention and records rationale. |
| Sector Workbench | Defines common sector drivers and source-backed sector context. |
| Indicator Library | Provides reusable macro, sector, system, market, and benchmark indicators. |
| Company Overview | May show a compact factor summary only after factors exist. |
| Critical Factors | Owns company-specific factor definition, monitoring, evidence, and review. |
| Model / Excel | Converts factor movement into explicit assumptions or model checks. |
| Thesis | Uses factors as evidence for recommendation, risks, and what would change the view. |

## First MVP Scope

The first implementation should be a definition and review workflow, not alerting.

### MVP: Factor Register

Goal:

- Allow an analyst to define 3 to 7 company-specific critical factors with
  source links and review metadata.

In scope:

- factor list for one company;
- add/edit/archive factor;
- category, linked indicator/source, threshold text, expected impact, confidence,
  status, and last reviewed date;
- evidence notes;
- source/method display when linked data supports it;
- local-first persistence;
- explicit empty state telling the analyst to add factors only after coverage and
  source review.

Out of scope:

- automated alerts;
- AI-generated thesis;
- valuation impact calculations;
- forecast model edits;
- peer comparison;
- push notifications;
- hidden fallback from missing indicator data to manual values.

## IA Proposal

Do not add the tab until storage and bridge behavior exist.

When implemented, add a Company subtab:

```text
Critical Factors
```

Suggested page structure:

1. Company header and existing source status.
2. Factor table:
   - factor;
   - category;
   - linked source;
   - latest value;
   - threshold;
   - status;
   - last reviewed.
3. Selected factor inspector:
   - thesis link;
   - evidence;
   - source lineage;
   - expected financial impact;
   - review notes.
4. Quiet actions:
   - add factor;
   - mark reviewed;
   - archive;
   - open linked source.

Avoid a large readiness band. A summary is only useful if it adds a new action
or source/method drill-down.

## Data And Audit Principles

- Every data-backed factor must show source, unit, period, timestamp, and
  source class.
- Manual factors must be labeled as manual.
- Calculated factors must expose formula or transformation.
- Missing linked data must render as unavailable, not zero.
- External/unofficial sources must never be mixed with official CVM/B3 data
  without labels.
- Factor status should be explainable from threshold, review date, source
  freshness, or analyst override.
- Factor changes must be auditable locally.

## Suggested Phases

### Phase 0: Foundation Gate

- Do not start Critical Factors until the target sector has enough source-backed
  drivers to support useful company factors.
- For Energy/Utilities, use
  `docs/energy-utilities-source-driver-readiness-audit.md` first.
- Build source contracts, local storage, read models, ownership mapping, and
  source-status UI before factor alerts or scoring.

### Phase 1: Requirements And Source Map

- Pick one pilot sector, preferably Energy/Utilities.
- List 8 to 12 possible sector drivers.
- Map each driver to existing app sources, missing sources, and source quality.
- Choose 3 to 7 sample company factors only after the source map shows enough
  usable evidence for a real covered company.

### Phase 2: Local Factor Register

- Add local persistence and bridge methods for factor CRUD.
- Keep the UI table-first and dense.
- Add explicit source/manual/calculated labels.
- Add tests for create/update/archive and missing linked source behavior.

### Phase 3: Review Workflow

- Add last reviewed date, stale review state, and evidence notes.
- Link coverage rationale to initial factor creation where possible.
- Add "mark reviewed" with audit history.

### Phase 4: Source-Backed Monitoring

- Resolve linked indicators and financial metrics.
- Show latest value, historical range, and threshold status.
- Keep unavailable/stale source states visible.

### Phase 5: Model And Thesis Handoff

- Link factors to model assumptions or Excel mapping outputs.
- Expose which factors changed since last review.
- Feed future thesis/recommendation builder with source-backed evidence.

## Not Yet

Do not build these first:

- alert center;
- dashboard cards;
- factor score;
- AI-generated factor list;
- valuation sensitivity;
- thesis recommendation;
- push notifications;
- sector-wide factor monitor for all companies.

## Acceptance Criteria

The Critical Factors lane is ready for implementation when:

- the target factor fields are agreed;
- at least one pilot sector has a driver-to-source map;
- missing and external data rules are explicit;
- factor ownership inside Company Workspace is confirmed;
- the first UI can be built without empty future panels;
- the feature can explain every factor as:

```text
factor -> linked data/manual evidence -> threshold -> status -> expected impact -> review history
```
