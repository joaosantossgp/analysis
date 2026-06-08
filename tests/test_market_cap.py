from __future__ import annotations

import io
import pytest
from pathlib import Path
from types import SimpleNamespace

from src.companies.market_cap import MarketCapService, MarketCapEntry
from src.platform.settings import build_settings
from tests.test_company_universe import FakeReadService


def _setup_service(tmp_path, catalog_items=None):
    settings = build_settings(project_root=tmp_path)
    # Configure custom path for company_universe_snapshot_path under tmp_path
    snapshot_path = tmp_path / "data" / "metadata" / "b3_market_cap_universe_snapshot.csv"
    object.__setattr__(settings.paths, "company_universe_snapshot_path", snapshot_path)

    read_service = None
    if catalog_items is not None:
        read_service = FakeReadService(settings, catalog_items)
        # Mock company_catalog attribute on FakeReadService
        class FakeCatalog:
            def list_entries(self):
                return catalog_items
        read_service.company_catalog = FakeCatalog()

    return MarketCapService(settings=settings, read_service=read_service), snapshot_path


def test_import_snapshot_success(tmp_path):
    catalog_items = [
        SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="33000167000101", ticker_b3="PETR4.SA", is_active=True),
        SimpleNamespace(cd_cvm=4170, company_name="VALE", nome_comercial="VALE ON", cnpj="33592510000154", ticker_b3="VALE3.SA", is_active=True),
    ]
    service, snapshot_path = _setup_service(tmp_path, catalog_items)

    csv_data = """as_of_date,rank,ticker,company_name,market_cap_brl,source,method,source_url_or_id
2026-05-28,1,PETR4,PETROBRAS,500000000000.0,B3,direct,http://b3.com.br
2026-05-28,2,VALE3,VALE,400000000000.0,B3,direct,http://b3.com.br
"""

    status = service.import_snapshot(io.StringIO(csv_data))
    assert status["available"] is True
    assert status["row_count"] == 2
    assert status["mapped_count"] == 2
    assert len(status["warnings"]) == 0

    # Verify offline reading
    entries = service.read_snapshot()
    assert len(entries) == 2
    assert entries[0].cd_cvm == 9512
    assert entries[0].mapping_status == "mapped"
    assert entries[0].mapping_confidence == 1.0
    assert entries[1].cd_cvm == 4170
    assert entries[1].mapping_status == "mapped"


def test_import_schema_validation_failures(tmp_path):
    service, _ = _setup_service(tmp_path, [])

    # Missing market cap column
    csv_missing_mkt = """as_of_date,rank,ticker,company_name
2026-05-28,1,PETR4,PETROBRAS
"""
    with pytest.raises(ValueError, match="missing a market cap column"):
        service.import_snapshot(io.StringIO(csv_missing_mkt))

    # Invalid float in market cap
    csv_invalid_float = """as_of_date,rank,ticker,company_name,market_cap_brl
2026-05-28,1,PETR4,PETROBRAS,not_a_float
"""
    with pytest.raises(ValueError, match="Invalid market cap numeric format"):
        service.import_snapshot(io.StringIO(csv_invalid_float))


def test_mapping_fallbacks(tmp_path):
    catalog_items = [
        # Match by CNPJ
        SimpleNamespace(cd_cvm=1234, company_name="CNPJ Match", nome_comercial=None, cnpj="12345678000199", ticker_b3=None, is_active=True),
        # Match by exact Name
        SimpleNamespace(cd_cvm=5678, company_name="NAME MATCH", nome_comercial="TRADE MATCH", cnpj=None, ticker_b3=None, is_active=True),
    ]
    service, _ = _setup_service(tmp_path, catalog_items)

    csv_data = """company_name,ticker,market_cap_brl,cnpj
Unmapped Ticker,XYZ9,1000000.0,
Match by CNPJ Company,,2000000.0,12-345.678/0001-99
TRADE MATCH,,3000000.0,
"""
    status = service.import_snapshot(io.StringIO(csv_data))
    assert status["row_count"] == 3
    assert status["mapped_count"] == 2
    assert status["unmapped_count"] == 1
    assert "1 companies could not be mapped" in status["warnings"][0]

    entries = service.read_snapshot()
    # Ordered by market cap desc: TRADE MATCH (3m), Match by CNPJ (2m), XYZ9 (1m)
    assert entries[0].company_name == "TRADE MATCH"
    assert entries[0].cd_cvm == 5678
    assert entries[0].mapping_status == "mapped"
    assert entries[0].mapping_confidence == 0.8  # name match

    assert entries[1].company_name == "Match by CNPJ Company"
    assert entries[1].cd_cvm == 1234
    assert entries[1].mapping_status == "mapped"
    assert entries[1].mapping_confidence == 0.9  # CNPJ match

    assert entries[2].company_name == "Unmapped Ticker"
    assert entries[2].cd_cvm is None
    assert entries[2].mapping_status == "unmapped"
    assert entries[2].mapping_confidence == 0.0


def test_fetch_from_yahoo_finance(tmp_path, monkeypatch):
    catalog_items = [
        SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="33000167000101", ticker_b3="PETR4.SA", is_active=True),
        SimpleNamespace(cd_cvm=4170, company_name="VALE", nome_comercial="VALE ON", cnpj="33592510000154", ticker_b3="VALE3.SA", is_active=True),
    ]
    service, snapshot_path = _setup_service(tmp_path, catalog_items)

    # 1. Verify failure when provider is local_snapshot
    object.__setattr__(service.settings, "market_cap_provider", "local_snapshot")
    with pytest.raises(RuntimeError, match="Yahoo Finance market-cap provider is not enabled"):
        service.fetch_from_yahoo_finance()

    # Enable yahoo_finance provider (canonical name)
    object.__setattr__(service.settings, "market_cap_provider", "yahoo_finance")
    object.__setattr__(service.settings, "enable_experimental_yfinance", True)

    mock_response_json = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "PETR4.SA",
                    "marketCap": 500000000000.0,
                    "longName": "Petróleo Brasileiro S.A. - Petrobras",
                    "shortName": "PETROBRAS PN"
                },
                {
                    "symbol": "VALE3.SA",
                    "marketCap": 400000000000.0,
                    "longName": "Vale S.A.",
                    "shortName": "VALE ON"
                }
            ],
            "error": None
        }
    }

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return mock_response_json

    called_urls = []
    def mock_session_get(self, url, **kwargs):
        if "symbols=" in url:
            called_urls.append(url)
            return FakeResponse()
        class DummyResponse:
            def raise_for_status(self): pass
            @property
            def text(self): return "dummy_crumb"
        return DummyResponse()

    import requests
    monkeypatch.setattr(requests.Session, "get", mock_session_get)

    status = service.fetch_from_yahoo_finance()

    assert len(called_urls) > 0
    assert "symbols=" in called_urls[0]
    assert status["available"] is True
    assert status["row_count"] == 2
    assert status["mapped_count"] == 2
    assert len(status["warnings"]) == 0

    entries = service.read_snapshot()
    assert len(entries) == 2
    assert entries[0].ticker == "PETR4.SA"
    assert entries[0].cd_cvm == 9512
    assert entries[0].rank == 1
    assert entries[0].market_cap_brl == 500000000000.0
    assert entries[0].source == "yahoo_finance"
    assert entries[0].method == "yahoo_finance_bulk_quote"
    assert entries[0].provider_status == "unofficial_free"
    assert entries[0].mapping_status == "mapped"

    assert entries[1].ticker == "VALE3.SA"
    assert entries[1].cd_cvm == 4170
    assert entries[1].rank == 2
    assert entries[1].market_cap_brl == 400000000000.0


def test_fetch_from_yahoo_finance_accepts_deprecated_yfinance_alias(tmp_path, monkeypatch):
    """fetch_from_yahoo_finance must not raise when market_cap_provider='yfinance' (deprecated alias)."""
    catalog_items = [
        SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="33000167000101", ticker_b3="PETR4.SA", is_active=True),
    ]
    service, snapshot_path = _setup_service(tmp_path, catalog_items)
    object.__setattr__(service.settings, "market_cap_provider", "yfinance")  # deprecated alias

    mock_response_json = {
        "quoteResponse": {
            "result": [{"symbol": "PETR4.SA", "marketCap": 500000000000.0, "longName": "PETROBRAS PN"}],
            "error": None,
        }
    }

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return mock_response_json

    import requests
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kwargs: FakeResponse())

    # Should NOT raise — 'yfinance' is accepted as an alias
    status = service.fetch_from_yahoo_finance()
    assert status["available"] is True
    # New snapshots must always write the canonical source name
    entries = service.read_snapshot()
    assert entries[0].source == "yahoo_finance"
    assert entries[0].method == "yahoo_finance_bulk_quote"


def test_read_snapshot_accepts_old_yfinance_bulk_quote_method(tmp_path):
    """Snapshots written by old code with method='yfinance_bulk_quote' must still be readable."""
    service, snapshot_path = _setup_service(tmp_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    headers = "as_of_date,rank,cd_cvm,cnpj,company_name,ticker,market_cap_brl,source,method,source_url_or_id,downloaded_at,mapping_status,mapping_confidence,notes,provider_status"
    # Old row uses the old method string
    row = "2026-05-24,1,9512,,PETROBRAS,PETR4,500000000000.0,yahoo_finance,yfinance_bulk_quote,http://example.com,2026-05-29T00:00:00Z,mapped,1.0,,unofficial_free"
    snapshot_path.write_text("\n".join([headers, row]), encoding="utf-8")

    entries = service.read_snapshot()
    assert len(entries) == 1
    assert entries[0].method == "yfinance_bulk_quote"  # old value preserved on read — no migration required
    assert entries[0].source == "yahoo_finance"


def test_import_snapshot_with_new_metrics(tmp_path):
    catalog_items = [
        SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="33000167000101", ticker_b3="PETR4.SA", is_active=True),
    ]
    service, _ = _setup_service(tmp_path, catalog_items)

    csv_data = """as_of_date,rank,ticker,company_name,market_cap_brl,source,method,source_url_or_id,dividend_yield,pe_ratio,pb_ratio,beta
2026-05-28,1,PETR4,PETROBRAS,500000000000.0,B3,direct,http://b3.com.br,0.082,10.5,1.2,0.95
"""
    status = service.import_snapshot(io.StringIO(csv_data))
    assert status["available"] is True
    assert status["row_count"] == 1
    
    entries = service.read_snapshot()
    assert len(entries) == 1
    assert entries[0].dividend_yield == 0.082
    assert entries[0].pe_ratio == 10.5
    assert entries[0].pb_ratio == 1.2
    assert entries[0].beta == 0.95


def test_fetch_from_yahoo_finance_with_metrics(tmp_path, monkeypatch):
    catalog_items = [
        SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="33000167000101", ticker_b3="PETR4.SA", is_active=True),
    ]
    service, _ = _setup_service(tmp_path, catalog_items)
    object.__setattr__(service.settings, "market_cap_provider", "yahoo_finance")

    mock_response_json = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "PETR4.SA",
                    "marketCap": 500000000000.0,
                    "longName": "PETROBRAS PN",
                    "trailingAnnualDividendYield": 0.075,
                    "trailingPE": 9.8,
                    "priceToBook": 1.15,
                    "beta": 0.85,
                }
            ],
            "error": None
        }
    }

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return mock_response_json

    def mock_session_get(self, url, **kwargs):
        if "symbols=" in url:
            return FakeResponse()
        class DummyResponse:
            def raise_for_status(self): pass
            @property
            def text(self): return "dummy_crumb"
        return DummyResponse()

    import requests
    monkeypatch.setattr(requests.Session, "get", mock_session_get)

    service.fetch_from_yahoo_finance()
    entries = service.read_snapshot()
    assert len(entries) == 1
    assert entries[0].dividend_yield == 0.075
    assert entries[0].pe_ratio == 9.8
    assert entries[0].pb_ratio == 1.15
    assert entries[0].beta == 0.85


def test_fetch_yahoo_price_history(tmp_path, monkeypatch):
    service, _ = _setup_service(tmp_path, [])
    
    mock_chart_json = {
        "chart": {
            "result": [
                {
                    "timestamp": [1609459200, 1640995200],  # 2021-01-01, 2022-01-01
                    "indicators": {
                        "adjclose": [
                            {"adjclose": [25.5, 30.0]}
                        ],
                        "quote": [
                            {"close": [24.0, 29.0]}
                        ]
                    }
                }
            ],
            "error": None
        }
    }
    
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return mock_chart_json
        
    def mock_get(url, **kwargs):
        return FakeResponse()
        
    import requests
    monkeypatch.setattr(requests, "get", mock_get)
    
    prices = service.fetch_yahoo_price_history("PETR4")
    assert prices == {2021: 25.5, 2022: 30.0}


