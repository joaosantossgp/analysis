from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from src.companies.universe import (
    CompanyUniverseService,
    CompanyUniverseUnavailableError,
)
from src.platform.db import build_engine
from src.platform.settings import build_settings


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
    yfinance_enabled: bool = False,
    yfinance_fetch_limit: int = 0,
):
    snapshot_path = tmp_path / "data" / "metadata" / "b3_market_cap_universe_snapshot.csv"
    monkeypatch.setenv(
        "CVM_ENABLE_YFINANCE_UNIVERSE_PROVIDER",
        "true" if yfinance_enabled else "false",
    )
    monkeypatch.setenv("CVM_YFINANCE_UNIVERSE_FETCH_LIMIT", str(yfinance_fetch_limit))
    monkeypatch.setenv("CVM_COMPANY_UNIVERSE_SNAPSHOT_PATH", str(snapshot_path))
    settings = build_settings(project_root=tmp_path)
    # Ensure build_settings paths are correctly adjusted
    object.__setattr__(settings.paths, "company_universe_snapshot_path", snapshot_path)
    if rows is not None:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rows, encoding="utf-8")
    return settings


def test_top_preset_uses_snapshot_and_warns_when_less_than_requested(tmp_path, monkeypatch):
    headers = "as_of_date,rank,cd_cvm,cnpj,company_name,ticker,market_cap_brl,source,method,source_url_or_id,downloaded_at,mapping_status,mapping_confidence,notes"
    row1 = "2026-05-24,1,9512,,PETROBRAS,PETR4,500000000000.0,test_snapshot,csv_import,http://b3.com.br,2026-05-29T00:00:00Z,mapped,1.0,"
    row2 = "2026-05-24,2,4170,,VALE,VALE3,400000000000.0,test_snapshot,csv_import,http://b3.com.br,2026-05-29T00:00:00Z,mapped,1.0,"
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join([headers, row1, row2]),
    )
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    # Setup database catalog mock
    class FakeCatalog:
        def list_entries(self):
            return [
                SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="", ticker_b3="PETR4", is_active=True),
                SimpleNamespace(cd_cvm=4170, company_name="VALE", nome_comercial="VALE", cnpj="", ticker_b3="VALE3", is_active=True),
            ]
    read_service.company_catalog = FakeCatalog()

    selection = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    ).get_company_universe_by_preset("top_100")

    assert selection.company_ids == (9512, 4170)
    assert selection.source == "test_snapshot"
    assert selection.source_date == "2026-05-24"
    assert selection.warning is not None
    assert "Only 2 valid ranked companies" in selection.warning


def test_yahoo_finance_is_default_provider_and_reads_are_local_only(tmp_path, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    assert settings.market_cap_provider == "yahoo_finance"
    assert settings.market_cap_auto_refresh is True
    assert settings.market_cap_cache_max_age_days == 7

    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )
    service = CompanyUniverseService(settings=settings, read_service=read_service)
    
    # Resolving Top presets must raise CompanyUniverseUnavailableError if no snapshot exists
    with pytest.raises(CompanyUniverseUnavailableError):
        service.get_company_universe_by_preset("top_100")


def test_yfinance_alias_normalizes_to_yahoo_finance(tmp_path, monkeypatch):
    """CVM_MARKET_CAP_PROVIDER=yfinance must be accepted as a deprecated alias for yahoo_finance."""
    import warnings
    monkeypatch.setenv("CVM_MARKET_CAP_PROVIDER", "yfinance")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings = build_settings(project_root=tmp_path)
    # The alias must be normalized to the canonical name
    assert settings.market_cap_provider == "yahoo_finance"
    # A deprecation warning must be emitted
    deprecation_msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("yfinance" in m and "yahoo_finance" in m for m in deprecation_msgs), (
        f"Expected DeprecationWarning about yfinance alias, got: {deprecation_msgs}"
    )



def test_top_preset_requires_market_cap_provider(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(tmp_path, monkeypatch, None)
    read_service = FakeReadService(settings, [])

    with pytest.raises(CompanyUniverseUnavailableError) as exc:
        CompanyUniverseService(
            settings=settings,
            read_service=read_service,
        ).get_company_universe_by_preset("top_200")

    assert "Market cap ranking source is unavailable" in str(exc.value)
    assert "BRAPI_TOKEN" not in str(exc.value)
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
    headers = "as_of_date,rank,cd_cvm,cnpj,company_name,ticker,market_cap_brl,source,method,source_url_or_id,downloaded_at,mapping_status,mapping_confidence,notes"
    row1 = "2026-05-24,1,9512,,PETROBRAS,PETR4,500000000000.0,test_snapshot,csv_import,http://b3.com.br,2026-05-29T00:00:00Z,mapped,1.0,"
    settings = _settings_with_snapshot(
        tmp_path,
        monkeypatch,
        "\n".join([headers, row1]),
    )
    read_service = FakeReadService(
        settings,
        [SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4")],
    )

    class FakeCatalog:
        def list_entries(self):
            return [
                SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="", ticker_b3="PETR4", is_active=True),
            ]
    read_service.company_catalog = FakeCatalog()

    service = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
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


def test_snapshot_provider_raises_error_if_missing(tmp_path, monkeypatch):
    settings = _settings_with_snapshot(tmp_path, monkeypatch, None)
    
    read_service = FakeReadService(
        settings,
        [
            SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", ticker_b3="PETR4"),
            SimpleNamespace(cd_cvm=4170, company_name="VALE", ticker_b3="VALE3"),
        ],
    )

    class FakeCatalog:
        def list_entries(self):
            return [
                SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="", ticker_b3="PETR4", is_active=True),
                SimpleNamespace(cd_cvm=4170, company_name="VALE", nome_comercial="VALE", cnpj="", ticker_b3="VALE3", is_active=True),
            ]
    read_service.company_catalog = FakeCatalog()

    service = CompanyUniverseService(
        settings=settings,
        read_service=read_service,
    )

    with pytest.raises(CompanyUniverseUnavailableError) as exc:
        service.get_company_universe_by_preset("top_100")

    assert "Market cap ranking source is unavailable" in str(exc.value)
    assert not settings.paths.company_universe_snapshot_path.exists()
