# Excel Exports

## Scope

This document covers the financial-statement Excel exports produced by
`src/financials/excel_exporter.py` and related export entry points exposed
through the desktop bridge. Other exports exist for market history, coverage,
country KPIs, and distribution modules; they should follow the same modeling
standards where feasible, but their exact workbook structures differ.

## Active Financial Workbook

Verified implementation:

- `desktop/bridge_api/companies.py::export_company_excel` writes workbooks into
  the resolved output directory and avoids overwriting existing files.
- `src/financials/read_service.py::build_company_excel_export` prepares company
  data, period scope, mapping preset, and payload.
- `src/financials/excel_exporter.py` creates the workbook with xlsxwriter and
  re-opens full exports with openpyxl to reject Excel error strings and merged
  cells.
- Tests in `tests/test_excel_exporter.py`, `tests/test_excel_mapping.py`, and
  `tests/test_period_scope.py` cover sheet order, hidden raw sheets, no merged
  cells, formulas, period scope, and metadata.

Visible sheets in the full company workbook:

- `Model`: analyst-facing model with statement sections, KPIs, checks, and
  source/data-quality blocks.
- `README`: workbook map, conventions, and period-policy notes.

Hidden/audit sheets:

- `raw_DRE`, `raw_BPA`, `raw_BPP`, `raw_DFC`, and optional `raw_DMPL`;
- `raw_KPIs`;
- `metadata`;
- `mapping_audit`.

Single-statement scoped exports contain the relevant raw sheet plus metadata.

## Required Standards

Financial workbooks must preserve these standards:

- no merged cells;
- use Center Across Selection if a visual header span is needed;
- clear separation between inputs/source-linked values, calculations, and
  outputs;
- formulas trace back to raw sheets or explicitly calculated rows;
- standardized dates, units, currencies, and scale;
- historical and projected periods separated; current financial exports do not
  implement forecast periods unless explicitly added and documented;
- clear hierarchy and subtotals;
- balance sheet, cash flow, net income, debt, and source/data-quality checks;
- negatives shown in parentheses;
- zeros shown as `-`;
- generated files must open without Excel repair.

The current financial exporter implements no-merge validation, linked/calculated
formatting conventions, hidden raw sheets, README/metadata, and check blocks.
Manual Excel-open validation is still required before a release.

## Period And Data Semantics

Financial statement exports must distinguish:

- annual DFP periods from quarterly ITR periods;
- consolidated vs individual report type;
- reported source rows from standardized model labels;
- unavailable source lines from actual zero values;
- CVM-reported values from CVMAnalytics-calculated KPIs/checks;
- official CVM statement values from external market or news data.

The current model period scope supports selected export scopes such as recent
history and full history through the bridge/API layer. The workbook README and
metadata include the selected scope label.

## Validation

Use the narrowest relevant validation:

```powershell
pytest tests/test_excel_exporter.py -q
pytest tests/test_excel_mapping.py -q
pytest tests/test_period_scope.py -q
```

For release candidates, also validate:

- export from the packaged app;
- open the generated `.xlsx` in Excel without repair prompts;
- inspect formulas and hidden raw sheets;
- verify no merged cells;
- verify negative/zero formats;
- verify data-quality/check rows for the selected company.

## Known Gaps

- Source inspection and unit tests do not prove Microsoft Excel will open every
  generated workbook on every user machine.
- Non-financial exports have their own workbook structures and should be
  audited separately before claiming full compliance with the financial model
  standard.
- Forecast/projected-period modeling is not documented as implemented in the
  active financial exporter.

## Coverage Universe Excel Export

The coverage universe export produces a comprehensive, audit-grade workbook with 7 sheets:

- **Summary**: High-level universe parameters, company counts, and overall capacity metrics.
- **Priorities**: The priority list of all companies in the universe, including their score, owner, score status, and any missing data flags. Blocked scores are exported as the string `"Blocked"` (never `0.0`), and partial scores as `"Partial"`. Missing numbers are exported as `"-"`.
- **Priority Factors**: Granular breakdown mapping each company against every priority scoring factor (raw value, weight, contribution, and missing flags).
- **Work Queue**: Active data-quality, news, checklist, and owner assignment tasks.
- **Capacity**: Tier load breakdown, hours by analyst owner, and scenario assumptions.
- **Decision History**: Audit trail of analyst assignments, score overrides, and manager decisions.
- **Methodology**: Documentation of prioritization scoring rules, weights, capacity multipliers, and caveats.

All sheets are generated with autofilters, frozen top rows, and no merged cells, ensuring they are fully database-compatible and readable by external analysis scripts.

