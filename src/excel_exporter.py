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
    "3.01": "Revenue",
    "3.02": "Costs",
    "3.03": "Gross Profit",
    "3.04": "Operating Expenses",
    "3.05": "Operating Result (EBIT)",
    "3.06": "Financial Result",
    "3.07": "Income Before Taxes",
    "3.08": "Income Taxes",
    "3.11": "Net Income",
    # BPA
    "1":        "Total Assets",
    "1.01":     "Current Assets",
    "1.01.01":  "Cash and Equivalents",
    "1.02":     "Non-current Assets",
    # BPP
    "2":        "Total Liabilities and Equity",
    "2.01":     "Current Liabilities",
    "2.01.04":  "Short-term Debt",
    "2.02":     "Non-current Liabilities",
    "2.02.01":  "Long-term Debt",
    "2.03":     "Equity",
    "2.03.01":  "Capital",
    "2.03.04":  "Retained Earnings",
    # DFC
    "6.01":     "Cash Flow from Operations (CFO)",
    "6.02":     "Cash Flow from Investing (CFI)",
    "6.02.01":  "Capex",
    "6.03":     "Cash Flow from Financing (CFF)",
    "6.04":     "Effect of FX on Cash",
    "6.05":     "Change in Cash",
    "6.01.01.DA": "Depreciation and Amortization",
}

_DRE_SUBTOTALS = {"3.01", "3.03", "3.05", "3.07", "3.11"}
_BPA_SUBTOTALS = {"1", "1.01", "1.02"}
_BPP_SUBTOTALS = {"2", "2.01", "2.02", "2.03"}
_DFC_SUBTOTALS = {"6.01", "6.02", "6.03", "6.05"}


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

        # Number formats with bracketed-red negatives (financial modeling
        # convention). Zero falls back to "-".
        num_fmt = "#,##0;[Red](#,##0);-"
        num_fmt_dec = "#,##0.0;[Red](#,##0.0);-"
        pct_fmt = "0.0%;[Red](0.0%);-"
        ratio_fmt = '0.00"x";[Red](0.00"x");-'
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
        cd_to_row: dict[str, int] = {}
        period_to_col: dict[str, int] = {}
        for c_idx, p in enumerate(period_cols, start=len(id_cols)):
            period_to_col[str(p)] = c_idx

        for r_idx, (_, row) in enumerate(df.iterrows(), start=1):
            cd = str(row.get("CD_CONTA", "")).strip()
            is_sub = cd in subtotals
            cd_to_row[cd] = r_idx + 1  # 1-indexed Excel row

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
        ws.set_column("C:C", 70)
        ws.set_row(1, 28)
        ws.write(1, 1, "README", self._fmt["title"])

        info = self.info
        company = str(info.get("company_name") or "—")
        ws.write(2, 1, f"Workbook for {company}", self._fmt["subtitle"])

        section_rows = [
            ("Main sheet",
             "`Model` — analyst-curated single sheet with Income Statement, "
             "Balance Sheet, Cash Flow Statement, optional DVA, KPIs, Checks, "
             "and Source / Data Quality blocks."),
            ("Period window",
             f"Annual: last {self.period_window[0]} fiscal years; "
             f"Quarterly: up to {self.period_window[1]} quarters per included annual year, "
             "interleaved chronologically (e.g. 1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ...)."),
            ("Units",
             "Model sheet: R$ mm (millions). CVM source: R$ mil (thousands); "
             "divided by 1,000 in the Model view. Raw sheets keep R$ mil."),
            ("Hidden sheets",
             "Right-click any visible sheet tab → Unhide… to audit raw_DRE / "
             "raw_BPA / raw_BPP / raw_DFC / raw_DVA / raw_KPIs / metadata. The "
             "raw sheets preserve the full CVM tree and full period history."),
            ("Conventions",
             "Linked values are green (link into raw_*); calculated values are "
             "black (formula in cell); negative numbers appear red and in "
             "parentheses; zero displays as `-`."),
            ("Checks",
             "Balance Sheet tie, Cash Flow tie, Critical Line Availability, "
             "Period Completeness, and DVA Availability are computed by formula "
             "on the Model sheet. The exporter also runs a post-write sweep that "
             "fails the export if any cell contains an Excel error code."),
            ("Limitations",
             "No forecast periods, no LTM column, no per-share / share-count / "
             "market-price rows, no sector-specific KPIs in v0.19.0. Full CVM "
             "history is available via the raw sheets."),
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

        # Conventions block (rows 1-9, 0-indexed)
        ws.write(1, 1, "Conventions", f["conv_header"])
        ws.write(2, 3, "Input",       f["conv_input"])
        ws.write(3, 3, "Output",      f["conv_output"])
        ws.write(4, 3, "Linked",      f["conv_linked"])
        ws.write(5, 3, "Calculation", f["conv_calc"])
        ws.write(6, 3, "Check (OK)",  f["conv_check"])
        ws.write(7, 3, "Note",        f["conv_note"])
        ws.write(8, 3, "Warning",     f["conv_warning"])
        ws.write(8, 4, "(red) negatives shown as (123)", f["conv_note"])

        # Title + subtitle
        company_name = str(info.get("company_name") or "—")
        ws.set_row(10, 26)
        last_col = max(4, 2 + len(periods))
        ws.merge_range(10, 1, 10, last_col,
                       f"Financial Statement Model — {company_name}",
                       f["title"])
        ws.write(11, 1, "R$ mm except per share and where indicated",
                 f["subtitle"])

        # Company info block (rows 13-21)
        latest_year = info.get("latest_year") or "—"
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
        for i, (label, value) in enumerate(rows_info):
            r = 13 + i
            ws.set_row(r, 14)
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
            line_codes=["3.01", "3.02", "3.03", "3.04", "3.05",
                        "3.06", "3.07", "3.08", "3.11"],
            subtotal_codes=_DRE_SUBTOTALS,
            indent_codes={"3.02": 1, "3.04": 1, "3.06": 1, "3.08": 1},
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
            line_codes=["6.01", "6.02", "6.02.01", "6.03", "6.04", "6.05"],
            subtotal_codes=_DFC_SUBTOTALS,
            indent_codes={"6.02.01": 1},
        )

        # Computed: FCF = CFO + Capex (Capex is negative in CVM source)
        cur = self._write_model_fcf(ws, cur, periods)

        # Section: Value Added Statement (DVA)
        dva_available = "DVA" in self.stmts and not self.stmts["DVA"].empty
        if dva_available:
            cur = self._write_model_section(
                ws, cur, periods,
                heading="Value Added Statement",
                stmt_type="DVA",
                line_codes=["7.08"],
                subtotal_codes={"7.08"},
                indent_codes={},
            )

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
        return row + 2

    def _write_model_section(
        self,
        ws,
        start_row: int,
        periods: list[str],
        *,
        heading: str,
        stmt_type: str,
        line_codes: list[str],
        subtotal_codes: set[str],
        indent_codes: dict[str, int],
    ) -> int:
        idx = self._raw_index.get(stmt_type)
        if idx is None:
            return start_row
        row = self._write_section_heading(ws, start_row, heading)

        sheet = idx["sheet_name"]
        cd_to_row = idx["cd_to_row"]
        period_to_col = idx["period_to_col"]
        f = self._fmt

        for code in line_codes:
            label = _MODEL_LINE_LABELS.get(code, code)
            is_sub = code in subtotal_codes
            indent = indent_codes.get(code, 0)
            display = ("    " * indent) + label + (" (=)" if is_sub else "")

            ws.set_row(row, 14)
            ws.write(row, 1, display,
                     f["label_subtotal"] if is_sub else f["label_body"])

            raw_row = cd_to_row.get(code)
            for c_idx, p in enumerate(periods, start=3):
                is_y = _is_annual_period(p)
                cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                            else f["num_subtotal"] if is_sub
                            else f["num_linked_y"] if is_y
                            else f["num_linked"])
                raw_col = period_to_col.get(p)
                if raw_row is None or raw_col is None:
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue
                # Build the cross-sheet formula reference. xlsxwriter
                # requires xl_rowcol_to_cell-style refs for sheet names.
                cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                safe_sheet = sheet.replace("'", "''")
                formula = (
                    f"=IFERROR('{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                    f',"-")'
                )
                ws.write_formula(row, c_idx, formula, cell_fmt)

            # remember the model row for this code so the Checks/KPIs
            # block can reference back into it
            self._model_rows[f"{stmt_type}:{code}"] = row + 1  # 1-indexed
            row += 1

        return row + 1

    def _write_model_balance_sheet(self, ws, start_row: int, periods: list[str]) -> int:
        if (("BPA" not in self.stmts or self.stmts["BPA"].empty)
                and ("BPP" not in self.stmts or self.stmts["BPP"].empty)):
            return start_row
        row = self._write_section_heading(ws, start_row, "Balance Sheet")

        def block(stype, codes, subs, indents, sub_label):
            nonlocal row
            f = self._fmt
            ws.set_row(row, 16)
            ws.write(row, 1, sub_label, f["label_subtotal"])
            row += 1
            idx = self._raw_index.get(stype)
            if idx is None:
                return
            sheet = idx["sheet_name"]
            cd_to_row = idx["cd_to_row"]
            period_to_col = idx["period_to_col"]
            for code in codes:
                label = _MODEL_LINE_LABELS.get(code, code)
                is_sub = code in subs
                indent = indents.get(code, 0)
                display = ("    " * indent) + label + (" (=)" if is_sub else "")
                ws.set_row(row, 14)
                ws.write(row, 1, display,
                         f["label_subtotal"] if is_sub else f["label_body"])
                raw_row = cd_to_row.get(code)
                for c_idx, p in enumerate(periods, start=3):
                    is_y = _is_annual_period(p)
                    cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                                else f["num_subtotal"] if is_sub
                                else f["num_linked_y"] if is_y
                                else f["num_linked"])
                    raw_col = period_to_col.get(p)
                    if raw_row is None or raw_col is None:
                        ws.write_blank(row, c_idx, None, cell_fmt)
                        continue
                    cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                    safe_sheet = sheet.replace("'", "''")
                    formula = (
                        f"=IFERROR('{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                        f',"-")'
                    )
                    ws.write_formula(row, c_idx, formula, cell_fmt)
                self._model_rows[f"{stype}:{code}"] = row + 1
                row += 1
            row += 1

        block("BPA",
              ["1", "1.01", "1.01.01", "1.02"],
              _BPA_SUBTOTALS,
              {"1.01": 1, "1.01.01": 2, "1.02": 1},
              "Assets")
        block("BPP",
              ["2", "2.01", "2.01.04", "2.02", "2.02.01",
               "2.03", "2.03.01", "2.03.04"],
              _BPP_SUBTOTALS,
              {"2.01": 1, "2.01.04": 2, "2.02": 1, "2.02.01": 2,
               "2.03": 1, "2.03.01": 2, "2.03.04": 2},
              "Liabilities & Equity")

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

        # Balance Sheet tie
        ws.set_row(row, 14)
        ws.write(row, 1, "Balance Sheet: Total Assets − (Liab. + Equity)",
                 f["check_label"])
        first_col_letter = xlsxwriter.utility.xl_col_to_name(3)
        last_col_letter = xlsxwriter.utility.xl_col_to_name(2 + len(periods))
        status_cell = f"{xlsxwriter.utility.xl_col_to_name(3)}{row + 1}"
        # Status formula references the diffs further right on the same row.
        ws.write_formula(
            row, 2,
            f'=IF(SUMPRODUCT(--(ABS({first_col_letter}{row + 1}:{last_col_letter}{row + 1})>0.5))=0,"OK","ERROR")',
            f["check_ok"],
        )
        for c_idx, _ in enumerate(periods, start=3):
            col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
            if ta is None or tle is None:
                ws.write_blank(row, c_idx, None, f["check_value"])
                continue
            formula = f'=IFERROR({col_letter}{ta}-{col_letter}{tle},"-")'
            ws.write_formula(row, c_idx, formula, f["check_value"])
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
        ]
        missing = [name for name, key in critical_lines
                   if self._model_rows.get(key) is None]
        ws.set_row(row, 14)
        ws.write(row, 1, "Critical Line Availability", f["check_label"])
        ws.write(row, 2, "OK" if not missing else "WARNING",
                 f["check_ok"] if not missing else f["check_warning"])
        if missing:
            ws.write(row, 3, "Missing: " + ", ".join(missing), f["source_warning"])
        row += 1

        # DVA Availability
        ws.set_row(row, 14)
        ws.write(row, 1, "DVA Availability", f["check_label"])
        ws.write(row, 2, "OK" if dva_available else "WARNING",
                 f["check_ok"] if dva_available else f["check_warning"])
        if not dva_available:
            ws.write(row, 3, "DVA not in current export", f["source_warning"])
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
        an Excel error string. Catches accidental #NUM! / #REF! / etc."""
        try:
            wb = openpyxl.load_workbook(io.BytesIO(payload), data_only=False)
        except Exception:  # pragma: no cover - re-open is best-effort
            return
        try:
            error_prefixes = ("#NUM!", "#REF!", "#VALUE!", "#DIV/0!",
                              "#NAME?", "#N/A", "#NULL!")
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
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
