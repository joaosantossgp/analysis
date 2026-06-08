# -*- coding: utf-8 -*-
"""Tests for Excel export period scope: query layer, read service, and
period resolution logic.

Uses an in-memory SQLite database seeded with:
  - cd_cvm 9512 (PETROBRAS): annual DFPs 2021–2025 + ITR-only year 2026 (1Q26, 2Q26)
  - cd_cvm 11223 (ITR_ONLY): only quarterly ITR periods (1Q25, 2Q25) — no DFP
  - cd_cvm 99999 (NO_DATA): company in catalog but no financial_reports rows
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.financials.query_layer import CVMQueryLayer
from src.financials.read_service import CVMReadService
from src.platform.settings import build_settings


# ─── DB fixtures ──────────────────────────────────────────────────────────────

def _seed_db(tmp_path: Path) -> CVMReadService:
    """Seed minimal DB and return a CVMReadService pointing at it."""
    settings = build_settings(project_root=tmp_path)
    db_path = settings.paths.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
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

        # Companies
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
                (9512,  "PETROBRAS", None, None, None, None, None, None, None, None, None, "comercial", "PETR4", 1, 1, "2026"),
                (11223, "ITR_ONLY",  None, None, None, None, None, None, None, None, None, "comercial", None,    2, 1, "2026"),
                (99999, "NO_DATA",   None, None, None, None, None, None, None, None, None, "comercial", None,    3, 1, "2026"),
            ],
        )

        # PETROBRAS: DFP years 2021–2025 + ITR-only 1Q26, 2Q26
        petr_rows = []
        for year in (2021, 2022, 2023, 2024, 2025):
            # Annual DFP row for DRE
            petr_rows.append(
                ("PETROBRAS", 9512, "DRE", year, str(year), "dre-1", "3.01", "Receita", "Receita", 0, float(year * 100))
            )
            # Quarterly ITR rows for same year
            for q in (1, 2, 3, 4):
                period = f"{q}Q{year - 2000}"
                petr_rows.append(
                    ("PETROBRAS", 9512, "DRE", year, period, "dre-1", "3.01", "Receita", "Receita", 0, float(year * 25))
                )
        # ITR-only year 2026 (no annual DFP row for 2026)
        for q, val in ((1, 290_000.0), (2, 295_000.0)):
            period = f"{q}Q26"
            petr_rows.append(
                ("PETROBRAS", 9512, "DRE", 2026, period, "dre-1", "3.01", "Receita", "Receita", 0, val)
            )
        conn.executemany(
            """
            INSERT INTO financial_reports (
                COMPANY_NAME, CD_CVM, STATEMENT_TYPE, REPORT_YEAR, PERIOD_LABEL,
                LINE_ID_BASE, CD_CONTA, DS_CONTA, STANDARD_NAME, QA_CONFLICT, VL_CONTA
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            petr_rows,
        )

        # ITR_ONLY company: only quarterly data, no DFP
        itr_rows = [
            ("ITR_ONLY", 11223, "DRE", 2025, "1Q25", "dre-1", "3.01", "Receita", "Receita", 0, 50_000.0),
            ("ITR_ONLY", 11223, "DRE", 2025, "2Q25", "dre-1", "3.01", "Receita", "Receita", 0, 55_000.0),
        ]
        conn.executemany(
            """
            INSERT INTO financial_reports (
                COMPANY_NAME, CD_CVM, STATEMENT_TYPE, REPORT_YEAR, PERIOD_LABEL,
                LINE_ID_BASE, CD_CONTA, DS_CONTA, STANDARD_NAME, QA_CONFLICT, VL_CONTA
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            itr_rows,
        )
        conn.commit()

    class _EmptyCatalog:
        def lookup_company(self, cd_cvm):
            return None
        def list_entries(self):
            return ()
        def search_companies(self, *, q, limit, exclude_codes=None):
            return ()

    svc = CVMReadService(settings=settings)
    svc._company_catalog = _EmptyCatalog()
    return svc


# ─── QueryLayer.get_available_export_periods ─────────────────────────────────

def test_query_layer_get_available_export_periods_annual_years(tmp_path):
    svc = _seed_db(tmp_path)
    result = svc.query_layer.get_available_export_periods(9512)
    assert result["annual_years"] == [2021, 2022, 2023, 2024, 2025]


def test_query_layer_get_available_export_periods_itr_only_year(tmp_path):
    svc = _seed_db(tmp_path)
    result = svc.query_layer.get_available_export_periods(9512)
    assert result["itr_only_years"] == [2026]
    assert result["all_export_years"] == [2021, 2022, 2023, 2024, 2025, 2026]


def test_query_layer_get_available_export_periods_itr_only_company(tmp_path):
    """Company with only quarterly ITR data (no DFP) — all years returned as ITR-only."""
    svc = _seed_db(tmp_path)
    result = svc.query_layer.get_available_export_periods(11223)
    assert result["annual_years"] == []
    assert result["itr_only_years"] == [2025]
    assert result["all_export_years"] == [2025]


def test_query_layer_get_available_export_periods_no_data(tmp_path):
    svc = _seed_db(tmp_path)
    result = svc.query_layer.get_available_export_periods(99999)
    assert result == {"annual_years": [], "itr_only_years": [], "all_export_years": []}


# ─── CVMReadService.resolve_excel_export_scope ───────────────────────────────

def test_resolve_scope_last_5_years(tmp_path):
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(9512, "last_5_years")
    # All 5 annual years + 2026 ITR
    assert set(scope["all_export_years"]) == {2021, 2022, 2023, 2024, 2025, 2026}
    assert scope["period_window"] == (5, 4)
    assert scope["scope_label"] == "Last 5 years"
    assert scope["itr_only_years"] == [2026]


def test_resolve_scope_last_3_years(tmp_path):
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(9512, "last_3_years")
    # Last 3 annual years (2023, 2024, 2025) + 2026 ITR
    assert set(scope["all_export_years"]) == {2023, 2024, 2025, 2026}
    assert scope["period_window"] == (3, 4)
    assert scope["scope_label"] == "Last 3 years"


def test_resolve_scope_last_10_years(tmp_path):
    """10-year scope is capped by available data (only 5 annual years exist)."""
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(9512, "last_10_years")
    # All available annual years (only 5) + 2026 ITR
    assert set(scope["all_export_years"]) == {2021, 2022, 2023, 2024, 2025, 2026}
    assert scope["period_window"] == (10, 4)
    assert scope["scope_label"] == "Last 10 years"


def test_resolve_scope_full_history(tmp_path):
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(9512, "full_history")
    assert set(scope["all_export_years"]) == {2021, 2022, 2023, 2024, 2025, 2026}
    assert scope["period_window"] == (5, 4)  # 5 = len(annual_years)
    assert scope["scope_label"] == "Full history"


def test_resolve_scope_itr_only_company(tmp_path):
    """Company with only ITR data: export years = ITR-only years, annuals = 0."""
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(11223, "last_5_years")
    assert scope["all_export_years"] == [2025]
    assert scope["period_window"] == (0, 4)


def test_resolve_scope_invalid_raises(tmp_path):
    svc = _seed_db(tmp_path)
    with pytest.raises(ValueError, match="Invalid period_scope"):
        svc.resolve_excel_export_scope(9512, "last_99_years")
