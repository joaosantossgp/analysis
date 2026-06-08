# Energy Utilities SIN KPIs

Active reference for the local-first SIN subsystem KPI module.

## Runtime and Storage

- Active UI surface: `apps/desktop-web`, inside the `Indicators` module under `Macroeconomic` -> `SIN Subsystems`.
- Desktop bridge: `desktop/bridge.py` methods `get_sin_kpi_dashboard`, `get_sin_kpi_series`, `get_sin_kpi_health`, `refresh_sin_kpis`.
- Python core: `src/energy_kpi/sin_catalog.py`, `src/energy_kpi/sin_ingest.py`, `src/energy_kpi/sin_refresh.py`, and `src/energy_kpi/read.py`.
- Local database: the existing `energy_kpis.db`, resolved by `src/platform/settings.py` as `settings.paths.energy_kpi_db_path`.
- Reads are offline-only. Opening the dashboard does not call ONS, CCEE, EPE, ANEEL, or any other network source.

## Supported MVP Sources

Implemented now:

- ONS `Balanço de Energia nos Subsistemas`: load, hydro generation, thermal generation, wind generation, solar generation, total generation, generation mix, net interchange proxy.
- ONS `EAR Diário por Subsistema`: stored energy in `MWmes` and `%`.
- ONS `ENA Diário por Subsistema`: gross and storable ENA in `MWmed` and `% MLT`.
- ONS `CMO Semi-Horário`: CMO in `R$/MWh`.
- CCEE `PLD horário`: PLD in `R$/MWh` when public direct download/API access works in the runtime environment.

Prepared for later:

- EPE electricity consumption by class/region/subsystem.
- ANEEL SIGA, MMGD, DEC/FEC, and tariff components.

## Tables

The SIN module reuses the existing Energy KPI tables:

- `kpi_catalog`
- `kpi_sources`
- `source_snapshots`
- `kpi_refresh_log`
- `data_quality_checks`

Additive SIN-specific tables:

- `subsystem_dimension`: stable internal subsystem codes and source aliases.
- `subsystem_kpi_values`: KPI observations keyed by `kpi_id + reference_datetime + subsystem_code`.

Canonical subsystem codes:

- `S`: South / Sul
- `SE_CO`: Southeast-Center West / Sudeste-Centro-Oeste
- `NE`: Northeast / Nordeste
- `N`: North / Norte

## Refresh Behavior

- Refresh is manual and user-triggered through `Indicators` -> `Macroeconomic` -> `SIN Subsystems`.
- Default refresh attempts current and previous calendar year.
- ONS datasets are discovered through official CKAN package metadata and downloaded as immutable local snapshots.
- CCEE PLD is attempted but treated as source-risky; if it returns 403 or another access error, the refresh can still finish as `partial` with ONS data available.
- Repeat refreshes are safe. `subsystem_kpi_values` uses a deterministic primary key and source hash to avoid duplicate observations.

## Known Limitations

- PLD depends on CCEE public access behavior; direct API/download may reject automated requests in some environments.
- Net interchange currently uses `val_intercambio` from ONS Balanço. Directional ONS Intercâmbio is a future connector.
- No forecasting, trading recommendations, power-market simulation, or automatic background refresh is included.
- EPE and ANEEL sources are catalog/preparation only in this MVP.

## Validation

Relevant commands after changes to this module:

```powershell
python -m pytest tests/energy_kpi -q
python -m pytest tests/test_settings.py tests/test_database_portability.py -q
npm --prefix apps/desktop-web run typecheck
npm --prefix apps/desktop-web run build
```
