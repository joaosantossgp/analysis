# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from src.platform.settings import build_settings
from src.companies.coverage import CoverageUniverseService, ensure_coverage_tables_for_connection


def _recent_liquidity_dates() -> list[str]:
    # SQLite date('now') is UTC-based; keep fixtures safely inside the rolling 30-day window.
    today_utc = datetime.now(timezone.utc).date()
    return [(today_utc - timedelta(days=offset)).isoformat() for offset in range(6, 1, -1)]


def _market_history_rows(*entries: tuple[int, str, float, float]) -> list[dict[str, object]]:
    dates = _recent_liquidity_dates()
    return [
        {
            "cd_cvm": cd_cvm,
            "ticker": ticker,
            "date": date_value,
            "volume": volume,
            "close": close,
            "source": "yahoo",
        }
        for cd_cvm, ticker, volume, close in entries
        for date_value in dates
    ]


@pytest.fixture
def test_engine(tmp_path):
    # Setup a temporary SQLite DB for testing
    db_path = tmp_path / "test_cvm.db"
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Initialize schema
    with engine.begin() as conn:
        ensure_coverage_tables_for_connection(conn)
        # Create minimal mock companies table as it is referenced
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS companies (
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
                    company_type TEXT NOT NULL DEFAULT 'comercial',
                    ticker_b3 TEXT,
                    coverage_rank INTEGER,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
                """
            )
        )
        
        # Create mock company_universe table for market cap joining
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS company_universe (
                    cd_cvm INTEGER NOT NULL,
                    ticker TEXT,
                    company_name TEXT NOT NULL,
                    market_cap REAL,
                    market_cap_rank INTEGER,
                    source TEXT NOT NULL,
                    source_date TEXT,
                    selected_preset TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (selected_preset, cd_cvm)
                )
                """
            )
        )

        # Create mock market_history table
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS market_history (
                    cd_cvm INTEGER NOT NULL,
                    ticker TEXT,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    adjusted_close REAL,
                    volume REAL,
                    dividend REAL,
                    split_ratio REAL,
                    source TEXT,
                    PRIMARY KEY (cd_cvm, ticker, date)
                )
                """
            )
        )

        # Seed mock companies
        conn.execute(
            text(
                """
                INSERT INTO companies (cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at)
                VALUES 
                (9512, 'PETROLEO BRASILEIRO S.A.', 'Energy', 'energy', 'PETR4', '2026-06-16T12:00:00Z'),
                (4170, 'VALE S.A.', 'Materials', 'materials', 'VALE3', '2026-06-16T12:00:00Z')
                """
            )
        )
        
        # Seed mock market cap
        conn.execute(
            text(
                """
                INSERT INTO company_universe (cd_cvm, ticker, company_name, market_cap, market_cap_rank, source, selected_preset, created_at, updated_at)
                VALUES 
                (9512, 'PETR4', 'PETROLEO BRASILEIRO S.A.', 500000000000.0, 1, 'test', 'all', '2026-06-16', '2026-06-16'),
                (4170, 'VALE3', 'VALE S.A.', 400000000000.0, 2, 'test', 'all', '2026-06-16', '2026-06-16')
                """
            )
        )

        # Seed mock market history volume (5 distinct dates per company, with raw close price)
        conn.execute(
            text(
                """
                INSERT INTO market_history (cd_cvm, ticker, date, volume, close, adjusted_close, source)
                VALUES (:cd_cvm, :ticker, :date, :volume, :close, :close, :source)
                """
            ),
            _market_history_rows(
                (9512, "PETR4", 50000000.0, 38.5),
                (4170, "VALE3", 15000000.0, 62.1),
            ),
        )


    return engine


def test_coverage_universe_service_lifecycle(test_engine):
    service = CoverageUniverseService(test_engine)

    # 1. List is initially empty
    universes = service.list_universes()
    assert len(universes) == 0

    # 2. Create a universe
    u_id = service.create_universe(
        name="Equity Coverage Watch 2026",
        purpose="Energy & Materials universe",
        analysis_type="Equity",
        benchmark="IBOV"
    )
    assert u_id is not None
    
    # 3. Retrieve universe details
    u = service.get_universe(u_id)
    assert u["name"] == "Equity Coverage Watch 2026"
    assert u["purpose"] == "Energy & Materials universe"
    assert u["analysis_type"] == "Equity"
    assert u["benchmark"] == "IBOV"
    assert u["status"] == "draft"
    assert "weights" in u["assumptions"]

    # 4. List universes
    universes = service.list_universes()
    assert len(universes) == 1
    assert universes[0]["company_count"] == 0

    # 5. Add companies to universe
    service.add_company_to_universe(
        universe_id=u_id,
        cd_cvm=9512,
        tier="must_cover",
        rationale="State-backed oil company with high sector relevance",
        owner="Analyst A"
    )
    
    service.add_company_to_universe(
        universe_id=u_id,
        cd_cvm=4170,
        tier="core",
        rationale="Major mining company",
        owner="Analyst B"
    )

    universes = service.list_universes()
    assert universes[0]["company_count"] == 2

    # 6. Check priority scores
    scores = service.calculate_priority_scores(u_id)
    assert len(scores) == 2
    
    petr = next(x for x in scores if x["cd_cvm"] == 9512)
    assert petr["tier"] == "must_cover"
    assert petr["owner_analyst"] == "Analyst A"
    # Verify calculated log scores
    assert petr["cap_score"] > 0
    assert petr["liquidity_observations"] == 5
    assert petr["vol_score"] > 0
    assert petr["final_score"] > 0

    # 7. Apply manual score override
    service.save_manual_score_override(
        universe_id=u_id,
        cd_cvm=9512,
        override=10.0,
        rationale="Increase score due to pending dividend surprise potential"
    )
    
    scores2 = service.calculate_priority_scores(u_id)
    petr2 = next(x for x in scores2 if x["cd_cvm"] == 9512)
    assert petr2["final_score"] == round(min(petr["calculated_score"] + 10.0, 100.0), 1)

    # 8. Check checklist deliverables
    checklist = service.get_coverage_checklists(u_id, 9512)
    assert len(checklist) > 0
    model_item = next(item for item in checklist if item["item_key"] == "model_updated")
    assert model_item["is_completed"] == 0

    # 9. Update checklist item
    service.update_checklist_item(
        universe_id=u_id,
        cd_cvm=9512,
        item_key="model_updated",
        is_completed=True,
        comments="Income statement & balance sheet model updated for 1Q26",
        rationale="Update model checklist step done"
    )
    
    checklist2 = service.get_coverage_checklists(u_id, 9512)
    model_item2 = next(item for item in checklist2 if item["item_key"] == "model_updated")
    assert model_item2["is_completed"] == 1
    assert model_item2["comments"] == "Income statement & balance sheet model updated for 1Q26"

    # 10. Verify work queue
    work_queue = service.get_work_queue(u_id)
    # PETR4 has model_updated complete, other checklist items remain incomplete
    assert len(work_queue) > 0
    # Make sure petr4 model_updated task is NOT in the queue
    assert not any(t["cd_cvm"] == 9512 and t["task_type"] == "checklist_incomplete" and "model_updated" in (t.get("item_key") or "") for t in work_queue)

    # 11. Verify capacity calculations
    cap_data = service.get_capacity_data(u_id)
    assert cap_data["available_hours"] == 1600.0
    assert cap_data["required_hours"] > 0
    assert "must_cover" in cap_data["tier_counts"]

    # 12. Save custom scenario
    custom_weights = {
        "must_cover": 150.0,
        "core": 100.0,
        "watchlist": 40.0,
        "opportunistic": 50.0,
        "excluded": 10.0,
        "inappropriate": 10.0,
    }
    service.save_capacity_scenario(
        universe_id=u_id,
        available_hours=2000.0,
        tier_hours=custom_weights
    )
    
    cap_data2 = service.get_capacity_data(u_id)
    assert cap_data2["available_hours"] == 2000.0
    assert cap_data2["tier_hours_assumptions"]["must_cover"] == 150.0

    # 13. Verify decision history log
    history = service.get_decision_history(u_id, 9512)
    assert len(history) > 0
    assert any(h["event_type"] == "score_override" for h in history)

    # 14. Remove company from universe
    service.remove_company_from_universe(u_id, 4170, rationale="Excluding Vale due to thematic shift")
    scores3 = service.calculate_priority_scores(u_id)
    assert len(scores3) == 1
    assert scores3[0]["cd_cvm"] == 9512

    # 15. Test duplication (with default copy_companies=True)
    dup_id_default = service.duplicate_universe(u_id, "Cloned Universe Default")
    assert dup_id_default is not None
    dup_default = service.get_universe(dup_id_default)
    assert dup_default["name"] == "Cloned Universe Default"
    # Company list should be copied
    dup_scores = service.calculate_priority_scores(dup_id_default)
    assert len(dup_scores) == 1
    assert dup_scores[0]["cd_cvm"] == 9512
    # Checklists should not be copied by default (they are initialized as not completed)
    dup_check = service.get_coverage_checklists(dup_id_default, 9512)
    assert len(dup_check) > 0
    assert all(chk["is_completed"] == 0 for chk in dup_check)
    service.delete_universe(dup_id_default)

    # 15b. Test duplication with checklists copy
    dup_id_check = service.duplicate_universe(u_id, "Cloned Universe with Checklists", copy_companies=True, copy_checklists=True)
    dup_check2 = service.get_coverage_checklists(dup_id_check, 9512)
    assert any(chk["item_key"] == "model_updated" and chk["is_completed"] == 1 for chk in dup_check2)
    service.delete_universe(dup_id_check)

    # 15c. Test duplication (without copy_companies)
    dup_id_empty = service.duplicate_universe(u_id, "Cloned Universe Empty", copy_companies=False)
    assert len(service.calculate_priority_scores(dup_id_empty)) == 0
    service.delete_universe(dup_id_empty)

    # 15d. Test bulk update companies (add & remove)
    bulk_id = service.create_universe("Bulk Universe", "Testing bulk updates", "Equity", "IBOV")
    # Bulk add PETR4 and VALE3 as core
    service.bulk_update_companies_in_universe(bulk_id, [9512, 4170], "core", "Bulk add energy and materials")
    bulk_scores = service.calculate_priority_scores(bulk_id)
    assert len(bulk_scores) == 2
    assert any(x["cd_cvm"] == 9512 and x["tier"] == "core" for x in bulk_scores)
    assert any(x["cd_cvm"] == 4170 and x["tier"] == "core" for x in bulk_scores)
    
    # Bulk change PETR4 to must_cover and remove VALE3 (tier='none')
    service.bulk_update_companies_in_universe(bulk_id, [9512], "must_cover", "Upgrade Petro")
    service.bulk_update_companies_in_universe(bulk_id, [4170], "none", "Remove Vale")
    bulk_scores2 = service.calculate_priority_scores(bulk_id)
    assert len(bulk_scores2) == 1
    assert bulk_scores2[0]["cd_cvm"] == 9512
    assert bulk_scores2[0]["tier"] == "must_cover"
    service.delete_universe(bulk_id)

    # 16. Delete universe
    service.delete_universe(u_id)
    assert service.get_universe(u_id) is None


def test_coverage_universe_edge_cases(test_engine):
    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe(
        name="Edge Cases Universe",
        purpose="Testing edge cases",
        analysis_type="Equity",
        benchmark="IBOV"
    )
    
    # Let's seed a company with Portuguese GICS to verify it gets blocked/rejected
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO companies (cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at)
                VALUES (1234, 'COMPANHIA PORTUGUESE GICS', 'Petróleo, Gás e Biocombustíveis', 'petroleo-gas-e-biocombustiveis', 'PORT4', '2026-06-16T12:00:00Z')
                """
            )
        )
        # Also seed market cap and 5 history records, but GICS sector is Portuguese
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO company_universe (cd_cvm, ticker, company_name, market_cap, market_cap_rank, source, selected_preset, created_at, updated_at)
                VALUES (1234, 'PORT4', 'COMPANHIA PORTUGUESE GICS', 100000000.0, 10, 'yahoo', 'all', '2026-06-16', '2026-06-16')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO market_history (cd_cvm, ticker, date, volume, close, adjusted_close, source)
                VALUES (:cd_cvm, :ticker, :date, :volume, :close, :close, :source)
                """
            ),
            _market_history_rows((1234, "PORT4", 100000.0, 10.0)),
        )

    service.add_company_to_universe(u_id, 1234, "watchlist", "Portuguese GICS company")
    scores = service.calculate_priority_scores(u_id)
    port_comp = next(x for x in scores if x["cd_cvm"] == 1234)
    # GICS sector should be resolved to Unknown/missing because it's Portuguese
    assert port_comp["gics_sector"] == "Unknown"
    assert "sector_complexity" in port_comp["missing_factors"]
    assert port_comp["sector_score"] is None

    # Let's seed a company with market cap conflict (equal priority, equal recency, different market cap values)
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO companies (cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at)
                VALUES (5678, 'CONFLICT MCAP S.A.', 'Energy', 'energy', 'CONF3', '2026-06-16T12:00:00Z')
                """
            )
        )
        # Multiple presets with equal source priority (e.g. cvm/b3) and dates, but different market caps
        conn.execute(
            text(
                """
                INSERT INTO company_universe (cd_cvm, ticker, company_name, market_cap, market_cap_rank, source, selected_preset, created_at, updated_at)
                VALUES 
                (5678, 'CONF3', 'CONFLICT MCAP S.A.', 100000000.0, 11, 'b3', 'all', '2026-06-16', '2026-06-16'),
                (5678, 'CONF3', 'CONFLICT MCAP S.A.', 200000000.0, 11, 'b3', 'top_500', '2026-06-16', '2026-06-16')
                """
            )
        )
        # 5 history records
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO market_history (cd_cvm, ticker, date, volume, close, adjusted_close, source)
                VALUES (:cd_cvm, :ticker, :date, :volume, :close, :close, :source)
                """
            ),
            _market_history_rows((5678, "CONF3", 100000.0, 10.0)),
        )

    service.add_company_to_universe(u_id, 5678, "watchlist", "Market cap conflict company")
    scores = service.calculate_priority_scores(u_id)
    conf_comp = next(x for x in scores if x["cd_cvm"] == 5678)
    assert conf_comp["market_cap"] is None
    assert conf_comp["market_cap_selection_origin"] == "database_conflict"
    assert "market_cap" in conf_comp["missing_factors"]

    # Test that overrides do NOT write score_snapshot to decision history
    service.save_manual_score_override(u_id, 1234, 15.0, "Manual override")
    with test_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM coverage_decision_history WHERE event_type = 'score_snapshot'")
        ).scalar()
        assert count == 0

    # Test score block behavior
    # Let's seed a company with only sector complexity available
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO companies (cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at)
                VALUES (9999, 'BLOCKED S.A.', 'Energy', 'energy', 'BLOC3', '2026-06-16T12:00:00Z')
                """
            )
        )
        # No market cap and no market history volume seeded!
    service.add_company_to_universe(u_id, 9999, "watchlist", "Blocked company")
    scores = service.calculate_priority_scores(u_id)
    bloc_comp = next(x for x in scores if x["cd_cvm"] == 9999)
    assert bloc_comp["score_status"] == "blocked"
    assert bloc_comp["calculated_score"] is None
    assert bloc_comp["final_score"] is None

    # Verify that applying manual override to a blocked score does NOT unblock it
    service.save_manual_score_override(u_id, 9999, 10.0, "Override blocked company")
    scores = service.calculate_priority_scores(u_id)
    bloc_comp = next(x for x in scores if x["cd_cvm"] == 9999)
    assert bloc_comp["score_status"] == "blocked"
    assert bloc_comp["final_score"] is None

    service.delete_universe(u_id)


def test_coverage_universe_hotfixes(test_engine):
    from src.companies.coverage import normalize_market_cap_source, _resolve_canonical_market_caps, CoverageUniverseService
    from unittest.mock import Mock

    # 1. Test normalize_market_cap_source
    assert normalize_market_cap_source("yahoo") == "yahoo_finance"
    assert normalize_market_cap_source("yahoo_finance") == "yahoo_finance"
    assert normalize_market_cap_source("imported_market_cap") == "imported_user_data"
    assert normalize_market_cap_source("imported_user_data") == "imported_user_data"
    assert normalize_market_cap_source("b3") == "official_b3"
    assert normalize_market_cap_source("cvm") == "official_cvm"
    assert normalize_market_cap_source(None) == "unknown"
    assert normalize_market_cap_source("random") == "unknown"

    # 2. Test _resolve_canonical_market_caps snapshot conflict
    entry1 = Mock(cd_cvm=1234, market_cap_brl=100000.0, source="b3", as_of_date="2026-06-16", downloaded_at="2026-06-16T12:00:00Z", rank=1, company_name="Test")
    entry2 = Mock(cd_cvm=1234, market_cap_brl=200000.0, source="b3", as_of_date="2026-06-16", downloaded_at="2026-06-16T12:00:00Z", rank=1, company_name="Test")
    res = _resolve_canonical_market_caps([entry1, entry2])
    assert 1234 in res
    best, conflicts = res[1234]
    assert conflicts is not None
    assert len(conflicts) == 2

    # 3. Test DB Fallback Conflict & Zero-Weight Factors
    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe(
        name="Hotfix Test Universe",
        purpose="Testing hotfixes",
        analysis_type="Equity",
        benchmark="IBOV"
    )

    # Seed companies
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO companies (cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at)
                VALUES 
                (7777, 'CONFLICT DB S.A.', 'Energy', 'energy', 'CONF7', '2026-06-16T12:00:00Z'),
                (8888, 'ZERO WEIGHT S.A.', 'Energy', 'energy', 'ZERO8', '2026-06-16T12:00:00Z')
                """
            )
        )
        # Seed conflict DB entries
        conn.execute(
            text(
                """
                INSERT INTO company_universe (cd_cvm, ticker, company_name, market_cap, market_cap_rank, source, selected_preset, created_at, updated_at)
                VALUES 
                (7777, 'CONF7', 'CONFLICT DB S.A.', 100000.0, 1, 'b3', 'all', '2026-06-16', '2026-06-16'),
                (7777, 'CONF7', 'CONFLICT DB S.A.', 200000.0, 1, 'b3', 'top_500', '2026-06-16', '2026-06-16')
                """
            )
        )
        # Seed 5 market history entries for both companies
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO market_history (cd_cvm, ticker, date, volume, close, adjusted_close, source)
                VALUES (:cd_cvm, :ticker, :date, :volume, :close, :close, :source)
                """
            ),
            _market_history_rows(
                (7777, "CONF7", 1000.0, 10.0),
                (8888, "ZERO8", 1000.0, 10.0),
            ),
        )

    service.add_company_to_universe(u_id, 7777, "core", "Conflict test")
    service.add_company_to_universe(u_id, 8888, "watchlist", "Zero weight test")

    # Let's verify DB Fallback conflict
    scores = service.calculate_priority_scores(u_id)
    conf_comp = next(x for x in scores if x["cd_cvm"] == 7777)
    assert conf_comp["market_cap"] is None
    assert conf_comp["market_cap_selection_origin"] == "database_conflict"
    assert "market_cap" in conf_comp["missing_factors"]

    # Now let's test zero-weight factor logic by modifying the universe assumptions weights
    assumptions = service.get_universe(u_id)["assumptions"]
    # Disable market cap and holding pct weights; keep volume and sector weights active.
    assumptions["weights"] = {
        "market_cap_weight": 0.0,
        "volume_weight": 0.5,
        "holding_weight": 0.0,
        "sector_weight": 0.5
    }
    service.update_universe(
        universe_id=u_id,
        name="Hotfix Test Universe",
        purpose="Testing hotfixes",
        benchmark="IBOV",
        status="draft",
        assumptions=assumptions
    )

    scores_zero = service.calculate_priority_scores(u_id)
    zero_comp = next(x for x in scores_zero if x["cd_cvm"] == 8888)

    # With volume and sector available, zero-weight missing factors should NOT block scoring.
    assert zero_comp["liquidity_observations"] == 5
    assert zero_comp["score_status"] == "complete"
    assert zero_comp["final_score"] is not None
    # Zero-weight factors should not be listed as missing
    assert "market_cap" not in zero_comp["missing_factors"]
    assert "holding_pct" not in zero_comp["missing_factors"]
    assert "sector_complexity" not in zero_comp["missing_factors"]
    # Factor details for zero-weight factors should have missing = False
    assert zero_comp["factor_details"]["market_cap"]["missing"] is False
    assert zero_comp["factor_details"]["holding_pct"]["missing"] is False
    assert zero_comp["factor_details"]["sector_complexity"]["missing"] is False

    # 4. Test delete transactional integrity (rollback)
    from sqlalchemy.engine.base import Connection
    original_execute = Connection.execute

    def mock_execute(self_conn, statement, *args, **kwargs):
        if "DELETE FROM coverage_universes" in str(statement):
            raise ValueError("Simulated DB failure")
        return original_execute(self_conn, statement, *args, **kwargs)

    # Verify rows exist before delete attempt
    with test_engine.connect() as conn:
        u_count = conn.execute(text("SELECT COUNT(*) FROM coverage_universes WHERE id = :u_id"), {"u_id": u_id}).scalar()
        comp_count = conn.execute(text("SELECT COUNT(*) FROM universe_companies WHERE universe_id = :u_id"), {"u_id": u_id}).scalar()
        assert u_count == 1
        assert comp_count == 2

    # Patch execution to raise error
    import unittest.mock as mock
    with mock.patch.object(Connection, "execute", new=mock_execute):
        with pytest.raises(ValueError, match="Simulated DB failure"):
            service.delete_universe(u_id)

    # Verify rows STILL exist (rolled back!)
    with test_engine.connect() as conn:
        u_count = conn.execute(text("SELECT COUNT(*) FROM coverage_universes WHERE id = :u_id"), {"u_id": u_id}).scalar()
        comp_count = conn.execute(text("SELECT COUNT(*) FROM universe_companies WHERE universe_id = :u_id"), {"u_id": u_id}).scalar()
        assert u_count == 1
        assert comp_count == 2

    # Now do a successful delete
    service.delete_universe(u_id)
    with test_engine.connect() as conn:
        u_count = conn.execute(text("SELECT COUNT(*) FROM coverage_universes WHERE id = :u_id"), {"u_id": u_id}).scalar()
        comp_count = conn.execute(text("SELECT COUNT(*) FROM universe_companies WHERE universe_id = :u_id"), {"u_id": u_id}).scalar()
        assert u_count == 0
        assert comp_count == 0


def test_coverage_keeps_cvm_code_out_of_ticker_field(test_engine, monkeypatch):
    class _Identity:
        company_name = "NO TICKER S.A."
        ticker_b3 = None

    class _Resolver:
        def resolve(self, cd_cvm):
            return _Identity()

    import src.companies.identity as identity_module

    monkeypatch.setattr(identity_module, "CompanyIdentityResolver", _Resolver)

    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe(
        name="No Ticker Universe",
        purpose="Ticker fallback regression",
        analysis_type="Equity",
        benchmark="IBOV",
    )
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO companies (
                    cd_cvm, company_name, gics_sector, gics_sector_slug, ticker_b3, updated_at
                )
                VALUES (
                    123456, 'NO TICKER S.A.', 'Energy', 'energy', NULL, '2026-06-18T12:00:00Z'
                )
                """
            )
        )

    service.add_company_to_universe(u_id, 123456, "watchlist", "No ticker regression")

    scores = service.calculate_priority_scores(u_id)
    row = next(item for item in scores if item["cd_cvm"] == 123456)
    assert row["ticker_b3"] is None

    queue = service.get_work_queue(u_id)
    task = next(item for item in queue if item["cd_cvm"] == 123456)
    assert task["ticker_b3"] is None
    # The new work queue uses an 'identifier' field like 'CVM 123456'
    assert "123456" in (task.get("identifier") or task.get("company_name") or "")


def test_owner_analyst_update(test_engine):
    """Owner update: persists, clears, and logs to decision_history."""
    from sqlalchemy import text as _t

    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe("Owner Test", "Owner test universe", "Equity", None)

    # Seed a company
    with test_engine.begin() as conn:
        conn.execute(_t(
            "INSERT INTO companies (cd_cvm, company_name, ticker_b3, is_active, updated_at) "
            "VALUES (7777, 'OWNER S.A.', 'OWNR3', 1, '2024-01-01')"
        ))

    service.add_company_to_universe(u_id, 7777, "core", "owner test seed")

    # Assign owner
    service.update_company_owner_analyst(u_id, 7777, owner="Alice", rationale="Initial assign")

    scores = service.calculate_priority_scores(u_id)
    row = next(s for s in scores if s["cd_cvm"] == 7777)
    assert row["owner_analyst"] == "Alice"

    # Decision history must have the owner_change event
    history = service.get_decision_history(u_id, 7777)
    owner_events = [h for h in history if h["event_type"] == "owner_change"]
    assert len(owner_events) >= 1
    assert owner_events[0]["new_value"] == "Alice"

    # Clear the owner
    service.update_company_owner_analyst(u_id, 7777, owner=None, rationale="Remove assign")
    scores2 = service.calculate_priority_scores(u_id)
    row2 = next(s for s in scores2 if s["cd_cvm"] == 7777)
    assert row2["owner_analyst"] is None


def test_recommendation_summary(test_engine):
    """Recommendation summary: returns proposed_actions, risks, summary metrics. Never auto-approves."""
    from sqlalchemy import text as _t

    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe("Rec Test", "Recommendation test universe", "Equity", None)

    with test_engine.begin() as conn:
        conn.execute(_t(
            "INSERT INTO companies (cd_cvm, company_name, ticker_b3, is_active, updated_at) "
            "VALUES (8888, 'REC S.A.', 'REC3', 1, '2024-01-01')"
        ))

    service.add_company_to_universe(u_id, 8888, "must_cover", "rec test seed")

    rec = service.get_recommendation_summary(u_id)

    # Must have all required keys
    assert "proposed_actions" in rec
    assert "risks" in rec
    assert "capacity_summary" in rec
    assert isinstance(rec["proposed_actions"], list)
    assert isinstance(rec["risks"], list)

    # manager_decision must not be auto-approved
    decision = rec.get("manager_decision") or {}
    assert decision.get("status") != "approved", "Recommendation must not auto-approve"


def test_manager_decision_change_logged(test_engine):
    """Manager decision status changes must be logged in coverage_decision_history."""
    from sqlalchemy import text as _t

    service = CoverageUniverseService(test_engine)
    u_id = service.create_universe("Decision Log Test", "Decision log test universe", "Equity", None)

    # Initial: no manager_decision in assumptions → treated as 'draft' baseline

    # Update via update_universe to simulate bridge save_coverage_manager_decision logic
    universe = service.get_universe(u_id)
    assumptions = universe.get("assumptions") or {}
    from src.companies.coverage import now_iso_seconds
    now = now_iso_seconds()

    assumptions["manager_decision"] = {"status": "pending_review", "decided_at": now, "notes": "Board review"}
    service.update_universe(
        u_id,
        universe["name"],
        universe.get("purpose"),
        universe.get("benchmark"),
        universe.get("status", "active"),
        assumptions,
    )

    # Log the decision manually (this is what the bridge does)
    # cd_cvm=0 is the sentinel for universe-level events (NOT NULL constraint)
    with test_engine.begin() as conn:
        conn.execute(
            _t(
                "INSERT INTO coverage_decision_history "
                "(universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp) "
                "VALUES (:u_id, 0, 'manager_decision_change', 'draft', 'pending_review', 'Board review', :ts)"
            ),
            {"u_id": u_id, "ts": now},
        )

    history = service.get_decision_history(u_id)
    decision_events = [h for h in history if h["event_type"] == "manager_decision_change"]
    assert len(decision_events) >= 1
    ev = decision_events[0]
    assert ev["previous_value"] == "draft"
    assert ev["new_value"] == "pending_review"
    # cd_cvm=0 is the sentinel for universe-level decisions
    assert ev["cd_cvm"] in (0, None)


def test_bridge_coverage_operations(test_engine):
    """Test bridge operations for manager decisions and owner changes calling the actual bridge class."""
    from desktop.bridge import CVMBridge
    from types import SimpleNamespace
    from src.companies.coverage import CoverageUniverseService

    class MockCVMBridge(CVMBridge):
        def __init__(self, engine):
            super().__init__()
            self._service = SimpleNamespace(engine=engine)

    bridge = MockCVMBridge(test_engine)
    service = CoverageUniverseService(test_engine)

    # 1. Setup a universe
    u_id = service.create_universe("Bridge Test", "Bridge test universe", "Equity", None)

    # Seed a company
    with test_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO companies (cd_cvm, company_name, ticker_b3, is_active, updated_at) "
                "VALUES (9999, 'BRIDGE CO S.A.', 'BRDG3', 1, '2024-01-01')"
            )
        )
    service.add_company_to_universe(u_id, 9999, "watchlist", "seed")

    # 2. Test update_company_owner_analyst via bridge
    # Check that empty rationale is rejected
    res = bridge.update_company_owner_analyst({
        "universe_id": u_id,
        "cd_cvm": 9999,
        "owner": "Bob",
        "rationale": ""
    })
    assert "error" in res
    assert "Rationale is required" in res["error"]

    res_whitespace = bridge.update_company_owner_analyst({
        "universe_id": u_id,
        "cd_cvm": 9999,
        "owner": "Bob",
        "rationale": "   "
    })
    assert "error" in res_whitespace

    # Check success
    res_success = bridge.update_company_owner_analyst({
        "universe_id": u_id,
        "cd_cvm": 9999,
        "owner": "  Bob  ",
        "rationale": "Assigning Bob"
    })
    assert res_success.get("success") is True

    # Verify persisted in database
    scores = service.calculate_priority_scores(u_id)
    row = next(s for s in scores if s["cd_cvm"] == 9999)
    assert row["owner_analyst"] == "Bob"

    # Check clear owner
    res_clear = bridge.update_company_owner_analyst({
        "universe_id": u_id,
        "cd_cvm": 9999,
        "owner": "",
        "rationale": "Clearing owner"
    })
    assert res_clear.get("success") is True
    scores = service.calculate_priority_scores(u_id)
    row = next(s for s in scores if s["cd_cvm"] == 9999)
    assert row["owner_analyst"] is None

    # 3. Test save_coverage_manager_decision via bridge
    # Check that empty rationale is rejected on status change
    res_mgr_err = bridge.save_coverage_manager_decision({
        "universe_id": u_id,
        "status": "pending_review",
        "notes": ""
    })
    assert "error" in res_mgr_err
    assert "Rationale is required" in res_mgr_err["error"]

    # Check success
    res_mgr_ok = bridge.save_coverage_manager_decision({
        "universe_id": u_id,
        "status": "pending_review",
        "notes": "Sending to board review"
    })
    assert res_mgr_ok.get("success") is True
    assert res_mgr_ok.get("status") == "pending_review"

    # Verify persisted in universe assumptions
    u = service.get_universe(u_id)
    assumptions = u.get("assumptions") or {}
    mgr_decision = assumptions.get("manager_decision") or {}
    assert mgr_decision.get("status") == "pending_review"
    assert mgr_decision.get("notes") == "Sending to board review"

    # Verify history logs contain manager_decision_change
    history = service.get_decision_history(u_id)
    events = [h for h in history if h["event_type"] == "manager_decision_change"]
    assert len(events) >= 1
    assert events[0]["previous_value"] == "draft"
    assert events[0]["new_value"] == "pending_review"
    assert events[0]["rationale"] == "Sending to board review"

