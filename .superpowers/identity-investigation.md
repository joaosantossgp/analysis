# CVM 25658 identity investigation

## Conclusion

**A targeted code fix is necessary before the interview.** This is not merely a historical log label: the live Documents database returns `CVM_25658` as the company name through both active company-list and company-detail paths. The local catalog already has the correct identity for the same CVM code, so a bounded read-time identity normalization can remove the interview-visible leak without changing financial rows.

## Reproduced against the live runtime data

- Database: `%USERPROFILE%\Documents\CVMAnalytics\db\cvm_financials.db`.
- `companies` row for `cd_cvm=25658`: `company_name='CVM_25658'`, ticker `AGXY3`, CNPJ `21240146000184`; it is active and has local financial reports.
- `CVMReadService.list_companies(search='AGXY3')` returns `company_name='CVM_25658'`, while local market-cap enrichment correctly adds snapshot data for `AGXY3`.
- `CVMReadService.get_company_info(25658)` returns `company_name='CVM_25658'`.
- `company_catalog.lookup_company(25658)` returns `AGROGALAXY PARTICIPAÇÕES S.A. - EM RECUPERAÇÃO JUDICIAL`, ticker `AGXY3`, and matching CNPJ. The market-cap snapshot likewise maps `cd_cvm=25658` to AgroGalaxy.

## Active data flow and leak points

1. The Vite directory calls `fetchCompanies` in `apps/desktop-web/src/lib/api/companies.ts:38`, which calls bridge `get_companies`.
2. `desktop/bridge_api/companies.py:24` invokes `CVMReadService.list_companies`.
3. `src/financials/read_service_query.py:867` prefers `_list_companies_with_market_cap_sort` when the snapshot is available (`:713`). It enriches tickers/market data only; it preserves the existing `CompanySearchResult.company_name` (`:766-793`).
4. For the live installed DB, the market-cap path uses local records because the local catalog is sufficient. `_load_local_company_universe_results` in `src/financials/read_service_coverage.py:1121` builds results from `companies.company_name`; it does not reconcile the catalog name. The catalog merge at `:2245` also retains a local DB result whenever present (`:2290-2293`).
5. Directory consumers visibly render the raw field, notably `apps/desktop-web/src/components/CompaniesTable.tsx:533`, the command palette (`src/components/command/commands/companies.ts:23`), coverage search/results (`src/routes/CoveragePage.tsx:1441`), and the home company selector (`src/components/home/widgets/shared/CompanySelector.tsx:26`).
6. The detail facade calls `get_company_info` in `apps/desktop-web/src/lib/api/companyDetail.ts:25`; bridge `desktop/bridge_api/companies.py:92` calls the service.
7. `CVMReadService.get_company_info` (`src/financials/read_service_query.py:224`) reads the local row first. `_enrich_company_identity_fallback` (`:449`) fills only missing ticker/CNPJ, never `company_name`; `_build_company_info_dto` (`:480`) retains any non-empty name, including the placeholder. The shared `EntityHeader` renders it directly at `apps/desktop-web/src/components/EntityHeader.tsx:168`, so `/empresas/25658` visibly leaks it.

## Cause and recommended repair

The name placeholder was persisted during the on-demand refresh (the refresh log records a successful request for company `25658` with `company_name: 'CVM_25658'`). Subsequent query paths treat any non-empty name as authoritative. The resolver cannot help today because its own primary result also reads the local placeholder; the catalog is the verified corrected source.

Implement a small, shared normalization at the active read-model boundary: when a local name matches the synthetic placeholder form `CVM_<same cd_cvm>`, replace it with the active catalog entry's company name (and optionally `nome_comercial`) for both directory result construction and `get_company_info`. Do **not** broadly overwrite non-placeholder local names and do not use market-cap snapshot names as identity authority. Add the same correction to the refresh/import write path later so future rows are stored correctly; that is secondary to the interview-visible read fix.

## Existing tests and gap

- `tests/test_company_market_cap_sort.py` covers local snapshot ordering, exact `cd_cvm`/ticker mapping, and fallback. It does not assert that a placeholder local name is normalized to a catalog name.
- `tests/test_backend_perf_optimizations.py:42` exercises the bridge `get_companies` call, but only with a stub service.
- `apps/desktop-web/src/components/CompaniesTable.test.ts` covers route/label helpers, not bridge payload rendering or identity normalization.
- No located test covers `CVMReadService.get_company_info` with a placeholder local `company_name` plus a verified catalog identity.

Add regression coverage at the Python read-service level for both `list_companies` (with snapshot enabled) and `get_company_info`: seed `cd_cvm=25658` with `company_name='CVM_25658'`, provide a catalog entry named AgroGalaxy, then assert neither result contains the placeholder. A thin bridge test is optional; TypeScript coverage is unnecessary if the API contract remains unchanged.

## Validation before interview

After the targeted fix, run the new regression tests and `pytest tests/test_company_market_cap_sort.py tests/test_backend_perf_optimizations.py`. Then open the real packaged/runtime app against the Documents root and verify: directory search `AGXY3`, command-palette search, and `/empresas/25658` header all display AgroGalaxy and continue to use CVM 25658 / AGXY3.
