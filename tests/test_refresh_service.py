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


def test_execute_does_not_refresh_market_cap(tmp_path, monkeypatch):
    db_path = tmp_path / "data" / "db" / "cvm_financials.db"
    _create_financial_reports_table(db_path)
    service = _make_service(tmp_path)
    market_cap_calls = []

    from src.companies.market_cap import MarketCapService
    from src.financials.scraper import CVMScraper

    monkeypatch.setattr(
        MarketCapService,
        "fetch_from_yahoo_finance",
        lambda *_args, **_kwargs: market_cap_calls.append(True),
    )
    monkeypatch.setattr(CVMScraper, "run", lambda *_args, **_kwargs: {})

    stages_seen = []
    result = service.execute(
        RefreshRequest(
            companies=("9512",),
            start_year=2025,
            end_year=2025,
            policy=RefreshPolicy(
                skip_complete_company_years=True,
                enable_fast_lane=False,
                force_refresh=False,
            ),
        ),
        stage_callback=lambda update: stages_seen.append(update.stage),
        persist_refresh_status=False,
    )

    assert market_cap_calls == []
    assert "market_cap" not in stages_seen
    assert result.market_cap_result is None


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
