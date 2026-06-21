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

## Read-Path Comparison

Phase 5.4 adds a diagnostic-only comparison script:

```powershell
python scripts/diagnostics/phase5_compare_hourly_read_paths.py `
  --manifest C:\tmp\cvma-phase5-hot-cold-full-one-month\manifest.json
```

Optional examples:

```powershell
python scripts/diagnostics/phase5_compare_hourly_read_paths.py `
  --manifest C:\tmp\cvma-phase5-hot-cold-full-one-month\manifest.json `
  --runs 5 `
  --output docs/diagnostics/phase5-hourly-read-path-comparison.json

python scripts/diagnostics/phase5_compare_hourly_read_paths.py `
  --manifest C:\tmp\cvma-phase5-hot-cold-full-one-month\manifest.json `
  --tier cold `
  --plant-parcel-code 1001 `
  --reference-month 2024-03 `
  --start-datetime 2024-03-01T00:00:00 `
  --end-datetime 2024-03-31T23:59:59
```

The comparison script:

- opens the canonical source `energy_kpis.db` with a SQLite read-only URI;
- opens the prototype hot SQLite DB with a SQLite read-only URI;
- reads cold Parquet partitions with `polars`;
- compares the hourly chart source rows row-for-row;
- records row hashes, elapsed read timings, source DB signatures, and
  mismatches;
- writes JSON only when `--output` is provided.

Automatic samples use full-month windows for `--full-months` prototypes. For
bounded prototypes, automatic samples use the exact first exported timestamp so
the comparison proves exported-row equality without pretending the bounded
artifact contains the full source month.

Local comparison against
`C:\tmp\cvma-phase5-hot-cold-full-one-month\manifest.json` passed with
`--runs 3`:

- hot sample: `2026-04`, parcel `1000672`, 720 rows, raw and hot row hashes
  matched;
- cold sample: `2024-03`, parcel `20001`, 744 rows, raw and cold row hashes
  matched;
- source DB signature unchanged: yes;
- report: `docs/diagnostics/phase5-hourly-read-path-comparison.json`.

## Next Decision Gate

Broaden the read-path comparison across more parcels, months, and at least one
ANEEL plant aggregation case before changing runtime routing. If those samples
match the raw SQLite rows and timings are acceptable, the next implementation
plan can introduce a backend read adapter behind the existing hourly chart
method. That adapter must still keep raw SQLite as the canonical fallback and
must ship behind equality tests before routing is changed.
