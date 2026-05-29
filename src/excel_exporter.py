# -*- coding: utf-8 -*-
"""src/excel_exporter.py — Analyst-ready Excel exporter (v0.19.0).

Produces a workbook centered on a single user-facing ``Model`` sheet
that consolidates the Income Statement, Balance Sheet, Cash Flow
Statement, optional Value Added Statement, KPIs, Checks, and Source /
Data Quality blocks. The full CVM tree and full period history remain
available in hidden ``raw_*`` sheets so the workbook stays auditable
without the model view becoming a data dump.

Visible sheets:
    Model    — analyst sheet (compact 5-year + 20-quarter window)
    README   — sheet map, conventions, period policy

Hidden sheets:
    raw_DRE / raw_BPA / raw_BPP / raw_DFC / raw_DVA (optional)
    raw_KPIs
    metadata

The legacy single-statement export path (used when a caller passes
``statement_type="DRE"`` etc) still produces a tightly-scoped workbook
that contains only ``Model`` and the relevant ``raw_<TYPE>`` sheet.

Usage::

    exp = ExcelExporter(company_info, statements, kpis_df)
    excel_bytes = exp.export()
"""
from __future__ import annotations

import io
import math
import re
from datetime import date, datetime
from typing import Optional

import numpy as np
import openpyxl
import pandas as pd
import xlsxwriter

from src.statement_summary import build_general_summary_blocks

try:
    from desktop.__version__ import __version__ as _APP_VERSION
except Exception:  # pragma: no cover - desktop package may be absent
    _APP_VERSION = "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Color palette — Aptos Narrow / Calibri financial modeling conventions
# ──────────────────────────────────────────────────────────────────────────────
PALETTE = {
    "blue_dark":    "#1F4E78",   # section headings, info labels
    "blue_input":   "#0070C0",   # manual input convention
    "green_linked": "#548235",   # linked-from-raw / OK status
    "orange_fill":  "#FFF2CC",   # output / hardcoded source rows
    "gray_text":    "#7F7F7F",   # notes
    "red_warn":     "#C00000",   # warnings, errors
    "amber":        "#BF8F00",   # warning status
    "annual_fill":  "#F2F2F2",   # annual period column shading
    "black":        "#1A1A1A",
}


# ──────────────────────────────────────────────────────────────────────────────
# Sheet names
# ──────────────────────────────────────────────────────────────────────────────
MODEL_SHEET = "Model"
README_SHEET = "README"
METADATA_SHEET = "metadata"
RAW_KPI_SHEET = "raw_KPIs"

_RAW_PREFIX = "raw_"
_LEGACY_TO_RAW = {
    "DRE": "raw_DRE",
    "BPA": "raw_BPA",
    "BPP": "raw_BPP",
    "DFC": "raw_DFC",
    "DVA": "raw_DVA",
    "DMPL": "raw_DMPL",
}

# Period window defaults — controlled by ExcelExporter(period_window=(annuals,
# quarters_per_year)). Annual + 4 quarters per annual = 25 columns by default.
DEFAULT_PERIOD_WINDOW: tuple[int, int] = (5, 4)


# ──────────────────────────────────────────────────────────────────────────────
# Analyst taxonomy — English labels keyed by CVM CD_CONTA. Falls back to
# STANDARD_NAME, then DS_CONTA when the code is not in this map.
# ──────────────────────────────────────────────────────────────────────────────
_MODEL_LINE_LABELS: dict[str, str] = {
    # DRE
    "3.01":    "Revenue",
    "3.01.01": "Operating Revenue (gross)",
    "3.01.02": "Other Revenue",
    "3.02":    "Costs",
    "3.02.01": "Cost of Goods/Services",
    "3.02.02": "Other Costs",
    "3.03":    "Gross Profit",
    "3.04":    "Operating Expenses (net)",
    "3.04.01": "Selling Expenses",
    "3.04.02": "General & Administrative",
    "3.04.03": "Losses on Receivables",
    "3.04.04": "Other Operating Income",
    "3.04.05": "Other Operating Income / Expenses",
    "3.04.06": "Other Operating Expenses",
    "3.04.07": "Equity Income",
    "3.05":    "Operating Result (EBIT)",
    "3.06":    "Financial Result",
    "3.06.01": "Financial Income",
    "3.06.02": "Financial Expenses",
    "3.07":    "Income Before Taxes (EBT)",
    "3.08":    "Income Taxes",
    "3.08.01": "Current Tax",
    "3.08.02": "Deferred Tax",
    "3.09":    "Continuing Operations — Net Result",
    "3.10":    "Discontinued Operations — Net Result",
    "3.11":    "Net Income",
    "3.11.01": "Attributable to Controlling Shareholders",
    "3.11.02": "Attributable to Non-controlling Interests",
    "3.99":    "Earnings per Share",
    # BPA
    "1":           "Total Assets",
    "1.01":        "Current Assets",
    "1.01.01":     "Cash and Equivalents",
    "1.01.02":     "Financial Investments",
    "1.01.03":     "Trade Receivables",
    "1.01.04":     "Inventories",
    "1.01.05":     "Biological Assets",
    "1.01.06":     "Recoverable Taxes",
    "1.01.07":     "Prepaid Expenses",
    "1.01.08":     "Other Current Assets",
    "1.01.09":     "Receivables — Sale of Assets",
    "1.02":        "Non-current Assets",
    "1.02.01":     "Long-term Receivables",
    "1.02.02":     "Investments",
    "1.02.03":     "Property, Plant & Equipment (PP&E)",
    "1.02.04":     "Intangible Assets",
    "1.02.05":     "Right-of-Use Assets",
    # BPP
    "2":           "Total Liabilities and Equity",
    "2.01":        "Current Liabilities",
    "2.01.01":     "Social & Labor Obligations",
    "2.01.02":     "Suppliers",
    "2.01.03":     "Tax Obligations",
    "2.01.04":     "Short-term Debt",
    "2.01.05":     "Other Current Obligations",
    "2.01.06":     "Current Provisions",
    "2.01.07":     "Liabilities — Discontinued Operations",
    "2.02":        "Non-current Liabilities",
    "2.02.01":     "Long-term Debt",
    "2.02.02":     "Other Non-current Obligations",
    "2.02.03":     "Deferred Tax Liabilities",
    "2.02.04":     "Non-current Provisions",
    "2.02.06":     "Deferred Revenue",
    "2.03":        "Equity",
    "2.03.01":     "Share Capital",
    "2.03.02":     "Capital Reserves",
    "2.03.04":     "Earnings Reserves",
    "2.03.05":     "Retained Earnings",
    "2.03.06":     "Equity Valuation Adjustments",
    "2.03.08":     "Other Comprehensive Income",
    "2.03.09":     "Non-controlling Interests",
    # DFC
    "6.01":         "Cash Flow from Operations (CFO)",
    "6.01.01":      "Cash Generated by Operations",
    "6.01.01.01":   "Net Income (DFC start)",
    "6.01.01.02":   "Depreciation & Amortization",
    "6.01.01.03":   "Depreciation & Amortization",
    "6.01.02":      "Working Capital Changes",
    "6.01.02.01":   "Δ Receivables",
    "6.01.02.02":   "Δ Inventories",
    "6.01.02.03":   "Δ Suppliers",
    "6.01.02.04":   "Δ Tax Obligations",
    "6.02":         "Cash Flow from Investing (CFI)",
    "6.02.01":      "Capex (PP&E acquisitions)",
    "6.02.02":      "Intangible Acquisitions",
    "6.02.03":      "Investments / Acquisitions",
    "6.03":         "Cash Flow from Financing (CFF)",
    "6.03.01":      "Debt Issuance",
    "6.03.02":      "Debt Repayment",
    "6.03.04":      "Dividends / Interest on Equity Paid",
    "6.04":         "Effect of FX on Cash",
    "6.05":         "Change in Cash",
    "6.05.01":      "Cash at Beginning of Period",
    "6.05.02":      "Cash at End of Period",
    # DVA
    "7.01":     "Revenue (Value Added base)",
    "7.01.01":  "Sales",
    "7.02":     "Inputs Acquired from Third Parties",
    "7.03":     "Gross Value Added",
    "7.04":     "Retentions (Depreciation)",
    "7.05":     "Net Value Added Produced",
    "7.06":     "Value Added Received in Transfer",
    "7.07":     "Value Added to Distribute",
    "7.08":     "Value Added Distribution",
    "7.08.01":  "Personnel",
    "7.08.02":  "Taxes, Fees & Contributions",
    "7.08.03":  "Third-party Capital Remuneration",
    "7.08.04":  "Own Capital Remuneration",
    # Computed (not raw)
    "6.01.01.DA": "Depreciation & Amortization",
}

_DRE_SUBTOTALS = {"3.01", "3.03", "3.05", "3.07", "3.09", "3.11"}

# Sign-role hints appended to Income Statement detail-line labels
# (WSP convention). Reflects the sign each line carries in the CVM source
# (costs/expenses are stored negative). Subtotals carry "(=)" instead.
# Lines absent from this map render with no hint (no asserted sign).
_DRE_SIGN_HINTS: dict[str, str] = {
    "3.01.01": "+", "3.01.02": "+",
    "3.02": "-", "3.02.01": "-", "3.02.02": "-",
    "3.04": "-", "3.04.01": "-", "3.04.02": "-",
    "3.04.05": "+/-", "3.04.06": "-", "3.04.07": "+/-",
    "3.06": "+/-", "3.06.01": "+", "3.06.02": "-",
    "3.08": "-", "3.08.01": "-", "3.08.02": "+/-",
    "3.10": "+/-", "3.11.01": "+/-", "3.11.02": "+/-",
}
_BPA_SUBTOTALS = {"1", "1.01", "1.02"}
_BPP_SUBTOTALS = {"2", "2.01", "2.02", "2.03"}
_DFC_SUBTOTALS = {"6.01", "6.01.01", "6.01.02", "6.02", "6.03", "6.05"}
_DVA_SUBTOTALS = {"7.03", "7.05", "7.07", "7.08"}

# Analyst spine — codes rendered on the Model sheet for each statement,
# with their indent level. A code not present in the raw data renders as
# "-" and is tracked in self._unmapped_codes for the Source / Data
# Quality block.
_DRE_SPINE: list[tuple[str, int]] = [
    ("3.01", 0), ("3.01.01", 1), ("3.01.02", 1),
    ("3.02", 0), ("3.02.01", 1), ("3.02.02", 1),
    ("3.03", 0),
    ("3.04", 0), ("3.04.01", 1), ("3.04.02", 1),
    ("3.04.05", 1), ("3.04.06", 1), ("3.04.07", 1),
    ("3.05", 0),
    ("3.06", 0), ("3.06.01", 1), ("3.06.02", 1),
    ("3.07", 0),
    ("3.08", 0), ("3.08.01", 1), ("3.08.02", 1),
    ("3.09", 0), ("3.10", 0),
    ("3.11", 0), ("3.11.01", 1), ("3.11.02", 1),
]
_BPA_SPINE: list[tuple[str, int]] = [
    ("1", 0),
    ("1.01", 1),
    ("1.01.01", 2), ("1.01.02", 2), ("1.01.03", 2),
    ("1.01.04", 2), ("1.01.05", 2), ("1.01.06", 2),
    ("1.01.07", 2), ("1.01.08", 2),
    ("1.02", 1),
    ("1.02.01", 2), ("1.02.02", 2), ("1.02.03", 2),
    ("1.02.04", 2), ("1.02.05", 2),
]
_BPP_SPINE: list[tuple[str, int]] = [
    ("2", 0),
    ("2.01", 1),
    ("2.01.01", 2), ("2.01.02", 2), ("2.01.03", 2),
    ("2.01.04", 2), ("2.01.05", 2), ("2.01.06", 2),
    ("2.02", 1),
    ("2.02.01", 2), ("2.02.02", 2), ("2.02.03", 2),
    ("2.02.04", 2), ("2.02.06", 2),
    ("2.03", 1),
    ("2.03.01", 2), ("2.03.02", 2), ("2.03.04", 2),
    ("2.03.05", 2), ("2.03.06", 2), ("2.03.08", 2),
    ("2.03.09", 2),
]
_DFC_SPINE: list[tuple[str, int]] = [
    ("6.01", 0),
    ("6.01.01", 1),
    ("6.01.01.01", 2), ("6.01.01.03", 2),
    ("6.01.02", 1),
    ("6.01.02.01", 2), ("6.01.02.02", 2),
    ("6.01.02.03", 2), ("6.01.02.04", 2),
    ("6.02", 0),
    ("6.02.01", 1), ("6.02.02", 1), ("6.02.03", 1),
    ("6.03", 0),
    ("6.03.01", 1), ("6.03.02", 1), ("6.03.04", 1),
    ("6.04", 0),
    ("6.05", 0),
    ("6.05.01", 1), ("6.05.02", 1),
]
_DVA_SPINE: list[tuple[str, int]] = [
    ("7.01", 0), ("7.01.01", 1),
    ("7.02", 0),
    ("7.03", 0),
    ("7.04", 0),
    ("7.05", 0),
    ("7.06", 0),
    ("7.07", 0),
    ("7.08", 0),
    ("7.08.01", 1), ("7.08.02", 1),
    ("7.08.03", 1), ("7.08.04", 1),
]


# ──────────────────────────────────────────────────────────────────────────────
# Period helpers
# ──────────────────────────────────────────────────────────────────────────────
_ANNUAL_RX = re.compile(r"^(?:19|20)\d{2}$")
_QUARTER_RX = re.compile(r"^([1-4])[QT](\d{2,4})$", flags=re.IGNORECASE)


def _is_annual_period(label: str) -> bool:
    return bool(_ANNUAL_RX.match(str(label).strip()))


def _parse_quarter(label: str) -> Optional[tuple[int, int]]:
    """Return (year, quarter) or None for non-quarter labels."""
    m = _QUARTER_RX.match(str(label).strip())
    if not m:
        return None
    q = int(m.group(1))
    y_str = m.group(2)
    year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
    return (year, q)


def _period_sort_key(p: str) -> tuple[int, int, int]:
    """Sort periods chronologically: 1Q24, 2Q24, ..., 4Q24, 2024, 1Q25, ..."""
    s = str(p).strip()
    if _is_annual_period(s):
        return (int(s), 5, 0)
    parsed = _parse_quarter(s)
    if parsed is not None:
        year, q = parsed
        return (year, q, 1)
    return (9999, 9, 9)


def _period_end_date(label: str) -> Optional[date]:
    """Map a period label to its end-of-period date.

    Examples::

        "1Q25" -> 2025-03-31
        "2Q25" -> 2025-06-30
        "3Q25" -> 2025-09-30
        "4Q25" -> 2025-12-31
        "2024" -> 2024-12-31
    """
    s = str(label).strip()
    if _is_annual_period(s):
        return date(int(s), 12, 31)
    parsed = _parse_quarter(s)
    if parsed is None:
        return None
    year, q = parsed
    if q == 1:
        return date(year, 3, 31)
    if q == 2:
        return date(year, 6, 30)
    if q == 3:
        return date(year, 9, 30)
    return date(year, 12, 31)


def _pick_model_periods(
    all_periods: list[str],
    annuals: int = 5,
    quarters_per_year: int = 4,
) -> list[str]:
    """Select the analyst window: last N annuals + their quarters.

    Quarters whose year matches one of the selected annuals are kept (up
    to ``quarters_per_year`` per annual year). The combined set is
    sorted chronologically so the result is the interleaved layout
    ``1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ..., 4Q25, 2025``.
    """
    annual_periods = sorted(
        [p for p in all_periods if _is_annual_period(p)],
        key=_period_sort_key,
    )
    selected_annuals = annual_periods[-annuals:] if annuals > 0 else []
    selected_years = {int(a) for a in selected_annuals}

    quarter_buckets: dict[int, list[str]] = {}
    for p in all_periods:
        parsed = _parse_quarter(p)
        if parsed is None:
            continue
        year, _ = parsed
        if year in selected_years:
            quarter_buckets.setdefault(year, []).append(p)

    selected_quarters: list[str] = []
    for year, qs in quarter_buckets.items():
        qs_sorted = sorted(qs, key=_period_sort_key)
        selected_quarters.extend(qs_sorted[-quarters_per_year:] if quarters_per_year > 0 else [])

    combined = list(set(selected_annuals) | set(selected_quarters))
    combined.sort(key=_period_sort_key)
    return combined


# ──────────────────────────────────────────────────────────────────────────────
# Numeric helpers
# ──────────────────────────────────────────────────────────────────────────────
_MODEL_SCALE_DIVISOR = 1000.0   # CVM stores R$ mil; Model shows R$ mm


def _is_safe_number(value) -> bool:
    """True iff value is a finite real number safe for write_number()."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
    return False


def _scaled(value) -> Optional[float]:
    """Scale a raw R$ mil value into R$ mm. Return None if not writable."""
    if not _is_safe_number(value):
        return None
    return float(value) / _MODEL_SCALE_DIVISOR


# ──────────────────────────────────────────────────────────────────────────────
# Public filename helpers
# ──────────────────────────────────────────────────────────────────────────────
def build_excel_file_stem(
    company_info: dict,
    *,
    generated_at: datetime | None = None,
    statement_type: str | None = None,
) -> str:
    timestamp = generated_at or datetime.now()
    ticker = company_info.get("ticker_b3") or f"cvm{company_info.get('cd_cvm', '')}"
    safe_ticker = str(ticker).replace(" ", "_").replace("/", "-")
    stem = f"{safe_ticker}_{timestamp.strftime('%Y%m%d')}"
    if statement_type:
        stem = f"{safe_ticker}_{statement_type}_{timestamp.strftime('%Y%m%d')}"
    return stem


def build_excel_filename(
    company_info: dict,
    *,
    generated_at: datetime | None = None,
    statement_type: str | None = None,
) -> str:
    return f"{build_excel_file_stem(company_info, generated_at=generated_at, statement_type=statement_type)}.xlsx"


# ──────────────────────────────────────────────────────────────────────────────
# Exporter
# ──────────────────────────────────────────────────────────────────────────────
class ExcelExportError(RuntimeError):
    """Raised when the post-write validator finds error cells."""


class ExcelExporter:
    """Generates the analyst-ready company workbook.

    Parameters
    ----------
    company_info : dict
        Output of ``CVMReadService.get_company_info_dict(cd_cvm)``.
    statements : dict[str, pd.DataFrame]
        Map of ``stmt_type -> wide pivot``.
    kpis_df : pd.DataFrame
        Output of ``KPIBundle.quarterly_dataframe()``.
    extra_sheets : list[str], optional
        Extra statement types to include (e.g. ``["DVA"]``).
    statement_type : str, optional
        If set, the workbook is scoped to a single statement.
    period_window : (int, int), optional
        ``(annuals, quarters_per_year)``. Defaults to ``(5, 4)`` which
        produces the interleaved 5-year + 4-quarter Equatorial layout
        (~25 columns).
    """

    def __init__(
        self,
        company_info: dict,
        statements: dict[str, pd.DataFrame],
        kpis_df: pd.DataFrame,
        extra_sheets: Optional[list[str]] = None,
        statement_type: Optional[str] = None,
        period_window: tuple[int, int] = DEFAULT_PERIOD_WINDOW,
    ):
        self.info = company_info or {}
        self.stmts = statements or {}
        self.kpis = kpis_df if kpis_df is not None else pd.DataFrame()
        self.extra = extra_sheets or []
        self.statement_type = statement_type
        self.period_window = period_window
        self._wb: Optional[xlsxwriter.Workbook] = None
        self._fmt: dict = {}
        # raw sheet layouts captured during write so the model sheet can
        # build formula references back into them
        self._raw_index: dict[str, dict] = {}
        # model period window (selected during _write_model_sheet)
        self._model_periods: list[str] = []
        # row tracker for Model sheet so checks/KPIs can reference cells
        self._model_rows: dict[str, int] = {}
        # spine codes that did not resolve to a raw row, per statement —
        # populated during _write_model_section and surfaced in the
        # Source / Data Quality block + README
        self._unmapped_codes: dict[str, list[str]] = {}
        # STANDARD_NAME index per statement for fallback resolution
        self._raw_std_name_index: dict[str, dict[str, int]] = {}
        # D&A resolution status — set in _write_model_da_and_ebitda and
        # surfaced as a Checks row (EBITDA depends on it).
        self._da_resolved: bool = False
        self._da_cd_conta: Optional[str] = None

    # ── public API ────────────────────────────────────────────────────────
    def export(self, statement_type: Optional[str] = None) -> bytes:
        stmt_t = statement_type or self.statement_type
        buf = io.BytesIO()
        # nan_inf_to_errors retained as a belt-and-braces safety net; the
        # _is_safe_number guard plus the post-write validator should mean
        # nothing reaches Excel's error encoding in normal operation.
        self._wb = xlsxwriter.Workbook(
            buf, {"in_memory": True, "nan_inf_to_errors": True}
        )
        self._build_formats()

        if stmt_t:
            # Scoped single-statement export — minimal workbook.
            self._write_raw_statement(stmt_t)
            self._write_metadata_sheet(scope=stmt_t)
        else:
            # Full export. Raw sheets are written first so the Model sheet
            # can reference their final row coordinates via formulas.
            for stype in ("DRE", "BPA", "BPP", "DFC"):
                self._write_raw_statement(stype)
            for stype in ("DVA", "DMPL"):
                if stype in self.stmts and not self.stmts[stype].empty:
                    self._write_raw_statement(stype)
            self._write_raw_kpi_sheet()
            self._write_metadata_sheet(scope=None)
            # Visible analyst sheets are written last so they appear at
            # the top of the workbook (xlsxwriter ordering).
            self._write_readme_sheet()
            self._write_model_sheet()
            self._reorder_visible_sheets()

        self._wb.close()
        payload = buf.getvalue()

        # Post-write validator — catches any error string that slipped
        # through (e.g. malformed formula references).
        if not stmt_t:
            self._validate_no_errors(payload)

        return payload

    # ── formats ───────────────────────────────────────────────────────────
    def _build_formats(self):
        wb = self._wb

        def fmt(**kw):
            return wb.add_format(kw)

        base = {"font_name": "Aptos Narrow", "font_size": 11}
        base_small = {"font_name": "Aptos Narrow", "font_size": 10}

        # Number formats: negatives in black parentheses (WSP financial
        # modeling convention — red is reserved for warnings/checks, not
        # ordinary negatives). Zero falls back to "-".
        num_fmt = "#,##0;(#,##0);-"
        num_fmt_dec = "#,##0.0;(#,##0.0);-"
        pct_fmt = "0.0%;(0.0%);-"
        ratio_fmt = '0.00"x";(0.00"x");-'
        date_fmt = "dd/mm/yy"

        self._fmt = {
            # ── conventions block ────────────────────────────────────────
            "conv_header":  fmt(**base, bold=True, italic=True,
                                font_color=PALETTE["blue_dark"]),
            "conv_input":   fmt(**base_small, font_color=PALETTE["blue_input"]),
            "conv_output":  fmt(**base_small, font_color=PALETTE["black"],
                                bg_color=PALETTE["orange_fill"]),
            "conv_linked":  fmt(**base_small, font_color=PALETTE["green_linked"]),
            "conv_calc":    fmt(**base_small, font_color=PALETTE["black"]),
            "conv_check":   fmt(**base_small, italic=True,
                                font_color=PALETTE["green_linked"]),
            "conv_note":    fmt(**base_small, italic=True,
                                font_color=PALETTE["gray_text"]),
            "conv_warning": fmt(**base_small, bold=True,
                                font_color=PALETTE["red_warn"]),

            # ── title / subtitle ──────────────────────────────────────────
            "title": fmt(font_name="Aptos Narrow", font_size=16, bold=True,
                          font_color=PALETTE["blue_dark"],
                          top=2, bottom=2,
                          top_color=PALETTE["blue_dark"],
                          bottom_color=PALETTE["blue_dark"],
                          valign="vcenter"),
            "subtitle": fmt(font_name="Aptos Narrow", font_size=11,
                             italic=True, font_color=PALETTE["gray_text"]),

            # ── company info block ────────────────────────────────────────
            "info_label": fmt(**base, bold=True,
                               font_color=PALETTE["blue_dark"]),
            "info_value": fmt(**base, font_color=PALETTE["black"]),

            # ── period header (3 rows) ────────────────────────────────────
            "period_label":      fmt(**base, bold=True,
                                       font_color=PALETTE["blue_dark"],
                                       top=1, bottom=1),
            "period_q":          fmt(**base, bold=True, align="center",
                                       font_color=PALETTE["blue_dark"],
                                       top=1),
            "period_y":          fmt(**base, bold=True, align="center",
                                       font_color=PALETTE["blue_dark"],
                                       top=1, bg_color=PALETTE["annual_fill"]),
            "period_date":       fmt(**base_small, align="center",
                                       num_format=date_fmt,
                                       font_color=PALETTE["gray_text"]),
            "period_date_y":     fmt(**base_small, align="center",
                                       num_format=date_fmt,
                                       font_color=PALETTE["gray_text"],
                                       bg_color=PALETTE["annual_fill"]),
            "period_type":       fmt(**base_small, italic=True, align="center",
                                       font_color=PALETTE["gray_text"],
                                       bottom=1),
            "period_type_y":     fmt(**base_small, italic=True, align="center",
                                       font_color=PALETTE["gray_text"],
                                       bottom=1, bg_color=PALETTE["annual_fill"]),

            # ── section heading ───────────────────────────────────────────
            "section_heading": fmt(font_name="Aptos Narrow", font_size=13,
                                    bold=True, font_color=PALETTE["blue_dark"],
                                    top=2, bottom=2,
                                    top_color=PALETTE["blue_dark"],
                                    bottom_color=PALETTE["blue_dark"]),

            # ── statement body — linked (green) and calc (black) ─────────
            "label_body":       fmt(**base),
            "label_indent":     fmt(**base),  # same — indent via spaces
            "label_subtotal":   fmt(**base, bold=True, top=1),
            "num_linked":       fmt(**base, num_format=num_fmt,
                                     align="right",
                                     font_color=PALETTE["green_linked"]),
            "num_linked_y":     fmt(**base, num_format=num_fmt,
                                     align="right",
                                     font_color=PALETTE["green_linked"],
                                     bg_color=PALETTE["annual_fill"]),
            "num_calc":         fmt(**base, num_format=num_fmt,
                                     align="right",
                                     font_color=PALETTE["black"]),
            "num_calc_y":       fmt(**base, num_format=num_fmt,
                                     align="right",
                                     font_color=PALETTE["black"],
                                     bg_color=PALETTE["annual_fill"]),
            "num_subtotal":     fmt(**base, bold=True, num_format=num_fmt,
                                     align="right", top=1),
            "num_subtotal_y":   fmt(**base, bold=True, num_format=num_fmt,
                                     align="right", top=1,
                                     bg_color=PALETTE["annual_fill"]),

            # ── KPI numbers ──────────────────────────────────────────────
            "kpi_label":   fmt(**base, italic=True,
                                font_color=PALETTE["black"]),
            "kpi_pct":     fmt(**base, num_format=pct_fmt, align="right"),
            "kpi_pct_y":   fmt(**base, num_format=pct_fmt, align="right",
                                bg_color=PALETTE["annual_fill"]),
            "kpi_ratio":   fmt(**base, num_format=ratio_fmt, align="right"),
            "kpi_ratio_y": fmt(**base, num_format=ratio_fmt, align="right",
                                bg_color=PALETTE["annual_fill"]),
            "kpi_num":     fmt(**base, num_format=num_fmt_dec, align="right"),
            "kpi_num_y":   fmt(**base, num_format=num_fmt_dec, align="right",
                                bg_color=PALETTE["annual_fill"]),

            # ── checks ────────────────────────────────────────────────────
            "check_label":   fmt(**base),
            "check_ok":      fmt(**base, font_color=PALETTE["green_linked"],
                                  bold=True),
            "check_warning": fmt(**base, font_color=PALETTE["amber"],
                                  bold=True),
            "check_error":   fmt(**base, font_color=PALETTE["red_warn"],
                                  bold=True),
            "check_value":   fmt(**base, num_format=num_fmt, align="right"),

            # ── source / data quality ─────────────────────────────────────
            "source_label": fmt(**base, bold=True,
                                  font_color=PALETTE["blue_dark"]),
            "source_value": fmt(**base, font_color=PALETTE["black"]),
            "source_note":  fmt(**base, italic=True,
                                  font_color=PALETTE["gray_text"]),
            "source_warning": fmt(**base, italic=True,
                                    font_color=PALETTE["red_warn"]),

            # ── raw sheet formats (compact, monochrome) ──────────────────
            "raw_header":     fmt(**base_small, bold=True,
                                    bg_color=PALETTE["blue_dark"],
                                    font_color="#FFFFFF", align="left"),
            "raw_header_num": fmt(**base_small, bold=True,
                                    bg_color=PALETTE["blue_dark"],
                                    font_color="#FFFFFF", align="center"),
            "raw_text":       fmt(**base_small),
            "raw_text_sub":   fmt(**base_small, bold=True),
            "raw_num":        fmt(**base_small, num_format=num_fmt,
                                    align="right"),
            "raw_num_sub":    fmt(**base_small, bold=True, num_format=num_fmt,
                                    align="right"),
        }

    # ── raw statement sheets ──────────────────────────────────────────────
    def _write_raw_statement(self, stmt_type: str):
        df = self.stmts.get(stmt_type)
        if df is None or df.empty:
            return
        sheet_name = _LEGACY_TO_RAW.get(stmt_type, f"raw_{stmt_type}")
        ws = self._wb.add_worksheet(sheet_name)
        subtotals = _stmt_subtotals(stmt_type)

        id_cols = [c for c in ("CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE")
                   if c in df.columns]
        period_cols = [c for c in df.columns if c not in id_cols]
        all_cols = id_cols + period_cols

        col_widths = {
            "CD_CONTA":      14,
            "DS_CONTA":      44,
            "STANDARD_NAME": 34,
            "LINE_ID_BASE":  20,
        }

        ws.set_row(0, 22)
        for c_idx, col in enumerate(all_cols):
            ws.set_column(c_idx, c_idx, col_widths.get(col, 12))
            ws.write(0, c_idx, col,
                     self._fmt["raw_header"] if col in id_cols
                     else self._fmt["raw_header_num"])

        # Index: CD_CONTA -> 1-indexed row number in the raw sheet so the
        # Model sheet can build cross-sheet formula references.
        # Also build a STANDARD_NAME -> row index for fallback mapping.
        cd_to_row: dict[str, int] = {}
        std_name_to_row: dict[str, int] = {}
        period_to_col: dict[str, int] = {}
        for c_idx, p in enumerate(period_cols, start=len(id_cols)):
            period_to_col[str(p)] = c_idx

        for r_idx, (_, row) in enumerate(df.iterrows(), start=1):
            cd = str(row.get("CD_CONTA", "")).strip()
            std = str(row.get("STANDARD_NAME", "") or "").strip()
            is_sub = cd in subtotals
            cd_to_row[cd] = r_idx + 1  # 1-indexed Excel row
            if std and std not in std_name_to_row:
                std_name_to_row[std] = r_idx + 1

            ws.set_row(r_idx, 15)
            for c_idx, col in enumerate(all_cols):
                val = row[col]
                if col in id_cols:
                    text = "" if pd.isna(val) else str(val)
                    ws.write(r_idx, c_idx, text,
                             self._fmt["raw_text_sub"] if is_sub
                             else self._fmt["raw_text"])
                    continue
                # period numeric — keep raw R$ mil (no scaling) on raw
                # sheets so analysts can audit the source values.
                if not _is_safe_number(val):
                    ws.write_blank(r_idx, c_idx, None,
                                   self._fmt["raw_num_sub"] if is_sub
                                   else self._fmt["raw_num"])
                else:
                    ws.write_number(r_idx, c_idx, float(val),
                                    self._fmt["raw_num_sub"] if is_sub
                                    else self._fmt["raw_num"])

        ws.freeze_panes(1, min(2, len(id_cols)))
        ws.hide_gridlines(2)
        # Auto-filter for analyst convenience.
        ws.autofilter(0, 0, len(df), len(all_cols) - 1)
        ws.hide()  # raw sheets hidden by default

        self._raw_index[stmt_type] = {
            "sheet_name": sheet_name,
            "cd_to_row": cd_to_row,
            "std_name_to_row": std_name_to_row,
            "period_to_col": period_to_col,
            "id_cols_count": len(id_cols),
            "n_rows": len(df),
        }

    # ── raw KPI sheet ─────────────────────────────────────────────────────
    def _write_raw_kpi_sheet(self):
        ws = self._wb.add_worksheet(RAW_KPI_SHEET)
        ws.hide_gridlines(2)
        kpis = self.kpis
        if kpis is None or kpis.empty:
            ws.write(0, 0, "KPIs not available", self._fmt["source_note"])
            ws.hide()
            return

        meta_cols = ["CATEGORIA", "KPI_ID", "KPI_NOME", "FORMULA",
                     "IS_PLACEHOLDER", "FORMAT_TYPE", "HIGHER_IS_BETTER",
                     "UNIDADE", "DELTA_YOY", "DELTA_YOY_PCT"]
        present_meta = [c for c in meta_cols if c in kpis.columns]
        period_cols = [c for c in kpis.columns if c not in meta_cols]
        all_cols = present_meta + period_cols

        col_widths = {
            "CATEGORIA": 18, "KPI_ID": 14, "KPI_NOME": 32,
            "FORMULA": 40, "FORMAT_TYPE": 12, "UNIDADE": 10,
        }
        for c_idx, col in enumerate(all_cols):
            ws.set_column(c_idx, c_idx, col_widths.get(col, 12))
            ws.write(0, c_idx, str(col), self._fmt["raw_header"])

        for r_idx, (_, kpi_row) in enumerate(kpis.iterrows(), start=1):
            for c_idx, col in enumerate(all_cols):
                v = kpi_row.get(col)
                if col in period_cols and _is_safe_number(v):
                    ws.write_number(r_idx, c_idx, float(v), self._fmt["raw_num"])
                elif v is None or (isinstance(v, float) and not math.isfinite(v)) or pd.isna(v):
                    ws.write_blank(r_idx, c_idx, None, self._fmt["raw_text"])
                else:
                    ws.write(r_idx, c_idx, str(v), self._fmt["raw_text"])

        ws.freeze_panes(1, len(present_meta))
        ws.autofilter(0, 0, len(kpis), len(all_cols) - 1)
        ws.hide()

    # ── metadata sheet ────────────────────────────────────────────────────
    def _write_metadata_sheet(self, scope: Optional[str] = None):
        ws = self._wb.add_worksheet(METADATA_SHEET)
        ws.set_column("A:A", 30)
        ws.set_column("B:B", 60)
        ws.set_column("C:C", 24)
        ws.set_row(0, 20)
        ws.write(0, 0, "Field",  self._fmt["raw_header"])
        ws.write(0, 1, "Value",  self._fmt["raw_header"])
        ws.write(0, 2, "Notes",  self._fmt["raw_header"])

        info = self.info
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stmts_present = scope or ", ".join(
            k for k in ("DRE", "BPA", "BPP", "DFC", "DVA", "DMPL")
            if k in self.stmts and not self.stmts[k].empty
        )

        rows = [
            ("Company",            str(info.get("company_name") or "—"), ""),
            ("CVM code",           str(info.get("cd_cvm") or "—"),       ""),
            ("Ticker B3",          str(info.get("ticker_b3") or "—"),    ""),
            ("CNPJ",               str(info.get("cnpj") or "—"),         ""),
            ("CVM sector",         str(info.get("setor_cvm") or "—"),    ""),
            ("Analytic sector",    str(info.get("setor_analitico") or "—"), ""),
            ("Statements present", stmts_present, "Raw sheets in this workbook"),
            ("Generated at",       now_str, ""),
            ("Source",             "CVM — dados.cvm.gov.br", "DFP/ITR filings"),
            ("App",                f"CVMAnalytics {_APP_VERSION}", ""),
            ("CVM scale",          "R$ mil (thousands)",
                                   "Most companies report in thousands of BRL"),
            ("Model scale",        "R$ mm (millions)",
                                   "Model sheet divides CVM source by 1,000"),
            ("Sign convention",    "Costs / expenses appear negative in CVM source", ""),
            ("D&A on DFC",         "CD_CONTA 6.01.01.* filtered by 'depreci' (excludes financial amortisation)",
                                   "EBITDA = EBIT + D&A"),
            ("Window — annual",    str(self.period_window[0]), ""),
            ("Window — quarters/year", str(self.period_window[1]), ""),
        ]
        for r_idx, (k, v, n) in enumerate(rows, start=1):
            ws.set_row(r_idx, 16)
            ws.write(r_idx, 0, k, self._fmt["source_label"])
            ws.write(r_idx, 1, v, self._fmt["source_value"])
            ws.write(r_idx, 2, n, self._fmt["source_note"])
        ws.freeze_panes(1, 0)
        ws.hide_gridlines(2)
        ws.hide()

    # ── README sheet ──────────────────────────────────────────────────────
    def _write_readme_sheet(self):
        ws = self._wb.add_worksheet(README_SHEET)
        ws.set_column("A:A", 2)
        ws.set_column("B:B", 30)
        ws.set_column("C:C", 80)
        ws.set_row(1, 28)
        ws.write(1, 1, "README", self._fmt["title"])

        info = self.info
        company = str(info.get("company_name") or "—")
        ws.write(2, 1, f"Workbook for {company}", self._fmt["subtitle"])

        # Build the dynamic raw-sheet list — only those actually written.
        raw_sheets_present = sorted(
            self._raw_index[k]["sheet_name"]
            for k in self._raw_index if "sheet_name" in self._raw_index[k]
        )
        if "raw_KPIs" not in raw_sheets_present and not self.kpis.empty:
            raw_sheets_present.append(RAW_KPI_SHEET)
        if METADATA_SHEET not in raw_sheets_present:
            raw_sheets_present.append(METADATA_SHEET)
        dva_available = "DVA" in self.stmts and not self.stmts["DVA"].empty
        dva_status_line = ("present (raw_DVA)" if dva_available
                           else "**not** present (no DVA in source data)")

        checks_present = (
            "Balance Sheet Tie, Cash Flow Tie, Net Income Tie, "
            "Period Completeness, Critical Line Availability, "
            "DVA Availability, Formula Error Scan."
        )

        section_rows = [
            ("Main sheet",
             "`Model` — analyst-curated single sheet with Income Statement, "
             "Balance Sheet, Cash Flow Statement, Value Added Statement "
             "(or explicit unavailability note), KPIs, Checks, and Source / "
             "Data Quality blocks."),
            ("Period window",
             f"Annual: last {self.period_window[0]} fiscal years. "
             f"Quarterly: up to {self.period_window[1]} quarters per included "
             "annual year, interleaved chronologically "
             "(e.g. 1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ...)."),
            ("Units",
             "Model sheet: R$ mm (millions). CVM source: R$ mil (thousands); "
             "divided by 1,000 in the Model view. Raw sheets keep R$ mil."),
            ("Hidden sheets",
             "Right-click any visible sheet tab → Unhide… to audit. "
             "Sheets actually present in this workbook: "
             + ", ".join(raw_sheets_present) + "."),
            ("DVA status",
             f"DVA is {dva_status_line} for this company."),
            ("Conventions",
             "Linked values are green (formula link into raw_*); calculated "
             "values are black (formula in cell); negative numbers appear "
             "in black parentheses (red is reserved for warnings/checks); "
             "zero and missing values both display "
             "as `-` (raw missing lines are tracked in Source / Data Quality "
             "so the analyst can distinguish unmapped from numerically zero)."),
            ("Checks",
             "Checks rendered on the Model sheet: " + checks_present
             + " The exporter also runs a post-write sweep that fails the "
             "export if any cell contains an Excel error code or any merged "
             "cell range."),
            ("Conventions block",
             "Rows 3–9 hold the conventions legend. They ship grouped and "
             "hidden by default — click the outline `+` in the left margin "
             "to expand."),
            ("Limitations",
             "No forecast periods, no LTM column, no per-share / share-count / "
             "market-price rows, no sector-specific KPIs in this release. "
             "Full CVM history and the full account tree are available via "
             "the hidden raw_* sheets."),
        ]
        for r_idx, (label, body) in enumerate(section_rows, start=4):
            ws.set_row(r_idx, 30)
            ws.write(r_idx, 1, label, self._fmt["info_label"])
            ws.write(r_idx, 2, body, self._fmt["source_value"])

        ws.hide_gridlines(2)
        ws.freeze_panes(2, 0)

    # ── Model sheet — main analyst view ───────────────────────────────────
    def _write_model_sheet(self):
        ws = self._wb.add_worksheet(MODEL_SHEET)
        ws.hide_gridlines(2)
        f = self._fmt
        info = self.info

        # Period window
        all_periods: set[str] = set()
        for df in self.stmts.values():
            if df is None or df.empty:
                continue
            id_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
            all_periods.update(str(c) for c in df.columns if c not in id_cols)
        periods = _pick_model_periods(
            sorted(all_periods, key=_period_sort_key),
            annuals=self.period_window[0],
            quarters_per_year=self.period_window[1],
        )
        self._model_periods = periods

        # Columns: A margin, B labels, C gap, D+ periods
        ws.set_column(0, 0, 2)
        ws.set_column(1, 1, 52)
        ws.set_column(2, 2, 2.5)
        for idx in range(3, 3 + max(len(periods), 1)):
            ws.set_column(idx, idx, 10)

        # Conventions block (rows 2-8 0-indexed = rows 3:9 1-indexed)
        # Grouped + hidden by default so the analyst-facing surface
        # starts visually at the title row. Excel shows an outline `+`
        # to expand the legend on demand.
        ws.write(1, 1, "Conventions", f["conv_header"])
        ws.write(2, 3, "Input",       f["conv_input"])
        ws.write(3, 3, "Output",      f["conv_output"])
        ws.write(4, 3, "Linked",      f["conv_linked"])
        ws.write(5, 3, "Calculation", f["conv_calc"])
        ws.write(6, 3, "Check (OK)",  f["conv_check"])
        ws.write(7, 3, "Note",        f["conv_note"])
        ws.write(8, 3, "Warning",     f["conv_warning"])
        ws.write(8, 4, "negatives shown as (123)", f["conv_note"])
        for r in range(2, 9):  # 0-indexed rows 2..8 = 1-indexed rows 3..9
            ws.set_row(r, 14, None, {"level": 1, "hidden": True})
        # Outline summary symbols above for the conventions group.
        ws.outline_settings(visible=True, symbols_below=False,
                             symbols_right=True, auto_style=False)

        # Title + subtitle — single-cell, NO merging (forbidden by spec).
        company_name = str(info.get("company_name") or "—")
        ws.set_row(10, 26)
        ws.write(10, 1, f"Financial Statement Model — {company_name}",
                 f["title"])
        # Repeat the title border style across the row range so the
        # visual band continues without merging cells.
        title_last_col = max(4, 2 + len(periods))
        for c_idx in range(2, title_last_col + 1):
            ws.write_blank(10, c_idx, None, f["title"])
        ws.write(11, 1, "R$ mm except per share and where indicated",
                 f["subtitle"])

        # Company info block (rows 14:22 1-indexed, 13-21 0-indexed)
        # Derive latest_year from the actual period window if the
        # company_info dict did not carry it. Same fallback for the
        # latest quarter.
        latest_year = info.get("latest_year")
        if not latest_year or str(latest_year) in ("—", "-", ""):
            annual_ps = [p for p in periods if _is_annual_period(p)]
            latest_year = annual_ps[-1] if annual_ps else "—"
        latest_q = "—"
        for p in reversed(periods):
            if _parse_quarter(p) is not None:
                latest_q = p
                break
        rows_info = [
            ("Company name",       company_name),
            ("Ticker",             str(info.get("ticker_b3") or "—")),
            ("CVM code",           str(info.get("cd_cvm") or "—")),
            ("CNPJ",               str(info.get("cnpj") or "—")),
            ("GICS sector",        str(info.get("setor_analitico") or "—")),
            ("CVM sector",         str(info.get("setor_cvm") or "—")),
            ("Latest fiscal year", str(latest_year)),
            ("Latest quarter",     str(latest_q)),
            ("Period window",
             f"{self.period_window[0]} annuals × up to {self.period_window[1]} quarters/year (interleaved)"),
        ]
        # Company info block ships grouped + hidden by default (product
        # decision): the analyst surface starts at the period header. The
        # outline "+" in the left margin expands it (Excel rows 13–22).
        ws.set_row(12, 14, None, {"level": 1, "hidden": True})  # spacer (Excel 13)
        for i, (label, value) in enumerate(rows_info):
            r = 13 + i
            ws.set_row(r, 14, None, {"level": 1, "hidden": True})
            ws.write(r, 1, label, f["info_label"])
            ws.write(r, 3, value, f["info_value"])

        # Period header — 3 rows (label / date / type)
        header_row = 23
        ws.set_row(header_row, 18)
        ws.write(header_row, 1, "Period", f["period_label"])
        ws.set_row(header_row + 1, 14)
        ws.write(header_row + 1, 1, "Period end date", f["period_label"])
        ws.set_row(header_row + 2, 14)
        ws.write(header_row + 2, 1, "Period type", f["period_label"])

        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            ws.write(header_row, c_idx, str(p),
                     f["period_y"] if is_y else f["period_q"])
            end_date = _period_end_date(p)
            if end_date is not None:
                ws.write_datetime(header_row + 1, c_idx,
                                  datetime(end_date.year, end_date.month,
                                           end_date.day),
                                  f["period_date_y"] if is_y else f["period_date"])
            else:
                ws.write_blank(header_row + 1, c_idx, None,
                               f["period_date_y"] if is_y else f["period_date"])
            ws.write(header_row + 2, c_idx,
                     "Annual" if is_y else "Quarter",
                     f["period_type_y"] if is_y else f["period_type"])

        ws.freeze_panes(header_row + 3, 3)

        cur = header_row + 4

        # Section: Income Statement
        cur = self._write_model_section(
            ws, cur, periods,
            heading="Income Statement",
            stmt_type="DRE",
            spine=_DRE_SPINE,
            subtotal_codes=_DRE_SUBTOTALS,
            sign_hints=_DRE_SIGN_HINTS,
        )

        # Computed: EBITDA and D&A
        cur = self._write_model_da_and_ebitda(ws, cur, periods)

        # Section: Balance Sheet
        cur = self._write_model_balance_sheet(ws, cur, periods)

        # Section: Cash Flow Statement
        cur = self._write_model_section(
            ws, cur, periods,
            heading="Cash Flow Statement",
            stmt_type="DFC",
            spine=_DFC_SPINE,
            subtotal_codes=_DFC_SUBTOTALS,
        )

        # Computed: FCF = CFO + Capex (Capex is negative in CVM source)
        cur = self._write_model_fcf(ws, cur, periods)

        # Section: Value Added Statement (DVA) — always visible. If the
        # company does not file DVA, render the heading and a single
        # warning note so the analyst sees it explicitly.
        dva_available = "DVA" in self.stmts and not self.stmts["DVA"].empty
        if dva_available:
            cur = self._write_model_section(
                ws, cur, periods,
                heading="Value Added Statement",
                stmt_type="DVA",
                spine=_DVA_SPINE,
                subtotal_codes=_DVA_SUBTOTALS,
            )
        else:
            cur = self._write_section_heading(ws, cur, "Value Added Statement")
            ws.set_row(cur, 16)
            ws.write(cur, 1,
                     "DVA unavailable in current export pipeline / "
                     "company data.",
                     f["source_warning"])
            cur += 2

        # KPIs
        cur = self._write_model_kpis(ws, cur, periods)

        # Checks
        cur = self._write_model_checks(ws, cur, periods, dva_available)

        # Source / Data Quality
        cur = self._write_model_source(ws, cur, periods, dva_available)

        # Print setup (carried over from v0.18.3)
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(0, header_row + 2)
        ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        ws.set_header(f"&L{MODEL_SHEET} &R{company_name}")
        ws.set_footer("&LCVMAnalytics &CPage &P of &N &R&D")
        ws.print_area(0, 0, cur, max(3, 2 + len(periods)))

    def _write_section_heading(self, ws, row: int, label: str) -> int:
        ws.set_row(row, 22)
        ws.write(row, 1, label, self._fmt["section_heading"])
        # Apply the section-heading border style across the same range
        # without merging cells (the spec forbids merged cells).
        for c_idx in range(2, max(3, 3 + len(self._model_periods))):
            ws.write_blank(row, c_idx, None, self._fmt["section_heading"])
        return row + 2

    def _resolve_raw_row(self, stmt_type: str, code: str) -> Optional[int]:
        """Look up the 1-indexed Excel row in the raw sheet for a spine
        code. Resolution order:
            1. exact CD_CONTA match
            2. STANDARD_NAME (mapped canonical name) match
            3. None -> caller renders "-" and tracks as unmapped.
        """
        idx = self._raw_index.get(stmt_type)
        if idx is None:
            return None
        row = idx["cd_to_row"].get(code)
        if row is not None:
            return row
        std_name = _MODEL_LINE_LABELS.get(code)
        if std_name:
            return idx["std_name_to_row"].get(std_name)
        return None

    def _write_model_section(
        self,
        ws,
        start_row: int,
        periods: list[str],
        *,
        heading: str,
        stmt_type: str,
        spine: list[tuple[str, int]],
        subtotal_codes: set[str],
        sign_hints: Optional[dict[str, str]] = None,
    ) -> int:
        """Render a statement section on the Model sheet, iterating the
        analyst spine (list of (CD_CONTA, indent_level)). Codes that
        don't resolve in the raw data render as ``-`` and are tracked in
        ``self._unmapped_codes[stmt_type]`` for the Source / Data
        Quality block to surface."""
        idx = self._raw_index.get(stmt_type)
        if idx is None:
            return start_row
        row = self._write_section_heading(ws, start_row, heading)

        sheet = idx["sheet_name"]
        period_to_col = idx["period_to_col"]
        f = self._fmt
        unmapped = self._unmapped_codes.setdefault(stmt_type, [])

        for code, indent in spine:
            label = _MODEL_LINE_LABELS.get(code, code)
            is_sub = code in subtotal_codes
            if is_sub:
                suffix = " (=)"
            else:
                hint = sign_hints.get(code) if sign_hints else None
                suffix = f" ({hint})" if hint else ""
            display = ("    " * indent) + label + suffix

            ws.set_row(row, 14)
            ws.write(row, 1, display,
                     f["label_subtotal"] if is_sub else f["label_body"])

            raw_row = self._resolve_raw_row(stmt_type, code)
            row_resolved = raw_row is not None

            for c_idx, p in enumerate(periods, start=3):
                is_y = _is_annual_period(p)
                cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                            else f["num_subtotal"] if is_sub
                            else f["num_linked_y"] if is_y
                            else f["num_linked"])
                raw_col = period_to_col.get(p)
                if not row_resolved or raw_col is None:
                    # Display "-" via the number format on a blank cell;
                    # do NOT write 0 (missing != zero).
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue
                cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                safe_sheet = sheet.replace("'", "''")
                formula = (
                    f"=IFERROR('{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                    f',"-")'
                )
                ws.write_formula(row, c_idx, formula, cell_fmt)

            if not row_resolved:
                unmapped.append(code)

            self._model_rows[f"{stmt_type}:{code}"] = row + 1  # 1-indexed
            row += 1

        return row + 1

    def _write_model_balance_sheet(self, ws, start_row: int, periods: list[str]) -> int:
        if (("BPA" not in self.stmts or self.stmts["BPA"].empty)
                and ("BPP" not in self.stmts or self.stmts["BPP"].empty)):
            return start_row
        row = self._write_section_heading(ws, start_row, "Balance Sheet")

        def block(stype, spine, subs, sub_label):
            nonlocal row
            f = self._fmt
            idx = self._raw_index.get(stype)
            if idx is None:
                return
            ws.set_row(row, 16)
            ws.write(row, 1, sub_label, f["label_subtotal"])
            row += 1
            sheet = idx["sheet_name"]
            period_to_col = idx["period_to_col"]
            unmapped = self._unmapped_codes.setdefault(stype, [])
            for code, indent in spine:
                label = _MODEL_LINE_LABELS.get(code, code)
                is_sub = code in subs
                display = ("    " * indent) + label + (" (=)" if is_sub else "")
                ws.set_row(row, 14)
                ws.write(row, 1, display,
                         f["label_subtotal"] if is_sub else f["label_body"])
                raw_row = self._resolve_raw_row(stype, code)
                row_resolved = raw_row is not None
                for c_idx, p in enumerate(periods, start=3):
                    is_y = _is_annual_period(p)
                    cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                                else f["num_subtotal"] if is_sub
                                else f["num_linked_y"] if is_y
                                else f["num_linked"])
                    raw_col = period_to_col.get(p)
                    if not row_resolved or raw_col is None:
                        ws.write_blank(row, c_idx, None, cell_fmt)
                        continue
                    cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                    safe_sheet = sheet.replace("'", "''")
                    formula = (
                        f"=IFERROR('{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                        f',"-")'
                    )
                    ws.write_formula(row, c_idx, formula, cell_fmt)
                if not row_resolved:
                    unmapped.append(code)
                self._model_rows[f"{stype}:{code}"] = row + 1
                row += 1
            row += 1

        block("BPA", _BPA_SPINE, _BPA_SUBTOTALS, "Assets")
        block("BPP", _BPP_SPINE, _BPP_SUBTOTALS, "Liabilities & Equity")

        return row

    def _write_model_da_and_ebitda(self, ws, start_row: int, periods: list[str]) -> int:
        idx = self._raw_index.get("DFC")
        if idx is None:
            return start_row
        f = self._fmt
        # Find first 6.01.01.* row containing "depreci" in DS_CONTA.
        dfc_df = self.stmts.get("DFC")
        if dfc_df is None or dfc_df.empty:
            return start_row
        da_row_in_raw = None
        for r_pos, (_, row_data) in enumerate(dfc_df.iterrows(), start=1):
            cd = str(row_data.get("CD_CONTA", "")).strip()
            ds = str(row_data.get("DS_CONTA", "") or "").lower()
            if cd.startswith("6.01.01") and "depreci" in ds:
                da_row_in_raw = r_pos + 1  # 1-indexed Excel row
                self._da_resolved = True
                self._da_cd_conta = cd
                break

        sheet = idx["sheet_name"]
        period_to_col = idx["period_to_col"]
        safe_sheet = sheet.replace("'", "''")

        # Write D&A row
        row = start_row
        ws.set_row(row, 14)
        ws.write(row, 1, "    Depreciation & Amortization (D&A)",
                 f["label_body"])
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = f["num_linked_y"] if is_y else f["num_linked"]
            raw_col = period_to_col.get(p)
            if da_row_in_raw is None or raw_col is None:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue
            cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(da_row_in_raw - 1, raw_col)
            formula = (
                f"=IFERROR('{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                f',"-")'
            )
            ws.write_formula(row, c_idx, formula, cell_fmt)
        self._model_rows["COMP:DA"] = row + 1
        row += 1

        # Write EBITDA = EBIT + D&A
        ebit_model_row = self._model_rows.get("DRE:3.05")
        ws.set_row(row, 14)
        ws.write(row, 1, "EBITDA (=)", f["label_subtotal"])
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = f["num_subtotal_y"] if is_y else f["num_subtotal"]
            if ebit_model_row is None or da_row_in_raw is None:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue
            col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
            ebit_ref = f"{col_letter}{ebit_model_row}"
            da_ref = f"{col_letter}{self._model_rows['COMP:DA']}"
            formula = f'=IFERROR({ebit_ref}+{da_ref},"-")'
            ws.write_formula(row, c_idx, formula, cell_fmt)
        self._model_rows["COMP:EBITDA"] = row + 1
        return row + 2

    def _write_model_fcf(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._fmt
        cfo_row = self._model_rows.get("DFC:6.01")
        capex_row = self._model_rows.get("DFC:6.02.01")
        if cfo_row is None or capex_row is None:
            return start_row
        row = start_row
        ws.set_row(row, 14)
        ws.write(row, 1, "Free Cash Flow (FCF) (=)", f["label_subtotal"])
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = f["num_subtotal_y"] if is_y else f["num_subtotal"]
            col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
            cfo_ref = f"{col_letter}{cfo_row}"
            capex_ref = f"{col_letter}{capex_row}"
            # Capex is negative in CVM convention so additive.
            formula = f'=IFERROR({cfo_ref}+{capex_ref},"-")'
            ws.write_formula(row, c_idx, formula, cell_fmt)
        self._model_rows["COMP:FCF"] = row + 1
        return row + 2

    def _write_model_kpis(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "KPIs / Ratios")

        rev = self._model_rows.get("DRE:3.01")
        gp = self._model_rows.get("DRE:3.03")
        ebit = self._model_rows.get("DRE:3.05")
        ebitda = self._model_rows.get("COMP:EBITDA")
        ni = self._model_rows.get("DRE:3.11")
        ta = self._model_rows.get("BPA:1")
        ca = self._model_rows.get("BPA:1.01")
        cash = self._model_rows.get("BPA:1.01.01")
        cl = self._model_rows.get("BPP:2.01")
        st_debt = self._model_rows.get("BPP:2.01.04")
        lt_debt = self._model_rows.get("BPP:2.02.01")
        eq = self._model_rows.get("BPP:2.03")
        cfo = self._model_rows.get("DFC:6.01")
        capex = self._model_rows.get("DFC:6.02.01")
        fcf = self._model_rows.get("COMP:FCF")

        def cell(letter, mrow):
            return f"{letter}{mrow}" if mrow else '"-"'

        def write_kpi(label, formula_fn, fmt_pct=True):
            nonlocal row
            ws.set_row(row, 14)
            ws.write(row, 1, "    " + label, f["kpi_label"])
            for c_idx, p in enumerate(periods, start=3):
                is_y = _is_annual_period(p)
                if fmt_pct:
                    cell_fmt = f["kpi_pct_y"] if is_y else f["kpi_pct"]
                else:
                    cell_fmt = f["kpi_ratio_y"] if is_y else f["kpi_ratio"]
                col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
                expr = formula_fn(col_letter, c_idx)
                if expr is None:
                    ws.write_blank(row, c_idx, None, cell_fmt)
                else:
                    ws.write_formula(row, c_idx, expr, cell_fmt)
            row += 1

        # Revenue Growth YoY — reference current vs previous column
        def rev_growth(col_letter, c_idx):
            if rev is None or c_idx <= 3:
                return None
            prev_letter = xlsxwriter.utility.xl_col_to_name(c_idx - 1)
            cur_ref = f"{col_letter}{rev}"
            prev_ref = f"{prev_letter}{rev}"
            return f'=IFERROR({cur_ref}/{prev_ref}-1,"-")'

        write_kpi("Revenue Growth (period-on-period)", rev_growth, True)
        write_kpi("Gross Margin",
                  lambda L, _: f'=IFERROR({cell(L,gp)}/{cell(L,rev)},"-")', True)
        write_kpi("EBITDA Margin",
                  lambda L, _: f'=IFERROR({cell(L,ebitda)}/{cell(L,rev)},"-")', True)
        write_kpi("EBIT Margin",
                  lambda L, _: f'=IFERROR({cell(L,ebit)}/{cell(L,rev)},"-")', True)
        write_kpi("Net Margin",
                  lambda L, _: f'=IFERROR({cell(L,ni)}/{cell(L,rev)},"-")', True)
        write_kpi("Return on Equity (ROE)",
                  lambda L, _: f'=IFERROR({cell(L,ni)}/{cell(L,eq)},"-")', True)
        write_kpi("Return on Assets (ROA)",
                  lambda L, _: f'=IFERROR({cell(L,ni)}/{cell(L,ta)},"-")', True)
        write_kpi("Net Debt / EBITDA",
                  lambda L, _: f'=IFERROR(({cell(L,st_debt)}+{cell(L,lt_debt)}-{cell(L,cash)})/{cell(L,ebitda)},"-")', False)
        write_kpi("Current Ratio",
                  lambda L, _: f'=IFERROR({cell(L,ca)}/{cell(L,cl)},"-")', False)
        write_kpi("CFO / Revenue",
                  lambda L, _: f'=IFERROR({cell(L,cfo)}/{cell(L,rev)},"-")', True)
        write_kpi("FCF / Revenue",
                  lambda L, _: f'=IFERROR({cell(L,fcf)}/{cell(L,rev)},"-")', True)
        write_kpi("Capex / Revenue",
                  lambda L, _: f'=IFERROR(-{cell(L,capex)}/{cell(L,rev)},"-")', True)

        return row + 1

    def _write_model_checks(self, ws, start_row: int, periods: list[str], dva_available: bool) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "Checks")

        ta = self._model_rows.get("BPA:1")
        tle = self._model_rows.get("BPP:2")
        bs_cash = self._model_rows.get("BPA:1.01.01")
        cf_end_cash = self._model_rows.get("DFC:6.05.02")
        ni_dre = self._model_rows.get("DRE:3.11")
        ni_dfc = self._model_rows.get("DFC:6.01.01.01")

        # Balance Sheet tie
        ws.set_row(row, 14)
        ws.write(row, 1, "Balance Sheet: Total Assets − (Liab. + Equity)",
                 f["check_label"])
        first_col_letter = xlsxwriter.utility.xl_col_to_name(3)
        last_col_letter = xlsxwriter.utility.xl_col_to_name(2 + len(periods))
        if ta is not None and tle is not None:
            # Size-relative tolerance: a period ties when |Assets − (L+E)|
            # is within max(0.5 R$ mm, 0.05% of that period's Total Assets).
            # The 0.5 floor keeps small companies sane; the relative term
            # avoids false ERRORs on very large balance sheets where ÷1000
            # scaling leaves sub-materiality noise.
            d = row + 1  # Excel row holding the per-period delta cells
            ta_rng = f"{first_col_letter}{ta}:{last_col_letter}{ta}"
            tol = f"IF(0.0005*ABS({ta_rng})>0.5,0.0005*ABS({ta_rng}),0.5)"
            ws.write_formula(
                row, 2,
                f'=IF(SUMPRODUCT(--(ABS({first_col_letter}{d}:{last_col_letter}{d})>{tol}))=0,"OK","ERROR")',
                f["check_ok"],
            )
        else:
            ws.write(row, 2, "WARNING", f["check_warning"])
        for c_idx, _ in enumerate(periods, start=3):
            col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
            if ta is None or tle is None:
                ws.write_blank(row, c_idx, None, f["check_value"])
                continue
            formula = f'=IFERROR({col_letter}{ta}-{col_letter}{tle},"-")'
            ws.write_formula(row, c_idx, formula, f["check_value"])
        row += 1

        # Cash Flow Tie — Ending Cash on DFC vs Cash on BPA
        ws.set_row(row, 14)
        ws.write(row, 1,
                 "Cash Flow Tie: Ending Cash (DFC) − Cash (BPA)",
                 f["check_label"])
        if cf_end_cash is not None and bs_cash is not None:
            ws.write_formula(
                row, 2,
                f'=IF(SUMPRODUCT(--(ABS({first_col_letter}{row + 1}:{last_col_letter}{row + 1})>0.5))=0,"OK","WARNING")',
                f["check_ok"],
            )
            for c_idx, _ in enumerate(periods, start=3):
                col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
                formula = (
                    f'=IFERROR({col_letter}{cf_end_cash}-{col_letter}{bs_cash},'
                    f'"-")'
                )
                ws.write_formula(row, c_idx, formula, f["check_value"])
        else:
            ws.write(row, 2, "WARNING", f["check_warning"])
            ws.write(row, 3, "DFC ending cash or BPA cash unavailable",
                     f["source_warning"])
            for c_idx, _ in enumerate(periods, start=3):
                ws.write_blank(row, c_idx, None, f["check_value"])
        row += 1

        # Net Income Tie — DRE 3.11 vs DFC 6.01.01.01 (NI as DFC start)
        ws.set_row(row, 14)
        ws.write(row, 1,
                 "Net Income Tie: DRE Net Income − DFC starting NI",
                 f["check_label"])
        if ni_dre is not None and ni_dfc is not None:
            ws.write_formula(
                row, 2,
                f'=IF(SUMPRODUCT(--(ABS({first_col_letter}{row + 1}:{last_col_letter}{row + 1})>0.5))=0,"OK","WARNING")',
                f["check_ok"],
            )
            for c_idx, _ in enumerate(periods, start=3):
                col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
                formula = (
                    f'=IFERROR({col_letter}{ni_dre}-{col_letter}{ni_dfc},'
                    f'"-")'
                )
                ws.write_formula(row, c_idx, formula, f["check_value"])
        else:
            ws.write(row, 2, "WARNING", f["check_warning"])
            ws.write(row, 3, "DFC starting net income unavailable",
                     f["source_warning"])
            for c_idx, _ in enumerate(periods, start=3):
                ws.write_blank(row, c_idx, None, f["check_value"])
        row += 1

        # Period Completeness
        n_model = len(periods)
        n_raw = max(
            (len(self.stmts[k].columns) - sum(1 for c in self.stmts[k].columns
                                              if c in ("CD_CONTA", "DS_CONTA",
                                                       "STANDARD_NAME", "LINE_ID_BASE"))
             for k in self.stmts if self.stmts[k] is not None and not self.stmts[k].empty),
            default=0,
        )
        ws.set_row(row, 14)
        ws.write(row, 1,
                 f"Period Completeness — Model: {n_model}, raw: {n_raw}",
                 f["check_label"])
        ws.write(row, 2, "OK" if n_model > 0 else "ERROR",
                 f["check_ok"] if n_model > 0 else f["check_error"])
        row += 1

        # Critical Line Availability — verify the model rows resolved
        critical_lines = [
            ("Revenue",      "DRE:3.01"),
            ("EBITDA",       "COMP:EBITDA"),
            ("EBIT",         "DRE:3.05"),
            ("Net Income",   "DRE:3.11"),
            ("Total Assets", "BPA:1"),
            ("Total Liab. & Equity", "BPP:2"),
            ("Cash",         "BPA:1.01.01"),
            ("ST Debt",      "BPP:2.01.04"),
            ("LT Debt",      "BPP:2.02.01"),
            ("Equity",       "BPP:2.03"),
            ("CFO",          "DFC:6.01"),
            ("Capex",        "DFC:6.02.01"),
            ("FCF",          "COMP:FCF"),
        ]

        def _row_has_value(model_row: int | None, stmt_type: str, code: str) -> bool:
            if model_row is None:
                return False
            # The model row exists but resolved to unmapped → still flag.
            unmapped = self._unmapped_codes.get(stmt_type, [])
            return code not in unmapped

        missing = []
        for name, key in critical_lines:
            mrow = self._model_rows.get(key)
            if mrow is None:
                missing.append(name)
                continue
            if key.startswith("COMP:"):
                continue  # computed lines depend on raws; covered indirectly
            stype, code = key.split(":", 1)
            if not _row_has_value(mrow, stype, code):
                missing.append(name)

        ws.set_row(row, 14)
        ws.write(row, 1, "Critical Line Availability", f["check_label"])
        ws.write(row, 2, "OK" if not missing else "WARNING",
                 f["check_ok"] if not missing else f["check_warning"])
        if missing:
            ws.write(row, 3, "Missing: " + ", ".join(missing),
                     f["source_warning"])
        row += 1

        # DVA Availability
        ws.set_row(row, 14)
        ws.write(row, 1, "DVA Availability", f["check_label"])
        ws.write(row, 2, "OK" if dva_available else "WARNING",
                 f["check_ok"] if dva_available else f["check_warning"])
        if not dva_available:
            ws.write(row, 3, "DVA not in current export pipeline",
                     f["source_warning"])
        row += 1

        # D&A Resolution — EBITDA = EBIT + D&A depends on the D&A line
        # resolving in the DFC raw sheet (substring match on a 6.01.01.*
        # 'depreci' line). Surface it so a silently-missing D&A (and thus a
        # D&A-less EBITDA) is visible to the analyst.
        ws.set_row(row, 14)
        ws.write(row, 1, "D&A Resolved (EBITDA dependency)", f["check_label"])
        ws.write(row, 2, "OK" if self._da_resolved else "WARNING",
                 f["check_ok"] if self._da_resolved else f["check_warning"])
        if self._da_resolved:
            ws.write(row, 3, f"Matched DFC line {self._da_cd_conta}",
                     f["source_note"])
        else:
            ws.write(row, 3,
                     "No 6.01.01.* 'depreci' line found — EBITDA excludes D&A",
                     f["source_warning"])
        row += 1

        # Formula Error Scan — value asserted by the post-write validator.
        # The cell text is set here so the analyst sees the result inline.
        ws.set_row(row, 14)
        ws.write(row, 1,
                 "Formula Error Scan (no #NUM! / #REF! / #VALUE! / #DIV-0!)",
                 f["check_label"])
        ws.write(row, 2, "OK", f["check_ok"])
        ws.write(row, 3,
                 "Validated by post-write sweep before workbook is returned.",
                 f["source_note"])
        row += 1

        return row + 1

    def _write_model_source(self, ws, start_row: int, periods: list[str], dva_available: bool) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "Source / Data Quality")
        info = self.info

        stmts_present = [k for k in ("DRE", "BPA", "BPP", "DFC", "DVA")
                         if k in self.stmts and not self.stmts[k].empty]
        rows_by_stmt = ", ".join(
            f"{k}={len(self.stmts[k])}"
            for k in stmts_present
        ) or "—"

        rows_src = [
            ("Generated by",        "CVMAnalytics"),
            ("App version",         str(_APP_VERSION)),
            ("Export timestamp",    datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("Company",             str(info.get("company_name") or "—")),
            ("CVM code",            str(info.get("cd_cvm") or "—")),
            ("Period window (Model)",
             f"Annual: {self.period_window[0]} years; "
             f"Quarterly: {self.period_window[1]} quarters/year (interleaved)"),
            ("Periods on Model",    str(len(periods))),
            ("Raw rows by statement", rows_by_stmt),
            ("Source",              "CVM filings processed by CVMAnalytics local database"),
            ("Units",               "Model: R$ mm. CVM source: R$ mil. Conversion: ÷1,000."),
            ("Full history",        "Available in hidden raw_* sheets."),
        ]
        if not dva_available:
            rows_src.append(
                ("Note — DVA",
                 "DVA: unavailable in current export pipeline for this company."),
            )
        # Surface unmapped spine codes per statement so the analyst can
        # see exactly which lines were not present in the raw filing.
        for stype in ("DRE", "BPA", "BPP", "DFC", "DVA"):
            unmapped = self._unmapped_codes.get(stype, [])
            if unmapped:
                rows_src.append(
                    (f"Unmapped — {stype}",
                     f"{len(unmapped)} spine line(s) absent in raw data: "
                     + ", ".join(unmapped)),
                )

        for label, value in rows_src:
            ws.set_row(row, 14)
            ws.write(row, 1, label, f["source_label"])
            ws.write(row, 3, value, f["source_value"])
            row += 1
        return row + 1

    # ── sheet ordering and validation ─────────────────────────────────────
    def _reorder_visible_sheets(self):
        """Put Model first, README second, then everything else as-is."""
        worksheets = self._wb.worksheets()
        if not worksheets:
            return
        name_to_ws = {ws.name: ws for ws in worksheets}
        desired_front = [n for n in (MODEL_SHEET, README_SHEET) if n in name_to_ws]
        rest = [ws for ws in worksheets if ws.name not in desired_front]
        new_order = [name_to_ws[n] for n in desired_front] + rest
        # xlsxwriter exposes the worksheets list directly; reordering by
        # index is the safe way to reposition tabs.
        for new_idx, ws in enumerate(new_order):
            ws.index = new_idx
        self._wb.worksheets_objs = new_order

    def _validate_no_errors(self, payload: bytes) -> None:
        """Re-open the workbook with openpyxl and abort if any cell holds
        an Excel error string OR any sheet has merged cells. Both are
        forbidden by the v0.19.x analyst-export contract."""
        try:
            wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
        except Exception:  # pragma: no cover - re-open is best-effort
            return
        try:
            error_prefixes = ("#NUM!", "#REF!", "#VALUE!", "#DIV/0!",
                              "#NAME?", "#N/A", "#NULL!")
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                # Merged cells are forbidden across the entire workbook.
                merged = list(ws.merged_cells.ranges)
                if merged:
                    raise ExcelExportError(
                        f"Merged cells found on {sheet_name}: "
                        f"{[str(r) for r in merged]}"
                    )
                for row in ws.iter_rows(values_only=False):
                    for cell in row:
                        v = cell.value
                        if isinstance(v, str) and v.startswith("#"):
                            for prefix in error_prefixes:
                                if v.startswith(prefix):
                                    raise ExcelExportError(
                                        f"Error cell {sheet_name}!{cell.coordinate}: {v}"
                                    )
        finally:
            wb.close()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers used across writers
# ──────────────────────────────────────────────────────────────────────────────
def _stmt_subtotals(stmt_type: str) -> set[str]:
    return {
        "DRE": _DRE_SUBTOTALS,
        "BPA": _BPA_SUBTOTALS,
        "BPP": _BPP_SUBTOTALS,
        "DFC": _DFC_SUBTOTALS,
        "DVA": {"7.08"},
    }.get(stmt_type, set())
