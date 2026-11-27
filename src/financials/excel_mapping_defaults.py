# -*- coding: utf-8 -*-
"""Default model mapping specs, spines, period selection, and formatting constants for Excel exports."""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from src.financials.excel_mapping import (
    DEFAULT_MAPPING_VERSION,
    SYSTEM_DEFAULT_PRESET_ID,
    VALID_MAPPING_OPERATIONS,
    ModelMappingDefinition,
    ModelMappingEntry,
    ModelMappingSource,
)

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


def _stmt_subtotals(stmt_type: str) -> set[str]:
    return {
        "DRE": _DRE_SUBTOTALS,
        "BPA": _BPA_SUBTOTALS,
        "BPP": _BPP_SUBTOTALS,
        "DFC": _DFC_SUBTOTALS,
    }.get(stmt_type, set())
