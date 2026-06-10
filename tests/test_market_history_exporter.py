from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest
from sqlalchemy import text

from src.companies.market_history import MarketHistoryService, ensure_market_history_tables_for_connection
from src.companies.market_history_exporter import (
    MarketHistoryExportError,
    build_market_history_export,
    build_market_history_filename,
)
from src.platform.db import build_engine
from src.platform.settings import build_settings


class FakeReadService:
    def __init__(self, settings):
        self.engine = build_engine(settings)
        with self.engine.begin() as conn:
            ensure_market_history_tables_for_connection(conn)

    @property
    def query_layer(self):
        class QueryLayer:
            def get_company_info(self, cd_cvm):
                return {
                    "cd_cvm": cd_cvm,
                    "company_name": "PETROBRAS PN",
                    "nome_comercial": "PETROBRAS",
                    "ticker_b3": "PETR4",
                }

        return QueryLayer()


def _service(tmp_path):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    read_service = FakeReadService(settings)
    return MarketHistoryService(settings=settings, read_service=read_service), read_service


def _seed_market_history(service, ticker="PETR4.SA", downloaded_at="2026-06-08T00:00:00+00:00"):
    rows = [
        ("2026-01-02", 10.0, 10.5, 9.5, 10.0, 9.0, 1000, 0.0),
        ("2026-01-03", 11.0, 11.5, 10.5, 11.0, 10.2, 2000, 0.5),
        ("2026-01-04", 12.0, 12.5, 11.5, 12.0, 11.4, 3000, 0.0),
    ]
    with service.engine.begin() as conn:
        for date, open_, high, low, close, adjusted_close, volume, dividend in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO market_history (
                        cd_cvm, ticker, date, open, high, low, close, adjusted_close,
                        volume, dividend, split_ratio, source, provider_status, downloaded_at
                    ) VALUES (
                        9512, :ticker, :date, :open, :high, :low, :close, :adjusted_close,
                        :volume, :dividend, 1.0, 'yahoo_finance', 'unofficial_free', :downloaded_at
                    )
                    """
                ),
                {
                    "ticker": ticker,
                    "date": date,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "adjusted_close": adjusted_close,
                    "volume": volume,
                    "dividend": dividend,
                    "downloaded_at": downloaded_at,
                },
            )


def _workbook(payload: bytes):
    return openpyxl.load_workbook(io.BytesIO(payload), data_only=True)


def _table_headers(ws):
    for row in ws.iter_rows():
        values = [cell.value for cell in row]
        if values and values[0] == "Date":
            return row[0].row, values
    raise AssertionError("Date header not found")


def _export(service, read_service, **overrides):
    params = {
        "service": service,
        "read_service": read_service,
        "cd_cvm": 9512,
        "ticker": "PETR4.SA",
        "period": "custom",
        "custom_start": "2026-01-02",
        "custom_end": "2026-01-04",
        "interval": "1d",
        "view": "price",
        "selected_series": ["close"],
        "generated_at": datetime(2026, 6, 10, tzinfo=timezone.utc),
    }
    params.update(overrides)
    return build_market_history_export(**params)


def test_price_export_close_only_has_real_dates_and_numbers(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    filename, payload, info = _export(service, read_service, selected_series=["close"])
    wb = _workbook(payload)
    ws = wb["Market Data"]
    header_row, headers = _table_headers(ws)

    assert filename == "PETR4_market_data_price_2026-01-02_to_2026-01-04.xlsx"
    assert headers[:2] == ["Date", "Close Price"]
    assert "Adjusted Close" not in headers
    assert info["observation_count"] == 3
    assert isinstance(ws.cell(header_row + 1, 1).value, datetime)
    assert ws.cell(header_row + 1, 2).value == 10
    assert isinstance(ws.cell(header_row + 1, 2).value, (int, float))
    assert ws.freeze_panes == ws.cell(header_row + 1, 2).coordinate
    assert ws.auto_filter.ref is not None
    assert list(ws.merged_cells.ranges) == []


def test_price_export_adjusted_and_close_columns(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    _, payload, _ = _export(service, read_service, selected_series=["adjusted_close", "close"])
    ws = _workbook(payload)["Market Data"]
    _, headers = _table_headers(ws)

    assert headers[:3] == ["Date", "Adjusted Close", "Close Price"]


def test_return_export_uses_decimal_percentage_scale(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    _, payload, _ = _export(
        service,
        read_service,
        view="return",
        selected_series=["price_return_index", "total_return_index"],
    )
    ws = _workbook(payload)["Market Data"]
    header_row, headers = _table_headers(ws)

    assert headers[:3] == ["Date", "Price Return", "Total Shareholder Return"]
    assert ws.cell(header_row + 1, 2).value == pytest.approx(0.0)
    assert ws.cell(header_row + 3, 2).value == pytest.approx(0.2)
    assert ws.cell(header_row + 3, 3).value == pytest.approx((11.4 / 9.0) - 1.0)
    assert ws.cell(header_row + 3, 2).number_format == "0.00%;(0.00%);-"


def test_yield_and_volume_exports_keep_selected_columns(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    _, yield_payload, _ = _export(service, read_service, view="yield", selected_series=["ttm_dividend_yield"])
    _, volume_payload, _ = _export(service, read_service, view="volume", selected_series=["volume"])

    yield_ws = _workbook(yield_payload)["Market Data"]
    volume_ws = _workbook(volume_payload)["Market Data"]
    _, yield_headers = _table_headers(yield_ws)
    volume_header_row, volume_headers = _table_headers(volume_ws)
    assert yield_headers[:2] == ["Date", "TTM Dividend Yield"]
    assert volume_headers[:2] == ["Date", "Trading Volume"]
    assert volume_ws.cell(volume_header_row + 3, 2).value == 3000


def test_price_base_100_mode_matches_chart_interpretation(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    _, payload, _ = _export(
        service,
        read_service,
        selected_series=["close"],
        value_mode="base_100",
    )
    ws = _workbook(payload)["Market Data"]
    header_row, _ = _table_headers(ws)
    assert ws.cell(header_row + 1, 2).value == 100
    assert ws.cell(header_row + 3, 2).value == 120


def test_all_supported_periods_export(tmp_path):
    service, read_service = _service(tmp_path)
    old_download = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    _seed_market_history(service, downloaded_at=old_download)

    for period in ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX"]:
        _, payload, info = _export(
            service,
            read_service,
            period=period,
            custom_start=None,
            custom_end=None,
        )
        assert _workbook(payload)["Market Data"].max_row > 1
        assert info["observation_count"] == 3


def test_alternative_share_class_uses_active_ticker(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service, ticker="PETR3.SA")

    filename, payload, _ = _export(service, read_service, ticker="PETR3.SA")
    ws = _workbook(payload)["Market Data"]

    assert filename.startswith("PETR3_market_data_price_")
    assert "PETR3.SA" in [cell.value for cell in ws["B"]]


def test_no_selected_series_and_no_local_data_fail(tmp_path):
    service, read_service = _service(tmp_path)
    with pytest.raises(MarketHistoryExportError, match="At least one"):
        _export(service, read_service, selected_series=[])
    with pytest.raises(MarketHistoryExportError, match="No local market history"):
        _export(service, read_service, selected_series=["close"])


def test_invalid_custom_range_fails(tmp_path):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)
    with pytest.raises(MarketHistoryExportError, match="less than or equal"):
        _export(service, read_service, custom_start="2026-01-04", custom_end="2026-01-02")


def test_filename_sanitization():
    filename = build_market_history_filename(
        ticker='PE/TR:4.SA',
        view='pr"ice',
        period="custom",
        custom_start="../2026-01-02",
        custom_end="2026-01-04",
    )
    assert filename == "PE_TR_4_market_data_pr_ice_2026-01-02_to_2026-01-04.xlsx"


def test_export_does_not_call_yahoo_finance(tmp_path, monkeypatch):
    service, read_service = _service(tmp_path)
    _seed_market_history(service)

    import yfinance as yf

    monkeypatch.setattr(yf, "Ticker", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("network call")))
    _, payload, _ = _export(service, read_service)
    assert _workbook(payload)["Market Data"].title == "Market Data"
