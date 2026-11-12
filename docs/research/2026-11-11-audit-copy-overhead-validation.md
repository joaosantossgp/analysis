# Financial audit-copy overhead validation (#492)

Avoiding redundant pandas audit-metadata copies reduced the two-company refresh
queue median by **48.1% for 2024** and **57.1% for 2022–2024** against the accepted
#484 baseline. All four financial/evidence table hashes and all 24 ingestion
workbooks remained equivalent. This is source-code validation; packaged
performance and recovery remain under [#485](https://github.com/joaosantossgp/analysis/issues/485).

## Change and attribution

Three local boundaries now create independent tabular frames without carrying
audit `attrs`: [standardizer input and worksheet output](../../src/financials/scraper.py#L638),
and [database reshaping](../../src/financials/database.py#L577). Worksheet formatting
uses the same clean frame. Original reports retain complete source observations
and value lineage for explicit SQL and audit-sheet serialization. The public
standardizer, financial rules, schema, SQL, transactions, dependencies and Excel
engine are unchanged.

Baseline cProfile attributed 29.407 of 34.124 instrumented seconds for Petrobras,
and 28.905 of 33.346 seconds for Vale, to recursive `deepcopy`. Candidate profiles
recorded about 0.0001 seconds of `deepcopy` per company. Total INSERT cursor time
was 0.352 seconds before and 0.374 seconds after; SQL batching was not the measured
bottleneck. These diagnostic runs establish attribution, not throughput: profiling
adds overhead, and the candidate profile overlapped the full test suite. All
percentage gains below use separate unprofiled runs.

## Method

Baseline commit: `2173488a35ea81917c7f77e997f20750e3da8560` (#483 plus #484).
The candidate is that commit plus the frozen three-boundary diff and regression
tests; exact file SHA-256 values are in the [evidence JSON](2026-11-11-audit-copy-overhead-validation.evidence.json).

Petrobras (CVM 9512) and Vale (4170) entered the real persistent refresh queue
with `source_scope=on_demand`. Three alternating baseline/candidate pairs per
scope produced **12 runs total**. Each used a fresh process, disposable data root
and identical copied official DFP/ITR ZIPs. The filesystem cache was not flushed;
annual ZIP bodies were cached, while normal official catalog GET and freshness
HEAD requests remained enabled. Tests, builds, profiles and application runtime
were stopped during these timing runs.

Resident/private memory was sampled every 50 ms for the worker process tree;
logical data plus temporary-file size every 250 ms, including sources, extracted
CSVs, database/WAL and workbooks. These are sampled peaks, not exact instantaneous
maxima or physical allocation. Queue time excludes process startup; process time
includes startup, output checks and monitoring. Stage intervals are wall-clock
unions, and nested stages must not be summed. The Windows host had 31.69 GiB
usable RAM and 28 logical CPUs; Python 3.11.15, pandas 3.1.1, Polars 2.1.0,
SQLAlchemy 2.1.8 and SQLite 3.53.1 were recorded in every run.

## Repeated results

Medians of three runs; memory/disk columns are medians of sampled peaks.

| Scope | Version | Queue s | Process s | Resident GiB | Private GiB | Data/temp GiB |
|---|---|---:|---:|---:|---:|---:|
| 2024 | baseline | 9.249 | 11.081 | 0.852 | 2.253 | 0.511 |
| 2024 | candidate | 4.804 | 6.802 | 0.900 | 2.237 | 0.512 |
| 2022–2024 | baseline | 29.407 | 31.716 | 1.235 | 2.494 | 1.523 |
| 2022–2024 | candidate | 12.606 | 14.906 | 1.286 | 2.535 | 1.523 |

Queue ranges were 9.181–11.042 versus 4.556–5.380 seconds for 2024, and
29.034–32.335 versus 11.517–13.228 seconds for 2022–2024. Persistence plus Excel
fell from 6.225 to 1.619 seconds and from 22.078 to 4.311 seconds, respectively.
The nested database transaction fell from 4.323 to 0.540 seconds and from
15.113 to 1.605 seconds. Source work remained 14 parses/extractions per one-year
run and 42 per three-year run.

**No RAM or disk improvement is claimed.** Median resident peaks increased 5.6%
and 4.1%, with overlapping ranges: 0.832–0.945 versus 0.859–0.913 GiB for 2024,
and 1.166–1.344 versus 1.199–1.325 GiB for 2022–2024. Logical disk footprint was
essentially unchanged. The result supports reducing redundant work, not storage
compression or a universal performance guarantee.

## Correctness, isolation and tests

Normalized hashes matched for `financial_reports`,
`financial_source_observations`, `financial_value_lineage` and `qa_logs` across
all six runs within each scope; only volatile IDs/timestamps were excluded.
Source ZIP hashes also matched. The 2024 scope retained 2,482 financial cells,
2,390 sources, 2,482 lineage rows and 309 QA events; 2022–2024 retained 7,446,
7,135, 7,409 and 1,225 respectively.

The 24 actual XLSX files were compared after timing. Sheet order, names, state,
dimensions and every cell's value/formula, type and number format matched within
each scope, including all audit sheets. Container timestamps were excluded;
byte-identical ZIP files are not claimed. Per-sheet digests are published in the
companion JSON.

All 24 company job claims completed on their first attempt, with separate
progress and results, no company-write retries, and zero retained cache at idle.
All six candidate runs had no heartbeat lock warnings. Baseline three-year run 1
had one transient heartbeat lock warning and is included in the results.
Audit hooks blocked writes and SQLite access outside each sandbox. Protected
research/user/checkout data fingerprints remained unchanged in every run.

- Eight regressions first failed on redundant recursive audit copies, then passed
  with zero copies. They check real SQLite and workbook output, full audit payloads,
  input preservation on success and injected database/workbook failures, rollback,
  reported EPS 3.14 and unavailable Q4. Both standardizer modes are covered.
- 149 focused financial QA, scraper, database-portability and bounded-refresh
  tests passed. The final eight-test rerun also passed. Constructor characterization
  preserved named index, mixed column labels, extension dtypes and original input.
- Full `tests/` plus `apps/api/tests/`: **1,019 passed, 4 failed, 1 skipped** in
  74.37 seconds. All four failures are the existing Windows clock-related entity
  relationship/resolution cases tracked in
  [#489](https://github.com/joaosantossgp/analysis/issues/489). The suite is not fully green.
- Storage budget, SQLite integrity and foreign-key checks passed on the final
  three-year candidate. Strict managed-ingestion validation exited **1** with
  three missing manifests: CCEE hourly, MMGD and fuel distribution. These optional
  sectors are absent from the financial-only fixture; no complete release gate is
  claimed. The financial writer remains WAL with `synchronous=OFF`; the results
  do not prove crash durability.

## Remaining validation

The owner's 2026-11-11 clarification makes **8 GB RAM / 30 GB free disk an
efficiency reference only**, not a mandatory machine or VM acceptance gate.
#485 continues on the available Windows host: exact-source packaged build,
desktop/WebView resource use, navigation and historical-chart responsiveness
during imports, offline reads, restart/recovery and backup/restore. These checks
are **Needs validation** here. No broader issuer sample, release, storage-engine
migration or multi-window implementation is implied.

Local raw artifacts: `scratch/bench492/*_final_*`,
`scratch/profile-persistence/candidate_profile_3y`,
`scratch/492-full-tests.{log,xml}` and the baseline profile in the #485 worktree.
The companion JSON retains the full comparison, workbook digests, guardrail
results, source/frozen-file hashes and test provenance. Its unchanged raw harness
note about target-8-GiB acceptance is historical wording, superseded by the
owner's reference-only clarification above.
