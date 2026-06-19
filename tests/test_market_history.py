from __future__ import annotations

import math
import pytest
import pandas as pd
from datetime import datetime, timedelta
from types import SimpleNamespace

from src.platform.settings import build_settings
from src.platform.db import build_engine
from src.companies.market_history import (
    MarketHistoryService,
    resolve_ticker,
    ensure_market_history_tables_for_connection,
)


def _setup_history_service(tmp_path, catalog_info=None):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    class FakeReadService:
        def __init__(self, settings, info):
            self.engine = build_engine(settings)
            self.info = info
            with self.engine.begin() as conn:
                ensure_market_history_tables_for_connection(conn)
                
        class QueryLayer:
            def __init__(self, info):
                self.info = info
            def get_company_info(self, cd_cvm):
                return self.info.get(cd_cvm)
                
        @property
        def query_layer(self):
            return self.QueryLayer(self.info)
            
    read_service = FakeReadService(settings, catalog_info or {})
    service = MarketHistoryService(settings=settings, read_service=read_service)
    return service, read_service


# 1. Ticker resolution and suffix normalization tests
def test_resolve_ticker_success(tmp_path):
    catalog_info = {
        9512: {"ticker_b3": "PETR4"},
        4170: {"ticker_b3": "VALE3.SA"},
    }
    service, read_service = _setup_history_service(tmp_path, catalog_info)
    
    # Resolves via query_layer info
    assert resolve_ticker(9512, read_service) == "PETR4.SA"
    assert resolve_ticker(4170, read_service) == "VALE3.SA"
    
    # Resolves via TICKER_MAP fallback (e.g. 9512 is mapped to PETR4 in TICKER_MAP)
    assert resolve_ticker(9512, None) == "PETR4.SA"
    
    # Ticker resolution failure for unknown code
    assert resolve_ticker(99999, None) is None


def test_resolve_company_tickers_success(tmp_path):
    catalog_info = {
        9512: {"ticker_b3": "PETR4"},
        4170: {"ticker_b3": "VALE3.SA"},
    }
    service, read_service = _setup_history_service(tmp_path, catalog_info)
    
    from src.companies.market_history import resolve_company_tickers
    
    petr_tickers = resolve_company_tickers(9512, read_service)
    assert "PETR4.SA" in petr_tickers
    assert "PETR3.SA" in petr_tickers
    assert "PETR11.SA" in petr_tickers
    assert petr_tickers[0] == "PETR4.SA"
    
    vale_tickers = resolve_company_tickers(4170, read_service)
    assert vale_tickers[0] == "VALE3.SA"
    assert "VALE3.SA" in vale_tickers
    assert "VALE4.SA" in vale_tickers


def test_eletrobras_market_history_uses_axia_yahoo_alias(tmp_path, monkeypatch):
    catalog_info = {2437: {"ticker_b3": "ELET3"}}
    service, read_service = _setup_history_service(tmp_path, catalog_info)

    from src.companies.market_history import resolve_company_tickers

    assert resolve_ticker(2437, read_service) == "AXIA3.SA"
    assert resolve_company_tickers(2437, read_service)[:3] == ["AXIA3.SA", "AXIA5.SA", "AXIA6.SA"]

    requested_tickers = []
    dates = pd.date_range(start="2026-06-01", periods=2)
    df = pd.DataFrame({
        "Open": [51.0, 52.0],
        "High": [52.0, 53.0],
        "Low": [50.0, 51.0],
        "Close": [51.5, 52.5],
        "Adj Close": [51.5, 52.5],
        "Volume": [1000000, 1200000],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates)

    class CapturingYFTicker:
        def __init__(self, ticker):
            requested_tickers.append(ticker)

        def history(self, *args, **kwargs):
            return df

    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", CapturingYFTicker)

    res = service.refresh_market_history(2437, start_date="2026-06-01")
    assert res["ok"] is True
    assert res["ticker"] == "AXIA3.SA"
    assert requested_tickers == ["AXIA3.SA"]
    assert res["inserted_rows"] == 2


# 2. Ingestion and provider-response normalization tests
class MockYFTicker:
    def __init__(self, df_to_return):
        self.df = df_to_return

    def history(self, *args, **kwargs):
        return self.df


def test_provider_response_normalization_and_rejection(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    # Build pandas DataFrame with some normal data, some missing values, and negative close (to be rejected)
    dates = pd.date_range(start="2026-05-01", periods=5)
    data = {
        "Open": [34.0, 34.5, float("nan"), 35.0, float("nan")],
        "High": [34.8, 35.0, 35.2, 35.6, 36.0],
        "Low": [33.8, 34.2, 34.0, 34.7, 35.1],
        "Close": [34.2, 34.7, -10.0, 35.1, 35.8],  # Index 2 Close is negative -> rejected
        "Adj Close": [32.5, 32.9, None, 33.3, 34.0],
        "Volume": [100000, 200000, 150000, 250000, 300000],
        "Dividends": [0.0, 1.5, 0.0, 0.0, 0.0],
        "Stock Splits": [1.0, 1.0, 1.0, 1.0, 1.0],
    }
    df = pd.DataFrame(data, index=dates)
    
    # Monkeypatch yfinance to return our mock
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))
    
    res = service.refresh_market_history(9512, start_date="2026-05-01")
    assert res["ok"] is True
    assert res["downloaded_rows"] == 4  # 5 rows total, 1 rejected negative price
    assert res["inserted_rows"] == 4
    assert res["rejected_rows"] == 1
    
    # Let's inspect local database content
    history_res = service.get_market_history(9512, start_date="2026-05-01", end_date="2026-05-05")
    assert history_res["has_local_data"] is True
    obs = history_res["observations"]
    assert len(obs) == 4
    
    # Check that open is null at index 3 (which is 2026-05-05)
    # Dates are: 05-01, 05-02, 05-04, 05-05 (05-03 rejected)
    assert obs[0]["date"] == "2026-05-01"
    assert obs[1]["date"] == "2026-05-02"
    assert obs[1]["dividend"] == 1.5
    assert obs[2]["date"] == "2026-05-04"
    assert obs[2]["open"] == 35.0
    assert obs[3]["date"] == "2026-05-05"
    assert obs[3]["open"] is None  # NaN converted to null


def test_duplicate_date_removal(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    # Build dataframe with duplicate date values in index
    dates = pd.to_datetime(["2026-05-01", "2026-05-01", "2026-05-02"])
    data = {
        "Open": [34.0, 34.2, 34.5],
        "High": [34.5, 34.5, 35.0],
        "Low": [33.8, 33.8, 34.2],
        "Close": [34.2, 34.1, 34.7],
        "Adj Close": [32.5, 32.4, 32.9],
        "Volume": [100000, 120000, 200000],
        "Dividends": [0.0, 0.0, 0.0],
        "Stock Splits": [1.0, 1.0, 1.0],
    }
    df = pd.DataFrame(data, index=dates)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))
    
    res = service.refresh_market_history(9512)
    assert res["ok"] is True
    # The deduping should keep one observation per date
    assert res["downloaded_rows"] == 2
    
    history_res = service.get_market_history(9512)
    assert len(history_res["observations"]) == 2


def test_zero_ohlc_values_do_not_pollute_summary(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)

    dates = pd.to_datetime(["2026-06-05", "2026-06-08"])
    df = pd.DataFrame({
        "Open": [41.0, 0.0],
        "High": [42.0, 0.0],
        "Low": [40.0, 0.0],
        "Close": [41.5, 41.2],
        "Adj Close": [41.5, 41.2],
        "Volume": [100000, 0],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates)

    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))

    res = service.refresh_market_history(9512)
    assert res["ok"] is True
    assert res["inserted_rows"] == 2

    hist = service.get_market_history(9512)
    obs = hist["observations"]
    assert obs[1]["open"] is None
    assert obs[1]["high"] is None
    assert obs[1]["low"] is None
    assert hist["summary"]["period_high"] == 42.0
    assert hist["summary"]["period_low"] == 40.0


# 3. Idempotent upserts and incremental refresh boundaries
def test_idempotent_upserts_and_incremental(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    dates = pd.date_range(start="2026-05-01", periods=3)
    data = {
        "Open": [34.0, 34.5, 35.0],
        "High": [34.8, 35.0, 35.6],
        "Low": [33.8, 34.2, 34.7],
        "Close": [34.2, 34.7, 35.1],
        "Adj Close": [32.5, 32.9, 33.3],
        "Volume": [100000, 200000, 250000],
        "Dividends": [0.0, 0.0, 0.0],
        "Stock Splits": [1.0, 1.0, 1.0],
    }
    df = pd.DataFrame(data, index=dates)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))
    
    # Initial download
    res1 = service.refresh_market_history(9512, start_date="2026-05-01")
    assert res1["inserted_rows"] == 3
    
    # Second download (same data) -> Idempotency check: rows should be unchanged
    res2 = service.refresh_market_history(9512, start_date="2026-05-01")
    assert res2["inserted_rows"] == 0
    assert res2["updated_rows"] == 0
    assert res2["unchanged_rows"] == 3
    
    # Update check: change Close on one date and re-run -> should count as updated_rows
    df.loc["2026-05-02", "Close"] = 36.0
    res3 = service.refresh_market_history(9512, start_date="2026-05-01")
    assert res3["updated_rows"] == 1
    assert res3["unchanged_rows"] == 2


# 4. Returns and dividend yield methodologies
def test_returns_and_cagr_short_period(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    dates_short = pd.date_range(start="2026-05-01", periods=3)
    df_short = pd.DataFrame({
        "Open": [10.0, 11.0, 12.0],
        "High": [10.5, 11.5, 12.5],
        "Low": [9.8, 10.8, 11.8],
        "Close": [10.0, 11.0, 12.0],
        "Adj Close": [9.0, 9.9, 11.4], # Adj close grows faster (e.g. after dividend)
        "Volume": [100, 100, 100],
        "Dividends": [0.0, 0.5, 0.0],
        "Stock Splits": [1.0, 1.0, 1.0],
    }, index=dates_short)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df_short))
    service.refresh_market_history(9512)
    
    hist_short = service.get_market_history(9512)
    summary_short = hist_short["summary"]
    
    # Price Return = 12.0 / 10.0 - 1 = +20%
    assert summary_short["price_return"] == pytest.approx(0.20)
    # Total Shareholder Return = 11.4 / 9.0 - 1 = +26.67%
    assert summary_short["total_return"] == pytest.approx(0.2666667, abs=1e-5)
    # CAGR should be null because period is less than 365 calendar days
    assert summary_short["annualized_total_return"] is None
    
    # Check ex-dividend ex-post TTM yield calculation
    obs = hist_short["observations"]
    # TTM dividend on 05-02 is 0.5, close is 11.0 -> TTM yield = 0.5/11.0 = 4.545%
    assert obs[1]["ttm_dividend_yield"] == pytest.approx(0.5 / 11.0)


def test_returns_and_cagr_long_period(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    dates_long = pd.to_datetime(["2025-01-01", "2026-01-01"])
    df_long = pd.DataFrame({
        "Open": [10.0, 14.4],
        "High": [10.0, 14.4],
        "Low": [10.0, 14.4],
        "Close": [10.0, 14.4],
        "Adj Close": [10.0, 14.4],
        "Volume": [100, 100],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates_long)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df_long))
    service.refresh_market_history(9512)
    
    hist_long = service.get_market_history(9512)
    summary_long = hist_long["summary"]
    # CAGR = (14.4 / 10.0) ^ (365 / 365) - 1 = 44%
    assert summary_long["annualized_total_return"] == pytest.approx(0.44)


# 5. Offline and provider-failure cache preservation tests
def test_fallback_on_provider_failure(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    # Fill database with initial valid data
    dates = pd.date_range(start="2026-05-01", periods=2)
    df = pd.DataFrame({
        "Open": [34.0, 34.5],
        "High": [34.8, 35.0],
        "Low": [33.8, 34.2],
        "Close": [34.2, 34.7],
        "Adj Close": [32.5, 32.9],
        "Volume": [100000, 200000],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))
    service.refresh_market_history(9512)
    
    # Now simulate provider failure (throws Exception)
    def failing_ticker_history(*args, **kwargs):
        raise RuntimeError("Yahoo Finance service unavailable")
        
    class FailingYFTicker:
        def __init__(self, ticker):
            pass
        def history(self, *args, **kwargs):
            return failing_ticker_history()
            
    monkeypatch.setattr(yf, "Ticker", FailingYFTicker)
    
    # Refresh should fail but return warning/error details, and NOT delete previous data
    res = service.refresh_market_history(9512)
    assert res["ok"] is False
    assert "Yahoo Finance service unavailable" in res["error"]
    
    # Verify local data is still present
    hist_res = service.get_market_history(9512)
    assert hist_res["has_local_data"] is True
    assert len(hist_res["observations"]) == 2


# 6. JSON bridge serialization check
def test_bridge_serialization_safety(tmp_path):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    # Directly insert rows with some NaN/Inf values (which can happen under SQLite or provider)
    # The service must clean them up and return standard JSON-serializable types.
    with service.engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(
            text(
                """
                INSERT INTO market_history (
                    cd_cvm, ticker, date, open, high, low, close, adjusted_close, volume, dividend, split_ratio, source, provider_status, downloaded_at
                ) VALUES (
                    9512, 'PETR4.SA', '2026-05-01', NULL, 35.0, 34.0, 34.5, 34.5, NULL, 0.0, 1.0, 'yahoo_finance', 'unofficial_free', '2026-06-08T00:00:00Z'
                )
                """
            )
        )
        
    hist = service.get_market_history(9512)
    assert hist["has_local_data"] is True
    obs = hist["observations"][0]
    
    # Check open is None (JSON null) and volume is None
    assert obs["open"] is None
    assert obs["volume"] is None
    # Check correct float conversions
    assert isinstance(obs["close"], float)
    assert obs["close"] == 34.5
    
    # Test JSON dumps doesn't raise error (e.g. no float('nan'), float('inf') or datetime objects)
    import json
    json_str = json.dumps(hist)
    loaded = json.loads(json_str)
    assert loaded["observations"][0]["open"] is None
    assert loaded["observations"][0]["close"] == 34.5


# 7. Date range validation and empty state warnings
def test_date_range_validation_and_warnings(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    dates = pd.date_range(start="2026-05-01", periods=3)
    df = pd.DataFrame({
        "Open": [34.0, 34.5, 35.0],
        "High": [34.8, 35.0, 35.6],
        "Low": [33.8, 34.2, 34.7],
        "Close": [34.2, 34.7, 35.1],
        "Adj Close": [32.5, 32.9, 33.3],
        "Volume": [100000, 200000, 250000],
        "Dividends": [0.0, 0.0, 0.0],
        "Stock Splits": [1.0, 1.0, 1.0],
    }, index=dates)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df))
    service.refresh_market_history(9512)
    
    # Query with non-overlapping period -> should warn and return empty observations
    hist = service.get_market_history(9512, start_date="2026-06-01", end_date="2026-06-30")
    assert len(hist["observations"]) == 0
    assert hist["summary"] is None
    assert any("contains no trading sessions" in w for w in hist["warnings"])


def test_multiple_tickers_persistence_and_retrieval(tmp_path, monkeypatch):
    catalog_info = {9512: {"ticker_b3": "PETR4"}}
    service, _ = _setup_history_service(tmp_path, catalog_info)
    
    # 1. Fetch first ticker (PETR4.SA)
    dates = pd.date_range(start="2026-05-01", periods=2)
    df_petr4 = pd.DataFrame({
        "Open": [34.0, 34.5],
        "High": [34.8, 35.0],
        "Low": [33.8, 34.2],
        "Close": [34.2, 34.7],
        "Adj Close": [32.5, 32.9],
        "Volume": [100000, 200000],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates)
    
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df_petr4))
    res1 = service.refresh_market_history(9512, ticker="PETR4.SA")
    assert res1["ok"] is True
    assert res1["inserted_rows"] == 2
    
    # 2. Fetch second ticker (PETR3.SA)
    df_petr3 = pd.DataFrame({
        "Open": [35.0, 35.5],
        "High": [35.8, 36.0],
        "Low": [34.8, 35.2],
        "Close": [35.2, 35.7],
        "Adj Close": [33.5, 34.0],
        "Volume": [150000, 250000],
        "Dividends": [0.0, 0.0],
        "Stock Splits": [1.0, 1.0],
    }, index=dates)
    
    monkeypatch.setattr(yf, "Ticker", lambda ticker: MockYFTicker(df_petr3))
    res2 = service.refresh_market_history(9512, ticker="PETR3.SA")
    assert res2["ok"] is True
    assert res2["inserted_rows"] == 2
    
    # 3. Retrieve PETR4.SA status and history
    status_petr4 = service.get_market_history_status(9512, ticker="PETR4.SA")
    assert status_petr4["ticker"] == "PETR4.SA"
    assert status_petr4["row_count"] == 2
    
    hist_petr4 = service.get_market_history(9512, ticker="PETR4.SA")
    assert len(hist_petr4["observations"]) == 2
    assert hist_petr4["observations"][0]["close"] == 34.2
    
    # 4. Retrieve PETR3.SA status and history
    status_petr3 = service.get_market_history_status(9512, ticker="PETR3.SA")
    assert status_petr3["ticker"] == "PETR3.SA"
    assert status_petr3["row_count"] == 2
    
    hist_petr3 = service.get_market_history(9512, ticker="PETR3.SA")
    assert len(hist_petr3["observations"]) == 2
    assert hist_petr3["observations"][0]["close"] == 35.2


# 8. Resolver robustness and normalization tests
def test_resolve_ticker_robustness(tmp_path):
    catalog_info = {
        9512: {"ticker_b3": "PETR4"},
        4170: {"ticker_b3": "VALE3.SA"},
    }
    service, read_service = _setup_history_service(tmp_path, catalog_info)
    
    # Verify robust integer conversion from string inputs
    assert resolve_ticker("9512", read_service) == "PETR4.SA"
    assert resolve_ticker("4170", read_service) == "VALE3.SA"
    
    # Verify no duplication of exchange suffix
    assert resolve_ticker("9512", None) == "PETR4.SA"
    assert resolve_ticker(9512, None) == "PETR4.SA"
    
    # Verify invalid non-numeric strings return None instead of raising exceptions
    assert resolve_ticker("invalid_cvm", read_service) is None
    assert resolve_ticker(None, read_service) is None
    
    from src.companies.market_history import resolve_company_tickers
    
    # Verify resolve_company_tickers also handles string CVM safely
    petr_tickers = resolve_company_tickers("9512", read_service)
    assert petr_tickers[0] == "PETR4.SA"
    assert "PETR3.SA" in petr_tickers
    
    invalid_tickers = resolve_company_tickers("invalid_cvm", read_service)
    assert invalid_tickers == []


# 9. On-demand database table creation tests
def test_on_demand_table_creation(tmp_path):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    class FakeReadService:
        def __init__(self, settings):
            self.engine = build_engine(settings)
            
        @property
        def query_layer(self):
            class FakeQueryLayer:
                def get_company_info(self, cd_cvm):
                    return None
            return FakeQueryLayer()
            
    read_service = FakeReadService(settings)
    
    # Verify the table does not exist initially
    from sqlalchemy import inspect
    inspector = inspect(read_service.engine)
    assert "market_history" not in inspector.get_table_names()
    
    service = MarketHistoryService(settings=settings, read_service=read_service)
    
    # Query status — this should automatically create the table
    status = service.get_market_history_status(9512, "PETR4.SA")
    assert status["ticker"] == "PETR4.SA"
    assert status["has_local_data"] is False
    assert status["warnings"] == ["No local market history has been downloaded yet."]
    
    # Verify the table exists now
    inspector = inspect(read_service.engine)
    assert "market_history" in inspector.get_table_names()
