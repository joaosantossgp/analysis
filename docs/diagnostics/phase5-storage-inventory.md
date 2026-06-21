# Phase 5.1 Storage Inventory

Date: 2026-06-21

Status: diagnostic-only baseline. No data migration, live compaction, index
drop, runtime read-path change, DuckDB, or Parquet tier was implemented.

## Command

```powershell
python scripts/diagnostics/phase5_storage_inventory.py
```

Optional exact SQLite object attribution, when a SQLite CLI with `dbstat` is
available:

```powershell
python scripts/diagnostics/phase5_storage_inventory.py --sqlite-cli C:\path\to\sqlite3.exe
```

The script uses SQLite read-only URI connections with `mode=ro` and
`PRAGMA query_only = ON`. It does not run `VACUUM`, `ANALYZE`, `REINDEX`,
checkpoint, schema changes, deletes, inserts, or updates.

## Local Result Summary

Data root:

```text
C:\Users\jadaojoao\Documents\CVMAnalytics
```

Database files:

| Database | Exists | DB bytes | WAL/SHM bytes | Tables | Indexes | Free bytes | dbstat |
|---|---:|---:|---:|---:|---:|---:|---|
| `cvm_financials.db` | yes | 480,301,056 | 374,760 | 25 | 44 | 0 | unavailable |
| `energy_kpis.db` | yes | 30,832,099,328 | 436,560 | 39 | 74 | 8,192 | unavailable |
| `news.db` | yes | 12,451,840 | 4,552,440 | 29 | 37 | 1,773,568 | unavailable |

Top-level folder scan:

| Folder | Exists | Bytes | Files | Dirs | Truncated |
|---|---:|---:|---:|---:|---:|
| `data_root` | yes | 41,237,193,921 | 530 | 132 | no |
| `db` | yes | 31,330,215,984 | 9 | 0 | no |
| `input/raw` | yes | 590,338,576 | 33 | 0 | no |
| `input/processed` | yes | 5,941,044,460 | 231 | 0 | no |
| `raw` | yes | 3,359,654,939 | 89 | 120 | no |
| `cache` | yes | 4,891,862 | 5 | 0 | no |
| `metadata` | yes | 79,140 | 2 | 0 | no |
| `output` | yes | 2,634,152 | 108 | 1 | no |
| `logs` | yes | 147,404 | 11 | 0 | no |

## Findings

- The dominant local storage item is still `energy_kpis.db`, at about 30.8 GB.
- CVM financial storage is comparatively small after the prior mart/export
  optimization work, at about 480 MB.
- Processed CVM input files and energy/raw source folders are large enough to
  include in future cold-tier analysis, but they remain source/audit material
  and were not modified.
- `dbstat` was not available in the Python SQLite build used for this run. The
  script records `dbstat_available=false`; exact per-object SQLite byte
  attribution should use a SQLite binary with `dbstat` if needed.
- Follow-up check on this machine found no `sqlite3` CLI on `PATH`, and Python
  SQLite reports `sqlite_compileoption_used('ENABLE_DBSTAT_VTAB') = 0`.
  The diagnostic now supports an explicit `--sqlite-cli` fallback for future
  exact `dbstat` runs without changing default behavior.

## Exact Dbstat Run

After the SQLite tools archive was provided locally, the ZIP was validated
against the official SQLite SHA3-256 hash:

```text
sqlite-tools-win-x64-3530200.zip
SHA3-256: 5092175a1e4c10776b3cf5a5c2b8cb9be489124ec90f6791fef27c356fad25a4
```

The bundled Codex Python runtime also exposes `ENABLE_DBSTAT_VTAB`, so the
inventory script collected exact object attribution successfully. Full JSON:

```text
docs/diagnostics/phase5-storage-inventory-dbstat.json
```

Largest `energy_kpis.db` objects:

| Object | Bytes | Approx GiB |
|---|---:|---:|
| `ccee_plant_parcel_hourly` | 19,384,406,016 | 18.05 |
| `sqlite_autoindex_ccee_plant_parcel_hourly_1` | 2,577,227,776 | 2.40 |
| `idx_cppe_parcel_ref` | 2,383,978,496 | 2.22 |
| `idx_cppe_ref_month` | 1,139,814,400 | 1.06 |
| `distribution_mmgd_projects` | 678,322,176 | 0.63 |
| `plant_parcel_daily_generation_mart` | 667,238,400 | 0.62 |
| `distribution_mmgd_project_snapshots` | 621,105,152 | 0.58 |
| `distribution_market_facts` | 513,536,000 | 0.48 |

The CCEE hourly fact table plus its three largest indexes account for about
25.49 GB, roughly 83% of `energy_kpis.db`.

Largest `cvm_financials.db` objects:

| Object | Bytes | Approx MiB |
|---|---:|---:|
| `financial_reports` | 169,152,512 | 161.32 |
| `sqlite_autoindex_financial_reports_1` | 52,924,416 | 50.47 |
| `idx_fr_cd_conta_period_label` | 40,067,072 | 38.21 |
| `idx_fr_cvm_year` | 33,103,872 | 31.57 |
| `idx_fr_cd_conta` | 31,240,192 | 29.79 |
| `idx_fr_cd_cvm_stmt_year` | 31,211,520 | 29.77 |

## Next Decision Gate

Use the exact attribution to drive the next Phase 5 slice. The safest next step
is a copy-based CCEE hourly hot/cold prototype, because the storage pressure is
concentrated in `ccee_plant_parcel_hourly` and its indexes. Do not start with
live database maintenance.
