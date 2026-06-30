"""Hot/cold prototype read adapter for CCEE plant-parcel hourly chart rows.

The raw SQLite database remains canonical. This module only reads validated
prototype artifacts and reports explicit fallback reasons when they cannot be
used. It is not wired into runtime chart routing by itself.
"""
from __future__ import annotations

import json
import sqlite3
import hashlib
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

HOURLY_TABLE = "ccee_plant_parcel_hourly"
PLANT_PARCELS_TABLE = "ccee_plant_parcels"
EXTERNAL_HOURLY_STORE_CATALOG = "external_hourly_store_catalog"
EXTERNAL_HOURLY_DATASET = HOURLY_TABLE
NUMERIC_COLUMNS = (
    "generation_mwh",
    "verified_generation_mwh",
    "verified_availability_mwh",
    "unavailability_mwh",
)

EntityType = Literal["ccee_plant_parcel", "aneel_plant"]
ReadPath = Literal["hot_sqlite", "cold_parquet"]


@dataclass(frozen=True)
class HourlyReadRequest:
    entity_id: str
    entity_type: EntityType
    reference_month: str
    start_datetime: str
    end_datetime: str
    limit: int


@dataclass(frozen=True)
class HourlyReadResult:
    rows: list[dict[str, Any]]
    read_path: ReadPath | None
    fallback_reason: str | None
    manifest_path: str | None = None
    artifact_path: str | None = None
    source_signature_ok: bool | None = None

    @property
    def ok(self) -> bool:
        return self.fallback_reason is None


def read_hourly_from_hot_cold(
    *,
    source_db_path: Path,
    manifest_path: Path | None,
    request: HourlyReadRequest,
) -> HourlyReadResult:
    """Return hourly chart rows from validated hot/cold artifacts when possible.

    On any unsafe or unavailable condition, the result has no rows and includes
    a fallback reason. Callers should then use the canonical raw SQLite query.
    """
    if manifest_path is None:
        return _unavailable("manifest_not_configured")
    manifest_path = manifest_path.expanduser().resolve()
    if not manifest_path.exists():
        return _unavailable("manifest_missing", manifest_path=manifest_path)

    source_db_path = source_db_path.expanduser().resolve()
    if not source_db_path.exists():
        return _unavailable("source_database_missing", manifest_path=manifest_path)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _unavailable(f"manifest_invalid:{exc}", manifest_path=manifest_path)

    if not _source_signature_matches(source_db_path, manifest):
        return _unavailable(
            "source_signature_mismatch",
            manifest_path=manifest_path,
            source_signature_ok=False,
        )

    month = _normalize_reference_month(request.reference_month)
    hot_months = {str(value) for value in manifest.get("selection", {}).get("hot_months", [])}
    cold_months = {str(value) for value in manifest.get("selection", {}).get("cold_months", [])}

    if month in hot_months:
        return _read_hot_sqlite(
            source_db_path=source_db_path,
            manifest_path=manifest_path,
            manifest=manifest,
            request=request,
            reference_month=month,
        )
    if month in cold_months:
        return _read_cold_parquet(
            source_db_path=source_db_path,
            manifest_path=manifest_path,
            manifest=manifest,
            request=request,
            reference_month=month,
        )
    return _unavailable(
        "reference_month_not_in_manifest",
        manifest_path=manifest_path,
        source_signature_ok=True,
    )


def _unavailable(
    reason: str,
    *,
    manifest_path: Path | None = None,
    artifact_path: Path | None = None,
    source_signature_ok: bool | None = None,
) -> HourlyReadResult:
    return HourlyReadResult(
        rows=[],
        read_path=None,
        fallback_reason=reason,
        manifest_path=str(manifest_path) if manifest_path else None,
        artifact_path=str(artifact_path) if artifact_path else None,
        source_signature_ok=source_signature_ok,
    )


def _normalize_reference_month(value: str) -> str:
    text_value = str(value or "").strip().replace("/", "-")
    if len(text_value) == 6 and "-" not in text_value:
        return f"{text_value[:4]}-{text_value[4:]}"
    return text_value


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _source_signature_matches(source_db_path: Path, manifest: dict[str, Any]) -> bool:
    current = _source_signature(source_db_path)
    expected = manifest.get("source_signature_after") or manifest.get("source_signature_before")
    if isinstance(expected, dict) and (
        int(expected.get("size_bytes") or -1) == current["size_bytes"]
        and int(expected.get("mtime_ns") or -1) == current["mtime_ns"]
    ):
        return True
    return _compact_source_metadata_matches(source_db_path, manifest)


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _expected_month_counts(manifest: dict[str, Any]) -> dict[str, int] | None:
    selection = manifest.get("selection") if isinstance(manifest.get("selection"), dict) else {}
    if selection.get("full_months") is not True:
        return None
    available_months = selection.get("available_months")
    if not isinstance(available_months, list) or not available_months:
        return None
    expected_by_month: dict[str, int] = {}
    for row in available_months:
        if not isinstance(row, dict):
            return None
        month = str(row.get("reference_month") or "").strip()
        if not month:
            return None
        expected_by_month[month] = int(row.get("row_count") or 0)
    return expected_by_month or None


def _catalog_matches(conn: sqlite3.Connection, manifest: dict[str, Any], expected_by_month: dict[str, int]) -> bool | None:
    catalog_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (EXTERNAL_HOURLY_STORE_CATALOG,),
    ).fetchone()
    if catalog_exists is None:
        return None

    row = conn.execute(
        f"""
        SELECT manifest_fingerprint, full_months, manifest_row_count, available_months_json
        FROM {EXTERNAL_HOURLY_STORE_CATALOG}
        WHERE dataset = ?
        """,
        (EXTERNAL_HOURLY_DATASET,),
    ).fetchone()
    if row is None:
        return False
    try:
        catalog_counts = json.loads(str(row["available_months_json"] or "{}"))
    except json.JSONDecodeError:
        return False
    normalized_counts = {str(month): int(count or 0) for month, count in dict(catalog_counts).items()}
    return (
        str(row["manifest_fingerprint"]) == _manifest_fingerprint(manifest)
        and int(row["full_months"] or 0) == 1
        and int(row["manifest_row_count"] or 0) == sum(expected_by_month.values())
        and normalized_counts == expected_by_month
    )


def _compact_source_metadata_matches(source_db_path: Path, manifest: dict[str, Any]) -> bool:
    """Accept compact DBs after raw hourly rows are externalized.

    Once ccee_plant_parcel_hourly rows are removed from energy_kpis.db, the
    database file signature necessarily changes. Some SQLite compaction paths
    preserve an empty table shell for compatibility, so reject only databases
    that still contain raw hourly rows. New compact DBs include a small audit
    catalog with the hourly store manifest fingerprint and month-level row
    counts. Older candidates fall back to scanning the daily mart.
    """
    expected_by_month = _expected_month_counts(manifest)
    if expected_by_month is None:
        return False

    try:
        with closing(_connect_readonly(source_db_path)) as conn:
            hourly_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (HOURLY_TABLE,),
            ).fetchone()
            if hourly_exists is not None:
                raw_hourly_row = conn.execute(f"SELECT 1 FROM {HOURLY_TABLE} LIMIT 1").fetchone()
                if raw_hourly_row is not None:
                    return False
            catalog_match = _catalog_matches(conn, manifest, expected_by_month)
            if catalog_match is not None:
                return catalog_match
            mart_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                ("plant_parcel_daily_generation_mart",),
            ).fetchone()
            if mart_exists is None:
                return False
            rows = conn.execute(
                """
                SELECT reference_month, SUM(hourly_observations) AS row_count
                FROM plant_parcel_daily_generation_mart
                GROUP BY reference_month
                ORDER BY reference_month
                """
            ).fetchall()
    except Exception:
        return False

    actual_by_month = {str(row["reference_month"]): int(row["row_count"] or 0) for row in rows}
    return actual_by_month == expected_by_month


def _hot_db_path(manifest: dict[str, Any]) -> Path | None:
    raw_path = manifest.get("artifacts", {}).get("hot", {}).get("path")
    if not raw_path:
        return None
    return Path(str(raw_path)).expanduser().resolve()


def _cold_part_paths(manifest: dict[str, Any], reference_month: str) -> list[Path]:
    for partition in manifest.get("artifacts", {}).get("cold", {}).get("partitions", []):
        if str(partition.get("reference_month") or "") != reference_month:
            continue
        return [
            Path(str(part.get("path"))).expanduser().resolve()
            for part in partition.get("parts", [])
            if part.get("path")
        ]
    return []


def _plant_parcel_codes_for_ceg(source_db_path: Path, ceg: str) -> list[str]:
    with closing(_connect_readonly(source_db_path)) as conn:
        rows = conn.execute(
            f"""
            SELECT plant_parcel_code
            FROM {PLANT_PARCELS_TABLE}
            WHERE ceg = ?
            ORDER BY plant_parcel_code
            """,
            (ceg,),
        ).fetchall()
    return [str(row["plant_parcel_code"]) for row in rows if row["plant_parcel_code"]]


def _normalize_sqlite_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("commercialization_period") is not None:
            item["commercialization_period"] = int(item["commercialization_period"])
        for column in NUMERIC_COLUMNS:
            if item.get(column) is not None:
                item[column] = float(item[column])
        normalized.append(item)
    return normalized


def _read_hot_sqlite(
    *,
    source_db_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    request: HourlyReadRequest,
    reference_month: str,
) -> HourlyReadResult:
    hot_path = _hot_db_path(manifest)
    if hot_path is None:
        return _unavailable("hot_sqlite_path_missing", manifest_path=manifest_path, source_signature_ok=True)
    if not hot_path.exists():
        return _unavailable(
            "hot_sqlite_missing",
            manifest_path=manifest_path,
            artifact_path=hot_path,
            source_signature_ok=True,
        )

    try:
        with closing(_connect_readonly(hot_path)) as conn:
            if request.entity_type == "aneel_plant":
                plant_parcel_codes = _plant_parcel_codes_for_ceg(source_db_path, request.entity_id)
                if not plant_parcel_codes:
                    return _unavailable(
                        "ceg_mapping_missing",
                        manifest_path=manifest_path,
                        artifact_path=hot_path,
                        source_signature_ok=True,
                    )
                rows = _read_sqlite_parcel_group(
                    conn,
                    plant_parcel_codes=plant_parcel_codes,
                    reference_month=reference_month,
                    start_datetime=request.start_datetime,
                    end_datetime=request.end_datetime,
                    limit=request.limit,
                )
            else:
                rows = _read_sqlite_parcel(
                    conn,
                    plant_parcel_code=request.entity_id,
                    reference_month=reference_month,
                    start_datetime=request.start_datetime,
                    end_datetime=request.end_datetime,
                    limit=request.limit,
                )
    except Exception as exc:
        return _unavailable(
            f"hot_sqlite_read_failed:{exc}",
            manifest_path=manifest_path,
            artifact_path=hot_path,
            source_signature_ok=True,
        )
    return HourlyReadResult(
        rows=rows,
        read_path="hot_sqlite",
        fallback_reason=None,
        manifest_path=str(manifest_path),
        artifact_path=str(hot_path),
        source_signature_ok=True,
    )


def _read_sqlite_parcel(
    conn: sqlite3.Connection,
    *,
    plant_parcel_code: str,
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            reference_datetime,
            commercialization_period,
            generation_center_of_gravity_mwh AS generation_mwh,
            verified_generation_ons_mwh AS verified_generation_mwh,
            verified_availability_mwh AS verified_availability_mwh,
            unavailability_mwh AS unavailability_mwh
        FROM {HOURLY_TABLE}
        WHERE plant_parcel_code = ?
          AND reference_month = ?
          AND reference_datetime >= ?
          AND reference_datetime <= ?
        ORDER BY reference_datetime ASC, commercialization_period ASC
        LIMIT ?
        """,
        (_normalize_entity_id(plant_parcel_code), reference_month, start_datetime, end_datetime, _bounded_limit(limit)),
    ).fetchall()
    return _normalize_sqlite_rows(rows)


def _read_sqlite_parcel_group(
    conn: sqlite3.Connection,
    *,
    plant_parcel_codes: list[str],
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    codes = [_normalize_entity_id(code) for code in plant_parcel_codes if str(code).strip()]
    if not codes:
        return []
    placeholders = ", ".join("?" for _ in codes)
    rows = conn.execute(
        f"""
        SELECT
            reference_datetime,
            commercialization_period,
            SUM(generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(verified_generation_ons_mwh) AS verified_generation_mwh,
            SUM(verified_availability_mwh) AS verified_availability_mwh,
            SUM(unavailability_mwh) AS unavailability_mwh
        FROM {HOURLY_TABLE}
        WHERE plant_parcel_code IN ({placeholders})
          AND reference_month = ?
          AND reference_datetime >= ?
          AND reference_datetime <= ?
        GROUP BY reference_datetime, commercialization_period
        ORDER BY reference_datetime ASC, commercialization_period ASC
        LIMIT ?
        """,
        (*codes, reference_month, start_datetime, end_datetime, _bounded_limit(limit)),
    ).fetchall()
    return _normalize_sqlite_rows(rows)


def _read_cold_parquet(
    *,
    source_db_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    request: HourlyReadRequest,
    reference_month: str,
) -> HourlyReadResult:
    part_paths = _cold_part_paths(manifest, reference_month)
    if not part_paths:
        return _unavailable("cold_partition_missing", manifest_path=manifest_path, source_signature_ok=True)
    missing = [str(path) for path in part_paths if not path.exists()]
    if missing:
        return _unavailable(
            f"cold_part_missing:{missing[0]}",
            manifest_path=manifest_path,
            artifact_path=part_paths[0],
            source_signature_ok=True,
        )

    try:
        if request.entity_type == "aneel_plant":
            plant_parcel_codes = _plant_parcel_codes_for_ceg(source_db_path, request.entity_id)
            if not plant_parcel_codes:
                return _unavailable(
                    "ceg_mapping_missing",
                    manifest_path=manifest_path,
                    artifact_path=part_paths[0],
                    source_signature_ok=True,
                )
            rows = _read_cold_parcel_group(
                part_paths,
                plant_parcel_codes=plant_parcel_codes,
                reference_month=reference_month,
                start_datetime=request.start_datetime,
                end_datetime=request.end_datetime,
                limit=request.limit,
            )
        else:
            rows = _read_cold_parcel(
                part_paths,
                plant_parcel_code=request.entity_id,
                reference_month=reference_month,
                start_datetime=request.start_datetime,
                end_datetime=request.end_datetime,
                limit=request.limit,
            )
    except Exception as exc:
        return _unavailable(
            f"cold_parquet_read_failed:{exc}",
            manifest_path=manifest_path,
            artifact_path=part_paths[0],
            source_signature_ok=True,
        )
    return HourlyReadResult(
        rows=rows,
        read_path="cold_parquet",
        fallback_reason=None,
        manifest_path=str(manifest_path),
        artifact_path=str(part_paths[0].parent),
        source_signature_ok=True,
    )


def _read_cold_parcel(
    part_paths: list[Path],
    *,
    plant_parcel_code: str,
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("polars is required for cold Parquet reads") from exc

    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .filter(
            (pl.col("plant_parcel_code").cast(pl.Utf8) == _normalize_entity_id(plant_parcel_code))
            & (pl.col("reference_month").cast(pl.Utf8) == reference_month)
            & (pl.col("reference_datetime").cast(pl.Utf8) >= str(start_datetime))
            & (pl.col("reference_datetime").cast(pl.Utf8) <= str(end_datetime))
        )
        .select(
            [
                pl.col("reference_datetime").cast(pl.Utf8).alias("reference_datetime"),
                pl.col("commercialization_period").cast(pl.Int64).alias("commercialization_period"),
                pl.col("generation_center_of_gravity_mwh").alias("generation_mwh"),
                pl.col("verified_generation_ons_mwh").alias("verified_generation_mwh"),
                pl.col("verified_availability_mwh").alias("verified_availability_mwh"),
                pl.col("unavailability_mwh").alias("unavailability_mwh"),
            ]
        )
        .sort(["reference_datetime", "commercialization_period"])
        .limit(_bounded_limit(limit))
        .collect()
    )
    return _normalize_polars_rows(frame.to_dicts())


def _read_cold_parcel_group(
    part_paths: list[Path],
    *,
    plant_parcel_codes: list[str],
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("polars is required for cold Parquet reads") from exc

    codes = [_normalize_entity_id(code) for code in plant_parcel_codes if str(code).strip()]
    if not codes:
        return []
    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .filter(
            (pl.col("plant_parcel_code").cast(pl.Utf8).is_in(codes))
            & (pl.col("reference_month").cast(pl.Utf8) == reference_month)
            & (pl.col("reference_datetime").cast(pl.Utf8) >= str(start_datetime))
            & (pl.col("reference_datetime").cast(pl.Utf8) <= str(end_datetime))
        )
        .with_columns(
            [
                pl.col("reference_datetime").cast(pl.Utf8).alias("reference_datetime"),
                pl.col("commercialization_period").cast(pl.Int64).alias("commercialization_period"),
            ]
        )
        .group_by(["reference_datetime", "commercialization_period"])
        .agg(
            [
                _sum_like_sqlite("generation_center_of_gravity_mwh", "generation_mwh"),
                _sum_like_sqlite("verified_generation_ons_mwh", "verified_generation_mwh"),
                _sum_like_sqlite("verified_availability_mwh", "verified_availability_mwh"),
                _sum_like_sqlite("unavailability_mwh", "unavailability_mwh"),
            ]
        )
        .sort(["reference_datetime", "commercialization_period"])
        .limit(_bounded_limit(limit))
        .collect()
    )
    return _normalize_polars_rows(frame.to_dicts())


def _sum_like_sqlite(source_column: str, alias: str):
    import polars as pl  # noqa: PLC0415

    return (
        pl.when(pl.col(source_column).is_not_null().any())
        .then(pl.col(source_column).sum())
        .otherwise(None)
        .alias(alias)
    )


def _normalize_polars_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = {
            "reference_datetime": str(row.get("reference_datetime")),
            "commercialization_period": int(row["commercialization_period"]),
            "generation_mwh": row.get("generation_mwh"),
            "verified_generation_mwh": row.get("verified_generation_mwh"),
            "verified_availability_mwh": row.get("verified_availability_mwh"),
            "unavailability_mwh": row.get("unavailability_mwh"),
        }
        for column in NUMERIC_COLUMNS:
            if item.get(column) is not None:
                item[column] = float(item[column])
        normalized.append(item)
    return normalized


def _normalize_entity_id(value: str) -> str:
    return str(value or "").strip()


def _bounded_limit(value: int) -> int:
    return max(1, min(int(value or 2_000), 5_000))
