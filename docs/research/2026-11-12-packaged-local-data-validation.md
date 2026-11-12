# Packaged local-data validation (#485)

The exact post-#492 Windows package completed the bounded lifecycle in **run 03**:
actual UI imports, readable financial evidence, visible storage failure/retry,
graceful shutdown, full-fixture backup/restore and offline reads. **Run 04 remains
failed**: its import and offline UI checks passed, but the disk monitor received
Windows access denied on a temporary WebView directory during final shutdown,
then forced cleanup of one owned process. Its completed import phase supplies
the separate populated-reader measurements below, not another clean lifecycle pass.

## Artifact and workload

- Source: `6ff589a6fffc33147a4d784e130a33fc688a7920`; version `0.30.0-rc.1`,
  built by `desktop/build_desktop.ps1` at `2026-11-12T02:44:27Z`.
- EXE SHA-256: `6c7f42ca3200f822cd70c2277dc9fdda9c12f8a9af968298364cdfe814cb3a78`.
  The complete bundle contains 2,640 files and 308,861,801 bytes; no database
  file was bundled. No tag or release was published.
- Actual Windows host: build 26200, 31.69 GiB usable RAM, 28 logical CPUs;
  run 03 began with about 5.93 GiB available RAM. **8 GB RAM / 30 GB free disk
  remain efficiency references only**, with no mandatory hardware or VM gate.
- Each fresh fixture contained company metadata for Petrobras (9512) and Vale
  (4170), plus identical copied official DFP/ITR ZIPs for 2022–2024. The real
  packaged Vite/pywebview UI selected the custom history range and CVM financial
  data with market-data download disabled. No financial rows were seeded.

The [evidence JSON](2026-11-12-packaged-local-data-validation.evidence.json)
contains exact build/dependency provenance, per-run frozen harness hashes,
source hashes, sampled resources, UI measurements and database results.
Run 03 queued both companies from the fresh UI. Run 04 first imported and
rendered Petrobras, then imported Vale while revisiting populated Petrobras
views. These are different scenarios, not repeated throughput measurements.

## Imports and UI responsiveness

All four company jobs across runs 03/04 succeeded on their first attempt. The
persisted job intervals were:

| Scenario | Petrobras execution s | Vale execution s | Interpretation |
|---|---:|---:|---|
| Run 03, fresh two-job queue | 11.735 | 5.764 | Individual job start to finish; excludes queue wait |
| Run 04, prepared reader | 10.514 | 10.568 | Petrobras prepared first; Vale then runs alongside UI reads |

Progress exposed queued, planning, download/extract, process-data,
persist-reports, finalizing and success states. The evidence records transitions
as sampled observations; it does not turn polling intervals into exact stage
durations. Directory, chart, DRE and DFC routes were inspected at 1366×768 and
900×768. Empty, loading, content, populated-chart and partial/stale states were
observed; neither final UI run reported console/page errors or route gaps.

Run 03 had **zero populated-chart samples while an import was active**. Its
fast empty-view navigation is not evidence for populated-chart contention.
Run 04 supplied four Petrobras chart renders while Vale was recorded **running**:
33.490, 36.256, 35.755 and 35.194 ms. Nearest-rank p50 was 35.194 ms and p95/max
36.256 ms. One additional 42.252 ms sample occurred while Vale was queued and is
reported separately. Four populated Petrobras statement routes with Vale running
had p50 39.543 ms and p95/max 42.728 ms.

These are small, warm-view samples. The first populated Petrobras chart in
run 04 took **1,342.605 ms** before Vale was queued. The largest explicit statement
bridge probe after import took **1,444.354 ms**. Bridge probes do not include every
React query; screenshots can delay observations, and 350 ms pacing between routes
is excluded from render timings. No universal latency SLA is inferred.

| Run 03 UI phase | Routes | Render p50 / p95 / max ms | Bridge probes | Bridge p50 / p95 / max ms |
|---|---:|---|---:|---|
| Initial empty fixture | 12 | 34.318 / 41.515 / 41.515 | 16 | 2.772 / 123.284 / 123.284 |
| Import phase, including post-import checks | 62 | 34.960 / 234.864 / 291.228 | 136 | 6.596 / 305.710 / 1239.697 |
| Restored fixture, offline | 12 | 39.546 / 612.829 / 612.829 | 16 | 9.985 / 1237.660 / 1237.660 |

The JSON separates route and bridge timings by measurement stage, visible state,
and recorded job activity. It preserves the four running and one queued chart
samples rather than blending them into an overall responsiveness number.

## Resources and sampling limits

Observed peaks for the owned EXE/WebView process tree; GiB uses powers of 1024.
Disk covers the entire disposable root, including backup, restored copy,
profiles, temporary files and evidence. Available RAM is host-wide.

| Run / phase | Resident GiB | Private GiB | Minimum available GiB | Sampled root GiB |
|---|---:|---:|---:|---:|
| 03 initial | 0.616 | 1.120 | 5.306 | 0.135 |
| 03 import | 1.839 | 2.852 | 3.539 | 1.531 |
| 03 storage error/retry | 1.637 | 2.672 | 3.799 | 1.549 |
| 03 offline restore | 0.861 | 1.383 | 4.214 | 4.614 |
| 04 initial | 0.620 | 1.121 | 5.572 | 0.136 |
| 04 prepared-reader import | 3.245 | 4.737 | 3.028 | 1.514 |
| 04 storage error/retry | 1.459 | 2.661 | 5.215 | 1.549 |
| 04 offline, before cleanup failure | 0.855 | 1.381 | 5.475 | 4.613 |

The larger run 04 memory peak is part of the result; run 03 is not a bound for
the populated-reader workload. Resource limits were not an 8 GB acceptance test.

The monitor was configured for 50 ms memory and 250 ms disk sampling, but achieved
cadence differed. Run 03 recorded 1,352 memory samples: interval median/p95/max
73/102/157 ms. Its **83 disk samples spanned 100.171 seconds**, with interval
median/p95/max **0.263/8.180/19.961 seconds**. Run 04 recorded 1,138 memory samples
(72/98/178 ms) and 69 disk samples over 83.865 seconds
(0.267/8.891/12.331 seconds). The run 03 import phase itself had only three disk
samples, separated by 11.981 and 13.053 seconds. Long gaps can miss transient peaks; sampled
logical file size is neither exact peak usage nor physical allocation.

Run 03's complete stopped fixture was 1,635,058,906 bytes (62 files). Backup and
fresh restore duplicated it; peak root size was 4,953,799,731 bytes. Adding the
separate application bundle gives **5,262,661,532 bytes (4.901 GiB)**. These numbers
include retained validation copies, not a claim that ordinary runtime needs
three copies or that the bundled EXE alone represents the footprint.

## Financial evidence, storage recovery and offline behavior

Both imports preserved the approved normalized hashes: 7,446 financial cells,
7,135 source observations, 7,409 lineage rows and 1,225 QA events. Six original
ZIP hashes also matched. The visible Vale DRE retained 112 QA events and reported
Q3 2024 EPS **3.14 BRL/share**; source/QA availability is not a claim that every
account passes financial QA.

The storage probe used a real Windows file-handle conflict. The UI exposed the
failed scan, retained the prior inventory and re-enabled retry. A subsequent
scan succeeded and cleared the error; transient contention also preserved the
cached snapshot. This validates storage-inventory failure/recovery, **not failed
financial-import recovery**.

Run 03 closed both original and restored application trees without forced
termination. Non-child exit codes were unavailable and are not represented as
zero. With the app stopped, the complete fixture manifest matched the backup
and fresh restored directory. Restored offline UI reads succeeded; integrity,
foreign keys, four table hashes and source ZIP hashes remained valid afterward.
This is an external backup/restore procedure, not a shipped restore feature.

Run 04 completed UI, storage, backup and offline checks, then failed its final
disk-monitor cleanup and forcibly stopped one owned PID. A separate read-only
post-cleanup check found intact SQLite/source hashes and no foreign-key errors.
That follow-up does not convert run 04 into a clean-shutdown pass.

The proxy permitted only official CVM connections during explicit import and
denied network access through it afterward. Run 03 logged 14 permitted CVM
CONNECT requests; updater/GitHub and WebView service attempts at startup and
offline were denied. Offline reads therefore passed despite attempted background
connections, not with an absence-of-network claim. Configured proxy enforcement
is not packet-level isolation and does not prove that every library honors it.

Original user/research data fingerprints were unchanged in runs 01–04 and both
startup diagnostics. The packaged app's configured data paths were verified
against the isolated fixture.
The existing [financial writer source](../../src/financials/database.py#L37) sets
WAL and `synchronous=OFF`; packaged evidence reports `synchronous=2` for its
separate read connection, not the writer.
These checks do not prove power-loss or crash durability.

## Diagnostics retained and next measurement

Run 01 failed to expose CDP under the initial launcher; a controlled diagnostic
established the working hidden PowerShell launcher. Run 02 imported successfully
but failed a harness results-file read/write race; its approximately 147 MB disk
peak was invalid because one disappearing temporary file discarded an entire
sample. The harness switched to a completion sentinel, paced UI navigation and
per-entry disk sampling. The report excludes those diagnostic measurements from
acceptance. Run 04's later access-denied cleanup failure remains visible.

The next bounded optimization candidate is company filtering for standalone
refresh jobs. In the active [worker](../../src/refresh/job_worker.py#L179), an absent
or incompatible next job returns no shared source cache. The
[scraper](../../src/financials/scraper.py#L385) then retains full-market CSV frames
in its local cache; the bounded cohort path filters company rows before retention.
This is a plausible explanation for run 04's higher memory, **not controlled
attribution**: measure standalone jobs with bounded company subsets before
claiming a gain. This follows the existing engine/schema and is not implemented
by #485.

Disk retention is a separate policy-research question. Run 03 retained
**1,448,999,217 bytes of extracted annual
CSVs (88.6% of the stopped fixture)**, versus a 27,770,880-byte financial database
plus its WAL/SHM. The separate [#492 profile and paired measurements](2026-11-11-audit-copy-overhead-validation.md)
recorded 3.980 seconds of read/filter/convert, 4.311 seconds of persistence/Excel
and a nested 1.605-second database transaction for three years. These observations
do not select a new storage architecture, change retention policy or authorize
automatic source-file deletion.

This closes the bounded evidence gap for the actual host and sample, not release
acceptance for every issuer or machine. Broader samples, failed financial-import
recovery, crash durability and new architecture remain unvalidated. Existing
#489 clock-test failures and optional-sector manifest gaps from #492 are unchanged.
Raw artifacts remain under `scratch/package485-run-03`,
`scratch/package485-run-04-populated-readers` and the retained diagnostic roots.
