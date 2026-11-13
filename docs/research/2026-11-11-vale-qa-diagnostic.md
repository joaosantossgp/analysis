# Vale 2024 quarterly QA diagnostic

> Historical evidence at baseline `5971c47`, published for #482. Code references,
> measurements and implementation gaps below describe 2026-11-11, not current main.
> See the [2026-11-13 review and delivery reconciliation](2026-11-13-local-data-evidence-review.md)
> for completed follow-ups, verification and remaining limits.

Date: 2026-11-11. Tracking: #482, parent #464. Status: reproduced diagnosis;
no financial correction, identity remapping, or application change approved here.
Baseline: `5971c4743aab784f33bcd0cf33bb4fa930fe17f9`.

## Result

All five `DFC_VALIDATION_FAILED` events were reproduced from the existing
consolidated CVM 4170 source CSVs: **one DRE event and four DFC events**. The
replayed account/period/value triples exactly match all **1,195** persisted Vale
financial rows: BPA 256, BPP 495, DRE 174, DFC 270. The database remained unchanged.

The demonstrated chain is:

1. Detail account codes change or are reused across source periods. Keeping
   `CD_CONTA` as the cross-period identity creates gaps and combines different
   descriptions in some rows.
2. Quarterly conversion substitutes zero for missing predecessor cells, and the
   annual check also substitutes zero for missing quarters. All five differences
   arise from these gaps; they do not prove an error in Vale's published annual
   cash-flow total.
3. The event producer omits account identity; persistence then discards the
   supplied `year` and `diff`. The five stored events cannot independently reveal
   their offending accounts or amounts.

The alerts remain unresolved. A successful import and exact replay are evidence
of reproducibility, not financial acceptance.

## Scope and reproducibility

Only this research note and scratch files under `tmp/vale-qa-20261111/` were
created by this diagnostic. The source snapshot is
`tmp/bench-20261111-two-companies/run1/data/`, not the user's runtime directory.
No application fixes, live database changes, refresh, export, or new CVM request
were performed.

The offline script `tmp/vale-qa-20261111/diagnose.py` AST-loads the exact active
pure transformation methods from `src/financials/scraper.py` and the two ID/name
helpers from `src/financials/utils.py`. It does not import the application or
instantiate `CVMScraper`/`CVMDatabase`. It filters existing CSV rows using
`CD_CVM=4170`, `ORDEM_EXERC=ÚLTIMO`, preserves original order, and calls the active
`process_all_reports` transformation. DVA/DMPL are omitted because that method
only processes BPA/BPP/DRE/DFC (`scraper.py:587-594`).

SQLite is opened with `mode=ro&immutable=1` and `PRAGMA query_only=ON`, after
asserting that the snapshot WAL is absent or empty.
A Python audit hook blocks writes outside scratch, unexpected database access,
and network connection/name-resolution attempts. Interpreter: the existing
benchmark venv, Python 3.11.15 / pandas 3.1.1. Run:

```powershell
& 'tmp/bench-20261111-two-companies/venv/Scripts/python.exe' 'tmp/vale-qa-20261111/diagnose.py'
```

Assertions verify five replayed events, five stored events, all 1,195 value
triples, unchanged database/source SHA-256 values, and a complete-quarter control
`100, 250, 420, 600 -> 100, 150, 170, 180` with no alert. Evidence and source rows
are in `tmp/vale-qa-20261111/evidence.json`; stdout is retained separately as
`replay-output.json`. These scratch files are local evidence, not packaged assets.

Environment note: the default Python lacked pandas. During interpreter
discovery, `py list` unexpectedly reported an install-manager update to 26.4.
The replay itself used the direct venv executable with its network audit guard;
the launcher was not used again.

## Exact events and source values

The table lists values **before** standalone conversion. `Missing` means no
`ÚLTIMO` row under that code and period in the inspected CSVs; it does not mean
the company omitted the entire statement. DFC values are BRL thousands, matching
`MOEDA=REAL`, `ESCALA_MOEDA=MIL`; `normalize_units` leaves `MIL` unchanged
(`src/financials/scraper.py:345-354`). DRE `3.99.01.02` is basic ON earnings per
share: source parent `3.99` explicitly says `Lucro por Ação - (Reais / Ação)`.
Its 1.93 difference is therefore not BRL thousands, despite the file-level
`ESCALA_MOEDA=MIL` metadata. No scaling correction was applied.

| Event order / statement | Account | Q1 YTD | Q2 YTD | Q3 YTD | Annual | Replayed absolute difference |
|---|---|---:|---:|---:|---:|---:|
| 1 / DRE | `3.99.01.02` | 1.93 | Missing | 8.48 | 7.39 | 1.93 |
| 2 / DFC | `6.01.01.08` | -302,000 | Missing | -682,000 | -1,141,000 | 302,000 |
| 3 / DFC | `6.01.03.09` | -669,000 | Missing | -2,129,000 | -4,934,000 | 669,000 |
| 4 / DFC | `6.01.03.10` | -591,000 | Missing | 0 | -2,876,000 | 591,000 |
| 5 / DFC | `6.02.11` | -425,000 | -976,000 | Missing | 0 | 976,000 |

Event order matches the replay order and stored IDs 1-5. Because stored IDs 2-5
have no account fields, their association is reconstructed from the deterministic
replay; it is not information available in the database events themselves.

All rows below are consolidated, CVM 4170, `ORDEM_EXERC=ÚLTIMO`, `MOEDA=REAL`,
`ESCALA_MOEDA=MIL`. DFP annual rows have `VERSAO=3`, reference/end `2024-12-31`,
start `2024-01-01`. ITR rows have `VERSAO=1`, start `2024-01-01`, and reference/end
`2024-03-31`, `2024-06-30`, or `2024-09-30` as indicated. These are filing-version
values, not a single global version ordering across DFP and ITR.

| Account | Annual source CSV line | Q1 source CSV line | Q2 source CSV line | Q3 source CSV line |
|---|---:|---:|---:|---:|
| DRE `3.99.01.02` | DFP DRE 20789 | ITR DRE 103131 | Missing | ITR DRE 103392 |
| DFC `6.01.01.08` | DFP DFC_MI 33031 | ITR DFC_MI 91829 | Missing | ITR DFC_MI 92037 |
| DFC `6.01.03.09` | DFP DFC_MI 33067 | ITR DFC_MI 91867 | Missing | ITR DFC_MI 92077 |
| DFC `6.01.03.10` | DFP DFC_MI 33069 | ITR DFC_MI 91869 | Missing | ITR DFC_MI 92079 |
| DFC `6.02.11` | DFP DFC_MI 33093 | ITR DFC_MI 91893 | ITR DFC_MI 91991 | Missing |

CSV line numbers include the header; full filenames appear in the hash manifest
below. The diagnostic retains the complete original row fields and CSV line
numbers in its evidence JSON.

## Source account identity and period evidence

The following observations come from the source rows, not from standardized
account labels:

- **Basic ON EPS:** Q2 uses `3.99.01.01`, YTD 5.34 and standalone 3.41
  (ITR DRE lines 103252-103253), while Q1/Q3/annual use `3.99.01.02`.
  The Q3 file also explicitly reports standalone 3.14 for July-September under
  `3.99.01.02` (line 103393), alongside YTD 8.48 (line 103392).
- **Dam provision:** Q2 `Provisão para descaracterização de barragens` is
  `6.01.01.07`, -683,000 (ITR DFC_MI 91937); Q1/Q3 use `6.01.01.08`, and the
  annual description is the plural `Provisões para descaracterização de barragens`.
- **Brumadinho payments:** the description appears under `6.01.03.09` in Q1,
  `.05` in Q2 (-2,039,000; line 91963), `.08` in Q3 (-3,078,000; line 92075),
  and `.09` annually. At Q3, `.09` instead describes dam decharacterization
  payments (-2,129,000; line 92077).
- **Dam payments:** `6.01.03.10` contains dam payments in Q1 and annually,
  but `Operações descontinuadas`, value zero, at Q3. Q2 dam payments appear
  under `.06`, -1,275,000 (line 91965), and Q3 under `.09` as above.
- **Samarco versus investment funds:** `6.02.11` describes Samarco payments in
  Q1/Q2, but annual `6.02.11` is `Aplicações em fundos de investimento`, zero.
  Q3 Samarco payments appear under `.10`, -1,601,000 (line 92101); annual
  Samarco payments appear under `.13`, -4,651,000 (DFP DFC_MI 33097).

These observations establish code/description instability. They do **not**
authorize matching accounts by description or treating all similarly named
reported amounts as a comparable economic series. Filing scope, restatement,
and account mapping still need explicit validation.

## Active calculation and logging path

1. `process_data` filters company/`ÚLTIMO`, creates IDs, normalizes units and
   stamps source type (`src/financials/scraper.py:395-430`). The CSV projection
   omits `VERSAO`, `MOEDA`, and source-file lineage (`:86-89`, `:368-377`).
   The ID helper chooses `CD_CONTA` whenever present
   (`src/financials/utils.py:165-186`).
2. Period labeling maps both January-September YTD and July-September reported
   standalone DRE rows to `3Q24` (`scraper.py:456-468`). The pivot uses
   `aggfunc='first'` (`:473-474`). Thus the explicit 3.14 source observation is
   discarded in favor of 8.48 before conversion in this snapshot.
3. Coalescing groups by code-level `LINE_ID_BASE`; its conflict test only checks
   unequal populated values **within the same period column** (`:523-542`).
   Different descriptions across disjoint periods merge without a conflict.
   It keeps one `DS_CONTA`; for example, persisted annual Brumadinho payments
   under `6.01.03.09` are labeled as dam payments. All 20 persisted values across
   the five offending accounts have `QA_CONFLICT=0`.
4. Both DRE and DFC use the same conversion (`:485-487`). Presence flags test
   whether the dataframe has quarter columns, not whether the particular
   account has a value (`:553-562`). Missing predecessor cells become zero.
5. For the first four events, let Q1 be `a`, missing Q2 be `NaN`, Q3 YTD be `c`,
   and annual be `A`. The output is `a, NaN, c, A-c`; the check sums missing
   quarters as zero and obtains `A+a`. The observed difference is exactly
   `abs(a)`. For `6.02.11`, the output is `-425000, -551000, NaN, 0`; the
   computed Q4 zero comes from annual zero minus missing Q3 filled with zero,
   and the difference is 976,000 (`:559-575`).
6. `_validate_quarterly_sum` checks every nonmissing annual value, even when
   quarters are missing. It emits only `type`, `statement`, `year`, `diff`
   (`:570-576`). The constant is 0.01 (`:38-39`); its comment says BRL millions,
   although amount normalization targets thousands and the DRE example is
   per-share. This unit-label inconsistency is separate from the reproduced
   missingness cause.
7. `process_all_reports` returns these events (`:587-594`), and `generate_excel`
   passes them to `insert_company_data` (`:627-636`). Database field mapping
   accepts `period` but not `year`, and has no mapping/storage column for `diff`
   (`src/financials/database.py:62-73`, `:479-503`). Therefore the persisted five
   rows retain only company, code, event type, and statement. `PERIOD`, account
   identifiers, description and action are all null.

The stored missing cells are absent financial rows because persistence drops
null values (`database.py:531-537`). The visible zero at `6.02.11` / `4Q24` is
different: it is a calculated numeric zero and is persisted. No evidence here
supports treating that zero as a reported fourth-quarter observation.

## Follow-up acceptance tests and limits

Recommended tests for a separately scoped financial-correctness issue:

1. Preserve this five-event snapshot as a regression fixture with source file,
   version, code, description, duration and unit. Retain a baseline replay test;
   change expected outputs only with reviewed financial semantics.
2. Test missing predecessor **cells** when the quarter column exists for other
   accounts, and separately test absent quarter columns. Missing required inputs
   must remain missing and produce a traceable incomplete status; a zero must
   require evidence. Keep the existing complete-quarter arithmetic control.
3. Test code reuse across distinct descriptions/periods and same-description
   movement across codes. Preserve source identities and surface unresolved
   comparability; do not silently merge by name or invent an economic mapping.
4. Test simultaneous YTD and reported standalone DRE rows, preserving both
   durations and explicit selection lineage. Cover per-share rows separately;
   **Needs validation:** the correct periodization and acceptance rule for EPS,
   whose source explicitly uses reais per share.
5. Round-trip QA company, statement, account/source identity, year/period,
   expected/actual/difference, unit, missing inputs and action through the chosen
   persistence contract. The current schema cannot retain that complete payload.
6. Check presentation/read consumers so a successful import or
   `QA_CONFLICT=false` cannot imply that these unresolved quarterly series passed
   financial QA. **Needs validation:** actual desktop display and export behavior;
   neither was exercised by this diagnostic.

Existing tests cover complete arithmetic (`tests/test_scraper.py:337-359`), but
the missing-Q2 test explicitly expects an empty error list (`:366-371`). The
coalescing tests cover within-period conflicts (`:296-305`), not the demonstrated
cross-period description reuse.

No application test suite or packaged runtime was run: this task changed no
application code and used an assertion-based isolated source replay. No new
remote filing was fetched; whether later CVM snapshots change these rows is
**Needs validation**. The financial accuracy of other Vale accounts, other years,
other companies, and any automatic remapping remains outside this diagnosis.

## Source fingerprint manifest

All paths below are relative to
`tmp/bench-20261111-two-companies/run1/data/`. The diagnostic DB SHA-256 was equal
before and after the read-only replay. The evidence JSON also fingerprints the
other six source CSVs read for complete BPA/BPP/DRE/DFC value parity.

| File | SHA-256 |
|---|---|
| `db/cvm_financials.db` | `b04de59499eeed6061b8df759b0d905b8470b928df4f9b1ba99f7cefc9da7540` |
| `input/processed/dfp_cia_aberta_DRE_con_2024.csv` | `bc0e2004b5901dd5c28ca66c52f4f7bb2d4c734f3c9d0fcd7c779ff5959c1a28` |
| `input/processed/itr_cia_aberta_DRE_con_2024.csv` | `5bc2b7718b99d91abfb7f10a0c5ec80dfd39415c037b8f777c11da3e79cdb2e7` |
| `input/processed/dfp_cia_aberta_DFC_MI_con_2024.csv` | `ad2eadea586d55e8693b1df0d6a12e81c77b7ebf8466857ef7f1ff353add8a5a` |
| `input/processed/itr_cia_aberta_DFC_MI_con_2024.csv` | `5639ad30db5fe5fbfd3025e4bc429c7ee37fb9974d45dd1b2887cf36db82539a` |
