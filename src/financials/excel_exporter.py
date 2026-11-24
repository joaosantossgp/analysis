# -*- coding: utf-8 -*-
"""src/financials/excel_exporter.py — Analyst-ready Excel exporter (v0.19.0).

Produces a workbook centered on a single user-facing ``Model`` sheet
that consolidates the Income Statement, Balance Sheet, Cash Flow
Statement, KPIs, Checks, and Source /
Data Quality blocks. The full CVM tree and full period history remain
available in hidden ``raw_*`` sheets so the workbook stays auditable
without the model view becoming a data dump.

Visible sheets:
    Model    — analyst sheet (compact 5-year + 20-quarter window)
    README   — sheet map, conventions, period policy

Hidden sheets:
    raw_DRE / raw_BPA / raw_BPP / raw_DFC / raw_DMPL (optional)
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
import json
import math
import re
from datetime import date, datetime
from typing import Optional

import numpy as np
import openpyxl
import pandas as pd
import xlsxwriter

from src.financials.excel_mapping import (
    DEFAULT_MAPPING_VERSION,
    SYSTEM_DEFAULT_PRESET_ID,
    VALID_MAPPING_OPERATIONS,
    MappingValidationIssue,
    ModelMappingDefinition,
    ModelMappingEntry,
    ModelMappingSource,
)
from src.financials.statement_summary import build_general_summary_blocks

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
MAPPING_AUDIT_SHEET = "mapping_audit"
RAW_KPI_SHEET = "raw_KPIs"

_RAW_PREFIX = "raw_"
_LEGACY_TO_RAW = {
    "DRE": "raw_DRE",
    "BPA": "raw_BPA",
    "BPP": "raw_BPP",
    "DFC": "raw_DFC",
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
    "6.01.03":      "Other Operating Cash Flows",
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
    ("6.01.03", 1),
    ("6.02", 0),
    ("6.02.01", 1), ("6.02.02", 1), ("6.02.03", 1),
    ("6.03", 0),
    ("6.03.01", 1), ("6.03.02", 1), ("6.03.04", 1),
    ("6.04", 0),
    ("6.05", 0),
    ("6.05.01", 1), ("6.05.02", 1),
]
# ── Financial institution spines ──────────────────────────────────────────────
# Banks and insurers file under COSIF/IFRS7 rules; their CVM CD_CONTA tree
# differs from the generic industrial spine above.  These spines cover the
# common codes observed across Itaú, Bradesco, and Santander (Brazil's three
# largest publicly-traded banks).  Codes that don't exist for a given company
# render as "-" through the normal _resolve_raw_row fallback.
_FIN_DRE_SPINE: list[tuple[str, int]] = [
    ("3.01", 0),
    ("3.01.01", 1), ("3.01.02", 1), ("3.01.03", 1), ("3.01.04", 1),
    ("3.01.05", 1), ("3.01.06", 1), ("3.01.07", 1),
    ("3.02", 0),
    ("3.02.01", 1), ("3.02.02", 1), ("3.02.03", 1),
    ("3.03", 0),
    ("3.04", 0),
    ("3.04.01", 1), ("3.04.02", 1), ("3.04.03", 1), ("3.04.04", 1),
    ("3.04.05", 1), ("3.04.06", 1), ("3.04.07", 1), ("3.04.08", 1),
    ("3.05", 0),
    ("3.06", 0), ("3.06.01", 1), ("3.06.02", 1),
    ("3.07", 0),
    ("3.08", 0),
    ("3.09", 0), ("3.09.01", 1), ("3.09.02", 1),
    ("3.10", 0),
    ("3.11", 0), ("3.11.01", 1), ("3.11.02", 1),
]
_FIN_DRE_SUBTOTALS: set[str] = {"3.01", "3.03", "3.05", "3.07", "3.09", "3.11"}
_FIN_DRE_SIGN_HINTS: dict[str, str] = {
    "3.01.01": "+", "3.01.02": "+/-", "3.01.03": "+/-", "3.01.04": "+/-",
    "3.01.05": "+", "3.01.06": "+", "3.01.07": "+",
    "3.02": "-", "3.02.01": "-", "3.02.02": "-", "3.02.03": "-",
    "3.04": "+/-",
    "3.04.01": "+/-", "3.04.02": "+", "3.04.03": "-", "3.04.04": "-",
    "3.04.05": "+", "3.04.06": "-", "3.04.07": "+/-", "3.04.08": "+/-",
    "3.06": "-", "3.06.01": "-", "3.06.02": "+/-",
    "3.09.01": "+", "3.09.02": "+/-",
    "3.11.01": "+", "3.11.02": "+/-",
}

_FIN_BPA_SPINE: list[tuple[str, int]] = [
    ("1", 0),
    ("1.01", 1), ("1.01.01", 2), ("1.01.02", 2),
    ("1.02", 1),
    ("1.02.01", 2), ("1.02.02", 2), ("1.02.03", 2), ("1.02.04", 2),
    ("1.03", 1), ("1.03.01", 2), ("1.03.02", 2), ("1.03.03", 2),
    ("1.04", 1),
    ("1.05", 1),
    ("1.06", 1),
    ("1.07", 1),
]
_FIN_BPA_SUBTOTALS: set[str] = {"1"}

_FIN_BPP_SPINE: list[tuple[str, int]] = [
    ("2", 0),
    ("2.01", 1),
    ("2.02", 1), ("2.02.01", 2), ("2.02.02", 2), ("2.02.03", 2), ("2.02.04", 2),
    ("2.03", 1), ("2.03.01", 2), ("2.03.02", 2), ("2.03.03", 2),
    ("2.03.04", 2), ("2.03.05", 2),
    ("2.04", 1),
    ("2.05", 1),
    ("2.06", 1),
    ("2.07", 1),
    ("2.08", 1), ("2.08.01", 2), ("2.08.04", 2), ("2.08.09", 2),
]
_FIN_BPP_SUBTOTALS: set[str] = {"2", "2.08"}

# Label overrides for financial institution codes.  Inherits all industrial
# labels and replaces only the codes whose semantics differ.
_FIN_MODEL_LINE_LABELS: dict[str, str] = {
    **_MODEL_LINE_LABELS,
    # DRE
    "3.01":    "Financial Intermediation Revenue",
    "3.01.01": "Interest Income",
    "3.01.02": "Interest Expense (within Revenue)",
    "3.01.03": "FX Gains / (Losses)",
    "3.01.04": "FV Adjustments — Assets & Liabilities",
    "3.01.05": "Service and Fee Revenue",
    "3.01.06": "Other Service Revenue",
    "3.01.07": "Other Revenue",
    "3.02":    "Financial Intermediation Expenses",
    "3.02.01": "Interest Expense",
    "3.02.02": "Expected Credit Loss — Loans",
    "3.02.03": "Expected Credit Loss — Other / Insurance",
    "3.03":    "Net Interest Income (NII)",
    "3.04":    "Other Operating Expenses / Revenue",
    "3.04.01": "Credit Loss / Service Revenue",
    "3.04.02": "Service Revenue",
    "3.04.03": "Administrative & Personnel Expenses",
    "3.04.04": "Tax Expenses",
    "3.04.05": "Other Operating Revenue",
    "3.04.06": "Other Operating Expenses",
    "3.04.07": "D&A",
    "3.04.08": "Equity Income",
    "3.05":    "Pre-tax Income",
    "3.06":    "Income Tax & Social Contribution",
    "3.09":    "Net Income (Consolidated)",
    "3.09.01": "Attributable to Controlling Shareholders",
    "3.09.02": "Attributable to Non-controlling Interests",
    # BPA
    "1.01":    "Cash and Equivalents",
    "1.01.01": "Cash",
    "1.01.02": "Liquid Applications",
    "1.02":    "Financial Assets",
    "1.02.01": "FA at FV through P&L",
    "1.02.02": "FA at FV through OCI",
    "1.02.03": "FA at Amortized Cost",
    "1.02.04": "FA at Amortized Cost (loans)",
    "1.03":    "Tax and Other Receivables",
    "1.03.01": "Recoverable Income Tax",
    "1.03.02": "Deferred Tax Asset",
    "1.03.03": "Other Receivables",
    "1.04":    "Other Assets",
    "1.05":    "Investments",
    "1.06":    "Property, Plant & Equipment",
    "1.07":    "Intangible Assets",
    # BPP
    "2.01":    "Financial Liabilities at FV through P&L",
    "2.02":    "Financial Liabilities at FV — Other",
    "2.02.01": "Deposits",
    "2.02.02": "Open Market Funding",
    "2.02.03": "Interbank Market Funding",
    "2.02.04": "Other Funding",
    "2.03":    "Financial Liabilities at Amortized Cost",
    "2.03.01": "Deposits",
    "2.03.02": "Open Market Funding",
    "2.03.03": "Interbank Market Funding",
    "2.03.04": "Institutional Funding",
    "2.03.05": "Other Financial Liabilities",
    "2.04":    "Provisions",
    "2.05":    "Tax Liabilities",
    "2.06":    "Other Liabilities",
    "2.07":    "Liabilities — Non-current Assets & Discontinued",
    "2.08":    "Equity",
    "2.08.01": "Share Capital",
    "2.08.04": "Earnings Reserves",
    "2.08.09": "Non-controlling Interests",
}

_REQUIRED_MODEL_CODES: dict[str, set[str]] = {
    "DRE": {"3.01", "3.05", "3.11"},
    "BPA": {"1"},
    "BPP": {"2"},
    "DFC": {"6.01"},
}


def is_financial_company_info(company_info: dict | None) -> bool:
    info = company_info or {}
    gics = str(info.get("gics_sector") or "").lower()
    company_type = str(info.get("company_type") or "").lower()
    return (
        "financ" in gics
        or "insur" in gics
        or "banco" in company_type
        or "bank" in company_type
        or "financ" in company_type
    )


def build_default_model_mapping(
    company_info: dict | None = None,
    *,
    is_financial_firm: bool | None = None,
) -> ModelMappingDefinition:
    """Build the system default mapping from the current analyst spine.

    The target ids intentionally match ``self._model_rows`` keys
    (``DRE:3.01``, ``BPA:1`` etc.) so downstream KPI/check formulas keep
    their existing references when a user changes only the raw sources.
    """
    is_fin = is_financial_company_info(company_info) if is_financial_firm is None else is_financial_firm
    labels = _FIN_MODEL_LINE_LABELS if is_fin else _MODEL_LINE_LABELS
    entries: list[ModelMappingEntry] = []
    order = 0

    def add_spine(
        *,
        group: str,
        stmt_type: str,
        spine: list[tuple[str, int]],
        subtotal_codes: set[str],
    ) -> None:
        nonlocal order
        for code, indent in spine:
            label = labels.get(code, code)
            entries.append(
                ModelMappingEntry(
                    target_id=f"{stmt_type}:{code}",
                    target_label=label,
                    group=group,
                    statement_type=stmt_type,
                    display_order=order,
                    indent_level=int(indent),
                    required=code in _REQUIRED_MODEL_CODES.get(stmt_type, set()),
                    operation="direct",
                    is_subtotal=code in subtotal_codes,
                    sources=(
                        ModelMappingSource(
                            statement_type=stmt_type,
                            line_id_base=code,
                            cd_conta=code,
                            label_snapshot=label,
                            sign=1,
                            position=0,
                        ),
                    ),
                )
            )
            order += 1

    add_spine(
        group="Income Statement",
        stmt_type="DRE",
        spine=_FIN_DRE_SPINE if is_fin else _DRE_SPINE,
        subtotal_codes=_FIN_DRE_SUBTOTALS if is_fin else _DRE_SUBTOTALS,
    )
    add_spine(
        group="Assets",
        stmt_type="BPA",
        spine=_FIN_BPA_SPINE if is_fin else _BPA_SPINE,
        subtotal_codes=_FIN_BPA_SUBTOTALS if is_fin else _BPA_SUBTOTALS,
    )
    add_spine(
        group="Liabilities & Equity",
        stmt_type="BPP",
        spine=_FIN_BPP_SPINE if is_fin else _BPP_SPINE,
        subtotal_codes=_FIN_BPP_SUBTOTALS if is_fin else _BPP_SUBTOTALS,
    )
    add_spine(
        group="Cash Flow Statement",
        stmt_type="DFC",
        spine=_DFC_SPINE,
        subtotal_codes=_DFC_SUBTOTALS,
    )

    return ModelMappingDefinition(
        preset_id=SYSTEM_DEFAULT_PRESET_ID,
        name="Default",
        description="System default model mapping shipped with CVMAnalytics.",
        origin="system",
        default_mapping_version=DEFAULT_MAPPING_VERSION,
        entries=tuple(entries),
    )


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
    to ``quarters_per_year`` per annual year).  Quarters from years that are
    *strictly newer* than the latest selected annual year are also included
    (up to ``quarters_per_year`` each) so that current-year ITR-only periods
    (e.g. ``1Q26`` when 2026 DFP has not been filed) appear in the workbook.

    The combined set is sorted chronologically:
    ``1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ..., 4Q25, 2025, 1Q26, 2Q26``.
    """
    annual_periods = sorted(
        [p for p in all_periods if _is_annual_period(p)],
        key=_period_sort_key,
    )
    selected_annuals = annual_periods[-annuals:] if annuals > 0 else []
    selected_years = {int(a) for a in selected_annuals}
    # Quarters from years strictly newer than the last selected annual are
    # always included so that ITR-only current-year data surfaces automatically.
    latest_selected_annual = max(selected_years, default=0)

    quarter_buckets: dict[int, list[str]] = {}
    for p in all_periods:
        parsed = _parse_quarter(p)
        if parsed is None:
            continue
        year, _ = parsed
        if year in selected_years or year > latest_selected_annual:
            quarter_buckets.setdefault(year, []).append(p)

    selected_quarters: list[str] = []
    for year, qs in quarter_buckets.items():
        qs_sorted = sorted(qs, key=_period_sort_key)
        selected_quarters.extend(qs_sorted[-quarters_per_year:] if quarters_per_year > 0 else qs_sorted)

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
        Extra statement types to include (e.g. ``["DMPL"]``).
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
        period_scope_label: Optional[str] = None,
        itr_only_years: Optional[list[int]] = None,
        model_mapping: Optional[ModelMappingDefinition | dict] = None,
        mapping_validation_issues: Optional[list[MappingValidationIssue | dict]] = None,
        engine: Optional[Any] = None,
        financial_evidence: Optional[dict] = None,
        evidence_only_reason: Optional[str] = None,
    ):
        self.info = company_info or {}
        self.engine = engine
        self.financial_evidence = financial_evidence or {}
        self.evidence_only_reason = evidence_only_reason
        self.stmts = statements or {}
        self.kpis = kpis_df if kpis_df is not None else pd.DataFrame()
        self.extra = extra_sheets or []
        self.statement_type = statement_type
        self.period_window = period_window
        self.period_scope_label: Optional[str] = period_scope_label
        self.itr_only_years: list[int] = list(itr_only_years or [])
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
        self._mapping_audit_rows: list[dict[str, object]] = []
        self._mapping_validation_issues: list[MappingValidationIssue] = []
        for issue in mapping_validation_issues or []:
            if isinstance(issue, MappingValidationIssue):
                self._mapping_validation_issues.append(issue)
            elif isinstance(issue, dict):
                self._mapping_validation_issues.append(
                    MappingValidationIssue(
                        severity=str(issue.get("severity") or "warning"),
                        code=str(issue.get("code") or "validation_issue"),
                        message=str(issue.get("message") or ""),
                        target_id=(str(issue.get("target_id")) if issue.get("target_id") else None),
                        source_id=(str(issue.get("source_id")) if issue.get("source_id") else None),
                    )
                )

        # Financial-firm detection — True when GICS sector is Financials or
        # company_type indicates a bank/insurer. The generic industrial spine
        # is not designed for financial institutions; a banner + check row
        # surface this so the workbook is never silently misleading.
        self._is_financial_firm: bool = is_financial_company_info(company_info)
        self._model_labels: dict[str, str] = (
            _FIN_MODEL_LINE_LABELS if self._is_financial_firm else _MODEL_LINE_LABELS
        )
        if isinstance(model_mapping, ModelMappingDefinition):
            self.model_mapping = model_mapping
        elif isinstance(model_mapping, dict):
            self.model_mapping = ModelMappingDefinition.from_payload(model_mapping)
        else:
            self.model_mapping = build_default_model_mapping(
                company_info,
                is_financial_firm=self._is_financial_firm,
            )

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

        if self.evidence_only_reason:
            for stype in self.stmts:
                self._write_raw_statement(stype)
            self._write_metadata_sheet(scope=stmt_t)
            ws = self._wb.add_worksheet(README_SHEET)
            ws.set_column('A:A', 110)
            ws.write_string(0, 0, 'Financial evidence only — analytical model unavailable', self._fmt['raw_header'])
            ws.write_string(2, 0, self.evidence_only_reason, self._fmt['source_note'])
            ws.write_string(4, 0, 'Review financial_qa and the source_observations/value_lineage audit sheets. Missing values remain unavailable.', self._fmt['source_note'])
            ws.write_string(6, 0, self.period_scope_label or '', self._fmt['source_note'])
            self._reorder_visible_sheets()
        elif stmt_t:
            # Scoped single-statement export — minimal workbook.
            self._write_raw_statement(stmt_t)
            self._write_metadata_sheet(scope=stmt_t)
        else:
            # Full export. Raw sheets are written first so the Model sheet
            # can reference their final row coordinates via formulas.
            for stype in ("DRE", "BPA", "BPP", "DFC"):
                self._write_raw_statement(stype)
            for stype in ("DMPL",):
                if stype in self.stmts and not self.stmts[stype].empty:
                    self._write_raw_statement(stype)
            self._write_raw_kpi_sheet()
            self._write_metadata_sheet(scope=None)
            # Visible analyst sheets are written last so they appear at
            # the top of the workbook (xlsxwriter ordering).
            self._write_readme_sheet()
            self._write_model_sheet()
            self._write_mapping_audit_sheet()
            self._reorder_visible_sheets()

        self._write_financial_evidence()
        self._wb.close()
        payload = buf.getvalue()

        # Post-write validator — catches any error string that slipped
        # through (e.g. malformed formula references).
        if not stmt_t:
            self._validate_no_errors(payload)

        return payload

    def _write_financial_evidence(self) -> None:
        """Keep source durations and unavailable-cell reasons outside model formulas."""
        for key, sheet_name in [('qa_events', 'financial_qa'), ('source_observations', 'source_observations'), ('value_lineage', 'value_lineage')]:
            records = self.financial_evidence.get(key, [])
            if not records:
                continue
            rows = []
            for record in records:
                row = dict(record)
                if 'source_inputs' in row:
                    row['source_ids'] = [source.get('observation_id') for source in row.pop('source_inputs')]
                rows.append(row)
            columns = list(dict.fromkeys(column for row in rows for column in row))
            ws = self._wb.add_worksheet(sheet_name)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(rows), len(columns) - 1)
            for col, name in enumerate(columns):
                ws.write_string(0, col, name, self._fmt['raw_header'])
                ws.set_column(col, col, 24)
                for idx, row in enumerate(rows, start=1):
                    value = row.get(name)
                    if value is None:
                        continue
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, ensure_ascii=False)
                    # Source values stay text-exact, and untrusted labels cannot become formulas.
                    ws.write_string(idx, col, str(value), self._fmt['raw_text'])
            if key != 'qa_events':
                ws.hide()

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
            "raw_per_share": fmt(**base_small, num_format='#,##0.00####;(#,##0.00####);-', align="right"),
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

        # Index: CD_CONTA / LINE_ID_BASE -> 1-indexed row number in the raw sheet so the
        # Model sheet can build cross-sheet formula references.
        # Also build a STANDARD_NAME -> row index for fallback mapping.
        cd_to_row: dict[str, int] = {}
        line_id_to_row: dict[str, int] = {}
        std_name_to_row: dict[str, int] = {}
        first_row_by_code: dict[str, int] = {}
        period_row_by_code: dict[tuple[str, str], int] = {}
        period_to_col: dict[str, int] = {}
        for c_idx, p in enumerate(period_cols, start=len(id_cols)):
            period_to_col[str(p)] = c_idx

        for r_idx, (_, row) in enumerate(df.iterrows(), start=1):
            cd = str(row.get("CD_CONTA", "")).strip()
            line_id = str(row.get("LINE_ID_BASE", "") or "").strip()
            std = str(row.get("STANDARD_NAME", "") or "").strip()
            is_sub = cd in subtotals
            excel_row = r_idx + 1
            if cd:
                cd_to_row[cd] = excel_row  # 1-indexed Excel row
            if line_id:
                line_id_to_row[line_id] = excel_row
            if std and std not in std_name_to_row:
                std_name_to_row[std] = excel_row
            codes = tuple(dict.fromkeys(code for code in (cd, line_id) if code))
            for code in codes:
                first_row_by_code.setdefault(code, excel_row)
                for period in period_cols:
                    key = (code, str(period))
                    if key not in period_row_by_code and _is_safe_number(row.get(period)):
                        period_row_by_code[key] = excel_row

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
                    number_format = self._fmt["raw_num_sub"] if is_sub else self._fmt["raw_num"]
                    if stmt_type == 'DRE' and (cd == '3.99' or cd.startswith('3.99.')):
                        number_format = self._fmt['raw_per_share']
                    ws.write_number(r_idx, c_idx, float(val), number_format)

        ws.freeze_panes(1, min(2, len(id_cols)))
        ws.hide_gridlines(2)
        # Auto-filter for analyst convenience.
        ws.autofilter(0, 0, len(df), len(all_cols) - 1)
        ws.hide()  # raw sheets hidden by default

        self._raw_index[stmt_type] = {
            "sheet_name": sheet_name,
            "cd_to_row": cd_to_row,
            "line_id_to_row": line_id_to_row,
            "std_name_to_row": std_name_to_row,
            "first_row_by_code": first_row_by_code,
            "period_row_by_code": period_row_by_code,
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
            k for k in ("DRE", "BPA", "BPP", "DFC", "DMPL")
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
                                   "DRE 3.99 per-share accounts remain BRL/share; see source_observations"),
            ("Financial QA", str(len(self.financial_evidence.get('qa_events', []))),
             "See financial_qa; absence of events is not financial acceptance" if self.financial_evidence.get('value_lineage') else
             "Legacy source/period evidence unavailable; explicit refresh required"),
            ("Model scale",        "R$ mm (millions)",
                                   "Model sheet divides CVM source by 1,000"),
            ("Sign convention",    "Costs / expenses appear negative in CVM source", ""),
            ("D&A on DFC",         "CD_CONTA 6.01.01.* filtered by 'depreci' (excludes financial amortisation)",
                                   "EBITDA = EBIT + D&A"),
            ("Window — annual",    str(self.period_window[0]), ""),
            ("Window — quarters/year", str(self.period_window[1]), ""),
            ("Export scope",       self.period_scope_label or "—", "Selected at export time"),
            ("Analytical years", ", ".join(map(str, self.financial_evidence.get('analytical_years', []))) or "—",
             "Complete-period scope used for the full workbook's analytical inputs"),
            ("Evidence years", ", ".join(map(str, self.financial_evidence.get('evidence_years', []))) or "—",
             "Local evidence discovery; audit sheets contain available source and QA records, with no completeness guarantee"),
            ("Mapping preset",      self.model_mapping.name, self.model_mapping.preset_id),
            ("Mapping version",     self.model_mapping.default_mapping_version, self.model_mapping.origin),
            ("ITR-only years",
             ", ".join(str(y) for y in self.itr_only_years) if self.itr_only_years else "none",
             "Years with quarterly ITR data but no closed annual DFP"),
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
        checks_present = (
            "Balance Sheet Tie, Cash Flow Tie, Net Income Tie, "
            "Period Completeness, Critical Line Availability, "
            "Formula Error Scan."
        )

        section_rows = [
            ("Main sheet",
             "`Model` — analyst-curated single sheet with Income Statement, "
             "Balance Sheet, Cash Flow Statement, KPIs, Checks, and Source / "
             "Data Quality blocks."),
            ("Period window",
             f"Annual: last {self.period_window[0]} fiscal years "
             f"({self.period_scope_label or 'default'} scope). "
             f"Quarterly: up to {self.period_window[1]} quarters per included "
             "annual year, interleaved chronologically "
             "(e.g. 1Q21, 2Q21, 3Q21, 4Q21, 2021, 1Q22, ...). "
             + (
                 f"ITR-only year(s) included: {', '.join(str(y) for y in self.itr_only_years)}. "
                 "These years have quarterly ITR data but no closed annual DFP yet."
                 if self.itr_only_years else ""
             )),
            ("Units",
             "Model sheet: R$ mm (millions). CVM source: R$ mil (thousands); "
             "divided by 1,000 in the Model view. Raw sheets keep R$ mil."),
            ("Hidden sheets",
             "Right-click any visible sheet tab → Unhide… to audit. "
             "Sheets actually present in this workbook: "
             + ", ".join(raw_sheets_present) + "."),
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

    def _populate_model_row_indices(self, periods: list[str]) -> None:
        """Pre-computes the row index of every mapped/spine target ID on the Model sheet

        to resolve forward/backward cell references in formulas.
        """
        # Replicates the row cursor increments on the Model sheet
        header_row = 23
        row = header_row + 4

        # 1. Income Statement
        _is_fin = self._is_financial_firm
        stmt_type = "DRE"
        if self._raw_index.get(stmt_type) is not None:
            row += 2  # heading
            from src.financials.excel_exporter import _FIN_DRE_SPINE, _DRE_SPINE  # noqa: PLC0415
            spine = _FIN_DRE_SPINE if _is_fin else _DRE_SPINE
            mapped_entries = self._mapping_entries("Income Statement", stmt_type)
            if mapped_entries:
                for entry in mapped_entries:
                    self._model_rows[entry.target_id] = row + 1
                    row += 1
                row += 1
            else:
                for code, _ in spine:
                    self._model_rows[f"{stmt_type}:{code}"] = row + 1
                    row += 1
                row += 1

        # 2. EBITDA and D&A
        if self._raw_index.get("DFC") is not None and not (self.stmts.get("DFC") is None or self.stmts["DFC"].empty):
            # D&A row
            self._model_rows["COMP:DA"] = row + 1
            row += 1
            # EBITDA row
            self._model_rows["COMP:EBITDA"] = row + 1
            row += 2  # returns row + 2

        # 3. Balance Sheet
        if not (("BPA" not in self.stmts or self.stmts["BPA"].empty)
                and ("BPP" not in self.stmts or self.stmts["BPP"].empty)):
            row += 2  # heading

            def simulate_block(stype, spine_list, sub_label):
                nonlocal row
                idx = self._raw_index.get(stype)
                if idx is None:
                    return
                row += 1  # sub_label
                m_entries = self._mapping_entries(sub_label, stype)
                if m_entries:
                    for entry in m_entries:
                        self._model_rows[entry.target_id] = row + 1
                        row += 1
                    row += 1
                    return
                for code, _ in spine_list:
                    self._model_rows[f"{stype}:{code}"] = row + 1
                    row += 1
                row += 1

            from src.financials.excel_exporter import _FIN_BPA_SPINE, _BPA_SPINE, _FIN_BPP_SPINE, _BPP_SPINE  # noqa: PLC0415
            if self._is_financial_firm:
                simulate_block("BPA", _FIN_BPA_SPINE, "Assets")
                simulate_block("BPP", _FIN_BPP_SPINE, "Liabilities & Equity")
            else:
                simulate_block("BPA", _BPA_SPINE, "Assets")
                simulate_block("BPP", _BPP_SPINE, "Liabilities & Equity")

        # 4. Cash Flow Statement
        stmt_type = "DFC"
        if self._raw_index.get(stmt_type) is not None:
            from src.financials.excel_exporter import _DFC_SPINE  # noqa: PLC0415
            spine = _DFC_SPINE
            row += 2  # heading
            mapped_entries = self._mapping_entries("Cash Flow Statement", stmt_type)
            if mapped_entries:
                for entry in mapped_entries:
                    self._model_rows[entry.target_id] = row + 1
                    row += 1
                row += 1
            else:
                for code, _ in spine:
                    self._model_rows[f"{stmt_type}:{code}"] = row + 1
                    row += 1
                row += 1

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
        self._populate_model_row_indices(periods)

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
        # Row 12 (0-indexed, Excel 13): spacer in the hidden info block for
        # industrial firms; visible financial-institution info banner for banks.
        if self._is_financial_firm:
            ws.set_row(12, 18)
            ws.write(
                12, 1,
                "ℹ Financial institution — financial-sector spine active. "
                "Net Income: 3.11 → 3.09 fallback. Cash = BPA 1.01. "
                "Industrial KPIs (EBITDA, Current Ratio, Net Debt/EBITDA) not shown.",
                f["check_label"],
            )
            for c_idx in range(2, max(3, 3 + len(periods))):
                ws.write_blank(12, c_idx, None, f["check_label"])
        else:
            ws.set_row(12, 14, None, {"level": 1, "hidden": True})  # spacer
        # Company info block ships grouped + hidden by default (product
        # decision): the analyst surface starts at the period header. The
        # outline "+" in the left margin expands it (Excel rows 14–22).
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
        _is_fin = self._is_financial_firm
        cur = self._write_model_section(
            ws, cur, periods,
            heading="Income Statement",
            stmt_type="DRE",
            spine=_FIN_DRE_SPINE if _is_fin else _DRE_SPINE,
            subtotal_codes=_FIN_DRE_SUBTOTALS if _is_fin else _DRE_SUBTOTALS,
            sign_hints=_FIN_DRE_SIGN_HINTS if _is_fin else _DRE_SIGN_HINTS,
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

        # KPIs
        cur = self._write_model_kpis(ws, cur, periods)

        # Checks
        cur = self._write_model_checks(ws, cur, periods)

        # Source / Data Quality
        cur = self._write_model_source(ws, cur, periods)

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

    def _resolve_raw_row_for_p(self, stmt_type: str, code: str, period: str) -> Optional[int]:
        """Look up the 1-indexed Excel row in the raw sheet for a code in a specific period.
        Handles description changes / duplicate codes dynamically by picking the row
        containing a safe number for the target period.
        """
        idx = self._raw_index.get(stmt_type)
        code_key = str(code or "").strip()
        if idx is not None and code_key:
            period_row_by_code = idx.get("period_row_by_code")
            first_row_by_code = idx.get("first_row_by_code")
            if period_row_by_code is not None and first_row_by_code is not None:
                row = period_row_by_code.get((code_key, str(period)))
                if row is not None:
                    return row
                return first_row_by_code.get(code_key)

        df = self.stmts.get(stmt_type)
        if df is None or df.empty:
            return None
        
        matching_rows = []
        for r_idx, (_, row) in enumerate(df.iterrows(), start=2): # 2-indexed (header is row 1)
            cd = str(row.get("CD_CONTA", "")).strip()
            line_id = str(row.get("LINE_ID_BASE") or "").strip()
            if cd == code or line_id == code:
                val = row.get(period)
                if _is_safe_number(val):
                    return r_idx
                matching_rows.append(r_idx)
        
        if matching_rows:
            return matching_rows[0]
        return None

    def _mapping_entries(self, group: str, stmt_type: str) -> list[ModelMappingEntry]:
        return [
            entry
            for entry in self.model_mapping.entries
            if entry.group == group and entry.statement_type == stmt_type
        ]

    def _get_ltm_quarters(self, p: str, periods: list[str]) -> Optional[list[str]]:
        """Return the column letters for the 4 quarters ending at period p (inclusive).
        
        If p is a quarter (e.g. "1Q25"), we need "1Q25", "4Q24", "3Q24", "2Q24".
        All 4 must exist in `periods`. If any is missing, returns None.
        """
        parsed = _parse_quarter(p)
        if parsed is None:
            return None
        year, q = parsed
        
        target_tuples = []
        cy, cq = year, q
        for _ in range(4):
            target_tuples.append((cy, cq))
            cq -= 1
            if cq == 0:
                cq = 4
                cy -= 1
                
        col_letters = []
        for ty, tq in target_tuples:
            found_col = None
            for c_idx, p_lbl in enumerate(periods, start=3):
                p_parsed = _parse_quarter(p_lbl)
                if p_parsed == (ty, tq):
                    found_col = xlsxwriter.utility.xl_col_to_name(c_idx)
                    break
            if found_col is None:
                return None
            col_letters.append(found_col)
        return col_letters

    def _get_stock_col(self, p: str, periods: list[str]) -> str:
        """Return the column letter to use for balance sheet / stock variables for period p.
        
        If p is a 4Q column (e.g. "4Q25"), returns the column letter of the corresponding
        annual period ("2025") if present in `periods`. Otherwise returns the column of p itself.
        """
        c_idx_self = 3 + periods.index(p)
        col_self = xlsxwriter.utility.xl_col_to_name(c_idx_self)
        
        parsed = _parse_quarter(p)
        if parsed is not None:
            year, q = parsed
            if q == 4:
                # Look for annual column for this year
                for c_idx, p_lbl in enumerate(periods, start=3):
                    if _is_annual_period(p_lbl) and str(p_lbl).strip() == str(year):
                        return xlsxwriter.utility.xl_col_to_name(c_idx)
        return col_self

    def _resolve_mapping_source(
        self,
        source: ModelMappingSource,
    ) -> tuple[int | None, str]:
        idx = self._raw_index.get(source.statement_type)
        if idx is None:
            return None, "statement_missing"
        row = idx.get("line_id_to_row", {}).get(source.line_id_base)
        if row is not None:
            return row, "line_id_base"
        cd = source.cd_conta or source.line_id_base
        if cd:
            row = idx.get("cd_to_row", {}).get(cd)
            if row is not None:
                return row, "cd_conta"
        if source.label_snapshot:
            row = idx.get("std_name_to_row", {}).get(source.label_snapshot)
            if row is not None:
                return row, "label_snapshot"
        return None, "missing"

    def _write_mapping_entry_values(
        self,
        ws,
        *,
        row: int,
        periods: list[str],
        entry: ModelMappingEntry,
        is_sub: bool,
    ) -> tuple[bool, list[str]]:
        f = self._fmt
        from src.financials.formulas import is_formula_row, get_formula_definitions  # noqa: PLC0415
        is_fin = self._is_financial_firm

        if is_formula_row(entry.target_id, is_fin):
            formula_def = get_formula_definitions(is_fin)[entry.target_id]
            deps = formula_def["dependencies"]
            reqs = formula_def["required"]
            
            all_reqs_in_model = all(r in self._model_rows for r in reqs)
            warnings = []
            for dep_id in reqs:
                if dep_id not in self._model_rows:
                    warnings.append(f"required dependency {dep_id} is missing from Model layout")
            for dep_id in deps:
                if dep_id not in reqs and dep_id not in self._model_rows:
                    warnings.append(f"optional dependency {dep_id} is missing from Model layout")

            resolved_formula = ""
            for c_idx, p in enumerate(periods, start=3):
                is_y = _is_annual_period(p)
                cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                            else f["num_subtotal"] if is_sub
                            else f["num_linked_y"] if is_y
                            else f["num_linked"])
                if not all_reqs_in_model:
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue

                col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
                req_refs = [f"{col_letter}{self._model_rows[dep_id]}" for dep_id in reqs if dep_id in self._model_rows]
                
                # Check optional deps mapping to see if they are active
                entries_by_id = {e.target_id: e for e in self.model_mapping.entries}
                opt_refs = []
                for dep_id in deps:
                    if dep_id not in reqs and dep_id in self._model_rows:
                        dep_entry = entries_by_id.get(dep_id)
                        if dep_entry and dep_entry.sources:
                            opt_refs.append(f"{col_letter}{self._model_rows[dep_id]}")

                all_refs = req_refs + opt_refs
                if not all_refs:
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue

                if req_refs:
                    cond_check = "AND(" + ",".join(f"ISNUMBER({ref})" for ref in req_refs) + ")"
                else:
                    cond_check = "OR(" + ",".join(f"ISNUMBER({ref})" for ref in opt_refs) + ")"

                sum_expression = "SUM(" + ",".join(all_refs) + ")"
                formula = f'=IF({cond_check},{sum_expression},"")'
                if not resolved_formula:
                    resolved_formula = formula
                ws.write_formula(row, c_idx, formula, cell_fmt)

            self._mapping_audit_rows.append(
                {
                    "target_id": entry.target_id,
                    "target_label": entry.target_label,
                    "group": entry.group,
                    "statement_type": entry.statement_type,
                    "operation": "formula",
                    "sources": "; ".join(deps),
                    "resolved": "yes" if all_reqs_in_model else "no",
                    "resolved_formula": resolved_formula,
                    "warnings": "; ".join(warnings),
                }
            )
            return all_reqs_in_model, warnings

        # Lazy initialization of ModelResolver helper properties
        if not hasattr(self, "_overrides"):
            from src.financials.resolver import ModelResolver
            resolver = ModelResolver(self.engine)
            self._overrides = resolver.get_overrides(self.info.get("cd_cvm", 0)) if self.engine else {}
            self._aliases = resolver.get_aliases() if self.engine else []

        target_overrides = self._overrides.get(entry.target_id, {})
        row_resolved = bool(entry.sources) or bool(target_overrides)
        overridden_periods: list[str] = []
        warnings: list[str] = []
        if entry.operation not in VALID_MAPPING_OPERATIONS:
            warnings.append(f"invalid operation: {entry.operation}")
        if not entry.sources:
            warnings.append("no source lines mapped")
        if entry.operation == "direct" and len(entry.sources) > 1:
            warnings.append("direct operation uses first source only")

        resolved_formula = ""
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = (f["num_subtotal_y"] if is_sub and is_y
                        else f["num_subtotal"] if is_sub
                        else f["num_linked_y"] if is_y
                        else f["num_linked"])
            if not row_resolved or entry.operation not in VALID_MAPPING_OPERATIONS:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue

            active_resolutions_for_p = []
            # A saved override (period first, then GLOBAL) replaces the preset sources for this period.
            override = target_overrides.get(str(p)) or target_overrides.get("GLOBAL")
            if override:
                overridden_periods.append(str(p))
                code = str(override["source_code"])
                sources_to_resolve = (ModelMappingSource(
                    statement_type=entry.statement_type,
                    line_id_base=code,
                    cd_conta=code,
                    label_snapshot=override.get("source_desc"),
                    sign=-1 if int(override.get("sign") or 1) < 0 else 1,
                ),)
            else:
                sources_to_resolve = entry.sources[:1] if entry.operation == "direct" else entry.sources
            for source in sources_to_resolve:
                raw_row = self._resolve_raw_row_for_p(source.statement_type, source.line_id_base, p)
                if raw_row is not None:
                    s_idx = self._raw_index.get(source.statement_type)
                    raw_col = s_idx["period_to_col"].get(p) if s_idx else None
                    if raw_col is not None:
                        active_resolutions_for_p.append((source, raw_row, raw_col, s_idx))

            if not active_resolutions_for_p:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue

            cond_terms = []
            math_terms = []
            for source, raw_row, raw_col, s_idx in active_resolutions_for_p:
                cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                safe_sheet = str(s_idx["sheet_name"]).replace("'", "''")
                cond_terms.append(f"'{safe_sheet}'!{cell_ref}<>\"\"")
                
                term = f"'{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                if (override or entry.operation == "sum_with_sign") and source.sign < 0:
                    term = f"-{term}"
                elif math_terms:
                    term = f"+{term}"
                math_terms.append(term)

            cond_expr = "OR(" + ",".join(cond_terms) + ")"
            if len(cond_terms) == 1:
                cond_expr = cond_terms[0]
            math_expr = "".join(math_terms)
            formula = f"=IF({cond_expr},{math_expr},\"\")"
            if not resolved_formula:
                resolved_formula = formula
            ws.write_formula(row, c_idx, formula, cell_fmt)

        if overridden_periods:
            warnings.append("manual override applied for periods: " + ", ".join(overridden_periods))
        self._mapping_audit_rows.append(
            {
                "target_id": entry.target_id,
                "target_label": entry.target_label,
                "group": entry.group,
                "statement_type": entry.statement_type,
                "operation": entry.operation,
                "sources": "; ".join(
                    f"{source.statement_type}:{source.line_id_base}"
                    + (f" ({source.label_snapshot})" if source.label_snapshot else "")
                    + (", sign=-1" if source.sign < 0 else "")
                    for source in entry.sources
                ),
                "resolved": "yes" if row_resolved else "no",
                "resolved_formula": resolved_formula,
                "warnings": "; ".join(warnings),
            }
        )
        return row_resolved, warnings

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
        mapped_entries = self._mapping_entries(heading, stmt_type)
        if mapped_entries:
            for entry in mapped_entries:
                code = entry.target_id.split(":", 1)[1] if ":" in entry.target_id else entry.target_id
                label = entry.target_label or self._model_labels.get(code, code)
                is_sub = bool(entry.is_subtotal)
                if is_sub:
                    suffix = " (=)"
                else:
                    hint = sign_hints.get(code) if sign_hints else None
                    suffix = f" ({hint})" if hint else ""
                display = ("    " * entry.indent_level) + label + suffix

                ws.set_row(row, 14)
                ws.write(row, 1, display,
                         f["label_subtotal"] if is_sub else f["label_body"])

                row_resolved, _warnings = self._write_mapping_entry_values(
                    ws,
                    row=row,
                    periods=periods,
                    entry=entry,
                    is_sub=is_sub,
                )
                if not row_resolved:
                    unmapped.append(code)
                self._model_rows[entry.target_id] = row + 1
                row += 1

            return row + 1

        for code, indent in spine:
            label = self._model_labels.get(code, code)
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
            mapped_entries = self._mapping_entries(sub_label, stype)
            if mapped_entries:
                for entry in mapped_entries:
                    code = entry.target_id.split(":", 1)[1] if ":" in entry.target_id else entry.target_id
                    label = entry.target_label or self._model_labels.get(code, code)
                    is_sub = bool(entry.is_subtotal)
                    display = ("    " * entry.indent_level) + label + (" (=)" if is_sub else "")
                    ws.set_row(row, 14)
                    ws.write(row, 1, display,
                             f["label_subtotal"] if is_sub else f["label_body"])
                    row_resolved, _warnings = self._write_mapping_entry_values(
                        ws,
                        row=row,
                        periods=periods,
                        entry=entry,
                        is_sub=is_sub,
                    )
                    if not row_resolved:
                        unmapped.append(code)
                    self._model_rows[entry.target_id] = row + 1
                    row += 1
                row += 1
                return
            for code, indent in spine:
                label = self._model_labels.get(code, code)
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

        if self._is_financial_firm:
            block("BPA", _FIN_BPA_SPINE, _FIN_BPA_SUBTOTALS, "Assets")
            block("BPP", _FIN_BPP_SPINE, _FIN_BPP_SUBTOTALS, "Liabilities & Equity")
        else:
            block("BPA", _BPA_SPINE, _BPA_SUBTOTALS, "Assets")
            block("BPP", _BPP_SPINE, _BPP_SUBTOTALS, "Liabilities & Equity")

        return row

    def _write_model_da_and_ebitda(self, ws, start_row: int, periods: list[str]) -> int:
        idx = self._raw_index.get("DFC")
        if idx is None:
            return start_row
        f = self._fmt
        dfc_df = self.stmts.get("DFC")
        if dfc_df is None or dfc_df.empty:
            return start_row

        # Collect mapped D&A raw rows from mapping
        da_sources = []
        for entry in self.model_mapping.entries:
            if entry.target_id in ("DFC:6.01.01.02", "DFC:6.01.01.03") or "depreci" in entry.target_label.lower():
                for source in entry.sources:
                    raw_row, method = self._resolve_mapping_source(source)
                    if raw_row is not None:
                        da_sources.append((source, raw_row, method, True))

        # Fallback to description matching if no mapped sources resolved
        if not da_sources:
            for r_pos, (_, row_data) in enumerate(dfc_df.iterrows(), start=1):
                cd = str(row_data.get("CD_CONTA", "")).strip()
                ds = str(row_data.get("DS_CONTA", "") or "").lower()
                if cd.startswith("6.01.01") and "depreci" in ds:
                    source = ModelMappingSource(
                        statement_type="DFC",
                        line_id_base=cd,
                        cd_conta=cd,
                        label_snapshot=row_data.get("DS_CONTA")
                    )
                    da_sources.append((source, r_pos + 1, "description_fallback", False))

        # Write D&A row
        row = start_row
        ws.set_row(row, 14)
        ws.write(row, 1, "    Depreciation & Amortization (D&A)",
                 f["label_body"])

        any_resolved = False
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = f["num_linked_y"] if is_y else f["num_linked"]

            # Filter for active sources in this period
            active_sources_for_p = []
            for source, _, method, is_mapped in da_sources:
                raw_row = self._resolve_raw_row_for_p(source.statement_type, source.line_id_base, p)
                if raw_row is not None:
                    s_idx = self._raw_index.get(source.statement_type)
                    raw_col = s_idx["period_to_col"].get(p) if s_idx else None
                    if raw_col is not None:
                        try:
                            val = dfc_df.iloc[raw_row - 2][p]
                            if _is_safe_number(val):
                                active_sources_for_p.append((source, raw_row, raw_col, s_idx, is_mapped))
                        except Exception:
                            pass

            # Check ambiguity for description-matched sources
            if active_sources_for_p:
                unmapped_actives = [item for item in active_sources_for_p if not item[4]]
                if len(unmapped_actives) > 1:
                    distinct_codes = {item[0].line_id_base for item in unmapped_actives}
                    if len(distinct_codes) > 1:
                        self._mapping_validation_issues.append(
                            MappingValidationIssue(
                                severity="warning",
                                code="ambiguous_da_sources",
                                message=f"Ambiguous D&A fallback candidates for period {p}: {', '.join(distinct_codes)}. Cell left blank.",
                            )
                        )
                        active_sources_for_p = []

            if not active_sources_for_p:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue

            any_resolved = True
            if len(active_sources_for_p) == 1:
                self._da_cd_conta = active_sources_for_p[0][0].cd_conta or active_sources_for_p[0][0].line_id_base

            cond_terms = []
            math_terms = []
            for source, raw_row, raw_col, s_idx, is_mapped in active_sources_for_p:
                cell_ref = xlsxwriter.utility.xl_rowcol_to_cell(raw_row - 1, raw_col)
                safe_sheet = str(s_idx["sheet_name"]).replace("'", "''")
                cond_terms.append(f"'{safe_sheet}'!{cell_ref}<>\"\"")
                
                term = f"'{safe_sheet}'!{cell_ref}/{_MODEL_SCALE_DIVISOR:.0f}"
                if math_terms:
                    term = f"+{term}"
                math_terms.append(term)

            cond_expr = "OR(" + ",".join(cond_terms) + ")"
            if len(cond_terms) == 1:
                cond_expr = cond_terms[0]
            math_expr = "".join(math_terms)
            formula = f"=IF({cond_expr},{math_expr},\"\")"
            ws.write_formula(row, c_idx, formula, cell_fmt)

        self._da_resolved = any_resolved
        self._model_rows["COMP:DA"] = row + 1
        row += 1

        # Write EBITDA = EBIT + D&A
        ebit_model_row = self._model_rows.get("DRE:3.05")
        ws.set_row(row, 14)
        ws.write(row, 1, "EBITDA (=)", f["label_subtotal"])
        for c_idx, p in enumerate(periods, start=3):
            is_y = _is_annual_period(p)
            cell_fmt = f["num_subtotal_y"] if is_y else f["num_subtotal"]
            da_model_row = self._model_rows.get("COMP:DA")
            if ebit_model_row is None or da_model_row is None:
                ws.write_blank(row, c_idx, None, cell_fmt)
                continue
            col_letter = xlsxwriter.utility.xl_col_to_name(c_idx)
            ebit_ref = f"{col_letter}{ebit_model_row}"
            da_ref = f"{col_letter}{da_model_row}"
            formula = f'=IF(AND(ISNUMBER({ebit_ref}),ISNUMBER({da_ref})),{ebit_ref}+{da_ref},"")'
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
            formula = f'=IF(AND(ISNUMBER({cfo_ref}),ISNUMBER({capex_ref})),{cfo_ref}+{capex_ref},"")'
            ws.write_formula(row, c_idx, formula, cell_fmt)
        self._model_rows["COMP:FCF"] = row + 1
        return row + 2

    def _write_model_kpis(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "KPIs / Ratios")

        is_fin = self._is_financial_firm
        rev = self._model_rows.get("DRE:3.01")
        gp = self._model_rows.get("DRE:3.03")
        ebit = self._model_rows.get("DRE:3.05")
        ebitda = self._model_rows.get("COMP:EBITDA")
        ta = self._model_rows.get("BPA:1")
        cfo = self._model_rows.get("DFC:6.01")
        capex = self._model_rows.get("DFC:6.02.01")
        fcf = self._model_rows.get("COMP:FCF")

        if is_fin:
            # Financial firm: NI resolves 3.11 first, fall back to 3.09
            ni = (self._model_rows.get("DRE:3.11")
                  or self._model_rows.get("DRE:3.09"))
            # Cash is BPA:1.01 for financial firms (not a sub-item of current assets)
            cash = self._model_rows.get("BPA:1.01")
            fin_inv = None
            # Equity is BPP:2.08 for financial firms
            eq = self._model_rows.get("BPP:2.08")
            ca = None
            cl = None
            st_debt = None
            lt_debt = None
        else:
            ni = self._model_rows.get("DRE:3.11")
            cash = self._model_rows.get("BPA:1.01.01")
            fin_inv = self._model_rows.get("BPA:1.01.02")
            ca = self._model_rows.get("BPA:1.01")
            cl = self._model_rows.get("BPP:2.01")
            st_debt = self._model_rows.get("BPP:2.01.04")
            lt_debt = self._model_rows.get("BPP:2.02.01")
            eq = self._model_rows.get("BPP:2.03")

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

        # Revenue Growth YoY
        def rev_growth(col_letter, c_idx):
            if rev is None:
                return None
            p = periods[c_idx - 3]
            if _is_annual_period(p):
                # Annual growth: compare with previous year's annual column
                try:
                    prev_year = str(int(p) - 1)
                    if prev_year in periods:
                        prev_col_idx = 3 + periods.index(prev_year)
                        prev_col = xlsxwriter.utility.xl_col_to_name(prev_col_idx)
                        cur_ref = f"{col_letter}{rev}"
                        prev_ref = f"{prev_col}{rev}"
                        return f'=IF(AND(ISNUMBER({cur_ref}),ISNUMBER({prev_ref}),{prev_ref}<>0),{cur_ref}/{prev_ref}-1,"")'
                except ValueError:
                    pass
                return None
            else:
                # Quarterly growth: LTM YoY growth
                parsed = _parse_quarter(p)
                if parsed is None:
                    return None
                year, q = parsed
                
                # Find the period label that matches (year - 1, q)
                prior_p = None
                for p_lbl in periods:
                    p_parsed = _parse_quarter(p_lbl)
                    if p_parsed == (year - 1, q):
                        prior_p = p_lbl
                        break
                if prior_p is None:
                    return None
                
                current_ltm_cols = self._get_ltm_quarters(p, periods)
                prior_ltm_cols = self._get_ltm_quarters(prior_p, periods)
                if not current_ltm_cols or not prior_ltm_cols:
                    return None
                
                cur_refs = [f"{c}{rev}" for c in current_ltm_cols]
                prior_refs = [f"{c}{rev}" for c in prior_ltm_cols]
                
                cond_cur = ",".join(f"ISNUMBER({r})" for r in cur_refs)
                cond_prior = ",".join(f"ISNUMBER({r})" for r in prior_refs)
                
                cur_sum = "SUM(" + ",".join(cur_refs) + ")"
                prior_sum = "SUM(" + ",".join(prior_refs) + ")"
                
                return f'=IF(AND({cond_cur},{cond_prior},{prior_sum}<>0),{cur_sum}/{prior_sum}-1,"")'

        write_kpi("Revenue Growth", rev_growth, True)

        def simple_ratio(num_row, den_row):
            def ratio_fn(col_letter, c_idx):
                if num_row is None or den_row is None:
                    return None
                num_ref = f"{col_letter}{num_row}"
                den_ref = f"{col_letter}{den_row}"
                return f'=IF(AND(ISNUMBER({num_ref}),ISNUMBER({den_ref}),{den_ref}<>0),{num_ref}/{den_ref},"")'
            return ratio_fn

        if is_fin:
            # NII = 3.03 for financial firms; replaces Gross Margin / EBIT
            write_kpi("NII Margin (NII / Revenue)", simple_ratio(gp, rev), True)
        else:
            write_kpi("Gross Margin", simple_ratio(gp, rev), True)
            write_kpi("EBITDA Margin", simple_ratio(ebitda, rev), True)
            write_kpi("EBIT Margin", simple_ratio(ebit, rev), True)

        write_kpi("Net Margin", simple_ratio(ni, rev), True)

        def return_on_equity(col_letter, c_idx):
            if ni is None or eq is None:
                return None
            p = periods[c_idx - 3]
            stock_col = self._get_stock_col(p, periods)
            if _is_annual_period(p):
                ni_ref = f"{col_letter}{ni}"
                eq_ref = f"{stock_col}{eq}"
                return f'=IF(AND(ISNUMBER({ni_ref}),ISNUMBER({eq_ref}),{eq_ref}<>0),{ni_ref}/{eq_ref},"")'
            else:
                ltm_cols = self._get_ltm_quarters(p, periods)
                if not ltm_cols:
                    return None
                ni_refs = [f"{c}{ni}" for c in ltm_cols]
                eq_ref = f"{stock_col}{eq}"
                cond = "AND(" + ",".join(f"ISNUMBER({r})" for r in ni_refs) + f",ISNUMBER({eq_ref}),{eq_ref}<>0)"
                ni_sum = "SUM(" + ",".join(ni_refs) + ")"
                return f'=IF({cond},{ni_sum}/{eq_ref},"")'

        write_kpi("Return on Equity (ROE)", return_on_equity, True)

        def return_on_assets(col_letter, c_idx):
            if ni is None or ta is None:
                return None
            p = periods[c_idx - 3]
            stock_col = self._get_stock_col(p, periods)
            if _is_annual_period(p):
                ni_ref = f"{col_letter}{ni}"
                ta_ref = f"{stock_col}{ta}"
                return f'=IF(AND(ISNUMBER({ni_ref}),ISNUMBER({ta_ref}),{ta_ref}<>0),{ni_ref}/{ta_ref},"")'
            else:
                ltm_cols = self._get_ltm_quarters(p, periods)
                if not ltm_cols:
                    return None
                ni_refs = [f"{c}{ni}" for c in ltm_cols]
                ta_ref = f"{stock_col}{ta}"
                cond = "AND(" + ",".join(f"ISNUMBER({r})" for r in ni_refs) + f",ISNUMBER({ta_ref}),{ta_ref}<>0)"
                ni_sum = "SUM(" + ",".join(ni_refs) + ")"
                return f'=IF({cond},{ni_sum}/{ta_ref},"")'

        write_kpi("Return on Assets (ROA)", return_on_assets, True)

        if not is_fin:
            def net_debt_to_ebitda(col_letter, c_idx):
                if (st_debt is None or lt_debt is None or cash is None or
                        fin_inv is None or ebitda is None):
                    return None
                p = periods[c_idx - 3]
                stock_col = self._get_stock_col(p, periods)
                st_ref = f"{stock_col}{st_debt}"
                lt_ref = f"{stock_col}{lt_debt}"
                cash_ref = f"{stock_col}{cash}"
                fin_ref = f"{stock_col}{fin_inv}"
                
                if _is_annual_period(p):
                    eb_ref = f"{col_letter}{ebitda}"
                    cond = f"AND(ISNUMBER({cash_ref}),ISNUMBER({eb_ref}),{eb_ref}<>0)"
                    return f'=IF({cond},(SUM({st_ref},{lt_ref})-SUM({cash_ref},{fin_ref}))/{eb_ref},"")'
                else:
                    eb_cols = self._get_ltm_quarters(p, periods)
                    if not eb_cols:
                        return None
                    eb_refs = [f"{c}{ebitda}" for c in eb_cols]
                    eb_cond = ",".join(f"ISNUMBER({r})" for r in eb_refs)
                    eb_sum = "SUM(" + ",".join(eb_refs) + ")"
                    cond = f"AND(ISNUMBER({cash_ref}),{eb_cond},{eb_sum}<>0)"
                    return f'=IF({cond},(SUM({st_ref},{lt_ref})-SUM({cash_ref},{fin_ref}))/{eb_sum},"")'

            write_kpi("Net Debt / EBITDA", net_debt_to_ebitda, False)

            def current_ratio(col_letter, c_idx):
                if ca is None or cl is None:
                    return None
                p = periods[c_idx - 3]
                stock_col = self._get_stock_col(p, periods)
                ca_ref = f"{stock_col}{ca}"
                cl_ref = f"{stock_col}{cl}"
                return f'=IF(AND(ISNUMBER({ca_ref}),ISNUMBER({cl_ref}),{cl_ref}<>0),{ca_ref}/{cl_ref},"")'

            write_kpi("Current Ratio", current_ratio, False)

        write_kpi("CFO / Revenue", simple_ratio(cfo, rev), True)
        write_kpi("FCF / Revenue", simple_ratio(fcf, rev), True)

        def capex_ratio(col_letter, c_idx):
            if capex is None or rev is None:
                return None
            capex_ref = f"{col_letter}{capex}"
            rev_ref = f"{col_letter}{rev}"
            return f'=IF(AND(ISNUMBER({capex_ref}),ISNUMBER({rev_ref}),{rev_ref}<>0),-{capex_ref}/{rev_ref},"")'

        write_kpi("Capex / Revenue", capex_ratio, True)

        return row + 1

    def _write_model_checks(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "Checks")

        is_fin = self._is_financial_firm
        ta = self._model_rows.get("BPA:1")
        tle = self._model_rows.get("BPP:2")
        # Financial firms have cash at BPA:1.01; industrial firms at BPA:1.01.01
        bs_cash = (self._model_rows.get("BPA:1.01")
                   if is_fin else self._model_rows.get("BPA:1.01.01"))
        cf_end_cash = self._model_rows.get("DFC:6.05.02")
        # NI tie: financial firms try 3.11 first, fall back to 3.09
        ni_dre = ((self._model_rows.get("DRE:3.11")
                   or self._model_rows.get("DRE:3.09"))
                  if is_fin else self._model_rows.get("DRE:3.11"))
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
            # IFERROR guards handle "-" strings in delta/ta cells (IFERROR
            # fallback from unmapped lines); without them ABS("-") = #VALUE!
            # propagates through SUMPRODUCT.
            d = row + 1  # Excel row holding the per-period delta cells
            ta_rng = f"{first_col_letter}{ta}:{last_col_letter}{ta}"
            tol = f"MAX(0.5,IFERROR(0.0005*ABS({ta_rng}),0.5))"
            ws.write_formula(
                row, 2,
                f'=IF(SUMPRODUCT(IFERROR(--(ABS({first_col_letter}{d}:{last_col_letter}{d})>{tol}),0))=0,"OK","ERROR")',
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
                f'=IF(SUMPRODUCT(IFERROR(--(ABS({first_col_letter}{row + 1}:{last_col_letter}{row + 1})>0.5),0))=0,"OK","WARNING")',
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
                f'=IF(SUMPRODUCT(IFERROR(--(ABS({first_col_letter}{row + 1}:{last_col_letter}{row + 1})>0.5),0))=0,"OK","WARNING")',
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
        if is_fin:
            critical_lines = [
                ("Financial Intermediation Revenue", "DRE:3.01"),
                ("Net Interest Income (NII)",        "DRE:3.03"),
                ("Pre-tax Income",                   "DRE:3.05"),
                ("Net Income",                       "DRE:3.11"),
                ("Total Assets",                     "BPA:1"),
                ("Total Liab. & Equity",             "BPP:2"),
                ("Cash",                             "BPA:1.01"),
                ("Equity",                           "BPP:2.08"),
                ("CFO",                              "DFC:6.01"),
                ("FCF",                              "COMP:FCF"),
            ]
        else:
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

    def _write_model_source(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._fmt
        row = self._write_section_heading(ws, start_row, "Source / Data Quality")
        info = self.info

        stmts_present = [k for k in ("DRE", "BPA", "BPP", "DFC", "DMPL")
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
            ("Financial QA", f"{len(self.financial_evidence.get('qa_events', []))} recorded event(s); see financial_qa and source_observations."
             if self.financial_evidence.get('value_lineage') else "Legacy source/period QA evidence unavailable; explicit refresh required."),
        ]
        # Surface unmapped spine codes per statement so the analyst can
        # see exactly which lines were not present in the raw filing.
        for stype in ("DRE", "BPA", "BPP", "DFC", "DMPL"):
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

    def _write_mapping_audit_sheet(self) -> None:
        ws = self._wb.add_worksheet(MAPPING_AUDIT_SHEET)
        ws.hide_gridlines(2)
        headers = [
            "Section",
            "Target ID",
            "Target label",
            "Statement",
            "Operation",
            "Sources",
            "Resolved",
            "Resolved formula",
            "Warnings",
        ]
        for c_idx, header in enumerate(headers):
            ws.write(0, c_idx, header, self._fmt["raw_header"])
            ws.set_column(c_idx, c_idx, 18 if c_idx != 5 else 60)

        row = 1
        for audit in self._mapping_audit_rows:
            values = [
                audit.get("group", ""),
                audit.get("target_id", ""),
                audit.get("target_label", ""),
                audit.get("statement_type", ""),
                audit.get("operation", ""),
                audit.get("sources", ""),
                audit.get("resolved", ""),
                audit.get("resolved_formula", ""),
                audit.get("warnings", ""),
            ]
            for c_idx, value in enumerate(values):
                ws.write(row, c_idx, str(value or ""), self._fmt["raw_text"])
            row += 1

        if self._mapping_validation_issues:
            row += 1
            issue_headers = ["Severity", "Code", "Target ID", "Source ID", "Message"]
            for c_idx, header in enumerate(issue_headers):
                ws.write(row, c_idx, header, self._fmt["raw_header"])
            row += 1
            for issue in self._mapping_validation_issues:
                values = [
                    issue.severity,
                    issue.code,
                    issue.target_id or "",
                    issue.source_id or "",
                    issue.message,
                ]
                for c_idx, value in enumerate(values):
                    ws.write(row, c_idx, str(value or ""), self._fmt["raw_text"])
                row += 1

        metadata = [
            ("Preset", self.model_mapping.name),
            ("Preset ID", self.model_mapping.preset_id),
            ("Origin", self.model_mapping.origin),
            ("Default mapping version", self.model_mapping.default_mapping_version),
        ]
        row += 1
        for label, value in metadata:
            ws.write(row, 0, label, self._fmt["raw_header"])
            ws.write(row, 1, str(value or ""), self._fmt["raw_text"])
            row += 1

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(0, len(self._mapping_audit_rows)), len(headers) - 1)
        ws.hide()

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
    }.get(stmt_type, set())
