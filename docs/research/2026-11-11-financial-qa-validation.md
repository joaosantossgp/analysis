# Conservative financial QA validation (#483)

Scope: consolidated Petrobras (CVM 9512) and Vale (CVM 4170), 2024 DFP/ITR,
using copies of the official annual ZIPs. The source fixture records the exact
78 relevant Vale rows, CSV line references and source hashes in
`tests/fixtures/vale_2024_financial_qa.json`. This validates the approved
conservative financial contract; it does not authorize an existing-data repair.

## Results

- A fresh isolated import completed for both companies: 1,240 Petrobras and
  1,242 Vale analytical cells, 2,390 retained source observations, and 2,482
  cell-lineage records. Null/unavailable cells remain stored with conflict
  status and are excluded from ordinary analytical reads.
- A repeated batch import produced identical normalized hashes for financial
  cells, source observations, lineage and QA. Volatile log IDs/timestamps were
  excluded from comparison. No duplicate source observations were introduced.
  A second fresh final-code replay produced the same hashes; all 2,390 new
  source import timestamps explicitly used UTC.
- Vale account `6.02.11` has no invented Q4 zero. Reported Q3 EPS for
  `3.99.01.02` remains 3.14 BRL/share. Code reuse across descriptions stays
  ambiguous; source observations remain auditable without automatic mapping.
- There are 309 explicit QA events (42 Petrobras, 267 Vale), including newly
  visible missing/ambiguous/non-additive periods. This is broader detection than
  the original five reconciliation alerts, not a claim that the source filings
  changed or became worse. Four Vale DRE reconciliation differences remain
  visible; reported observations are not silently rewritten to force a match.
- Both real read-service Excel exports opened through openpyxl with visible
  QA and hidden source/lineage audit sheets. Regression tests cover the direct
  ingestion workbook, per-share decimal precision and missing D&A propagation.

## Validation boundaries

The Python/API suite ran in a disposable profile with an audit hook rejecting
original-data writes, SQLite connections to the original data roots and external
network calls. Final run: **979 passed, 4 failed, 1 skipped** in 54.08 seconds.
The remaining failures are in unchanged entity relationship/resolution timing tests on Windows.
An independent archive of baseline `58486271904e3a07d29a4a33152ca9cf9c316b45`
reproduced four failures in those modules (32 passed), and a separate targeted
probe reproduced the fifth failing test on that same baseline. These clock-sensitive
failures remain a validation limitation; this change does not fix the registry.
They are tracked separately in [#489](https://github.com/joaosantossgp/analysis/issues/489).
Focused financial/read/export/portability/API checks passed (277), followed by
131 passing financial/API checks after final review fixes. The expanded legacy
test and global refresh-invalidation test failed before their respective fixes
and passed afterward. The independent reviewer closed all five findings and
reported no remaining actionable findings.

An earlier full run also encountered a transient Windows access-denied error
replacing an unrelated energy manifest. That test passed in targeted current and
baseline probes and in the final full run. No energy ingestion code was changed.

Frontend after review fixes: **119 tests passed**, TypeScript typecheck and production build passed.
The real desktop entry point, pywebview bridge and built Vite app were exercised
against the sandbox database. Vale DRE displayed 40 QA events and EPS 3.14.
Widths 1,366 and 900 pixels had no document horizontal overflow or JavaScript
page errors. An absent company showed the real empty state; an explicitly
injected bridge delay/error verified loading and failure rendering, then was
removed. This was a source desktop run, not packaged-release acceptance.

A separate constructed fixture retained only Vale's reported Q2 DFC account
`6.01.03.05`, intentionally omitting its required predecessor. Through the real
desktop bridge, annual years stayed empty, statement evidence years returned
2024, and the statement page displayed `MISSING_PREDECESSOR` despite having no
usable analytical rows. At both laptop widths the warning remained visible with
no JavaScript errors. The actual bridge export produced a 10,406-byte audit
workbook with an explicit partial-evidence README, QA/source/lineage sheets and
no analytical Model. The fixture and screenshots remain under
`scratch/bench483/itr-only/`; this is a regression fixture, not a complete filing.

The final single-worker resource sample recorded 12.98 seconds for the worker
process, peak sampled resident memory 1.272 GiB, private memory 2.641 GiB and
data/temp disk 0.511 GiB. This is one diagnostic observation, not a repeated
performance comparison. The host has 32 GiB RAM; Windows 11
with 8 GiB RAM and 30 GB available remains **Needs validation** under #485.

The storage-budget check passed (6,098,944 bytes across the final sandbox's main
databases). Strict managed-ingestion validation reported only absent
CCEE, MMGD and fuel-distribution manifests; those datasets are outside this
financial sandbox. No manifests were fabricated to make that gate pass.

Original user and research data fingerprints were unchanged. Raw evidence stays
local under the issue worktree's ignored `scratch/bench483/run2/` directory
(`summary.json`, `audit.json` and guardrail output). The main desktop UI evidence
is under `run1/`; the partial-only UI evidence is under `itr-only/`.
No original database was repaired or reimported. Live PostgreSQL compatibility,
packaged recovery and target-hardware acceptance remain **Needs validation**.
