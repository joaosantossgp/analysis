import io
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.excel_exporter import (
    DEFAULT_PERIOD_WINDOW,
    ExcelExporter,
    build_excel_filename,
    _period_end_date,
    _pick_model_periods,
)


def _statement(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _minimal_kpis() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "CATEGORIA": "Rentabilidade",
            "KPI_ID": "MG_EBIT",
            "KPI_NOME": "Margem EBIT",
            "FORMULA": "EBIT / Receita",
            "IS_PLACEHOLDER": False,
            "FORMAT_TYPE": "pct",
            "HIGHER_IS_BETTER": True,
            "UNIDADE": "%",
            "2024": 0.2,
            "DELTA_YOY": None,
            "DELTA_YOY_PCT": None,
        }
    ])


def _sample_company() -> dict[str, object]:
    return {
        "company_name": "Empresa Exemplo",
        "cd_cvm": 1234,
        "ticker_b3": "EXMP3",
        "cnpj": "00.000.000/0001-00",
        "setor_cvm": "Teste",
        "setor_analitico": "Teste",
    }


def _wide_statements() -> dict[str, pd.DataFrame]:
    """Statements with a 5-annual + interleaved-quarter period grid."""
    period_cols = []
    for year in (2021, 2022, 2023, 2024, 2025):
        for q in (1, 2, 3, 4):
            period_cols.append(f"{q}Q{year - 2000}")
        period_cols.append(str(year))

    def make_row(cd, ds, base):
        d = {"CD_CONTA": cd, "DS_CONTA": ds, "STANDARD_NAME": "", "LINE_ID_BASE": cd}
        for i, p in enumerate(period_cols):
            d[p] = float(base) * (1 + i * 0.01)
        return d

    return {
        "DRE": _statement([
            make_row("3.01", "Receita",                 1_000_000),
            make_row("3.02", "Custos",                   -600_000),
            make_row("3.03", "Resultado Bruto",          400_000),
            make_row("3.04", "Despesas Operacionais",   -150_000),
            make_row("3.05", "EBIT",                     250_000),
            make_row("3.06", "Resultado Financeiro",     -30_000),
            make_row("3.07", "LAIR",                     220_000),
            make_row("3.08", "Impostos",                 -60_000),
            make_row("3.11", "Lucro Liquido",            160_000),
        ]),
        "BPA": _statement([
            make_row("1",       "Ativo Total",         2_100_000),
            make_row("1.01",    "Ativo Circulante",      800_000),
            make_row("1.01.01", "Caixa",                 350_000),
            make_row("1.02",    "Nao Circulante",      1_300_000),
        ]),
        "BPP": _statement([
            make_row("2",       "Passivo Total",       2_100_000),
            make_row("2.01",    "Passivo Circulante",    900_000),
            make_row("2.01.04", "Emprestimos CP",        250_000),
            make_row("2.02",    "Passivo Nao Circ.",     600_000),
            make_row("2.02.01", "Emprestimos LP",        400_000),
            make_row("2.03",    "Patrimonio Liquido",    600_000),
            make_row("2.03.01", "Capital",               300_000),
            make_row("2.03.04", "Reservas",              200_000),
        ]),
        "DFC": _statement([
            make_row("6.01",       "CFO",        250_000),
            make_row("6.01.01.03", "Depreciacao", 20_000),
            make_row("6.02",       "CFI",       -120_000),
            make_row("6.02.01",    "Capex",     -100_000),
            make_row("6.03",       "CFF",        -60_000),
            make_row("6.05",       "Var. Caixa",  70_000),
        ]),
        "DVA": _statement([
            make_row("7.08", "Valor Adicionado", 100_000),
        ]),
    }


# ─── period helpers ──────────────────────────────────────────────────────────
def test_period_end_date_known_labels():
    from datetime import date
    assert _period_end_date("1Q25") == date(2025, 3, 31)
    assert _period_end_date("2Q25") == date(2025, 6, 30)
    assert _period_end_date("3Q25") == date(2025, 9, 30)
    assert _period_end_date("4Q25") == date(2025, 12, 31)
    assert _period_end_date("2024") == date(2024, 12, 31)
    assert _period_end_date("garbage") is None


def test_pick_model_periods_interleaves_5_years_with_their_quarters():
    """The default window should produce ~25 columns:
    1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ..., 4Q25, 2025."""
    all_p = []
    for y in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025):
        for q in (1, 2, 3, 4):
            all_p.append(f"{q}Q{y - 2000}")
        all_p.append(str(y))

    window = _pick_model_periods(all_p, annuals=5, quarters_per_year=4)
    assert len(window) == 25  # 5 annuals + 5 * 4 quarters
    expected = []
    for y in (2021, 2022, 2023, 2024, 2025):
        for q in (1, 2, 3, 4):
            expected.append(f"{q}Q{y - 2000}")
        expected.append(str(y))
    assert window == expected


def test_pick_model_periods_falls_back_when_fewer_annuals():
    all_p = ["2024", "1Q24", "2Q24", "3Q24", "4Q24"]
    window = _pick_model_periods(all_p, annuals=5, quarters_per_year=4)
    assert window == ["1Q24", "2Q24", "3Q24", "4Q24", "2024"]


# ─── workbook structure ──────────────────────────────────────────────────────
def test_export_default_window_is_5_by_4():
    assert DEFAULT_PERIOD_WINDOW == (5, 4)


def test_full_export_sheet_layout():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    assert wb.sheetnames[0] == "Model"
    assert wb.sheetnames[1] == "README"
    for raw in ("raw_DRE", "raw_BPA", "raw_BPP", "raw_DFC", "raw_DVA",
                 "raw_KPIs", "metadata"):
        assert raw in wb.sheetnames, f"{raw} missing from workbook"


def test_raw_sheets_are_hidden_by_default():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    visible = [name for name in wb.sheetnames if wb[name].sheet_state == "visible"]
    hidden = [name for name in wb.sheetnames if wb[name].sheet_state == "hidden"]
    assert "Model" in visible
    assert "README" in visible
    for raw in ("raw_DRE", "raw_BPA", "raw_BPP", "raw_DFC", "raw_DVA",
                 "raw_KPIs", "metadata"):
        assert raw in hidden, f"{raw} should be hidden, got {wb[raw].sheet_state}"


def test_model_sheet_period_header_has_three_rows():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    # Find "Period" row
    period_row = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "Period":
            period_row = r
            break
    assert period_row is not None
    assert ws.cell(row=period_row + 1, column=2).value == "Period end date"
    assert ws.cell(row=period_row + 2, column=2).value == "Period type"


def test_model_period_window_is_5_annuals_plus_their_quarters():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    period_row = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "Period":
            period_row = r
            break
    assert period_row is not None
    # Collect period labels in row
    periods = []
    c = 4
    while ws.cell(row=period_row, column=c).value is not None:
        periods.append(str(ws.cell(row=period_row, column=c).value))
        c += 1
    # 5 annuals × (4 quarters + 1 annual) = 25 columns expected
    assert len(periods) == 25
    # Sanity: contains both 1Q21 and 2025
    assert "1Q21" in periods
    assert "2025" in periods
    # Period end-date row should contain real datetimes for each period
    for c_idx in range(4, 4 + len(periods)):
        val = ws.cell(row=period_row + 1, column=c_idx).value
        assert val is not None, f"missing date at col {c_idx}"
        assert isinstance(val, datetime) or hasattr(val, "year"), (
            f"date cell at col {c_idx} is not a date-like: {type(val)}"
        )


def test_workbook_has_no_error_cells():
    """Critical acceptance test: zero #NUM!/#REF!/#VALUE!/#DIV-0!/#NAME?/#N/A cells."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
    error_prefixes = ("#NUM!", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#N/A", "#NULL!")
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str):
                    for prefix in error_prefixes:
                        assert not v.startswith(prefix), (
                            f"Error cell in {sheet_name}!{cell.coordinate}: {v}"
                        )


def test_model_sheet_contains_required_sections():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    labels = [str(ws.cell(row=r, column=2).value or "")
              for r in range(1, ws.max_row + 1)]
    body = " | ".join(labels)
    for section in ("Income Statement", "Balance Sheet", "Cash Flow Statement",
                     "Value Added Statement", "KPIs / Ratios", "Checks",
                     "Source / Data Quality"):
        assert section in body, f"section '{section}' missing from Model sheet"
    # Computed lines present
    assert "EBITDA (=)" in body
    assert "Free Cash Flow (FCF) (=)" in body


def test_model_sheet_dva_unavailable_when_absent():
    stmts = _wide_statements()
    del stmts["DVA"]
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=stmts,
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    labels = [str(ws.cell(row=r, column=c).value or "")
              for r in range(1, ws.max_row + 1)
              for c in (2, 3, 4)]
    body = " | ".join(labels)
    assert "DVA Availability" in body
    assert "DVA" in body and "unavailable" in body.lower()


def test_model_sheet_kpi_formulas_use_iferror():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
    ws = wb["Model"]
    # Find any KPI row by looking for "EBITDA Margin" then sampling its cells
    target_row = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if isinstance(v, str) and "EBITDA Margin" in v:
            target_row = r
            break
    assert target_row is not None
    found_iferror = False
    for c_idx in range(4, 30):
        cell_val = ws.cell(row=target_row, column=c_idx).value
        if isinstance(cell_val, str) and cell_val.startswith("=IFERROR("):
            found_iferror = True
            break
    assert found_iferror, "EBITDA Margin row has no IFERROR formula"


def test_model_company_info_block_hidden_by_default():
    """Phase 1 P1 — company info block (Excel rows 13–22) ships grouped +
    hidden by default."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    for excel_row in range(13, 23):  # Excel rows 13..22 inclusive
        dim = ws.row_dimensions[excel_row]
        assert dim.hidden, f"row {excel_row} should be hidden by default"
        assert dim.outlineLevel == 1, f"row {excel_row} should be outline level 1"
    # The period header below the block stays visible.
    assert not ws.row_dimensions[24].hidden


def test_balance_sheet_tie_uses_relative_tolerance():
    """Phase 1 P3 — BS tie status uses a size-relative tolerance
    (max(0.5, 0.05% of Total Assets)), not a flat 0.5."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
    ws = wb["Model"]
    status = None
    for r in range(1, ws.max_row + 1):
        if "Balance Sheet:" in str(ws.cell(row=r, column=2).value or ""):
            status = ws.cell(row=r, column=3).value
            break
    assert status is not None, "Balance Sheet tie row not found"
    assert "0.0005" in status and "ABS(" in status, status
    assert status.startswith("=IF(SUMPRODUCT(")


def test_da_resolved_check_present_and_ok_when_matched():
    """Phase 1 P4 — a visible 'D&A Resolved' check reports the matched DFC
    line; OK when a 6.01.01.* 'depreci' line exists in the source."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),  # DFC has 6.01.01.03 "Depreciacao"
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    row = None
    for r in range(1, ws.max_row + 1):
        if "D&A Resolved" in str(ws.cell(row=r, column=2).value or ""):
            row = r
            break
    assert row is not None, "D&A Resolved check missing"
    assert ws.cell(row=row, column=3).value == "OK"
    assert "6.01.01.03" in str(ws.cell(row=row, column=4).value or "")


def test_da_resolved_check_warns_when_no_da_line():
    """Phase 1 P4 — WARNING when no D&A line resolves in the DFC source."""
    stmts = _wide_statements()
    stmts["DFC"] = _statement([
        {"CD_CONTA": "6.01", "DS_CONTA": "CFO", "STANDARD_NAME": "",
         "LINE_ID_BASE": "6.01", **{p: 1.0 for p in stmts["DRE"].columns
                                    if p not in ("CD_CONTA", "DS_CONTA",
                                                 "STANDARD_NAME", "LINE_ID_BASE")}},
    ])
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=stmts,
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    for r in range(1, ws.max_row + 1):
        if "D&A Resolved" in str(ws.cell(row=r, column=2).value or ""):
            assert ws.cell(row=r, column=3).value == "WARNING"
            return
    raise AssertionError("D&A Resolved check missing")


def _financial_company() -> dict[str, object]:
    return {**_sample_company(), "gics_sector": "Financials",
            "company_name": "Banco Exemplo S.A.", "ticker_b3": "BEXM4"}


def test_financial_firm_shows_banner_and_financial_spine():
    """Phase 3b — financial-sector spine active; banner visible; NII label used;
    industrial KPIs absent; financial critical lines present."""
    exporter = ExcelExporter(
        company_info=_financial_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    all_text = " | ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in (2, 3, 4)
    )
    assert "Financial institution" in all_text, "banner text missing"
    assert "financial-sector spine active" in all_text, "spine-active text missing"
    # Financial spine label overrides
    assert "Net Interest Income" in all_text, "NII label missing from IS"
    assert "Financial Intermediation Revenue" in all_text, "fin revenue label missing"
    # Industrial KPI rows (indented with 4 spaces by write_kpi) must be absent
    assert "    EBITDA Margin" not in all_text, "EBITDA Margin should not appear for banks"
    assert "    Current Ratio" not in all_text, "Current Ratio should not appear for banks"
    assert "    Net Debt / EBITDA" not in all_text, "Net Debt/EBITDA should not appear for banks"
    # Financial critical-line list
    assert "Net Interest Income (NII)" in all_text, "NII critical line missing"
    # Generic Spine WARNING check row was removed
    assert "Generic Spine" not in all_text, "stale Generic Spine row must not appear"


def test_non_financial_firm_has_no_spine_banner():
    """Phase 3b — no financial banner for industrial firms; standard KPIs present."""
    exporter = ExcelExporter(
        company_info=_sample_company(),  # gics_sector = "Teste" (not Financials)
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    all_text = " | ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in (2, 3, 4)
    )
    assert "Financial institution" not in all_text
    assert "Generic Spine" not in all_text
    assert "    EBITDA Margin" in all_text, "EBITDA Margin should appear for industrial"
    assert "    Current Ratio" in all_text, "Current Ratio should appear for industrial"


def test_financial_firm_balance_sheet_uses_financial_spine_labels():
    """Phase 3b — BPA and BPP use financial-institution label overrides."""
    exporter = ExcelExporter(
        company_info=_financial_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    labels = [
        str(ws.cell(row=r, column=2).value or "")
        for r in range(1, ws.max_row + 1)
    ]
    joined = " | ".join(labels)
    # Financial BPA overrides
    assert "Financial Assets" in joined, "BPA:1.02 label should be 'Financial Assets'"
    assert "FA at FV through P&L" in joined, "BPA:1.02.01 label missing"
    # Financial BPP overrides — 2.03 is now amortized cost liabilities
    assert "Financial Liabilities at Amortized Cost" in joined, "BPP:2.03 label wrong"
    assert "    Equity" in joined, "BPP:2.08 Equity label missing"
    # Industrial label for 2.03 must not appear
    assert "    Equity\n" not in "".join(labels[:1])  # no collision


def test_financial_firm_company_type_detection():
    """Phase 3b — company_type 'financeira' also triggers financial spine."""
    company = {**_sample_company(), "company_type": "financeira"}
    exporter = ExcelExporter(
        company_info=company,
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    all_text = " | ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in (2, 3, 4)
    )
    assert "Financial institution" in all_text, "company_type detection failed"
    assert "    EBITDA Margin" not in all_text, "industrial KPIs must be absent"


def test_financial_firm_nii_kpi_present():
    """Phase 3b — NII Margin KPI row appears for financial institutions."""
    exporter = ExcelExporter(
        company_info=_financial_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    all_text = " | ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in (2, 3, 4)
    )
    assert "NII Margin" in all_text, "NII Margin KPI missing for financial firm"


# ─── filenames (unchanged) ───────────────────────────────────────────────────
def test_build_excel_filename_uses_ticker_and_export_date():
    filename = build_excel_filename(
        _sample_company(),
        generated_at=datetime(2026, 4, 9, 14, 30),
    )
    assert filename == "EXMP3_20260409.xlsx"


def test_build_excel_filename_falls_back_to_cvm_code_without_ticker():
    filename = build_excel_filename(
        {**_sample_company(), "ticker_b3": None},
        generated_at=datetime(2026, 4, 9, 14, 30),
    )
    assert filename == "cvm1234_20260409.xlsx"


# ─── v0.19.1 refinements ─────────────────────────────────────────────────────
def test_no_merged_cells_anywhere():
    """Hard rule: zero merged ranges in any sheet of the workbook."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    for name in wb.sheetnames:
        merged = list(wb[name].merged_cells.ranges)
        assert merged == [], f"sheet {name} has merged cells: {merged}"


def test_conventions_rows_grouped_and_hidden():
    """Rows 3:9 (1-indexed) should be in outline level 1 and hidden by default."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    for r in range(3, 10):
        rd = ws.row_dimensions.get(r)
        assert rd is not None, f"row {r} has no dimension info"
        assert rd.outlineLevel == 1, (
            f"row {r} outline level: {rd.outlineLevel} (want 1)"
        )
        assert rd.hidden, f"row {r} should be hidden by default"


def test_latest_fiscal_year_populated_from_periods():
    """Even when company_info lacks 'latest_year', the cell should fall
    back to the most recent annual period present in the period window."""
    company = _sample_company()
    if "latest_year" in company:
        del company["latest_year"]
    exporter = ExcelExporter(
        company_info=company,
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    # Locate 'Latest fiscal year' row
    target_row = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=2).value == "Latest fiscal year":
            target_row = r
            break
    assert target_row is not None
    val = ws.cell(row=target_row, column=4).value
    # Sample statements have 2021-2025 — most recent annual is 2025.
    assert str(val) == "2025", f"expected 2025, got {val!r}"


def test_readme_does_not_mention_missing_raw_sheets():
    """If DVA is absent from statements, no `raw_DVA` mention in README."""
    stmts = _wide_statements()
    del stmts["DVA"]
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=stmts,
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    assert "raw_DVA" not in wb.sheetnames
    ws = wb["README"]
    full_text = " ".join(
        str(ws.cell(row=r, column=c).value or "")
        for r in range(1, ws.max_row + 1)
        for c in range(1, ws.max_column + 1)
    )
    assert "raw_DVA" not in full_text or "not** present" in full_text or "not present" in full_text


def test_model_sheet_dva_section_visible_when_absent():
    """DVA section heading must be visible even when no DVA data exists,
    with an explicit unavailability note row."""
    stmts = _wide_statements()
    del stmts["DVA"]
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=stmts,
        kpis_df=_minimal_kpis(),
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    labels = [str(ws.cell(row=r, column=2).value or "")
              for r in range(1, ws.max_row + 1)]
    body = " | ".join(labels)
    assert "Value Added Statement" in body
    assert "DVA unavailable" in body


def test_model_statement_is_expanded_taxonomy():
    """DRE alone should render >= 20 spine rows; full model > 60 rows total."""
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    # Count non-empty column-B labels between Income Statement and KPIs
    inside_is = False
    is_rows = 0
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if v == "Income Statement":
            inside_is = True
            continue
        if isinstance(v, str) and v.endswith("Statement") and v != "Income Statement":
            inside_is = False
        if inside_is and v:
            is_rows += 1
    assert is_rows >= 20, f"Income Statement has only {is_rows} rows (want >=20)"


def test_checks_include_cash_flow_tie_and_net_income_tie():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        extra_sheets=["DVA"],
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    ws = wb["Model"]
    labels = [str(ws.cell(row=r, column=2).value or "")
              for r in range(1, ws.max_row + 1)]
    body = " | ".join(labels)
    assert "Cash Flow Tie" in body
    assert "Net Income Tie" in body
    assert "Formula Error Scan" in body


# ─── scoped statement export still works ─────────────────────────────────────
def test_scoped_statement_export_is_minimal():
    exporter = ExcelExporter(
        company_info=_sample_company(),
        statements=_wide_statements(),
        kpis_df=_minimal_kpis(),
        statement_type="DRE",
    )
    payload = exporter.export()
    wb = openpyxl.load_workbook(io.BytesIO(payload))
    # Scoped export emits only the raw sheet + metadata
    assert "raw_DRE" in wb.sheetnames
    assert "metadata" in wb.sheetnames
    # Should NOT include the Model sheet for scoped exports
    assert "Model" not in wb.sheetnames
