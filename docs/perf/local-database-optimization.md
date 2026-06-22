# Local Database Optimization

Status note for the local SQLite optimization work completed in June 2026.

## Completed phases

### Phase 1: Energy KPI hot path

The `energy_kpis.db` hot path was moved away from broad reads of
`ccee_plant_parcel_hourly`.

Implemented:

- rebuildable plant/parcel marts:
  - `plant_parcel_daily_generation_mart`;
  - `plant_parcel_hourly_preview_mart`;
  - `plant_parcel_source_submarket_monthly_mart`;
- mart freshness metadata in `energy_mart_builds`;
- guarded hourly drill-down requiring explicit narrow filters;
- default UI/API reads for plant charts and diagnostics using marts where
  possible;
- maintenance commands:
  - `python scripts/data/rebuild_energy_marts.py --reference-month YYYY-MM`;
  - `python scripts/data/rebuild_energy_marts.py --all`;
  - `python scripts/data/compact_energy_db.py ...`.

Observed local result:

- `energy_kpis.db` reduced from about 36.49 GB to about 30.83 GB after the
  validated maintenance/compaction flow.

Raw hourly facts and source snapshots remain preserved. Mart rebuilds do not
delete source data.

### Phase 2: CVM financial optimization planning

The CVM financial database was profiled before implementation.

Observed baseline:

- `cvm_financials.db`: about 466 MB before CVM marts;
- `financial_reports`: 1,514,771 rows;
- freelist count was 0, so plain `VACUUM` was not expected to shrink the file;
- main opportunity was lighter repeated reads rather than urgent file-size
  reduction.

### Phase 3.1: CVM financial mart foundation

Implemented additive, rebuildable CVM marts:

- `company_financial_directory_mart`;
- `company_financial_period_mart`;
- `company_kpi_account_mart`;
- `financial_mart_builds`.

Maintenance command:

```powershell
python scripts/data/rebuild_cvm_financial_marts.py
```

The rebuild is idempotent and preserves `financial_reports`.

### Phase 3.2: CVM directory and company metadata cutover

After a successful mart rebuild, these reads use CVM marts by default:

- Companies list metadata;
- available-year lookups;
- Company Detail latest-period metadata.

Fresh or unbuilt profiles keep the raw-query fallback until
`financial_mart_builds` reports successful mart status.

### Phase 3.3: CVM KPI and historical indicators cutover

After a successful mart rebuild, these reads use `company_kpi_account_mart`:

- annual KPI account reads;
- all-period KPI account reads;
- sector metric rows;
- historical indicator metrics.

Direct financial SQL for historical indicators was moved out of the pywebview
bridge and into the centralized financial query layer.

Depreciation/amortization extraction still reads `financial_reports` because it
depends on DFC statement-line text matching that is not yet represented in the
KPI account mart.

### Phase 3.4: CVM index benchmark on copied DB

No live CVM indexes were dropped.

A copied-database benchmark showed these `financial_reports` indexes are
candidates for a later backup-and-compact maintenance flow:

- `idx_fr_cd_cvm`;
- `idx_fr_period_label`;
- `idx_fr_cd_conta`;
- `idx_fr_cd_cvm_period_label`;
- `idx_fr_cd_conta_period_label`;
- `idx_fr_year_period`.

Keep for now:

- `idx_fr_cd_cvm_stmt_year`;
- `idx_fr_cvm_year`.

Copied-DB result:

- source copy: about 480 MB;
- compact copy after candidate drops: about 297 MB;
- `PRAGMA quick_check`: `ok`;
- representative Companies, Company Detail, KPI, statement, DFC, and
  export-period reads did not regress for the measured sample.

Do not drop these indexes on the live database without a timestamped backup,
copied-DB equality checks, compact-copy validation, and packaged runtime smoke
test.

### Phase 4: Excel/export optimization

Implemented in commit `6a7e6f9`.

Excel/export workflows now load statement frames through one export read pack
per call instead of repeating raw statement reads for each statement type.
`CVMQueryLayer.get_statements()` batches statement matrix reads while still
using raw `financial_reports` as the canonical audit source for workbook raw
statement sheets.

Workbook formula row resolution now uses a period-aware raw-sheet row index
instead of scanning statement DataFrames repeatedly during model sheet
generation. Equality guardrails cover sheet contracts, statement-scoped export,
mapping preview values, batched read calls, and duplicate account-code rows.

Observed local PETR4 result after implementation:

- one batched statement read for DRE/BPA/BPP/DFC/DMPL across 2021-2026;
- total export smoke time about 527 ms;
- period-specific raw-row resolver cost about 1.4 ms for about 2,000 calls.

## Remaining phases

### Phase 5: Broader multi-source/cold-tier evaluation

Started with Phase 5.1 as a diagnostic-only storage inventory. This first slice
does not migrate data, drop indexes, compact live databases, add DuckDB, add
Parquet routing, or change runtime read paths.

Implemented:

- `scripts/diagnostics/phase5_storage_inventory.py`;
- focused tests in `tests/test_phase5_storage_inventory.py`;
- local run summary in `docs/diagnostics/phase5-storage-inventory.md`.

The diagnostic inventory opens SQLite databases with read-only URI connections
and records database size, WAL/SHM sidecars, page/freelist stats,
`sqlite_master` inventory, optional `dbstat` object sizes, guarded row counts,
and bounded folder sizes under the local data root.

Phase 5.2 added an opt-in `--sqlite-cli` fallback for exact `dbstat` collection
when a SQLite CLI with `ENABLE_DBSTAT_VTAB` is available. The default diagnostic
run does not invoke an external CLI so it remains fast and avoids accidental
full-object scans of the large energy database.

An exact `dbstat` run was then completed after validating the local SQLite tools
archive. The largest `energy_kpis.db` objects are `ccee_plant_parcel_hourly`
and its indexes:

- `ccee_plant_parcel_hourly`: about 19.38 GB;
- `sqlite_autoindex_ccee_plant_parcel_hourly_1`: about 2.58 GB;
- `idx_cppe_parcel_ref`: about 2.38 GB;
- `idx_cppe_ref_month`: about 1.14 GB.

Together, the CCEE hourly table and these three indexes account for about
25.49 GB, roughly 83% of `energy_kpis.db`.

Phase 5.3 added a copy-based CCEE hourly hot/cold prototype tool:

```powershell
python scripts/diagnostics/phase5_hot_cold_hourly_prototype.py `
  --output-dir C:\tmp\cvma-phase5-hot-cold `
  --hot-months 1 `
  --cold-month 2024-03 `
  --max-rows-per-month 100000
```

The prototype opens the source `energy_kpis.db` read-only, copies selected
recent months into a separate hot SQLite database, exports selected old months
to partitioned Parquet, and writes a validation manifest. It is bounded by
default and does not alter runtime routing or live data.

The real local bounded run validated successfully with the source DB unchanged:
100,000 hot rows produced a 37,908,480-byte SQLite copy, and 100,000 cold rows
produced 4,803,375 bytes of Parquet. A full selected-month run also validated
successfully: the hot month `2026-04` copied 2,827,440 rows into a
1,084,678,144-byte SQLite database, while the cold month `2024-03` exported
2,310,864 rows into 113,633,074 bytes of Parquet.

Phase 5.4 added a diagnostic read-path comparison tool:

```powershell
python scripts/diagnostics/phase5_compare_hourly_read_paths.py `
  --manifest C:\tmp\cvma-phase5-hot-cold-full-one-month\manifest.json
```

It compares canonical raw SQLite hourly chart rows against the prototype hot
SQLite and cold Parquet artifacts, records row hashes and read timings, and
keeps all SQLite inputs read-only. It does not change bridge methods, frontend
contracts, or source data.

The real full one-month comparison passed with `--samples-per-tier 3`,
`--aneel-samples-per-tier 1`, `--include-aneel-aggregation`, and `--runs 3`:
three hot parcel samples, one hot ANEEL CEG aggregation sample, three cold
parcel samples, and one cold ANEEL CEG aggregation sample all matched canonical
raw SQLite row hashes, with the source DB signature unchanged. The JSON report
is stored at `docs/diagnostics/phase5-hourly-read-path-comparison.json`.

A CEG-only follow-up run used `--auto-entity-type aneel_plant`,
`--aneel-samples-per-tier 3`, and `--runs 2`. It compared three hot CEG samples
and three cold CEG samples, with 6/6 row-hash matches, zero mismatches, and the
source DB signature unchanged. Median first-run timing was about `5.43x` faster
for hot SQLite CEG aggregation and about `82.84x` faster for cold Parquet CEG
aggregation. The JSON report is stored at
`docs/diagnostics/phase5-hourly-ceg-read-path-comparison.json`.

A wider two-hot/two-cold full-month prototype then selected hot months
`2026-03` and `2026-04`, and cold months `2024-03` and `2024-04`. It copied
5,732,760 hot rows into a `2,200,080,384`-byte SQLite database and exported
4,556,544 cold rows into `225,443,218` bytes of Parquet, with the source DB
signature unchanged. The wider CEG-only comparison produced 12/12 row-hash
matches, zero mismatches, and median first-run speedups of about `2.71x` for hot
SQLite CEG aggregation and about `83.43x` for cold Parquet CEG aggregation. The
JSON report is stored at
`docs/diagnostics/phase5-hourly-ceg-read-path-comparison-wide.json`.

The broadened comparison also showed that the current raw SQLite CEG aggregation
query is the next hot spot. Parcel windows are already bounded and fast after
warm-up, but CEG-level hourly drill-downs repeatedly join the large raw hourly
table to `ccee_plant_parcels`.

The backend adapter foundation now exists in
`src/energy_kpi/hourly_read_adapter.py`, and
`EnergyKPIReadService.get_plant_parcel_chart_data` has conservative runtime
routing around it. ANEEL CEG hourly aggregation may use validated hot/cold
artifacts when `CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST` is configured. Parcel-level
hourly charts stay on raw SQLite by default, unless
`CVM_ENERGY_HOURLY_HOT_COLD_ENABLE_PARCELS=1` is set explicitly. Unsafe or
unavailable artifacts fall back to raw SQLite with explicit
`metadata.hourly_read_path` fields.

Future Phase 5 work should use this baseline before choosing between a runtime
read adapter expansion, additional exact `dbstat` profiling, broader hot/cold
prototypes, or any backup-and-compact maintenance flow.
