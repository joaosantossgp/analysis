# Interview scope investigation — 2026-08-02

## Conclusion

No code fix is warranted solely because the CVM financial marts are empty. The
active shared Documents database is correctly on the canonical raw-query path,
so the company directory's local-data flags and all five downloaded company
detail/statement/KPI reads remain functional. Treat the limited local coverage
and directory-universe dependency as demo guidance, not as a claim that the
whole universe has local financial statements.

## Verified live-data state (read-only)

- Dev defaults to the shared release data root; this is documented at
  `docs/dev-runtime-and-data-paths.md:42-81`.
- `%USERPROFILE%\\Documents\\CVMAnalytics\\db\\cvm_financials.db` has 5
  `companies`, 38,046 `financial_reports`, and five distinct `CD_CVM` values:
  Petrobras (9512), Aegea (23396), Alares (25194), Aeris (25283), and CVM_25658
  / AGXY3. Each has standard-statement periods; Petrobras and Aegea include
  1Q26.
- `company_financial_directory_mart`, `company_financial_period_mart`, and
  `company_kpi_account_mart` each contain 0 rows. `financial_mart_builds` also
  contains 0 rows: there is no success metadata that could make an empty mart
  active.
- The local market-cap snapshot has 211 ranked/mapped rows, dated 2026-08-02;
  all identify `yahoo_finance` / `unofficial_free`. This is market data, not
  local CVM financial coverage.

## Why empty marts do not break the active demo

- Mart selection is gated by a successful `financial_mart_builds` record in
  `src/financials/query_layer.py:224-247`. With no records, every mart check is
  false.
- Directory metadata, company years/readiness, latest-period data, KPIs, and
  statements have canonical `financial_reports` fallbacks (`query_layer.py:271,
  844, 1066, 1252, 1287, 1463, 1590`). Statements intentionally remain raw-row
  reads for auditability.
- The project documentation explicitly says fresh/unbuilt profiles retain the
  canonical raw-query path (`docs/dev-runtime-and-data-paths.md:317-347`).
- Focused regression tests passed: `pytest -q tests/test_financial_marts.py
  tests/test_company_financial_readiness.py tests/test_company_market_cap_sort.py`
  → **20 passed**. The parity test is at `tests/test_financial_marts.py:182`.

## Interview/demo guidance

1. Open a company that is already downloaded (prefer Petrobras) for the company
   overview, statements, and KPI/history path. Do not present catalog-only
   names as locally downloaded financial coverage.
2. Describe the directory accurately: 211 companies are locally ranked by the
   market-cap snapshot; the broader ~663 company directory is catalog metadata
   with only five local financial-report datasets in this profile.
3. Keep network available for the broad-directory demonstration. Because the
   local database has fewer than the 100-company catalog threshold
   (`src/financials/read_service.py:54`), the market-cap directory merges the
   CVM catalog with local rows (`read_service_query.py:713-865`,
   `read_service_coverage.py:2245-2365`). If that catalog request is unavailable,
   it degrades to the five local rows. The downloaded company financials remain
   readable offline.
4. Preflight once in the actual desktop runtime: Settings → Diagnostics must
   show the Documents root; search/open Petrobras; load its statements and
   indicators; then show the directory snapshot date/source label. Avoid running
   dev and packaged desktop against the shared root simultaneously.

## Potential follow-up, not a pre-interview mart fix

If a reliable full-directory offline experience is a product requirement,
persist/cache the CVM catalog and show its freshness/source state. Current
catalog loading is network-backed (`src/companies/catalog.py:52-157`), whereas
the market-cap snapshot is local. This is independent of financial mart
maintenance. Rebuilding marts is optional performance maintenance; it would
write to the live Documents DB and is unnecessary for the interview.
