from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from sqlalchemy import create_engine

from desktop.bridge import CVMBridge
from src.companies.market_cap import MarketCapService
from src.platform.settings import build_settings


def _bridge_with_empty_price_history(tmp_path):
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute("CREATE TABLE market_history (cd_cvm INTEGER, date TEXT, adjusted_close REAL)")
    engine = create_engine(f"sqlite:///{settings.paths.db_path.as_posix()}")
    service = SimpleNamespace(
        settings=settings,
        engine=engine,
        query_layer=SimpleNamespace(
            get_company_historical_indicator_metrics=lambda cd_cvm: {2024: {"roe": 0.1, "mg_ebit": 0.2, "mg_liq": 0.05}},
            get_company_info=lambda cd_cvm: {"ticker_b3": "PETR4"},
        ),
    )
    bridge = CVMBridge()
    bridge._service = service
    return bridge


def test_watchlist_read_never_fetches_prices_from_the_network(tmp_path, monkeypatch):
    def _network(*_args, **_kwargs):
        raise AssertionError("a normal view must not call Yahoo Finance")

    monkeypatch.setattr(MarketCapService, "fetch_yahoo_price_history", _network)
    payload = _bridge_with_empty_price_history(tmp_path).get_company_historical_indicators({"cd_cvm": 9512})

    assert payload["ok"] is True
    assert payload["price_history_status"] == "missing"
    assert payload["yearly_data"][0]["stock_price"] is None


def test_failed_startup_update_check_is_not_reported_as_up_to_date(monkeypatch):
    from desktop.updater import UpdateChecker

    def _offline(self, current_version):
        return {"status": "check_failed", "update_available": False, "error": "Could not reach GitHub Releases."}

    monkeypatch.setattr(UpdateChecker, "get_latest_release_status", _offline)
    bridge = CVMBridge()
    bridge._start_update_check()

    result = bridge.check_update()
    assert result["available"] is False
    assert result["status"] == "check_failed"
    assert "GitHub" in result["error"]
