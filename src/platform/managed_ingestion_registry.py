"""Registry for large local-first managed ingestion contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.energy_kpi.distribution.mmgd_store import MMGD_CONTRACT
from src.energy_kpi.hourly_store_ingest import CCEE_HOURLY_CONTRACT
from src.platform.managed_ingestion_contract import DEFAULT_LINEAGE_FIELDS, ManagedDatasetContract

ManagedDatasetStatus = Literal["implemented", "planned"]
SqliteTableClassification = Literal[
    "managed_externalized",
    "sqlite_mart",
    "small_relational",
    "accepted_row_store",
]


@dataclass(frozen=True)
class ManagedSqliteTable:
    database: str
    table_name: str
    classification: SqliteTableClassification
    notes: str


@dataclass(frozen=True)
class ManagedDatasetRegistration:
    status: ManagedDatasetStatus
    contract: ManagedDatasetContract
    manifest_required: bool
    sqlite_tables: tuple[ManagedSqliteTable, ...]
    notes: str


FUEL_DISTRIBUTION_INTAKE_CONTRACT = ManagedDatasetContract(
    domain="energy",
    dataset_id="fuel_distribution_sector_intake",
    fact_grain="fuel-distribution entity-period detail",
    storage_layers=("metadata_sqlite", "raw_snapshot", "cold_parquet", "mart_sqlite"),
    lineage_fields=DEFAULT_LINEAGE_FIELDS,
    detail_reads_require_bounds=True,
    default_hot_partitions=1,
)

_CORE_SQLITE_TABLES: tuple[ManagedSqliteTable, ...] = (
    ManagedSqliteTable(
        database="cvm_financials.db",
        table_name="financial_reports",
        classification="accepted_row_store",
        notes="Core CVM financial statement row store; not a high-frequency sector feed.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="subsystem_kpi_values",
        classification="accepted_row_store",
        notes="Current SIN KPI relational observations; accepted until a future size profile requires externalization.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_market_facts",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_continuity_facts",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_delinquency_facts",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_energy_balance_facts",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_continuity_compensations",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_continuity_limits",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
    ManagedSqliteTable(
        database="energy_kpis.db",
        table_name="distribution_tariff_facts",
        classification="accepted_row_store",
        notes="Current electricity distribution relational fact table below main DB budget.",
    ),
)


def registered_managed_datasets() -> tuple[ManagedDatasetRegistration, ...]:
    """Return implemented and planned managed-ingestion dataset registrations."""
    return (
        ManagedDatasetRegistration(
            status="implemented",
            contract=CCEE_HOURLY_CONTRACT,
            manifest_required=True,
            sqlite_tables=(
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="ccee_plant_parcel_hourly",
                    classification="managed_externalized",
                    notes="Large hourly detail is externalized to the managed hot/cold store.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="plant_parcel_daily_generation_mart",
                    classification="sqlite_mart",
                    notes="Rebuildable daily mart for app chart reads.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="plant_parcel_hourly_preview_mart",
                    classification="sqlite_mart",
                    notes="Rebuildable compact preview mart for hourly detail.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="plant_ceg_hourly_generation_mart",
                    classification="sqlite_mart",
                    notes="Rebuildable CEG-level hourly mart.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="plant_parcel_source_submarket_monthly_mart",
                    classification="sqlite_mart",
                    notes="Rebuildable source/submarket monthly mart.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="external_hourly_store_catalog",
                    classification="small_relational",
                    notes="Catalog fingerprint for the managed hourly store.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="energy_mart_builds",
                    classification="small_relational",
                    notes="Mart rebuild audit metadata.",
                ),
            ),
            notes="CCEE hourly plant-parcel facts use managed hot SQLite plus cold Parquet.",
        ),
        ManagedDatasetRegistration(
            status="implemented",
            contract=MMGD_CONTRACT,
            manifest_required=True,
            sqlite_tables=(
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="distribution_mmgd_projects",
                    classification="managed_externalized",
                    notes="Legacy MMGD project dimension table is empty after externalization.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="distribution_mmgd_project_snapshots",
                    classification="managed_externalized",
                    notes="MMGD project-month detail is externalized to managed Parquet.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="distribution_mmgd_monthly_mart",
                    classification="sqlite_mart",
                    notes="Compact monthly MMGD summary for app reads.",
                ),
                ManagedSqliteTable(
                    database="energy_kpis.db",
                    table_name="managed_dataset_catalog",
                    classification="small_relational",
                    notes="Catalog metadata for managed analytical datasets.",
                ),
            ),
            notes="ANEEL MMGD project detail uses managed Parquet with bounded distributor/month reads.",
        ),
        ManagedDatasetRegistration(
            status="planned",
            contract=FUEL_DISTRIBUTION_INTAKE_CONTRACT,
            manifest_required=False,
            sqlite_tables=(),
            notes="Planned Energy/Fuel Distribution intake; source discovery and sizing must happen before importer work.",
        ),
    )


def registered_sqlite_table_classifications() -> tuple[ManagedSqliteTable, ...]:
    """Return explicit table classifications used by large-table validation."""
    dataset_tables = tuple(
        table
        for registration in registered_managed_datasets()
        for table in registration.sqlite_tables
    )
    return _CORE_SQLITE_TABLES + dataset_tables


def registered_managed_dataset_contracts() -> tuple[ManagedDatasetContract, ...]:
    """Return implemented large-fact managed storage contracts."""
    return (
        tuple(
            registration.contract
            for registration in registered_managed_datasets()
            if registration.status == "implemented"
        )
    )
