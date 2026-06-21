# Phase 5.1 Storage Inventory

Date: 2026-06-21

Status: diagnostic-only baseline. No data migration, live compaction, index
drop, runtime read-path change, DuckDB, or Parquet tier was implemented.

## Command

```powershell
python scripts/diagnostics/phase5_storage_inventory.py
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

## Next Decision Gate

Use this inventory to decide the next Phase 5 slice. The safest next step is a
copy-based prototype for energy hot/cold tiering or an exact `dbstat` run with a
SQLite CLI that supports the virtual table. Do not start with live database
maintenance.
