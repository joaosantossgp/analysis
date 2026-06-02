# Indicators Module

Active reference for the desktop `Indicators` module at `apps/desktop-web/src/routes/CountryKpisPage.tsx`.

## Product Shape

- Route: `/indicators` (legacy `/country-kpis` redirects here for backward compatibility).
- Top navigation label: `Indicators`.
- The page is a thin host for the **Indicator Explorer** (default view) with one
  secondary view toggle:
  - `Explorer`: scalable, metadata-driven catalog of local-first macro/energy KPIs.
  - `Sector & Company`: microeconomic CVM sector snapshots + company KPI coverage.

The former nested `Macroeconomic → Country/SIN → Matrix/Trend` tab tree is
retired. Those visualizations are now reached from an indicator's detail panel
(see below), which scales to many more indicators than fixed tabs.

## Indicator Explorer

`apps/desktop-web/src/components/indicators/explorer/`

The Explorer is **catalog-driven**: it does not hardcode an indicator list. It
reads the backend `kpi_catalog` (country `energy_utilities.country.*` + SIN
`energy_utilities.sin.*`) via `get_kpi_catalog`, joins it with the cached series
and health snapshots, and normalises everything into `IndicatorRecord[]` through
the registry at `apps/desktop-web/src/lib/indicators/registry.ts`.

Layout:
- `ExplorerStatusStrip` — total indicators, sources, cached locally, stale,
  failed/blocked, last refresh.
- `ExplorerToolbar` — debounced search + faceted filters (Theme, Source,
  Frequency, Geography, Status, Type) + sort + favorites toggle.
- `IndicatorCatalogTable` — dense, sticky-header table. **Renders no charts.**
- `IndicatorDetailPanel` — full reproducibility metadata for the selected
  indicator plus **exactly one** lazy preview chart, source refresh / Excel
  export, related-indicator links, and the composite-view launchers
  (electricity matrix via `MatrixView`, SIN generation mix via `GenerationMix`).

Favorites (pinned indicators) persist to `localStorage`
(`cvm:indicators:favorites:v1`) via `apps/desktop-web/src/lib/indicators/useFavorites.ts`.

### Reproducibility metadata

Every field shown maps to a real backend field — nothing is invented; missing
values render as `—`:

| Explorer field | Backend source |
| --- | --- |
| Source / dataset | `KPICatalogEntry.primary_source`, kpi_id namespace, series `source_dataset` |
| Raw field | series `source_field` |
| Methodology / value type | `calculation_method` (`direct` = raw; `derived_*` = derived) |
| Unit | `KPICatalogEntry.unit` |
| Reference period / coverage | series `period` / `reference_datetime` (min–max) |
| Last refresh | `get_energy_kpi_health` / SIN dashboard `last_successful_update` |
| Cache status | derived: cached / stale / not cached / failed / blocked |
| Caveats / audit / verification | `source_caveats`, `audit_notes`, `source_verification_status` |
| Data quality | series `data_quality_status`, `source_conflict`, `fallback_used` |

### Performance

Five cached bridge reads back the whole Explorer (catalog + country series —
shared with the detail chart — + SIN dashboard + 2 health). No per-row queries,
no charts in the table, exactly one chart for the selected indicator. The SIN
preview series is fetched lazily only when a SIN indicator is selected. Search
is debounced (300ms); filtering/sorting are memoised.

## Sector & Company view

`apps/desktop-web/src/components/indicators/SectorCompanyPanel.tsx`. Reuses
existing CVM local data through the bridge:

- Sector snapshots: `get_sectors` via `apps/desktop-web/src/lib/api/sectors.ts`.
- Company coverage: `get_companies` via `apps/desktop-web/src/lib/api/companies.ts`.

This view is intentionally not a new data layer. It is the UI organization point
for company/sector indicators already owned by the CVM read-service/KPI engine,
which is why it is not part of the energy `kpi_catalog`.

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

Reads are offline-only. Manual refresh actions are explicit and source-specific:

- Country energy refresh: `refresh_energy_kpis`.
- SIN refresh: `refresh_sin_kpis`.

Browser mode renders a non-blocking browser-only banner. Mock mode
(`npm run dev:mock`) renders a dev-only catalog fixture (`MOCK_KPI_CATALOG` in
`apps/desktop-web/src/lib/bridge/mock.ts`) so the Explorer is testable without
the Python bridge. The fixture is excluded from production builds.

## Validation

After changing this module, run:

```powershell
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
python -m pytest tests/energy_kpi -q
```
