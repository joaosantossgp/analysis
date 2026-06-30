"""Managed storage for ANEEL MMGD distributed-generation project detail."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import text

from src.platform.managed_ingestion_contract import (
    DEFAULT_LINEAGE_FIELDS,
    ManagedDatasetContract,
    managed_store_paths,
    validate_manifest_contract,
    validate_contract,
)

MMGD_DATASET_ID = "distribution_mmgd_projects"

MMGD_CONTRACT = ManagedDatasetContract(
    domain="energy",
    dataset_id=MMGD_DATASET_ID,
    fact_grain="project_reference_month",
    storage_layers=("metadata_sqlite", "raw_snapshot", "cold_parquet", "mart_sqlite"),
    lineage_fields=DEFAULT_LINEAGE_FIELDS,
    detail_reads_require_bounds=True,
    default_hot_partitions=1,
)


def ensure_mmgd_managed_tables(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS managed_dataset_catalog (
            dataset_id       TEXT PRIMARY KEY,
            domain           TEXT NOT NULL,
            manifest_path    TEXT NOT NULL,
            base_path        TEXT NOT NULL,
            row_count        INTEGER NOT NULL,
            partition_count  INTEGER NOT NULL,
            contract_json    TEXT NOT NULL,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS distribution_mmgd_monthly_mart (
            distributor_id       TEXT NOT NULL,
            reference_month      TEXT NOT NULL,
            mmgd_projects_count  INTEGER NOT NULL,
            mmgd_capacity_kw     REAL,
            source_snapshot_id   TEXT,
            source_row_count     INTEGER NOT NULL,
            updated_at           TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (distributor_id, reference_month)
        )
    """))


def _manifest_payload(
    *,
    base_dir: Path,
    snapshot_id: str,
    row_count: int,
    partitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_id": MMGD_DATASET_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "contract": MMGD_CONTRACT.to_manifest_contract(),
        "storage": {
            "base_dir": str(base_dir),
            "format": "parquet",
            "partitioning": ["reference_month"],
        },
        "selection": {
            "snapshot_id": snapshot_id,
            "full_snapshot": True,
        },
        "validation": {
            "ok": True,
            "row_count": row_count,
        },
        "partitions": partitions,
    }


def persist_mmgd_snapshot_to_managed_store(
    *,
    data_dir: Path,
    conn,
    frame: pl.DataFrame,
    snapshot_id: str,
) -> dict[str, Any]:
    """Persist parsed MMGD detail to Parquet and compact SQLite marts."""
    validate_contract(MMGD_CONTRACT)
    ensure_mmgd_managed_tables(conn)

    if frame.height == 0:
        return {"row_count": 0, "partitions": []}
    if "reference_month" not in frame.columns:
        raise ValueError("MMGD managed storage requires reference_month")
    if "distributor_id" not in frame.columns:
        raise ValueError("MMGD managed storage requires distributor_id")

    paths = managed_store_paths(data_dir, domain=MMGD_CONTRACT.domain, dataset_id=MMGD_CONTRACT.dataset_id)
    detail_root = paths.cold_dir / "mmgd_project_detail"
    detail_root.mkdir(parents=True, exist_ok=True)

    months = sorted(str(value) for value in frame.select("reference_month").unique().to_series().to_list())
    partitions: list[dict[str, Any]] = []
    for month in months:
        part_frame = frame.filter(pl.col("reference_month") == month).sort("project_id")
        partition_dir = detail_root / f"reference_month={month}"
        if partition_dir.exists():
            shutil.rmtree(partition_dir)
        partition_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = partition_dir / f"part-{snapshot_id}.parquet"
        part_frame.write_parquet(parquet_path, compression="zstd")
        partitions.append(
            {
                "reference_month": month,
                "row_count": part_frame.height,
                "path": str(parquet_path),
                "bytes": parquet_path.stat().st_size,
            }
        )

    mart_frame = (
        frame.group_by(["distributor_id", "reference_month"])
        .agg(
            [
                pl.len().alias("mmgd_projects_count"),
                pl.col("installed_capacity_kw").sum().alias("mmgd_capacity_kw"),
            ]
        )
        .sort(["distributor_id", "reference_month"])
    )
    for month in months:
        conn.execute(
            text("DELETE FROM distribution_mmgd_monthly_mart WHERE reference_month = :month"),
            {"month": month},
        )
    conn.execute(
        text("""
            INSERT INTO distribution_mmgd_monthly_mart (
                distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw,
                source_snapshot_id, source_row_count, updated_at
            )
            VALUES (
                :distributor_id, :reference_month, :mmgd_projects_count, :mmgd_capacity_kw,
                :source_snapshot_id, :source_row_count, datetime('now')
            )
        """),
        [
            {
                **row,
                "source_snapshot_id": snapshot_id,
                "source_row_count": int(row["mmgd_projects_count"]),
            }
            for row in mart_frame.to_dicts()
        ],
    )

    manifest = _manifest_payload(
        base_dir=paths.base_dir,
        snapshot_id=snapshot_id,
        row_count=frame.height,
        partitions=partitions,
    )
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    paths.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    conn.execute(
        text("""
            INSERT INTO managed_dataset_catalog (
                dataset_id, domain, manifest_path, base_path, row_count,
                partition_count, contract_json, updated_at
            )
            VALUES (
                :dataset_id, :domain, :manifest_path, :base_path, :row_count,
                :partition_count, :contract_json, datetime('now')
            )
            ON CONFLICT(dataset_id) DO UPDATE SET
                domain = excluded.domain,
                manifest_path = excluded.manifest_path,
                base_path = excluded.base_path,
                row_count = excluded.row_count,
                partition_count = excluded.partition_count,
                contract_json = excluded.contract_json,
                updated_at = datetime('now')
        """),
        {
            "dataset_id": MMGD_DATASET_ID,
            "domain": MMGD_CONTRACT.domain,
            "manifest_path": str(paths.manifest_path),
            "base_path": str(paths.base_dir),
            "row_count": int(frame.height),
            "partition_count": len(partitions),
            "contract_json": json.dumps(MMGD_CONTRACT.to_manifest_contract(), sort_keys=True),
        },
    )
    return {
        "base_dir": str(paths.base_dir),
        "manifest_path": str(paths.manifest_path),
        "row_count": int(frame.height),
        "partitions": partitions,
    }


def _require_bounded_detail(distributor_id: str | None, reference_month: str | None) -> tuple[str, str]:
    distributor = str(distributor_id or "").strip()
    month = str(reference_month or "").strip()
    if not distributor or not month:
        raise ValueError("MMGD detail reads require distributor_id and reference_month")
    return distributor, month


def _read_valid_manifest(data_dir: Path) -> dict[str, Any]:
    paths = managed_store_paths(data_dir, domain=MMGD_CONTRACT.domain, dataset_id=MMGD_CONTRACT.dataset_id)
    if not paths.manifest_path.exists():
        raise FileNotFoundError(f"MMGD managed manifest not found: {paths.manifest_path}")
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    validate_manifest_contract(manifest, MMGD_CONTRACT)
    if manifest.get("dataset_id") != MMGD_DATASET_ID:
        raise ValueError(f"Unexpected MMGD manifest dataset_id: {manifest.get('dataset_id')!r}")
    validation = manifest.get("validation")
    if not isinstance(validation, dict) or validation.get("ok") is not True:
        raise ValueError("MMGD managed manifest validation is not ok")
    return manifest


def _safe_limit(limit: int | None) -> int:
    if limit is None:
        return 500
    return max(1, min(int(limit), 5_000))


def read_mmgd_project_detail(
    *,
    data_dir: Path,
    distributor_id: str | None,
    reference_month: str | None,
    limit: int | None = 500,
) -> dict[str, Any]:
    """Read bounded MMGD project detail from managed Parquet partitions."""
    distributor, month = _require_bounded_detail(distributor_id, reference_month)
    bounded_limit = _safe_limit(limit)
    manifest = _read_valid_manifest(Path(data_dir))
    partitions = [
        partition
        for partition in manifest.get("partitions", [])
        if isinstance(partition, dict) and str(partition.get("reference_month")) == month
    ]
    parquet_paths = [str(partition.get("path")) for partition in partitions if partition.get("path")]
    existing_paths = [path for path in parquet_paths if Path(path).exists()]
    if not existing_paths:
        return {
            "source": "managed_parquet",
            "dataset_id": MMGD_DATASET_ID,
            "manifest_path": str(managed_store_paths(Path(data_dir), domain=MMGD_CONTRACT.domain, dataset_id=MMGD_CONTRACT.dataset_id).manifest_path),
            "distributor_id": distributor,
            "reference_month": month,
            "rows": [],
            "count": 0,
            "total_matching_rows": 0,
            "truncated": False,
        }

    scan = pl.scan_parquet(existing_paths).filter(pl.col("distributor_id") == distributor)
    total_matching = int(scan.select(pl.len()).collect().item())
    frame = scan.sort("project_id").limit(bounded_limit).collect()
    sensitive_columns = {"normalized_cnpj", "raw_name"}
    rows = [
        {key: value for key, value in row.items() if key not in sensitive_columns}
        for row in frame.to_dicts()
    ]
    return {
        "source": "managed_parquet",
        "dataset_id": MMGD_DATASET_ID,
        "manifest_path": str(managed_store_paths(Path(data_dir), domain=MMGD_CONTRACT.domain, dataset_id=MMGD_CONTRACT.dataset_id).manifest_path),
        "distributor_id": distributor,
        "reference_month": month,
        "rows": rows,
        "count": len(rows),
        "total_matching_rows": total_matching,
        "truncated": total_matching > len(rows),
    }
