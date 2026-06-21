# Phase 5.3 CCEE Hourly Hot/Cold Prototype

Date: 2026-06-21

Status: prototype tooling only. No live database maintenance, runtime routing,
schema migration, index drop, source deletion, or packaged-app behavior change
was implemented.

## Why This Exists

The exact Phase 5 `dbstat` inventory showed that `ccee_plant_parcel_hourly` and
its three largest indexes account for about 25.49 GB, roughly 83% of
`energy_kpis.db`.

This script gives a safe way to prototype the likely architecture direction:

- recent CCEE hourly months remain queryable in a small SQLite hot database;
- selected older months are exported as partitioned Parquet cold files;
- a manifest records row-count validation and source database signatures.

## Command

Bounded prototype, safe default row cap:

```powershell
python scripts/diagnostics/phase5_hot_cold_hourly_prototype.py `
  --output-dir C:\tmp\cvma-phase5-hot-cold `
  --hot-months 1 `
  --cold-month 2024-03 `
  --max-rows-per-month 100000
```

Full selected months, only for planned copy/prototype runs with enough disk:

```powershell
python scripts/diagnostics/phase5_hot_cold_hourly_prototype.py `
  --output-dir C:\tmp\cvma-phase5-hot-cold-full `
  --hot-months 1 `
  --cold-month 2024-03 `
  --full-months
```

The source `energy_kpis.db` is opened through a SQLite read-only URI with
`PRAGMA query_only = ON`.

## Output

The prototype writes:

```text
<output-dir>/
├── hot/
│   └── energy_hot.sqlite
├── cold/
│   └── ccee_plant_parcel_hourly/
│       └── reference_month=YYYY-MM/
│           └── part-0000.parquet
└── manifest.json
```

The manifest includes:

- source DB size/mtime before and after;
- selected hot/cold months;
- row cap or `full_months=true`;
- copied hot-row counts;
- exported cold-row counts;
- hot DB `PRAGMA quick_check`;
- validation status.

## Safety Boundaries

- The script never writes to the source database.
- The default row cap prevents accidental multi-GB prototype output.
- Existing output directories are refused unless `--replace-output` is passed.
- Output cannot be the source DB path or its DB directory.
- Parquet export requires `polars`, already listed in project requirements.

## Validation

Focused fixture tests cover:

- bounded row-copy behavior;
- full selected-month copy/export behavior;
- source database signature unchanged;
- generated hot SQLite `quick_check`;
- existing-output refusal.

Manual validation in this Codex sandbox compiled the script and executed those
test functions directly because the sandbox Python runtime does not include
`pytest` or `polars`.

## Next Decision Gate

Run the bounded prototype against the real Documents data root in a normal
project Python environment with `polars` installed. If the manifest validates,
use the measured hot SQLite and cold Parquet sizes to decide whether a real
hot/cold migration design is worth planning.
