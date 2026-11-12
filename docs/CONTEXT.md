# CONTEXT.md - Financial Pipeline Domain Rules

> Technical reference for business rules and the financial pipeline in `src/`
> and `apps/api`. For runtime architecture, sources, Excel, development, and
> release, see `docs/architecture.md`, `docs/data-sources.md`,
> `docs/excel-exports.md`, `docs/development.md`, and `docs/build-release.md`.
> For folder layout, see `docs/reference/repository-map.md`. For agent operating
> rules, see `AGENTS.md`.

---

## 1. What the pipeline does

Extracts historical financial statements of CVM-listed companies, stores them
in local SQLite (optional PostgreSQL), and exposes the data through the
pywebview desktop app (static Vite UI + Python bridge) and a FastAPI adapter for hosted/dev/local HTTP access. The adapter exposes
queries, exports and explicit refresh commands; it is not read-only. The goal is reliable, readable, and
verifiable output that never mixes periods, versions, or conflicting lines.

**End goal:** a single pipeline that takes a company plus start/end years,
persists statements and metadata, and serves queries and exports through the
desktop app, the HTTP API, and auditable Excel.

**Data source:** public CVM data - `https://dados.cvm.gov.br` (DFP annual + ITR
quarterly).

---

## 2. Completed technical scope

- **Priority 1:** accounting integrity and correct periodization - balance
  Total Assets/Total Liabilities, never stamp annual values onto quarters,
  handle the year window.
- **Priority 2:** stable `LINE_ID_BASE` key, wide base, `DS_CONTA_norm`,
  `ORDEM_EXERC='ULTIMO'` filter, conflict QA, clean Excel export.
- **Priority 3:** account standardization through a dictionary
  (`STANDARD_NAME`) and a `PADRONIZACAO` Excel sheet.
- **Priorities 4-8:** mass expansion (449 companies), vectorization + WAL +
  parallelism, FastAPI adapter, desktop migration to pywebview with packaged
  static Vite, automated tests. The old Next.js UI was removed from the active
  tree.

---

## 3. Essential business rules

- The financial pipeline preserves the **BPA**, **BPP**, **DRE**, and **DFC**
  statements. The current analytical Excel exposes a `Model` sheet and keeps
  the complete statements in hidden `raw_*` sheets; see
  `docs/excel-exports.md`.
- Lines are identified by a stable `LINE_ID_BASE`: always `CD_CONTA` when
  available, otherwise a deterministic synthetic key.
- `DS_CONTA_norm` is required on every sheet: lowercase, accents removed,
  trimmed, whitespace collapsed, NBSP removed.
- Output must not use artificial suffixes such as `#1`, `#2`.

### DRE and DFC rules

- DRE and DFC keep quarterly and annual columns (`1Q`, `2Q`, `3Q`, `4Q`,
  `YYYY`).
- Preserve published observations before selecting a period: company, account
  code and description, filing version, report type, start/end dates, source
  file, original value text, currency and scale. YTD and reported standalone
  observations with the same end date are separate inputs.
- Prefer an unambiguous reported standalone duration. Otherwise, additive
  monetary flows use compatible cumulative observations:
  - `Q1 = YTD_1Q`
  - `Q2 = YTD_2Q - YTD_1Q`
  - `Q3 = YTD_3Q - YTD_2Q`
  - `Q4 = ANNUAL - YTD_3Q`
  - `YYYY = ANNUAL`
- A missing predecessor cell or column leaves the derived quarter unavailable,
  with account/period/input QA. Do not replace it with zero or subtract Q2 to
  approximate Q4. Derived Q4 requires annual and Q3 YTD; an explicit reported
  October-December observation can be selected directly.
- DRE `3.99` and descendants are per-share amounts in BRL/share for REAL
  filings, regardless of the file-level monetary scale. Select only published
  applicable durations; never subtract or reconcile their annual/quarterly
  values as additive flows.
- Reused codes with different normalized descriptions, report perimeters or
  units in the imported history are ambiguous. Keep the source observations,
  exclude their analytical series, and record QA. Different codes are never
  matched by similar descriptions. Distinct versions for the same duration
  are retained and cannot be selected arbitrarily.
- Annual reconciliation runs only for complete additive inputs. An import
  succeeding or a package being present is not financial QA acceptance.

### QA and acceptance criteria

Required validations for the financial layer and/or Excel exports:

- `LINE_ID_BASE` unique per sheet
- `DS_CONTA_norm` has no nulls
- no `"#"` in final IDs
- BPA and BPP balance (Total Assets = Total Liabilities)
- DFC: `Q1 + Q2 + Q3 + Q4 = YYYY` when all periods exist

QA logs, sheets, and metadata must preserve traceability. The current
analytical workbook uses `README`, `metadata`, `mapping_audit`, `raw_*`, and
check blocks; do not document legacy sheets as required without validating the
implementation.

---

## 4. Pipeline and data flow

### Full cycle (download -> database -> query)

**1. Trigger**

- CLI: `python main.py --companies ... --start_year ... --end_year ...`
- Desktop app (`desktop/app.py`): calls the scraper through the bridge for the
  companies/range selected in the UI
- Batch scripts: `scripts/data/batch_completo.py`,
  `scripts/data/atualizar_todos.py`

**2. Download and extraction**

- `src/financials/scraper.py` downloads CVM ZIPs to `data/input/raw`
- CSVs (BPA/BPP/DRE/DFC/DMPL) are extracted to `data/input/processed`

**3. Transform and normalization**

- filters by `CD_CVM`, normalizes financial units
- derives period labels, builds per-statement tables
- generates `LINE_ID_BASE`, applies standardization and QA logs

**4. Persistence**

- `src/financials/database.py` writes long-form rows to `financial_reports` and
  QA events to `qa_logs`. Source observations are retained by content identity
  in `financial_source_observations`; `financial_value_lineage` links each
  analytical cell to its unit, status, formula and source observation IDs.
- Statement rows, lineage and QA are replaced transactionally only for the
  imported statement-years. Other years and immutable source observations
  survive retries and partial-history imports. QA retains complete input,
  account, year, period, unit, missing-input and reconciliation context.
- company metadata is updated in `companies`
- refresh status is persisted in `company_refresh_status`
- Excel export is available in `output/reports/`

**5. Query**

- `src/financials/read_service.py` is the source of truth for the read layer
- `apps/api` (FastAPI) is a thin HTTP adapter over `read_service`
- The desktop app uses the Vite SPA in `apps/desktop-web` and calls the Python
  bridge directly through `desktop/bridge.py`, avoiding an HTTP hop at local
  runtime

### Coverage model

- **Universe:** active companies in the CVM master list
- **Covered cell:** company-year with the complete package
  (`BPA + BPP + DRE + DFC`)
- **Closed year:** counts as covered only when the complete package exists for
  the annual `YYYY` period; `1Q/2Q/3Q` without an annual period do not count as
  annual coverage
- **Hybrid signal:** `financial_reports` + raw/processed files + local cache

### Freshness by financial period

- A company's "updated through" indicator uses the most recent complete period
  per `CD_CVM`, not a global date or only the latest annual year.
- A period is complete only when the core package `BPA + BPP + DRE + DFC`
  exists for the same `PERIOD_LABEL` with `QA_CONFLICT = false`.
- Annual periods display as `FY2025`; quarterly periods keep the normalized
  format `1Q26`, `2Q26`, etc.
- Quarterly years newer than the latest complete DFP enter the Excel scope only
  when that year has at least one complete quarter.
- Quarterly values persisted in `financial_reports` have already gone through
  scraper normalization; DFC/DRE YTD values are converted to standalone before
  reads, UI, Model Mapping, and Excel consume them.
- Unavailable cells are stored as null with `QA_CONFLICT=true`, so they cannot
  satisfy complete-period coverage or enter default analytical queries. A
  reported numeric zero remains readable. Missing D&A propagates to EBITDA
  ratios; partial D&A component sums are unavailable.
- Statement matrix responses expose `qa_events` and `quality_evidence`
  (`available`, `partial`, `legacy_unknown`). Available evidence does not mean
  QA passed. Existing databases remain readable without a hidden reimport or
  read-time schema repair; an explicit company/year refresh captures the new
  source evidence. Legacy QA with an unknown year remains visible.
- Statement-year discovery uses local financial rows, source observations and
  dated QA, including ITR-only or entirely excluded periods. It is separate
  from annual KPI years and complete-period readiness. Desktop
  `get_company_statement_years` and HTTP `/companies/{cd_cvm}/statement-years`
  share the same read service; the statement screen uses this evidence list.
- Export scope can include partial evidence years within the selected window
  (or every evidence year for full history), explicitly labeled as partial.
  Analytical statements, KPIs and `Model` keep the existing complete-period
  scope; QA/source/lineage audit includes the additional evidence years. If no
  complete scope exists, or its required model inputs are unresolved, a partial
  export is an evidence-only workbook with a visible explanation and no `Model`.
  Invalid mappings still block export. Neither path changes coverage/readiness.

---

## 5. Stack and code conventions

**Stack:**

- Python: 3.11+, pandas, polars, sqlalchemy, requests, yfinance, pywebview,
  PyInstaller
- Desktop UI: Vite, React, TypeScript, Tailwind v4
- Hosted/dev API: FastAPI (queries, exports and explicit refresh commands)
- DB: local SQLite + optional PostgreSQL through `DATABASE_URL`

**Conventions:**

- `snake_case` for variables and file names
- object-oriented core engine (`CVMScraper`)
- `USER CONFIGURATION` block at the top of each executable script
- `LINE_ID_BASE` as the canonical identifier

Setup and run commands live in `docs/development.md`.

---

## 6. Troubleshooting

| Symptom | Diagnosis |
|---------|-----------|
| No data in the app | Check that `financial_reports` has rows and that the selected company/years were processed |
| Company missing | Check that the `CD_CVM` was processed successfully |
| SQL error in the updater | Inspect `output/logs/refresh_runs.jsonl` and confirm SQLite is not locked |
| List repeats the same companies | Check that `last_success_at` is being updated in `company_refresh_status` |
| ETA does not appear | Expected while there are few throughput samples |
| Coverage numbers are stale | Force a ranking refresh and check the local cache |
| Market widgets are empty | Check yfinance availability and the ticker mapping |
| Cockpit returns empty | Check `apps/api/app/routes/` and the actual coverage for the selected company/years |

---

## 7. Non-obvious technical decisions

Implementation decisions that are not obvious from reading the code and have
caused bugs before:

| Decision | Reason |
|---------|-------|
| `int(year)` before passing a SQLite param | numpy int64 fails silently |
| yfinance `dividendYield` is already a percentage | do not multiply by 100 |
| SQLAlchemy IN clause: `bindparam("x", expanding=True)` | lists as SQL params |
| `_upsert_company_metadata`: INSERT OR IGNORE + UPDATE | preserves CNPJ/ticker filled by `setup_companies_table` |
| `fillna("")` before `pivot_table` | avoids silent loss of rows with null `STANDARD_NAME` |
| `apps/api` consumes `src/financials/read_service.py` | avoids reimplementing SQL and KPI logic in the HTTP adapter |
