from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import IntegrityError

from src.companies.entity_registry_schema import ensure_entity_registry_schema, validate_entity_registry_schema
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


def test_sqlite_schema_rejects_direct_entity_id_updates_and_orphans(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registry.db'}")
    ensure_entity_registry_schema(engine)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO entity_registry_entities (
                    entity_id, entity_kind, lifecycle_status, lifecycle_reason,
                    created_origin, created_at, updated_at
                ) VALUES ('entity-1', 'organization', 'active', NULL,
                          'source_ingestion', '2026-01-01T00:00:00+00:00',
                          '2026-01-01T00:00:00+00:00')
            """)
        )

    with pytest.raises(Exception, match="immutable"):
        with engine.begin() as conn:
            conn.execute(text("UPDATE entity_registry_entities SET entity_id = 'entity-2'"))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO entity_registry_alias_claims (
                        alias_id, entity_id, alias_type, raw_value, locale, origin,
                        evidence_id, evidence_status, effective_from, effective_to,
                        system_from, system_to
                    ) VALUES ('alias-1', 'missing-entity', 'trade_name', 'ORPHAN', NULL,
                              'source_ingestion', NULL, 'none',
                              '2026-01-01T00:00:00+00:00', NULL,
                              '2026-01-01T00:00:00+00:00', NULL)
                """)
            )


def test_schema_enables_foreign_keys_for_preexisting_pooled_connections(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pooled.db'}",
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
    )
    first = engine.connect()
    second = engine.connect()
    first.execute(text("PRAGMA foreign_keys = OFF"))
    second.execute(text("PRAGMA foreign_keys = OFF"))
    first.close()
    second.close()

    ensure_entity_registry_schema(engine)

    for index in range(2):
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        text("""
                            INSERT INTO entity_registry_alias_claims (
                                alias_id, entity_id, alias_type, raw_value, origin,
                                evidence_status, effective_from, system_from
                            ) VALUES (:alias_id, 'orphan', 'trade_name', 'ORPHAN',
                                      'source_ingestion', 'none',
                                      '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                        """),
                        {"alias_id": f"orphan-{index}"},
                    )


def test_schema_validation_rejects_same_name_incomplete_shape_without_ddl(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'incomplete.db'}")
    table_names = (
        "entity_registry_entities",
        "entity_registry_evidence",
        "entity_registry_identifier_claims",
        "entity_registry_alias_claims",
        "entity_registry_organization_facets",
        "entity_registry_lifecycle_events",
        "entity_registry_identifier_guards",
    )
    with engine.begin() as conn:
        for table_name in table_names:
            conn.execute(text(f"CREATE TABLE {table_name} (id TEXT PRIMARY KEY)"))

    with pytest.raises(ValueError, match="incomplete"):
        validate_entity_registry_schema(engine)
