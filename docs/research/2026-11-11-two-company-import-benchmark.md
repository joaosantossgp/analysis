# Isolated two-company DFP/ITR import benchmark

> Historical evidence at baseline `5971c47`, published for #482. Code references,
> measurements and implementation gaps below describe 2026-11-11, not current main.
> See the [2026-11-13 review and delivery reconciliation](2026-11-13-local-data-evidence-review.md)
> for completed follow-ups, verification and remaining limits.

Date: 2026-11-11. Code baseline: `5971c4743aab784f33bcd0cf33bb4fa930fe17f9`.
Related research: #466. This is a measured pilot, not an architecture decision.

## Scope and result

Imported consolidated 2024 DFP/ITR for Petrobras (CVM 9512), then Vale (4170),
successfully through the current `CVMScraper`. Each company used a fresh scraper
instance and shared isolated source files. Petrobras started without ZIPs; Vale
reused the downloaded ZIPs. This mirrors the instance/cache boundary of separate
company jobs, but does not run the desktop queue, read marts, bridge or UI.

The run produced 1,240 financial rows for Petrobras and 1,195 for Vale. Both have
2024 annual and 1Q24–4Q24 period labels; these are pipeline outputs, not a claim
that the source publishes a separate fourth-quarter ITR. SQLite integrity check
returned `ok`. Both Excel files opened in read-only mode with BPA/BPP/DRE/DFC sheets.
Vale produced five `DFC_VALIDATION_FAILED` QA records (one labelled DRE, four DFC).
Their causes were subsequently traced in the
[Vale diagnosis](2026-11-11-vale-qa-diagnostic.md). Successful ingestion alone
is not financial acceptance; later fixes and remaining limits are in the review above.

## Timings

Seconds, one run, instrumentation included. Stages below exclude their nested
substage where applicable; tiny unlisted orchestration costs explain rounding gaps.

| Stage | Petrobras, empty file cache | Vale, ZIPs cached |
|---|---:|---:|
| Constructor/schema/account dictionary | 0.052 | 0.015 |
| Initial company catalog fetch/parse | 0.417 | 0.209 |
| Download or freshness check + extraction | 4.536 | 0.776 |
| Read/parse CSVs | 1.728 | 1.306 |
| Filtering/conversion, excluding CSV reads | 0.123 | 0.123 |
| Financial transformation | 0.092 | 0.117 |
| Database transaction, including payload preparation | 0.175 | 0.154 |
| Export preparation/identity lookup/Excel, excluding DB | 0.738 | 0.416 |
| **Company total** | **7.868** | **3.121** |

The monitored invocation took **13.765 s**, including process startup, imports,
cleanup and monitor overhead. The two company operations sum to 10.989 s.
Environment installation and subsequent validation are excluded.

DFP/ITR download tasks run concurrently. The combined stage uses the union of
their intervals, not their sum. Individual DFP/ITR task durations were
2.905/4.535 s for Petrobras and 0.352/0.776 s for Vale. Extraction calls summed
to 0.758 s and 1.017 s respectively, but overlap and are already included above.
HTTP event timestamps for streamed responses end at response headers; they are
**not** complete network-transfer timings. Pure transfer and extraction were
not separated into additive wall-clock stages.

Both companies performed 14 CSV reads with zero parsed-cache hits. Vale made
HEAD freshness checks and no second ZIP GET, yet extracted the same 14 files.
Each company fetched the official company catalog twice: initial catalog and
identity lookup during persistence/export. Sources and ZIP hashes are in the
[evidence JSON](2026-11-11-two-company-import-benchmark.evidence.json).

## RAM and disk

The isolated worker process tree reached **1.102 GiB resident RAM (RSS/working
set)** and **2.417 GiB private committed memory**. These are different metrics,
not quantities to add. RAM was sampled approximately every 50 ms. UI/WebView,
OS, monitoring controller and other applications are excluded.

| Retained data category | MiB |
|---|---:|
| Extracted consolidated annual CSVs, all companies | 465.25 |
| Original DFP/ITR ZIPs | 43.99 |
| SQLite database, both companies | 1.03 |
| Two Excel exports | 0.052 |
| Copied reference/account mappings | 0.323 |
| **Final data total** | **510.64** |

Peak sampled data + temporary-file size was **511.41 MiB**, measured every
250 ms. Logical file bytes are reported, not NTFS allocated space; brief peaks
between samples may be missed. The separate disposable Python environment used
260.62 MiB, excluded from data figures. Measurement logs/scripts add a small
additional amount. Both companies share the annual source files: 465 MiB must
not be multiplied by company count. Larger histories/other source classes are
not represented by this pilot.

## Isolation and reproducibility

All benchmark writes were directed to
`tmp/bench-20261111-two-companies/run1/` under the repository. The worker clears
inherited CVM/database configuration, sets explicit sandbox paths before imports,
asserts resolved settings paths, and uses a Python audit hook to reject observed
file writes/SQLite opens outside the sandbox. Explicit scraper directories prevent
constructor defaults from selecting the normal data roots. Requests were limited
to `dados.cvm.gov.br`; no market provider or external database was configured.

Original runtime and repository data files have identical sizes, modification
times and SHA-256 hashes before and after execution, rechecked after validation.
No application source was changed. Local harness, per-call events, 50 ms samples,
stdout, source ZIPs, CSVs, DB and workbooks remain in the isolated benchmark folder.
Evidence JSON contains aggregate results, exact byte sizes, versions, HTTP events,
row counts and source ZIP hashes without copying the protected data inventory.

Host: Intel Core i7-14700, 28 logical CPUs, 31.69 GiB usable physical RAM,
Windows build 26200; approximately 127 GiB disk free before setup. Dependencies
were installed into a new Python 3.11.15 environment: pandas 3.1.1, Polars 2.1.0,
SQLAlchemy 2.1.8, SQLite 3.53.1. This is not the packaged application's pinned
runtime. No repeat-run distribution, controlled OS cache or CPU/RAM limit was used.
The current engine configures WAL and `synchronous=OFF`
(`src/financials/database.py:36-37`). These transaction times reflect that existing
configuration; they are not a benchmark of a durability-preserving alternative
or evidence of crash/power-loss safety.

## What this establishes

For this workload, acquisition and repeated extraction/parsing dominate; SQLite
transaction time is small. The ~465 MiB extracted annual corpus dwarfs the ~1 MiB
normalized two-company database. These observations support investigating shared
annual parsing and source-file retention before changing database engines; they
do not establish the speedup of any proposed optimization.

Active implementation references: full-file CSV reading and instance cache in
`src/financials/scraper.py:356`; cached ZIP extraction in `:334`; combined database
and Excel generation in `:627`; company transaction in
`src/financials/database.py:424`. See the
[code diagnostic](2026-11-11-import-code-diagnostic.md) for callers and scope.

**Historical evidence gaps at this stage** (later delivery and owner decisions
are reconciled in the review above): desktop/packaged behavior; browsing during imports; larger company/year sets and other
data classes; recovery/durability; persistent marts; QA failures. No application
test suite ran because this experiment changed no application code. Verification
consisted of real imports, output inspection, DB integrity/counts and preservation
hashes. No migration, optimization or multi-window implementation was performed.
