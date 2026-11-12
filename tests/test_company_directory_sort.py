"""Directory ordering is global, local-only and stable across page boundaries."""
import sqlite3
from pathlib import Path

import pytest

from desktop.bridge import CVMBridge
from test_company_market_cap_sort import (
    _company, _seed_db, _write_snapshot, _snap_row, _FakeCatalog, _FakeCatalogEntry,
)


@pytest.fixture
def directory(tmp_path):
    svc = _seed_db(tmp_path, [
        _company(30, "zeta", None),
        _company(20, "Alpha", "ZZZ3"),
        _company(10, "alpha", "AAA3"),
    ])
    with sqlite3.connect(svc.settings.paths.db_path) as conn:
        for code, years in [(10, [2023]), (20, [2023, 2024])]:
            for year in years:
                conn.execute('INSERT INTO financial_reports (CD_CVM, REPORT_YEAR, PERIOD_LABEL) VALUES (?, ?, ?)', (code, year, str(year)))
        conn.execute("UPDATE companies SET gics_sector=NULL, gics_industry_group=NULL, gics_industry=NULL, gics_sub_industry=NULL, gics_sector_slug=NULL, setor_cvm=NULL, setor_analitico=NULL WHERE cd_cvm=30")
    return svc


def ids(bridge, **params):
    result = bridge.get_companies(params)
    assert "error" not in result, result
    return [item["cd_cvm"] for item in result["items"]]


@pytest.mark.parametrize("column,asc,desc", [
    ("company", [10, 20, 30], [30, 10, 20]),
    ("ticker", [10, 20, 30], [20, 10, 30]),
    ("sector", [10, 20, 30], [10, 20, 30]),
    ("industryGroup", [10, 20, 30], [10, 20, 30]),
    ("cvm", [10, 20, 30], [30, 20, 10]),
    ("data", [30, 10, 20], [10, 20, 30]),
    ("years", [30, 10, 20], [20, 10, 30]),
    ("marketCap", [20, 10, 30], [10, 20, 30]),
])
@pytest.mark.parametrize("snapshot", [False, True])
def test_bridge_sorts_full_directory_before_pagination(directory, column, asc, desc, snapshot):
    if snapshot:
        _write_snapshot(Path(directory.settings.paths.company_universe_snapshot_path), [
            _snap_row("AAA3.SA", 200, 1, cd_cvm="10"),
            _snap_row("ZZZ3.SA", 100, 2, cd_cvm="20"),
        ])
    elif column == "marketCap":
        asc = desc = [10, 20, 30]  # All absent: stable CVM tie-breaker.
    bridge = CVMBridge()
    bridge._service = directory
    for direction, expected in [("asc", asc), ("desc", desc), ("asc", asc)]:
        actual = [ids(bridge, sort_by=column, sort_direction=direction, page=p, page_size=1)[0] for p in (1, 2, 3)]
        assert actual == expected


def test_catalog_search_and_gics_filter_precede_sort(directory):
    directory._company_catalog = _FakeCatalog([_FakeCatalogEntry(5, "alpha catalog")])
    bridge = CVMBridge()
    bridge._service = directory
    assert ids(bridge, search="alpha", sort_by="cvm", sort_direction="asc") == [5, 10, 20]
    assert ids(bridge, sector="energy", sort_by="cvm", sort_direction="desc", page_size=1) == [20]


@pytest.mark.parametrize("params", [
    {"sort_by": "company; DROP TABLE companies"},
    {"sort_by": "company", "sort_direction": "sideways"},
    {"sort_by": []},
])
def test_invalid_sort_is_an_explicit_bridge_error(directory, params):
    bridge = CVMBridge()
    bridge._service = directory
    result = bridge.get_companies(params)
    assert "error" in result
    assert result["items"] == []

@pytest.mark.parametrize("ready_mart", [False, True])
def test_sort_with_raw_and_ready_mart_and_no_network(tmp_path, monkeypatch, ready_mart):
    from test_financial_marts import _seed_financial_db
    from test_company_market_cap_sort import _EmptyCompanyCatalog
    from src.financials.marts import rebuild_financial_marts, DIRECTORY_MART_NAME
    from src.financials.query_layer import CVMQueryLayer
    from src.financials.read_service import CVMReadService
    from src.platform.settings import build_settings
    import requests

    engine = _seed_financial_db(tmp_path)
    if ready_mart:
        with engine.begin() as conn:
            rebuild_financial_marts(conn)
    svc = CVMReadService(settings=build_settings(project_root=tmp_path))
    svc.engine = engine
    svc.query_layer = CVMQueryLayer(engine=engine)
    svc._company_catalog = _EmptyCompanyCatalog()
    assert svc.query_layer._is_financial_mart_ready(DIRECTORY_MART_NAME) == ready_mart
    def deny(*args, **kwargs):
        raise AssertionError("Directory reads must not use the network")
    monkeypatch.setattr(requests.sessions.Session, "request", deny)
    bridge = CVMBridge()
    bridge._service = svc
    assert ids(bridge, sort_by="years", sort_direction="asc", page_size=1) == [99999]
    assert ids(bridge, sort_by="years", sort_direction="desc", page_size=1) == [9512]
    assert ids(bridge, sort_by="company", sort_direction="asc", page=2, page_size=1) == [9512]


def test_non_year_sort_only_reads_years_for_returned_page(directory, monkeypatch):
    observed = []
    original = directory.query_layer.get_company_years_map
    def observe(codes):
        observed.append(codes)
        return original(codes)
    monkeypatch.setattr(directory.query_layer, "get_company_years_map", observe)
    page = directory.list_companies(sort_by="company", sort_direction="asc", page_size=1)
    assert page.items[0].cd_cvm == 10
    assert observed == [[10]]
