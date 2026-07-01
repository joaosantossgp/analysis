from __future__ import annotations

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
    from src.platform.managed_ingestion_registry import registered_managed_dataset_contracts

    contracts = registered_managed_dataset_contracts()
    dataset_ids = [contract.dataset_id for contract in contracts]

    assert "ccee_plant_generation_hourly" in dataset_ids
    assert "distribution_mmgd_projects" in dataset_ids
    assert len(dataset_ids) == len(set(dataset_ids))
    for contract in contracts:
        validate_contract(contract)


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
