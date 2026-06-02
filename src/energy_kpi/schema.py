"""Energy KPI database schema — separate energy_kpis.db.

7 tables: kpi_catalog, country_dimension, country_kpi_values,
          kpi_sources, source_snapshots, kpi_refresh_log, data_quality_checks.

SIN subsystem support is additive and uses the same local DB, with
subsystem_dimension and subsystem_kpi_values.

Plant/plant-parcel support is also additive and keeps source metadata,
refresh logs, ANEEL SIGA plant registry rows, CCEE plant parcel monthly rows,
and CCEE hourly generation rows in this same local energy database.

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

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS subsystem_dimension (
            subsystem_code TEXT PRIMARY KEY,
            display_name   TEXT NOT NULL,
            source_aliases  TEXT,
            sort_order      INTEGER NOT NULL
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS subsystem_kpi_values (
            kpi_id              TEXT NOT NULL,
            subsystem_code      TEXT NOT NULL,
            reference_datetime  TEXT NOT NULL,
            source_value        REAL,
            normalized_value    REAL,
            unit                TEXT,
            source              TEXT NOT NULL,
            source_dataset      TEXT NOT NULL,
            source_field        TEXT,
            source_hash         TEXT NOT NULL,
            snapshot_id         TEXT,
            ingestion_batch_id  TEXT,
            data_quality_status TEXT NOT NULL DEFAULT 'ok',
            created_at          TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (kpi_id, reference_datetime, subsystem_code)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_skv_subsystem_ref ON "
        "subsystem_kpi_values(subsystem_code, reference_datetime)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_skv_dataset_ref ON "
        "subsystem_kpi_values(source_dataset, reference_datetime)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_skv_snapshot ON subsystem_kpi_values(snapshot_id)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS energy_sources (
            source_id         TEXT PRIMARY KEY,
            source_name       TEXT NOT NULL,
            dataset_name      TEXT NOT NULL,
            provider          TEXT NOT NULL,
            official_url      TEXT,
            refresh_frequency TEXT,
            granularity       TEXT,
            description       TEXT,
            known_caveats     TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS energy_source_refresh_log (
            refresh_id           TEXT PRIMARY KEY,
            source_id            TEXT NOT NULL,
            requested_by         TEXT,
            started_at           TEXT NOT NULL,
            finished_at          TEXT,
            status               TEXT NOT NULL DEFAULT 'running',
            period_start         TEXT,
            period_end           TEXT,
            rows_downloaded      INTEGER,
            rows_inserted        INTEGER,
            rows_updated         INTEGER,
            error_message        TEXT,
            local_file_path      TEXT,
            checksum             TEXT,
            source_snapshot_date TEXT
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_esrl_source_started ON "
        "energy_source_refresh_log(source_id, started_at)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS aneel_siga_plants (
            ceg                       TEXT PRIMARY KEY,
            plant_name                TEXT,
            ceg_core                  TEXT,
            generation_type           TEXT,
            generation_source         TEXT,
            uf                        TEXT,
            phase                     TEXT,
            operation_start_date      TEXT,
            grant_type                TEXT,
            authorized_capacity_kw    REAL,
            inspected_capacity_kw     REAL,
            physical_guarantee_kw     REAL,
            agent_name                TEXT,
            ownership_description     TEXT,
            source_updated_at         TEXT,
            raw_payload_hash          TEXT NOT NULL,
            snapshot_id               TEXT,
            updated_at                TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_aneel_siga_uf ON aneel_siga_plants(uf)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_aneel_siga_source ON aneel_siga_plants(generation_source)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ccee_plant_parcels (
            plant_parcel_code        TEXT PRIMARY KEY,
            plant_parcel_acronym     TEXT,
            asset_code               TEXT,
            asset_acronym            TEXT,
            ceg                      TEXT,
            plant_name               TEXT,
            agent_name               TEXT,
            agent_profile            TEXT,
            submarket                TEXT,
            generation_source        TEXT,
            fuel                     TEXT,
            uf                       TEXT,
            dispatch_type            TEXT,
            parcel_feature           TEXT,
            capacity_mw              REAL,
            physical_guarantee_mwmed REAL,
            mre_flag                 TEXT,
            quota_regime_flag        TEXT,
            source_reference_month   TEXT,
            source_updated_at        TEXT,
            raw_payload_hash         TEXT NOT NULL,
            snapshot_id              TEXT,
            updated_at               TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cpp_ceg ON ccee_plant_parcels(ceg)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cpp_submarket ON ccee_plant_parcels(submarket)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cpp_source ON ccee_plant_parcels(generation_source)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cpp_ref_month ON ccee_plant_parcels(source_reference_month)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ccee_plant_parcel_monthly (
            reference_month                      TEXT NOT NULL,
            plant_parcel_code                    TEXT NOT NULL,
            plant_parcel_acronym                 TEXT,
            asset_code                           TEXT,
            asset_acronym                        TEXT,
            ceg                                  TEXT,
            plant_name                           TEXT,
            agent_code                           TEXT,
            agent_profile                        TEXT,
            agent_name                           TEXT,
            dispatch_type                        TEXT,
            loss_pooling_flag                    TEXT,
            generation_source                    TEXT,
            fuel                                 TEXT,
            submarket                            TEXT,
            uf                                   TEXT,
            parcel_feature                       TEXT,
            mre_flag                             TEXT,
            quota_regime_flag                    TEXT,
            commercial_operation_start_date      TEXT,
            discount_percent                     REAL,
            capacity_mw                          REAL,
            physical_guarantee_mwmed             REAL,
            commercial_operation_factor          REAL,
            internal_loss_abatement_factor       REAL,
            generation_center_of_gravity_mwmed   REAL,
            test_generation_mwmed                REAL,
            gf_center_of_gravity_mwmed           REAL,
            energy_security_generation_mwmed     REAL,
            constrained_on_generation_mwmed      REAL,
            reserve_operation_generation_mwmed   REAL,
            unit_commitment_generation_mwmed     REAL,
            source_dataset                       TEXT NOT NULL,
            raw_payload_hash                     TEXT NOT NULL,
            snapshot_id                          TEXT,
            updated_at                           TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (reference_month, plant_parcel_code)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppm_ceg ON ccee_plant_parcel_monthly(ceg)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppm_parcel_ref ON "
        "ccee_plant_parcel_monthly(plant_parcel_code, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppm_ref ON ccee_plant_parcel_monthly(reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppm_submarket ON ccee_plant_parcel_monthly(submarket)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppm_source ON ccee_plant_parcel_monthly(generation_source)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ccee_plant_parcel_hourly (
            reference_datetime                         TEXT NOT NULL,
            reference_month                            TEXT NOT NULL,
            commercialization_period                   INTEGER NOT NULL,
            plant_parcel_code                          TEXT NOT NULL,
            plant_acronym                              TEXT,
            generation_source                          TEXT,
            submarket                                  TEXT,
            plant_type                                 TEXT,
            generation_center_of_gravity_mwmed         REAL,
            generation_center_of_gravity_mwh           REAL,
            internal_loss_factor_pct                   REAL,
            loss_generation_apportionment_factor_mwh   REAL,
            energy_security_generation_mwh             REAL,
            constrained_on_generation_mwh              REAL,
            adjusted_restriction_charge_energy_mwmed   REAL,
            unavailability_mwh                         REAL,
            declared_cost_mwh                          REAL,
            hydraulic_displacement_factor_mwh          REAL,
            verified_generation_ons_mwh                REAL,
            verified_availability_mwh                  REAL,
            inflexible_generation_mwmed                REAL,
            substitute_unavailability_generation_mwh   REAL,
            reserve_power_generation_mwh               REAL,
            unit_commitment_generation_mwmed           REAL,
            final_merit_order_generation_mwh           REAL,
            adjusted_physical_guarantee_mwh            REAL,
            source_dataset                             TEXT NOT NULL,
            raw_payload_hash                           TEXT NOT NULL,
            snapshot_id                                TEXT,
            updated_at                                 TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (reference_datetime, commercialization_period, plant_parcel_code)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppe_parcel_ref ON "
        "ccee_plant_parcel_hourly(plant_parcel_code, reference_datetime)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppe_ref ON ccee_plant_parcel_hourly(reference_datetime)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppe_ref_month ON ccee_plant_parcel_hourly(reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppe_submarket ON ccee_plant_parcel_hourly(submarket)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cppe_source ON ccee_plant_parcel_hourly(generation_source)"
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
