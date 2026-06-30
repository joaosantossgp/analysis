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
