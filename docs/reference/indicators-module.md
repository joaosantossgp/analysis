# Indicators Module

Active reference for the desktop `Indicators` workspace at
`apps/desktop-web/src/routes/CountryKpisPage.tsx`.

## Product Shape

- Route: `/indicators`.
- Legacy route: `/country-kpis` redirects to `/indicators`.
- Query shape: `?section=<section>&sub=<energy-subview>`.
- The workspace is organized around the analyst path:
  `sector -> company/portfolio -> asset -> indicator -> source/export`.

Top-level sections:

| Section | Purpose |
| --- | --- |
| `Workspace` | Landing page for available workflows, Energy coverage, source status, and future work areas. |
| `Sectors` | Sector workspaces. Energy is the first deep sector. |
| `Companies & Assets` | CVM registry, economic groups, sectoral asset links, and mapping hub. |
| `Indicator Library` | Catalog-driven KPI search and metadata surface. |
| `Data Health & Sources` | Centralized source coverage and refresh audit where available. |
| `Exports & Verification` | Inventory of real export paths, source evidence and pre-export checks. |

Compatibility:

- Missing `section` defaults to `Workspace`.
- Legacy `section=discover` resolves to `Companies & Assets`.
- Legacy `section=favorites` resolves to `Indicator Library`.
- `section=exports` opens the export/verification inventory.
- Existing Energy deep links with `section=energy&sub=...` remain valid.

## Energy Workspace

Energy is the first deep sector workspace. Current subviews:

| Subview | Component | Current coverage |
| --- | --- | --- |
| `Overview` | inline overview in `CountryKpisPage.tsx` | Workflow map, Energy analysis spine, portfolio/asset coverage snapshot. |
| `Distribution` | `components/indicators/distribution/DistributorExplorer.tsx` | ANEEL distributor operational KPIs, charts, detail tabs, refresh, Excel export. |
| `Generation` | `components/indicators/PlantParcelExplorer.tsx` | CCEE plant-parcel catalog, generation series, source status, manual import support. |
| `Fuel` | `components/indicators/FuelDistributionExplorer.tsx` | ANP fuel sales marts and bounded detail preview. |
| `Power System` | `components/indicators/SINKpiPanel.tsx` | SIN operating indicators with source status and local cached reads. |
| `Matrix & Trends` | `components/indicators/explorer/IndicatorExplorer.tsx` | Country energy and electricity matrix indicators from the KPI catalog. |

Do not remove or hide these subviews when reorganizing the workspace.

The Energy overview also exposes an analysis spine:

- Sector context: distribution, generation, fuel, SIN and matrix panels.
- Company portfolios: linked distributors and generation assets by CVM company
  or custom owner.
- Asset review: mapped plants, distributors and unresolved ownership links.
- Source verification: snapshots, source status, refresh logs and partial source
  warnings.
- Indicator outputs: verified source data feeding the Indicator Library and
  export-ready views.

The portfolio/asset snapshot uses the same existing bridge data as
`Companies & Assets`: `get_conglomerates`, `get_asset_mappings`, and
`get_company_universe`. It does not add new Energy indicators, forecasts,
ownership inference, or schema.

## Indicator Library

`components/indicators/explorer/`

The Indicator Library is catalog-driven. It reads the backend `kpi_catalog`,
joins cached series and health snapshots, and normalizes records through
`apps/desktop-web/src/lib/indicators/registry.ts`.

Layout:

- `ExplorerStatusStrip` — total indicators, sources, cached locally, stale,
  failed/blocked, last refresh.
- `ExplorerToolbar` — debounced search, facets, sort, favorites toggle.
- `IndicatorCatalogTable` — dense sticky-header table with no inline charts.
- `IndicatorDetailPanel` — reproducibility metadata, preview chart, source
  refresh, Excel export where supported, related indicators, composite view
  launchers.

Favorites persist to `localStorage` under `cvm:indicators:favorites:v1`.

Every metadata field shown by the Explorer must map to a real backend field or
render as `—`. Do not invent source, coverage, quality, confidence, or freshness
metadata in the frontend.

## Companies & Assets

`components/indicators/SectorCompanyPanel.tsx`

This view connects CVM company identity with sectoral assets where data is
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

Centralized health currently covers ANEEL distribution through
`get_distribution_health`.

Other source health is still shown inside specialist views:

- Generation source status lives in `PlantParcelExplorer`.
- SIN source status lives in `SINKpiPanel`.
- Fuel marts are readable, but centralized health is not yet available.

The UI should label this as partial coverage. Do not imply that all source
health is centralized until the bridge and data model support it.

## Exports & Verification

`CountryKpisPage.tsx` exposes an `Exports & Verification` section as a
workspace inventory and checklist. It does not generate a new centralized
export manifest in this phase.

Direct export paths currently visible from Indicators:

- Distribution Excel report: generated inside `Energy -> Distribution` after
  selecting a distributor or economic group. Uses the existing
  `export_distribution_excel` bridge method.
- Country energy KPI Excel: generated from the Indicator Library / Matrix &
  Trends detail panel for supported country-level KPIs. Uses the existing
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
