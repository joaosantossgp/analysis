from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from src.companies.entity_registry_schema import ensure_entity_registry_schema
from src.financials.database import init_db_tables


def test_registry_schema_is_idempotent_and_leaves_legacy_rows_untouched(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registry.db'}")
    init_db_tables(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO companies (cd_cvm, company_name, updated_at) "
                "VALUES (9512, 'PETROBRAS', '2026-07-29T00:00:00+00:00')"
            )
        )
        conn.execute(
            text(
                'INSERT INTO financial_reports ('
                '"CD_CVM", "STATEMENT_TYPE", "PERIOD_LABEL", "LINE_ID_BASE") '
                "VALUES (9512, 'BPA', 'FY2025', '1')"
            )
        )

    ensure_entity_registry_schema(engine)
    ensure_entity_registry_schema(engine)

    inspector = inspect(engine)
    assert {
        "entity_registry_entities",
        "entity_registry_evidence",
        "entity_registry_identifier_claims",
        "entity_registry_alias_claims",
    }.issubset(set(inspector.get_table_names()))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM companies")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM financial_reports")).scalar_one() == 1


def test_normal_startup_does_not_create_registry_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")

    init_db_tables(engine)

    assert "entity_registry_entities" not in inspect(engine).get_table_names()
