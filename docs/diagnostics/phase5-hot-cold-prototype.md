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

## Local Run Results

The prototype was run against the real local `energy_kpis.db` on 2026-06-21.
Both runs kept the source DB size/mtime unchanged and produced a valid manifest.

Bounded smoke run:

```powershell
python scripts/diagnostics/phase5_hot_cold_hourly_prototype.py `
  --output-dir C:\tmp\cvma-phase5-hot-cold-bounded `
  --replace-output `
  --hot-months 1 `
  --cold-month 2024-03 `
  --max-rows-per-month 100000
```

Results:

- hot SQLite: 100,000 rows, 37,908,480 bytes;
- cold Parquet: 100,000 rows, 4,803,375 bytes;
- validation: OK;
- source unchanged: yes.

Full selected-month run:

```powershell
python scripts/diagnostics/phase5_hot_cold_hourly_prototype.py `
  --output-dir C:\tmp\cvma-phase5-hot-cold-full-one-month `
  --replace-output `
  --hot-months 1 `
  --cold-month 2024-03 `
  --full-months
```

Results:

- hot month `2026-04`: 2,827,440 rows, 1,084,678,144 bytes;
- cold month `2024-03`: 2,310,864 rows, 113,633,074 bytes;
- validation: OK;
- source unchanged: yes.

This confirms that cold Parquet is materially smaller for older hourly data,
but it does not prove runtime query behavior yet. The next design step should
measure read patterns before proposing any live routing or migration.

## Validation

Focused fixture tests cover:

- bounded row-copy behavior;
- full selected-month copy/export behavior;
- source database signature unchanged;
- generated hot SQLite `quick_check`;
- existing-output refusal.

Manual validation also compiled the script and ran the bounded and full
selected-month prototype commands above against the real local data root.

## Next Decision Gate

Plan a read-path design for CCEE hourly data before any migration proposal. The
design should preserve the raw SQLite source as canonical, keep a rebuildable
manifest, and prove equality/performance for the user-facing hourly drill-downs
before changing runtime routing.
