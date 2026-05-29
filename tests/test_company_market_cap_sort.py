"""Tests: Companies list sorted by local market-cap snapshot.

Covers:
- Sorted by market_cap_brl DESC when snapshot exists and maps companies
- Unmapped companies appear after mapped companies
- Fallback to default sort when snapshot is absent
- Missing snapshot does not crash
- Malformed snapshot does not crash (missing required columns)
- Read path makes no network calls
- Mapping is cd_cvm-first then ticker_b3; no fuzzy name guessing
- market_cap_sort_meta present when sorted, absent otherwise
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.read_service import CVMReadService
from src.settings import build_settings


class _EmptyCompanyCatalog:
    """Stub catalog — makes CVMReadService use only the test DB, never the real CSV catalog."""
    def lookup_company(self, cd_cvm: int):
        return None

    def list_entries(self):
        return ()

    def search_companies(self, *, q: str, limit: int, exclude_codes=None):
        return ()


class _FakeCatalogEntry:
    """Minimal catalog entry for tests."""
    def __init__(self, cd_cvm: int, company_name: str, ticker_b3: str | None = None):
        self.cd_cvm = cd_cvm
        self.company_name = company_name
        self.ticker_b3 = ticker_b3
        self.setor_cvm = None
        self.nome_comercial = None
        self.is_active = True


class _FakeCatalog:
    """Catalog with specific test entries."""
    def __init__(self, entries: list):
        self._entries = entries

    def lookup_company(self, cd_cvm: int):
        return None

    def list_entries(self):
        return self._entries

    def search_companies(self, *, q: str, limit: int, exclude_codes=None):
        return ()


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_HEADER = (
    "as_of_date,rank,cd_cvm,cnpj,company_name,ticker,"
    "market_cap_brl,source,method,source_url_or_id,"
    "downloaded_at,mapping_status,mapping_confidence,notes,provider_status"
)


def _snap_row(
    ticker: str,
    market_cap_brl: float,
    rank: int,
    *,
    cd_cvm: str = "",
    as_of_date: str = "2026-05-29",
    mapping_status: str = "unmapped",
    mapping_confidence: float = 0.0,
) -> str:
    """Build a canonical snapshot CSV row. ticker should be the .SA form."""
    company_name = ticker.replace(".SA", "")
    return (
        f"{as_of_date},{rank},{cd_cvm},,{company_name},{ticker},"
        f"{market_cap_brl},yahoo_finance,yahoo_finance_bulk_quote,"
        f"https://example.com,{as_of_date}T00:00:00Z,"
        f"{mapping_status},{mapping_confidence},,unofficial_free"
    )


def _write_snapshot(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([_SNAPSHOT_HEADER] + rows), encoding="utf-8")


# ---------------------------------------------------------------------------
# DB / service helpers
# ---------------------------------------------------------------------------

def _seed_db(tmp_path: Path, companies: list[dict]) -> CVMReadService:
    """Build a minimal SQLite DB + CVMReadService for tests."""
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(settings.paths.db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE companies (
                cd_cvm INTEGER PRIMARY KEY,
                company_name TEXT NOT NULL,
                nome_comercial TEXT,
                cnpj TEXT,
                setor_cvm TEXT,
                setor_analitico TEXT,
                gics_sector TEXT,
                gics_sector_slug TEXT,
                gics_industry_group TEXT,
                gics_industry TEXT,
                gics_sub_industry TEXT,
                company_type TEXT,
                ticker_b3 TEXT,
                coverage_rank INTEGER,
                is_active INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE financial_reports (
                COMPANY_NAME TEXT,
                CD_CVM INTEGER,
                STATEMENT_TYPE TEXT,
                REPORT_YEAR INTEGER,
                PERIOD_LABEL TEXT,
                LINE_ID_BASE TEXT,
                CD_CONTA TEXT,
                DS_CONTA TEXT,
                STANDARD_NAME TEXT,
                QA_CONFLICT INTEGER,
                VL_CONTA REAL
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO companies (
                cd_cvm, company_name, nome_comercial, cnpj,
                setor_cvm, setor_analitico, gics_sector, gics_sector_slug,
                gics_industry_group, gics_industry, gics_sub_industry,
                company_type, ticker_b3, coverage_rank, is_active, updated_at
            ) VALUES (
                :cd_cvm, :company_name, :nome_comercial, :cnpj,
                :setor_cvm, :setor_analitico, :gics_sector, :gics_sector_slug,
                :gics_industry_group, :gics_industry, :gics_sub_industry,
                :company_type, :ticker_b3, :coverage_rank, :is_active, :updated_at
            )
            """,
            companies,
        )
        conn.commit()

    svc = CVMReadService(settings=settings)
    # Inject empty catalog so only the test DB rows are visible.
    svc._company_catalog = _EmptyCompanyCatalog()  # type: ignore[assignment]
    return svc


_COMPANY_DEFAULTS = dict(
    nome_comercial=None,
    cnpj=None,
    setor_cvm="Energia",
    setor_analitico="Energia",
    gics_sector="Energy",
    gics_sector_slug="energy",
    gics_industry_group="Energy",
    gics_industry="Oil, Gas",
    gics_sub_industry="Integrated Oil",
    company_type="comercial",
    coverage_rank=None,
    is_active=1,
    updated_at="2026-01-01",
)


def _company(cd_cvm: int, name: str, ticker: str | None = None, *, has_data: bool = False) -> dict:
    row = {**_COMPANY_DEFAULTS, "cd_cvm": cd_cvm, "company_name": name, "ticker_b3": ticker}
    if has_data:
        row["coverage_rank"] = cd_cvm  # non-null → triggers has_financial_data path
    return row


# ---------------------------------------------------------------------------
# Test: default sort when snapshot available
# ---------------------------------------------------------------------------

def test_sorted_by_market_cap_descending_when_snapshot_exists(tmp_path):
    """Companies with mapped market cap appear first, sorted market_cap_brl DESC."""
    svc = _seed_db(tmp_path, [
        _company(1001, "Alpha Corp", "ALPH3"),
        _company(1002, "Beta Corp", "BETA3"),
        _company(1003, "Gamma Corp", "GAMM3"),  # unmapped — no snapshot entry
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [
        _snap_row("BETA3.SA", 400_000_000_000.0, 1),
        _snap_row("ALPH3.SA", 200_000_000_000.0, 2),
    ])

    page = svc.list_companies(page=1, page_size=10)
    names = [item.company_name for item in page.items]

    assert names[0] == "Beta Corp", "Highest market cap first"
    assert names[1] == "Alpha Corp", "Second highest market cap second"
    assert names[2] == "Gamma Corp", "Unmapped company last"


def test_market_cap_brl_populated_for_mapped_companies(tmp_path):
    """market_cap_brl is set on enriched companies and None for unmapped ones."""
    svc = _seed_db(tmp_path, [
        _company(1001, "Alpha Corp", "ALPH3"),
        _company(1002, "Zeta Corp", "ZETA3"),
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("ALPH3.SA", 500_000_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    items_by_name = {item.company_name: item for item in page.items}

    alpha = items_by_name["Alpha Corp"]
    assert alpha.market_cap_brl == 500_000_000_000.0
    assert alpha.market_cap_rank == 1
    assert alpha.market_cap_source == "yahoo_finance"
    assert alpha.market_cap_provider_status == "unofficial_free"
    assert alpha.market_cap_as_of_date == "2026-05-29"

    zeta = items_by_name["Zeta Corp"]
    assert zeta.market_cap_brl is None
    assert zeta.market_cap_rank is None


def test_market_cap_sort_meta_present_when_sorted(tmp_path):
    """market_cap_sort_meta is included in the page when market cap sort is active."""
    svc = _seed_db(tmp_path, [_company(1001, "Alpha Corp", "ALPH3")])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("ALPH3.SA", 100_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    assert page.market_cap_sort_meta is not None
    meta = page.market_cap_sort_meta
    assert meta.as_of_date == "2026-05-29"
    assert meta.source == "yahoo_finance"
    assert meta.provider_status == "unofficial_free"
    assert meta.mapped_count == 1
    assert meta.total_in_snapshot == 1


# ---------------------------------------------------------------------------
# Test: fallback when snapshot absent
# ---------------------------------------------------------------------------

def test_no_snapshot_returns_default_sort_without_crash(tmp_path):
    """list_companies works normally when no snapshot file exists."""
    svc = _seed_db(tmp_path, [
        _company(1001, "Zeta Corp", "ZETA3"),
        _company(1002, "Alpha Corp", "ALPH3"),
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    assert not snapshot_path.exists()

    page = svc.list_companies(page=1, page_size=10)
    assert len(page.items) == 2
    assert page.market_cap_sort_meta is None


# ---------------------------------------------------------------------------
# Test: malformed snapshot — graceful degradation
# ---------------------------------------------------------------------------

def test_malformed_snapshot_falls_back_gracefully(tmp_path):
    """A snapshot missing required columns does not crash list_companies."""
    svc = _seed_db(tmp_path, [_company(1001, "Alpha Corp", "ALPH3")])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    # Missing required columns (e.g. no market_cap_brl)
    snapshot_path.write_text("ticker,market_cap_brl\nALPH3.SA,100000\n", encoding="utf-8")

    page = svc.list_companies(page=1, page_size=10)
    assert len(page.items) == 1
    assert page.market_cap_sort_meta is None  # malformed → fell back to default sort


# ---------------------------------------------------------------------------
# Test: no network calls from read path
# ---------------------------------------------------------------------------

def test_list_companies_makes_no_network_calls(tmp_path):
    """The market-cap read path is purely local — no network requests."""
    svc = _seed_db(tmp_path, [_company(1001, "Alpha Corp", "ALPH3")])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("ALPH3.SA", 100_000_000.0, 1)])

    with patch("requests.Session") as mock_session, patch("requests.get") as mock_get:
        svc.list_companies(page=1, page_size=10)
        mock_session.assert_not_called()
        mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Test: exact identifier matching only
# ---------------------------------------------------------------------------

def test_mapping_uses_ticker_exact_match_only(tmp_path):
    """Ticker matching strips .SA but is otherwise exact — no fuzzy name guessing."""
    svc = _seed_db(tmp_path, [
        _company(1001, "Alpha Corp", "ALPH3"),
        _company(1002, "Alpha Corp Variant", "ALPH3V"),  # different ticker, similar name
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    # Only ALPH3.SA is in snapshot — ALPH3V must NOT be enriched via name similarity
    _write_snapshot(snapshot_path, [_snap_row("ALPH3.SA", 500_000_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    items_by_ticker = {item.ticker_b3: item for item in page.items}

    assert items_by_ticker["ALPH3"].market_cap_brl == 500_000_000_000.0
    assert items_by_ticker["ALPH3V"].market_cap_brl is None


def test_cd_cvm_takes_priority_over_ticker(tmp_path):
    """cd_cvm exact match is used before ticker when both are present in snapshot."""
    svc = _seed_db(tmp_path, [_company(9512, "Petrobras", "PETR4")])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    # Entry has cd_cvm=9512 set; should be found by cd_cvm lookup first
    _write_snapshot(snapshot_path, [
        _snap_row("PETR4.SA", 500_000_000_000.0, 1, cd_cvm="9512", mapping_status="mapped", mapping_confidence=1.0),
    ])

    page = svc.list_companies(page=1, page_size=10)
    assert len(page.items) == 1
    assert page.items[0].market_cap_brl == 500_000_000_000.0


# ---------------------------------------------------------------------------
# Test: unmapped companies always appear after mapped ones
# ---------------------------------------------------------------------------

def test_unmapped_after_mapped_regardless_of_name_order(tmp_path):
    """Unmapped companies sort after all mapped ones even if name is alphabetically first."""
    svc = _seed_db(tmp_path, [
        _company(1001, "AAA Corp unmapped", "AAAC3"),
        _company(1002, "ZZZ Corp mapped", "ZZZC3"),
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("ZZZC3.SA", 100_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    names = [item.company_name for item in page.items]
    assert names[0] == "ZZZ Corp mapped", "Mapped company first despite Z name"
    assert names[1] == "AAA Corp unmapped", "Unmapped last despite A name"


# ---------------------------------------------------------------------------
# Test: pagination preserves market-cap order
# ---------------------------------------------------------------------------

def test_pagination_preserves_market_cap_order(tmp_path):
    """Market cap order is preserved across pages."""
    tickers = ["CORP_A", "CORP_B", "CORP_C", "CORP_D", "CORP_E", "CORP_F"]
    companies = [_company(1000 + i, f"Corp {t}", t) for i, t in enumerate(tickers)]
    svc = _seed_db(tmp_path, companies)
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    # Corp A gets highest cap (600B), Corp F gets lowest (100B)
    rows = [
        _snap_row(f"{t}.SA", (len(tickers) - i) * 100_000_000_000.0, i + 1)
        for i, t in enumerate(tickers)
    ]
    _write_snapshot(snapshot_path, rows)

    page1 = svc.list_companies(page=1, page_size=3)
    page2 = svc.list_companies(page=2, page_size=3)

    caps_p1 = [item.market_cap_brl for item in page1.items]
    caps_p2 = [item.market_cap_brl for item in page2.items]

    assert all(c is not None for c in caps_p1), "All page-1 companies should be mapped"
    assert all(c is not None for c in caps_p2), "All page-2 companies should be mapped"
    assert caps_p1 == sorted(caps_p1, reverse=True), "Page 1 sorted desc"
    assert min(caps_p1) > max(caps_p2), "Page 1 caps all higher than page 2"


# ---------------------------------------------------------------------------
# Test: unmapped fallback order preserves has_financial_data tier
# ---------------------------------------------------------------------------

def test_unmapped_companies_with_data_appear_before_catalog_stubs(tmp_path):
    """Unmapped companies that have financial data appear before catalog stubs (no data)."""
    svc = _seed_db(tmp_path, [
        _company(1001, "Stub Corp no data", "STUB3"),          # no data, no market cap
        _company(1002, "Data Corp no market cap", "DATA3", has_data=False),  # no data, no cap
        _company(1003, "Mapped Corp", "MAPC3"),                 # has market cap
    ])
    # Seed financial_reports for Data Corp to give it has_financial_data=True
    import sqlite3
    with sqlite3.connect(str(svc.settings.paths.db_path)) as conn:
        conn.execute(
            "INSERT INTO financial_reports (COMPANY_NAME, CD_CVM, STATEMENT_TYPE, REPORT_YEAR, "
            "PERIOD_LABEL, LINE_ID_BASE, CD_CONTA, DS_CONTA, STANDARD_NAME, QA_CONFLICT, VL_CONTA) "
            "VALUES ('Data Corp', 1002, 'DRE', 2024, '2024', 'd1', '3.01', 'Receita', 'Receita', 0, 100.0)"
        )
        conn.commit()
    svc.invalidate_read_caches()

    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("MAPC3.SA", 200_000_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    names = [item.company_name for item in page.items]
    assert names[0] == "Mapped Corp", "Market-cap mapped first"
    assert names[1] == "Data Corp no market cap", "Has-data company before stub"
    assert names[2] == "Stub Corp no data", "Pure stub last"


def test_catalog_companies_not_in_db_appear_as_stubs(tmp_path):
    """Catalog companies not in the local DB are shown as stubs; market cap enriched when in snapshot."""
    svc = _seed_db(tmp_path, [_company(1001, "Alpha Corp", "ALPH3")])
    # Provide catalog with BOTH companies — Beta Corp is catalog-only (not in DB)
    svc._company_catalog = _FakeCatalog([  # type: ignore[assignment]
        _FakeCatalogEntry(1001, "Alpha Corp", "ALPH3"),
        _FakeCatalogEntry(1002, "Beta Corp", "BETA3"),
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [
        _snap_row("ALPH3.SA", 300_000_000_000.0, 1),
        _snap_row("BETA3.SA", 100_000_000_000.0, 2),  # catalog-only, not in DB
    ])

    page = svc.list_companies(page=1, page_size=10)
    names = [item.company_name for item in page.items]
    tickers = [item.ticker_b3 for item in page.items]

    assert len(page.items) == 2, "Catalog stub included in results"
    assert names[0] == "Alpha Corp"   # higher market cap
    assert names[1] == "Beta Corp"
    assert "BETA3" in tickers


def test_snapshot_ticker_fills_null_db_ticker(tmp_path):
    """When DB ticker_b3 is null, snapshot ticker fills in when matched by cd_cvm."""
    # Company 1001 in DB has no ticker; snapshot matches it by cd_cvm=1001
    svc = _seed_db(tmp_path, [_company(1001, "Alpha Corp", None)])
    # Catalog also has no ticker for this company
    svc._company_catalog = _FakeCatalog([  # type: ignore[assignment]
        _FakeCatalogEntry(1001, "Alpha Corp", None),
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    # Entry has cd_cvm=1001 so it matches the DB company directly
    _write_snapshot(snapshot_path, [
        _snap_row("ALPH3.SA", 100_000_000.0, 1, cd_cvm="1001", mapping_status="mapped"),
    ])

    page = svc.list_companies(page=1, page_size=10)
    tickers = [item.ticker_b3 for item in page.items]
    assert any(t == "ALPH3" for t in tickers), "Snapshot ticker fills null DB ticker"


def test_ticker_sa_suffix_normalised_for_lookup(tmp_path):
    """DB tickers with .SA suffix (e.g. PETR4.SA) match snapshot keys stripped of .SA."""
    # Seed DB with .SA-suffixed ticker (as some installs store it)
    svc = _seed_db(tmp_path, [
        _company(9512, "Petrobras", "PETR4.SA"),  # .SA in DB
    ])
    snapshot_path = Path(svc.settings.paths.company_universe_snapshot_path)
    _write_snapshot(snapshot_path, [_snap_row("PETR4.SA", 500_000_000_000.0, 1)])

    page = svc.list_companies(page=1, page_size=10)
    assert page.items[0].market_cap_brl == 500_000_000_000.0, \
        "Ticker .SA suffix must be normalised for lookup"
