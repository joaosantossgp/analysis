"""Shared contract for large local-first analytical ingestions."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

StorageLayer = Literal[
    "metadata_sqlite",
    "raw_snapshot",
    "hot_sqlite",
    "cold_parquet",
    "mart_sqlite",
    "ui_cache",
]

DEFAULT_LINEAGE_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_url_or_path",
    "download_timestamp",
    "import_batch_id",
    "parser_version",
    "content_hash",
    "entity_id",
    "period",
    "frequency",
    "unit",
    "transformation_id",
)

REQUIRED_STORAGE_LAYERS: tuple[StorageLayer, ...] = (
    "metadata_sqlite",
    "mart_sqlite",
)


class ManagedStoreValidationError(ValueError):
    """Raised when a managed ingestion/storage contract is unsafe."""


@dataclass(frozen=True)
class ManagedStorePaths:
    base_dir: Path
    manifest_path: Path
    raw_dir: Path
    hot_dir: Path
    cold_dir: Path
    mart_dir: Path


@dataclass(frozen=True)
class ManagedDatasetContract:
    domain: str
    dataset_id: str
    fact_grain: str
    storage_layers: tuple[StorageLayer, ...]
    lineage_fields: tuple[str, ...]
    detail_reads_require_bounds: bool
    default_hot_partitions: int
    schema_version: int = 1

    def to_manifest_contract(self) -> dict[str, object]:
        return {
            "schema_version": int(self.schema_version),
            "domain": self.domain,
            "dataset_id": self.dataset_id,
            "fact_grain": self.fact_grain,
            "storage_layers": list(self.storage_layers),
            "lineage_fields": list(self.lineage_fields),
            "detail_reads_require_bounds": bool(self.detail_reads_require_bounds),
            "default_hot_partitions": int(self.default_hot_partitions),
        }


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower()).strip("_")
    if not normalized:
        raise ManagedStoreValidationError("managed storage identifiers must not be empty")
    return normalized


def managed_store_paths(data_dir: Path, *, domain: str, dataset_id: str) -> ManagedStorePaths:
    data_root = Path(data_dir).expanduser().resolve()
    base_dir = data_root / "analytics" / _slug(domain) / _slug(dataset_id)
    return ManagedStorePaths(
        base_dir=base_dir,
        manifest_path=base_dir / "manifest.json",
        raw_dir=base_dir / "raw",
        hot_dir=base_dir / "hot",
        cold_dir=base_dir / "cold",
        mart_dir=base_dir / "marts",
    )


def validate_contract(contract: ManagedDatasetContract) -> None:
    if contract.schema_version < 1:
        raise ManagedStoreValidationError("schema_version must be >= 1")
    if not contract.domain.strip():
        raise ManagedStoreValidationError("domain is required")
    if not contract.dataset_id.strip():
        raise ManagedStoreValidationError("dataset_id is required")
    if not contract.fact_grain.strip():
        raise ManagedStoreValidationError("fact_grain is required")
    layers = set(contract.storage_layers)
    missing_layers = [layer for layer in REQUIRED_STORAGE_LAYERS if layer not in layers]
    if missing_layers:
        raise ManagedStoreValidationError(f"missing storage layers: {', '.join(missing_layers)}")
    if not ({"hot_sqlite", "cold_parquet"} & layers):
        raise ManagedStoreValidationError("large facts require at least one managed analytical fact layer")
    missing_lineage = [field for field in DEFAULT_LINEAGE_FIELDS if field not in set(contract.lineage_fields)]
    if missing_lineage:
        raise ManagedStoreValidationError(f"missing lineage fields: {', '.join(missing_lineage)}")
    if not contract.detail_reads_require_bounds:
        raise ManagedStoreValidationError("managed analytical facts require bounded detail reads")
    if int(contract.default_hot_partitions) < 1:
        raise ManagedStoreValidationError("default_hot_partitions must be >= 1")


def validate_manifest_contract(manifest: dict, expected: ManagedDatasetContract) -> None:
    validate_contract(expected)
    raw_contract = manifest.get("contract")
    if not isinstance(raw_contract, dict):
        raise ManagedStoreValidationError("manifest is missing contract")

    expected_payload = expected.to_manifest_contract()
    for field in ("domain", "dataset_id", "fact_grain"):
        if raw_contract.get(field) != expected_payload[field]:
            raise ManagedStoreValidationError(
                f"manifest contract {field}={raw_contract.get(field)!r} does not match "
                f"expected {expected_payload[field]!r}"
            )

    for field in ("storage_layers", "lineage_fields"):
        actual = tuple(str(value) for value in raw_contract.get(field, []))
        expected_values = tuple(str(value) for value in expected_payload[field])  # type: ignore[index]
        missing = [value for value in expected_values if value not in set(actual)]
        if missing:
            raise ManagedStoreValidationError(f"manifest contract {field} missing: {', '.join(missing)}")

    if bool(raw_contract.get("detail_reads_require_bounds")) is not True:
        raise ManagedStoreValidationError("manifest contract must require bounded detail reads")
    if int(raw_contract.get("default_hot_partitions") or 0) < 1:
        raise ManagedStoreValidationError("manifest contract default_hot_partitions must be >= 1")
