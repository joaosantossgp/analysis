# Standalone source-memory validation (#495)

Giving standalone refresh jobs the existing bounded source context reduced
three-year median resident memory from **2.672 to 1.425 GiB (46.7%)** across
three controlled pairs. Within each scope, every candidate resident-memory peak
was below every baseline peak. All four financial/evidence table hashes and all
24 ingestion workbooks remained equivalent. Three-year throughput was effectively unchanged; no disk
reduction is claimed. **The exact candidate package completed the isolated lifecycle.**

## Change and provenance

The [worker admission change](../../src/refresh/job_worker.py#L191) starts with
the current company and optionally adds the compatible, never-attempted FIFO
next job. Existing parser/cache code filters and independently copies the
admitted company rows. Standalone completion releases the context immediately.
Force/retry exclusions, the 128 MiB retained-row budget, 60-second reuse limit,
financial rules, source files, schema, engine and dependencies are unchanged.

The measured baseline is #485 checkout `893f7348ad7766f94f9cb1c722b424145bce8795`.
Its entire Git tree equals merged base `c42fca7caa0f9e47716e21259a3eae7874e41bbf`
(`bb2982a21cd1519bfe1e8f16e90ae62cb0e5d5e9`); their diff is empty. The candidate
uses that merged base plus the frozen worker change. Exact per-run source-file,
harness, raw-artifact and workbook digests are retained in the
[evidence JSON](2026-11-12-standalone-source-memory-validation.evidence.json).

## Controlled method

Petrobras (9512) and Vale (4170) entered the real persistent queue **separately**,
with completion and idle before admitting the second company. No two-company
cache reuse occurred. Three alternating baseline/candidate pairs for 2024 and
2022–2024 produced **12 runs and 24 first-attempt company jobs**. Each run used a
fresh process and disposable root with identical copied official annual ZIPs.
The same #485 Python interpreter ran all 12 cases: Python 3.11.15, pandas 3.1.1,
Polars 2.1.0, SQLAlchemy 2.1.8 and SQLite 3.53.1.

The Windows host had 31.69 GiB usable RAM and 28 logical CPUs. The filesystem
cache was not flushed. Annual ZIP bodies were local; ordinary official CVM
catalog GET and freshness HEAD requests remained enabled, with other HTTP hosts
blocked. Tests, builds, profiling and application runtime were stopped during
timing. Workbook comparison and full tests ran afterward.

Queue time includes admission, both individual jobs and the intervening idle
checks; process time also includes startup, output verification and monitoring.
Resident/private memory covers the worker process tree. Logical disk covers
data and temporary files, including ZIPs, CSVs, database/WAL and workbooks, but
excludes the package, backup and profiles. These are sampled peaks, not exact
instantaneous maxima or allocated disk space.

## Repeated results

Medians of three runs; memory and disk are medians of sampled peaks. GiB uses
powers of 1024. Parentheses show the observed resident-memory range.

| Scope | Version | Queue s | Process s | Resident GiB (range) | Private GiB | Data/temp GiB |
|---|---|---:|---:|---:|---:|---:|
| 2024 | baseline | 7.811 | 9.371 | 1.215 (1.198–1.222) | 2.624 | 0.511 |
| 2024 | candidate | 6.312 | 7.808 | 1.093 (1.070–1.134) | 2.397 | 0.511 |
| 2022–2024 | baseline | 17.891 | 19.732 | 2.672 (2.622–2.684) | 4.349 | 1.525 |
| 2022–2024 | candidate | 17.862 | 19.736 | 1.425 (1.327–1.466) | 2.568 | 1.524 |

Resident memory fell 10.0% for one year and 46.7% for three years; private memory
fell 8.7% and 41.0%. Three-year private ranges were 4.334–4.367 versus
2.555–2.596 GiB. Minimum available host RAM ranged from 3.639–3.778 GiB in
three-year baseline runs and 4.808–4.939 GiB in candidates; this is host-wide
context, not a controlled application allocation measurement.

One-year queue time fell 19.2%, with ranges 7.177–9.355 versus 6.284–6.884 seconds.
Three-year ranges overlapped: 17.393–20.153 versus 15.902–18.538 seconds. Its
median difference was only 0.16%, and the third candidate pair was 6.6% slower.
**No repeatable three-year speedup or universal throughput guarantee is claimed.**

At persistence, every baseline three-year company retained **42 full-market
frames / 6,329,156 rows**; one-year jobs retained 14 frames / 2,129,734 rows.
All candidates retained **zero scraper-local full-market frames**. Their bounded
contexts named only the current company: three-year Petrobras retained
13,561,068 bytes and Vale 13,245,665 bytes (about 12.9 and 12.6 MiB). All idle
checks found zero retained bytes. This removes retained full-market frames;
parsing still transiently reads full annual CSVs.

Parse and extraction counts stayed at 28 per one-year two-company run and 84
per three-year run. Disk ranges overlapped; the candidate still stores the same
source corpus. In the final three-year candidate, extracted CSVs occupied
1,448,999,217 bytes, source ZIPs 137,821,882 bytes and the database 27,770,880
bytes. **No disk reduction or source-deletion policy follows.**

Stage medians are wall-clock unions; nested stages must not be summed:

| Stage | 2024 baseline → candidate s | 2022–2024 baseline → candidate s |
|---|---:|---:|
| CSV read | 2.794 → 2.210 | 7.300 → 6.610 |
| Read/filter/convert, including CSV read | 3.101 → 2.327 | 7.998 → 7.060 |
| Annual download/extract tasks | 1.344 → 1.232 | 3.231 → 4.020 |
| Financial transformation | 0.560 → 0.510 | 1.511 → 1.447 |
| Persistence and Excel | 1.543 → 1.545 | 4.204 → 4.215 |
| Database transaction, within persistence | 0.527 → 0.525 | 1.645 → 1.635 |

## Sampling, equivalence and isolation

Configured intervals were 50 ms for memory and 250 ms for disk. Actual pooled
intervals across the three runs of each group were:

| Scope/version | Memory p50 / p95 / max ms | Disk p50 / p95 / max ms |
|---|---:|---:|
| 2024 baseline | 63 / 134 / 664 | 262.5 / 369 / 664 |
| 2024 candidate | 63 / 72 / 766 | 258 / 312 / 766 |
| 2022–2024 baseline | 64 / 96 / 1176 | 262 / 351 / 1176 |
| 2022–2024 candidate | 64 / 77 / 868 | 261 / 334 / 868 |

Normalized hashes matched within each scope for `financial_reports`,
`financial_source_observations`, `financial_value_lineage` and `qa_logs`; only
volatile row IDs/timestamps were excluded. Counts were respectively
2,482 / 2,390 / 2,482 / 309 for 2024 and 7,446 / 7,135 / 7,409 / 1,225 for
2022–2024. Source ZIP hashes matched across all runs.

The 24 actual XLSX files matched in sheet order, names, visibility, dimensions
and every cell's value/formula, type and number format, including source,
lineage and QA sheets. XLSX container timestamps were excluded; byte-identical
files are not claimed. All jobs succeeded on attempt one; no company-write
retry or heartbeat-lock warning was recorded. Audit guards confined writes and
database access to each sandbox. Every protected original-data fingerprint
remained unchanged.

## Tests and guardrails

Four new regression cases first failed because full-market frames survived until
persistence. The candidate passed **57** bounded-source, worker and refresh-service
tests, including singleton release, excluded next jobs, force/retry fallback and
existing pair/budget/lifecycle behavior. Protected originals were unchanged.

The full core/API suite recorded **1,027 passed, 3 failed, 1 skipped** in 66.89
seconds. The three failures are existing entity-resolution clock-boundary cases
tracked in [#489](https://github.com/joaosantossgp/analysis/issues/489), not a fully
green suite. Full-suite original-data fingerprints remained unchanged.

Storage budget, SQLite integrity and foreign-key checks passed on three-year
candidate run 1. Strict managed-ingestion validation failed for three absent
optional-sector manifests (CCEE hourly, MMGD and fuel distribution) in the
financial-only fixture. This is not a complete release gate. The financial writer
was verified as WAL with `synchronous=0` (OFF); the separate read connection
reported `synchronous=2`. The results do not establish crash durability.

## Packaged validation and limits

The canonical build at `d8a3d57d56a8e8f43f9b1219be123aa9106a4c96` passed the real UI import, populated readers during import, storage inventory error/retry, graceful shutdown, external backup/restore and offline reads. Both shutdowns were unforced, with no remaining owned process. Financial/audit and source hashes survived restoration; original data fingerprints were unchanged.

EXE SHA-256: `82b132bd65c21185fac12a288a850afa99e124aba81c71385ab28b9ce8976a39`. The bundle contains 2,647 files / 315,702,581 bytes and no database. Four populated-chart renders while the other company was running took 33.209, 43.735, 36.404 and 36.634 ms. These are warm samples, not a universal latency guarantee.

Whole-process sampled peaks were 2,071,769,088 bytes resident and 3,166,449,664 private. Minimum available host RAM was 4,466,511,872 bytes. The sampled disposable-root peak was 4,947,731,833 bytes, including backup and restored copies; the bundle is separate. Exact per-phase readings and achieved sampling intervals are in the evidence JSON. No invalid disk sample was recorded, and complete scans succeeded after both stops. Sampling still can miss transient peaks.

The build environment also contains API development dependencies; the prior package had a different bundle size. This single package run is a separate validation, not a controlled before/after resource comparison. The twelve worker benchmarks used the identical interpreter. The configured proxy allowed official CVM traffic during explicit refresh and blocked other traffic through it; this is not packet-level isolation. Non-child exit codes were unavailable. Backup/restore is an external procedure, not a shipped feature; storage error recovery does not establish failed financial-import or crash recovery.

Independent Ponytail review approved the frozen source, harness and benchmark evidence. The controller checked the final packaged evidence directly; the reviewer reached its usage limit before the final independent package-document pass.

The owner's 8 GB RAM / 30 GB free disk are efficiency references, not hardware gates. No migration, storage-engine change, multi-window implementation or release follows. The next storage question is extracted-CSV retention; no source deletion is authorized by this result.
