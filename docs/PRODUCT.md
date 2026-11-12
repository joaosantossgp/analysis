# Product

## Register

product

## Users

Financial market analysts in Equity, Credit, IB, and related areas, plus analytical investors who need to compare Brazilian companies, read historical indicators, validate financial statements, and decide where to go deeper. Usage is focused: desktop, dense data, and verification of periods, companies, sectors, operational assets, and financial signals.

## Product Purpose

CVM Analytics turns public CVM financial statements into a local, queryable, and auditable experience. The product exists to reduce friction between raw regulatory data and a trustworthy financial reading: find companies, inspect indicators, check statements, update the local database, and keep enough traceability to support analytical decisions.

## Core Product Principle: Minimalism

Minimalism is a core principle of CVMAnalytics.

In this product, minimalism does not mean fewer features or hiding important information. It means showing the right information with strong hierarchy, low friction, consistent patterns, and no unnecessary visual or textual noise.

Design decision: less is more useful when it reduces visible choices, repeated labels, decorative containers, and generic text. Less is not useful when it removes the source, period, unit, method, caveat, state, or next action the analyst needs to trust the result.

The interface should help the analyst move quickly from:

- selecting a company, sector, portfolio, or asset;
- source data;
- indicator;
- historical trend;
- financial interpretation;
- export or next action.

Practical rules:

- Be direct without removing material context.
- Prefer dense, readable, professional layouts over decorative dashboards.
- Show summary first and detail on demand.
- Avoid repeated labels, vague helper text, redundant cards, and generic dashboard patterns.
- Treat redundant panels as a product bug: a summary should exist only if it adds a decision, action, or source/method drill-down the screen does not already offer.
- Standardize tables, indicators, filters, and charts across pages.
- Preserve auditability: source, period, unit, currency, consolidation, and calculation method must remain accessible.
- Never hide failures, missing data, partial sources, or quality problems to make the screen look "clean".
- Empty, loading, and error states must be explicit, useful, and close to the affected component.
- The interface should support fast professional judgment, not casual browsing.

## Primary navigation and Home

Home, Companies, Sectors and Indicators are primary workspaces. Settings remains
visible as a utility; Coverage and News remain accessible through More, direct
routes and the command palette. This is a hierarchy change, not removal of those
workflows or their data.

An empty Home offers Open Companies. The explicitly chosen recommended layout
contains Watchlist and Market Price; Database Monitor, Priority Queue and News
remain optional widgets. Existing v4 layouts and configurations are preserved.
The compact status/job summary and source/error/offline states remain visible.

## Brand Personality

Technical and auditable, precise, sober, and premium. The interface should convey operational confidence, financial domain expertise, and attention to detail, without looking decorative or promotional.

## Anti-references

It must not look like a generic SaaS dashboard, a fintech landing page, a neon crypto panel, a raw corporate spreadsheet, or a tool that sacrifices traceability for flashy charts.

## Design Principles

- Clarity before impact: emphasize hierarchy, period, source, and data state before visual effects.
- Operational minimalism: remove visual and textual noise while keeping material information, auditability, and clear paths to go deeper.
- Density with control: allow rich comparative reading without overloading the user with ornaments or duplicated controls.
- Visible auditing: states, filters, coverage, errors, and data origin must be understandable when they matter for the decision.
- Premium sobriety: use the dark theme, accents, and spacing to create focus and confidence, not spectacle.
- Reliable local flows: optimize for desktop use with local SQLite and predictable behavior without depending on remote services.

## Page Review Workflow

When a page is reviewed, the work must be incremental and based on the real implementation. The agent must:

1. Inspect the route, active components, data facades, and existing states.
2. Compare the page against the operational minimalism principle.
3. Separate the essential, secondary context, and optional detail.
4. Propose small, targeted changes before any broad redesign.
5. Preserve working flows, existing data, sources, exports, and error states.
6. Validate loading, empty, error, partial data, responsiveness, and perceived performance.
7. Report risks, assumptions, and uncertainties that affect product decisions or data quality.

## Accessibility & Inclusion

Target WCAG AA for body text, controls, visible focus, and component boundaries. Charts and indicators must not rely on color alone: legends, labels, tooltips, and text states must carry the meaning. Respect reduced-motion preferences and keep keyboard navigation working in filters, selectors, tabs, and tables.
