from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.platform.managed_ingestion_contract import (
    DEFAULT_LINEAGE_FIELDS,
    ManagedDatasetContract,
    ManagedStoreValidationError,
    managed_store_paths,
    validate_contract,
    validate_manifest_contract,
)


def test_registered_managed_dataset_contracts_are_unique_and_valid():
    from src.platform.managed_ingestion_registry import (
        registered_managed_dataset_contracts,
        registered_managed_datasets,
    )

    contracts = registered_managed_dataset_contracts()
    dataset_ids = [contract.dataset_id for contract in contracts]

    assert "ccee_plant_generation_hourly" in dataset_ids
    assert "distribution_mmgd_projects" in dataset_ids
    assert "fuel_distribution_sector_intake" in dataset_ids
    assert len(dataset_ids) == len(set(dataset_ids))
    for contract in contracts:
        validate_contract(contract)

    registrations = registered_managed_datasets()
    registration_ids = [registration.contract.dataset_id for registration in registrations]
    fuel_registration = next(
        registration
        for registration in registrations
        if registration.contract.dataset_id == "fuel_distribution_sector_intake"
    )
    assert "fuel_distribution_sector_intake" in registration_ids
    assert fuel_registration.status == "implemented"
    assert fuel_registration.manifest_required is True
    assert fuel_registration.contract.domain == "energy"
    assert fuel_registration.contract.fact_grain == "fuel-sales source-geography-product-period detail"
    assert "cold_parquet" in fuel_registration.contract.storage_layers
    assert {table.table_name for table in fuel_registration.sqlite_tables} == {
        "fuel_distribution_product_year_mart"
    }


def test_managed_ingestion_contract_report_can_require_manifests(tmp_path: Path):
    from scripts.data.check_managed_ingestion_contracts import build_managed_ingestion_contract_report

    contract = ManagedDatasetContract(
        domain="energy",
        dataset_id="future_heavy_sector_fact",
        fact_grain="entity-period detail",
        storage_layers=("metadata_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS,
        detail_reads_require_bounds=True,
        default_hot_partitions=1,
    )

    warning_report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        contracts=(contract,),
        require_manifests=False,
    )
    assert warning_report["ok"] is True
    assert warning_report["warnings"][0]["check"] == "manifest_missing"

    failure_report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        contracts=(contract,),
        require_manifests=True,
    )
    assert failure_report["ok"] is False
    assert failure_report["failures"][0]["check"] == "manifest_missing"


def test_managed_ingestion_contract_report_accepts_planned_without_manifest(tmp_path: Path):
    from scripts.data.check_managed_ingestion_contracts import build_managed_ingestion_contract_report
    from src.platform.managed_ingestion_registry import (
        ManagedDatasetRegistration,
    )

    contract = ManagedDatasetContract(
        domain="energy",
        dataset_id="future_heavy_sector_intake",
        fact_grain="entity-period detail",
        storage_layers=("metadata_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS,
        detail_reads_require_bounds=True,
        default_hot_partitions=1,
    )
    planned = ManagedDatasetRegistration(
        status="planned",
        contract=contract,
        manifest_required=False,
        sqlite_tables=(),
        notes="Synthetic planned registration for validation coverage.",
    )
    report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        registrations=(planned,),
        require_manifests=True,
    )

    assert report["ok"] is True
    assert report["implemented_contracts"] == []
    assert report["planned_contracts"][0]["dataset_id"] == "future_heavy_sector_intake"

    duplicate = ManagedDatasetRegistration(
        status=planned.status,
        contract=planned.contract,
        manifest_required=planned.manifest_required,
        sqlite_tables=planned.sqlite_tables,
        notes=planned.notes,
    )
    duplicate_report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        registrations=(planned, duplicate),
        require_manifests=True,
    )
    assert duplicate_report["ok"] is False
    assert duplicate_report["failures"][0]["check"] == "duplicate_dataset_id"


def test_strict_sqlite_large_table_scan_fails_unclassified_table(tmp_path: Path):
    from scripts.data.check_managed_ingestion_contracts import build_managed_ingestion_contract_report

    db_path = tmp_path / "energy_kpis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE future_heavy_fact (id INTEGER PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO future_heavy_fact (value) VALUES (?)",
            [("a",), ("b",), ("c",)],
        )

    report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        registrations=(),
        require_manifests=True,
        scan_sqlite_large_tables=True,
        sqlite_database_paths=(db_path,),
        sqlite_row_threshold=2,
    )

    assert report["ok"] is False
    assert report["sqlite_large_tables"][0]["table_name"] == "future_heavy_fact"
    assert report["unclassified_large_tables"][0]["table_name"] == "future_heavy_fact"
    assert report["failures"][0]["check"] == "sqlite_large_table_unclassified"


def test_strict_sqlite_large_table_scan_accepts_registered_table(tmp_path: Path):
    from scripts.data.check_managed_ingestion_contracts import build_managed_ingestion_contract_report

    db_path = tmp_path / "cvm_financials.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE financial_reports (id INTEGER PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO financial_reports (value) VALUES (?)",
            [("a",), ("b",), ("c",)],
        )

    report = build_managed_ingestion_contract_report(
        data_dir=tmp_path,
        registrations=(),
        require_manifests=True,
        scan_sqlite_large_tables=True,
        sqlite_database_paths=(db_path,),
        sqlite_row_threshold=2,
    )

    assert report["ok"] is True
    assert report["sqlite_large_tables"][0]["classification"] == "accepted_row_store"
    assert report["unclassified_large_tables"] == []


def test_managed_dataset_contract_requires_lineage_and_bounded_detail_reads():
    contract = ManagedDatasetContract(
        domain="energy",
        dataset_id="ccee_hourly",
        fact_grain="plant-parcel hour",
        storage_layers=("metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS[:-1],
        detail_reads_require_bounds=False,
        default_hot_partitions=2,
    )

    with pytest.raises(ManagedStoreValidationError, match="missing lineage fields"):
        validate_contract(contract)

    complete_lineage = ManagedDatasetContract(
        domain="energy",
        dataset_id="ccee_hourly",
        fact_grain="plant-parcel hour",
        storage_layers=("metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS,
        detail_reads_require_bounds=False,
        default_hot_partitions=2,
    )
    with pytest.raises(ManagedStoreValidationError, match="bounded detail reads"):
        validate_contract(complete_lineage)


def test_managed_store_paths_are_sanitized_under_data_root(tmp_path: Path):
    paths = managed_store_paths(tmp_path, domain="Energy Sector", dataset_id="../CCEE Hourly")

    assert paths.base_dir == tmp_path / "analytics" / "energy_sector" / "ccee_hourly"
    assert paths.manifest_path == paths.base_dir / "manifest.json"
    assert paths.hot_dir == paths.base_dir / "hot"
    assert paths.cold_dir == paths.base_dir / "cold"


def test_manifest_contract_validation_accepts_required_shape():
    contract = ManagedDatasetContract(
        domain="energy",
        dataset_id="ccee_plant_generation_hourly",
        fact_grain="plant-parcel hour",
        storage_layers=("metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS,
        detail_reads_require_bounds=True,
        default_hot_partitions=2,
    )
    manifest = {
        "schema_version": 1,
        "contract": {
            "domain": "energy",
            "dataset_id": "ccee_plant_generation_hourly",
            "fact_grain": "plant-parcel hour",
            "storage_layers": ["metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"],
            "lineage_fields": list(DEFAULT_LINEAGE_FIELDS),
            "detail_reads_require_bounds": True,
            "default_hot_partitions": 2,
        },
    }

    validate_manifest_contract(manifest, contract)


def test_manifest_contract_validation_rejects_dataset_mismatch():
    contract = ManagedDatasetContract(
        domain="energy",
        dataset_id="ccee_plant_generation_hourly",
        fact_grain="plant-parcel hour",
        storage_layers=("metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"),
        lineage_fields=DEFAULT_LINEAGE_FIELDS,
        detail_reads_require_bounds=True,
        default_hot_partitions=2,
    )
    manifest = {
        "schema_version": 1,
        "contract": {
            "domain": "energy",
            "dataset_id": "other_dataset",
            "fact_grain": "plant-parcel hour",
            "storage_layers": ["metadata_sqlite", "hot_sqlite", "cold_parquet", "mart_sqlite"],
            "lineage_fields": list(DEFAULT_LINEAGE_FIELDS),
            "detail_reads_require_bounds": True,
            "default_hot_partitions": 2,
        },
    }

    with pytest.raises(ManagedStoreValidationError, match="dataset_id"):
        validate_manifest_contract(manifest, contract)
