# Design

This document owns visual and interaction rules for the active Vite desktop UI.
Product principles live in [PRODUCT.md](PRODUCT.md); integration and state
acceptance live in the [Vite UI contract](skills/CVMANALYTICS_VITE_UI_SKILL.md).

## Implemented design system

The executable token definitions are in
[`apps/desktop-web/src/index.css`](../apps/desktop-web/src/index.css).
Reuse its Tailwind v4 utilities instead of copying values into components.

| Role | Implemented tokens / fonts |
|---|---|
| Surfaces | `surface-0` through `surface-4` (neutral black/gray) |
| Borders | `border-subtle`, `border-default`, `border-strong`, `border-focus` |
| Text | `text-primary`, `text-secondary`, `text-tertiary`, `text-disabled` |
| Actions and focus | `action-primary` and its hover/active/muted variants (orange) |
| Operational states | `state-ok`, `state-warn`, `state-err`, `state-info` |
| Financial numbers | `num-pos`, `num-neg`, `num-neutral`, `num-flag-high`, `num-flag-low` |
| Identifiers and charts | `id-ticker`, `id-link`, `chart-1` through `chart-6` |
| UI font | Inter with system fallbacks; bundled locally |
| Numeric font | JetBrains Mono with system fallbacks; bundled locally |

Earlier teal/OKLCH palettes and Space Grotesk/Manrope/IBM Plex font specifications
were not the implemented Vite theme. They are not requirements for maintenance.
Any palette, font or component-library migration needs its own approved scope.
`@base-ui/react` is not installed; reuse the existing components and check
package.json before proposing another library. Use `getSectorColor` for sector
semantics where the existing UI uses it.

## Visual rules

- Dense, readable, analyst-grade layouts. Use compact controls, a clear hierarchy
  and tonal surfaces; avoid ornamental dashboards, gradients and nested cards.
- Use semantic colors sparingly. Status, financial sign, entity identity and
  chart series are separate roles. Always pair color with labels or symbols.
- Use tabular numbers and right alignment for numeric columns; left-align text.
  Put exact scale/currency in headers and show missing values as an em dash.
- Keep source, period, currency, units, consolidation, method and quality
  accessible next to the evidence. Do not sacrifice them to visual minimalism.
- Match existing spacing, radii and control sizes from index.css and the nearest
  shared component. Do not introduce a second token vocabulary.
- Preserve visible keyboard focus, meaningful labels, accessible close paths,
  practical WCAG AA contrast and reduced-motion preferences.
- Bundle fonts locally. Do not copy proprietary terminal branding or visual
  identity; use general principles of information density and clarity.

## Workspace patterns

### Navigation and workspace ownership

Home, Companies, Sectors and Indicators are the primary workspaces; Settings
remains visible as a utility. Follow the existing
[primary navigation](../apps/desktop-web/src/components/shell/ModuleNav.tsx#L16)
and [contextual tabs](../apps/desktop-web/src/components/shell/SubNav.tsx#L16).

Companies owns Directory, Coverage and Assets & Mapping. Keep those three tabs
on the directory, Coverage and asset-mapping surfaces. Within Coverage, show
Prioritization, Work Queue and Capacity when a universe is selected. Company
detail uses its own issuer-level tabs described below. Keep analyst Coverage
inside Companies distinct from company Coverage Status and Settings' local-data
coverage. Indicators retains Library and Energy; indicator source health belongs
in Settings.

News is retired from active workspaces. Existing News URLs and saved Home widgets
show retirement notices without querying news; preserve saved settings and data,
and leave widget removal to the user. Do not offer new News navigation or widgets.
See the [product ownership contract](PRODUCT.md#primary-navigation-and-home) and
[current routes and compatibility behavior](architecture.md#active-routes).

### Analytical Workspace Patterns

The Indicator Library detail redesign establishes a reusable pattern for dense
analytical pages across the app. Treat it as the baseline for Companies (including
Coverage and Assets & Mapping), Sectors, Indicators and future Modeling surfaces
when the user must select an entity or metric and inspect evidence without
losing context.

**Index plus detail.** A table, list, or grid is usually an index into analysis,
not the final destination. It should support search, filtering, comparison, and
selection. Selecting a row should open the relevant evidence or actions in
place when that preserves an active analytical task. Navigation is appropriate
when the selection opens a deeper workspace, such as a Companies directory row
opening `/empresas/:cdCvm` as the issuer workspace.

**Detail preserves context.** Detail panels, drawers, and inspectors should
stay within the visible work area, respect the right content margin, and follow
the user's scroll position. On wide screens, prefer a right-side panel that
compresses the index. On narrow screens, stack the detail below the index. When
the evidence is chart-heavy or table-heavy, allow resizing and fullscreen
inspection instead of making the whole page wider.

**Charts are first-class evidence.** When a time series exists, a chart should
usually be the primary preview, with the table available for audit and exact
values. Use a shared chart grammar: compact controls, chart-type switching,
options inside the chart bounds, visible legends, editable series where
supported, explicit units/periods, and empty/error states close to the chart.

**Metadata belongs near the evidence.** Unit and period belong with the chart,
table header, or value. Source and domain belong immediately near the evidence
they qualify. Definitions belong behind inline help next to the indicator,
metric, column, or page title. Internal ids, implementation paths, and broad
metadata grids should stay out of the primary visual hierarchy unless the user
is in an audit or source-review workflow.

**Selection replaces redundant commands.** Avoid dedicated `Open` columns and
repeated action buttons when row selection is the natural action. Keep
favorites, help, status, and row-level actions attached to the object they
modify, not spread across low-value columns.

**Panels are bounded tools, not floating dashboards.** A side panel should be
anchored to the table or workspace it explains. It must not float outside the
page margin, cover unrelated navigation, or make the source table unusable at a
normal laptop width.

**Useful catalogs open useful data.** A library, directory, or hub should not
stop at metadata when local data is available. It should open a useful chart,
table, source state, or action directly. If only a definition is available, the
UI must say so plainly instead of implying that data failed to load.

### Company Workspace Pattern

The Company area should become the clearest expression of the app's design
system because it is the main issuer-level analyst workspace.

**Company identity is the workspace spine.** Company name, ticker, CVM id,
CNPJ, sector classification, local data status, latest period, and mapped
operating connections anchor the workspace. Sub-tabs should feel like different
modes of work on the same company, not separate dashboards.

**The directory is an index.** The Companies page should optimize for selecting,
filtering, comparing, and prioritizing issuers. It should not become a generic
company-card dashboard. Dense rows, coverage/source status, and direct
selection matter more than decorative summaries.

**Overview answers readiness, evidence, and next action.** The first company
screen should answer: is this company ready for analysis, what evidence is
available, and what should the analyst inspect next? It should reuse the
identity header, command bar, market preview, and company indicators instead of
adding redundant readiness cards.

**Company tabs are workflow modes.** The issuer context offers Directory as the
return path, plus Overview, Financial Statements and Coverage Status. Financial
Statements is the official evidence surface; Coverage Status provides company
readiness and setup context. Excel Mapping remains an export/model-mapping
action with a dedicated window, rather than a company tab or forecast model
([command](../apps/desktop-web/src/components/CompanyCommandBar.tsx#L131),
[window route](../apps/desktop-web/src/App.tsx#L85)). Future Critical Factors,
Peers, Valuation and Thesis tabs should appear only when they have source-backed
behavior.

**Company-specific indicators stay inside the Company workspace.** Do not move
issuer metrics into the general Indicator Library. The Library owns macro,
sector, system, market, and benchmark indicators that open without an entity
selector. Company metrics belong next to company identity, company periods,
company source state, and company exports.

**Evidence panels should drill down in place.** Company indicator rows, market
series, statement accounts, coverage checklist items, and mapping rows should
prefer contextual detail panels or bounded drill-downs before adding new pages.
Navigation remains appropriate when the user is intentionally entering a deep
workspace. In the Companies directory, row activation should navigate to
`/empresas/:cdCvm`; inside the issuer workspace, contextual detail should
preserve the current analytical context whenever practical.

## Tables, charts and bounded panels

- Keep long table headers visible during vertical scrolling; selection must
  remain identifiable when detail opens.
- Charts need readable units, periods and legends; do not connect missing
  observations or use decorative fills to hide sparse data.
- Use a shared chart grammar: compact controls, chart/table switching when
  available, and source/method access near the plotted evidence.
- Details must preserve a usable main table at laptop width. Prefer an anchored
  right panel on wide screens and a stacked or explicitly dismissible view on
  narrow screens. Support resize/fullscreen where dense evidence needs it.
- On failure or missing data, retain navigation and a useful next action.
  Loading, empty, partial and stale states are part of the product, not polish.

Validation and reporting requirements are defined once in
[AGENTS.md](../AGENTS.md); follow the [Vite UI contract](skills/CVMANALYTICS_VITE_UI_SKILL.md)
for bridge-specific checks.
