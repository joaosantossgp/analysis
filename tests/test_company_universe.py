from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from src.company_universe import (
    CompanyUniverseService,
    CompanyUniverseUnavailableError,
)
from src.db import build_engine
from src.settings import build_settings


class FakeReadService:
    def __init__(self, settings, items):
        self.engine = build_engine(settings)
        self.items = tuple(items)

    def list_companies(self, **kwargs):
        return SimpleNamespace(items=self.items)


def _settings_with_snapshot(
    tmp_path,
    monkeypatch,
    rows: str | None,
    *,
    brapi_token: str | None = None,
    yfinance_enabled: bool = False,
    yfinance_fetch_limit: int = 0,
):
    snapshot_path = tmp_path / "data" / "metadata" / "b3_market_cap_universe_snapshot.csv"
    if brapi_token:
        monkeypatch.setenv("BRAPI_TOKEN", brapi_token)
    else:
        monkeypatch.delenv("BRAPI_TOKEN", raising=False)
        monkeypatch.delenv("CVM_BRAPI_TOKEN", raising=False)
    monkeypatch.setenv(
        "CVM_ENABLE_YFINANCE_UNIVERSE_PROVIDER",
        "true" if yfinance_enabled else "false",
    )
    monkeypatch.setenv("CVM_YFINANCE_UNIVERSE_FETCH_LIMIT", str(yfinance_fetch_limit))
    monkeypatch.setenv("CVM_COMPANY_UNIVERSE_SNAPSHOT_PATH", str(snapshot_path))
    settings = build_settings(project_root=tmp_path)
    if rows is not None:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rows, encoding="utf-8")
    return settings


class FakeBrapiResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_top_preset_uses_snapshot_and_warns_when_less_than_requested(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join(
            [
                "cd_cvm,ticker,company_name,market_cap,market_cap_rank,source,source_date",
                "9512,PETR4,PETROBRAS,500000000000,1,test_snapshot,2026-05-24",
                "4170,VALE3,VALE,400000000000,2,test_snapshot,2026-05-24",
            ]
        ),
    )
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("top_100")

    assert selection.company_ids == (9512, 4170)
    assert selection.source == "test_snapshot"
    assert selection.source_date == "2026-05-24"
    assert selection.warning is not None
    assert "Only 2 valid ranked companies" in selection.warning


def test_brapi_provider_is_primary_when_configured(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join(
            [
                "cd_cvm,ticker,company_name,market_cap,market_cap_rank,source,source_date",
                "9512,PETR4,PETROBRAS,1,1,test_snapshot,2026-05-24",
            ]
        ),
        brapi_token="test-token",
    )
    calls = []

    def fake_get(url, headers, params, timeout):
        calls.append((url, headers, params, timeout))
        return FakeBrapiResponse(
            {
                "stocks": [
                    {"stock": "VALE3", "name": "VALE", "market_cap_basic": 700.0},
                    {"stock": "PETR4", "name": "PETROBRAS", "market_cap_basic": 600.0},
                ]
            }
        )

    monkeypatch.setattr("src.company_universe.requests.get", fake_get)
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("top_100")

    assert selection.company_ids == (4170, 9512)
    assert selection.source == "brapi_quote_list"
    assert calls[0][0].endswith("/quote/list")
    assert calls[0][1]["Authorization"] == "Bearer test-token"
    assert calls[0][2]["sortBy"] == "market_cap_basic"


def test_snapshot_fallback_is_used_when_brapi_fails(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join(
            [
                "cd_cvm,ticker,company_name,market_cap,market_cap_rank,source,source_date",
                "9512,PETR4,PETROBRAS,500000000000,1,test_snapshot,2026-05-24",
                "4170,VALE3,VALE,400000000000,2,test_snapshot,2026-05-24",
            ]
        ),
        brapi_token="test-token",
    )

    def fake_get(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr("src.company_universe.requests.get", fake_get)
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("top_100")

    assert selection.company_ids == (9512, 4170)
    assert selection.source == "test_snapshot"


def test_yfinance_provider_is_opt_in_cached_dev_fallback(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        None,
        yfinance_enabled=True,
    )
    settings.paths.yfinance_cache_path.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.yfinance_cache_path.write_text(
        json.dumps(
            {
                "PETR4.SA": {"mktcap": 500000000000, "fetched_at": "2026-05-24T10:00:00"},
                "VALE3.SA": {"mktcap": 400000000000, "fetched_at": "2026-05-24T10:00:00"},
            }
        ),
        encoding="utf-8",
    )
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("top_100")

    assert selection.company_ids == (9512, 4170)
    assert selection.source == "yfinance_experimental"


def test_top_preset_requires_market_cap_provider(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(tmp_path, monkeypatch, None)
    read_service = FakeReadService(settings, [])

    with pytest.raises(CompanyUniverseUnavailableError) as exc:
        CompanyUniverseService(
            settings=settings,
            read_service=read_service,
        ).get_company_universe_by_preset("top_200")

    assert "Market cap ranking source is unavailable" in str(exc.value)
    assert "BRAPI_TOKEN" in str(exc.value)
    assert "All B3 companies" in str(exc.value)


def test_all_preset_uses_available_cvm_companies_without_market_cap_snapshot(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(tmp_path, monkeypatch, None)
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("all")

    assert selection.company_ids == (9512, 4170)
    assert selection.source == "cvm_company_catalog"
    assert selection.warning is None


def test_onboarding_state_skips_existing_financial_data(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(tmp_path, monkeypatch, None)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE financial_reports (
                "CD_CVM" INTEGER,
                "COMPANY_NAME" TEXT
            )
            """
        )
        conn.execute(
            'INSERT INTO financial_reports ("CD_CVM", "COMPANY_NAME") VALUES (9512, "PETROBRAS")'
        )
        conn.commit()

    state = CompanyUniverseService(
        settings=settings,
        read_service=FakeReadService(settings, []),
    ).get_onboarding_state()

    assert state["first_run_completed"] is True
    assert state["should_show"] is False
    assert state["setup_status"] == "existing_data"


def test_mark_setup_started_persists_state_and_company_universe(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join(
            [
                "cd_cvm,ticker,company_name,market_cap,market_cap_rank,source,source_date",
                "9512,PETR4,PETROBRAS,500000000000,1,test_snapshot,2026-05-24",
            ]
        ),
    )
    service = CompanyUniverseService(
        settings=settings,
        read_service=FakeReadService(
            settings,
            [SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4")],
        ),
    )
    selection = service.get_company_universe_by_preset("top_100")

    service.mark_setup_started(selection, refresh_job_id="job-1")

    state = json.loads(settings.paths.onboarding_state_path.read_text(encoding="utf-8"))
    assert state["first_run_completed"] is False
    assert state["selected_company_universe"] == "top_100"
    assert state["refresh_job_id"] == "job-1"

    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM company_universe").fetchone()[0]
        preset = conn.execute(
            "SELECT selected_preset FROM company_universe WHERE cd_cvm = 9512"
        ).fetchone()[0]
    assert count == 1
    assert preset == "top_100"
