# -*- coding: utf-8 -*-
"""Workbook cell format definitions for ExcelExporter."""
from __future__ import annotations

from src.financials.excel_mapping_defaults import PALETTE


class ExcelFormatsMixin:
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
