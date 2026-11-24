import io
import sys
from pathlib import Path
import pandas as pd
import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.financials.formulas import (
    evaluate_formulas,
    is_formula_row,
    get_formula_definitions,
)
from src.financials.excel_exporter import ExcelExporter, build_default_model_mapping
from src.financials.excel_mapping import ModelMappingDefinition, ModelMappingEntry, ModelMappingSource


class MockEntry:
    def __init__(self, target_id, target_label, sources=None):
        self.target_id = target_id
        self.target_label = target_label
        self.sources = sources or []


def test_formula_definitions_and_checking():
    # Test that formula rows are correctly identified
    assert is_formula_row("DRE:3.03", is_financial=False) is True
    assert is_formula_row("DRE:3.03", is_financial=True) is True
    assert is_formula_row("DRE:3.01", is_financial=False) is False

    defs = get_formula_definitions(is_financial=False)
    assert "DRE:3.03" in defs
    assert defs["DRE:3.03"]["dependencies"] == ["DRE:3.01", "DRE:3.02"]


def test_evaluate_formulas_basic():
    # 1. Gross Profit calculated from Revenue and negative Costs
    # DRE:3.03 = DRE:3.01 (Revenue) + DRE:3.02 (Costs)
    entries = [
        MockEntry("DRE:3.01", "Revenue"),
        MockEntry("DRE:3.02", "Costs"),
        MockEntry("DRE:3.03", "Gross Profit"),
    ]
    periods = ["2024", "2025"]
    values_by_target_period = {
        "DRE:3.01": {"2024": 100.0, "2025": 120.0},
        "DRE:3.02": {"2024": -45.0, "2025": -50.0},
        "DRE:3.03": {"2024": None, "2025": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    # Validate calculations
    assert updated_vals["DRE:3.03"]["2024"] == 55.0
    assert updated_vals["DRE:3.03"]["2025"] == 70.0
    assert check_statuses["DRE:3.03"]["2024"]["status"] == "calculated"
    assert len(issues) == 0


def test_evaluate_formulas_missing_required():
    # 4. Correct behavior when one required input is missing
    # Gross Profit = Revenue + Costs. If Costs is missing, GP should be None/unavailable.
    entries = [
        MockEntry("DRE:3.01", "Revenue"),
        MockEntry("DRE:3.02", "Costs"),
        MockEntry("DRE:3.03", "Gross Profit"),
    ]
    periods = ["2024"]
    values_by_target_period = {
        "DRE:3.01": {"2024": 100.0},
        "DRE:3.02": {"2024": None},  # Mapped but missing (or unmapped)
        "DRE:3.03": {"2024": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    assert updated_vals["DRE:3.03"]["2024"] is None
    assert check_statuses["DRE:3.03"]["2024"]["status"] == "unavailable"


def test_evaluate_formulas_missing_optional():
    # 5. Correct distinction between missing values and optional values
    # Financial Result (3.06) = Financial Income (3.06.01) + Financial Expenses (3.06.02)
    # Both dependencies are optional. If unmapped, they are treated as 0.0.
    entries = [
        MockEntry("DRE:3.06", "Financial Result"),
    ]
    periods = ["2024"]
    values_by_target_period = {
        "DRE:3.06": {"2024": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    # Both dependencies unmapped/missing -> optional -> defaults to 0.0 -> sum is 0.0
    assert updated_vals["DRE:3.06"]["2024"] == 0.0
    assert check_statuses["DRE:3.06"]["2024"]["status"] == "calculated"


def test_evaluate_formulas_reconciliation():
    # 6. Reported-versus-calculated reconciliation and rounding tolerance
    # Let's map a source to Gross Profit so that reported_val is available
    entries = [
        MockEntry("DRE:3.01", "Revenue"),
        MockEntry("DRE:3.02", "Costs"),
        MockEntry("DRE:3.03", "Gross Profit", sources=[object()]),  # sources present -> reported exists
    ]
    periods = ["2024", "2025", "2026"]
    
    # 2024: exact match
    # 2025: rounding difference (diff = 0.5 <= 1.0 tolerance)
    # 2026: mismatch (diff = 5.0 > 1.0 tolerance)
    values_by_target_period = {
        "DRE:3.01": {"2024": 100.0, "2025": 100.0, "2026": 100.0},
        "DRE:3.02": {"2024": -45.0, "2025": -45.0, "2026": -45.0},
        "DRE:3.03": {"2024": 55.0, "2025": 54.5, "2026": 50.0},  # reported values slot
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
        tolerance=1.0,
    )

    # 2024 check status
    assert updated_vals["DRE:3.03"]["2024"] == 55.0
    assert check_statuses["DRE:3.03"]["2024"]["status"] == "pass"
    assert check_statuses["DRE:3.03"]["2024"]["variance"] == 0.0

    # 2025 check status
    assert updated_vals["DRE:3.03"]["2025"] == 55.0
    assert check_statuses["DRE:3.03"]["2025"]["status"] == "rounding_difference"
    assert check_statuses["DRE:3.03"]["2025"]["variance"] == 0.5

    # 2026 check status
    assert updated_vals["DRE:3.03"]["2026"] == 55.0
    assert check_statuses["DRE:3.03"]["2026"]["status"] == "mismatch"
    assert check_statuses["DRE:3.03"]["2026"]["variance"] == 5.0
    assert len(issues) == 1
    assert "does not match reported CVM value" in issues[0].message


def test_excel_exporter_contains_formulas():
    # 10. Excel cells containing formulas rather than hardcoded values
    company_info = {
        "company_name": "Formula Test S.A.",
        "cd_cvm": 9999,
        "ticker_b3": "FORM3",
        "cnpj": "00.000.000/0001-99",
        "setor_cvm": "Industrial",
    }
    
    # Minimal statements that populate Revenue, Costs and Gross Profit
    def _row(cd_conta: str, label: str, value: float) -> dict[str, object]:
        return {
            "CD_CONTA": cd_conta,
            "DS_CONTA": label,
            "STANDARD_NAME": label,
            "LINE_ID_BASE": cd_conta,
            "2024": value,
        }

    statements = {
        "DRE": pd.DataFrame([
            _row("3.01", "Revenue", 100_000),
            _row("3.02", "Costs", -60_000),
            _row("3.03", "Gross Profit", 40_000),
        ]),
        "BPA": pd.DataFrame([]),
        "BPP": pd.DataFrame([]),
        "DFC": pd.DataFrame([]),
    }

    # Generate standard preset mapping
    model_mapping = build_default_model_mapping(company_info)

    exporter = ExcelExporter(
        company_info=company_info,
        statements=statements,
        kpis_df=pd.DataFrame(),
        model_mapping=model_mapping,
    )

    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)

    ws = wb["Model"]
    
    # Find row coordinates for Revenue, Costs and Gross Profit on sheet
    revenue_row = None
    costs_row = None
    gp_row = None
    
    for row in range(1, ws.max_row + 1):
        label = str(ws.cell(row=row, column=2).value or "").strip()
        if label == "Revenue (=)":
            revenue_row = row
        elif label == "Costs (-)":
            costs_row = row
        elif label == "Gross Profit (=)":
            gp_row = row

    assert revenue_row is not None
    assert costs_row is not None
    assert gp_row is not None

    # Retrieve Gross Profit cell formula
    gp_cell_val = ws.cell(row=gp_row, column=4).value  # Column D (2024 value)
    assert isinstance(gp_cell_val, str)
    assert gp_cell_val.startswith("=IF(")
    assert f"SUM(D{revenue_row},D{costs_row})" in gp_cell_val


def test_evaluate_formulas_cfo_three_components():
    entries = [
        MockEntry("DFC:6.01.01", "Cash Generated by Operations"),
        MockEntry("DFC:6.01.02", "Working Capital Changes"),
        MockEntry("DFC:6.01.03", "Other Operating Cash Flows"),
        MockEntry("DFC:6.01", "CFO"),
    ]
    periods = ["2024"]
    values_by_target_period = {
        "DFC:6.01.01": {"2024": 1921.0},
        "DFC:6.01.02": {"2024": -716.0},
        "DFC:6.01.03": {"2024": -338.0},
        "DFC:6.01": {"2024": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    assert updated_vals["DFC:6.01"]["2024"] == 867.0
    assert check_statuses["DFC:6.01"]["2024"]["status"] == "calculated"


def test_evaluate_formulas_cfo_optional_missing():
    # 6.01.03 is unmapped -> values_by_target_period has no DFC:6.01.03
    entries = [
        MockEntry("DFC:6.01.01", "Cash Generated by Operations"),
        MockEntry("DFC:6.01.02", "Working Capital Changes"),
        MockEntry("DFC:6.01", "CFO"),
    ]
    periods = ["2024"]
    values_by_target_period = {
        "DFC:6.01.01": {"2024": 1921.0},
        "DFC:6.01.02": {"2024": -716.0},
        "DFC:6.01": {"2024": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    # 6.01.03 unmapped -> treated as 0.0 -> CFO is 1205.0
    assert updated_vals["DFC:6.01"]["2024"] == 1205.0
    assert check_statuses["DFC:6.01"]["2024"]["status"] == "calculated"


def test_evaluate_formulas_cfo_mapped_missing():
    # 6.01.03 is mapped, but missing (None) in 2024
    entries = [
        MockEntry("DFC:6.01.01", "Cash Generated by Operations"),
        MockEntry("DFC:6.01.02", "Working Capital Changes"),
        MockEntry("DFC:6.01.03", "Other Operating Cash Flows", sources=[object()]),  # mapped
        MockEntry("DFC:6.01", "CFO"),
    ]
    periods = ["2024"]
    values_by_target_period = {
        "DFC:6.01.01": {"2024": 1921.0},
        "DFC:6.01.02": {"2024": -716.0},
        "DFC:6.01.03": {"2024": None},  # mapped but missing (None)
        "DFC:6.01": {"2024": None},
    }

    updated_vals, check_statuses, issues = evaluate_formulas(
        is_financial=False,
        entries=entries,
        periods=periods,
        values_by_target_period=values_by_target_period,
    )

    # Since DFC:6.01.03 has sources (mapped) but value is None -> missing required/mapped -> CFO is None
    assert updated_vals["DFC:6.01"]["2024"] is None
    assert check_statuses["DFC:6.01"]["2024"]["status"] == "unavailable"


def test_excel_exporter_cfo_three_component_formula():
    company_info = {
        "company_name": "CFO Formula Test S.A.",
        "cd_cvm": 8888,
        "ticker_b3": "CFOT3",
        "cnpj": "00.000.000/0001-88",
        "setor_cvm": "Industrial",
    }
    
    def _row(cd_conta: str, label: str, value: float) -> dict[str, object]:
        return {
            "CD_CONTA": cd_conta,
            "DS_CONTA": label,
            "STANDARD_NAME": label,
            "LINE_ID_BASE": cd_conta,
            "2024": value,
        }

    statements = {
        "DRE": pd.DataFrame([]),
        "BPA": pd.DataFrame([]),
        "BPP": pd.DataFrame([]),
        "DFC": pd.DataFrame([
            _row("6.01.01", "Cash Generated by Operations", 1921000),
            _row("6.01.02", "Working Capital Changes", -716000),
            _row("6.01.03", "Other Operating Cash Flows", -338000),
            _row("6.01", "Cash Flow from Operations (CFO)", 867000),
        ]),
    }

    model_mapping = build_default_model_mapping(company_info)
    
    # Let's map DFC:6.01.03 to check it's included
    # Since it's in the default spine, build_default_model_mapping will include it!
    # Let's assert that the default mapping has DFC:6.01.03
    has_cfo_other = any(e.target_id == "DFC:6.01.03" for e in model_mapping.entries)
    assert has_cfo_other is True

    exporter = ExcelExporter(
        company_info=company_info,
        statements=statements,
        kpis_df=pd.DataFrame(),
        model_mapping=model_mapping,
    )

    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)

    ws = wb["Model"]
    
    # Find row coordinates
    gen_row = None
    wc_row = None
    other_row = None
    cfo_row = None
    
    for row in range(1, ws.max_row + 1):
        label = str(ws.cell(row=row, column=2).value or "").strip()
        if label == "Cash Generated by Operations (=)":
            gen_row = row
        elif label == "Working Capital Changes (=)":
            wc_row = row
        elif label == "Other Operating Cash Flows":
            other_row = row
        elif label == "Cash Flow from Operations (CFO) (=)":
            cfo_row = row

    assert gen_row is not None
    assert wc_row is not None
    assert other_row is not None
    assert cfo_row is not None

    cfo_cell_val = ws.cell(row=cfo_row, column=4).value  # Column D (2024 value)
    assert isinstance(cfo_cell_val, str)
    assert cfo_cell_val.startswith("=IF(")
    assert f"SUM(D{gen_row},D{wc_row},D{other_row})" in cfo_cell_val
