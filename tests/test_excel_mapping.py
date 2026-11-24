import io
import sys
from dataclasses import replace
from pathlib import Path

import openpyxl
import pandas as pd
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.financials.excel_exporter import ExcelExporter, build_default_model_mapping
from src.financials.excel_mapping import (
    ExcelMappingRepository,
    ModelMappingDefinition,
    ModelMappingSource,
    SYSTEM_DEFAULT_PRESET_ID,
)
from src.financials.read_service import CVMReadService


def _company() -> dict[str, object]:
    return {
        "company_name": "Mapping Test S.A.",
        "cd_cvm": 1234,
        "ticker_b3": "MAPT3",
        "cnpj": "00.000.000/0001-00",
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


def _statements() -> dict[str, pd.DataFrame]:
    return {
        "DRE": pd.DataFrame(
            [
                _row("3.01.01", "Gross Revenue", 1_000_000),
                _row("3.01.02", "Revenue Deductions", -100_000),
                _row("3.01", "Revenue", 900_000),
                _row("3.05", "EBIT", 200_000),
                _row("3.11", "Net Income", 140_000),
            ]
        ),
        "BPA": pd.DataFrame(
            [
                _row("1", "Total Assets", 1_400_000),
                _row("1.01", "Current Assets", 600_000),
            ]
        ),
        "BPP": pd.DataFrame(
            [
                _row("2", "Total Liabilities and Equity", 1_400_000),
                _row("2.03", "Equity", 700_000),
            ]
        ),
        "DFC": pd.DataFrame(
            [
                _row("6.01", "Cash Flow from Operations", 220_000),
                _row("6.01.01.03", "Depreciation and Amortization", 25_000),
                _row("6.02.01", "Capex", -80_000),
            ]
        ),
    }


def _custom_revenue_mapping() -> ModelMappingDefinition:
    default = build_default_model_mapping(_company())
    entries = []
    for entry in default.entries:
        if entry.target_id == "DRE:3.01":
            entry = replace(
                entry,
                operation="sum_with_sign",
                sources=(
                    ModelMappingSource(
                        statement_type="DRE",
                        line_id_base="3.01.01",
                        cd_conta="3.01.01",
                        label_snapshot="Gross Revenue",
                        sign=1,
                        position=0,
                    ),
                    ModelMappingSource(
                        statement_type="DRE",
                        line_id_base="3.01.02",
                        cd_conta="3.01.02",
                        label_snapshot="Revenue Deductions",
                        sign=-1,
                        position=1,
                    ),
                ),
            )
        entries.append(entry)
    return replace(
        default,
        preset_id="user:test-mapping",
        name="Custom Revenue Mapping",
        description="Revenue is mapped from two raw lines.",
        origin="user",
        entries=tuple(entries),
    )


def _find_model_row(ws, label: str) -> int:
    for row in range(1, ws.max_row + 1):
        value = str(ws.cell(row=row, column=2).value or "")
        if value.strip() == label:
            return row
    raise AssertionError(f"Model row not found: {label}")


def test_custom_mapping_generates_signed_raw_sheet_formula_and_audit_sheet():
    exporter = ExcelExporter(
        company_info=_company(),
        statements=_statements(),
        kpis_df=pd.DataFrame(),
        model_mapping=_custom_revenue_mapping(),
    )

    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)

    ws = wb["Model"]
    revenue_row = _find_model_row(ws, "Revenue (=)")
    formula = str(ws.cell(row=revenue_row, column=4).value)
    assert formula.startswith("=IF(")
    assert "'raw_DRE'!" in formula
    assert "/1000" in formula
    assert "-'raw_DRE'!" in formula

    audit = wb["mapping_audit"]
    assert audit.sheet_state == "hidden"
    headers = [audit.cell(row=1, column=col).value for col in range(1, audit.max_column + 1)]
    assert "Resolved formula" in headers
    audit_rows = [
        [audit.cell(row=row, column=col).value for col in range(1, audit.max_column + 1)]
        for row in range(2, audit.max_row + 1)
    ]
    revenue_audit = next(row for row in audit_rows if row[1] == "DRE:3.01")
    assert "DRE:3.01.01" in revenue_audit[5]
    assert "DRE:3.01.02" in revenue_audit[5]
    assert "raw_DRE" in revenue_audit[7]


def test_mapping_formula_uses_period_specific_duplicate_source_row():
    statements = _statements()
    statements["DRE"] = pd.DataFrame(
        [
            {
                "CD_CONTA": "3.01",
                "DS_CONTA": "Revenue 2023",
                "STANDARD_NAME": "Revenue",
                "LINE_ID_BASE": "dre-revenue-a",
                "2023": 1_000_000.0,
                "2024": None,
            },
            {
                "CD_CONTA": "3.01",
                "DS_CONTA": "Revenue 2024",
                "STANDARD_NAME": "Revenue",
                "LINE_ID_BASE": "dre-revenue-b",
                "2023": None,
                "2024": 2_000_000.0,
            },
            {
                "CD_CONTA": "3.05",
                "DS_CONTA": "EBIT",
                "STANDARD_NAME": "EBIT",
                "LINE_ID_BASE": "3.05",
                "2023": 200_000.0,
                "2024": 250_000.0,
            },
            {
                "CD_CONTA": "3.11",
                "DS_CONTA": "Net Income",
                "STANDARD_NAME": "Net Income",
                "LINE_ID_BASE": "3.11",
                "2023": 140_000.0,
                "2024": 150_000.0,
            },
        ]
    )
    exporter = ExcelExporter(
        company_info=_company(),
        statements=statements,
        kpis_df=pd.DataFrame(),
        model_mapping=build_default_model_mapping(_company()),
    )

    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)

    ws = wb["Model"]
    revenue_row = _find_model_row(ws, "Revenue (=)")
    formulas = [
        str(ws.cell(row=revenue_row, column=col).value)
        for col in range(1, ws.max_column + 1)
        if isinstance(ws.cell(row=revenue_row, column=col).value, str)
    ]
    assert any("'raw_DRE'!E2/1000" in formula for formula in formulas)
    assert any("'raw_DRE'!F3/1000" in formula for formula in formulas)


def test_mapping_repository_persists_presets_and_company_defaults(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mapping.db'}")
    repository = ExcelMappingRepository(engine)
    mapping = _custom_revenue_mapping()

    saved = repository.save_preset(mapping)
    loaded = repository.load_preset(saved.preset_id)

    assert loaded is not None
    assert loaded.preset_id == saved.preset_id
    assert loaded.name == "Custom Revenue Mapping"
    revenue_entry = next(entry for entry in loaded.entries if entry.target_id == "DRE:3.01")
    assert revenue_entry.operation == "sum_with_sign"
    assert [source.line_id_base for source in revenue_entry.sources] == ["3.01.01", "3.01.02"]
    assert [source.sign for source in revenue_entry.sources] == [1, -1]

    repository.set_company_default_preset(1234, saved.preset_id)
    assert repository.get_company_default_preset_id(1234) == saved.preset_id

    presets = repository.list_presets(company_default_preset_id=saved.preset_id)
    assert presets[0]["preset_id"] == SYSTEM_DEFAULT_PRESET_ID
    assert any(
        preset["preset_id"] == saved.preset_id and preset["company_default"]
        for preset in presets
    )

    repository.set_company_default_preset(1234, SYSTEM_DEFAULT_PRESET_ID)
    assert repository.get_company_default_preset_id(1234) is None


def test_mapping_preview_rows_and_raw_lines_include_scaled_values():
    mapping = _custom_revenue_mapping()
    statements = _statements()
    periods = ["2024"]

    preview_rows = CVMReadService._model_preview_rows(
        mapping,
        statements,
        periods,
        issues=[],
    )
    revenue = next(row for row in preview_rows if row["target_id"] == "DRE:3.01")
    assert revenue["source_count"] == 2
    assert revenue["values_by_period"]["2024"] == 1100.0

    raw_lines = CVMReadService._raw_mapping_lines(
        statements,
        preview_periods=periods,
        mapped_targets=CVMReadService._mapping_source_targets(mapping),
    )
    gross_revenue = next(line for line in raw_lines if line["line_id_base"] == "3.01.01")
    assert gross_revenue["sample_values_by_period"]["2024"] == 1000.0
    assert gross_revenue["mapped_targets"][0]["target_id"] == "DRE:3.01"


def test_public_service_preserves_mapping_commands(tmp_path):
    from src.financials.resolver import ModelResolver

    engine = create_engine(f"sqlite:///{tmp_path / 'facade-mapping.db'}")
    service = object.__new__(CVMReadService)
    service.engine = engine
    service.excel_mapping_repository = ExcelMappingRepository(engine)
    try:
        result = service.save_excel_mapping_preset({"mapping": _custom_revenue_mapping().to_dict()})
        preset_id = result["preset"]["preset_id"]
        assert result["ok"] is True
        service.set_company_excel_mapping_default(1234, preset_id)
        assert service.excel_mapping_repository.get_company_default_preset_id(1234) == preset_id
        assert service.excel_mapping_repository.load_preset(preset_id) is not None

        assert service.save_excel_mapping_override(
            1234, "DRE:3.01", "2024", "3.01.01", source_desc="Gross Revenue", sign=-1,
        ) == {"ok": True}
        override = ModelResolver(engine).get_overrides(1234)["DRE:3.01"]["2024"]
        assert override["source_code"] == "3.01.01"
        assert override["sign"] == -1
        assert service.delete_excel_mapping_override(1234, "DRE:3.01", "2024") == {"ok": True}
        assert ModelResolver(engine).get_overrides(1234) == {}
    finally:
        engine.dispose()


def _override_engine(tmp_path, *overrides):
    from src.financials.excel_mapping import ensure_excel_mapping_tables_for_connection
    from src.financials.resolver import ModelResolver

    engine = create_engine(f"sqlite:///{tmp_path / 'overrides.db'}")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    for period, code, sign in overrides:
        ModelResolver(engine).save_override(1234, "DRE:3.01", period, code, source_desc=code, sign=sign)
    return engine


def _two_period_statements() -> dict[str, pd.DataFrame]:
    statements = _statements()
    statements["DRE"] = statements["DRE"].assign(**{"2023": statements["DRE"]["2024"]})[
        ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE", "2023", "2024"]
    ]
    return statements


def _revenue_formulas_and_audit(engine, statements):
    exporter = ExcelExporter(
        company_info=_company(),
        statements=statements,
        kpis_df=pd.DataFrame(),
        model_mapping=build_default_model_mapping(_company()),
        engine=engine,
    )
    wb = openpyxl.load_workbook(io.BytesIO(exporter.export()), data_only=False)
    ws = wb["Model"]
    row = _find_model_row(ws, "Revenue (=)")
    formulas = [str(ws.cell(row=row, column=col).value) for col in (4, 5)]
    audit = wb["mapping_audit"]
    audit_row = next(
        [audit.cell(row=r, column=c).value for c in range(1, audit.max_column + 1)]
        for r in range(2, audit.max_row + 1)
        if audit.cell(row=r, column=2).value == "DRE:3.01"
    )
    return formulas, audit_row


def test_period_override_replaces_preset_source_only_for_that_period(tmp_path):
    engine = _override_engine(tmp_path, ("2024", "3.01.01", 1))
    (f2023, f2024), audit_row = _revenue_formulas_and_audit(engine, _two_period_statements())
    # raw_DRE rows: 3.01.01 is row 2, 3.01 is row 4.
    assert "'raw_DRE'!" in f2023 and "4/1000" in f2023
    assert "'raw_DRE'!" in f2024 and "2/1000" in f2024 and "4/1000" not in f2024
    assert "manual override" in " ".join(str(v) for v in audit_row if v)


def test_global_override_applies_to_every_period_with_its_sign(tmp_path):
    engine = _override_engine(tmp_path, ("GLOBAL", "3.01.02", -1))
    (f2023, f2024), _ = _revenue_formulas_and_audit(engine, _two_period_statements())
    for formula in (f2023, f2024):
        assert "-'raw_DRE'!" in formula and "3/1000" in formula
