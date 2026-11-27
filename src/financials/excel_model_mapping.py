# -*- coding: utf-8 -*-
"""Model sheet layout, mapping resolution, and primary statement section writers for ExcelExporter."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import xlsxwriter

from src.financials.excel_mapping import (
    VALID_MAPPING_OPERATIONS,
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


class ExcelModelMappingMixin:
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

            if self._is_financial_firm:
                simulate_block("BPA", _FIN_BPA_SPINE, "Assets")
                simulate_block("BPP", _FIN_BPP_SPINE, "Liabilities & Equity")
            else:
                simulate_block("BPA", _BPA_SPINE, "Assets")
                simulate_block("BPP", _BPP_SPINE, "Liabilities & Equity")

        # 4. Cash Flow Statement
        stmt_type = "DFC"
        if self._raw_index.get(stmt_type) is not None:
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
            ("GICS sector",        str(info.get("gics_sector") or "—")),
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
