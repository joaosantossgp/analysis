# Local-data research execution cycle

> Historical evidence at baseline `5971c47`, published for #482. Code references,
> measurements and implementation gaps below describe 2026-11-11, not current main.
> See the [2026-11-13 review and delivery reconciliation](2026-11-13-local-data-evidence-review.md)
> for completed follow-ups, verification and remaining limits.

Date: 2026-11-11. Baseline: `5971c4743aab784f33bcd0cf33bb4fa930fe17f9`.
Tracking: [#482](https://github.com/joaosantossgp/analysis/issues/482), contributing
to #466 under #464. Status: historical experiments complete; reviewed evidence published for #482.

## Execution contract

The owner authorized sequential research execution with progress updates between
steps, escalation for material decisions, and preservation of the current data.
This cycle compared batching, diagnosed the Vale QA alerts and expanded history
to 2022â€“2024 with concurrent backend reads. It did not authorize application
changes, financial remapping, migration or multi-window implementation.

All imports used separate directories under `tmp/bench-20261111-two-companies/`.
The original two-company run and its artifacts remain intact. Original runtime
and repository data sizes, modification times and SHA-256 hashes matched after
every monitored run and after validation. Workers rejected observed writes and
SQLite connections outside their sandbox; CVM/database environment overrides
were reset before importing the application. Empty sandbox DB files were created
before resolving settings to avoid the existing shared-worktree path fallback.
No application source changed. New environments and measurements are not a
packaged build; the host and dependency versions are documented in the
[initial benchmark](2026-11-11-two-company-import-benchmark.md).

## 1. Existing batch call versus separate company calls

Both paths used the same current code and identical preseeded 2024 ZIPs, a fresh
database and Petrobras/Vale in that order. Sequence: separate1, batch1, batch2,
separate2, separate3, batch3. Each invocation ran in a fresh process/environment
configuration. Operating-system caches and other host activity were uncontrolled;
HEAD/catalog requests remained live. This is a small repeated pilot, not a
statistically isolated performance laboratory.

| Metric | Separate calls | Existing batch call |
|---|---:|---:|
| Invocation elapsed, three runs (s) | 10.031 / 10.699 / 11.635 | 6.661 / 6.901 / 9.119 |
| Median invocation elapsed | 10.699 s | 6.901 s |
| Median core operations, excluding startup/cleanup | 7.966 s | 4.266 s |
| Median of sampled peak resident memory | 1.096 GiB | 0.950 GiB |
| Median of sampled private committed peaks | 2.420 GiB | 2.269 GiB |
| CSV calls / misses / hits | 28 / 28 / 0 | 28 / 14 / 14 |
| CSV extractions | 28 | 14 |
| HTTP HEAD / GET | 4 / 4 | 2 / 3 |
| Final financial rows / QA events | 2,435 / 5 | 2,435 / 5 |

Median invocation time was **35.5% lower** in the batch path. All six normalized
financial row hashes and QA hashes matched (database row IDs excluded). Workbook
binary equivalence was not asserted. Disk use remained approximately 511 MiB;
both paths retain the same source corpus. No ZIP GET occurred in these paired
runs; GETs were catalog requests. Batch catalog request count differs because of
existing identity-resolution behavior, not an experimental replacement.

The mechanism is observable: `_csv_cache` survives between companies within one
`CVMScraper.run` and is cleared at its end (`src/financials/scraper.py:356-389`,
`:738-853`). Download tasks run once per run (`:699-736`). The desktop worker
currently requests one company per job (`src/refresh/job_worker.py:272`), and
the service creates a scraper per request (`src/refresh/service.py:498`). This
experiment does not implement shared queue batching, cancellation or failure
semantics; those are the scope of #484.

## 2. Vale QA root cause

The [separate diagnostic](2026-11-11-vale-qa-diagnostic.md) reproduced every
alert and all 1,195 persisted Vale values against the source snapshot. The root
chain includes changing/reused account codes across periods, zero substitution
for missing predecessor cells, collapse of reported/YTD durations, and discarded
QA context. An unsupported derived Q4 zero is demonstrable. EPS is also present
in the affected DRE rows and needs its own semantic treatment.

These are correctness findings, not evidence that CVM/Vale annual totals are
wrong. No automatic name-based remapping or formula correction was performed.
The main agent reran the assertion-based replay and inspected the active
conversion, pivot and QA persistence code. #483 records the proposed conservative
correction boundary and acceptance tests at the time. #483 has since been
delivered; see the review above for its accepted contract and remaining limits.

## 3. Three-year import with concurrent reads

One bounded run imported consolidated 2022â€“2024 for the same two companies.
It started from a copy of the original 2024 DB so existing data was available
to read. 2024 ZIPs were cached; four official ZIPs for 2022/2023 were downloaded.
The reader used a separate service/engine in another thread in the same worker
process. It repeatedly requested 2024 company information, DRE matrices and
annual/quarterly financial KPIs, allowing direct before/during/after comparison.
It did not request market prices or render charts. Reader-originated HTTP was
blocked. The reader ran for about two seconds before and after import.

| Measurement | Result |
|---|---:|
| Core import operation | 19.965 s |
| Whole monitored invocation, including read setup/baseline/post-read windows | 28.510 s |
| Peak sampled resident RAM | 1.736 GiB |
| Peak sampled private committed memory | 3.077 GiB |
| Peak data + temporary files | 1.482 GiB |
| Retained data before validation | 1.481 GiB |
| Financial rows | 7,266 |
| QA events | 15, all Vale |

The final DB contained both companies in all three requested years; the 2024
account/period/value rows matched the initial one-year run. DB integrity returned
`ok`. The additional 2022/2023 QA events were retained but not individually
root-caused; financial acceptance of those years remains **Needs validation**.

During import, **450 calls completed without exceptions or empty responses**:

| Backend operation | Calls | Median | p95 | Maximum |
|---|---:|---:|---:|---:|
| Company information | 150 | 6.16 ms | 29.13 ms | 164.46 ms |
| DRE statement matrix | 150 | 10.57 ms | 35.99 ms | 174.81 ms |
| Financial historical KPIs | 150 | 38.39 ms | 108.22 ms | 489.25 ms |

These are complete service-call latencies, not SQL-only or UI frame timings.
The bridge consumes these methods (`desktop/bridge_api/companies.py:96`, `:172`,
`:336`), as does the HTTP adapter (`apps/api/app/routes/companies.py:282`, `:301`).
Reading without errors does not prove cross-call snapshot consistency or latest
data visibility. The sample is small and includes download time in the concurrent
window; the table does not isolate the commit interval.

An additional offline pass blocked all socket connections and exercised the full
three-year range: 40 statement calls (median 5.29 ms, p95 8.91 ms, max 17.81 ms)
and 40 KPI calls (29.52 / 44.62 / 67.21 ms). All returned nonempty results.
This validates those backend read paths offline, not the complete desktop app.

## Verification and limits

- RAM sampled at approximately 50 ms; disk at 250 ms. Peaks between samples can
  be missed. RSS and private commitment are different, nonadditive metrics.
- Storage-budget guardrail passed on the sandbox with a 30,000,000,000-byte
  active-data limit. This is not a full installed-footprint or backup budget.
- The strict managed-ingestion guardrail **failed** on missing CCEE, MMGD and
  fuel manifests. Those datasets were not imported by this DFP/ITR experiment.
  No fake manifests or unrelated energy ingestion were added to make it pass.
- Resource/time guards (5 GiB RSS, 7 GiB private commitment, 6 GiB per-run data,
  20 minutes) did not trigger. These are stop guards, not an 8 GB system emulator.
- Source ZIP hashes, per-run outputs/stages and read distributions are in the
  [evidence JSON](2026-11-11-local-data-cycle.evidence.json); raw traces and harness
  scripts remain local under the sandbox folder. Several run copies consume
  additional diagnostic disk space and are not the product's retained footprint.
  The whole benchmark folder, including the environment and all retained run
  copies, measured 5.227 GiB at final verification. Nothing was deleted.
- The current database uses WAL and `synchronous=OFF`
  (`src/financials/database.py:36-37`); timings do not establish crash durability.
- No application suite/packaged UI run was performed because this cycle changed
  only research/instrumentation. Assertions cover output equivalence, DB integrity,
  source/data preservation and the exact QA replay. No result certifies the real
  8 GB target, large universes, energy history, UI responsiveness or recovery.

## Follow-up delivery

The original sequence was #483 (financial QA), #484 (bounded source reuse), then
#485 (packaged validation). All are now delivered, as are #492 and #495.
The [publication review](2026-11-13-local-data-evidence-review.md) links their
artifact-specific evidence. These old measurements are not post-fix benchmarks.
The owner later made 8 GB RAM / 30 GB free disk an efficiency guide rather than
a mandatory hardware/VM gate. No new target-machine run is required to publish
this research. The owner subsequently closed #464 and #466 as not planned for
now; see the [incremental delivery direction](../PRODUCT_DIRECTION.md#delivery-direction-2026-11-13).
No migration or multi-window implementation is authorized by #482.
