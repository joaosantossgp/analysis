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

## Remaining phases

### Phase 4: Excel/export optimization

Next step.

Goal: reduce repeated raw statement reads during Excel/export workflows without
changing workbook values, formulas, layout, file names, or auditability.

Required first:

- profile current export read path;
- add workbook/value equality tests;
- test representative companies;
- keep raw `financial_reports` as canonical audit source.

### Phase 5: Broader multi-source/cold-tier evaluation

Future step. Consider only after SQLite marts, indexes, and export paths are
stable and measured.

