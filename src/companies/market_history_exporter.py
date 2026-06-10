# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any

import xlsxwriter

from src.companies.market_history import MarketHistoryService


VALID_PERIODS = {"1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX", "custom"}
VALID_INTERVALS = {"1d", "1wk", "1mo"}
VALID_VIEWS = {"price", "return", "yield", "volume"}
SERIES_BY_VIEW = {
    "price": {
        "close": ("Close Price", "close", "price"),
        "adjusted_close": ("Adjusted Close", "adjusted_close", "price"),
    },
    "return": {
        "price_return_index": ("Price Return", "price_return_index", "percent_index"),
        "total_return_index": ("Total Shareholder Return", "total_return_index", "percent_index"),
    },
    "yield": {
        "ttm_dividend_yield": ("TTM Dividend Yield", "ttm_dividend_yield", "percent"),
    },
    "volume": {
        "volume": ("Trading Volume", "volume", "volume"),
    },
}
VIEW_LABELS = {
    "price": "Price",
    "return": "Return",
    "yield": "Dividend Yield",
    "volume": "Volume",
}
SOURCE_DISCLAIMER = "Yahoo Finance is an unofficial free source; values are cached locally by CVMAnalytics."


class MarketHistoryExportError(ValueError):
    pass


def build_market_history_export(
    *,
    service: MarketHistoryService,
    read_service: Any,
    cd_cvm: int,
    ticker: str | None,
    period: str,
    custom_start: str | None = None,
    custom_end: str | None = None,
    interval: str = "1d",
    view: str = "price",
    selected_series: list[str] | tuple[str, ...] | None = None,
    value_mode: str | None = None,
    chart_type: str | None = None,
    generated_at: datetime | None = None,
) -> tuple[str, bytes, dict[str, Any]]:
    request = _validate_request(
        cd_cvm=cd_cvm,
        ticker=ticker,
        period=period,
        custom_start=custom_start,
        custom_end=custom_end,
        interval=interval,
        view=view,
        selected_series=selected_series,
    )
    generated = generated_at or datetime.now(timezone.utc)

    history = service.get_market_history(
        request["cd_cvm"],
        ticker=request["ticker"],
        start_date=request["custom_start"] if request["period"] == "custom" else None,
        end_date=request["custom_end"] if request["period"] == "custom" else None,
        period=None if request["period"] == "custom" else request["period"],
        interval=request["interval"],
    )
    if history.get("error"):
        raise MarketHistoryExportError(str(history["error"]))
    if not history.get("has_local_data"):
        raise MarketHistoryExportError("No local market history is available for this ticker.")

    observations = history.get("observations") or []
    if not observations:
        raise MarketHistoryExportError("The selected market-history range has no observations.")

    company = _company_info(read_service, request["cd_cvm"])
    rows, columns = _build_table_rows(
        observations=observations,
        view=request["view"],
        selected_series=request["selected_series"],
        value_mode=value_mode,
    )
    if not rows:
        raise MarketHistoryExportError("The selected series contain no exportable observations.")

    payload = _write_workbook(
        company=company,
        history=history,
        request=request,
        rows=rows,
        columns=columns,
        value_mode=value_mode,
        chart_type=chart_type,
        generated_at=generated,
    )
    filename = build_market_history_filename(
        ticker=history.get("ticker") or request["ticker"] or f"cvm{request['cd_cvm']}",
        view=request["view"],
        period=request["period"],
        custom_start=request["custom_start"],
        custom_end=request["custom_end"],
        generated_at=generated,
    )
    info = {
        "observation_count": len(rows),
        "first_observation_date": rows[0]["Date"],
        "last_observation_date": rows[-1]["Date"],
        "ticker": history.get("ticker") or request["ticker"],
        "view": request["view"],
        "interval": history.get("interval") or request["interval"],
    }
    return filename, payload, info


def build_market_history_filename(
    *,
    ticker: str,
    view: str,
    period: str,
    custom_start: str | None = None,
    custom_end: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    safe_ticker = _sanitize_filename_part(str(ticker).replace(".SA", "").upper()) or "ticker"
    safe_view = _sanitize_filename_part(view.lower()) or "market"
    if period == "custom":
        start = _sanitize_filename_part(custom_start or "start")
        end = _sanitize_filename_part(custom_end or "end")
        suffix = f"{start}_to_{end}"
    else:
        suffix = _sanitize_filename_part(period)
    if not suffix:
        suffix = (generated_at or datetime.now()).strftime("%Y-%m-%d")
    return f"{safe_ticker}_market_data_{safe_view}_{suffix}.xlsx"


def _validate_request(**params: Any) -> dict[str, Any]:
    cd_cvm = int(params["cd_cvm"])
    if cd_cvm <= 0:
        raise MarketHistoryExportError("cd_cvm is required.")

    ticker = str(params.get("ticker") or "").strip().upper() or None
    if ticker and "." not in ticker:
        ticker = f"{ticker}.SA"
    if not ticker:
        raise MarketHistoryExportError("ticker is required.")

    period = str(params.get("period") or "1Y").strip()
    period_key = period.upper() if period.lower() != "custom" else "custom"
    if period_key not in VALID_PERIODS:
        raise MarketHistoryExportError(f"Invalid market period: {period!r}.")

    interval = str(params.get("interval") or "1d").strip()
    if interval not in VALID_INTERVALS:
        raise MarketHistoryExportError(f"Invalid market interval: {interval!r}.")

    view = str(params.get("view") or "price").strip().lower()
    if view not in VALID_VIEWS:
        raise MarketHistoryExportError(f"Invalid market view: {view!r}.")

    selected_raw = params.get("selected_series") or []
    selected = [str(item) for item in selected_raw if isinstance(item, str)]
    allowed = SERIES_BY_VIEW[view]
    selected = [item for item in selected if item in allowed]
    if not selected:
        raise MarketHistoryExportError("At least one visible market series must be selected.")

    custom_start = _date_or_none(params.get("custom_start"))
    custom_end = _date_or_none(params.get("custom_end"))
    if period_key == "custom":
        if not custom_start or not custom_end:
            raise MarketHistoryExportError("Custom start and end dates are required.")
        if custom_start > custom_end:
            raise MarketHistoryExportError("Custom start date must be less than or equal to end date.")

    return {
        "cd_cvm": cd_cvm,
        "ticker": ticker,
        "period": period_key,
        "custom_start": custom_start,
        "custom_end": custom_end,
        "interval": interval,
        "view": view,
        "selected_series": selected,
    }


def _build_table_rows(
    *,
    observations: list[dict[str, Any]],
    view: str,
    selected_series: list[str],
    value_mode: str | None,
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]]]:
    columns = [("Date", "Date", "date")]
    base_values: dict[str, float] = {}
    if view == "price" and value_mode == "base_100":
        for series_id in selected_series:
            _, field, _ = SERIES_BY_VIEW[view][series_id]
            for obs in observations:
                value = obs.get(field)
                if value not in (None, 0):
                    base_values[series_id] = float(value)
                    break

    for series_id in selected_series:
        label, _, kind = SERIES_BY_VIEW[view][series_id]
        if view == "price" and value_mode == "base_100":
            kind = "number"
        excel_kind = "percent" if kind == "percent_index" else kind
        columns.append((label, series_id, excel_kind))

    rows: list[dict[str, Any]] = []
    for obs in observations:
        row: dict[str, Any] = {"Date": obs.get("date")}
        any_value = False
        for series_id in selected_series:
            _, field, kind = SERIES_BY_VIEW[view][series_id]
            value = obs.get(field)
            if value is None:
                row[series_id] = None
                continue
            number = float(value)
            if kind == "percent_index":
                number -= 1.0
            elif view == "price" and value_mode == "base_100":
                base = base_values.get(series_id)
                number = (number / base) * 100.0 if base else number
            row[series_id] = number
            any_value = True
        if any_value:
            rows.append(row)
    return rows, columns


def _write_workbook(
    *,
    company: dict[str, Any],
    history: dict[str, Any],
    request: dict[str, Any],
    rows: list[dict[str, Any]],
    columns: list[tuple[str, str, str]],
    value_mode: str | None,
    chart_type: str | None,
    generated_at: datetime,
) -> bytes:
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True, "nan_inf_to_errors": True})
    worksheet = workbook.add_worksheet("Market Data")

    formats = {
        "title": workbook.add_format({"bold": True, "font_size": 13}),
        "label": workbook.add_format({"bold": True, "font_color": "#1F4E78"}),
        "header": workbook.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1}),
        "date": workbook.add_format({"num_format": "yyyy-mm-dd"}),
        "price": workbook.add_format({"num_format": 'R$ #,##0.00;(R$ #,##0.00);-'}),
        "percent": workbook.add_format({"num_format": "0.00%;(0.00%);-"}),
        "volume": workbook.add_format({"num_format": "#,##0;(#,##0);-"}),
        "number": workbook.add_format({"num_format": "#,##0.00;(#,##0.00);-"}),
    }

    worksheet.write(0, 0, "Historical Market Data Export", formats["title"])
    metadata = _metadata_rows(company, history, request, rows, value_mode, chart_type, generated_at)
    row_idx = 2
    for label, value, kind in metadata:
        worksheet.write(row_idx, 0, label, formats["label"])
        _write_cell(worksheet, row_idx, 1, value, kind, formats)
        row_idx += 1

    row_idx += 1
    worksheet.write(row_idx, 0, "Summary", formats["title"])
    row_idx += 1
    for label, value, kind in _summary_rows(request["view"], history.get("summary") or {}, rows):
        worksheet.write(row_idx, 0, label, formats["label"])
        _write_cell(worksheet, row_idx, 1, value, kind, formats)
        row_idx += 1

    row_idx += 2
    table_header_row = row_idx
    for col_idx, (label, _, _) in enumerate(columns):
        worksheet.write(table_header_row, col_idx, label, formats["header"])

    for offset, data_row in enumerate(rows, start=1):
        excel_row = table_header_row + offset
        for col_idx, (_, key, kind) in enumerate(columns):
            value = data_row.get(key)
            _write_cell(worksheet, excel_row, col_idx, value, kind, formats)

    last_row = table_header_row + len(rows)
    last_col = len(columns) - 1
    worksheet.autofilter(table_header_row, 0, last_row, last_col)
    worksheet.freeze_panes(table_header_row + 1, 1)
    worksheet.set_column(0, 0, 13)
    for col_idx, (_, _, kind) in enumerate(columns[1:], start=1):
        width = 18 if kind != "volume" else 16
        worksheet.set_column(col_idx, col_idx, width)

    workbook.close()
    return output.getvalue()


def _metadata_rows(
    company: dict[str, Any],
    history: dict[str, Any],
    request: dict[str, Any],
    rows: list[dict[str, Any]],
    value_mode: str | None,
    chart_type: str | None,
    generated_at: datetime,
) -> list[tuple[str, Any, str]]:
    selected_labels = [SERIES_BY_VIEW[request["view"]][sid][0] for sid in request["selected_series"]]
    return [
        ("Company", company.get("company_name") or company.get("nome_comercial") or "", "text"),
        ("CVM code", request["cd_cvm"], "number"),
        ("Ticker", history.get("ticker") or request["ticker"], "text"),
        ("Share class", _share_class_label(history.get("ticker") or request["ticker"]), "text"),
        ("Source", history.get("source") or "yahoo_finance", "text"),
        ("Source disclaimer", SOURCE_DISCLAIMER, "text"),
        ("Export timestamp", generated_at.replace(tzinfo=None), "datetime"),
        ("Cache status", "stale" if history.get("is_stale") else "offline ready", "text"),
        ("Cache last updated", _date_or_none(history.get("last_downloaded_at")), "date"),
        ("Selected market period", request["period"], "text"),
        ("Custom start date", request["custom_start"], "date"),
        ("Custom end date", request["custom_end"], "date"),
        ("Active market view", VIEW_LABELS[request["view"]], "text"),
        ("Selected series", ", ".join(selected_labels), "text"),
        ("Observation interval", history.get("interval") or request["interval"], "text"),
        ("First observation date", rows[0]["Date"], "date"),
        ("Last observation date", rows[-1]["Date"], "date"),
        ("Exported observation count", len(rows), "number"),
        ("Chart value interpretation", _value_interpretation(request["view"], value_mode), "text"),
        ("Chart type", chart_type or "", "text"),
    ]


def _summary_rows(view: str, summary: dict[str, Any], rows: list[dict[str, Any]]) -> list[tuple[str, Any, str]]:
    latest_date = rows[-1]["Date"] if rows else None
    if view == "price":
        return [
            ("Latest price", summary.get("final_close"), "price"),
            ("Latest observation date", latest_date, "date"),
            ("Period high", summary.get("period_high"), "price"),
            ("Period low", summary.get("period_low"), "price"),
        ]
    if view == "return":
        return [
            ("Price return", summary.get("price_return"), "percent"),
            ("Total shareholder return", summary.get("total_return"), "percent"),
            ("Annualized return", summary.get("annualized_total_return"), "percent"),
        ]
    if view == "yield":
        return [
            ("Latest TTM dividend yield", _latest_value(rows, "ttm_dividend_yield"), "percent"),
            ("Dividends per share", summary.get("dividends_per_share"), "price"),
            ("Latest observation date", latest_date, "date"),
        ]
    return [
        ("Latest volume", _latest_value(rows, "volume"), "volume"),
        ("Average volume", summary.get("average_daily_volume"), "volume"),
        ("Latest observation date", latest_date, "date"),
    ]


def _write_cell(worksheet: Any, row: int, col: int, value: Any, kind: str, formats: dict[str, Any]) -> None:
    if value is None or value == "":
        worksheet.write_blank(row, col, None)
        return
    if kind in {"date", "datetime"}:
        parsed = _parse_datetime(value)
        if parsed is None:
            worksheet.write(row, col, str(value))
        else:
            worksheet.write_datetime(row, col, parsed, formats["date"])
        return
    if kind in {"price", "percent", "volume", "number"}:
        try:
            worksheet.write_number(row, col, float(value), formats[kind])
            return
        except (TypeError, ValueError):
            worksheet.write_blank(row, col, None)
            return
    worksheet.write(row, col, value)


def _company_info(read_service: Any, cd_cvm: int) -> dict[str, Any]:
    try:
        info = read_service.query_layer.get_company_info(cd_cvm)
        if info:
            return dict(info)
    except Exception:
        pass
    return {"cd_cvm": cd_cvm, "company_name": f"CVM {cd_cvm}"}


def _date_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    return text[:10]


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = _date_or_none(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def _latest_value(rows: list[dict[str, Any]], key: str) -> Any:
    for row in reversed(rows):
        value = row.get(key)
        if value is not None:
            return value
    return None


def _share_class_label(ticker: str | None) -> str | None:
    if not ticker:
        return None
    symbol = ticker.replace(".SA", "")
    if symbol.endswith("3"):
        return f"{symbol} (Common/ON)"
    if symbol.endswith(("4", "5", "6")):
        return f"{symbol} (Preferred/PN)"
    if symbol.endswith("11"):
        return f"{symbol} (Unit)"
    return symbol


def _value_interpretation(view: str, value_mode: str | None) -> str:
    if view == "return":
        return "Cumulative percentage return (stored as decimal fractions)."
    if view == "yield":
        return "TTM dividend yield stored as decimal fractions."
    if view == "price" and value_mode == "base_100":
        return "Price series indexed to base 100."
    return "Raw local cached values."


def _sanitize_filename_part(value: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", str(value).strip())
    cleaned = cleaned.replace(" ", "_").replace("..", "_")
    return re.sub(r"_+", "_", cleaned).strip("._")
