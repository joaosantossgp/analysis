# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from src.platform.settings import build_settings
from src.companies.coverage import CoverageUniverseService, ensure_coverage_tables_for_connection


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
                INSERT INTO companies (cd_cvm, company_name, gics_sector, ticker_b3, updated_at)
                VALUES 
                (9512, 'PETROLEO BRASILEIRO S.A.', 'Petróleo, Gás e Biocombustíveis', 'PETR4', '2026-06-16T12:00:00Z'),
                (4170, 'VALE S.A.', 'Materiais Básicos', 'VALE3', '2026-06-16T12:00:00Z')
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

        # Seed mock market history volume
        conn.execute(
            text(
                """
                INSERT INTO market_history (cd_cvm, ticker, date, volume, adjusted_close, source)
                VALUES 
                (9512, 'PETR4', '2026-06-15', 50000000.0, 38.5, 'yahoo'),
                (4170, 'VALE3', '2026-06-15', 15000000.0, 62.1, 'yahoo')
                """
            )
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
    assert not any(t["cd_cvm"] == 9512 and t["item_key"] == "model_updated" for t in work_queue)

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

