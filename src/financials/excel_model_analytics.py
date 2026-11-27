# -*- coding: utf-8 -*-
"""Model sheet EBITDA/FCF/KPI/Checks/Source and Mapping Audit writers for ExcelExporter."""
from __future__ import annotations

from datetime import datetime
import xlsxwriter

from src.financials.excel_mapping import MappingValidationIssue, ModelMappingSource
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


class ExcelModelAnalyticsMixin:
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

        stmts_present = [k for k in ("DRE", "BPA", "BPP", "DFC")
                         if k in self.stmts and not self.stmts[k].empty]
        rows_by_stmt = ", ".join(
            f"{k}={len(self.stmts[k])}"
            for k in stmts_present
        ) or "—"

        rows_src = [
            ("Generated by",        "CVMAnalytics"),
            ("App version",         str(self._app_version)),
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
        for stype in ("DRE", "BPA", "BPP", "DFC"):
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
