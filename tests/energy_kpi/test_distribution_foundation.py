"""Tests for Slice 1: Distribution Foundation & Master Data."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text
from src.energy_kpi.distribution import (
    seed_distribution_static_data,
    normalize_cnpj,
    check_ownership_overlaps,
)
from src.energy_kpi.schema import ensure_energy_kpi_tables_for_connection


def test_cnpj_normalization():
    # Valid CNPJ with punctuation
    assert normalize_cnpj("15.139.629/0001-94") == "15139629000194"
    # Valid CNPJ raw
    assert normalize_cnpj("15139629000194") == "15139629000194"
    # Under-digit CNPJ (zero-padded)
    assert normalize_cnpj("6272793000184") == "06272793000184"
    # None/empty
    assert normalize_cnpj(None) is None
    assert normalize_cnpj("") is None
    # Invalid lengths
    assert normalize_cnpj("12345") is None  # Too short to zero-pad to 14
    assert normalize_cnpj("12345678901234567") is None  # Too long


def test_seed_distribution_static_data(db_conn):
    # DDL tables should be created by the fixture db_conn since it runs ensure_energy_kpi_tables_for_connection
    # Run seeder
    seed_distribution_static_data(db_conn)

    # Check Economic Groups
    groups = db_conn.execute(text("SELECT economic_group_id, group_name FROM distribution_economic_groups")).fetchall()
    assert len(groups) > 0
    assert any(g[0] == "neoenergia" for g in groups)

    # Check Listed Companies
    companies = db_conn.execute(text("SELECT cd_cvm, company_name FROM distribution_listed_companies")).fetchall()
    assert len(companies) > 0
    assert any(c[0] == 18660 for c in companies)

    # Check Distributors
    distributors = db_conn.execute(text("SELECT distributor_id, canonical_name, primary_uf FROM distribution_distributors")).fetchall()
    assert len(distributors) > 0
    assert any(d[0] == "coelba" and d[2] == "BA" for d in distributors)

    # Check Aliases
    aliases = db_conn.execute(text("SELECT alias_id, distributor_id, source FROM distribution_distributor_aliases")).fetchall()
    assert len(aliases) > 0
    assert any(a[1] == "coelba" for a in aliases)

    # Check Ownership History
    history = db_conn.execute(text("SELECT ownership_id, distributor_id, valid_from FROM distribution_ownership_history")).fetchall()
    assert len(history) > 0
    assert any(h[1] == "neoenergia_brasilia" for h in history)


def test_check_ownership_overlaps_detects_conflicts(db_conn):
    seed_distribution_static_data(db_conn)

    # Confirm there are no overlaps in the default seeded data
    conflicts = check_ownership_overlaps(db_conn)
    assert len(conflicts) == 0, f"Seeded data has overlaps: {conflicts}"

    # Insert a conflicting ownership row
    # coelba normally has coelba_neo valid from 2000-01-01 to 2099-12-31
    # Let's insert a second row for coelba that overlaps
    db_conn.execute(text("""
        INSERT INTO distribution_ownership_history (
            ownership_id, distributor_id, economic_group_id, cd_cvm,
            valid_from, valid_to, control_status, operational_consolidation_flag
        )
        VALUES ('coelba_conflict', 'coelba', 'cpfl', 18660, '2020-01-01', '2025-12-31', 'controlled', 1)
    """))

    conflicts = check_ownership_overlaps(db_conn)
    assert len(conflicts) == 1
    assert conflicts[0]["distributor_id"] == "coelba"
    assert {conflicts[0]["id_a"], conflicts[0]["id_b"]} == {"coelba_neo", "coelba_conflict"}


def test_distribution_old_schema_upgrade_adds_columns_without_data_loss(tmp_path):
    db_path = tmp_path / "old-distribution.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE distribution_tariff_facts (
                fact_id TEXT PRIMARY KEY,
                distributor_id TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                resolution TEXT,
                valid_from TEXT,
                valid_to TEXT,
                tariff_base TEXT,
                subgroup TEXT,
                modality TEXT,
                class_name TEXT,
                subclass TEXT,
                consumer_detail TEXT,
                tariff_period TEXT,
                unit TEXT NOT NULL,
                tusd_value REAL,
                te_value REAL,
                source_row_hash TEXT NOT NULL,
                snapshot_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            INSERT INTO distribution_tariff_facts (
                fact_id, distributor_id, reference_month, unit, source_row_hash
            )
            VALUES ('old-tariff-row', 'coelba', '2025-01', 'R$/MWh', 'old-hash')
        """))
        conn.execute(text("""
            CREATE TABLE distribution_delinquency_indicators (
                indicator_code TEXT PRIMARY KEY,
                indicator_name TEXT NOT NULL,
                description TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO distribution_delinquency_indicators (
                indicator_code, indicator_name, description
            )
            VALUES ('ITot1', 'ITot1', 'old description')
        """))

    with engine.connect() as conn:
        ensure_energy_kpi_tables_for_connection(conn)
        seed_distribution_static_data(conn)

        tariff_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(distribution_tariff_facts)")).fetchall()
        }
        indicator_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(distribution_delinquency_indicators)")).fetchall()
        }
        assert "accessing_agent" in tariff_cols
        assert {"unit", "analytical_category", "publication_status", "is_lead_kpi"}.issubset(indicator_cols)

        old_row_count = conn.execute(text("""
            SELECT count(*) FROM distribution_tariff_facts WHERE fact_id = 'old-tariff-row'
        """)).scalar()
        assert old_row_count == 1

        registered_codes = conn.execute(text("""
            SELECT count(DISTINCT indicator_code) FROM distribution_delinquency_indicators
        """)).scalar()
        assert registered_codes == 80
