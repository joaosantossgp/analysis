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
import io
from pathlib import Path

import openpyxl
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
                setor_cvm, gics_sector, gics_sector_slug,
                gics_industry_group, gics_industry, gics_sub_industry,
                company_type, ticker_b3, coverage_rank, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (9512,  "PETROBRAS", None, None, None, None, None, None, None, None, "comercial", "PETR4", 1, 1, "2026"),
                (11223, "ITR_ONLY",  None, None, None, None, None, None, None, None, "comercial", None,    2, 1, "2026"),
                (33445, "PARTIAL_ITR", None, None, None, None, None, None, None, None, "comercial", None, 3, 1, "2026"),
                (44556, "CONFLICTED_ITR", None, None, None, None, None, None, None, None, "comercial", None, 4, 1, "2026"),
                (99999, "NO_DATA",   None, None, None, None, None, None, None, None, "comercial", None,    5, 1, "2026"),
            ],
        )

        # PETROBRAS: DFP years 2021–2025 + ITR-only 1Q26, 2Q26
        petr_rows = []
        core_lines = {
            "BPA": [("1", "Ativo Total", "Ativo Total")],
            "BPP": [("2", "Passivo Total", "Passivo Total")],
            "DRE": [
                ("3.01", "Receita", "Receita"),
                ("3.05", "Resultado Operacional", "Resultado Operacional"),
                ("3.11", "Lucro Liquido", "Lucro Liquido"),
            ],
            "DFC": [("6.01", "Fluxo de Caixa Operacional", "Fluxo de Caixa Operacional")],
        }

        def add_package(rows, company, cd_cvm, year, period, value, qa_conflict=0):
            for stmt, lines in core_lines.items():
                for cd_conta, ds_conta, standard_name in lines:
                    rows.append(
                        (
                            company,
                            cd_cvm,
                            stmt,
                            year,
                            period,
                            f"{stmt.lower()}-{cd_conta}",
                            cd_conta,
                            ds_conta,
                            standard_name,
                            qa_conflict,
                            float(value),
                        )
                    )

        for year in (2021, 2022, 2023, 2024, 2025):
            # Annual DFP package
            add_package(petr_rows, "PETROBRAS", 9512, year, str(year), year * 100)
            # Quarterly ITR rows for same year
            for q in (1, 2, 3, 4):
                period = f"{q}Q{year - 2000}"
                add_package(petr_rows, "PETROBRAS", 9512, year, period, year * 25)
        # ITR-only year 2026 (no annual DFP row for 2026)
        for q, val in ((1, 290_000.0), (2, 295_000.0)):
            period = f"{q}Q26"
            add_package(petr_rows, "PETROBRAS", 9512, 2026, period, val)
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
        itr_rows = []
        add_package(itr_rows, "ITR_ONLY", 11223, 2025, "1Q25", 50_000.0)
        add_package(itr_rows, "ITR_ONLY", 11223, 2025, "2Q25", 55_000.0)
        # PARTIAL_ITR: latest 1Q26 has only DRE, so freshness must stay FY2025.
        for year in (2024, 2025):
            add_package(itr_rows, "PARTIAL_ITR", 33445, year, str(year), year * 10)
        itr_rows.append(
            ("PARTIAL_ITR", 33445, "DRE", 2026, "1Q26", "dre-3.01", "3.01", "Receita", "Receita", 0, 10_000.0)
        )
        # CONFLICTED_ITR: complete-looking 1Q26 rows are all conflicted, so they are ignored.
        add_package(itr_rows, "CONFLICTED_ITR", 44556, 2025, "2025", 202_500.0)
        add_package(itr_rows, "CONFLICTED_ITR", 44556, 2026, "1Q26", 20_260.0, qa_conflict=1)
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


def test_latest_financial_period_prefers_complete_itr_when_newer(tmp_path):
    svc = _seed_db(tmp_path)
    info = svc.get_company_info_dict(9512)
    assert info["latest_financial_period_label"] == "2Q26"
    assert info["latest_financial_period_display"] == "2Q26"
    assert info["latest_financial_period_type"] == "quarter"
    assert info["latest_financial_period_year"] == 2026
    assert info["latest_financial_period_quarter"] == 2


def test_latest_financial_period_uses_annual_when_no_complete_newer_quarter(tmp_path):
    svc = _seed_db(tmp_path)
    info = svc.get_company_info_dict(33445)
    assert info["latest_financial_period_label"] == "2025"
    assert info["latest_financial_period_display"] == "FY2025"
    assert info["latest_financial_period_type"] == "annual"


def test_latest_financial_period_ignores_conflicted_quarter(tmp_path):
    svc = _seed_db(tmp_path)
    info = svc.get_company_info_dict(44556)
    assert info["latest_financial_period_label"] == "2025"
    assert info["latest_financial_period_display"] == "FY2025"


def test_latest_financial_period_supports_itr_only_company(tmp_path):
    svc = _seed_db(tmp_path)
    info = svc.get_company_info_dict(11223)
    assert info["latest_financial_period_label"] == "2Q25"
    assert info["latest_financial_period_display"] == "2Q25"
    assert info["latest_financial_period_type"] == "quarter"


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


def test_resolve_scope_does_not_include_incomplete_newer_itr_year(tmp_path):
    svc = _seed_db(tmp_path)
    scope = svc.resolve_excel_export_scope(33445, "last_5_years")
    assert scope["all_export_years"] == [2024, 2025]
    assert scope["itr_only_years"] == []


def test_resolve_scope_invalid_raises(tmp_path):
    svc = _seed_db(tmp_path)
    with pytest.raises(ValueError, match="Invalid period_scope"):
        svc.resolve_excel_export_scope(9512, "last_99_years")


def test_model_mapping_preview_includes_latest_itr_periods(tmp_path):
    svc = _seed_db(tmp_path)
    workspace = svc.get_excel_mapping_workspace(9512, period_scope="last_5_years")
    assert "1Q26" in workspace["preview_periods"]
    assert "2Q26" in workspace["preview_periods"]
    assert workspace["company"]["latest_financial_period_display"] == "2Q26"


def _workbook(payload: bytes, *, data_only: bool = False):
    return openpyxl.load_workbook(io.BytesIO(payload), data_only=data_only)


def test_company_excel_export_contract_from_seeded_database(tmp_path):
    svc = _seed_db(tmp_path)

    filename, payload = svc.build_company_excel_export(
        9512,
        period_scope="last_5_years",
    )
    wb = _workbook(payload, data_only=False)

    assert filename.startswith("PETR4_")
    assert wb.sheetnames[:2] == ["Model", "README"]
    hidden_sheet_names = (
        "raw_DRE",
        "raw_BPA",
        "raw_BPP",
        "raw_DFC",
        "raw_KPIs",
        "metadata",
        "mapping_audit",
    )
    for sheet_name in hidden_sheet_names:
        assert sheet_name in wb.sheetnames
    for sheet_name in hidden_sheet_names:
        assert wb[sheet_name].sheet_state == "hidden"
    for sheet_name in wb.sheetnames:
        assert list(wb[sheet_name].merged_cells.ranges) == []

    raw_dre = wb["raw_DRE"]
    headers = [
        raw_dre.cell(row=1, column=col).value
        for col in range(1, raw_dre.max_column + 1)
    ]
    assert headers[:4] == ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]
    period_col = headers.index("2Q26") + 1
    assert raw_dre.cell(row=2, column=period_col).value == 295_000.0

    model = wb["Model"]
    formula_values = [
        cell.value
        for row in model.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("=")
    ]
    assert any("'raw_DRE'!" in formula for formula in formula_values)
    assert any("/1000" in formula for formula in formula_values)

    metadata = wb["metadata"]
    fields = [
        metadata.cell(row=row, column=1).value
        for row in range(1, metadata.max_row + 1)
    ]
    assert "Export scope" in fields


def test_company_excel_export_loads_statement_frames_in_one_batch(tmp_path, monkeypatch):
    svc = _seed_db(tmp_path)
    calls: list[tuple[int, tuple[int, ...], tuple[str, ...]]] = []
    original = svc.query_layer.get_statements

    def spy_get_statements(*, cd_cvm, years, stmt_types, exclude_conflicts=True):
        calls.append((
            int(cd_cvm),
            tuple(int(year) for year in years),
            tuple(stmt_types),
        ))
        return original(
            cd_cvm=cd_cvm,
            years=years,
            stmt_types=stmt_types,
            exclude_conflicts=exclude_conflicts,
        )

    monkeypatch.setattr(svc.query_layer, "get_statements", spy_get_statements)

    svc.build_company_excel_export(9512, period_scope="last_5_years")

    assert calls == [
        (
            9512,
            (2021, 2022, 2023, 2024, 2025, 2026),
            ("DRE", "BPA", "BPP", "DFC"),
        )
    ]


def test_statement_scoped_excel_export_contract_from_seeded_database(tmp_path):
    svc = _seed_db(tmp_path)

    filename, payload = svc.build_company_excel_export(
        9512,
        statement_type="DRE",
        period_scope="last_5_years",
    )
    wb = _workbook(payload, data_only=False)

    assert filename.startswith("PETR4_DRE_")
    assert "raw_DRE" in wb.sheetnames
    assert "metadata" in wb.sheetnames
    assert "Model" not in wb.sheetnames
    assert "README" not in wb.sheetnames

    raw_dre = wb["raw_DRE"]
    headers = [
        raw_dre.cell(row=1, column=col).value
        for col in range(1, raw_dre.max_column + 1)
    ]
    period_col = headers.index("2Q26") + 1
    assert raw_dre.cell(row=2, column=period_col).value == 295_000.0


def test_statement_scoped_excel_export_loads_only_requested_statement(tmp_path, monkeypatch):
    svc = _seed_db(tmp_path)
    calls: list[tuple[str, ...]] = []
    original = svc.query_layer.get_statements

    def spy_get_statements(*, cd_cvm, years, stmt_types, exclude_conflicts=True):
        calls.append(tuple(stmt_types))
        return original(
            cd_cvm=cd_cvm,
            years=years,
            stmt_types=stmt_types,
            exclude_conflicts=exclude_conflicts,
        )

    monkeypatch.setattr(svc.query_layer, "get_statements", spy_get_statements)

    svc.build_company_excel_export(
        9512,
        statement_type="DRE",
        period_scope="last_5_years",
    )

    assert calls == [("DRE",)]


def test_model_mapping_workspace_preview_values_match_seeded_raw_data(tmp_path):
    svc = _seed_db(tmp_path)

    workspace = svc.get_excel_mapping_workspace(9512, period_scope="last_5_years")
    revenue = next(
        row for row in workspace["model_preview_rows"]
        if row["target_id"] == "DRE:3.01"
    )
    raw_revenue = next(
        line for line in workspace["raw_lines"]
        if line["statement_type"] == "DRE" and line["line_id_base"] == "dre-3.01"
    )

    assert revenue["values_by_period"]["2Q26"] == 295.0
    assert raw_revenue["sample_values_by_period"]["2Q26"] == 295.0


def test_model_mapping_workspace_loads_statement_frames_in_one_batch(tmp_path, monkeypatch):
    svc = _seed_db(tmp_path)
    calls: list[tuple[str, ...]] = []
    original = svc.query_layer.get_statements

    def spy_get_statements(*, cd_cvm, years, stmt_types, exclude_conflicts=True):
        calls.append(tuple(stmt_types))
        return original(
            cd_cvm=cd_cvm,
            years=years,
            stmt_types=stmt_types,
            exclude_conflicts=exclude_conflicts,
        )

    monkeypatch.setattr(svc.query_layer, "get_statements", spy_get_statements)

    svc.get_excel_mapping_workspace(9512, period_scope="last_5_years")

    assert calls == [("DRE", "BPA", "BPP", "DFC")]
