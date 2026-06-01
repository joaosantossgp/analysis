"""Energy KPI database schema — separate energy_kpis.db.

7 tables: kpi_catalog, country_dimension, country_kpi_values,
          kpi_sources, source_snapshots, kpi_refresh_log, data_quality_checks.

Usage:
    engine = get_energy_kpi_engine(settings)   # creates DB + tables
    with engine.connect() as conn: ...
"""
from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine, text, Engine

from src.settings import AppSettings


def ensure_energy_kpi_tables_for_connection(conn) -> None:
    """Create all energy KPI tables. Safe to call multiple times (idempotent)."""
    conn.execute(text("PRAGMA journal_mode = WAL"))
    conn.execute(text("PRAGMA synchronous = OFF"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kpi_catalog (
            kpi_id                    TEXT PRIMARY KEY,
            display_name              TEXT NOT NULL,
            description               TEXT,
            kpi_type                  TEXT,
            macro_category            TEXT,
            subsector                 TEXT,
            sector                    TEXT NOT NULL DEFAULT 'Energy Utilities',
            geography_type            TEXT NOT NULL DEFAULT 'country',
            entity_type               TEXT NOT NULL DEFAULT 'country',
            unit                      TEXT,
            frequency                 TEXT NOT NULL DEFAULT 'annual',
            primary_source            TEXT,
            primary_source_field      TEXT,
            fallback_source           TEXT,
            fallback_source_field     TEXT,
            calculation_method        TEXT,
            v1_status                 TEXT,
            dashboard_priority        TEXT,
            excel_export_priority     TEXT,
            source_verification_status TEXT,
            higher_is_better          INTEGER,
            source_caveats            TEXT,
            audit_notes               TEXT,
            owner_module              TEXT NOT NULL DEFAULT 'energy_kpi',
            availability_status       TEXT NOT NULL DEFAULT 'available',
            created_at                TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS country_dimension (
            iso_code     TEXT PRIMARY KEY,
            country_name TEXT NOT NULL,
            region       TEXT,
            is_v1_scope  INTEGER NOT NULL DEFAULT 0
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS country_kpi_values (
            kpi_id              TEXT NOT NULL,
            iso_code            TEXT NOT NULL,
            period              INTEGER NOT NULL,
            value               REAL,
            value_owid          REAL,
            value_ember         REAL,
            unit                TEXT,
            source              TEXT,
            source_priority     INTEGER,
            source_field        TEXT,
            data_quality_status TEXT NOT NULL DEFAULT 'ok',
            source_conflict     INTEGER NOT NULL DEFAULT 0,
            fallback_used       INTEGER NOT NULL DEFAULT 0,
            last_updated        TEXT,
            snapshot_id         TEXT,
            PRIMARY KEY (kpi_id, iso_code, period)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kpi_sources (
            source            TEXT PRIMARY KEY,
            display_name      TEXT NOT NULL,
            base_url          TEXT,
            license           TEXT,
            default_priority  INTEGER,
            cadence           TEXT,
            retrieval_method  TEXT,
            schema_version    TEXT,
            notes             TEXT,
            last_refresh_at   TEXT
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS source_snapshots (
            snapshot_id          TEXT PRIMARY KEY,
            source               TEXT NOT NULL,
            fetched_at           TEXT NOT NULL,
            file_path            TEXT NOT NULL,
            sha256               TEXT,
            row_count            INTEGER,
            source_version_label TEXT,
            status               TEXT NOT NULL DEFAULT 'ok'
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS kpi_refresh_log (
            run_id         TEXT PRIMARY KEY,
            started_at     TEXT NOT NULL,
            finished_at    TEXT,
            source         TEXT,
            status         TEXT NOT NULL DEFAULT 'running',
            rows_ingested  INTEGER,
            rows_conflict  INTEGER,
            error          TEXT,
            triggered_by   TEXT
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS data_quality_checks (
            check_id     TEXT PRIMARY KEY,
            run_id       TEXT,
            check_name   TEXT NOT NULL,
            severity     TEXT NOT NULL DEFAULT 'info',
            passed       INTEGER NOT NULL DEFAULT 1,
            details_json TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    # Indexes for common query patterns
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ckv_kpi_iso ON country_kpi_values(kpi_id, iso_code)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ckv_iso_period ON country_kpi_values(iso_code, period)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ckv_snapshot ON country_kpi_values(snapshot_id)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dqc_run ON data_quality_checks(run_id)"
    ))


def ensure_energy_kpi_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        ensure_energy_kpi_tables_for_connection(conn)


@lru_cache(maxsize=1)
def _build_energy_kpi_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    ensure_energy_kpi_tables(engine)
    return engine


def get_energy_kpi_engine(settings: AppSettings) -> Engine:
    """Return (and lazily create) the energy KPI SQLite engine.

    The engine is cached by DB URL. Tables are created on first access.
    The DB file is at settings.paths.energy_kpi_db_path — separate from
    cvm_financials.db to allow independent refresh and zero migration risk.
    """
    settings.paths.energy_kpi_db_path.parent.mkdir(parents=True, exist_ok=True)
    return _build_energy_kpi_engine(settings.paths.energy_kpi_sqlite_url)
