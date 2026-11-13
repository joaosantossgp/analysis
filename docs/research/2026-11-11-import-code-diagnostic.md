# Import code diagnostic

> Historical evidence at baseline `5971c47`, published for #482. Code references,
> measurements and implementation gaps below describe 2026-11-11, not current main.
> See the [2026-11-13 review and delivery reconciliation](2026-11-13-local-data-evidence-review.md)
> for completed follow-ups, verification and remaining limits.

Date: 2026-11-11. Status: static diagnostic; no measured bottleneck or approved implementation.
Baseline: `5971c4743aab784f33bcd0cf33bb4fa930fe17f9`. Scope: active CVM refresh and CCEE hourly managed storage. No application imports, runtime database access, network ingestion or benchmarks were performed. Only this note was written.

## Findings ranked for measurement

### 1. Desktop company jobs can repeatedly parse the same annual CVM files

The active desktop worker is constructed in `desktop/bridge_api/refresh.py:1215` and runs at `:1223`. Each claimed job calls the refresh service (`src/refresh/job_worker.py:182`) with a single company and its requested year range (`:272`). Each planned execution constructs a new scraper (`src/refresh/service.py:498`), whose CSV cache is instance-local (`src/financials/scraper.py:131`).

Within one scraper run, year/document download tasks are deduplicated (`scraper.py:699`), and parsed files are cached (`:356`). Across separate company jobs, however, overlapping annual CSVs can be parsed again. Existing ZIPs undergo a remote metadata check (`:269`), and selected CSVs are extracted even when the ZIP is reused (`:298`, `:334`). This is repeated checking/extraction/parsing, **not evidence that every company downloads the ZIP again**. Planning can skip complete work before constructing the scraper (`service.py:467`).

**Needs validation:** number of overlapping planned jobs, actual HEAD/GET counts, cache-hit rates and time spent extracting/parsing. This is the strongest code-supported work-amplification hypothesis; first compare two eligible company jobs sharing a year on an isolated copy.

### 2. CVM import materializes full files, filters per company and always exports Excel

The Polars path reads a full CSV before selecting columns (`src/financials/scraper.py:361`, `:368`); its exception path reads with pandas (`:372`). Each company filters the cached file and converts selected rows to pandas (`:408`, `:413`). Cached frames remain until the run ends (`:853`). Companies are processed sequentially (`:742`); the download pool is capped at eight independently of the stored `max_workers` value (`:121`, `:719`). This does not establish that additional writer concurrency would help.

Every successfully processed company calls `generate_excel` (`:817`), which commits database work through `insert_company_data` (`:627`) and then writes an openpyxl workbook (`:638`). Thus import wall time includes Excel serialization and lock retries. An export failure can occur after database persistence; timing and status interpretation must distinguish these stages.

**Needs validation:** parser branch actually used, full-frame/cache peak memory, filtering/conversion cost and Excel share of total time. Do not remove financial transformations or audit-ready export behavior merely to reduce runtime.

### 3. CVM writes are batched, but small batches and transformation inside the transaction deserve measurement

`src/financials/database.py:374` uses multi-row `to_sql`; the batch size is capped by 900 divided by column count (`:254`, `:405`). The 12-column financial payload (`:566`) therefore uses at most 75 rows per multi-row insert under this rule. This is not row-by-row insertion. One company transaction starts at `:424`, replaces scoped company/year rows (`:442`), performs wide-to-long conversion (`:531`) and concatenation/deduplication (`:574`) before inserting (`:587`). Index definitions exist at `:112` through `:125`; their actual presence, use and write cost were not inspected.

**Needs validation:** parameter limits of the bundled SQLite, insert-call counts, transformation versus execution/commit time, lock wait, index plans and WAL growth. Smaller SQL batches may add overhead, but neither increasing them nor dropping indexes is justified by code inspection alone.

### 4. Managed energy storage still performs several large materializations and rollover operations

The active hourly caller parses a snapshot and invokes managed persistence (`src/energy_kpi/plant_parcel_refresh.py:171` through `:188`). The managed path is conditional on an external-store catalog (`src/energy_kpi/hourly_store_ingest.py:57`); unmigrated installations can use the caller's SQLite fallback (`plant_parcel_refresh.py:181`).

Managed writes copy each month into a full Python tuple list (`hourly_store_ingest.py:304`, `:329`) before `executemany`, committing after the requested months (`:334`). Mart preparation then copies the full input again and builds the entire list of dictionaries before slicing it into 50,000-record execution batches (`:499` through `:510`). Those batches bound SQL calls, not the full in-memory record list. Temporary mart indexes are also built (`:511`).

Cold rollover is chunked at 100,000 rows (`:28`, `:467`), but includes ordered SQLite reads (`:454`), Parquet writes (`:473`), deletion of rolled hot rows and a `VACUUM` whenever rollover occurs (`:406` through `:412`). These are separate CPU, memory and I/O candidates. Raw evidence is a separate retained layer: for example local plant snapshot intake copies source bytes, hashes them and counts rows (`src/energy_kpi/plant_parcel_ingest.py:238` through `:253`). Raw retention is not redundant solely because normalized Parquet exists.

**Needs validation:** actual managed/fallback route, imported month sizes, peak memory, sort/index cost, rollover frequency, temporary disk headroom and VACUUM time. Recovery also needs a separate check: cold rewriting removes the existing month directory before writing replacement parts (`hourly_store_ingest.py:449`), while manifest/catalog publication occurs later (`:92`). This is a static interruption risk, not evidence of a past failure.

### 5. Existing logs support outcomes better than full phase attribution

CVM persists `RefreshResult` to `refresh_runs.jsonl` (`src/refresh/service.py:419`); its contract records company results and planning counts, without dedicated per-phase timings (`src/platform/contracts.py:153` through `:186`). Queue records have start/finish fields (`src/refresh/jobs.py:63`, `:65`), but job elapsed time cannot isolate download, parsing, conversion, database or Excel cost.

Energy has some useful instrumentation: mart rebuild timing (`src/energy_kpi/plant_marts.py:52`, `:125`), persisted aggregate duration (`src/energy_kpi/plant_parcel_refresh.py:304`), and before/after storage telemetry (`src/energy_kpi/hourly_store_ingest.py:100`). The managed persistence function does not separately time hot insertion, record conversion, cold serialization and VACUUM. Actual logged values and completeness were not examined here.

## Smallest useful follow-up

Use provenance-recorded copies and agreed workloads to measure those stages separately, including CPU, peak process memory, bytes read/written, transaction/lock time, WAL/temp growth, output rows and result parity. Start with overlapping CVM company jobs and one representative hourly month, then one rollover case. Correlate the root diagnosis's live inventory/log evidence with these paths before naming the dominant bottleneck. The static evidence does not justify a database replacement, broad rewrite, deletion of source evidence or a production import run.
