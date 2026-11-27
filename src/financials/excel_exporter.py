# -*- coding: utf-8 -*-
"""src/financials/excel_exporter.py — Analyst-ready Excel exporter (v0.19.0).

Orchestrates workbook assembly across focused modules:
- ``excel_mapping_defaults.py``: spines, default model mapping, period & filename helpers
- ``excel_formats.py``: workbook cell styles
- ``excel_model_mapping.py``: Model sheet layout, mapping resolution, statement sections
- ``excel_model_analytics.py``: EBITDA, FCF, KPIs, Checks, Source, and Mapping Audit
"""
from __future__ import annotations

import io
import json
import math
from datetime import datetime
from typing import Any, Optional

import openpyxl
import pandas as pd
import xlsxwriter

from src.financials.excel_formats import ExcelFormatsMixin
from src.financials.excel_mapping import (
    DEFAULT_MAPPING_VERSION,
    SYSTEM_DEFAULT_PRESET_ID,
    VALID_MAPPING_OPERATIONS,
    MappingValidationIssue,
    ModelMappingDefinition,
    ModelMappingEntry,
    ModelMappingSource,
)
from src.financials.excel_mapping_defaults import (
    DEFAULT_PERIOD_WINDOW,
    MAPPING_AUDIT_SHEET,
    METADATA_SHEET,
    MODEL_SHEET,
    PALETTE,
    RAW_KPI_SHEET,
    README_SHEET,
    _ANNUAL_RX,
    _BPA_SPINE,
    _BPA_SUBTOTALS,
    _BPP_SPINE,
    _BPP_SUBTOTALS,
    _DFC_SPINE,
    _DFC_SUBTOTALS,
    _DRE_SIGN_HINTS,
    _DRE_SPINE,
    _DRE_SUBTOTALS,
    _FIN_BPA_SPINE,
    _FIN_BPA_SUBTOTALS,
    _FIN_BPP_SPINE,
    _FIN_BPP_SUBTOTALS,
    _FIN_DRE_SIGN_HINTS,
    _FIN_DRE_SPINE,
    _FIN_DRE_SUBTOTALS,
    _FIN_MODEL_LINE_LABELS,
    _LEGACY_TO_RAW,
    _MODEL_LINE_LABELS,
    _MODEL_SCALE_DIVISOR,
    _QUARTER_RX,
    _RAW_PREFIX,
    _REQUIRED_MODEL_CODES,
    _is_annual_period,
    _is_safe_number,
    _parse_quarter,
    _period_end_date,
    _period_sort_key,
    _pick_model_periods,
    _scaled,
    _stmt_subtotals,
    build_default_model_mapping,
    build_excel_file_stem,
    build_excel_filename,
    is_financial_company_info,
)
from src.financials.excel_model_analytics import ExcelModelAnalyticsMixin
from src.financials.excel_model_mapping import ExcelModelMappingMixin
from src.financials.statement_summary import build_general_summary_blocks

_DEFAULT_APP_VERSION: str = "unknown"


def set_default_app_version(version: str) -> None:
    """Register the host runtime version for workbook metadata without coupling src/ to desktop/."""
    global _DEFAULT_APP_VERSION
    _DEFAULT_APP_VERSION = str(version or "unknown")


class ExcelExportError(Exception):
    """Raised when workbook generation or formula/error validation fails."""


class ExcelExporter(ExcelFormatsMixin, ExcelModelMappingMixin, ExcelModelAnalyticsMixin):
    """Generates the analyst-ready company workbook.

Parameters
----------
company_info : dict
    Output of ``CVMReadService.get_company_info_dict(cd_cvm)``.
statements : dict[str, pd.DataFrame]
    Map of ``stmt_type -> wide pivot``.
kpis_df : pd.DataFrame
    Output of ``KPIBundle.quarterly_dataframe()``.
statement_type : str, optional
    If set, the workbook is scoped to a single statement.
period_window : (int, int), optional
    ``(annuals, quarters_per_year)``. Defaults to ``(5, 4)`` which
    produces the interleaved 5-year + 4-quarter Equatorial layout
    (~25 columns)."""

    def __init__(
        self,
        company_info: dict,
        statements: dict[str, pd.DataFrame],
        kpis_df: pd.DataFrame,
        statement_type: Optional[str] = None,
        period_window: tuple[int, int] = DEFAULT_PERIOD_WINDOW,
        period_scope_label: Optional[str] = None,
        itr_only_years: Optional[list[int]] = None,
        model_mapping: Optional[ModelMappingDefinition | dict] = None,
        mapping_validation_issues: Optional[list[MappingValidationIssue | dict]] = None,
        engine: Optional[Any] = None,
        financial_evidence: Optional[dict] = None,
        evidence_only_reason: Optional[str] = None,
        app_version: Optional[str] = None,
    ):
        self.info = company_info or {}
        self._app_version = str(app_version or _DEFAULT_APP_VERSION)
        self.engine = engine
        self.financial_evidence = financial_evidence or {}
        self.evidence_only_reason = evidence_only_reason
        self.stmts = statements or {}
        self.kpis = kpis_df if kpis_df is not None else pd.DataFrame()
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
            k for k in ("DRE", "BPA", "BPP", "DFC")
            if k in self.stmts and not self.stmts[k].empty
        )

        rows = [
            ("Company",            str(info.get("company_name") or "—"), ""),
            ("CVM code",           str(info.get("cd_cvm") or "—"),       ""),
            ("Ticker B3",          str(info.get("ticker_b3") or "—"),    ""),
            ("CNPJ",               str(info.get("cnpj") or "—"),         ""),
            ("CVM sector",         str(info.get("setor_cvm") or "—"),    ""),
            ("GICS sub-industry",  str(info.get("gics_sub_industry") or "—"), "Curated by CVMAnalytics; not an official MSCI/S&P classification"),
            ("Statements present", stmts_present, "Raw sheets in this workbook"),
            ("Generated at",       now_str, ""),
            ("Source",             "CVM — dados.cvm.gov.br", "DFP/ITR filings"),
            ("App",                f"CVMAnalytics {self._app_version}", ""),
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
