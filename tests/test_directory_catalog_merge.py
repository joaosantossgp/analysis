from __future__ import annotations

import sqlite3

from src.companies.catalog import CompanyCatalogEntry
from src.financials.read_service import CVMReadService
from src.platform.settings import build_settings

LOCAL_COUNT = 120  # above the old 100-company switch to local-only rows


class _Catalog:
    def __init__(self, entries):
        self._entries = tuple(entries)

    def list_entries(self):
        return self._entries

    def lookup_company(self, cd_cvm: int):
        return next((e for e in self._entries if e.cd_cvm == cd_cvm), None)

    def search_companies(self, *, q: str, limit: int, exclude_codes=None):
        return ()


def _entry(cd_cvm: int, name: str, active: bool = True) -> CompanyCatalogEntry:
    return CompanyCatalogEntry(cd_cvm, name, None, None, None, None, active)


def _service(tmp_path, catalog_entries):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute(
            "CREATE TABLE companies (cd_cvm INTEGER PRIMARY KEY, company_name TEXT NOT NULL, nome_comercial TEXT,"
            " cnpj TEXT, setor_cvm TEXT, gics_sector TEXT, gics_sector_slug TEXT, gics_industry_group TEXT,"
            " gics_industry TEXT, gics_sub_industry TEXT, company_type TEXT, ticker_b3 TEXT, coverage_rank INTEGER,"
            " is_active INTEGER, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE financial_reports (COMPANY_NAME TEXT, CD_CVM INTEGER, STATEMENT_TYPE TEXT, REPORT_YEAR INTEGER,"
            " PERIOD_LABEL TEXT, LINE_ID_BASE TEXT, CD_CONTA TEXT, DS_CONTA TEXT, STANDARD_NAME TEXT,"
            " QA_CONFLICT INTEGER, VL_CONTA REAL)"
        )
        conn.executemany(
            "INSERT INTO companies (cd_cvm, company_name, company_type, is_active, updated_at) VALUES (?, ?, 'comercial', 1, '2026')",
            [(code, f"LOCAL {code}") for code in range(1, LOCAL_COUNT + 1)],
        )
    service = CVMReadService(settings=settings)
    service._company_catalog = _Catalog(catalog_entries)
    return service


def _directory_codes(service) -> set[int]:
    page = service.list_companies(search="", sector_slug=None, page=1, page_size=1000)
    return {int(item.cd_cvm) for item in page.items}


def test_directory_keeps_active_catalog_companies_beyond_100_local_rows(tmp_path):
    catalog = [_entry(code, f"LOCAL {code}") for code in range(1, LOCAL_COUNT + 1)]
    catalog.append(_entry(999, "NOT DOWNLOADED YET"))
    service = _service(tmp_path, catalog)
    assert 999 in _directory_codes(service)


def test_directory_omits_inactive_catalog_companies(tmp_path):
    catalog = [_entry(code, f"LOCAL {code}") for code in range(1, LOCAL_COUNT + 1)]
    catalog.append(_entry(998, "CANCELLED REGISTRATION", active=False))
    service = _service(tmp_path, catalog)
    assert 998 not in _directory_codes(service)
