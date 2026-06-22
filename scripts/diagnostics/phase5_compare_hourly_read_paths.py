#!/usr/bin/env python3
"""Compare CCEE hourly raw SQLite reads with hot/cold prototype artifacts.

This is diagnostic-only. It does not change runtime routing, migrate data,
compact databases, or write to the source/hot SQLite databases. SQLite inputs
are opened through read-only URI connections.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import sqlite3
import sys
import time
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import HOURLY_TABLE  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_LIMIT = 2_000
DEFAULT_RUNS = 1
DEFAULT_SAMPLES_PER_TIER = 1
DEFAULT_ANEEL_SAMPLES_PER_TIER = 1
NUMERIC_TOLERANCE = 1e-9
PLANT_PARCELS_TABLE = "ccee_plant_parcels"
CEG_MART_TABLE = "ceg_hourly_generation_mart"
COMPARISON_COLUMNS = (
    "reference_datetime",
    "commercialization_period",
    "generation_mwh",
    "verified_generation_mwh",
    "verified_availability_mwh",
    "unavailability_mwh",
)
SOURCE_VALUE_COLUMNS = {
    "generation_mwh": "generation_center_of_gravity_mwh",
    "verified_generation_mwh": "verified_generation_ons_mwh",
    "verified_availability_mwh": "verified_availability_mwh",
    "unavailability_mwh": "unavailability_mwh",
}
Tier = Literal["hot", "cold"]
EntityType = Literal["ccee_plant_parcel", "aneel_plant"]
AutoEntityType = Literal["all", "ccee_plant_parcel", "aneel_plant"]
WindowMode = Literal["auto", "month", "sample_datetime"]
RowsReader = Callable[[], list[dict[str, Any]]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _source_signature(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _hash_rows(rows: list[dict[str, Any]]) -> str:
    def canonical(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 9)
        if isinstance(value, dict):
            return {key: canonical(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [canonical(inner) for inner in value]
        return value

    payload = json.dumps(canonical(rows), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    text = str(value)
    if text == "nan":
        return None
    return text


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = {column: _normalize_value(row.get(column)) for column in COMPARISON_COLUMNS}
    period = normalized.get("commercialization_period")
    if period is not None:
        normalized["commercialization_period"] = int(period)
    for column in SOURCE_VALUE_COLUMNS:
        value = normalized.get(column)
        if value is not None:
            normalized[column] = float(value)
    return normalized


def _rows_from_sqlite(
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
        (plant_parcel_code, reference_month, start_datetime, end_datetime, limit),
    ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _plant_parcel_codes_for_ceg(conn: sqlite3.Connection, ceg: str) -> list[str]:
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


def _rows_from_sqlite_aneel_plant(
    conn: sqlite3.Connection,
    *,
    ceg: str,
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            h.reference_datetime,
            h.commercialization_period,
            SUM(h.generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(h.verified_generation_ons_mwh) AS verified_generation_mwh,
            SUM(h.verified_availability_mwh) AS verified_availability_mwh,
            SUM(h.unavailability_mwh) AS unavailability_mwh
        FROM {HOURLY_TABLE} h
        JOIN {PLANT_PARCELS_TABLE} p ON p.plant_parcel_code = h.plant_parcel_code
        WHERE p.ceg = ?
          AND h.reference_month = ?
          AND h.reference_datetime >= ?
          AND h.reference_datetime <= ?
        GROUP BY h.reference_datetime, h.commercialization_period
        ORDER BY h.reference_datetime ASC, h.commercialization_period ASC
        LIMIT ?
        """,
        (ceg, reference_month, start_datetime, end_datetime, limit),
    ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _rows_from_ceg_mart(
    conn: sqlite3.Connection,
    *,
    ceg: str,
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
            generation_mwh,
            verified_generation_mwh,
            verified_availability_mwh,
            unavailability_mwh
        FROM {CEG_MART_TABLE}
        WHERE ceg = ?
          AND reference_month = ?
          AND reference_datetime >= ?
          AND reference_datetime <= ?
        ORDER BY reference_datetime ASC, commercialization_period ASC
        LIMIT ?
        """,
        (ceg, reference_month, start_datetime, end_datetime, limit),
    ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _rows_from_sqlite_parcel_group(
    conn: sqlite3.Connection,
    *,
    plant_parcel_codes: list[str],
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    codes = [str(code) for code in plant_parcel_codes if str(code)]
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
        (*codes, reference_month, start_datetime, end_datetime, limit),
    ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _timed_read(reader: RowsReader, *, runs: int) -> dict[str, Any]:
    bounded_runs = max(1, int(runs or 1))
    elapsed: list[float] = []
    result: list[dict[str, Any]] = []
    for idx in range(bounded_runs):
        started = time.perf_counter()
        rows = reader()
        elapsed.append(round((time.perf_counter() - started) * 1000, 3))
        if idx == 0:
            result = rows
    return {
        "rows": result,
        "row_count": len(result),
        "elapsed_ms": elapsed[0],
        "elapsed_runs_ms": elapsed,
        "rows_hash": _hash_rows(result),
    }


def _values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= NUMERIC_TOLERANCE
    return left == right


def _compare_rows(
    raw_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    differences: list[dict[str, Any]] = []
    if len(raw_rows) != len(candidate_rows):
        differences.append(
            {
                "type": "row_count",
                "raw_count": len(raw_rows),
                "candidate_count": len(candidate_rows),
            }
        )

    for idx, (raw_row, candidate_row) in enumerate(zip(raw_rows, candidate_rows)):
        for column in COMPARISON_COLUMNS:
            raw_value = raw_row.get(column)
            candidate_value = candidate_row.get(column)
            if not _values_equal(raw_value, candidate_value):
                differences.append(
                    {
                        "type": "value",
                        "row_index": idx,
                        "column": column,
                        "raw": raw_value,
                        "candidate": candidate_value,
                    }
                )
                if len(differences) >= 20:
                    return {
                        "match": False,
                        "difference_count": len(differences),
                        "differences": differences,
                        "truncated": True,
                    }

    return {
        "match": not differences,
        "difference_count": len(differences),
        "differences": differences,
        "truncated": False,
    }


def _month_window(reference_month: str) -> tuple[str, str]:
    year_text, month_text = reference_month.split("-", 1)
    year = int(year_text)
    month = int(month_text)
    last_day = calendar.monthrange(year, month)[1]
    return (
        f"{year:04d}-{month:02d}-01T00:00:00",
        f"{year:04d}-{month:02d}-{last_day:02d}T23:59:59",
    )


def _resolve_window(
    *,
    manifest: dict[str, Any],
    reference_month: str,
    sample_datetime: str | None,
    start_datetime: str | None,
    end_datetime: str | None,
    window_mode: WindowMode,
) -> tuple[str, str, str]:
    if start_datetime and end_datetime:
        return str(start_datetime), str(end_datetime), "explicit"
    full_months = bool(manifest.get("selection", {}).get("full_months"))
    resolved_mode = "month" if window_mode == "auto" and full_months else window_mode
    if resolved_mode == "auto":
        resolved_mode = "sample_datetime"
    if resolved_mode == "month":
        start, end = _month_window(reference_month)
        return start, end, "month"
    if not sample_datetime:
        start, end = _month_window(reference_month)
        return start, end, "month_fallback"
    return sample_datetime, sample_datetime, "sample_datetime"


def _manifest_path(manifest_path: Path | None, prototype_dir: Path | None) -> Path:
    if manifest_path:
        return manifest_path.expanduser().resolve()
    if prototype_dir:
        return (prototype_dir.expanduser().resolve() / "manifest.json").resolve()
    raise ValueError("Either --manifest or --prototype-dir is required.")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Manifest does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _hot_db_path(manifest: dict[str, Any]) -> Path:
    value = manifest.get("artifacts", {}).get("hot", {}).get("path")
    if not value:
        raise ValueError("Manifest does not include artifacts.hot.path")
    return Path(str(value)).expanduser().resolve()


def _cold_partitions(manifest: dict[str, Any]) -> dict[str, list[Path]]:
    partitions: dict[str, list[Path]] = {}
    for partition in manifest.get("artifacts", {}).get("cold", {}).get("partitions", []):
        month = str(partition.get("reference_month") or "").strip()
        if not month:
            continue
        paths = [
            Path(str(part.get("path"))).expanduser().resolve()
            for part in partition.get("parts", [])
            if part.get("path")
        ]
        partitions[month] = paths
    return partitions


def _sqlite_parcel_samples(
    conn: sqlite3.Connection,
    reference_month: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT plant_parcel_code, reference_month, MIN(reference_datetime) AS reference_datetime
        FROM {HOURLY_TABLE}
        WHERE reference_month = ?
        GROUP BY plant_parcel_code, reference_month
        ORDER BY plant_parcel_code ASC
        LIMIT ?
        """,
        (reference_month, max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def _sqlite_aneel_samples(
    conn: sqlite3.Connection,
    reference_month: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT
            p.ceg,
            h.reference_month,
            MIN(h.reference_datetime) AS reference_datetime,
            COUNT(DISTINCT h.plant_parcel_code) AS plant_parcel_count
        FROM {HOURLY_TABLE} h
        JOIN {PLANT_PARCELS_TABLE} p ON p.plant_parcel_code = h.plant_parcel_code
        WHERE h.reference_month = ?
          AND p.ceg IS NOT NULL
          AND TRIM(p.ceg) <> ''
        GROUP BY p.ceg, h.reference_month
        ORDER BY plant_parcel_count DESC, p.ceg ASC
        LIMIT ?
        """,
        (reference_month, max(1, int(limit))),
    ).fetchall()
    return [dict(row) for row in rows]


def _cold_parcel_samples(part_paths: list[Path], *, limit: int) -> list[dict[str, Any]]:
    if not part_paths:
        return []
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Cold Parquet comparison requires polars.") from exc

    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(["plant_parcel_code", "reference_month", "reference_datetime"])
        .group_by(["plant_parcel_code", "reference_month"])
        .agg(pl.col("reference_datetime").min().alias("reference_datetime"))
        .sort(["plant_parcel_code", "reference_month"])
        .limit(max(1, int(limit)))
        .collect()
    )
    return [
        {
            "plant_parcel_code": str(row["plant_parcel_code"]),
            "reference_month": str(row["reference_month"]),
            "reference_datetime": str(row["reference_datetime"]),
        }
        for row in frame.to_dicts()
    ]


def _manual_sample(
    *,
    tier: Tier,
    reference_month: str,
    entity_type: EntityType,
    entity_id: str,
    sample_datetime: str | None,
) -> dict[str, Any]:
    return {
        "label": f"manual_{tier}_{entity_type}_{reference_month}_{entity_id}",
        "tier": tier,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "reference_month": reference_month,
        "plant_parcel_code": entity_id if entity_type == "ccee_plant_parcel" else None,
        "ceg": entity_id if entity_type == "aneel_plant" else None,
        "sample_datetime": sample_datetime,
    }


def _auto_samples(
    manifest: dict[str, Any],
    *,
    raw_conn: sqlite3.Connection,
    hot_conn: sqlite3.Connection | None,
    cold_paths: dict[str, list[Path]],
    tier: str,
    samples_per_tier: int,
    aneel_samples_per_tier: int,
    include_aneel_aggregation: bool,
    auto_entity_type: AutoEntityType,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    selected_hot = [str(month) for month in manifest.get("selection", {}).get("hot_months", [])]
    selected_cold = [str(month) for month in manifest.get("selection", {}).get("cold_months", [])]
    per_tier = max(1, int(samples_per_tier or DEFAULT_SAMPLES_PER_TIER))
    aneel_per_tier = max(1, int(aneel_samples_per_tier or DEFAULT_ANEEL_SAMPLES_PER_TIER))
    full_months = bool(manifest.get("selection", {}).get("full_months"))
    include_parcel_samples = auto_entity_type in {"all", "ccee_plant_parcel"}
    include_aneel_samples = full_months and (
        auto_entity_type == "aneel_plant" or (auto_entity_type == "all" and include_aneel_aggregation)
    )

    if tier in {"all", "hot"} and hot_conn is not None:
        for month in selected_hot:
            if include_parcel_samples:
                for sample in _sqlite_parcel_samples(hot_conn, month, limit=per_tier):
                    samples.append(
                        {
                            "label": f"auto_hot_parcel_{month}_{sample['plant_parcel_code']}",
                            "tier": "hot",
                            "entity_type": "ccee_plant_parcel",
                            "entity_id": str(sample["plant_parcel_code"]),
                            "reference_month": month,
                            "plant_parcel_code": str(sample["plant_parcel_code"]),
                            "ceg": None,
                            "sample_datetime": str(sample["reference_datetime"]),
                        }
                    )
            if include_aneel_samples:
                for sample in _sqlite_aneel_samples(raw_conn, month, limit=aneel_per_tier):
                    samples.append(
                        {
                            "label": f"auto_hot_aneel_{month}_{sample['ceg']}",
                            "tier": "hot",
                            "entity_type": "aneel_plant",
                            "entity_id": str(sample["ceg"]),
                            "reference_month": month,
                            "plant_parcel_code": None,
                            "ceg": str(sample["ceg"]),
                            "sample_datetime": str(sample["reference_datetime"]),
                            "plant_parcel_count": int(sample["plant_parcel_count"] or 0),
                        }
                    )

    if tier in {"all", "cold"}:
        for month in selected_cold:
            if include_parcel_samples:
                for sample in _cold_parcel_samples(cold_paths.get(month, []), limit=per_tier):
                    samples.append(
                        {
                            "label": f"auto_cold_parcel_{month}_{sample['plant_parcel_code']}",
                            "tier": "cold",
                            "entity_type": "ccee_plant_parcel",
                            "entity_id": str(sample["plant_parcel_code"]),
                            "reference_month": month,
                            "plant_parcel_code": str(sample["plant_parcel_code"]),
                            "ceg": None,
                            "sample_datetime": str(sample["reference_datetime"]),
                        }
                    )
            if include_aneel_samples:
                for sample in _sqlite_aneel_samples(raw_conn, month, limit=aneel_per_tier):
                    samples.append(
                        {
                            "label": f"auto_cold_aneel_{month}_{sample['ceg']}",
                            "tier": "cold",
                            "entity_type": "aneel_plant",
                            "entity_id": str(sample["ceg"]),
                            "reference_month": month,
                            "plant_parcel_code": None,
                            "ceg": str(sample["ceg"]),
                            "sample_datetime": str(sample["reference_datetime"]),
                            "plant_parcel_count": int(sample["plant_parcel_count"] or 0),
                        }
                    )

    return samples


def _read_cold_rows(
    part_paths: list[Path],
    *,
    plant_parcel_code: str,
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not part_paths:
        raise FileNotFoundError(f"No cold Parquet parts found for reference_month={reference_month}")
    missing = [str(path) for path in part_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing cold Parquet part(s): {', '.join(missing)}")
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Cold Parquet comparison requires polars.") from exc

    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .filter(
            (pl.col("plant_parcel_code").cast(pl.Utf8) == str(plant_parcel_code))
            & (pl.col("reference_month").cast(pl.Utf8) == str(reference_month))
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
        .limit(max(1, int(limit)))
        .collect()
    )
    return [_normalize_row(row) for row in frame.to_dicts()]


def _sum_like_sqlite(source_column: str, alias: str):
    import polars as pl  # noqa: PLC0415

    return (
        pl.when(pl.col(source_column).is_not_null().any())
        .then(pl.col(source_column).sum())
        .otherwise(None)
        .alias(alias)
    )


def _read_cold_aneel_rows(
    part_paths: list[Path],
    *,
    plant_parcel_codes: list[str],
    reference_month: str,
    start_datetime: str,
    end_datetime: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not part_paths:
        raise FileNotFoundError(f"No cold Parquet parts found for reference_month={reference_month}")
    codes = [str(code) for code in plant_parcel_codes if str(code)]
    if not codes:
        return []
    missing = [str(path) for path in part_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing cold Parquet part(s): {', '.join(missing)}")
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Cold Parquet comparison requires polars.") from exc

    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .filter(
            (pl.col("plant_parcel_code").cast(pl.Utf8).is_in(codes))
            & (pl.col("reference_month").cast(pl.Utf8) == str(reference_month))
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
        .limit(max(1, int(limit)))
        .collect()
    )
    return [_normalize_row(row) for row in frame.to_dicts()]


def _compare_sample(
    sample: dict[str, Any],
    *,
    manifest: dict[str, Any],
    raw_conn: sqlite3.Connection,
    hot_conn: sqlite3.Connection | None,
    ceg_mart_conn: sqlite3.Connection | None,
    cold_paths: dict[str, list[Path]],
    start_datetime: str | None,
    end_datetime: str | None,
    window_mode: WindowMode,
    limit: int,
    runs: int,
) -> dict[str, Any]:
    tier = str(sample["tier"])
    entity_type = str(sample.get("entity_type") or "ccee_plant_parcel")
    entity_id = str(sample.get("entity_id") or sample.get("plant_parcel_code") or sample.get("ceg") or "")
    reference_month = str(sample["reference_month"])
    plant_parcel_code = str(sample.get("plant_parcel_code") or "")
    ceg = str(sample.get("ceg") or "")
    start_value, end_value, resolved_window_mode = _resolve_window(
        manifest=manifest,
        reference_month=reference_month,
        sample_datetime=sample.get("sample_datetime"),
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        window_mode=window_mode,
    )
    bounded_limit = max(1, int(limit or DEFAULT_LIMIT))
    plant_parcel_codes: list[str] = []
    if entity_type == "aneel_plant":
        plant_parcel_codes = _plant_parcel_codes_for_ceg(raw_conn, ceg or entity_id)

    if entity_type == "aneel_plant":
        raw = _timed_read(
            lambda: _rows_from_sqlite_aneel_plant(
                raw_conn,
                ceg=ceg or entity_id,
                reference_month=reference_month,
                start_datetime=start_value,
                end_datetime=end_value,
                limit=bounded_limit,
            ),
            runs=runs,
        )
    else:
        raw = _timed_read(
            lambda: _rows_from_sqlite(
                raw_conn,
                plant_parcel_code=plant_parcel_code or entity_id,
                reference_month=reference_month,
                start_datetime=start_value,
                end_datetime=end_value,
                limit=bounded_limit,
            ),
            runs=runs,
        )

    if tier == "hot":
        if hot_conn is None:
            raise ValueError("Hot comparison requested but hot DB is unavailable.")
        candidate_source = "hot_sqlite"
        if entity_type == "aneel_plant":
            candidate = _timed_read(
                lambda: _rows_from_sqlite_parcel_group(
                    hot_conn,
                    plant_parcel_codes=plant_parcel_codes,
                    reference_month=reference_month,
                    start_datetime=start_value,
                    end_datetime=end_value,
                    limit=bounded_limit,
                ),
                runs=runs,
            )
        else:
            candidate = _timed_read(
                lambda: _rows_from_sqlite(
                    hot_conn,
                    plant_parcel_code=plant_parcel_code or entity_id,
                    reference_month=reference_month,
                    start_datetime=start_value,
                    end_datetime=end_value,
                    limit=bounded_limit,
                ),
                runs=runs,
            )
    elif tier == "cold":
        candidate_source = "cold_parquet"
        part_paths = cold_paths.get(reference_month, [])
        if entity_type == "aneel_plant":
            candidate = _timed_read(
                lambda: _read_cold_aneel_rows(
                    part_paths,
                    plant_parcel_codes=plant_parcel_codes,
                    reference_month=reference_month,
                    start_datetime=start_value,
                    end_datetime=end_value,
                    limit=bounded_limit,
                ),
                runs=runs,
            )
        else:
            candidate = _timed_read(
                lambda: _read_cold_rows(
                    part_paths,
                    plant_parcel_code=plant_parcel_code or entity_id,
                    reference_month=reference_month,
                    start_datetime=start_value,
                    end_datetime=end_value,
                    limit=bounded_limit,
                ),
                runs=runs,
            )
    else:
        raise ValueError(f"Unsupported sample tier: {tier}")

    comparison = _compare_rows(raw["rows"], candidate["rows"])
    result = {
        "label": sample.get("label"),
        "tier": tier,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "reference_month": reference_month,
        "plant_parcel_code": plant_parcel_code or None,
        "ceg": ceg or None,
        "plant_parcel_count": int(sample.get("plant_parcel_count") or len(plant_parcel_codes) or 0),
        "start_datetime": start_value,
        "end_datetime": end_value,
        "window_mode": resolved_window_mode,
        "limit": bounded_limit,
        "raw": {
            "source": "raw_sqlite",
            "row_count": raw["row_count"],
            "elapsed_ms": raw["elapsed_ms"],
            "elapsed_runs_ms": raw["elapsed_runs_ms"],
            "rows_hash": raw["rows_hash"],
        },
        "candidate": {
            "source": candidate_source,
            "row_count": candidate["row_count"],
            "elapsed_ms": candidate["elapsed_ms"],
            "elapsed_runs_ms": candidate["elapsed_runs_ms"],
            "rows_hash": candidate["rows_hash"],
        },
        **comparison,
    }
    if entity_type == "aneel_plant" and ceg_mart_conn is not None:
        ceg_mart = _timed_read(
            lambda: _rows_from_ceg_mart(
                ceg_mart_conn,
                ceg=ceg or entity_id,
                reference_month=reference_month,
                start_datetime=start_value,
                end_datetime=end_value,
                limit=bounded_limit,
            ),
            runs=runs,
        )
        result["ceg_mart"] = {
            "source": "ceg_sqlite_mart",
            "row_count": len(ceg_mart["rows"]),
            "elapsed_ms": ceg_mart["elapsed_ms"],
            "elapsed_runs_ms": ceg_mart["elapsed_runs_ms"],
            "rows_hash": ceg_mart["rows_hash"],
        }
        result["ceg_mart_comparison"] = _compare_rows(raw["rows"], ceg_mart["rows"])
    return result


def compare_hourly_read_paths(
    *,
    manifest_path: Path | None = None,
    prototype_dir: Path | None = None,
    database: Path | None = None,
    ceg_mart_path: Path | None = None,
    tier: str = "all",
    entity_type: EntityType = "ccee_plant_parcel",
    entity_id: str | None = None,
    plant_parcel_code: str | None = None,
    reference_month: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    window_mode: WindowMode = "auto",
    limit: int = DEFAULT_LIMIT,
    runs: int = DEFAULT_RUNS,
    samples_per_tier: int = DEFAULT_SAMPLES_PER_TIER,
    aneel_samples_per_tier: int = DEFAULT_ANEEL_SAMPLES_PER_TIER,
    include_aneel_aggregation: bool = False,
    auto_entity_type: AutoEntityType = "all",
) -> dict[str, Any]:
    resolved_manifest_path = _manifest_path(manifest_path, prototype_dir)
    manifest = _load_manifest(resolved_manifest_path)
    source_db = (
        database.expanduser().resolve()
        if database is not None
        else Path(str(manifest.get("source_database"))).expanduser().resolve()
    )
    if not source_db.exists():
        raise FileNotFoundError(f"Source energy database does not exist: {source_db}")

    source_before = _source_signature(source_db)
    hot_path = _hot_db_path(manifest)
    cold_paths = _cold_partitions(manifest)
    resolved_ceg_mart_path = ceg_mart_path.expanduser().resolve() if ceg_mart_path is not None else None
    if resolved_ceg_mart_path is not None and not resolved_ceg_mart_path.exists():
        raise FileNotFoundError(f"CEG mart database does not exist: {resolved_ceg_mart_path}")
    resolved_entity_id = entity_id or plant_parcel_code

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with closing(_connect_readonly(source_db)) as raw_conn:
        with ExitStack() as stack:
            hot_conn = stack.enter_context(closing(_connect_readonly(hot_path)))
            ceg_mart_conn = (
                stack.enter_context(closing(_connect_readonly(resolved_ceg_mart_path)))
                if resolved_ceg_mart_path is not None
                else None
            )
            if resolved_entity_id and reference_month:
                manual_tiers = ["hot", "cold"] if tier == "all" else [tier]
                samples = [
                    _manual_sample(
                        tier=sample_tier,  # type: ignore[arg-type]
                        reference_month=reference_month,
                        entity_type=entity_type,
                        entity_id=resolved_entity_id,
                        sample_datetime=start_datetime,
                    )
                    for sample_tier in manual_tiers
                    if sample_tier in {"hot", "cold"}
                ]
            else:
                samples = _auto_samples(
                    manifest,
                    raw_conn=raw_conn,
                    hot_conn=hot_conn,
                    cold_paths=cold_paths,
                    tier=tier,
                    samples_per_tier=samples_per_tier,
                    aneel_samples_per_tier=aneel_samples_per_tier,
                    include_aneel_aggregation=include_aneel_aggregation,
                    auto_entity_type=auto_entity_type,
                )
            for sample in samples:
                try:
                    results.append(
                        _compare_sample(
                            sample,
                            manifest=manifest,
                            raw_conn=raw_conn,
                            hot_conn=hot_conn,
                            ceg_mart_conn=ceg_mart_conn,
                            cold_paths=cold_paths,
                            start_datetime=start_datetime,
                            end_datetime=end_datetime,
                            window_mode=window_mode,
                            limit=limit,
                            runs=runs,
                        )
                    )
                except Exception as exc:
                    errors.append(
                        {
                            "label": sample.get("label"),
                            "tier": sample.get("tier"),
                            "entity_type": sample.get("entity_type"),
                            "entity_id": sample.get("entity_id"),
                            "reference_month": sample.get("reference_month"),
                            "plant_parcel_code": sample.get("plant_parcel_code"),
                            "ceg": sample.get("ceg"),
                            "error": str(exc),
                        }
                    )

    source_after = _source_signature(source_db)
    source_unchanged = source_before == source_after
    matched = sum(1 for result in results if result.get("match") is True)
    mismatched = sum(1 for result in results if result.get("match") is False)
    ceg_mart_comparisons = [
        result["ceg_mart_comparison"]
        for result in results
        if result.get("ceg_mart_comparison") is not None
    ]
    ceg_mart_matched = sum(1 for comparison in ceg_mart_comparisons if comparison.get("match") is True)
    ceg_mart_mismatched = sum(1 for comparison in ceg_mart_comparisons if comparison.get("match") is False)
    ceg_mart_ok = (
        not ceg_mart_comparisons
        or (ceg_mart_matched == len(ceg_mart_comparisons) and ceg_mart_mismatched == 0)
    )
    validation_ok = bool(results and matched == len(results) and ceg_mart_ok and not errors and source_unchanged)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "phase5_hourly_read_path_comparison",
        "generated_at_utc": _utc_now(),
        "read_only_source": True,
        "manifest_path": str(resolved_manifest_path),
        "source_database": str(source_db),
        "ceg_mart_path": str(resolved_ceg_mart_path) if resolved_ceg_mart_path else None,
        "source_signature_before": source_before,
        "source_signature_after": source_after,
        "source_unchanged": source_unchanged,
        "prototype": {
            "hot_sqlite_path": str(hot_path),
            "cold_partition_months": sorted(cold_paths),
        },
        "parameters": {
            "tier": tier,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "plant_parcel_code": plant_parcel_code,
            "reference_month": reference_month,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "window_mode": window_mode,
            "limit": int(limit),
            "runs": int(runs),
            "samples_per_tier": int(samples_per_tier),
            "aneel_samples_per_tier": int(aneel_samples_per_tier),
            "include_aneel_aggregation": bool(include_aneel_aggregation),
            "auto_entity_type": auto_entity_type,
        },
        "samples": results,
        "errors": errors,
        "summary": {
            "validation_ok": validation_ok,
            "sample_count": len(results),
            "error_count": len(errors),
            "matched": matched,
            "mismatched": mismatched,
            "ceg_mart_samples": len(ceg_mart_comparisons),
            "ceg_mart_matched": ceg_mart_matched,
            "ceg_mart_mismatched": ceg_mart_mismatched,
            "hot_samples": sum(1 for result in results if result.get("tier") == "hot"),
            "cold_samples": sum(1 for result in results if result.get("tier") == "cold"),
            "parcel_samples": sum(1 for result in results if result.get("entity_type") == "ccee_plant_parcel"),
            "aneel_plant_samples": sum(1 for result in results if result.get("entity_type") == "aneel_plant"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare raw SQLite CCEE hourly reads with hot/cold prototype artifacts."
    )
    parser.add_argument("--manifest", help="Path to a hot/cold prototype manifest.json.")
    parser.add_argument("--prototype-dir", help="Prototype output directory containing manifest.json.")
    parser.add_argument("--database", help="Canonical source energy_kpis.db. Defaults to manifest source_database.")
    parser.add_argument("--ceg-mart", help="Optional diagnostic CEG hourly mart SQLite database to compare.")
    parser.add_argument(
        "--tier",
        choices=("all", "hot", "cold"),
        default="all",
        help="Which prototype tier to compare.",
    )
    parser.add_argument(
        "--entity-type",
        choices=("ccee_plant_parcel", "aneel_plant"),
        default="ccee_plant_parcel",
        help="Manual sample entity type. Ignored for automatic sampling.",
    )
    parser.add_argument("--entity-id", help="Manual sample entity ID. For aneel_plant, use CEG.")
    parser.add_argument("--plant-parcel-code", help="Manual plant parcel code sample.")
    parser.add_argument("--reference-month", help="Manual reference month sample, YYYY-MM.")
    parser.add_argument("--start-datetime", help="Manual window start datetime.")
    parser.add_argument("--end-datetime", help="Manual window end datetime.")
    parser.add_argument(
        "--window-mode",
        choices=("auto", "month", "sample_datetime"),
        default="auto",
        help="Auto uses full-month windows for full prototypes and exact sample datetimes for bounded prototypes.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Row limit, matching the chart guardrail.")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS, help="Read timing runs per sample.")
    parser.add_argument(
        "--samples-per-tier",
        type=int,
        default=DEFAULT_SAMPLES_PER_TIER,
        help="Automatic parcel samples per selected hot/cold month.",
    )
    parser.add_argument(
        "--aneel-samples-per-tier",
        type=int,
        default=DEFAULT_ANEEL_SAMPLES_PER_TIER,
        help="Automatic ANEEL CEG aggregation samples per selected hot/cold month.",
    )
    parser.add_argument(
        "--include-aneel-aggregation",
        action="store_true",
        help="Also auto-sample ANEEL CEG-level hourly aggregation cases for full-month prototypes.",
    )
    parser.add_argument(
        "--auto-entity-type",
        choices=("all", "ccee_plant_parcel", "aneel_plant"),
        default="all",
        help=(
            "Automatic sample entity type. Use aneel_plant for CEG-only "
            "aggregation benchmarks on full-month prototypes."
        ),
    )
    parser.add_argument("--output", help="Optional JSON output path. Defaults to stdout only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = compare_hourly_read_paths(
        manifest_path=Path(args.manifest).expanduser().resolve() if args.manifest else None,
        prototype_dir=Path(args.prototype_dir).expanduser().resolve() if args.prototype_dir else None,
        database=Path(args.database).expanduser().resolve() if args.database else None,
        ceg_mart_path=Path(args.ceg_mart).expanduser().resolve() if args.ceg_mart else None,
        tier=args.tier,
        entity_type=args.entity_type,
        entity_id=args.entity_id,
        plant_parcel_code=args.plant_parcel_code,
        reference_month=args.reference_month,
        start_datetime=args.start_datetime,
        end_datetime=args.end_datetime,
        window_mode=args.window_mode,
        limit=args.limit,
        runs=args.runs,
        samples_per_tier=args.samples_per_tier,
        aneel_samples_per_tier=args.aneel_samples_per_tier,
        include_aneel_aggregation=args.include_aneel_aggregation,
        auto_entity_type=args.auto_entity_type,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["summary"]["validation_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
