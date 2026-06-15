# Energy Database Phase 2 Audit

Generated from `tools/profile_energy_db.py` on the active local
`energy_kpis.db` in read-only mode.

## Safety

- Database: `C:\Users\jadaojoao\Documents\CVMAnalytics\db\energy_kpis.db`
- Connection mode: SQLite URI `mode=ro`
- Main file before/after: `36,483,608,576` bytes, unchanged
- Main file mtime before/after: unchanged
- WAL before/after: `90,672` bytes, unchanged
- SHM before/after: `32,768` bytes, unchanged
- Schema version: `128`
- Page size: `4096`
- Page count: `8,907,131`
- Freelist count: `2`
- Journal mode: `wal`
- SQLite compile option `ENABLE_DBSTAT_VTAB`: not available

Because `dbstat` is unavailable in this Python SQLite build, exact table and
index byte attribution cannot be reported. The JSON profile records table and
index byte fields as `null` rather than estimating them as exact values.

## Composition

The database contains 34 application tables and 34 application indexes.

Largest row-count contributors:

| Table | Kind | Rows | Columns | Indexes |
|---|---:|---:|---:|---:|
| `ccee_plant_parcel_hourly` | historical fact | 66,719,664 | 30 | 5 |
| `distribution_mmgd_project_snapshots` | snapshot | 3,923,184 | 8 | 1 |
| `distribution_mmgd_projects` | metadata/current-ish | 3,923,184 | 16 | 1 |
| `distribution_market_facts` | historical fact | 1,602,847 | 21 | 1 |
| `distribution_continuity_facts` | historical fact | 1,200,360 | 10 | 2 |
| `distribution_delinquency_facts` | historical fact | 1,112,622 | 8 | 0 |
| `distribution_energy_balance_facts` | historical fact | 982,166 | 14 | 1 |
| `subsystem_kpi_values` | historical fact | 656,184 | 15 | 3 |
| `distribution_continuity_compensations` | metadata/fact | 544,725 | 10 | 0 |
| `distribution_continuity_limits` | metadata/fact | 435,859 | 10 | 0 |
| `distribution_tariff_facts` | historical fact | 317,309 | 19 | 1 |
| `ccee_plant_parcel_monthly` | historical fact | 82,458 | 36 | 5 |

## Largest Contributors

`ccee_plant_parcel_hourly` is the dominant confirmed storage driver by evidence:

- 66.7M rows, 30 columns, and 5 secondary indexes.
- 26 monthly partitions from `2024-03` through `2026-04`.
- Average rows per month: about 2.57M.
- Latest measured months: `2026-02` 2.59M, `2026-03` 2.91M, `2026-04` 2.83M.
- The database file is 33.98 GiB; no other table approaches this row count.

Other meaningful growth areas:

- `distribution_mmgd_projects` and `distribution_mmgd_project_snapshots` both
  contain 3.92M rows. This pair should be checked for duplicated current-state
  versus snapshot payloads.
- Distribution market, continuity, delinquency, and balance fact tables total
  several million rows but are much smaller than CCEE hourly.
- `subsystem_kpi_values` has 656k rows and is not the primary storage driver.

## Time and Source Distribution

`ccee_plant_parcel_hourly`:

- Source dataset: `GERACAO_HORARIA_USINA`, 66.7M rows.
- Largest generation source groups:
  - Eolica: 22.21M
  - Solar Fotovoltaica: 13.88M
  - Hidraulica PCH: 8.09M
  - Hidraulica CGH: 7.69M
  - Termica a Biomassa: 6.66M

`ccee_plant_parcel_monthly`:

- 82,458 rows across 23 months.
- Source dataset: `PARCELA_USINA_MONTANTE_MENSAL`.
- Monthly table is not the storage problem by row count.

Distribution:

- `distribution_market_facts`: 1.60M rows across 28 months.
- `distribution_continuity_facts`: 1.20M rows across 77 months.
- `distribution_delinquency_facts`: 1.11M rows across 173 months.
- `distribution_energy_balance_facts`: 982k rows across 243 months.

## Query Profiling

Representative query timings on the production database:

| Query | Plan summary | Rows | Time |
|---|---|---:|---:|
| plant detail latest | PK lookup on `ccee_plant_parcels` | 1 | 0.68 ms |
| monthly plant series | `idx_cppm_parcel_ref` | 16 | 5.64 ms |
| hourly plant series by parcel/month | `idx_cppe_parcel_ref`; temp B-tree for order | 0 in sampled case | 3125 ms |
| SIN latest reference | covering index `idx_skv_dataset_ref` | 1 | 58 ms |
| distribution distributor series | `idx_dist_market_ref` | 42,456 | 1211 ms |

The hourly query shape should likely be backed by `(plant_parcel_code,
reference_month, reference_datetime, commercialization_period)` if SQLite
continues to serve hot hourly detail. The current `(plant_parcel_code,
reference_datetime)` index cannot efficiently combine plant + month + ordering.
No index changes were made in this phase.

## Ingestion Findings

CCEE plant ingestion:

- `PlantParcelRefreshJob` refreshes one source/period at a time.
- Writes run through SQLAlchemy `engine.begin()` with retry on SQLite locks.
- CCEE hourly persistence uses `INSERT OR REPLACE`.
- Hourly rows are executed in batches of 50,000.
- Manual import checks for a previous successful import by file hash, but
  automatic refresh uses source period replacement through primary-key conflict.
- Hourly fact table repeats text fields per row: `plant_acronym`,
  `generation_source`, `submarket`, `plant_type`, `source_dataset`,
  `raw_payload_hash`, `snapshot_id`.

Distribution ingestion:

- Uses fact tables with stable identifiers and source row hashes.
- Aggregates are rebuilt after refresh.
- Some current/snapshot pairs, especially MMGD projects and snapshots, need a
  closer duplication audit before retention or tiering decisions.

## Duplication and Normalization Findings

Confirmed normalization opportunities:

- `ccee_plant_parcel_hourly` repeats categorical text tens of millions of times.
- `source_dataset`, generation source, submarket, plant type, snapshot id, and
  raw hash are good candidates for integer dictionary keys in SQLite or
  dictionary encoding in Parquet.
- Current CCEE parcel state in `ccee_plant_parcels` is intentionally duplicated
  from monthly data for fast current-state reads; treat it as query-performance
  duplication, not accidental waste.

Suspected duplication:

- `distribution_mmgd_projects` and `distribution_mmgd_project_snapshots` have
  identical row counts in the current profile. Validate whether project rows are
  full current state plus every snapshot, or whether imported snapshot files are
  being mirrored unnecessarily.

Intentional auditability:

- Raw files under the Energy raw root and source snapshots preserve provenance.
  They should not be treated as disposable without a retention policy.

## Growth Model

Observed CCEE hourly rows:

- 66,719,664 rows over 26 months.
- Average monthly rows: about 2,566,140.
- Approximate whole-database bytes per CCEE hourly row, using the full DB size
  as an upper bound: about 547 bytes/row. This includes other tables and indexes,
  so it is not an exact table storage metric.

Projection if the current design keeps appending similar hourly months:

- 12 months: about 30.8M new rows; up to about 16.7 GiB additional DB growth.
- 24 months: about 61.6M new rows; up to about 33.5 GiB.
- 60 months: about 154.0M new rows; up to about 83.8 GiB.

These are conservative upper-bound estimates because exact CCEE hourly table and
index bytes are unavailable without `dbstat`.

## Optimization Options

### A. Optimize existing SQLite schema

- Benefit: medium to high if repeated text and redundant indexes are reduced.
- Risk: medium; requires schema migration and query updates.
- Complexity: medium.
- Confidence: medium.
- Best first target: normalize CCEE hourly repeated text and add a hot-query
  composite index in a test copy only.

### B. Hot SQLite plus cold archive

- Benefit: high; keeps recent 12-24 months queryable in SQLite and moves older
  hourly history out of the main DB.
- Risk: medium; requires manifest, routing, backup, and offline validation.
- Complexity: medium-high.
- Confidence: high for storage containment.

### C. Parquet/DuckDB for large analytical facts

- Benefit: very high for append-heavy time-series storage and scans.
- Risk: medium-high; adds an engine and packaging surface.
- Complexity: high.
- Confidence: high for CCEE hourly, lower for transactional/import metadata.
- Keep SQLite owning dimensions, snapshots, refresh state, quality checks,
  manifests, and recent summaries.

### D. Split Energy domains into independent SQLite databases

- Benefit: medium; isolates backup, locking, and growth by domain.
- Risk: medium; cross-domain reads and packaging complexity increase.
- Complexity: medium.
- Confidence: medium.

### E. Controlled SQLite rebuild

- Benefit: unknown until table/index byte attribution is available from a copy
  with `dbstat` or the SQLite CLI.
- Risk: high against production data.
- Complexity: high.
- Confidence: low until exact page attribution is available.

## Recommendation

Do not start with deletion, VACUUM, or a production rebuild.

Recommended next architecture direction:

1. Build an exact profiler path against a safe filesystem copy using a SQLite
   binary with `dbstat`.
2. Prototype CCEE hourly hot/cold tiering: recent months in SQLite, older
   months in partitioned Parquet with a SQLite manifest.
3. Keep current-state and metadata in SQLite.
4. Add a targeted hot-query index only after testing on a copy:
   `(plant_parcel_code, reference_month, reference_datetime,
   commercialization_period)`.
5. Validate MMGD project/snapshot duplication before changing distribution
   storage.

## Roadmap

Immediate low-risk work:

- Add copy-based exact `dbstat` profiling.
- Add query benchmarks for real UI-selected plant parcels and distributors.
- Add profile snapshots to Settings diagnostics as cached links only.

Medium-risk schema work:

- Normalize CCEE hourly categorical dimensions in a test database.
- Benchmark candidate composite indexes.
- Add retention policy docs for refresh logs and source snapshots.

Migration work:

- Design CCEE hourly partition manifest.
- Build import/export validation against a copied DB.
- Implement atomic backup, migration, rollback, and integrity checks.

Release validation:

- Compare query results before/after migration.
- Validate offline packaged app.
- Validate backup/restore and rollback.
- Validate storage inventory before/after.

