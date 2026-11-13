# Local-data evidence publication review

> Owner decision, 2026-11-13: #464 and #466 are closed as not planned for now.
> This research and its evidence are preserved as historical reference. Pending
> multi-window plans below are superseded by the
> [incremental delivery direction](../PRODUCT_DIRECTION.md#delivery-direction-2026-11-13).
> This decision does not claim that the proposed work was implemented or validated.

Date: 2026-11-13. Delivery: #482; references #464 and #466.
Application baseline reviewed for current status: `4d045d28b404b5e0746efa88aea657e063cc2105`.
Historical experiment baseline: `5971c4743aab784f33bcd0cf33bb4fa930fe17f9`.

## Published evidence and scope

- [Initial import benchmark](2026-11-11-two-company-import-benchmark.md) and its
  [structured evidence](2026-11-11-two-company-import-benchmark.evidence.json).
- [Static import diagnostic](2026-11-11-import-code-diagnostic.md).
- [Repeated batching and concurrent-read cycle](2026-11-11-local-data-cycle.md)
  and its [structured evidence](2026-11-11-local-data-cycle.evidence.json).
- [Vale QA diagnosis](2026-11-11-vale-qa-diagnostic.md).

These records describe two companies and bounded 2024 / 2022–2024 samples.
They explain the findings behind later work; they do not measure current main.
The separate-call versus batch medians remain 10.699 s versus 6.901 s (35.5%
lower). Backend concurrency is not desktop responsiveness or snapshot consistency.

## Publication verification

The [review evidence](2026-11-13-local-data-evidence-review.evidence.json) records
checks and SHA-256 fingerprints of the six original report/evidence files.
Read-only checks against retained local artifacts established:

- All six annual ZIP hashes and four cycle harness hashes match the records.
- All seven cycle run summaries match raw summaries. Financial and QA normalized
  hashes were recomputed from each database, excluding row IDs exactly as in the
  original summarizer; all databases passed integrity checks. Reads used SQLite
  `mode=ro&immutable=1` after confirming WAL files were empty. All six paired runs
  have identical financial and QA hashes. Company-operation durations, CSV call
  counts and cache hits match retained event logs; medians were recomputed.
- Nine read distributions match raw `reads.json`, including 450 nonempty,
  error-free calls during import. The 80 offline calls match the retained
  validation output; this review did not perform a new offline run.
- Seven historical before/after protected-file inventories match. This verifies
  the recorded preservation evidence, not the present contents of user data.
- Ten Vale source CSV hashes and the original diagnostic database hash match.
  The five alert records match retained replay output. The source replay itself
  was not rerun; the original 1,195-value parity claim remains historical replay
  evidence. The initial benchmark summary and its two ZIP hashes also match.

The original research checkout, user data and raw artifacts were left intact.
No application imports, new ingestion, financial recalculation, application test
suite or packaged run were performed for this documentation-only delivery.
Raw CSVs, databases, downloads, environments and local harnesses are not committed.
Absolute source-checkout prefixes in published JSON were removed; remaining
paths are relative to that checkout. Measurements, hashes and failure records
are unchanged. Markdown adds historical banners and replaces obsolete guidance.
Original file hashes allow the retained originals to be distinguished from these
publication edits; this is not a self-contained reproduction package.

## Reconciliation with delivered work

| Finding | Delivered evidence | Boundary |
|---|---|---|
| Missing periods, ambiguous identities and lost QA context | #483 / PR #490: [financial QA](2026-11-11-financial-qa-validation.md) | Conservative source/lineage contract; ambiguous or unavailable values remain visible. No bulk user-data repair. |
| Annual-source reuse across compatible jobs | #484 / PR #491: [bounded refresh](2026-11-11-bounded-refresh-validation.md) | 128 MiB retained subset, 60-second admission window; per-job semantics preserved. |
| Packaged lifecycle | #485 / PR #494: [packaged validation](2026-11-12-packaged-local-data-validation.md) | Run 03 supplies accepted bounded evidence. Run 04 failed monitor cleanup and has sampling gaps; it is not a clean pass. |
| Audit-evidence copy overhead | #492: [copy overhead validation](2026-11-11-audit-copy-overhead-validation.md) | Separate baseline; no RAM/disk improvement claim. |
| Standalone-job memory | #495: [standalone validation](2026-11-12-standalone-source-memory-validation.md) | Three-year RSS fell from 2.672 to 1.425 GiB; no three-year throughput/disk gain. |

All five issues are closed and their deliveries are in main. Their percentages
must not be combined: workloads, runtimes and baselines differ. The owner made
8 GB RAM / 30 GB free disk an efficiency guide, not a mandatory hardware/VM gate.
The old financial approval queue is completed, not a request to repeat those tasks.
The separate #486 company-to-Excel cycle is also closed following owner acceptance
and explicit waivers of packaged disconnected-network and final fresh-sandbox
update checks. Waived checks are not passes and do not extend #485's evidence.

## Remaining limits and next boundary

- Original 2022/2023 Vale alerts were not individually diagnosed. #483 does not
  establish financial acceptance of every account or year, or resolve source
  identity ambiguities by name.
- Larger universes, other source classes, cross-call snapshot consistency,
  crash/power-loss durability and multi-window behavior remain unproven by this
  pilot. The strict managed-ingestion check failed for absent out-of-sample
  CCEE/MMGD/fuel manifests; its recorded failure is preserved.
- Current performance must be established from a new, explicitly scoped workload
  if needed. No engine rewrite, storage migration or multi-window implementation
  follows from these historical measurements.

These limits do not require new experiments to close #482's evidence delivery.
At publication, #464 and #466 remained open for product scoping. The subsequent
owner decision above supersedes that next step: both are now not planned, while
this evidence remains available for independently scoped app improvements.
