# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.platform.contracts import RefreshPolicy, RefreshRequest
from src.refresh.service import HeadlessRefreshService
from src.platform.settings import build_settings
from src.financials.utils import current_reporting_year_cap


def _create_financial_reports_table(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE financial_reports (
                CD_CVM INTEGER,
                COMPANY_NAME TEXT,
                REPORT_YEAR INTEGER,
                STATEMENT_TYPE TEXT,
                PERIOD_LABEL TEXT
            )
            """
        )
        conn.commit()


def _insert_rows(path: Path, rows: list[tuple[int, str, int, str, str]]) -> None:
    with sqlite3.connect(str(path)) as conn:
        conn.executemany(
            """
            INSERT INTO financial_reports (
                CD_CVM, COMPANY_NAME, REPORT_YEAR, STATEMENT_TYPE, PERIOD_LABEL
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _make_service(tmp_path: Path) -> HeadlessRefreshService:
    settings = build_settings(project_root=tmp_path)
    return HeadlessRefreshService(settings=settings)


def test_build_company_year_plan_requires_annual_period_for_closed_years(tmp_path: Path):
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)
    _insert_rows(
        db_path,
        [
            (9512, "PETROBRAS", 2025, "BPA", "1Q25"),
            (9512, "PETROBRAS", 2025, "BPP", "2Q25"),
            (9512, "PETROBRAS", 2025, "DRE", "3Q25"),
            (9512, "PETROBRAS", 2025, "DFC", "3Q25"),
            (4170, "VALE", 2025, "BPA", "2025"),
            (4170, "VALE", 2025, "BPP", "2025"),
            (4170, "VALE", 2025, "DRE", "2025"),
            (4170, "VALE", 2025, "DFC", "2025"),
        ],
    )

    service = _make_service(tmp_path)
    request = RefreshRequest(
        companies=("9512", "4170"),
        start_year=2025,
        end_year=2025,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    planned_companies, year_overrides, stats = service.build_company_year_plan(request)

    assert planned_companies == ["9512"]
    assert year_overrides == {9512: [2025]}
    assert stats["planned_company_years"] == 1
    assert stats["skipped_complete_company_years"] == 1


def test_build_company_year_plan_treats_closed_year_as_complete_after_annual_insert(tmp_path: Path):
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)
    _insert_rows(
        db_path,
        [
            (9512, "PETROBRAS", 2025, "BPA", "1Q25"),
            (9512, "PETROBRAS", 2025, "BPP", "2Q25"),
            (9512, "PETROBRAS", 2025, "DRE", "3Q25"),
            (9512, "PETROBRAS", 2025, "DFC", "3Q25"),
            (9512, "PETROBRAS", 2025, "BPA", "2025"),
            (9512, "PETROBRAS", 2025, "BPP", "2025"),
            (9512, "PETROBRAS", 2025, "DRE", "2025"),
            (9512, "PETROBRAS", 2025, "DFC", "2025"),
        ],
    )

    service = _make_service(tmp_path)
    request = RefreshRequest(
        companies=("9512",),
        start_year=2025,
        end_year=2025,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    planned_companies, year_overrides, stats = service.build_company_year_plan(request)

    assert planned_companies == []
    assert year_overrides == {}
    assert stats["planned_company_years"] == 0
    assert stats["skipped_complete_company_years"] == 1


def test_build_company_year_plan_keeps_current_year(tmp_path: Path):
    """Current-year ITR (e.g. 1T26) must stay in the plan, not be dropped as future."""
    current_year = current_reporting_year_cap()
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)
    # Petrobras has full annual history through last closed year but no current year.
    _insert_rows(
        db_path,
        [
            (9512, "PETROBRAS", current_year - 1, "BPA", str(current_year - 1)),
            (9512, "PETROBRAS", current_year - 1, "BPP", str(current_year - 1)),
            (9512, "PETROBRAS", current_year - 1, "DRE", str(current_year - 1)),
            (9512, "PETROBRAS", current_year - 1, "DFC", str(current_year - 1)),
        ],
    )

    service = _make_service(tmp_path)
    request = RefreshRequest(
        companies=("9512",),
        start_year=current_year,
        end_year=current_year,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    planned_companies, year_overrides, stats = service.build_company_year_plan(request)

    assert planned_companies == ["9512"]
    assert year_overrides == {9512: [current_year]}
    assert stats["dropped_future_years"] == 0


def test_build_company_year_plan_drops_strictly_future_year(tmp_path: Path):
    """A year beyond the current calendar year is still rejected as future."""
    current_year = current_reporting_year_cap()
    future_year = current_year + 1
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)

    service = _make_service(tmp_path)
    request = RefreshRequest(
        companies=("9512",),
        start_year=future_year,
        end_year=future_year,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    planned_companies, year_overrides, stats = service.build_company_year_plan(request)

    assert planned_companies == []
    assert year_overrides == {}
    assert stats["dropped_future_years"] == 1


def test_build_company_year_plan_current_year_not_blocked_by_closed_history(tmp_path: Path):
    """Complete annual history through last closed year must not mark current year complete."""
    current_year = current_reporting_year_cap()
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)
    # Equatorial-style: full annual package for the closed year only.
    _insert_rows(
        db_path,
        [
            (20010, "EQUATORIAL", current_year - 1, "BPA", str(current_year - 1)),
            (20010, "EQUATORIAL", current_year - 1, "BPP", str(current_year - 1)),
            (20010, "EQUATORIAL", current_year - 1, "DRE", str(current_year - 1)),
            (20010, "EQUATORIAL", current_year - 1, "DFC", str(current_year - 1)),
        ],
    )

    service = _make_service(tmp_path)
    request = RefreshRequest(
        companies=("20010",),
        start_year=current_year - 1,
        end_year=current_year,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    planned_companies, year_overrides, stats = service.build_company_year_plan(request)

    # Closed year is complete and skipped; current year remains needed.
    assert planned_companies == ["20010"]
    assert year_overrides == {20010: [current_year]}


def test_max_refresh_year_helper_caps_at_current_year():
    assert current_reporting_year_cap(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 2026
    assert current_reporting_year_cap(datetime(2026, 12, 31, tzinfo=timezone.utc)) == 2026


def test_execute_includes_market_cap_step(tmp_path, monkeypatch):
    from src.platform.contracts import RefreshRequest, RefreshPolicy
    from types import SimpleNamespace
    import requests

    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)

    service = _make_service(tmp_path)
    # Enable the flag
    object.__setattr__(service.settings, "enable_experimental_yfinance", True)

    mock_response_json = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "PETR4.SA",
                    "marketCap": 500000000000.0,
                    "longName": "PETROBRAS PN"
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

    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kwargs: FakeResponse())

    # We also mock the catalog lookup inside _map_entries
    class FakeCatalog:
        def list_entries(self):
            return [
                SimpleNamespace(cd_cvm=9512, company_name="PETROBRAS", nome_comercial="PETRO", cnpj="", ticker_b3="PETR4", is_active=True)
            ]

    # Mock list_companies and company_catalog on read_service/catalog
    class FakeReadService:
        def __init__(self):
            self.company_catalog = FakeCatalog()
        def list_companies(self, **kwargs):
            return SimpleNamespace(items=[])

    service.read_service = FakeReadService()

    # Stub CVMScraper.run so it doesn't try to query actual CVM servers or read raw files
    from src.financials.scraper import CVMScraper
    monkeypatch.setattr(CVMScraper, "run", lambda *args, **kwargs: {})

    request = RefreshRequest(
        companies=("9512",),
        start_year=2025,
        end_year=2025,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    stages_seen = []
    def stage_callback(update):
        stages_seen.append(update.stage)

    result = service.execute(
        request,
        stage_callback=stage_callback,
        persist_refresh_status=False
    )

    assert "market_cap" in stages_seen
    assert result.market_cap_result is not None
    assert result.market_cap_result["status"] == "success"
    assert result.market_cap_result["source"] == "yahoo_finance"
    assert result.market_cap_result["provider_status"] == "unofficial_free"
    assert result.market_cap_result["row_count"] == 1
    assert service.settings.paths.company_universe_snapshot_path.exists()


def test_execute_market_cap_fallback_to_cache(tmp_path, monkeypatch):
    from src.platform.contracts import RefreshRequest, RefreshPolicy
    import requests

    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)

    service = _make_service(tmp_path)
    # Set to yahoo_finance provider but fetch will fail (raising exception)
    object.__setattr__(service.settings, "market_cap_provider", "yahoo_finance")

    # Create a valid local snapshot file beforehand
    snapshot_path = service.settings.paths.company_universe_snapshot_path
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    headers = "as_of_date,rank,cd_cvm,cnpj,company_name,ticker,market_cap_brl,source,method,source_url_or_id,downloaded_at,mapping_status,mapping_confidence,notes,provider_status"
    row1 = "2026-05-24,1,9512,,PETROBRAS,PETR4,500000000000.0,yahoo_finance,yfinance_bulk_quote,http://b3.com.br,2026-05-29T00:00:00Z,mapped,1.0,,unofficial_free"
    snapshot_path.write_text("\n".join([headers, row1]), encoding="utf-8")

    # Mock network fetch to raise exception
    def mock_session_get(self, url, **kwargs):
        raise RuntimeError("Network Error")
    monkeypatch.setattr(requests.Session, "get", mock_session_get)

    # Stub CVMScraper.run
    from src.financials.scraper import CVMScraper
    monkeypatch.setattr(CVMScraper, "run", lambda *args, **kwargs: {})

    request = RefreshRequest(
        companies=("9512",),
        start_year=2025,
        end_year=2025,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    result = service.execute(request, persist_refresh_status=False)
    assert result.market_cap_result is not None
    assert result.market_cap_result["status"] == "warning"
    assert "Could not refresh Yahoo Finance market-cap data. Using latest local snapshot from 2026-05-24." in result.market_cap_result["warnings"][0]


def test_execute_market_cap_blocked_when_no_snapshot(tmp_path, monkeypatch):
    from src.platform.contracts import RefreshRequest, RefreshPolicy
    import requests

    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)

    service = _make_service(tmp_path)
    object.__setattr__(service.settings, "market_cap_provider", "yahoo_finance")

    # Ensure no snapshot file exists
    snapshot_path = service.settings.paths.company_universe_snapshot_path
    if snapshot_path.exists():
        snapshot_path.unlink()

    # Mock network fetch to raise exception
    def mock_session_get(self, url, **kwargs):
        raise RuntimeError("Network Error")
    monkeypatch.setattr(requests.Session, "get", mock_session_get)

    # Stub CVMScraper.run
    from src.financials.scraper import CVMScraper
    monkeypatch.setattr(CVMScraper, "run", lambda *args, **kwargs: {})

    request = RefreshRequest(
        companies=("9512",),
        start_year=2025,
        end_year=2025,
        policy=RefreshPolicy(
            skip_complete_company_years=True,
            enable_fast_lane=False,
            force_refresh=False,
        ),
    )

    result = service.execute(request, persist_refresh_status=False)
    assert result.market_cap_result is not None
    assert result.market_cap_result["status"] == "blocked"
    assert "Could not build the market-cap list from Yahoo Finance and no local snapshot is available." in result.market_cap_result["warnings"][0]
