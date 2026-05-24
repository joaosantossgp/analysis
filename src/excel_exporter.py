# -*- coding: utf-8 -*-
"""
src/excel_exporter.py — Exportador Excel profissional para analistas.

Gera workbook com até 9 abas:
  CAPA · KPIs · DRE · BPA · BPP · DFC · DVA · DMPL · METADADOS

Uso standalone:
    exp = ExcelExporter(company_info, statements, kpis_df)
    excel_bytes = exp.export()   # → bytes para st.download_button ou salvar em disco

Uso no Streamlit:
    st.download_button("Baixar Excel", exp.export(),
                       file_name=f"{ticker}.xlsx",
                       mime="application/vnd.ms-excel")
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import xlsxwriter

from src.statement_summary import build_general_summary_blocks

try:
    from desktop.__version__ import __version__ as _APP_VERSION
except Exception:  # pragma: no cover - desktop package may be missing in some envs
    _APP_VERSION = "unknown"

# ──────────────────────────────────────────────────────────────────────────────
# Paleta de cores
# ──────────────────────────────────────────────────────────────────────────────
C = {
    "azul_escuro":  "#1B3A5C",   # cabeçalhos de seção
    "azul_medio":   "#2E6DA4",   # subtotais
    "azul_claro":   "#D6E4F0",   # fundo subtotal
    "cinza_claro":  "#F2F2F2",   # linhas pares / placeholders
    "cinza_texto":  "#808080",   # texto de placeholders
    "verde_claro":  "#D5F0D5",   # delta positivo
    "vermelho_claro":"#FFD5D5",  # delta negativo
    "branco":       "#FFFFFF",
    "texto_escuro": "#1A1A1A",
    "vermelho_val": "#C0392B",   # fonte para valores negativos
    "capa_azul":    "#1B3A5C",
    "capa_acento":  "#2E86AB",
}

# Contas que são subtotais (negrito + fundo) nas demonstrações
_SUBTOTAIS = {
    "DRE": {"3.01", "3.03", "3.05", "3.07", "3.11"},
    "BPA": {"1", "1.01", "1.02"},
    "BPP": {"2", "2.01", "2.02", "2.03"},
    "DFC": {"6.01", "6.02", "6.03"},
    "DVA": {"7.08"},
    "DMPL": set(),
}

# Siglas → nomes completos para tab labels
_STMT_LABELS = {
    "DRE":  "DRE",
    "BPA":  "BPA",
    "BPP":  "BPP",
    "DFC":  "DFC",
    "DVA":  "DVA",
    "DMPL": "DMPL",
}

# Categorias de KPI na ordem desejada
_KPI_CATEGORY_ORDER = [
    "Rentabilidade", "Liquidez", "Endividamento",
    "Fluxo de Caixa", "Crescimento", "Valuation",
]

# ──────────────────────────────────────────────────────────────────────────────
# Financial Statement Model — analyst-ready single-sheet template
# Style contract extracted from the Wall Street Prep "Equatorial model.xlsx"
# reference workbook. See docs/releases/v0.18.1.md and the v0.19.0 notes for
# the visual layout: convention legend, title, company info block, period
# header, statement sections (Income Statement / Balance Sheet / Cash Flow /
# DVA / KPIs), checks, and source/data-quality block.
# ──────────────────────────────────────────────────────────────────────────────
_MODEL_SHEET_NAME = "Financial Statement Model"

# Scale conversion: CVM stores R$ mil (thousands); the model displays R$ mm
# (millions). One division by 1000 across all numeric writes.
_MODEL_SCALE_DIVISOR = 1000.0

# Section heading and indentation conventions
_DRE_SUBTOTAL_KEYS = {"3.01", "3.03", "3.05", "3.07", "3.11"}
_BPA_SUBTOTAL_KEYS = {"1", "1.01", "1.02"}
_BPP_SUBTOTAL_KEYS = {"2", "2.01", "2.02", "2.03"}
_DFC_SUBTOTAL_KEYS = {"6.01", "6.02", "6.03", "6.05"}
_DVA_SUBTOTAL_KEYS = {"7.08"}


def _period_sort_key(p: str) -> tuple[int, int, int]:
    """Sort key so periods order as: ..., 1Q24, 2Q24, 3Q24, 4Q24, 2024, 1Q25..."""
    s = str(p).strip()
    m_year = re.match(r"^(19|20)\d{2}$", s)
    if m_year:
        return (int(s), 5, 0)
    m_q = re.match(r"^([1-4])[QT](\d{2,4})$", s, flags=re.IGNORECASE)
    if m_q:
        q = int(m_q.group(1))
        y_str = m_q.group(2)
        y = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
        return (y, q, 1)
    return (9999, 9, 9)


def _indent_for_code(cd_conta: str) -> int:
    """4-space-per-level indentation by CVM CD_CONTA depth (root = 0)."""
    s = str(cd_conta or "").strip()
    if not s:
        return 0
    return max(0, s.count(".")) * 4


def _suffix_for_row(cd_conta: str, subtotals: set[str]) -> str:
    """Reference workbook uses `(=)` for subtotals/totals, `(+/-)` for body."""
    s = str(cd_conta or "").strip()
    if s in subtotals:
        return " (=)"
    return ""


def build_excel_file_stem(
    company_info: dict,
    *,
    generated_at: datetime | None = None,
    statement_type: str | None = None,
) -> str:
    """Retorna o file stem padrao usado pelos downloads de Excel."""
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


class ExcelExporter:
    """Gera workbook Excel profissional para uma empresa CVM.

    Parâmetros
    ----------
    company_info : dict
        Saída de CVMQueryLayer.get_company_info().
    statements   : dict[str, pd.DataFrame]
        Mapa {stmt_type: df_wide} — saída de CVMQueryLayer.get_statement().
    kpis_df      : pd.DataFrame
        Saída de kpi_engine.compute_all_kpis().
    extra_sheets : list[str], opcional
        Tipos adicionais a incluir (ex: ["DVA", "DMPL"]) se disponíveis.
    """

    def __init__(
        self,
        company_info: dict,
        statements: dict[str, pd.DataFrame],
        kpis_df: pd.DataFrame,
        extra_sheets: Optional[list[str]] = None,
        statement_type: Optional[str] = None,
    ):
        self.info       = company_info
        self.stmts      = statements
        self.kpis       = kpis_df
        self.extra      = extra_sheets or []
        self.statement_type = statement_type
        self._wb:  xlsxwriter.Workbook | None = None
        self._fmt: dict = {}

    # ──────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────

    def export(self, statement_type: Optional[str] = None) -> bytes:
        """Retorna o workbook como bytes. Pronto para download ou escrita em disco."""
        stmt_t = statement_type or self.statement_type
        buf = io.BytesIO()
        self._wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
        self._build_formats()
        self._build_model_formats()

        # v0.19.0 — analyst-ready Financial Statement Model is the main sheet.
        # Rendered only on the full export (no statement_type scope), since
        # statement-scoped exports are still served by the single-sheet
        # legacy path used by the bridge.
        if not stmt_t:
            self._write_financial_statement_model()

        self._write_capa()
        if not stmt_t:
            self._write_general()
            self._write_kpis()
            for stmt in ["DRE", "BPA", "BPP", "DFC"]:
                if stmt in self.stmts and not self.stmts[stmt].empty:
                    self._write_statement(stmt)
            for stmt in ["DVA", "DMPL"]:
                if stmt in self.extra and stmt in self.stmts and not self.stmts[stmt].empty:
                    self._write_statement(stmt)
        else:
            if stmt_t in self.stmts and not self.stmts[stmt_t].empty:
                self._write_statement(stmt_t)
            elif stmt_t in ["DVA", "DMPL"] and stmt_t in self.extra and stmt_t in self.stmts and not self.stmts[stmt_t].empty:
                self._write_statement(stmt_t)
        self._write_metadata(statement_type=stmt_t)

        self._wb.close()
        buf.seek(0)
        return buf.read()

    # ──────────────────────────────────────────────────────────────────────
    # Formatos
    # ──────────────────────────────────────────────────────────────────────

    def _build_formats(self):
        wb = self._wb

        def fmt(**kw) -> xlsxwriter.workbook.Format:
            return wb.add_format(kw)

        base = {"font_name": "Calibri", "font_size": 10, "text_wrap": False}

        self._fmt = {
            # ── Gerais ──────────────────────────────────────────────────
            "normal":      fmt(**base),
            "normal_num":  fmt(**base, num_format="#,##0"),
            "normal_pct":  fmt(**base, num_format="0.0%"),
            "normal_2x":   fmt(**base, num_format="0.00x"),
            "neg_num":     fmt(**base, num_format="#,##0", font_color=C["vermelho_val"]),
            "neg_pct":     fmt(**base, num_format="0.0%",  font_color=C["vermelho_val"]),
            "bold":        fmt(**base, bold=True),

            # ── Cabeçalho de seção (KPIs) ───────────────────────────────
            "sec_header":  fmt(**base, bold=True,
                               font_color=C["branco"], bg_color=C["azul_escuro"],
                               align="left", valign="vcenter"),

            # ── Subtotais (demonstrações) ────────────────────────────────
            "subtotal":    fmt(**base, bold=True, bg_color=C["azul_claro"]),
            "subtotal_num":fmt(**base, bold=True, bg_color=C["azul_claro"],
                               num_format='#,##0;-#,##0;"-"'),
            "subtotal_neg":fmt(**base, bold=True, bg_color=C["azul_claro"],
                               num_format='#,##0;(#,##0);"-"', font_color=C["vermelho_val"]),

            # ── Placeholder (KPI futuro) ─────────────────────────────────
            "placeholder": fmt(**base, italic=True, font_color=C["cinza_texto"],
                               bg_color=C["cinza_claro"]),

            # ── Cabeçalho de coluna (linha 1) ────────────────────────────
            "col_header":  fmt(**base, bold=True, bg_color=C["azul_escuro"],
                               font_color=C["branco"], align="center",
                               valign="vcenter", border=1),
            "col_header_l":fmt(**base, bold=True, bg_color=C["azul_escuro"],
                               font_color=C["branco"], align="left",
                               valign="vcenter", border=1),

            # ── Delta YoY ────────────────────────────────────────────────
            "delta_pos":   fmt(**base, bg_color=C["verde_claro"],
                               num_format="▲ 0.0%", align="center"),
            "delta_neg":   fmt(**base, bg_color=C["vermelho_claro"],
                               num_format="▼ 0.0%", align="center"),
            "delta_zero":  fmt(**base, num_format="0.0%", align="center"),

            # ── Números com alinhamento central (colunas de período) ─────
            "num_center":  fmt(**base, num_format='#,##0;-#,##0;"-"', align="right"),
            "pct_center":  fmt(**base, num_format="0.0%",  align="right"),
            "ratio_center":fmt(**base, num_format="0.00x", align="right"),
            "neg_center":  fmt(**base, num_format='#,##0;(#,##0);"-"', align="right",
                               font_color=C["vermelho_val"]),

            # ── Capa ──────────────────────────────────────────────────────
            "capa_title":  fmt(font_name="Calibri", font_size=22, bold=True,
                               font_color=C["branco"], bg_color=C["capa_azul"],
                               valign="vcenter"),
            "capa_sub":    fmt(font_name="Calibri", font_size=12,
                               font_color=C["branco"], bg_color=C["capa_azul"],
                               valign="vcenter"),
            "capa_label":  fmt(font_name="Calibri", font_size=10, bold=True,
                               font_color=C["azul_escuro"]),
            "capa_value":  fmt(font_name="Calibri", font_size=10,
                               font_color=C["texto_escuro"]),
            "capa_warn":   fmt(font_name="Calibri", font_size=9, italic=True,
                               font_color=C["vermelho_val"]),

            # ── Metadados ──────────────────────────────────────────────────
            "meta_key":    fmt(**base, bold=True, font_color=C["azul_escuro"]),
            "meta_val":    fmt(**base),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Financial Statement Model (main analyst-ready sheet, v0.19.0)
    # ──────────────────────────────────────────────────────────────────────

    def _build_model_formats(self):
        wb = self._wb

        def fmt(**kw) -> xlsxwriter.workbook.Format:
            return wb.add_format(kw)

        # Aptos Narrow (Office 365 default modern font); Calibri is a safe
        # fallback Excel will resolve when Aptos is unavailable. We declare
        # Aptos Narrow as the primary so the workbook visually matches the
        # reference on machines that have it.
        base = {"font_name": "Aptos Narrow", "font_size": 11}

        num_fmt = '#,##0;(#,##0);"-"'
        num_fmt_dec = '#,##0.0;(#,##0.0);"-"'
        pct_fmt = '0.0%;(0.0%);"-"'
        ratio_fmt = '0.00"x";(0.00"x");"-"'

        self._mfmt = {
            # Conventions block
            "conv_header": fmt(**base, bold=True, italic=True,
                               font_color="#1F4E78"),
            "conv_input":  fmt(**base, font_color="#0070C0"),
            "conv_output": fmt(**base, font_color="#3F3F3F", bg_color="#FFF2CC"),
            "conv_calc":   fmt(**base, font_color="#1A1A1A"),
            "conv_check":  fmt(**base, font_color="#548235", italic=True),
            "conv_note":   fmt(**base, font_color="#7F7F7F", italic=True),
            "conv_warning":fmt(**base, font_color="#C00000", bold=True),

            # Title / subtitle
            "title": fmt(font_name="Aptos Narrow", font_size=15, bold=True,
                          font_color="#1F4E78",
                          top=2, bottom=2, top_color="#1F4E78",
                          bottom_color="#1F4E78", valign="vcenter"),
            "subtitle": fmt(font_name="Aptos Narrow", font_size=11,
                             italic=True, font_color="#7F7F7F"),

            # Company info block
            "info_label": fmt(**base, bold=True, font_color="#1F4E78"),
            "info_value": fmt(**base, font_color="#1A1A1A"),

            # Period header
            "period_header_label": fmt(**base, bold=True, top=1, bottom=1,
                                        font_color="#1F4E78"),
            "period_header_q":     fmt(**base, bold=True, align="center",
                                        top=1, bottom=1, font_color="#1F4E78"),
            "period_header_y":     fmt(**base, bold=True, align="center",
                                        top=1, bottom=1, font_color="#1F4E78",
                                        bg_color="#F2F2F2"),

            # Section heading
            "section_heading": fmt(font_name="Aptos Narrow", font_size=13,
                                    bold=True, font_color="#1F4E78",
                                    top=2, bottom=2, top_color="#1F4E78",
                                    bottom_color="#1F4E78"),

            # Statement body
            "label_body":     fmt(**base),
            "label_subtotal": fmt(**base, bold=True, top=1),
            "num_body":       fmt(**base, num_format=num_fmt, align="right"),
            "num_body_y":     fmt(**base, num_format=num_fmt, align="right",
                                   bg_color="#F2F2F2"),
            "num_subtotal":   fmt(**base, bold=True, num_format=num_fmt,
                                   align="right", top=1),
            "num_subtotal_y": fmt(**base, bold=True, num_format=num_fmt,
                                   align="right", top=1, bg_color="#F2F2F2"),

            # KPI rows
            "kpi_label":   fmt(**base, italic=True, font_color="#1A1A1A"),
            "kpi_pct":     fmt(**base, num_format=pct_fmt, align="right"),
            "kpi_pct_y":   fmt(**base, num_format=pct_fmt, align="right",
                                bg_color="#F2F2F2"),
            "kpi_ratio":   fmt(**base, num_format=ratio_fmt, align="right"),
            "kpi_ratio_y": fmt(**base, num_format=ratio_fmt, align="right",
                                bg_color="#F2F2F2"),
            "kpi_num":     fmt(**base, num_format=num_fmt_dec, align="right"),
            "kpi_num_y":   fmt(**base, num_format=num_fmt_dec, align="right",
                                bg_color="#F2F2F2"),

            # Checks
            "check_label":   fmt(**base),
            "check_ok":      fmt(**base, font_color="#548235", bold=True),
            "check_warning": fmt(**base, font_color="#BF8F00", bold=True),
            "check_error":   fmt(**base, font_color="#C00000", bold=True),
            "check_value":   fmt(**base, num_format=num_fmt, align="right"),

            # Source / data quality
            "source_label": fmt(**base, bold=True, font_color="#1F4E78"),
            "source_value": fmt(**base, font_color="#3F3F3F"),
            "source_note":  fmt(**base, italic=True, font_color="#7F7F7F"),
        }

    def _collect_model_periods(self) -> list[str]:
        periods: set[str] = set()
        for df in self.stmts.values():
            if df is None or df.empty:
                continue
            id_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
            for c in df.columns:
                if c not in id_cols:
                    periods.add(str(c))
        ordered = sorted(periods, key=_period_sort_key)
        return ordered

    def _period_is_annual(self, period: str) -> bool:
        return bool(re.match(r"^(19|20)\d{2}$", str(period).strip()))

    def _write_financial_statement_model(self):
        ws = self._wb.add_worksheet(_MODEL_SHEET_NAME)
        f = self._mfmt
        info = self.info or {}
        periods = self._collect_model_periods()

        # Column widths matched to reference workbook
        ws.set_column(0, 0, 2)       # A: margin
        ws.set_column(1, 1, 52)      # B: labels
        ws.set_column(2, 2, 2.5)     # C: gap
        for idx in range(3, 3 + max(len(periods), 1)):
            ws.set_column(idx, idx, 10)

        ws.hide_gridlines(2)

        # ── Conventions block ───────────────────────────────────────────────
        # B2 header, D3..D8 legend
        ws.write(1, 1, "Conventions", f["conv_header"])
        ws.write(2, 3, "Input",       f["conv_input"])
        ws.write(3, 3, "Output",      f["conv_output"])
        ws.write(4, 3, "Calculation", f["conv_calc"])
        ws.write(5, 3, "Check",       f["conv_check"])
        ws.write(6, 3, "Note",        f["conv_note"])
        ws.write(7, 3, "Warning",     f["conv_warning"])

        # ── Title + subtitle (rows 9-10, 0-indexed 8-9) ──────────────────────
        company_name = str(info.get("company_name") or "—")
        ws.set_row(8, 24)
        title = f"Financial Statement Model For {company_name}"
        # Compute span based on number of period columns; min 4 to look balanced
        title_last_col = max(4, 2 + len(periods))
        ws.merge_range(8, 1, 8, title_last_col, title, f["title"])
        ws.write(9, 1, "R$ mm except per share and where indicated", f["subtitle"])

        # ── Company info block (rows 12-19, 0-indexed 11-18) ─────────────────
        latest_year = info.get("latest_year") or (periods[-1] if periods else "—")
        latest_quarter = "—"
        for p in reversed(periods):
            m_q = re.match(r"^([1-4])[QT](\d{2,4})$", str(p))
            if m_q:
                latest_quarter = p
                break

        rows_info = [
            ("Company name",       company_name),
            ("Ticker",             str(info.get("ticker_b3") or "—")),
            ("CVM code",           str(info.get("cd_cvm") or "—")),
            ("CNPJ",               str(info.get("cnpj") or "—")),
            ("GICS sector",        str(info.get("setor_analitico") or "—")),
            ("CVM sector",         str(info.get("setor_cvm") or "—")),
            ("Latest fiscal year", str(latest_year)),
            ("Latest quarter",     str(latest_quarter)),
        ]
        for i, (label, value) in enumerate(rows_info):
            r = 11 + i
            ws.set_row(r, 14)
            ws.write(r, 1, label, f["info_label"])
            ws.write(r, 3, value, f["info_value"])

        # ── Period header (row 21, 0-indexed 20) ─────────────────────────────
        period_row = 20
        ws.set_row(period_row, 18)
        ws.write(period_row, 1, "Fiscal year", f["period_header_label"])
        for c_idx, p in enumerate(periods, start=3):
            if self._period_is_annual(p):
                ws.write(period_row, c_idx, str(p), f["period_header_y"])
            else:
                ws.write(period_row, c_idx, str(p), f["period_header_q"])

        # Freeze pane below period header + after label/gap columns
        ws.freeze_panes(period_row + 2, 3)

        # ── Statement sections ──────────────────────────────────────────────
        cur = period_row + 2

        cur = self._write_model_statement(
            ws, cur, periods,
            stmt_type="DRE",
            heading="Income Statement",
            subtotals=_DRE_SUBTOTAL_KEYS,
        )
        cur = self._write_model_balance_sheet(ws, cur, periods)
        cur = self._write_model_statement(
            ws, cur, periods,
            stmt_type="DFC",
            heading="Cash Flow Statement",
            subtotals=_DFC_SUBTOTAL_KEYS,
        )
        if "DVA" in self.stmts and not self.stmts["DVA"].empty:
            cur = self._write_model_statement(
                ws, cur, periods,
                stmt_type="DVA",
                heading="Value Added Statement",
                subtotals=_DVA_SUBTOTAL_KEYS,
            )

        cur = self._write_model_kpis(ws, cur, periods)
        cur = self._write_model_checks(ws, cur, periods)
        cur = self._write_model_source_block(ws, cur, periods)

        # v0.18.3 — analyst-friendly print setup. Landscape, fit to one page
        # wide (height unrestricted), repeat the conventions/title/period
        # header rows (1-21) on every printed page, narrow margins.
        ws.set_landscape()
        ws.set_paper(9)  # A4
        ws.fit_to_pages(1, 0)
        ws.repeat_rows(0, 20)
        ws.set_margins(left=0.4, right=0.4, top=0.5, bottom=0.5)
        ws.set_header(f"&L{_MODEL_SHEET_NAME} &R{info.get('company_name') or ''}")
        ws.set_footer("&LCVMAnalytics &CPage &P of &N &R&D")
        ws.print_area(0, 0, cur, max(3, 2 + len(periods)))

    def _write_section_heading(self, ws, row: int, label: str) -> int:
        f = self._mfmt
        ws.set_row(row, 22)
        ws.write(row, 1, label, f["section_heading"])
        return row + 2

    def _write_model_statement(
        self,
        ws,
        start_row: int,
        periods: list[str],
        *,
        stmt_type: str,
        heading: str,
        subtotals: set[str],
    ) -> int:
        f = self._mfmt
        df = self.stmts.get(stmt_type)
        if df is None or df.empty:
            return start_row

        row = self._write_section_heading(ws, start_row, heading)

        id_cols = [c for c in ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]
                   if c in df.columns]
        period_cols_in_df = [c for c in df.columns if c not in id_cols]

        for _, stmt_row in df.iterrows():
            cd = str(stmt_row.get("CD_CONTA", "")).strip()
            ds = str(stmt_row.get("DS_CONTA", "") or "").strip()
            is_subtotal = cd in subtotals
            indent = _indent_for_code(cd)
            suffix = _suffix_for_row(cd, subtotals)
            label = (" " * indent) + ds + suffix

            ws.set_row(row, 14)
            ws.write(row, 1, label,
                     f["label_subtotal"] if is_subtotal else f["label_body"])

            for c_idx, period in enumerate(periods, start=3):
                annual = self._period_is_annual(period)
                if period not in period_cols_in_df:
                    cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                                else f["num_subtotal"] if is_subtotal
                                else f["num_body_y"] if annual
                                else f["num_body"])
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue
                v = stmt_row.get(period)
                if pd.isna(v) or v is None:
                    cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                                else f["num_subtotal"] if is_subtotal
                                else f["num_body_y"] if annual
                                else f["num_body"])
                    ws.write_blank(row, c_idx, None, cell_fmt)
                    continue
                value_mm = float(v) / _MODEL_SCALE_DIVISOR
                cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                            else f["num_subtotal"] if is_subtotal
                            else f["num_body_y"] if annual
                            else f["num_body"])
                ws.write_number(row, c_idx, value_mm, cell_fmt)
            row += 1

        return row + 1  # one blank spacer row after section

    def _write_model_balance_sheet(self, ws, start_row: int, periods: list[str]) -> int:
        """Render BPA + BPP under one combined "Balance Sheet" heading."""
        bpa = self.stmts.get("BPA")
        bpp = self.stmts.get("BPP")
        if (bpa is None or bpa.empty) and (bpp is None or bpp.empty):
            return start_row

        row = self._write_section_heading(ws, start_row, "Balance Sheet")

        for stmt_type, subtotals, sub_label in [
            ("BPA", _BPA_SUBTOTAL_KEYS, "Assets"),
            ("BPP", _BPP_SUBTOTAL_KEYS, "Liabilities & Equity"),
        ]:
            df = self.stmts.get(stmt_type)
            if df is None or df.empty:
                continue
            f = self._mfmt
            ws.set_row(row, 16)
            ws.write(row, 1, sub_label, f["label_subtotal"])
            row += 1

            id_cols = [c for c in ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]
                       if c in df.columns]
            period_cols_in_df = [c for c in df.columns if c not in id_cols]

            for _, stmt_row in df.iterrows():
                cd = str(stmt_row.get("CD_CONTA", "")).strip()
                ds = str(stmt_row.get("DS_CONTA", "") or "").strip()
                is_subtotal = cd in subtotals
                indent = _indent_for_code(cd)
                suffix = _suffix_for_row(cd, subtotals)
                label = (" " * indent) + ds + suffix

                ws.set_row(row, 14)
                ws.write(row, 1, label,
                         f["label_subtotal"] if is_subtotal else f["label_body"])

                for c_idx, period in enumerate(periods, start=3):
                    annual = self._period_is_annual(period)
                    if period not in period_cols_in_df:
                        cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                                    else f["num_subtotal"] if is_subtotal
                                    else f["num_body_y"] if annual
                                    else f["num_body"])
                        ws.write_blank(row, c_idx, None, cell_fmt)
                        continue
                    v = stmt_row.get(period)
                    if pd.isna(v) or v is None:
                        cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                                    else f["num_subtotal"] if is_subtotal
                                    else f["num_body_y"] if annual
                                    else f["num_body"])
                        ws.write_blank(row, c_idx, None, cell_fmt)
                        continue
                    value_mm = float(v) / _MODEL_SCALE_DIVISOR
                    cell_fmt = (f["num_subtotal_y"] if is_subtotal and annual
                                else f["num_subtotal"] if is_subtotal
                                else f["num_body_y"] if annual
                                else f["num_body"])
                    ws.write_number(row, c_idx, value_mm, cell_fmt)
                row += 1
            row += 1  # spacer between Assets and Liab&Equity

        return row

    def _write_model_kpis(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._mfmt
        if self.kpis is None or self.kpis.empty:
            return start_row

        row = self._write_section_heading(ws, start_row, "KPIs / Ratios")

        meta_cols = {"CATEGORIA", "KPI_ID", "KPI_NOME", "FORMULA",
                     "IS_PLACEHOLDER", "FORMAT_TYPE", "HIGHER_IS_BETTER",
                     "UNIDADE", "DELTA_YOY", "DELTA_YOY_PCT"}
        kpi_period_cols = [str(c) for c in self.kpis.columns if c not in meta_cols]

        current_cat = None
        for _, kpi_row in self.kpis.iterrows():
            if bool(kpi_row.get("IS_PLACEHOLDER", False)):
                continue  # skip placeholder KPIs in the analyst model

            cat = str(kpi_row.get("CATEGORIA") or "")
            if cat and cat != current_cat:
                current_cat = cat
                ws.set_row(row, 14)
                ws.write(row, 1, f"  {cat}", f["info_label"])
                row += 1

            fmt_type = str(kpi_row.get("FORMAT_TYPE") or "ratio").lower()
            unit = str(kpi_row.get("UNIDADE") or "")
            kpi_name = str(kpi_row.get("KPI_NOME") or "")
            label = f"    {kpi_name}"
            if unit:
                label = f"{label} ({unit})"

            ws.set_row(row, 14)
            ws.write(row, 1, label, f["kpi_label"])

            for c_idx, period in enumerate(periods, start=3):
                annual = self._period_is_annual(period)
                if period not in kpi_period_cols:
                    blank_fmt = (f["kpi_pct_y"] if fmt_type == "pct" and annual
                                  else f["kpi_pct"] if fmt_type == "pct"
                                  else f["kpi_ratio_y"] if annual
                                  else f["kpi_ratio"])
                    ws.write_blank(row, c_idx, None, blank_fmt)
                    continue
                v = kpi_row.get(period)
                if v is None or pd.isna(v):
                    blank_fmt = (f["kpi_pct_y"] if fmt_type == "pct" and annual
                                  else f["kpi_pct"] if fmt_type == "pct"
                                  else f["kpi_ratio_y"] if annual
                                  else f["kpi_ratio"])
                    ws.write_blank(row, c_idx, None, blank_fmt)
                    continue
                if fmt_type == "pct":
                    cell_fmt = f["kpi_pct_y"] if annual else f["kpi_pct"]
                elif fmt_type == "ratio":
                    cell_fmt = f["kpi_ratio_y"] if annual else f["kpi_ratio"]
                else:
                    cell_fmt = f["kpi_num_y"] if annual else f["kpi_num"]
                ws.write_number(row, c_idx, float(v), cell_fmt)
            row += 1

        return row + 1

    def _write_model_checks(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._mfmt
        row = self._write_section_heading(ws, start_row, "Checks")

        # Balance Sheet check: Total Assets vs Total Liabilities + Equity
        bpa = self.stmts.get("BPA")
        bpp = self.stmts.get("BPP")
        if (bpa is not None and not bpa.empty
                and bpp is not None and not bpp.empty):
            assets_row = bpa[bpa["CD_CONTA"].astype(str) == "1"]
            liab_row   = bpp[bpp["CD_CONTA"].astype(str) == "2"]
            ws.set_row(row, 14)
            ws.write(row, 1, "Balance Sheet: Assets - (Liab. + Equity)",
                     f["check_label"])
            all_ok = True
            for c_idx, period in enumerate(periods, start=3):
                a_val = None
                l_val = None
                if not assets_row.empty and period in assets_row.columns:
                    a_val = assets_row.iloc[0].get(period)
                if not liab_row.empty and period in liab_row.columns:
                    l_val = liab_row.iloc[0].get(period)
                if (a_val is None or pd.isna(a_val)
                        or l_val is None or pd.isna(l_val)):
                    ws.write_blank(row, c_idx, None, f["check_value"])
                    continue
                diff_mm = (float(a_val) - float(l_val)) / _MODEL_SCALE_DIVISOR
                ws.write_number(row, c_idx, diff_mm, f["check_value"])
                if abs(diff_mm) > 0.5:  # > R$ 500k diff after rounding to R$ mm
                    all_ok = False
            ws.write(row, 2, "OK" if all_ok else "WARNING",
                     f["check_ok"] if all_ok else f["check_warning"])
            row += 1

        # Period completeness
        ws.set_row(row, 14)
        ws.write(row, 1, "Period Completeness (count of periods exported)",
                 f["check_label"])
        ws.write(row, 2, "OK" if periods else "ERROR",
                 f["check_ok"] if periods else f["check_error"])
        # show count under the last period column for visibility
        for c_idx, period in enumerate(periods, start=3):
            ws.write_blank(row, c_idx, None, f["check_value"])
        if periods:
            ws.write_number(row, 3, float(len(periods)), f["check_value"])
        row += 1

        # Duplicate Line ID check
        ws.set_row(row, 14)
        dup_count = 0
        for stmt_type in ("DRE", "BPA", "BPP", "DFC", "DVA"):
            df = self.stmts.get(stmt_type)
            if df is None or df.empty or "CD_CONTA" not in df.columns:
                continue
            counts = df["CD_CONTA"].astype(str).value_counts()
            dup_count += int((counts > 1).sum())
        ws.write(row, 1, "Duplicate CD_CONTA across statements",
                 f["check_label"])
        ws.write(row, 2, "OK" if dup_count == 0 else "WARNING",
                 f["check_ok"] if dup_count == 0 else f["check_warning"])
        ws.write_number(row, 3, float(dup_count), f["check_value"])
        row += 1

        # Critical Line Availability (DRE 3.01 Receita, DRE 3.11 Net Income)
        ws.set_row(row, 14)
        crit_missing = []
        dre = self.stmts.get("DRE")
        if dre is not None and not dre.empty and "CD_CONTA" in dre.columns:
            present = set(dre["CD_CONTA"].astype(str).tolist())
            for code, name in [("3.01", "Receita"), ("3.11", "Lucro Líquido")]:
                if code not in present:
                    crit_missing.append(f"{code} {name}")
        else:
            crit_missing.append("DRE missing entirely")
        ws.write(row, 1, "Critical line availability (DRE 3.01, 3.11)",
                 f["check_label"])
        ws.write(row, 2, "OK" if not crit_missing else "WARNING",
                 f["check_ok"] if not crit_missing else f["check_warning"])
        if crit_missing:
            ws.write(row, 3, "; ".join(crit_missing), f["source_value"])
        row += 1

        return row + 1

    def _write_model_source_block(self, ws, start_row: int, periods: list[str]) -> int:
        f = self._mfmt
        row = self._write_section_heading(ws, start_row, "Source / Data Quality")
        info = self.info or {}

        stmts_present = [k for k in ("DRE", "BPA", "BPP", "DFC", "DVA", "DMPL")
                         if k in self.stmts and not self.stmts[k].empty]
        rows_by_stmt = ", ".join(
            f"{k}={len(self.stmts[k])}"
            for k in stmts_present
        ) or "—"

        rows_source = [
            ("Generated by",       "CVMAnalytics"),
            ("App version",        str(_APP_VERSION)),
            ("Export timestamp",   datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("Company",            str(info.get("company_name") or "—")),
            ("CVM code",           str(info.get("cd_cvm") or "—")),
            ("Periods exported",   str(len(periods))),
            ("Rows by statement",  rows_by_stmt),
            ("Source",             "CVM filings processed by CVMAnalytics local database"),
            ("Units",              "Values displayed in R$ mm (millions); CVM source is R$ mil (thousands), divided by 1,000 for this model"),
        ]
        for label, value in rows_source:
            ws.set_row(row, 14)
            ws.write(row, 1, label, f["source_label"])
            ws.write(row, 3, value, f["source_value"])
            row += 1

        return row + 1

    # ──────────────────────────────────────────────────────────────────────
    # Aba CAPA
    # ──────────────────────────────────────────────────────────────────────

    def _write_capa(self):
        ws = self._wb.add_worksheet("CAPA")
        ws.set_column("A:A", 2)
        ws.set_column("B:B", 22)
        ws.set_column("C:C", 40)
        ws.set_column("D:D", 20)

        info = self.info
        name    = info.get("company_name", "—")
        ticker  = info.get("ticker_b3") or "—"
        cd_cvm  = info.get("cd_cvm", "—")
        setor   = info.get("setor_analitico") or info.get("setor_cvm") or "—"
        cnpj    = info.get("cnpj") or "—"
        now_str = datetime.now().strftime("%Y-%m-%d  %H:%M")

        # Título
        ws.set_row(1, 40)
        ws.merge_range("B2:D2", name, self._fmt["capa_title"])
        ws.set_row(2, 25)
        ws.merge_range("B3:D3", f"{setor}  ·  CVM: {cd_cvm}  ·  {ticker}", self._fmt["capa_sub"])

        # Linha separadora
        ws.set_row(3, 6)
        ws.merge_range("B4:D4", "", self._wb.add_format({
            "bg_color": C["capa_acento"]
        }))

        # Dados
        rows_info = [
            ("Ticker B3",        ticker),
            ("Código CVM",       str(cd_cvm)),
            ("CNPJ",             cnpj),
            ("Setor CVM",        info.get("setor_cvm") or "—"),
            ("Setor Analítico",  setor),
            ("Gerado em",        now_str),
            ("Fonte de dados",   "CVM — dados.cvm.gov.br"),
            ("Escala valores",   "Ver nota abaixo"),
            ("Unidade padrão",   "R$ milhares (exceto onde indicado na aba METADADOS)"),
        ]

        r = 5
        for label, value in rows_info:
            ws.set_row(r, 18)
            ws.write(r, 1, label, self._fmt["capa_label"])
            ws.write(r, 2, value, self._fmt["capa_value"])
            r += 1

        # Nota de escala
        r += 1
        ws.merge_range(r, 1, r, 3,
            "⚠  NOTA DE ESCALA: Valores armazenados conforme reportado à CVM. "
            "A maioria das empresas reporta em R$ mil (milhares). Algumas empresas "
            "(ex: Ânima) reportam em R$ milhões. Consulte a aba METADADOS para confirmar.",
            self._fmt["capa_warn"])

        # Ocultar linhas de grade
        ws.hide_gridlines(2)

    # ──────────────────────────────────────────────────────────────────────
    # Aba KPIs
    # ──────────────────────────────────────────────────────────────────────

    def _write_kpis(self):
        ws = self._wb.add_worksheet("KPIs")
        kpis = self.kpis

        if kpis is None or kpis.empty:
            ws.write(0, 0, "KPIs não disponíveis", self._fmt["normal"])
            return

        # Detectar colunas de anos
        meta_cols = {"CATEGORIA", "KPI_ID", "KPI_NOME", "FORMULA",
                     "IS_PLACEHOLDER", "FORMAT_TYPE", "HIGHER_IS_BETTER",
                     "UNIDADE", "DELTA_YOY", "DELTA_YOY_PCT"}
        year_cols = [c for c in kpis.columns if c not in meta_cols]

        # ── Cabeçalho ────────────────────────────────────────────────────
        ws.set_row(0, 22)
        headers = ["INDICADOR", "FÓRMULA", "UNIDADE"] + [str(y) for y in year_cols] + ["Δ YoY", "Tendência"]
        col_widths = [32, 42, 8] + [10] * len(year_cols) + [10, 12]

        for c, (h, w) in enumerate(zip(headers, col_widths)):
            ws.write(0, c, h, self._fmt["col_header_l"] if c < 3 else self._fmt["col_header"])
            ws.set_column(c, c, w)

        # Freeze header + coluna INDICADOR
        ws.freeze_panes(1, 1)

        # ── Linhas por categoria ──────────────────────────────────────────
        row = 1
        current_cat = None
        for _, kpi_row in kpis.iterrows():
            cat = kpi_row["CATEGORIA"]

            # Inserir separador de seção quando muda a categoria
            if cat != current_cat:
                current_cat = cat
                ws.set_row(row, 18)
                ws.write(row, 0, f"  {cat.upper()}", self._fmt["sec_header"])
                for _c in range(1, len(headers)):
                    ws.write_blank(row, _c, None, self._fmt["sec_header"])
                row += 1

            is_placeholder = bool(kpi_row.get("IS_PLACEHOLDER", False))
            fmt_type = kpi_row.get("FORMAT_TYPE", "ratio")
            higher   = bool(kpi_row.get("HIGHER_IS_BETTER", True))

            txt_fmt = self._fmt["placeholder"] if is_placeholder else self._fmt["normal"]

            ws.set_row(row, 16)
            ws.write(row, 0, kpi_row["KPI_NOME"], txt_fmt)
            ws.write(row, 1, kpi_row["FORMULA"],  txt_fmt)
            ws.write(row, 2, kpi_row.get("UNIDADE", ""), txt_fmt)

            # Valores por ano
            for c_idx, yr in enumerate(year_cols, start=3):
                v = kpi_row.get(yr)
                if is_placeholder or v is None:
                    ws.write_blank(row, c_idx, None, txt_fmt)
                    continue
                num_fmt = (self._fmt["pct_center"] if fmt_type == "pct"
                           else self._fmt["ratio_center"])
                ws.write_number(row, c_idx, v, num_fmt)

            # Delta YoY
            delta = kpi_row.get("DELTA_YOY")
            delta_pct = kpi_row.get("DELTA_YOY_PCT")
            c_delta  = 3 + len(year_cols)
            c_trend  = c_delta + 1

            if is_placeholder or delta is None or delta_pct is None:
                ws.write_blank(row, c_delta, None, txt_fmt)
                ws.write_blank(row, c_trend, None, txt_fmt)
            else:
                is_good = (delta > 0) == higher
                delta_fmt = (self._fmt["delta_pos"] if is_good
                             else self._fmt["delta_neg"])
                ws.write_number(row, c_delta, delta,     (self._fmt["pct_center"]
                                                           if fmt_type == "pct"
                                                           else self._fmt["ratio_center"]))
                trend = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
                trend_fmt = (self._fmt["delta_pos"] if is_good else
                             self._fmt["delta_neg"])
                ws.write(row, c_trend, trend, trend_fmt)

            row += 1

        ws.hide_gridlines(2)

    # ──────────────────────────────────────────────────────────────────────
    # Abas de demonstrações (DRE / BPA / BPP / DFC / DVA / DMPL)
    # ──────────────────────────────────────────────────────────────────────


    def _get_global_periods(self) -> list[str]:
        # Coleta todos os períodos únicos de todas as demonstrações e KPIs
        periods = set()

        # Dos stmts
        for df in self.stmts.values():
            if df is not None and not df.empty:
                id_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
                for c in df.columns:
                    if c not in id_cols:
                        periods.add(str(c))

        # Dos KPIs
        if self.kpis is not None and not self.kpis.empty:
            meta_cols = {"CATEGORIA", "KPI_ID", "KPI_NOME", "FORMULA",
                         "IS_PLACEHOLDER", "FORMAT_TYPE", "HIGHER_IS_BETTER",
                         "UNIDADE", "DELTA_YOY", "DELTA_YOY_PCT"}
            for c in self.kpis.columns:
                if c not in meta_cols:
                    periods.add(str(c))

        # Sort them by year then quarter (e.g., '2024' < '1Q25' doesn't work out of the box with lexicographical sort if 1Q25 refers to 2025).
        # Typically the columns are '2020', '2021', '1T25', '1Q25', '2025-03-31'. We need a custom sort key.
        def _sort_key(p):
            # If it's a 4-digit year, assume Q4 of that year for sorting purposes.
            import re
            m_year = re.match(r"^20\d{2}$", p)
            if m_year:
                return (int(p), 5, p)
            m_quarter = re.match(r"^([1-4])[QT](20\d{2}|\d{2})$", p)
            if m_quarter:
                q = int(m_quarter.group(1))
                y_str = m_quarter.group(2)
                y = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
                return (y, q, p)
            # Default fallback for other formats
            return (9999, 9, p)

        try:
            return sorted(list(periods), key=_sort_key)
        except Exception:
            return sorted(list(periods))

    def _write_general(self):
        ws = self._wb.add_worksheet("GERAL")
        blocks = build_general_summary_blocks(self.stmts)

        global_periods = self._get_global_periods()

        ws.set_column(0, 0, 14)
        ws.set_column(1, 1, 42)

        if global_periods:
            ws.set_column(2, 1 + len(global_periods), 13)

        if not blocks:
            ws.write(0, 0, "Resumo condensado indisponível", self._fmt["normal"])
            ws.hide_gridlines(2)
            return

        row = 0
        for block in blocks:
            last_col = max(1, 1 + len(global_periods))
            ws.write(row, 0, block.title, self._fmt["sec_header"])
            for c_idx in range(1, last_col + 1):
                ws.write_blank(row, c_idx, None, self._fmt["sec_header"])
            row += 1

            headers = ["CD_CONTA", "LINHA"] + [str(col) for col in global_periods]
            for c_idx, header in enumerate(headers):
                fmt = self._fmt["col_header_l"] if c_idx < 2 else self._fmt["col_header"]
                ws.write(row, c_idx, header, fmt)
            row += 1

            for _, stmt_row in block.rows.iterrows():
                is_subtotal = bool(stmt_row.get("IS_SUBTOTAL", False))
                text_fmt = self._fmt["subtotal"] if is_subtotal else self._fmt["normal"]
                ws.write(row, 0, str(stmt_row.get("CD_CONTA", "")), text_fmt)
                ws.write(row, 1, str(stmt_row.get("LABEL", "")), text_fmt)

                for c_idx, period_col in enumerate(global_periods, start=2):
                    # It's possible the block doesn't have this period, or it's NaN
                    if period_col not in block.rows.columns:
                        value = None
                    else:
                        value = stmt_row.get(period_col)

                    if pd.isna(value) or value is None:
                        blank_fmt = self._fmt["subtotal_num"] if is_subtotal else self._fmt["normal"]
                        ws.write_blank(row, c_idx, None, blank_fmt)
                        continue

                    number = float(value)
                    if is_subtotal:
                        num_fmt = self._fmt["subtotal_neg"] if number < 0 else self._fmt["subtotal_num"]
                    else:
                        num_fmt = self._fmt["neg_center"] if number < 0 else self._fmt["num_center"]
                    ws.write_number(row, c_idx, number, num_fmt)

                row += 1

            row += 1

        ws.hide_gridlines(2)

    def _write_statement(self, stmt_type: str):
        df = self.stmts.get(stmt_type)
        if df is None or df.empty:
            return

        label = _STMT_LABELS.get(stmt_type, stmt_type)
        ws = self._wb.add_worksheet(label)
        subtotais = _SUBTOTAIS.get(stmt_type, set())

        # Colunas fixas e de período
        id_cols    = [c for c in ["CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"]
                      if c in df.columns]
        period_cols = [c for c in df.columns if c not in id_cols]

        all_cols = id_cols + period_cols
        col_widths = {
            "CD_CONTA":      14,
            "DS_CONTA":      44,
            "STANDARD_NAME": 34,
            "LINE_ID_BASE":  24,
        }

        # ── Cabeçalho ────────────────────────────────────────────────────
        ws.set_row(0, 22)
        for c_idx, col in enumerate(all_cols):
            w = col_widths.get(col, 13)
            ws.set_column(c_idx, c_idx, w)
            fmt = self._fmt["col_header_l"] if col in id_cols else self._fmt["col_header"]
            ws.write(0, c_idx, col, fmt)

        # Freeze: linha 1 + primeiras 3 colunas
        freeze_cols = min(3, len(id_cols))
        ws.freeze_panes(1, freeze_cols)

        # ── Dados ────────────────────────────────────────────────────────
        for r_idx, (_, row) in enumerate(df.iterrows(), start=1):
            cd = str(row.get("CD_CONTA", ""))
            is_subtotal = cd in subtotais

            ws.set_row(r_idx, 15)

            for c_idx, col in enumerate(all_cols):
                val = row[col]
                is_period = col in period_cols

                if not is_period:
                    # Coluna de texto
                    ws.write(r_idx, c_idx, "" if pd.isna(val) else str(val),
                             self._fmt["subtotal"] if is_subtotal else self._fmt["normal"])
                    continue

                # Coluna numérica (período)
                if pd.isna(val) or val is None:
                    ws.write_blank(r_idx, c_idx, None,
                                   self._fmt["subtotal_num"] if is_subtotal
                                   else self._fmt["normal"])
                    continue

                v = float(val)
                if is_subtotal:
                    fmt = (self._fmt["subtotal_neg"] if v < 0
                           else self._fmt["subtotal_num"])
                else:
                    fmt = (self._fmt["neg_center"] if v < 0
                           else self._fmt["num_center"])
                ws.write_number(r_idx, c_idx, v, fmt)

        # v0.18.3 — auto-filter on the header row so analysts can quickly
        # filter by CD_CONTA / DS_CONTA / STANDARD_NAME on the legacy
        # statement sheets. Range covers the full populated grid.
        last_row = len(df)  # data starts at row 1, header at row 0
        last_col = len(all_cols) - 1
        if last_row > 0 and last_col >= 0:
            ws.autofilter(0, 0, last_row, last_col)

        ws.hide_gridlines(2)

    # ──────────────────────────────────────────────────────────────────────
    # Aba METADADOS
    # ──────────────────────────────────────────────────────────────────────

    def _write_metadata(self, statement_type: Optional[str] = None):
        ws = self._wb.add_worksheet("METADADOS")
        ws.set_column("A:A", 30)
        ws.set_column("B:B", 60)
        ws.set_column("C:C", 20)

        ws.set_row(0, 22)
        ws.write(0, 0, "CAMPO",  self._fmt["col_header_l"])
        ws.write(0, 1, "VALOR",  self._fmt["col_header_l"])
        ws.write(0, 2, "NOTAS",  self._fmt["col_header_l"])

        info = self.info
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if statement_type:
            stmts_present = statement_type
        else:
            stmts_present = ", ".join(
                k for k in ["DRE", "BPA", "BPP", "DFC", "DVA", "DMPL"]
                if k in self.stmts and not self.stmts[k].empty
            )

        rows = [
            ("Empresa",              info.get("company_name", "—"),          ""),
            ("Código CVM (cd_cvm)",  str(info.get("cd_cvm", "—")),           ""),
            ("Ticker B3",            info.get("ticker_b3") or "—",           ""),
            ("CNPJ",                 info.get("cnpj") or "—",                ""),
            ("Setor CVM",            info.get("setor_cvm") or "—",           ""),
            ("Setor Analítico",      info.get("setor_analitico") or "—",     ""),
            ("Demonstrações",        stmts_present,                          "Abas geradas neste workbook"),
            ("Gerado em",            now_str,                                ""),
            ("Fonte de dados",       "CVM — dados.cvm.gov.br",               "DFP/ITR"),
            ("Ferramenta",           "cvm_reports_capture",                  "github / uso interno"),
            ("Escala padrão CVM",    "R$ milhares (mil)",                    "A maioria das empresas"),
            ("Atenção escala",       "Verificar empresa — algumas reportam em R$ milhões",
             "Ex: Ânima Holding reporta em R$ mi"),
            ("QA_CONFLICT",          "Linhas com conflito de dados excluídas", "QA_CONFLICT=0 aplicado"),
            ("D&A na DFC",           "CD_CONTA 6.01.01.x filtrado por 'depreci' (exclui amortiz. financeira)",
             "EBITDA = EBIT + D&A"),
            ("EBITDA",               "EBIT (3.05) + D&A (DFC 6.01.01.x)",   "Se D&A não encontrado → NaN"),
            ("Dívida Liq./EBITDA",   "Proxy: PNC - Caixa / EBITDA",          "PNC ≈ dívida financeira LP"),
            ("Liquidez Seca",        "Sem separação de estoque no nível 1",  "≈ Liquidez Corrente"),
            ("CAPEX / Receita",      "FCI total (proxy)",                    "Inclui todas saídas de investimento"),
            ("Placeholders (*)",     "KPIs futuros marcados com * requerem preço de mercado", ""),
        ]

        for r_idx, (key, val, note) in enumerate(rows, start=1):
            ws.set_row(r_idx, 16)
            ws.write(r_idx, 0, key,  self._fmt["meta_key"])
            ws.write(r_idx, 1, val,  self._fmt["meta_val"])
            ws.write(r_idx, 2, note, self._fmt["normal"])

        ws.freeze_panes(1, 0)
        ws.hide_gridlines(2)
