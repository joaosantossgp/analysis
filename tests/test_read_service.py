# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3

from src.gics_manual_mapping import GICS_11_SECTORS
from src.read_service import CVMReadService, resolve_refresh_year_range
from src.settings import build_settings
from src.utils import current_reporting_year_cap


def test_resolve_refresh_year_range_defaults_through_current_year():
    start_year, end_year = resolve_refresh_year_range({}, default_start_year=2010)
    assert start_year == 2010
    assert end_year == current_reporting_year_cap()


def test_resolve_refresh_year_range_respects_explicit_end_year():
    start_year, end_year = resolve_refresh_year_range(
        {"end_year": current_reporting_year_cap()},
        default_start_year=2010,
    )
    assert end_year == current_reporting_year_cap()


def test_resolve_refresh_range_defaults_end_to_current_year(tmp_path):
    service = CVMReadService(settings=build_settings(project_root=tmp_path))
    start_year, end_year = service._resolve_refresh_range(start_year=2010, end_year=None)
    assert start_year == 2010
    assert end_year == current_reporting_year_cap()


class _EmptyCompanyCatalog:
    def lookup_company(self, cd_cvm: int):
        return None

    def list_entries(self):
        return ()

    def search_companies(self, *, q: str, limit: int, exclude_codes=None):
        return ()


def test_list_refresh_status_returns_stable_dto_contract(tmp_path):
    settings = build_settings(project_root=tmp_path)
    db_path = settings.paths.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE company_refresh_status (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT,
                source_scope TEXT,
                last_attempt_at TEXT,
                last_success_at TEXT,
                last_status TEXT,
                last_error TEXT,
                last_start_year INTEGER,
                last_end_year INTEGER,
                last_rows_inserted INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO company_refresh_status (
                cd_cvm, company_name, source_scope,
                last_attempt_at, last_success_at, last_status, last_error,
                last_start_year, last_end_year, last_rows_inserted, updated_at
            ) VALUES (
                9512, 'PETROBRAS', 'local',
                '2026-04-07T10:00:00', '2026-04-07T10:01:00', 'success', NULL,
                2024, 2025, 120, '2026-04-07T10:01:00'
            )
            """
        )
        conn.commit()

    service = CVMReadService(settings=settings)
    rows = service.list_refresh_status()

    assert len(rows) == 1
    dto = rows[0]
    assert dto.cd_cvm == 9512
    assert dto.company_name == "PETROBRAS"
    assert dto.last_status == "success"
    assert dto.last_rows_inserted == 120
    assert dto.to_dict()["source_scope"] == "local"


def _seed_sector_read_service(tmp_path):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE companies (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT NOT NULL,
                nome_comercial TEXT,
                cnpj TEXT,
                setor_cvm TEXT,
                setor_analitico TEXT,
                gics_sector TEXT,
                gics_sector_slug TEXT,
                gics_industry_group TEXT,
                gics_industry TEXT,
                gics_sub_industry TEXT,
                company_type TEXT,
                ticker_b3 TEXT,
                coverage_rank INTEGER,
                is_active INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE financial_reports (
                COMPANY_NAME TEXT,
                CD_CVM INTEGER,
                STATEMENT_TYPE TEXT,
                REPORT_YEAR INTEGER,
                PERIOD_LABEL TEXT,
                LINE_ID_BASE TEXT,
                CD_CONTA TEXT,
                DS_CONTA TEXT,
                STANDARD_NAME TEXT,
                QA_CONFLICT INTEGER,
                VL_CONTA REAL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO companies (
                cd_cvm, company_name, nome_comercial, cnpj,
                setor_cvm, setor_analitico, gics_sector, gics_sector_slug,
                gics_industry_group, gics_industry, gics_sub_industry,
                company_type, ticker_b3, coverage_rank, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    9512,
                    "PETROBRAS",
                    "Petrobras",
                    "33",
                    "Energia",
                    "Energia",
                    "Energy",
                    "energy",
                    "Energy",
                    "Oil, Gas & Consumable Fuels",
                    "Integrated Oil & Gas",
                    "comercial",
                    "PETR4",
                    1,
                    1,
                    "2026",
                ),
                (
                    11223,
                    "SABESP",
                    "Sabesp",
                    "43",
                    "Saneamento",
                    None,
                    "Utilities",
                    "utilities",
                    "Utilities",
                    "Water Utilities",
                    "Water Utilities",
                    "comercial",
                    "SBSP3",
                    3,
                    1,
                    "2026",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO financial_reports (
                COMPANY_NAME, CD_CVM, STATEMENT_TYPE, REPORT_YEAR, PERIOD_LABEL,
                LINE_ID_BASE, CD_CONTA, DS_CONTA, STANDARD_NAME, QA_CONFLICT, VL_CONTA
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("PETROBRAS", 9512, "BPP", 2023, "2023", "bpp-1", "2.03", "Patrimonio Liquido", "Patrimonio Liquido", 0, 300.0),
                ("PETROBRAS", 9512, "DRE", 2023, "2023", "dre-1", "3.01", "Receita", "Receita", 0, 1000.0),
                ("PETROBRAS", 9512, "DRE", 2023, "2023", "dre-2", "3.05", "EBIT", "EBIT", 0, 200.0),
                ("PETROBRAS", 9512, "DRE", 2023, "2023", "dre-3", "3.11", "Lucro", "Lucro_Liq", 0, 150.0),
                ("PETROBRAS", 9512, "BPP", 2024, "2024", "bpp-2", "2.03", "Patrimonio Liquido", "Patrimonio Liquido", 0, 380.0),
                ("PETROBRAS", 9512, "DRE", 2024, "2024", "dre-4", "3.01", "Receita", "Receita", 0, 1100.0),
                ("PETROBRAS", 9512, "DRE", 2024, "2024", "dre-5", "3.05", "EBIT", "EBIT", 0, 240.0),
                ("PETROBRAS", 9512, "DRE", 2024, "2024", "dre-6", "3.11", "Lucro", "Lucro_Liq", 0, 180.0),
                ("SABESP", 11223, "DRE", 2024, "2024", "dre-7", "3.01", "Receita", "Receita", 0, 420.0),
            ],
        )
        conn.commit()

    service = CVMReadService(settings=settings)
    service._company_catalog = _EmptyCompanyCatalog()
    return service


def test_list_sectors_hub_counts_sum_matches_full_universe(tmp_path):
    """Sector hub totals must equal companies that resolve to a GICS hub (unpaged directory)."""
    service = _seed_sector_read_service(tmp_path)
    all_rows, _ = service.query_layer.get_companies_directory_page(
        search="",
        sector_name=None,
        page=1,
        page_size=None,
    )
    items = service._build_company_results(all_rows)
    classified = sum(
        1 for item in items if item.gics_sector and item.gics_sector in GICS_11_SECTORS
    )
    dto = service.list_sectors()
    hub_sum = sum(row.company_count for row in dto.items if row.group_type == "sector")
    assert hub_sum == classified


def test_list_sectors_returns_stable_snapshot_contract(tmp_path):
    service = _seed_sector_read_service(tmp_path)

    dto = service.list_sectors()

    names = [row.sector_name for row in dto.items]
    assert "Energy" in names
    assert "Utilities" in names

    energia = next(row for row in dto.items if row.sector_name == "Energy")
    saneamento = next(row for row in dto.items if row.sector_name == "Utilities")
    assert energia.latest_year == 2024
    assert energia.sub_industries == ("Integrated Oil & Gas",)
    assert round(energia.snapshot.roe or 0.0, 6) == round(180.0 / 380.0, 6)
    assert saneamento.latest_year == 2024
    assert saneamento.snapshot.roe is None


def test_get_sector_detail_defaults_to_latest_year_and_keeps_null_metrics(tmp_path):
    service = _seed_sector_read_service(tmp_path)

    detail = service.get_sector_detail("utilities")

    assert detail is not None
    assert detail.selected_year == 2024
    assert detail.available_years == (2024,)
    assert detail.companies[0].company_name == "SABESP"
    assert detail.companies[0].roe is None

