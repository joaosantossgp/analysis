"""Incremental ingestion helpers for the managed CCEE hourly store."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.energy_kpi.plant_marts import rebuild_plant_hourly_marts
from src.platform.managed_ingestion_contract import (
    DEFAULT_LINEAGE_FIELDS,
    ManagedDatasetContract,
    validate_manifest_contract,
)
from src.platform.settings import AppSettings

HOURLY_TABLE = "ccee_plant_parcel_hourly"
CATALOG_TABLE = "external_hourly_store_catalog"
MANIFEST_RELATIVE_PATH = Path("analytics") / "energy" / "ccee_plant_generation_hourly" / "manifest.json"
DEFAULT_MAX_HOT_MONTHS = 2
DEFAULT_COLD_PARQUET_CHUNK_SIZE = 100_000
CCEE_HOURLY_CONTRACT = ManagedDatasetContract(
    domain="energy",
    dataset_id="ccee_plant_generation_hourly",
    fact_grain="plant-parcel hour",
    storage_layers=("metadata_sqlite", "raw_snapshot", "hot_sqlite", "cold_parquet", "mart_sqlite"),
    lineage_fields=DEFAULT_LINEAGE_FIELDS,
    detail_reads_require_bounds=True,
    default_hot_partitions=DEFAULT_MAX_HOT_MONTHS,
)
HOT_STORE_EXTRA_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_cppe_hot_parcel_month_datetime
ON ccee_plant_parcel_hourly (
    plant_parcel_code,
    reference_month,
    reference_datetime,
    commercialization_period
)
"""


def persist_ccee_hourly_to_managed_store(settings: AppSettings, conn, frame: pd.DataFrame) -> dict[str, Any] | None:
    """Persist CCEE hourly rows to the managed hot store when the DB is compacted.

    Returns ``None`` when the database has not been migrated to the external
    hourly store yet. In that case callers should use the legacy SQLite upsert.
    """
    if frame.empty:
        return None
    catalog = _load_catalog(conn)
    if catalog is None:
        return None
    if _main_hourly_has_rows(conn):
        raise RuntimeError(
            "External hourly store catalog is present, but ccee_plant_parcel_hourly still has rows. "
            "Refusing to import into two raw hourly stores."
        )

    manifest_path = Path(str(catalog["manifest_path"])).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = (settings.paths.data_dir / MANIFEST_RELATIVE_PATH).resolve()
    manifest_path = manifest_path.resolve()
    manifest = _load_manifest(manifest_path)
    _validate_catalog_matches_manifest(catalog, manifest)

    months = _frame_months(frame)
    storage_before = _storage_snapshot(
        settings=settings,
        manifest=manifest,
        manifest_path=manifest_path,
        hot_path=_hot_db_path(manifest),
    )
    hot_write = _write_hot_sqlite(manifest, frame, months)
    rollover = _roll_hot_months_to_cold(manifest, hot_write["hot_path"], months)
    mart_rebuild = _rebuild_marts_from_frame(conn, frame, months)
    updated_manifest = _updated_manifest(
        manifest,
        manifest_path,
        months,
        rollover["hot_counts"],
        rollover["cold_partitions"],
        rollover["hot_months"],
        rollover["cold_months"],
    )
    _write_manifest(manifest_path, updated_manifest)
    _write_catalog(conn, settings, manifest_path, updated_manifest)
    storage_after = _storage_snapshot(
        settings=settings,
        manifest=updated_manifest,
        manifest_path=manifest_path,
        hot_path=hot_write["hot_path"],
    )
    storage_telemetry = {
        "mode": "managed_hourly_store",
        "dataset": HOURLY_TABLE,
        "reference_months": months,
        "rolled_to_cold_months": rollover["rolled_to_cold_months"],
        "before": storage_before,
        "after": storage_after,
        "mart_rebuild": mart_rebuild,
    }
    return {
        "used_external_store": True,
        "rows_inserted": int(len(frame)),
        "reference_months": months,
        "manifest_path": str(manifest_path),
        "hot_months": rollover["hot_months"],
        "cold_months": rollover["cold_months"],
        "rolled_to_cold_months": rollover["rolled_to_cold_months"],
        "storage_telemetry": storage_telemetry,
        "mart_rebuild": mart_rebuild,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_catalog(conn) -> dict[str, Any] | None:
    exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {"table_name": CATALOG_TABLE},
    ).scalar()
    if not exists:
        return None
    row = conn.execute(
        text(f"""
            SELECT dataset, manifest_path, manifest_fingerprint, source_database,
                   full_months, manifest_row_count, available_months_json
            FROM {CATALOG_TABLE}
            WHERE dataset = :dataset
        """),
        {"dataset": HOURLY_TABLE},
    ).mappings().first()
    return dict(row) if row else None


def _main_hourly_has_rows(conn) -> bool:
    exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table_name"),
        {"table_name": HOURLY_TABLE},
    ).scalar()
    if not exists:
        return False
    return conn.execute(text(f"SELECT 1 FROM main.{HOURLY_TABLE} LIMIT 1")).scalar() is not None


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"Managed hourly store manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("selection", {}).get("full_months") is not True:
        raise ValueError(f"Managed hourly store manifest is not marked as full-month data: {manifest_path}")
    if manifest.get("validation", {}).get("ok") is not True:
        raise ValueError(f"Managed hourly store manifest is not valid: {manifest_path}")
    if "contract" in manifest:
        validate_manifest_contract(manifest, CCEE_HOURLY_CONTRACT)
    return manifest


def repair_ccee_hourly_manifest_contract(
    settings: AppSettings,
    conn,
    *,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Add the hourly managed-store contract to a valid legacy manifest."""
    resolved_manifest_path = Path(manifest_path or (settings.paths.data_dir / MANIFEST_RELATIVE_PATH)).resolve()
    manifest = _load_manifest(resolved_manifest_path)
    if "contract" in manifest:
        validate_manifest_contract(manifest, CCEE_HOURLY_CONTRACT)
        return {
            "dataset_id": CCEE_HOURLY_CONTRACT.dataset_id,
            "manifest_path": str(resolved_manifest_path),
            "repaired": False,
        }

    manifest["contract"] = CCEE_HOURLY_CONTRACT.to_manifest_contract()
    validate_manifest_contract(manifest, CCEE_HOURLY_CONTRACT)
    _write_manifest(resolved_manifest_path, manifest)
    _write_catalog(conn, settings, resolved_manifest_path, manifest)
    return {
        "dataset_id": CCEE_HOURLY_CONTRACT.dataset_id,
        "manifest_path": str(resolved_manifest_path),
        "repaired": True,
    }


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in manifest.get("selection", {}).get("available_months") or []:
        month = str(row.get("reference_month") or "").strip()
        if month:
            counts[month] = int(row.get("row_count") or 0)
    return counts


def _path_size(path: Path | None) -> int:
    if path is None:
        return 0
    try:
        return int(path.stat().st_size) if path.exists() else 0
    except OSError:
        return 0


def _sqlite_sidecar_bytes(path: Path) -> int:
    return sum(_path_size(path.with_name(path.name + suffix)) for suffix in ("-wal", "-shm", "-journal"))


def _cold_parquet_bytes(manifest: dict[str, Any]) -> int:
    total = 0
    for partition in manifest.get("artifacts", {}).get("cold", {}).get("partitions", []) or []:
        for part in partition.get("parts", []) or []:
            raw_path = part.get("path")
            total += _path_size(Path(str(raw_path)).expanduser()) if raw_path else int(part.get("size_bytes") or 0)
    return total


def _storage_snapshot(
    *,
    settings: AppSettings,
    manifest: dict[str, Any],
    manifest_path: Path,
    hot_path: Path,
) -> dict[str, Any]:
    counts = _manifest_counts(manifest)
    hot_months = [str(month) for month in manifest.get("selection", {}).get("hot_months", [])]
    cold_months = [str(month) for month in manifest.get("selection", {}).get("cold_months", [])]
    db_path = Path(settings.paths.energy_kpi_db_path).expanduser()
    return {
        "main_database_bytes": _path_size(db_path),
        "main_database_sidecar_bytes": _sqlite_sidecar_bytes(db_path),
        "hot_sqlite_bytes": _path_size(hot_path),
        "hot_sqlite_sidecar_bytes": _sqlite_sidecar_bytes(hot_path),
        "cold_parquet_bytes": _cold_parquet_bytes(manifest),
        "manifest_bytes": _path_size(manifest_path),
        "manifest_row_count": sum(counts.values()),
        "hot_month_count": len(hot_months),
        "cold_month_count": len(cold_months),
        "hot_months": hot_months,
        "cold_months": cold_months,
    }


def _validate_catalog_matches_manifest(catalog: dict[str, Any], manifest: dict[str, Any]) -> None:
    counts = _manifest_counts(manifest)
    try:
        catalog_counts = json.loads(str(catalog.get("available_months_json") or "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("External hourly store catalog has invalid month-count JSON.") from exc
    normalized_counts = {str(month): int(count or 0) for month, count in dict(catalog_counts).items()}
    if str(catalog.get("manifest_fingerprint") or "") != _manifest_fingerprint(manifest):
        raise ValueError("External hourly store catalog does not match the managed hourly store manifest.")
    if int(catalog.get("full_months") or 0) != 1:
        raise ValueError("External hourly store catalog is not marked as full-month data.")
    if int(catalog.get("manifest_row_count") or 0) != sum(counts.values()):
        raise ValueError("External hourly store catalog row count does not match the manifest.")
    if normalized_counts != counts:
        raise ValueError("External hourly store catalog month counts do not match the manifest.")


def _frame_months(frame: pd.DataFrame) -> list[str]:
    months = sorted({str(value) for value in frame["reference_month"].dropna().unique() if str(value).strip()})
    if not months:
        raise ValueError("CCEE hourly import has no reference_month values.")
    return months


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _hot_db_path(manifest: dict[str, Any]) -> Path:
    raw_path = manifest.get("artifacts", {}).get("hot", {}).get("path")
    if not raw_path:
        raise ValueError("Managed hourly store manifest does not include artifacts.hot.path.")
    path = Path(str(raw_path)).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Managed hourly hot SQLite store not found: {path}")
    return path


def _sqlite_columns(sqlite_conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = sqlite_conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    columns = [str(row[1]) for row in rows]
    if not columns:
        raise ValueError(f"Managed hourly hot SQLite store is missing table: {table_name}")
    return columns


def _frame_records(frame: pd.DataFrame, columns: list[str]) -> list[tuple[Any, ...]]:
    prepared = frame.copy()
    if "updated_at" in columns and "updated_at" not in prepared.columns:
        prepared["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prepared = prepared[[column for column in columns if column in prepared.columns]]
    prepared = prepared.astype(object).where(pd.notna(prepared), None)
    return [tuple(row) for row in prepared.itertuples(index=False, name=None)]


def _write_hot_sqlite(manifest: dict[str, Any], frame: pd.DataFrame, months: list[str]) -> dict[str, Any]:
    hot_path = _hot_db_path(manifest)
    with closing(sqlite3.connect(hot_path, timeout=30)) as hot_conn:
        columns = _sqlite_columns(hot_conn, HOURLY_TABLE)
        insert_columns = [column for column in columns if column in frame.columns or column == "updated_at"]
        placeholders = ", ".join("?" for _ in insert_columns)
        insert_sql = (
            f"INSERT OR REPLACE INTO {_quote_identifier(HOURLY_TABLE)} "
            f"({', '.join(_quote_identifier(column) for column in insert_columns)}) "
            f"VALUES ({placeholders})"
        )
        for month in months:
            hot_conn.execute(
                f"DELETE FROM {_quote_identifier(HOURLY_TABLE)} WHERE reference_month = ?",
                (month,),
            )
            month_frame = frame.loc[frame["reference_month"] == month].copy()
            records = _frame_records(month_frame, insert_columns)
            if records:
                hot_conn.executemany(insert_sql, records)
        hot_conn.execute(HOT_STORE_EXTRA_INDEX_SQL)
        hot_conn.commit()
        counts = {
            str(row[0]): int(row[1])
            for row in hot_conn.execute(
                f"""
                SELECT reference_month, COUNT(*)
                FROM {_quote_identifier(HOURLY_TABLE)}
                GROUP BY reference_month
                ORDER BY reference_month
                """
            ).fetchall()
        }
        return {"hot_path": hot_path, "hot_counts": counts}


def _max_hot_months(manifest: dict[str, Any]) -> int:
    raw = manifest.get("selection", {}).get("max_hot_months")
    if raw is None:
        raw = manifest.get("artifacts", {}).get("hot", {}).get("max_hot_months")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_HOT_MONTHS
    return max(1, value)


def _cold_root(manifest: dict[str, Any]) -> Path:
    raw_path = manifest.get("artifacts", {}).get("cold", {}).get("path")
    if raw_path:
        return Path(str(raw_path)).expanduser().resolve()
    output_dir = manifest.get("artifacts", {}).get("output_dir")
    if not output_dir:
        raise ValueError("Managed hourly store manifest does not include artifacts.cold.path or artifacts.output_dir.")
    return Path(str(output_dir)).expanduser().resolve() / "cold"


def _roll_hot_months_to_cold(
    manifest: dict[str, Any],
    hot_path: Path,
    imported_months: list[str],
) -> dict[str, Any]:
    existing_hot_months = {str(month) for month in manifest.get("selection", {}).get("hot_months", [])}
    hot_months = sorted(existing_hot_months | set(imported_months))
    max_hot_months = _max_hot_months(manifest)
    keep_hot_months = hot_months[-max_hot_months:]
    rolled_months = [month for month in hot_months if month not in set(keep_hot_months)]

    cold_partitions = [
        dict(partition)
        for partition in manifest.get("artifacts", {}).get("cold", {}).get("partitions", [])
        if str(partition.get("reference_month") or "") not in set(imported_months) | set(rolled_months)
    ]
    cold_months = [
        str(month)
        for month in manifest.get("selection", {}).get("cold_months", [])
        if str(month) not in set(imported_months) | set(rolled_months)
    ]

    cold_root = _cold_root(manifest)
    with closing(sqlite3.connect(hot_path, timeout=30)) as hot_conn:
        hot_conn.row_factory = sqlite3.Row
        columns = _sqlite_columns(hot_conn, HOURLY_TABLE)
        for month in rolled_months:
            partition = _write_cold_partition_from_hot(
                hot_conn,
                cold_root=cold_root,
                reference_month=month,
                columns=columns,
                chunk_size=DEFAULT_COLD_PARQUET_CHUNK_SIZE,
            )
            cold_partitions.append(partition)
            cold_months.append(month)
            hot_conn.execute(
                f"DELETE FROM {_quote_identifier(HOURLY_TABLE)} WHERE reference_month = ?",
                (month,),
            )
        if rolled_months:
            hot_conn.commit()
            hot_conn.execute("VACUUM")
        hot_counts = {
            str(row[0]): int(row[1])
            for row in hot_conn.execute(
                f"""
                SELECT reference_month, COUNT(*)
                FROM {_quote_identifier(HOURLY_TABLE)}
                GROUP BY reference_month
                ORDER BY reference_month
                """
            ).fetchall()
        }
        hot_conn.commit()

    return {
        "hot_counts": hot_counts,
        "hot_months": sorted(hot_counts),
        "cold_months": sorted(set(cold_months)),
        "cold_partitions": sorted(cold_partitions, key=lambda row: str(row.get("reference_month") or "")),
        "rolled_to_cold_months": rolled_months,
    }


def _write_cold_partition_from_hot(
    hot_conn: sqlite3.Connection,
    *,
    cold_root: Path,
    reference_month: str,
    columns: list[str],
    chunk_size: int,
) -> dict[str, Any]:
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Hot-to-cold rollover requires polars for Parquet writes.") from exc

    month_dir = cold_root / HOURLY_TABLE / f"reference_month={reference_month}"
    if month_dir.exists():
        shutil.rmtree(month_dir)
    month_dir.mkdir(parents=True, exist_ok=True)

    selected_cols = ", ".join(_quote_identifier(column) for column in columns)
    cursor = hot_conn.execute(
        f"""
        SELECT {selected_cols}
        FROM {_quote_identifier(HOURLY_TABLE)}
        WHERE reference_month = ?
        ORDER BY reference_datetime, commercialization_period, plant_parcel_code
        """,
        (reference_month,),
    )
    written = 0
    parts: list[dict[str, Any]] = []
    part_idx = 0
    while True:
        rows = cursor.fetchmany(max(1, int(chunk_size)))
        if not rows:
            break
        tuples = [tuple(row[column] for column in columns) for row in rows]
        frame = pl.DataFrame(tuples, schema=columns, orient="row", infer_schema_length=None)
        part_path = month_dir / f"part-{part_idx:04d}.parquet"
        frame.write_parquet(part_path)
        parts.append({
            "path": str(part_path),
            "row_count": len(rows),
            "size_bytes": part_path.stat().st_size,
        })
        written += len(rows)
        part_idx += 1
    return {
        "reference_month": reference_month,
        "path": str(month_dir),
        "row_count": written,
        "expected_row_count": written,
        "parts": parts,
        "ok": written > 0 and all(part["size_bytes"] > 0 for part in parts),
    }


def _rebuild_marts_from_frame(conn, frame: pd.DataFrame, months: list[str]) -> dict[str, Any]:
    conn.execute(text(f"DROP TABLE IF EXISTS temp.{HOURLY_TABLE}"))
    conn.execute(text(f"CREATE TEMP TABLE {HOURLY_TABLE} AS SELECT * FROM main.{HOURLY_TABLE} WHERE 0"))
    temp_columns = [
        str(row["name"])
        for row in conn.execute(text(f"PRAGMA temp.table_info({HOURLY_TABLE})")).mappings().all()
    ]
    insert_columns = [column for column in temp_columns if column in frame.columns or column == "updated_at"]
    prepared = frame.copy()
    if "updated_at" in insert_columns and "updated_at" not in prepared.columns:
        prepared["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prepared = prepared[insert_columns].astype(object).where(pd.notna(prepared), None)
    stmt = text(
        f"INSERT INTO {HOURLY_TABLE} "
        f"({', '.join(_quote_identifier(column) for column in insert_columns)}) "
        f"VALUES ({', '.join(':' + column for column in insert_columns)})"
    )
    records = prepared.to_dict(orient="records")
    for start in range(0, len(records), 50_000):
        conn.execute(stmt, records[start:start + 50_000])
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS temp.idx_temp_cppe_ref_month ON {HOURLY_TABLE}(reference_month)"
    ))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS temp.idx_temp_cppe_parcel_ref "
        f"ON {HOURLY_TABLE}(plant_parcel_code, reference_datetime)"
    ))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS temp.idx_temp_cppe_parcel_month_ref "
        f"ON {HOURLY_TABLE}(plant_parcel_code, reference_month, reference_datetime)"
    ))
    try:
        return rebuild_plant_hourly_marts(conn, reference_months=months)
    finally:
        conn.execute(text(f"DROP TABLE IF EXISTS temp.{HOURLY_TABLE}"))


def _updated_manifest(
    manifest: dict[str, Any],
    manifest_path: Path,
    months: list[str],
    hot_counts: dict[str, int],
    cold_partitions: list[dict[str, Any]],
    hot_months: list[str],
    cold_months: list[str],
) -> dict[str, Any]:
    updated = json.loads(json.dumps(manifest, ensure_ascii=False))
    existing_counts = _manifest_counts(updated)
    cold_counts = {
        str(partition.get("reference_month")): int(partition.get("row_count") or 0)
        for partition in cold_partitions
        if partition.get("reference_month")
    }
    for month in months:
        existing_counts[month] = int(hot_counts.get(month, cold_counts.get(month, 0)))
    available = [
        {"reference_month": month, "row_count": int(existing_counts[month])}
        for month in sorted(existing_counts)
    ]
    updated.setdefault("selection", {})
    updated["selection"]["available_months"] = available
    updated["selection"]["hot_months"] = hot_months
    updated["selection"]["cold_months"] = cold_months
    updated["selection"]["max_hot_months"] = _max_hot_months(updated)
    updated["selection"]["full_months"] = True

    artifacts = updated.setdefault("artifacts", {})
    updated["contract"] = CCEE_HOURLY_CONTRACT.to_manifest_contract()
    artifacts["manifest_path"] = str(manifest_path)
    hot = artifacts.setdefault("hot", {})
    hot["months"] = hot_months
    hot["row_counts"] = {month: int(hot_counts.get(month, 0)) for month in hot_months}
    hot["expected_row_counts"] = dict(hot["row_counts"])
    hot_path = Path(str(hot.get("path"))).expanduser()
    hot["size_bytes"] = hot_path.stat().st_size if hot_path.exists() else 0
    with closing(sqlite3.connect(hot_path, timeout=30)) as hot_conn:
        hot["quick_check"] = str(hot_conn.execute("PRAGMA quick_check").fetchone()[0])
    hot["ok"] = hot["quick_check"].lower() == "ok" and all(hot["row_counts"].values())

    cold = artifacts.setdefault("cold", {})
    cold["months"] = cold_months
    cold["partitions"] = cold_partitions
    cold["ok"] = all(bool(partition.get("ok")) for partition in cold.get("partitions", []))

    updated["updated_at_utc"] = _utc_now()
    validation = updated.setdefault("validation", {})
    validation["hot_ok"] = bool(hot["ok"])
    validation["cold_ok"] = bool(cold["ok"])
    validation["ok"] = bool(hot["ok"] and cold["ok"])
    return updated


def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> None:
    temp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(manifest_path)


def _write_catalog(conn, settings: AppSettings, manifest_path: Path, manifest: dict[str, Any]) -> None:
    counts = _manifest_counts(manifest)
    conn.execute(
        text(f"""
            INSERT OR REPLACE INTO {CATALOG_TABLE}
                (dataset, manifest_path, manifest_fingerprint, source_database, full_months,
                 manifest_row_count, available_months_json)
            VALUES
                (:dataset, :manifest_path, :manifest_fingerprint, :source_database, 1,
                 :manifest_row_count, :available_months_json)
        """),
        {
            "dataset": HOURLY_TABLE,
            "manifest_path": str(manifest_path),
            "manifest_fingerprint": _manifest_fingerprint(manifest),
            "source_database": str(settings.paths.energy_kpi_db_path),
            "manifest_row_count": sum(counts.values()),
            "available_months_json": json.dumps(counts, sort_keys=True, separators=(",", ":")),
        },
    )
