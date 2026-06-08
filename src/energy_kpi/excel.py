"""Energy KPI Excel exporter — 4-tab workbook.

Tabs:
  1. KPI Catalog     — definitions filtered by excel_export_priority
  2. Country KPIs    — country × year × KPI time series
  3. Source Metadata — source registry + last snapshot info
  4. Data Quality    — DQ checks for last run

Conventions (matching src/financials/excel_exporter.py):
  - Negatives in parentheses: (value)
  - Zeros → "-"
  - Units in column headers
  - No merged cells
  - Every value row has snapshot_id for provenance tracing
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import xlsxwriter

from src.energy_kpi.read import EnergyKPIReadService
from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)

# Number formats (negatives in parentheses, zeros → "-")
_FMT_NUM = "#,##0.0;(#,##0.0);-"
_FMT_PCT = "0.0%;(0.0%);-"
_FMT_INT = "#,##0;(#,##0);-"
_FMT_TEXT = "@"

_HEADER_COLOR = "#1F3864"
_ALT_ROW_COLOR = "#F2F2F2"
_DQ_FAIL_COLOR = "#FFE0E0"


def export_country_kpis(
    settings: AppSettings,
    iso_codes: list[str] | None = None,
    kpi_ids: list[str] | None = None,
) -> Path:
    """Export a 4-tab workbook to settings.paths.reports_dir.

    Returns the path to the written .xlsx file.
    """
    svc = EnergyKPIReadService(settings)
    engine = get_energy_kpi_engine(settings)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    settings.paths.reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = settings.paths.reports_dir / f"energy_country_kpis_{timestamp}.xlsx"

    with xlsxwriter.Workbook(str(out_path)) as wb:
        _write_catalog_tab(wb, svc)
        _write_time_series_tab(wb, svc, iso_codes=iso_codes, kpi_ids=kpi_ids)
        _write_source_metadata_tab(wb, engine)
        _write_dq_tab(wb, engine)

    logger.info("Energy KPI workbook written to %s", out_path)
    return out_path


# ── Tab 1: KPI Catalog ────────────────────────────────────────────────────────

def _write_catalog_tab(wb: xlsxwriter.Workbook, svc: EnergyKPIReadService) -> None:
    ws = wb.add_worksheet("KPI Catalog")
    header_fmt = wb.add_format({
        "bold": True, "bg_color": _HEADER_COLOR, "font_color": "white",
        "border": 1, "text_wrap": True, "valign": "vcenter",
    })
    text_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
    alt_fmt = wb.add_format({"text_wrap": True, "valign": "top", "bg_color": _ALT_ROW_COLOR})

    entries = svc.get_kpi_catalog(excel_export_priority="required") + \
              svc.get_kpi_catalog(excel_export_priority="optional")
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for e in entries:
        if e.kpi_id not in seen:
            seen.add(e.kpi_id)
            deduped.append(e)
    entries = deduped

    headers = [
        "KPI ID", "Display Name", "Description", "Type", "Category",
        "Subsector", "Unit", "Source", "Calc Method", "V1 Status",
        "Dashboard Priority", "Export Priority", "Source Status",
        "Higher Is Better", "Source Caveats", "Audit Notes",
    ]
    col_widths = [40, 30, 50, 12, 20, 20, 8, 8, 14, 18, 18, 14, 14, 14, 40, 40]

    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, header_fmt)
        ws.set_column(col, col, w)

    ws.freeze_panes(1, 0)

    for row_idx, e in enumerate(entries, start=1):
        fmt = alt_fmt if row_idx % 2 == 0 else text_fmt
        row = [
            e.kpi_id, e.display_name, e.description, e.kpi_type, e.macro_category,
            e.subsector, e.unit, e.primary_source, e.calculation_method, e.v1_status,
            e.dashboard_priority, e.excel_export_priority, e.source_verification_status,
            "" if e.higher_is_better is None else ("Yes" if e.higher_is_better else "No"),
            e.source_caveats, e.audit_notes,
        ]
        for col, val in enumerate(row):
            ws.write(row_idx, col, val, fmt)

    ws.autofilter(0, 0, len(entries), len(headers) - 1)


# ── Tab 2: Country KPI Time Series ───────────────────────────────────────────

def _write_time_series_tab(
    wb: xlsxwriter.Workbook,
    svc: EnergyKPIReadService,
    iso_codes: list[str] | None = None,
    kpi_ids: list[str] | None = None,
) -> None:
    ws = wb.add_worksheet("Country KPIs")
    header_fmt = wb.add_format({
        "bold": True, "bg_color": _HEADER_COLOR, "font_color": "white",
        "border": 1, "valign": "vcenter",
    })
    num_fmt = wb.add_format({"num_format": _FMT_NUM})
    num_alt_fmt = wb.add_format({"num_format": _FMT_NUM, "bg_color": _ALT_ROW_COLOR})
    pct_fmt = wb.add_format({"num_format": _FMT_PCT})
    pct_alt_fmt = wb.add_format({"num_format": _FMT_PCT, "bg_color": _ALT_ROW_COLOR})
    text_fmt = wb.add_format({})
    alt_fmt = wb.add_format({"bg_color": _ALT_ROW_COLOR})
    conflict_fmt = wb.add_format({"bg_color": "#FFF3CD"})

    values = svc.get_country_kpi_series(kpi_ids=kpi_ids, iso_codes=iso_codes)

    headers = [
        "KPI ID", "Display Name", "Country", "ISO Code", "Year",
        "Value", "Unit", "Source", "DQ Status", "Conflict",
        "Fallback Used", "Source Field", "Snapshot ID",
    ]
    col_widths = [44, 32, 20, 8, 6, 12, 8, 8, 14, 8, 12, 28, 38]

    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, header_fmt)
        ws.set_column(col, col, w)

    ws.freeze_panes(1, 0)

    # Build catalog lookup for display names + units
    catalog_map = {e.kpi_id: e for e in svc.get_kpi_catalog()}

    for row_idx, v in enumerate(values, start=1):
        is_conflict = v.source_conflict
        entry = catalog_map.get(v.kpi_id)
        unit = entry.unit if entry else v.unit

        is_pct = unit == "%"
        is_alt = row_idx % 2 == 0

        val_fmt = (pct_alt_fmt if is_pct else num_alt_fmt) if is_alt else (pct_fmt if is_pct else num_fmt)
        row_text_fmt = conflict_fmt if is_conflict else (alt_fmt if is_alt else text_fmt)

        row_data = [
            v.kpi_id,
            entry.display_name if entry else "",
            v.country_name,
            v.iso_code,
            v.period,
        ]
        for col, val in enumerate(row_data):
            ws.write(row_idx, col, val, row_text_fmt)

        # Value with unit-aware format
        if v.value is None:
            ws.write(row_idx, 5, "-", row_text_fmt)
        elif is_pct:
            ws.write(row_idx, 5, v.value / 100, val_fmt)
        else:
            ws.write(row_idx, 5, v.value, val_fmt)

        rest = [
            unit, v.source, v.data_quality_status,
            "Yes" if v.source_conflict else "",
            "Yes" if v.fallback_used else "",
            v.source_field,
            v.snapshot_id,
        ]
        for i, val in enumerate(rest, start=6):
            ws.write(row_idx, i, val, row_text_fmt)

    ws.autofilter(0, 0, len(values), len(headers) - 1)


# ── Tab 3: Source Metadata ────────────────────────────────────────────────────

def _write_source_metadata_tab(wb: xlsxwriter.Workbook, engine) -> None:
    from sqlalchemy import text
    ws = wb.add_worksheet("Source Metadata")
    header_fmt = wb.add_format({
        "bold": True, "bg_color": _HEADER_COLOR, "font_color": "white", "border": 1,
    })
    text_fmt = wb.add_format({})
    alt_fmt = wb.add_format({"bg_color": _ALT_ROW_COLOR})

    with engine.connect() as conn:
        sources = conn.execute(text(
            "SELECT source, display_name, base_url, license, default_priority, "
            "cadence, retrieval_method, notes, last_refresh_at FROM kpi_sources"
        )).fetchall()
        snapshots = conn.execute(text(
            "SELECT source, snapshot_id, fetched_at, sha256, row_count, "
            "source_version_label, status FROM source_snapshots ORDER BY fetched_at DESC LIMIT 10"
        )).fetchall()

    # Sources section
    src_headers = ["Source", "Display Name", "URL", "License", "Priority",
                   "Cadence", "Retrieval", "Notes", "Last Refresh"]
    for col, h in enumerate(src_headers):
        ws.write(0, col, h, header_fmt)
        ws.set_column(col, col, [12, 30, 40, 12, 8, 14, 14, 50, 22][col])

    for row_idx, r in enumerate(sources, start=1):
        fmt = alt_fmt if row_idx % 2 == 0 else text_fmt
        for col, val in enumerate(r):
            ws.write(row_idx, col, val or "", fmt)

    # Snapshots section (offset by sources + 2 rows)
    snap_row_start = len(sources) + 3
    snap_headers = ["Source", "Snapshot ID", "Fetched At", "SHA-256 (first 12)",
                    "Row Count", "Version Label", "Status"]
    for col, h in enumerate(snap_headers):
        ws.write(snap_row_start, col, h, header_fmt)

    for i, r in enumerate(snapshots):
        row = snap_row_start + 1 + i
        fmt = alt_fmt if i % 2 == 0 else text_fmt
        vals = [r[0], r[1], r[2], (r[3] or "")[:12], r[4], r[5], r[6]]
        for col, val in enumerate(vals):
            ws.write(row, col, val or "", fmt)


# ── Tab 4: Data Quality ───────────────────────────────────────────────────────

def _write_dq_tab(wb: xlsxwriter.Workbook, engine) -> None:
    from sqlalchemy import text
    ws = wb.add_worksheet("Data Quality")
    header_fmt = wb.add_format({
        "bold": True, "bg_color": _HEADER_COLOR, "font_color": "white", "border": 1,
    })
    pass_fmt = wb.add_format({"bg_color": "#E8F5E9"})
    fail_fmt = wb.add_format({"bg_color": _DQ_FAIL_COLOR})
    warn_fmt = wb.add_format({"bg_color": "#FFF3CD"})
    text_fmt = wb.add_format({})

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT check_name, severity, passed, details_json, created_at, run_id
            FROM data_quality_checks
            WHERE run_id = (
                SELECT run_id FROM kpi_refresh_log ORDER BY started_at DESC LIMIT 1
            )
            ORDER BY severity DESC, passed ASC
        """)).fetchall()

    headers = ["Check Name", "Severity", "Passed", "Details", "Created At", "Run ID"]
    col_widths = [28, 10, 8, 80, 22, 38]
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, header_fmt)
        ws.set_column(col, col, w)

    ws.freeze_panes(1, 0)

    for row_idx, r in enumerate(rows, start=1):
        passed = bool(r[2])
        severity = r[1]
        if not passed and severity == "error":
            fmt = fail_fmt
        elif not passed and severity == "warn":
            fmt = warn_fmt
        else:
            fmt = pass_fmt if passed else text_fmt
        ws.write(row_idx, 0, r[0], fmt)
        ws.write(row_idx, 1, severity, fmt)
        ws.write(row_idx, 2, "Yes" if passed else "No", fmt)
        ws.write(row_idx, 3, r[3] or "", fmt)
        ws.write(row_idx, 4, r[4] or "", fmt)
        ws.write(row_idx, 5, r[5] or "", fmt)
