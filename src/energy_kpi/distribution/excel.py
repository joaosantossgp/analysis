"""Excel exporter for the electricity distribution analytics domain."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xlsxwriter

from src.energy_kpi.distribution.read import DistributionReadService
from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import AppSettings
from sqlalchemy import text
logger = logging.getLogger(__name__)

# Color and formatting tokens (consistent with src/energy_kpi/excel.py)
_HEADER_COLOR = "#1F3864"
_ALT_ROW_COLOR = "#F2F2F2"
_FMT_NUM = "#,##0.0;(#,##0.0);-"
_FMT_PCT = "0.0%;(0.0%);-"
_FMT_INT = "#,##0;(#,##0);-"
_FMT_MONEY = "R$ #,##0.00;(R$ #,##0.00);-"
_FMT_MONEY_COMPACT = "R$ #,##0;(R$ #,##0);-"


def export_distribution_excel(
    settings: AppSettings,
    entity_type: str,
    entity_id: str,
) -> Path:
    """Generate and write a multi-tab ANEEL distribution Excel workbook.

    Returns the Path to the written file.
    """
    svc = DistributionReadService(settings)
    engine = get_energy_kpi_engine(settings)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    settings.paths.reports_dir.mkdir(parents=True, exist_ok=True)
    
    prefix = f"distributor_{entity_id}" if entity_type == "distributor" else f"group_{entity_id}"
    out_path = settings.paths.reports_dir / f"aneel_{prefix}_{timestamp}.xlsx"

    # Fetch data
    series = svc.get_series(entity_type=entity_type, entity_id=entity_id, frequency="monthly")
    
    detail: dict[str, Any] | None = None
    if entity_type == "distributor":
        detail = svc.get_distributor_detail(entity_id)
    else:
        detail = svc.get_group_detail(entity_id)

    if not detail:
        raise ValueError(f"Could not load details for {entity_type} {entity_id}")

    with xlsxwriter.Workbook(str(out_path)) as wb:
        # Create formats
        header_fmt = wb.add_format({
            "bold": True, "bg_color": _HEADER_COLOR, "font_color": "white",
            "border": 1, "text_wrap": True, "valign": "vcenter",
        })
        bold_fmt = wb.add_format({"bold": True})
        text_fmt = wb.add_format({"valign": "top"})
        text_alt_fmt = wb.add_format({"valign": "top", "bg_color": _ALT_ROW_COLOR})
        
        num_fmt = wb.add_format({"num_format": _FMT_NUM, "valign": "top"})
        num_alt_fmt = wb.add_format({"num_format": _FMT_NUM, "bg_color": _ALT_ROW_COLOR, "valign": "top"})
        
        pct_fmt = wb.add_format({"num_format": _FMT_PCT, "valign": "top"})
        pct_alt_fmt = wb.add_format({"num_format": _FMT_PCT, "bg_color": _ALT_ROW_COLOR, "valign": "top"})
        
        int_fmt = wb.add_format({"num_format": _FMT_INT, "valign": "top"})
        int_alt_fmt = wb.add_format({"num_format": _FMT_INT, "bg_color": _ALT_ROW_COLOR, "valign": "top"})
        
        money_fmt = wb.add_format({"num_format": _FMT_MONEY_COMPACT, "valign": "top"})
        money_alt_fmt = wb.add_format({"num_format": _FMT_MONEY_COMPACT, "bg_color": _ALT_ROW_COLOR, "valign": "top"})

        formats = {
            "header": header_fmt,
            "bold": bold_fmt,
            "text": text_fmt,
            "text_alt": text_alt_fmt,
            "num": num_fmt,
            "num_alt": num_alt_fmt,
            "pct": pct_fmt,
            "pct_alt": pct_alt_fmt,
            "int": int_fmt,
            "int_alt": int_alt_fmt,
            "money": money_fmt,
            "money_alt": money_alt_fmt,
        }

        # 1. Overview Tab
        _write_overview_tab(wb, detail, entity_type, formats)
        
        # 2. Market Tab
        _write_market_tab(wb, series, formats)
        
        # 3. Energy Balance Tab
        _write_balance_tab(wb, series, formats)
        
        # 4. Losses Tab
        _write_losses_tab(wb, series, formats)
        
        # 5. Quality Tab
        _write_quality_tab(wb, series, formats)
        
        # 6. Tariffs Tab (only for distributor)
        if entity_type == "distributor":
            _write_tariffs_tab(wb, series, formats)
            
        # 7. Delinquency Tab
        _write_delinquency_tab(wb, series, formats)
        
        # 8. Distributed Generation Tab
        _write_mmgd_tab(wb, series, formats)
        
        # 9. Source Files Tab
        _write_source_files_tab(wb, engine, formats)
        
        # 10. Methodology Tab
        _write_methodology_tab(wb, formats)

    logger.info("Distribution Excel report successfully written to %s", out_path)
    return out_path


def _write_overview_tab(wb: xlsxwriter.Workbook, detail: dict[str, Any], entity_type: str, formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("OVERVIEW")
    ws.set_column(0, 0, 25)
    ws.set_column(1, 1, 60)
    
    ws.write(0, 0, "METRIC / ATTRIBUTE", formats["header"])
    ws.write(0, 1, "VALUE", formats["header"])
    
    row = 1
    if entity_type == "distributor":
        identity = detail["identity"]
        attributes = [
            ("Canonical Name", identity["canonical_name"]),
            ("Legal Name", identity["legal_name"]),
            ("Trade Name", identity["trade_name"]),
            ("Normalized CNPJ", identity["normalized_cnpj"]),
            ("ANEEL Agent Code", identity["agent_code"]),
            ("ANEEL Distributor Code", identity["distributor_code"]),
            ("Concession Type", identity["concession_type"]),
            ("Primary State (UF)", identity["primary_uf"]),
            ("Service Area Description", identity["service_area"]),
            ("Concession Status", identity["status"]),
        ]
        for label, val in attributes:
            ws.write(row, 0, label, formats["bold"])
            ws.write(row, 1, val or "—", formats["text"])
            row += 1
            
        # Write ownership history
        row += 1
        ws.write(row, 0, "OWNERSHIP HISTORY TIMELINE", formats["header"])
        ws.write(row, 1, "", formats["header"])
        row += 1
        
        sub_headers = ["Valid From", "Valid To", "Economic Group", "CVM Code", "Listed Company Name", "Ticker", "Ownership %", "Consolidated"]
        for col, h in enumerate(sub_headers):
            ws.write(row, col, h, formats["header"])
            ws.set_column(col, col, 18)
        row += 1
        
        for idx, h in enumerate(detail["ownership_history"]):
            fmt = formats["text_alt"] if idx % 2 == 0 else formats["text"]
            ws.write(row, 0, h["valid_from"], fmt)
            ws.write(row, 1, "Present" if h["valid_to"].startswith("2099") else h["valid_to"], fmt)
            ws.write(row, 2, h["group_name"] or "Independent/Unmapped", fmt)
            ws.write(row, 3, h["cd_cvm"] or "—", fmt)
            ws.write(row, 4, h["company_name"] or "—", fmt)
            ws.write(row, 5, h["ticker_b3"] or "—", fmt)
            ws.write(row, 6, h["ownership_percentage"] or "—", fmt)
            ws.write(row, 7, "Yes" if h["operational_consolidation_flag"] == 1 else "No", fmt)
            row += 1
            
    else:
        # Economic Group Overview
        identity = detail["identity"]
        attributes = [
            ("Economic Group Name", identity["group_name"]),
            ("Linked Listed Company", identity["company_name"]),
            ("Ticker B3", identity["ticker_b3"]),
            ("CVM Code", identity["cd_cvm"]),
        ]
        for label, val in attributes:
            ws.write(row, 0, label, formats["bold"])
            ws.write(row, 1, val or "—", formats["text"])
            row += 1
            
        # Write portfolio history
        row += 1
        ws.write(row, 0, "HISTORICAL CONTROLLED PORTFOLIO", formats["header"])
        ws.write(row, 1, "", formats["header"])
        row += 1
        
        sub_headers = ["Distributor ID", "Canonical Name", "Trade Name", "Valid From", "Valid To", "Control Status", "Ownership %", "Consolidated"]
        for col, h in enumerate(sub_headers):
            ws.write(row, col, h, formats["header"])
            ws.set_column(col, col, 18)
        row += 1
        
        for idx, p in enumerate(detail["portfolio"]):
            fmt = formats["text_alt"] if idx % 2 == 0 else formats["text"]
            ws.write(row, 0, p["distributor_id"], fmt)
            ws.write(row, 1, p["canonical_name"], fmt)
            ws.write(row, 2, p["trade_name"] or "—", fmt)
            ws.write(row, 3, p["valid_from"], fmt)
            ws.write(row, 4, "Present" if p["valid_to"].startswith("2099") else p["valid_to"], fmt)
            ws.write(row, 5, p["control_status"] or "—", fmt)
            ws.write(row, 6, p["ownership_percentage"] or "—", fmt)
            ws.write(row, 7, "Yes" if p["operational_consolidation_flag"] == 1 else "No", fmt)
            row += 1


def _write_market_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("MARKET")
    headers = ["Reference Month", "Billed Energy (MWh)", "Revenue (BRL)", "Realized Average Tariff (R$/MWh)"]
    col_widths = [18, 24, 24, 30]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        money_fmt = formats["money_alt"] if is_alt else formats["money"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        
        if r["billed_energy_mwh"] is None:
            ws.write(idx, 1, "—", txt_fmt)
        else:
            ws.write(idx, 1, r["billed_energy_mwh"], val_fmt)
            
        if r["revenue_brl"] is None:
            ws.write(idx, 2, "—", txt_fmt)
        else:
            ws.write(idx, 2, r["revenue_brl"], money_fmt)
            
        # Recalculate realized average tariff
        if r["revenue_brl"] is not None and r["billed_energy_mwh"] and r["billed_energy_mwh"] > 0:
            avg_tariff = r["revenue_brl"] / r["billed_energy_mwh"]
            ws.write(idx, 3, avg_tariff, val_fmt)
        else:
            ws.write(idx, 3, "—", txt_fmt)
            
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_balance_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("ENERGY_BALANCE")
    headers = ["Reference Month", "Injected Energy (MWh)", "Measured Energy (MWh)"]
    col_widths = [18, 24, 24]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        
        if r["injected_energy_mwh"] is None:
            ws.write(idx, 1, "—", txt_fmt)
        else:
            ws.write(idx, 1, r["injected_energy_mwh"], val_fmt)
            
        if r["measured_energy_mwh"] is None:
            ws.write(idx, 2, "—", txt_fmt)
        else:
            ws.write(idx, 2, r["measured_energy_mwh"], val_fmt)
            
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_losses_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("LOSSES")
    headers = ["Reference Month", "Total Losses (MWh)", "Losses Percentage (%)"]
    col_widths = [18, 24, 24]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        pct_fmt = formats["pct_alt"] if is_alt else formats["pct"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        
        if r["losses_mwh"] is None:
            ws.write(idx, 1, "—", txt_fmt)
        else:
            ws.write(idx, 1, r["losses_mwh"], val_fmt)
            
        if r["losses_pct"] is None:
            ws.write(idx, 2, "—", txt_fmt)
        else:
            ws.write(idx, 2, r["losses_pct"], pct_fmt)
            
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_quality_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("QUALITY")
    headers = ["Reference Month", "DEC Actual (Hours)", "DEC Limit (Hours)", "FEC Actual (Times)", "FEC Limit (Times)", "Compensation Count", "Compensation Value (BRL)"]
    col_widths = [18, 20, 20, 20, 20, 22, 26]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        int_fmt = formats["int_alt"] if is_alt else formats["int"]
        money_fmt = formats["money_alt"] if is_alt else formats["money"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        
        ws.write(idx, 1, r["dec_actual"] if r["dec_actual"] is not None else "—", val_fmt if r["dec_actual"] is not None else txt_fmt)
        ws.write(idx, 2, r["dec_limit"] if r["dec_limit"] is not None else "—", val_fmt if r["dec_limit"] is not None else txt_fmt)
        ws.write(idx, 3, r["fec_actual"] if r["fec_actual"] is not None else "—", val_fmt if r["fec_actual"] is not None else txt_fmt)
        ws.write(idx, 4, r["fec_limit"] if r["fec_limit"] is not None else "—", val_fmt if r["fec_limit"] is not None else txt_fmt)
        ws.write(idx, 5, r["compensation_count"] if r["compensation_count"] is not None else "—", int_fmt if r["compensation_count"] is not None else txt_fmt)
        ws.write(idx, 6, r["compensation_value"] if r["compensation_value"] is not None else "—", money_fmt if r["compensation_value"] is not None else txt_fmt)
        
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_tariffs_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("TARIFFS")
    headers = ["Reference Month", "TE Homologated (R$/MWh)", "TUSD Homologated (R$/MWh)"]
    col_widths = [18, 28, 28]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        ws.write(idx, 1, r["te_homologated"] if r["te_homologated"] is not None else "—", val_fmt if r["te_homologated"] is not None else txt_fmt)
        ws.write(idx, 2, r["tusd_homologated"] if r["tusd_homologated"] is not None else "—", val_fmt if r["tusd_homologated"] is not None else txt_fmt)
        
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_delinquency_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("DELINQUENCY")
    headers = ["Reference Month", "Delinquency Percentage (%)"]
    col_widths = [18, 28]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        pct_fmt = formats["pct_alt"] if is_alt else formats["pct"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        ws.write(idx, 1, r["delinquency_pct"] if r["delinquency_pct"] is not None else "—", pct_fmt if r["delinquency_pct"] is not None else txt_fmt)
        
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_mmgd_tab(wb: xlsxwriter.Workbook, series: list[dict[str, Any]], formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("DISTRIBUTED_GENERATION")
    headers = ["Reference Month", "MMGD Projects Count", "MMGD Installed Capacity (kW)"]
    col_widths = [18, 24, 28]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    for idx, r in enumerate(series, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        int_fmt = formats["int_alt"] if is_alt else formats["int"]
        val_fmt = formats["num_alt"] if is_alt else formats["num"]
        
        ws.write(idx, 0, r["period"], txt_fmt)
        ws.write(idx, 1, r["mmgd_projects_count"] if r["mmgd_projects_count"] is not None else "—", int_fmt if r["mmgd_projects_count"] is not None else txt_fmt)
        ws.write(idx, 2, r["mmgd_capacity_kw"] if r["mmgd_capacity_kw"] is not None else "—", val_fmt if r["mmgd_capacity_kw"] is not None else txt_fmt)
        
    ws.autofilter(0, 0, len(series), len(headers) - 1)


def _write_source_files_tab(wb: xlsxwriter.Workbook, engine: Any, formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("SOURCE_FILES")
    headers = ["Snapshot ID", "Source / Dataset", "Fetched At", "SHA-256 Checksum", "Row Count", "File Path"]
    col_widths = [38, 24, 20, 64, 14, 80]
    
    for col, (h, w) in enumerate(zip(headers, col_widths)):
        ws.write(0, col, h, formats["header"])
        ws.set_column(col, col, w)
        
    ws.freeze_panes(1, 0)
    
    query = """
        SELECT snapshot_id, source, fetched_at, sha256, row_count, file_path
        FROM source_snapshots
        ORDER BY fetched_at DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()
        
    for idx, r in enumerate(rows, start=1):
        is_alt = idx % 2 == 0
        txt_fmt = formats["text_alt"] if is_alt else formats["text"]
        int_fmt = formats["int_alt"] if is_alt else formats["int"]
        
        ws.write(idx, 0, r[0], txt_fmt)
        ws.write(idx, 1, r[1], txt_fmt)
        ws.write(idx, 2, r[2], txt_fmt)
        ws.write(idx, 3, r[3] or "—", txt_fmt)
        ws.write(idx, 4, r[4] if r[4] is not None else "—", int_fmt if r[4] is not None else txt_fmt)
        ws.write(idx, 5, r[5], txt_fmt)
        
    ws.autofilter(0, 0, len(rows), len(headers) - 1)


def _write_methodology_tab(wb: xlsxwriter.Workbook, formats: dict[str, Any]) -> None:
    ws = wb.add_worksheet("METHODOLOGY")
    ws.set_column(0, 0, 25)
    ws.set_column(1, 1, 80)
    
    ws.write(0, 0, "METRIC / CALCULATION", formats["header"])
    ws.write(0, 1, "FORMULA AND METHODOLOGICAL NOTES", formats["header"])
    
    methods = [
        ("Realized Average Tariff", "Computed month-by-month as Revenue (BRL) divided by Billed Energy (MWh)."),
        ("Group Losses Percentage", "Consolidated mathematically across controlled entities as SUM(losses_mwh) / SUM(injected_energy_mwh). Simple arithmetical averaging is avoided."),
        ("Group DEC / FEC Actuals", "Consolidated weighted average: weighted by monthly active consumer counts (NumCon indicator) from ANEEL continuity facts."),
        ("Group Delinquency", "Consolidated weighted average: weighted by monthly revenue (revenue_brl) from SAMP Mercado facts."),
        ("MMGD Installed Capacity", "MMGD capacity stock is represented at end-of-period. Commissioning dates are parsed dynamically. Owner name and CPF/CNPJ data are stripped at parse-time for security."),
        ("Offline Guarantee", "All data in this report is extracted entirely from the local SQLite store (energy_kpis.db), preserving complete offline operability."),
    ]
    
    for idx, (label, val) in enumerate(methods, start=1):
        ws.write(idx, 0, label, formats["bold"])
        ws.write(idx, 1, val, formats["text"])
