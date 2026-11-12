# Bounded annual refresh validation (#484)

The persistent refresh worker now reuses annual source preparation across two
compatible, already queued company jobs. Each company keeps its claim, progress,
transaction and result. No database migration, existing-data repair, dependency
change or multi-window implementation is included. This is source-code delivery,
not a packaged release.

## Method

Baseline: accepted #483 on `13cd067ea7f8d8c2b8b0fb35b496c36c5f2a5038`.
Petrobras (CVM 9512) and Vale (4170) entered the real persistent queue with
`source_scope=on_demand`. Three alternating pairs used identical copied official
DFP/ITR ZIPs for each scope. Each run had a fresh Python process and disposable
data directory; the Windows filesystem cache was not flushed. Annual ZIP bodies
were cached, while normal official CVM catalog GET and freshness HEAD requests
remained enabled. No tests, builds, application runtime or Git maintenance ran
during the final measurements.

Resident/private memory was sampled every 50 ms for the worker process tree;
logical data plus temporary-file size every 250 ms, including ZIPs, extracted
CSVs, database/WAL and generated workbooks. These are sampled peaks, not exact
instantaneous maxima or physical disk allocation. Queue time excludes Python
startup; process time includes startup, output checks and monitoring overhead.
The host had 31.69 GiB usable RAM and 28 logical CPUs. This is not 8 GB acceptance.

## Repeated results

Medians of three runs; memory/disk columns are medians of sampled peaks.

| Scope | Version | Queue s | Process s | Resident GiB | Private GiB | Data/temp GiB | CSV parses / extractions |
|---|---|---:|---:|---:|---:|---:|---:|
| 2022-2024 | baseline | 35.936 | 38.548 | 2.676 | 4.328 | 1.523 | 84 / 84 |
| 2022-2024 | candidate | 29.936 | 32.826 | 1.286 | 2.529 | 1.523 | 42 / 42 |
| 2024-2024 | baseline | 10.786 | 13.291 | 1.214 | 2.646 | 0.511 | 28 / 28 |
| 2024-2024 | candidate | 9.308 | 11.797 | 0.915 | 2.245 | 0.511 | 14 / 14 |

- 2022-2024: queue time fell **16.7%**. Baseline range 34.906–37.072s; candidate 29.446–31.598s. Observed retained subsets: 25.56 MiB; idle retention: zero in every run.
- 2024-2024: queue time fell **13.7%**. Baseline range 10.728–11.310s; candidate 9.285–9.521s. Observed retained subsets: 8.57 MiB; idle retention: zero in every run.

Disk footprint is essentially unchanged: reuse avoids repeated work but keeps
the same source files and persisted results. It is not database compression.
The 128 MiB budget limits retained source subsets, not total process memory.

## Stage timings

Median seconds for both companies together. Download preparation includes
freshness checks and extraction. CSV read is inside read/filter/convert;
database transaction is inside persistence/Excel. Do not sum nested rows.

| Stage | 2024 baseline | 2024 candidate | 2022–2024 baseline | 2022–2024 candidate |
|---|---:|---:|---:|---:|
| Company catalog | 0.427 | 0.426 | 0.426 | 0.428 |
| Download preparation | 1.165 | 0.625 | 4.392 | 1.709 |
| ZIP extraction (nested) | 1.067 | 0.513 | 4.281 | 1.573 |
| Read/filter/convert | 2.355 | 1.340 | 7.036 | 3.926 |
| CSV read and subset/cache handling (nested) | 2.171 | 1.237 | 6.475 | 3.612 |
| Financial transformation/QA | 0.482 | 0.454 | 1.467 | 1.403 |
| Persistence and Excel | 6.226 | 6.299 | 21.919 | 21.857 |
| Database transaction (nested) | 4.333 | 4.387 | 15.076 | 15.087 |

## Correctness and isolation

All four normalized table hashes matched across all six runs within each scope:
`financial_reports`, `financial_source_observations`, `financial_value_lineage`
and `qa_logs`. Only volatile IDs/timestamps were excluded. Source ZIP hashes also
matched. Exact hashes, stage ranges, per-company times and raw sample summaries
are in the companion [evidence JSON](2026-11-11-bounded-refresh-validation.evidence.json).

| Scope | Financial cells | Sources | Lineage | QA events |
|---|---:|---:|---:|---:|
| 2022-2024 | 7446 | 7135 | 7409 | 1225 |
| 2024-2024 | 2482 | 2390 | 2482 | 309 |

Every queue run completed both company job claims on their first attempt, with separate
progress and completion records. The cohort released retained frames at idle.
One baseline and one candidate three-year run each logged a transient SQLite
lock warning in the heartbeat writer; all imports still completed. All runs
are retained. Per-run heartbeat warnings and company write retries are
counted in the evidence JSON. This existing contention remains a #485 check.
Audit hooks rejected writes and SQLite access outside the sandbox. Hashes and
metadata of the original research checkout data, existing user data and baseline
data stayed unchanged. Runtime tests used another disposable root.

## Tests and runtime

- 32 bounded-reuse regressions cover all seven statement file families, source
  mutation/missing/corrupt files, byte/time/cohort bounds, skipped years, failures,
  retry, cancellation callback, stop and independent company outputs.
- Real-source measurements found an empty-subset conversion defect when PyArrow
  was unavailable. A regression reproduced the lost columns and disabled cache.
  The fallback now preserves empty column names/types; nonempty financial
  conversion is unchanged. Final measurements exclude the pre-fix diagnostic runs.
- After that fix, 134 focused tests passed. Full `tests/` plus `apps/api/tests/`:
  **1,012 passed, 3 failed, 1 skipped** in 67.94s. The three unchanged Windows
  entity relationship/resolution clock failures remain tracked in
  [#489](https://github.com/joaosantossgp/analysis/issues/489); no new failing module.
- All 44 repository/CI/bridge-inventory/packaged-harness contract tests passed.
- The Vite production build passed. No frontend or bridge contract changed.
  Real built Vite plus pywebview exercised empty queue, individual progress,
  deliberately injected Vale failure, and explicit successful retry. Petrobras
  success remained separate. The refreshed Vale DRE returned QA evidence and
  reported Q3 EPS 3.14. No JavaScript errors; 1366 and 900 px layouts inspected.
  The deliberate 1.5s state-observation delay is excluded from benchmarks.
- Existing service cancellation behavior is tested. Persistent jobs still have
  no public cancellation API; this delivery does not add or claim one.
- Storage budget and SQLite integrity/foreign-key checks passed. The strict
  managed-ingestion guardrail reports missing optional CCEE, MMGD and fuel
  distribution manifests in this financial-only sandbox; it is not a complete
  sector-data release gate. Effective financial writer settings remain WAL and
  `synchronous=OFF`; timings do not prove crash durability.
- Independent Ponytail review of the final code and empty-subset regression:
  Ship. `git diff --check` passed.

## Limits and next step

[#485](https://github.com/joaosantossgp/analysis/issues/485) remains open for the
packaged application on Windows 11 with 8 GB RAM and 30 GB free disk: whole
desktop/WebView memory, navigation and historical-chart latency during imports,
offline reads, restart/recovery and backup/restore. A representative larger
universe and latency criteria still need to be agreed before expanding the sample.
No storage-engine migration or multi-window implementation follows from these
throughput measurements alone.

Local detailed artifacts: `scratch/bench484/{baseline,candidate}_final_*`,
`scratch/bench484/ui-smoke`, `scratch/484-final-tests.{log,xml}`. These are ignored
scratch evidence; the companion JSON publishes the comparison and source hashes.
