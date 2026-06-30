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

import logging
import threading
from functools import lru_cache

from sqlalchemy import create_engine, text, Engine

from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)
_ENGINE_BUILD_LOCK = threading.RLock()


def _is_sqlite_locked_error(exc: Exception) -> bool:
    return "database is locked" in str(exc).lower()


def _configure_energy_kpi_connection(conn, *, enable_wal: bool) -> None:
    """Apply SQLite pragmas without making read-only startup fail on locks."""
    conn.execute(text("PRAGMA busy_timeout = 250"))
    if enable_wal:
        try:
            conn.execute(text("PRAGMA journal_mode = WAL"))
        except Exception as exc:
            if not _is_sqlite_locked_error(exc):
                raise
            logger.debug("energy KPI WAL setup skipped because database is locked")
    try:
        conn.execute(text("PRAGMA synchronous = OFF"))
    except Exception as exc:
        if not _is_sqlite_locked_error(exc):
            raise
        logger.debug("energy KPI synchronous setup skipped because database is locked")
    conn.execute(text("PRAGMA busy_timeout = 5000"))


def _ensure_columns(conn, table_name: str, columns: dict[str, str]) -> None:
    """Add missing SQLite columns for additive schema upgrades."""
    existing = {
        str(row[1])
        for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def ensure_energy_kpi_tables_for_connection(conn, *, enable_wal: bool = True) -> None:
    """Create all energy KPI tables. Safe to call multiple times (idempotent)."""
    _configure_energy_kpi_connection(conn, enable_wal=enable_wal)

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
    _ensure_columns(
        conn,
        "energy_source_refresh_log",
        {
            "requested_period": "TEXT",
            "dataset_name": "TEXT",
            "source_url": "TEXT",
            "downloaded_bytes": "INTEGER",
            "source_rows": "INTEGER",
            "parsed_rows": "INTEGER",
            "normalized_rows": "INTEGER",
            "rows_skipped": "INTEGER",
            "warning_message": "TEXT",
            "detected_encoding": "TEXT",
            "import_mode": "TEXT",
            "original_file_name": "TEXT",
            "file_size_bytes": "INTEGER",
            "file_hash": "TEXT",
            "file_type": "TEXT",
            "detected_period": "TEXT",
            "source_page_url": "TEXT",
            "canonical_rows": "INTEGER",
            "valid_domain_rows": "INTEGER",
            "missing_key_rows": "INTEGER",
            "invalid_value_rows": "INTEGER",
            "unresolved_identity_rows": "INTEGER",
            "non_distributor_entity_rows": "INTEGER",
            "exact_duplicate_rows": "INTEGER",
            "duplicate_groups": "INTEGER",
            "conflicting_logical_keys": "INTEGER",
            "conflict_rows": "INTEGER",
            "quarantined_rows": "INTEGER",
            "lead_kpi_rows": "INTEGER",
            "supporting_detail_rows": "INTEGER",
            "intentionally_excluded_rows": "INTEGER",
            "rejected_rows": "INTEGER",
            "rows_unchanged": "INTEGER",
            "rows_removed_deactivated": "INTEGER",
            "final_published_rows": "INTEGER",
            "affected_periods": "TEXT",
            "affected_distributors": "INTEGER",
            "affected_non_distributors": "INTEGER",
            "elapsed_download_ms": "INTEGER",
            "elapsed_parse_ms": "INTEGER",
            "elapsed_publish_ms": "INTEGER",
            "elapsed_aggregate_ms": "INTEGER",
            "elapsed_lock_wait_ms": "INTEGER",
            "peak_rss_mb": "REAL",
            "cpu_time_ms": "INTEGER",
            "parser_version": "TEXT",
            "schema_fingerprint": "TEXT",
            "snapshot_id": "TEXT",
            "final_source_status": "TEXT",
            "storage_telemetry_json": "TEXT",
        },
    )
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_esrl_source_started ON "
        "energy_source_refresh_log(source_id, started_at)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS ccee_discovered_resources (
            dataset_id                   TEXT NOT NULL,
            resource_name                TEXT NOT NULL,
            period_type                  TEXT NOT NULL,
            year                         INTEGER NOT NULL,
            month                        INTEGER,
            format                       TEXT NOT NULL,
            resource_url                 TEXT NOT NULL,
            discovered_at                TEXT NOT NULL,
            last_successful_download_at  TEXT,
            checksum                     TEXT,
            source_page_url              TEXT,
            status                       TEXT NOT NULL DEFAULT 'discovered',
            PRIMARY KEY (dataset_id, resource_name)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_cdr_dataset_period ON "
        "ccee_discovered_resources(dataset_id, year, month)"
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
        "CREATE INDEX IF NOT EXISTS idx_cppe_ref_month ON ccee_plant_parcel_hourly(reference_month)"
    ))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plant_parcel_daily_generation_mart (
            plant_parcel_code             TEXT NOT NULL,
            reference_date                TEXT NOT NULL,
            reference_month               TEXT NOT NULL,
            generation_mwh                REAL,
            verified_generation_mwh       REAL,
            verified_availability_mwh     REAL,
            unavailability_mwh            REAL,
            hourly_observations           INTEGER NOT NULL DEFAULT 0,
            first_reference_datetime      TEXT,
            last_reference_datetime       TEXT,
            source_dataset                TEXT,
            first_snapshot_id             TEXT,
            last_snapshot_id              TEXT,
            rebuilt_at                    TEXT NOT NULL,
            build_version                 TEXT NOT NULL,
            PRIMARY KEY (plant_parcel_code, reference_date)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ppdgm_parcel_month_date ON "
        "plant_parcel_daily_generation_mart(plant_parcel_code, reference_month, reference_date)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ppdgm_month_date ON "
        "plant_parcel_daily_generation_mart(reference_month, reference_date)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plant_parcel_hourly_preview_mart (
            plant_parcel_code                  TEXT NOT NULL,
            reference_datetime                 TEXT NOT NULL,
            reference_month                    TEXT NOT NULL,
            commercialization_period           INTEGER NOT NULL,
            generation_center_of_gravity_mwh   REAL,
            verified_generation_ons_mwh        REAL,
            verified_availability_mwh          REAL,
            unavailability_mwh                 REAL,
            source_dataset                     TEXT,
            snapshot_id                        TEXT,
            rebuilt_at                         TEXT NOT NULL,
            build_version                      TEXT NOT NULL,
            PRIMARY KEY (plant_parcel_code, reference_datetime, commercialization_period)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_pphpm_parcel_ref ON "
        "plant_parcel_hourly_preview_mart(plant_parcel_code, reference_datetime)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plant_ceg_hourly_generation_mart (
            ceg                         TEXT NOT NULL,
            reference_datetime          TEXT NOT NULL,
            reference_month             TEXT NOT NULL,
            commercialization_period    INTEGER NOT NULL,
            generation_mwh              REAL,
            verified_generation_mwh     REAL,
            verified_availability_mwh   REAL,
            unavailability_mwh          REAL,
            plant_parcel_count          INTEGER NOT NULL DEFAULT 0,
            source_dataset              TEXT,
            first_snapshot_id           TEXT,
            last_snapshot_id            TEXT,
            rebuilt_at                  TEXT NOT NULL,
            build_version               TEXT NOT NULL,
            PRIMARY KEY (ceg, reference_datetime, commercialization_period)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_pcghgm_ceg_month_ref ON "
        "plant_ceg_hourly_generation_mart(ceg, reference_month, reference_datetime)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_pcghgm_month_ceg ON "
        "plant_ceg_hourly_generation_mart(reference_month, ceg)"
    ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS energy_mart_builds (
            mart_name                  TEXT PRIMARY KEY,
            build_version              TEXT NOT NULL,
            rebuilt_at                 TEXT NOT NULL,
            source_table               TEXT NOT NULL,
            source_row_estimate        INTEGER,
            source_max_rowid           INTEGER,
            source_latest_reference    TEXT,
            period_start               TEXT,
            period_end                 TEXT,
            row_count                  INTEGER,
            status                     TEXT NOT NULL,
            error_message              TEXT,
            metadata_json              TEXT
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plant_parcel_source_submarket_monthly_mart (
            reference_month             TEXT NOT NULL,
            generation_source           TEXT NOT NULL,
            submarket                   TEXT NOT NULL,
            plant_parcel_count          INTEGER NOT NULL,
            hourly_observations         INTEGER NOT NULL,
            generation_mwh              REAL,
            verified_generation_mwh     REAL,
            first_reference_datetime    TEXT,
            last_reference_datetime     TEXT,
            source_dataset              TEXT,
            first_snapshot_id           TEXT,
            last_snapshot_id            TEXT,
            rebuilt_at                  TEXT NOT NULL,
            build_version               TEXT NOT NULL,
            PRIMARY KEY (reference_month, generation_source, submarket)
        )
    """))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ppssmm_source_month ON "
        "plant_parcel_source_submarket_monthly_mart(generation_source, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_ppssmm_submarket_month ON "
        "plant_parcel_source_submarket_monthly_mart(submarket, reference_month)"
    ))

    # ANEEL Electricity Distribution Analytics Domain Tables
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_economic_groups (
            economic_group_id TEXT PRIMARY KEY,
            group_name        TEXT NOT NULL,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_listed_companies (
            cd_cvm       INTEGER PRIMARY KEY,
            company_name TEXT NOT NULL,
            ticker_b3    TEXT,
            cnpj         TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_distributors (
            distributor_id     TEXT PRIMARY KEY,
            canonical_name     TEXT NOT NULL,
            current_legal_name TEXT,
            trade_name         TEXT,
            normalized_cnpj    TEXT,
            agent_code         TEXT,
            distributor_code   TEXT,
            concession_type   TEXT,
            primary_uf         TEXT,
            service_area       TEXT,
            status             TEXT NOT NULL DEFAULT 'active',
            classification     TEXT NOT NULL DEFAULT 'distributor',
            created_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    _ensure_columns(
        conn,
        "distribution_distributors",
        {
            "classification": "TEXT NOT NULL DEFAULT 'distributor'",
        },
    )

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_distributor_aliases (
            alias_id       TEXT PRIMARY KEY,
            distributor_id TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            source         TEXT NOT NULL,
            source_cnpj    TEXT,
            source_name    TEXT,
            normalized_name TEXT,
            match_method   TEXT,
            match_status   TEXT NOT NULL DEFAULT 'reviewed',
            review_notes   TEXT,
            created_at     TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_ownership_history (
            ownership_id                   TEXT PRIMARY KEY,
            distributor_id                 TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            economic_group_id              TEXT REFERENCES distribution_economic_groups(economic_group_id) ON DELETE SET NULL,
            cd_cvm                         INTEGER REFERENCES distribution_listed_companies(cd_cvm) ON DELETE SET NULL,
            valid_from                     TEXT NOT NULL,
            valid_to                       TEXT NOT NULL,
            control_status                 TEXT,
            ownership_percentage           REAL,
            operational_consolidation_flag INTEGER NOT NULL DEFAULT 1,
            mapping_source                 TEXT,
            mapping_status                 TEXT NOT NULL DEFAULT 'reviewed',
            review_notes                   TEXT,
            created_at                     TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at                     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS conglomerate_asset_mappings (
            asset_id       TEXT NOT NULL,
            asset_type     TEXT NOT NULL,
            cd_cvm         INTEGER,
            custom_owner_name TEXT,
            mapping_source TEXT NOT NULL DEFAULT 'auto',
            review_notes   TEXT,
            updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (asset_id, asset_type)
        )
    """))

    _ensure_columns(
        conn,
        "conglomerate_asset_mappings",
        {
            "custom_owner_name": "TEXT",
        },
    )

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_market_facts (
            fact_id                     TEXT PRIMARY KEY,
            distributor_id              TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            reference_month             TEXT NOT NULL,
            market_type                 TEXT,
            tariff_modality             TEXT,
            tariff_subgroup             TEXT,
            consumer_class              TEXT,
            consumer_subclass           TEXT,
            consumer_detail             TEXT,
            tariff_period               TEXT,
            energy_option               TEXT,
            accessing_agent_cnpj        TEXT,
            accessing_agent_name        TEXT,
            metric_name                 TEXT NOT NULL,
            raw_value                   REAL,
            normalized_value            REAL,
            original_unit               TEXT,
            normalized_unit             TEXT,
            source_row_hash             TEXT NOT NULL,
            snapshot_id                 TEXT,
            created_at                  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_energy_balance_facts (
            fact_id                TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            reference_month        TEXT NOT NULL,
            balance_modality       TEXT,
            energy_flow            TEXT,
            balance_characteristic TEXT,
            balance_detail         TEXT,
            raw_value              REAL,
            normalized_value       REAL,
            original_unit          TEXT,
            normalized_unit        TEXT,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_continuity_facts (
            fact_id                TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            set_id                 TEXT NOT NULL,
            set_name               TEXT,
            indicator_code         TEXT NOT NULL,
            reference_month        TEXT NOT NULL,
            actual_value           REAL,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_continuity_limits (
            limit_id               TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            set_id                 TEXT NOT NULL,
            set_name               TEXT,
            indicator_code         TEXT NOT NULL,
            validity_year          INTEGER NOT NULL,
            limit_value            REAL,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_continuity_compensations (
            compensation_id        TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            set_id                 TEXT NOT NULL,
            set_name               TEXT,
            reference_month        TEXT NOT NULL,
            compensation_count     INTEGER,
            compensation_value     REAL,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_tariff_facts (
            fact_id                TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            resolution_title       TEXT,
            valid_from             TEXT NOT NULL,
            valid_to               TEXT NOT NULL,
            tariff_base            TEXT,
            subgroup               TEXT,
            modality               TEXT,
            consumer_class         TEXT,
            consumer_subclass      TEXT,
            consumer_detail        TEXT,
            tariff_period          TEXT,
            accessing_agent        TEXT,
            unit                   TEXT NOT NULL,
            tusd_value             REAL,
            te_value               REAL,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    _ensure_columns(
        conn,
        "distribution_tariff_facts",
        {
            "consumer_class": "TEXT",
            "consumer_subclass": "TEXT",
            "accessing_agent": "TEXT",
        },
    )
    tariff_cols = {
        row[1] for row in conn.execute(text("PRAGMA table_info(distribution_tariff_facts)")).fetchall()
    }
    if "class_name" in tariff_cols:
        conn.execute(text(
            "UPDATE distribution_tariff_facts "
            "SET consumer_class = class_name "
            "WHERE consumer_class IS NULL AND class_name IS NOT NULL"
        ))
    if "subclass" in tariff_cols:
        conn.execute(text(
            "UPDATE distribution_tariff_facts "
            "SET consumer_subclass = subclass "
            "WHERE consumer_subclass IS NULL AND subclass IS NOT NULL"
        ))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_tariff_conflicts (
            conflict_row_id       TEXT PRIMARY KEY,
            business_key_hash     TEXT NOT NULL,
            normalized_cnpj       TEXT,
            raw_name              TEXT,
            resolution_title      TEXT,
            valid_from            TEXT,
            valid_to              TEXT,
            tariff_base           TEXT,
            subgroup              TEXT,
            modality              TEXT,
            consumer_class        TEXT,
            consumer_subclass     TEXT,
            consumer_detail       TEXT,
            tariff_period         TEXT,
            accessing_agent       TEXT,
            unit                  TEXT,
            tusd_value            REAL,
            te_value              REAL,
            source_row_hash       TEXT NOT NULL,
            snapshot_id           TEXT,
            conflict_reason       TEXT NOT NULL,
            created_at            TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_delinquency_facts (
            fact_id                TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            reference_month        TEXT NOT NULL,
            indicator_code         TEXT NOT NULL,
            actual_value           REAL,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_delinquency_indicators (
            indicator_code         TEXT PRIMARY KEY,
            indicator_name         TEXT NOT NULL,
            description            TEXT,
            unit                   TEXT,
            analytical_category    TEXT,
            publication_status     TEXT,
            is_lead_kpi            INTEGER NOT NULL DEFAULT 0
        )
    """))
    _ensure_columns(
        conn,
        "distribution_delinquency_indicators",
        {
            "unit": "TEXT",
            "analytical_category": "TEXT",
            "publication_status": "TEXT",
            "is_lead_kpi": "INTEGER NOT NULL DEFAULT 0",
        },
    )

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_mmgd_projects (
            project_id             TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            municipality           TEXT,
            uf                     TEXT,
            generation_type        TEXT,
            generation_source      TEXT,
            size_category          TEXT,
            latitude               REAL,
            longitude              REAL,
            connection_date        TEXT,
            status                 TEXT NOT NULL DEFAULT 'active',
            deactivated_at_month   TEXT,
            deactivation_reason    TEXT,
            deactivation_snapshot_id TEXT,
            source_row_hash        TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    _ensure_columns(
        conn,
        "distribution_mmgd_projects",
        {
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "deactivated_at_month": "TEXT",
            "deactivation_reason": "TEXT",
            "deactivation_snapshot_id": "TEXT",
            "source_row_hash": "TEXT",
        },
    )

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_mmgd_project_snapshots (
            snapshot_row_id        TEXT PRIMARY KEY,
            project_id             TEXT NOT NULL REFERENCES distribution_mmgd_projects(project_id) ON DELETE CASCADE,
            reference_month        TEXT NOT NULL,
            installed_capacity_kw  REAL,
            beneficiary_units_count INTEGER,
            source_row_hash        TEXT NOT NULL,
            snapshot_id            TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_monthly_aggregates (
            aggregate_id           TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            reference_month        TEXT NOT NULL,
            billed_energy_mwh      REAL,
            revenue_brl            REAL,
            measured_energy_mwh    REAL,
            injected_energy_mwh    REAL,
            losses_mwh             REAL,
            losses_pct             REAL,
            dec_actual             REAL,
            fec_actual             REAL,
            dec_limit              REAL,
            fec_limit              REAL,
            compensation_count     INTEGER,
            compensation_value     REAL,
            delinquency_pct        REAL,
            mmgd_projects_count    INTEGER,
            mmgd_capacity_kw       REAL,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_annual_aggregates (
            aggregate_id           TEXT PRIMARY KEY,
            distributor_id         TEXT NOT NULL REFERENCES distribution_distributors(distributor_id) ON DELETE CASCADE,
            reference_year         INTEGER NOT NULL,
            billed_energy_mwh      REAL,
            revenue_brl            REAL,
            measured_energy_mwh    REAL,
            injected_energy_mwh    REAL,
            losses_mwh             REAL,
            losses_pct             REAL,
            dec_actual             REAL,
            fec_actual             REAL,
            dec_limit              REAL,
            fec_limit              REAL,
            compensation_count     INTEGER,
            compensation_value     REAL,
            delinquency_pct        REAL,
            mmgd_projects_count    INTEGER,
            mmgd_capacity_kw       REAL,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))

    # Indexes for distribution analytics
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_market_ref ON distribution_market_facts(distributor_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_bal_ref ON distribution_energy_balance_facts(distributor_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_cont_ref ON distribution_continuity_facts(distributor_id, set_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_cont_indicator_ref ON "
        "distribution_continuity_facts(indicator_code, distributor_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_mmgd_proj ON distribution_mmgd_projects(distributor_id)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_mmgd_snap ON distribution_mmgd_project_snapshots(project_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_monthly_agg ON distribution_monthly_aggregates(distributor_id, reference_month)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_annual_agg ON distribution_annual_aggregates(distributor_id, reference_year)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_dist_tariff_series_lookup ON "
        "distribution_tariff_facts(distributor_id, subgroup, consumer_class, unit, valid_from, valid_to)"
    ))



def migrate_unmapped_distributors(conn) -> None:
    """Migrate facts associated with unmapped distributor IDs (e.g. unmapped_04895728000180)
    into canonical IDs (e.g. equatorial_pa) if a match is found in the newly seeded
    distributors or aliases. Also dynamically reclassifies existing unmapped/unresolved rows.
    """
    from src.energy_kpi.distribution.catalog import seed_distribution_static_data
    from src.energy_kpi.distribution.ingest import classify_distribution_entity
    seed_distribution_static_data(conn)

    # Reclassify any existing unmapped or unresolved distributor rows dynamically
    rows = conn.execute(text("""
        SELECT distributor_id, canonical_name, normalized_cnpj, status, classification
        FROM distribution_distributors
        WHERE distributor_id LIKE 'unmapped_%' OR distributor_id LIKE 'unresolved_%'
    """)).fetchall()
    for r in rows:
        dist_id, name, cnpj, status, classification = r
        new_class = classify_distribution_entity(name, cnpj)
        new_status = 'active' if new_class in ('distributor', 'unknown') else 'unresolved_source_entity'
        if new_class != classification or new_status != status:
            conn.execute(
                text("UPDATE distribution_distributors SET classification = :cls, status = :status WHERE distributor_id = :id"),
                {"cls": new_class, "status": new_status, "id": dist_id}
            )

    # Build target mapping (normalized_cnpj -> distributor_id)
    target_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors WHERE distributor_id NOT LIKE 'unmapped_%' AND distributor_id NOT LIKE 'unresolved_%'")).fetchall():
        if r[1]:
            target_map[r[1]] = r[0]

    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        target_map[r[1]] = r[0]

    # Find existing unmapped distributors
    unmapped_rows = conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors WHERE distributor_id LIKE 'unmapped_%'")).fetchall()

    # Tables to migrate
    tables_to_update = [
        "distribution_market_facts",
        "distribution_energy_balance_facts",
        "distribution_continuity_facts",
        "distribution_continuity_limits",
        "distribution_continuity_compensations",
        "distribution_tariff_facts",
        "distribution_delinquency_facts",
        "distribution_mmgd_projects",
    ]

    for unmapped_id, cnpj in unmapped_rows:
        if cnpj in target_map:
            target_id = target_map[cnpj]
            logger.info("Migrating facts from %s to canonical ID %s (%s)", unmapped_id, target_id, cnpj)
            for tbl in tables_to_update:
                try:
                    conn.execute(
                        text(f"UPDATE OR IGNORE {tbl} SET distributor_id = :target WHERE distributor_id = :unmapped"),
                        {"target": target_id, "unmapped": unmapped_id}
                    )
                    conn.execute(
                        text(f"DELETE FROM {tbl} WHERE distributor_id = :unmapped"),
                        {"unmapped": unmapped_id}
                    )
                except Exception as e:
                    logger.warning("Failed to migrate table %s for %s: %s", tbl, unmapped_id, e)

            # Finally delete the old unmapped distributor record
            conn.execute(
                text("DELETE FROM distribution_distributors WHERE distributor_id = :unmapped"),
                {"unmapped": unmapped_id}
            )


def ensure_energy_kpi_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        ensure_energy_kpi_tables_for_connection(conn)
        migrate_unmapped_distributors(conn)


@lru_cache(maxsize=1)
def _build_energy_kpi_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False, "timeout": 5.0})
    ensure_energy_kpi_tables(engine)
    return engine


def get_energy_kpi_engine(settings: AppSettings) -> Engine:
    """Return (and lazily create) the energy KPI SQLite engine.

    The engine is cached by DB URL. Tables are created on first access.
    The DB file is at settings.paths.energy_kpi_db_path — separate from
    cvm_financials.db to allow independent refresh and zero migration risk.
    """
    settings.paths.energy_kpi_db_path.parent.mkdir(parents=True, exist_ok=True)
    with _ENGINE_BUILD_LOCK:
        return _build_energy_kpi_engine(settings.paths.energy_kpi_sqlite_url)
