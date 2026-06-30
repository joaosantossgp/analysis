# 0007 - Local Analytical Storage for Large Facts

- **Status:** accepted
- **Date:** 2026-06-29
- **Author:** human+ai

## Context

CVMAnalytics is a local-first desktop application. The active UI is the Vite app
in `apps/desktop-web`, served through the pywebview bridge in `desktop/bridge.py`.
Runtime user data is stored under `%USERPROFILE%\Documents\CVMAnalytics`.

The energy KPI database grew to about 28.7 GiB in `energy_kpis.db`; the broader
local data root was about 38.4 GiB before the storage migration work. The main
driver was `ccee_plant_parcel_hourly`, with 66,719,664 CCEE plant-parcel hourly
rows across 26 months. This row-store design does not scale to the expected
multi-sector product scope.

## Decision

Large analytical and time-series facts must not be eagerly materialized into the
main application SQLite database by default.

Use a tiered local storage model:

- SQLite remains the store for app metadata, import state, source snapshots,
  lineage, dimensions, smaller relational data, and rebuildable marts.
- Large immutable or append-mostly facts move to managed analytical stores under
  `analytics/<domain>/...`.
- For CCEE hourly generation, use a hot/cold store:
  - latest months in a smaller SQLite hot store;
  - older full-month partitions in Parquet;
  - a manifest with row counts, source signature, validation status, and
    available months.
- Keep summary marts in SQLite for overview screens and load hourly detail only
  through bounded entity/date-range drill-down.
- Compact SQLite databases must retain an audit catalog linking externalized
  facts back to the manifest and source row counts.

## Implementation Notes

The first implemented slice externalized `ccee_plant_parcel_hourly`:

- Managed hourly store:
  `%USERPROFILE%\Documents\CVMAnalytics\analytics\energy\ccee_plant_generation_hourly`
- Live compact DB:
  `%USERPROFILE%\Documents\CVMAnalytics\db\energy_kpis.db`
- Rollback backup:
  `%USERPROFILE%\Documents\CVMAnalytics\backup\energy_kpis_swap_20260629T142611Z`

The compact live DB keeps no raw hourly rows in `ccee_plant_parcel_hourly`.
It keeps `external_hourly_store_catalog` to prove that the external hourly store
matches the full-month manifest and the daily mart observation counts.

Large future datasets should declare the shared managed-ingestion contract in
`src/platform/managed_ingestion_contract.py` before import implementation starts.
The contract requires:

- explicit domain, dataset ID, fact grain, and schema version;
- metadata SQLite plus SQLite marts for app state and summary reads;
- at least one managed analytical fact layer such as hot SQLite or cold Parquet;
- full lineage fields for source, timestamp, import batch, parser version,
  content hash, entity, period, frequency, unit, and transformation;
- bounded detail reads for high-granularity facts;
- an explicit hot-partition retention setting.

Managed manifests should include the contract block so release validation can
prove that heavy ingestions follow the local-first storage architecture instead
of silently returning to monolithic SQLite facts.

## Alternatives Considered

- **Optimized SQLite only:** lower dependency risk, but still poor fit for
  high-frequency multi-sector analytical facts and likely to recreate the same
  growth problem.
- **Sector/domain split only:** useful for packaging and on-demand imports, but
  still insufficient if each domain stores high-frequency facts row-by-row in
  SQLite.
- **Hybrid SQLite plus analytical files:** best fit for local-first operation,
  offline reads, auditability, bounded drill-down, and scale beyond energy.

## Consequences

- The app must treat raw/source facts, normalized facts, marts, and UI caches as
  separate layers.
- Importers must preserve source name, source path or URL, timestamps, hashes,
  parser/import version, entity IDs, period, unit, scale, and transformation
  lineage.
- UI reads should prefer summary marts and bounded drill-down. Startup and normal
  overview flows must not scan external high-frequency facts.
- Release and support workflows need storage diagnostics, rebuild commands, and
  rollback instructions.
- Release validation should run a storage budget check so large facts do not
  silently return to the main SQLite databases.

Default guardrail command:

```powershell
python scripts/data/check_storage_budget.py
```

Default budgets:

- any one main SQLite database: 12 GiB;
- all main SQLite databases: 16 GiB;
- active local storage excluding rollback backups: 32 GiB.

Rollback backups are reported as reclaimable warnings by default. Use
`--fail-on-backups` only after the release process explicitly disallows retained
rollback backups.

## Validation

For the CCEE hourly migration:

- Original live `energy_kpis.db`: about 28.7 GiB.
- New live compact `energy_kpis.db`: about 5.0 GiB.
- Managed hourly store: about 4.8 GiB.
- Externalized rows: 66,719,664.
- SQLite `quick_check` on the compact live DB: `ok`.
- Sample read paths after swap selected `hot_sqlite` or `cold_parquet` with no
  raw SQLite fallback.

## Follow-Up

- Add a storage manager or diagnostics UI for local data size, backups, and
  rebuild status.
- Apply the same storage review before onboarding large datasets in other
  sectors.
- Add documented retention rules for rollback backups after user acceptance.
