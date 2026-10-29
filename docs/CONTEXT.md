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
pywebview desktop app (static Vite UI + Python bridge) and a read-only FastAPI
adapter for hosted/dev/local HTTP access. The goal is reliable, readable, and
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
- DFC is not cumulative: YTD -> standalone conversion happens internally.
  - `Q1 = YTD_1Q`
  - `Q2 = YTD_2Q - YTD_1Q`
  - `Q3 = YTD_3Q - YTD_2Q`
  - `Q4 = ANNUAL - YTD_3Q`
  - `YYYY = ANNUAL`
- Missing quarter: leave `NaN` and record it in QA; never invent values.
- `4Q` depends on the annual `YYYY` being present; an isolated quarter does not
  produce a reliable `4Q`.

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
  QA events to `qa_logs`
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

---

## 5. Stack and code conventions

**Stack:**

- Python: 3.11+, pandas, polars, sqlalchemy, requests, yfinance, pywebview,
  PyInstaller
- Desktop UI: Vite, React, TypeScript, Tailwind v4
- Hosted/dev API: FastAPI (read-only)
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
