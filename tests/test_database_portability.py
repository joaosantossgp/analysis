# -*- coding: utf-8 -*-
"""
Regression tests for cross-dialect behavior in src/financials/database.py.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.financials.database import CVMDatabase
from src.companies.entity_registry_schema import ensure_entity_registry_schema


class _RecorderConn:
    def __init__(self, fail_on_execute: bool = False):
        self.fail_on_execute = fail_on_execute
        self.calls: list[tuple[str, dict | None]] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        if self.fail_on_execute:
            raise RuntimeError("forced execute failure")
        return None

    def execution_options(self, **kwargs):
        return self


class _Ctx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, dialect_name: str):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.connect_conn = _RecorderConn()
        self.begin_conn = _RecorderConn()
        self.connect_calls = 0
        self.begin_calls = 0

    def connect(self):
        self.connect_calls += 1
        return _Ctx(self.connect_conn)

    def begin(self):
        self.begin_calls += 1
        return _Ctx(self.begin_conn)


def _new_db_with_engine(engine):
    db = CVMDatabase.__new__(CVMDatabase)
    db._engine = engine
    return db


class _FakeFrame:
    def __init__(self, columns: list[str]):
        self.columns = columns
        self.calls: list[dict] = []

    def to_sql(self, *args, **kwargs):
        self.calls.append(kwargs)
        return None


@patch("src.financials.database._backfill_companies_metadata")
def test_init_db_applies_pragmas_for_sqlite_only(mock_backfill):
    db = _new_db_with_engine(_FakeEngine("sqlite"))
    db._init_db()

    pragma_sql = "\n".join(sql for sql, _ in db._engine.connect_conn.calls)
    assert "PRAGMA journal_mode = WAL" in pragma_sql
    assert "PRAGMA synchronous = OFF" in pragma_sql

    ddl_sql = "\n".join(sql for sql, _ in db._engine.begin_conn.calls)
    assert "CREATE TABLE IF NOT EXISTS financial_reports" in ddl_sql
    assert "CREATE TABLE IF NOT EXISTS qa_logs" in ddl_sql
    # SQLite indexes use regular begin() — no CONCURRENTLY
    assert "idx_fr_cd_cvm" in ddl_sql
    assert "CONCURRENTLY" not in ddl_sql


@patch("src.financials.database._backfill_companies_metadata")
def test_init_db_skips_pragmas_for_postgresql(mock_backfill):
    db = _new_db_with_engine(_FakeEngine("postgresql"))
    db._init_db()

    # connect() is called once for CONCURRENTLY index creation (outside transaction)
    assert db._engine.connect_calls == 1
    ddl_sql = "\n".join(sql for sql, _ in db._engine.begin_conn.calls)
    assert "PRAGMA" not in ddl_sql
    assert "CREATE TABLE IF NOT EXISTS financial_reports" in ddl_sql

    idx_sql = "\n".join(sql for sql, _ in db._engine.connect_conn.calls)
    assert "CONCURRENTLY" in idx_sql
    assert "idx_fr_cd_cvm" in idx_sql
    assert "idx_fr_cd_cvm_stmt_year" in idx_sql
    assert "idx_companies_ticker" in idx_sql
    assert "idx_qa_logs_scope" in idx_sql


def test_startup_keeps_only_the_financial_reports_indexes_reads_use(tmp_path):
    from sqlalchemy import create_engine, text

    path = tmp_path / "legacy.db"
    CVMDatabase(str(path))._engine.dispose()
    legacy = create_engine(f"sqlite:///{path}")
    with legacy.begin() as conn:  # indexes created by versions before #586
        conn.execute(text('CREATE INDEX idx_fr_cd_cvm ON financial_reports("CD_CVM")'))
        conn.execute(text('CREATE INDEX idx_fr_cd_conta_period_label ON financial_reports("CD_CONTA", "PERIOD_LABEL")'))
    legacy.dispose()

    db = CVMDatabase(str(path))
    with db._engine.connect() as conn:
        names = {row[1] for row in conn.execute(text("PRAGMA index_list('financial_reports')"))}
    db._engine.dispose()
    assert names == {"sqlite_autoindex_financial_reports_1", "idx_fr_cd_cvm_stmt_year",
                     "idx_fr_cvm_year", "idx_fr_year_period"}


def test_scoped_qa_replacement_uses_an_index_on_a_legacy_database(tmp_path):
    from sqlalchemy import create_engine, text

    path = tmp_path / "legacy.db"
    legacy = create_engine(f"sqlite:///{path}")
    with legacy.begin() as conn:
        conn.execute(text('CREATE TABLE qa_logs (id INTEGER PRIMARY KEY, "CD_CVM" INTEGER, "STATEMENT_TYPE" TEXT)'))
    legacy.dispose()

    db = CVMDatabase(str(path))
    with db._engine.connect() as conn:
        plan = conn.execute(text('EXPLAIN QUERY PLAN DELETE FROM qa_logs WHERE "CD_CVM" = 1 '
                                 'AND "STATEMENT_TYPE" = \'DRE\' AND "REPORT_YEAR" = 2024')).fetchall()
    db._engine.dispose()
    assert "USING INDEX idx_qa_logs_scope" in " ".join(row[3] for row in plan)


def test_upsert_company_metadata_uses_dialect_safe_sql():
    db = _new_db_with_engine(_FakeEngine("postgresql"))
    conn = _RecorderConn()

    db._upsert_company_metadata(
        conn,
        company_name="ACME S.A.",
        cvm_code=12345,
        company_type="comercial",
        setor_cvm="Energia",
        ticker_b3="ACME3.SA",
    )

    sql_joined = "\n".join(sql.lower() for sql, _ in conn.calls)
    assert "insert or ignore" not in sql_joined
    assert "strftime" not in sql_joined
    assert "where not exists" in sql_joined

    assert len(conn.calls) == 2
    insert_params = conn.calls[0][1]
    assert insert_params is not None
    assert isinstance(insert_params["updated_at"], str)
    assert "T" in insert_params["updated_at"]


def test_upsert_company_metadata_raises_on_failure():
    db = _new_db_with_engine(_FakeEngine("sqlite"))
    conn = _RecorderConn(fail_on_execute=True)

    with pytest.raises(RuntimeError):
        db._upsert_company_metadata(
            conn,
            company_name="BROKEN S.A.",
            cvm_code=999,
            company_type="comercial",
            setor_cvm=None,
            ticker_b3=None,
        )


def test_to_sql_with_retry_scales_chunksize_for_sqlite_variable_limit():
    db = _new_db_with_engine(_FakeEngine("sqlite"))
    frame = _FakeFrame(
        [
            "COMPANY_NAME", "CD_CVM", "COMPANY_TYPE", "STATEMENT_TYPE",
            "REPORT_YEAR", "PERIOD_LABEL", "LINE_ID_BASE", "CD_CONTA",
            "DS_CONTA", "STANDARD_NAME", "QA_CONFLICT", "VL_CONTA",
        ]
    )

    db._to_sql_with_retry("financial_reports", frame, _RecorderConn())

    assert len(frame.calls) == 1
    assert frame.calls[0]["chunksize"] == 75


def test_to_sql_with_retry_keeps_default_chunksize_for_postgresql():
    db = _new_db_with_engine(_FakeEngine("postgresql"))
    frame = _FakeFrame(["a", "b", "c"])

    db._to_sql_with_retry("financial_reports", frame, _RecorderConn())

    assert len(frame.calls) == 1
    assert frame.calls[0]["chunksize"] == 2000


def test_registry_schema_uses_portable_ddl_without_startup_integration():
    engine = _FakeEngine("postgresql")

    ensure_entity_registry_schema(engine)

    ddl_sql = "\n".join(sql for sql, _ in engine.begin_conn.calls)
    assert "CREATE TABLE IF NOT EXISTS entity_registry_entities" in ddl_sql
    assert "PRAGMA" not in ddl_sql
    assert "entity_registry_prevent_entity_id_update" in ddl_sql
