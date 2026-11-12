# Indicators Module

Active reference for the desktop `Indicators` module at
`apps/desktop-web/src/routes/CountryKpisPage.tsx`.

## Product Shape

- Route: `/indicators`.
- Legacy route: `/country-kpis` redirects to `/indicators`.
- Query shape: `?section=<section>&sub=<energy-subview>`.
- The module is organized around the analyst path:
  `sector -> company/portfolio -> asset -> indicator -> source/export`.

Top-level sections are `Indicator Library` and `Energy`. Energy retains all
five specialist subviews. Companies & Assets now belongs to Companies at
`/empresas/assets`; distribution source health and its full snapshot/refresh
audit belongs to Settings at `/settings/indicator-sources`.

Compatibility:

- Missing `section`, `overview`, `favorites`, and the old `exports` section open
  Indicator Library, where compact inline export/source-check help is available.
- `section=entities` and legacy `section=discover` redirect to `/empresas/assets`.
- `section=health` redirects to `/settings/indicator-sources`.
- Redirects preserve all query parameters other than the old `section` selector.
- Missing `sub` or legacy `sub=overview` inside Energy defaults to Distribution.
- Existing `section=energy&sub=...` links remain valid.

The Utilities sector's Macro / Country matrix remains available. It preserves
cross-country comparison, year selection and source disagreement evidence;
equivalence with IndicatorExplorer has not been established. A contextual link
opens Energy's Matrix & Trends catalog.

## Energy Sector

Energy is the first deep sector. Current subviews:

| Subview | Component | Current coverage |
| --- | --- | --- |
| `Distribution` | `components/indicators/distribution/DistributorExplorer.tsx` | ANEEL distributor operational KPIs, charts, detail tabs, refresh, Excel export. |
| `Generation` | `components/indicators/PlantParcelExplorer.tsx` | CCEE plant-parcel catalog, generation series, source status, manual import support. |
| `Fuel` | `components/indicators/FuelDistributionExplorer.tsx` | ANP fuel sales marts and bounded detail preview. |
| `Power System` | `components/indicators/SINKpiPanel.tsx` | SIN operating indicators with source status and local cached reads. |
| `Matrix & Trends` | `components/indicators/explorer/IndicatorExplorer.tsx` | Catalog-backed country energy/electricity and SIN records, with metadata, previews, source refresh and supported export. |

Do not remove or hide these subviews when reorganizing the module.

## Indicator Library

`components/indicators/explorer/`

The default Indicator Library page is an indicator list, not the detailed catalog
browser. It lists only indicators whose chart/table can be opened directly from
the library without an entity selector. Company-, distributor-, asset-, plant-,
parcel-, ticker-, fuel product-, state-, or economic-group-specific indicators
belong in their specialist workflows, not in the default library.

Current library rows include:

- Catalog-backed country energy/electricity records from the backend
  `kpi_catalog`, opened through `Energy -> Matrix & Trends`.
- Catalog-backed SIN power-system records from the backend `kpi_catalog`,
  opened through `Energy -> Power System`.
- Static fallback definitions for those same country and SIN namespaces when
  the local catalog is unavailable, clearly marked as definition-only until
  cached series are available.

Do not list company KPI definitions, distributor metrics, Generation plant or
portfolio metrics, Fuel product/state/region metrics, individual subsystem
observations, or any other row that requires a selector before data can render.
Those records belong in their dedicated detail pages. For example, Distribution
metrics such as billed energy, DEC, FEC, losses, injected energy and
delinquency remain inside `Energy -> Distribution`.

UI pattern:

- One page title: `Indicator Library`, with inline definition help explaining
  that the page is the central library for indicators that open without an
  entity selector.
- No summary cards, dashboard counters, generic intro paragraph, or
  implementation-detail warning panels.
- Compact controls above the table: unlabeled search input plus domain, source,
  unit, type, status and favorites filters.
- Dense table with indicator name, inline definition help, unit, period, scope,
  domain, source, and favorite action inside the indicator cell. Selecting the
  row opens the indicator detail panel; there is no separate open column or
  specialist navigation action in the Library.
- Row selection opens a right-side detail panel on wide screens, compressing the
  table while preserving scroll position. On narrow screens, the panel stacks
  below the table. On wide screens, the panel is docked to the indicator table
  bounds and the visible app viewport while the table scrolls, so selecting a
  lower row keeps the detail panel in view without crossing the page's right
  content margin. The user can resize the panel horizontally from its left edge
  or switch it to a fullscreen overlay for larger chart inspection. The panel is
  intentionally minimal: indicator name with favorite action, definition, unit
  above the chart, the same configurable
  `IndicatorControls` / `IndicatorChart` / `IndicatorLegend` pattern used by
  Financial indicators, then source and domain. It does not show a broad
  metadata grid, latest-observation table, specialist navigation, or
  per-indicator export actions.
- The table and side panel must be useful without requiring navigation to a
  specialist page. Specialist workflows remain available from their own
  sections rather than as secondary actions in the Library detail panel.
- Indicator-level export remains outside the default Library detail panel.
  Country KPI export is still available in catalog mode through
  `export_country_kpis_excel`.

The backend-driven catalog browser still exists, but it is scoped to
`Energy -> Matrix & Trends`. In catalog mode, `IndicatorExplorer` reads the
backend `kpi_catalog`, joins cached series and health snapshots, and normalizes
records through `apps/desktop-web/src/lib/indicators/registry.ts`.

Catalog mode layout:

- `ExplorerStatusStrip` - total indicators, sources, cached locally, stale,
  failed/blocked, last refresh.
- `ExplorerToolbar` - debounced search, facets, sort, favorites toggle.
- `IndicatorCatalogTable` - dense sticky-header table with no inline charts.
- `IndicatorDetailPanel` - reproducibility metadata, preview chart, source
  refresh, Excel export where supported, related indicators, composite view
  launchers.

Favorites persist to `localStorage` under `cvm:indicators:favorites:v1` inside
the catalog browser. There is no top-level Favorites page.

Current backend catalog namespaces are `energy_utilities.country.*` and
`energy_utilities.sin.*`. Distribution, fuel, generation and company financial
indicators currently have specialist pages or contracts, but they are
entity-dependent and must not be surfaced in the default Indicator Library. Do
not invent units, periods, formulas, coverage or freshness values; if metadata
is not available, label it as unavailable.

Every metadata field shown by the Explorer must map to a real backend field or
render as `—`. Do not invent source, coverage, quality, confidence, or freshness
metadata in the frontend.

## Indicator UX Minimalism Standards

Indicators are a core product surface. They must be dense, comparable,
traceable, and fast to interpret without becoming generic dashboard panels.

For each indicator area, future reviews must check:

- Metric name: clear, stable, and specific enough for financial analysis.
- Unit: visible near the value, table header, axis, or detail metadata.
- Period: clear for point-in-time, quarterly, annual, accumulated, and LTM
  views.
- Value type: reported, calculated, estimated, imported, external, unavailable,
  or not supported by current data.
- Source: traceable to the underlying source, local cache, import, bridge
  method, or catalog metadata when available.
- Formula: available for calculated indicators when the backend/catalog exposes
  it.
- Consolidation: consolidated and individual data must not be visually mixed
  without clear labels.
- Missing values: shown explicitly as missing or unavailable, never silently
  converted to zero or hidden.
- Historical comparison: easy to scan through trends, tables, or bounded chart
  previews without overloading the page.
- Filters: consistent with the rest of Indicators and aligned to real data
  fields.
- Visual hierarchy: summary first, detail on demand, source/audit metadata
  accessible.
- Noise level: no repeated labels, vague helper copy, redundant cards, or
  decorative chart framing that slows interpretation.
- Analyst value: the page should help an Equity, Credit, IB, or sector analyst
  reach a decision or next action faster.

Minimalism does not override auditability. If the app lacks source,
calculation, confidence, coverage, or freshness metadata for an indicator, the
UI should state that the metadata is unavailable instead of inventing it.

## Companies & Assets

`components/indicators/SectorCompanyPanel.tsx`

At `/empresas/assets`, this view connects CVM company identity with sectoral assets where data is
available. It currently exposes:

- Portfolio Overview as the default company/asset workflow.
- CVM company registry and listed/non-listed entities.
- Economic groups.
- Linked distributors and generation assets by owner.
- Mapping Review for auto-linked, manual, custom-owner, and unresolved assets.
- Automatic mapping, manual overrides, manual unlinks, custom-owner links, and
  persisted review notes.

Manual user mappings are expected product behavior. Do not treat them as a
hidden workaround.

Current limitations:

- Automatic mapping confidence is not recorded in the local data model.
- Mapping Review edits are limited to the existing local bridge contract:
  target CVM company, custom owner, unresolved/manual unlink, and review note.
- Portfolio Overview uses existing bridge fields only; it does not add new
  company-to-asset schema.
- There is no separate audit history table yet. The current mapping row stores
  the latest manual relationship, note, source flag, and backend timestamp.

## Data Health & Sources

At `/settings/indicator-sources`, centralized health currently covers ANEEL distribution through
`get_distribution_health`.

Other source health is still shown inside specialist views:

- Generation source status lives in `PlantParcelExplorer`.
- SIN source status lives in `SINKpiPanel`.
- Fuel marts are readable, but centralized health is not yet available.

The UI should label this as partial coverage. Do not imply that all source
health is centralized until the bridge and data model support it.

## Exports & Verification

`CountryKpisPage.tsx` provides compact inline export/source-check help, linking
to real specialist export actions and source health. There is no dedicated
export inventory page or centralized export manifest. The unused inventory
configuration was removed; real export components and bridge methods remain.

Direct export paths currently visible from Indicators:

- Distribution Excel report: generated inside `Energy -> Distribution` after
  selecting a distributor or economic group. Uses the existing
  `export_distribution_excel` bridge method.
- Country energy KPI Excel: generated from the `Energy -> Matrix & Trends`
  detail panel for supported country-level KPIs. Uses the existing
  `export_country_kpis_excel` bridge method.

Source-review paths without a centralized export action:

- Generation asset review: `Energy -> Generation`, with source status, manual
  imports, plant detail and owner mapping.
- SIN subsystem review: `Energy -> Power System`, with source status, local
  record counts, snapshots and refresh errors where available.
- Fuel mart review: `Energy -> Fuel`, with source dataset ids, product/state/year
  filters and bounded detail previews.
- Mapping Review notes: `Companies & Assets`, with the latest manual mapping
  note stored on the local mapping row.

The UI must keep these distinctions visible. Do not label a workflow as
downloadable unless the active bridge/API exposes an export action for it.

## Runtime Contract

React components must keep using the facade path:

```text
UI component
-> apps/desktop-web/src/lib/api/*
-> apps/desktop-web/src/lib/bridge/adapter.ts
-> window.pywebview.api
-> desktop/bridge.py
-> Python services / SQLite
```

Reads are local-first. Refresh actions are explicit and source-specific.
Browser mode must render non-blocking browser-only states instead of crashing.

## Validation

After changing this module, run the relevant subset first, then the broader
frontend checks:

```powershell
npm --prefix apps/desktop-web run test -- src/routes/__tests__/CountryKpisPage.test.ts
npm --prefix apps/desktop-web run test
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```

For Energy data-path changes, also run the relevant Python tests. UI-only
navigation/copy changes do not require Python data tests unless bridge behavior
or data contracts changed.
