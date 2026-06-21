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
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import HOURLY_TABLE  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_LIMIT = 2_000
DEFAULT_RUNS = 1
NUMERIC_TOLERANCE = 1e-9
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
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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


def _first_sqlite_sample(conn: sqlite3.Connection, reference_month: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"""
        SELECT plant_parcel_code, reference_month, reference_datetime
        FROM {HOURLY_TABLE}
        WHERE reference_month = ?
        ORDER BY reference_datetime ASC, commercialization_period ASC, plant_parcel_code ASC
        LIMIT 1
        """,
        (reference_month,),
    ).fetchone()
    return dict(row) if row else None


def _first_cold_sample(part_paths: list[Path]) -> dict[str, Any] | None:
    if not part_paths:
        return None
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("Cold Parquet comparison requires polars.") from exc

    frame = (
        pl.scan_parquet([str(path) for path in part_paths])
        .select(["plant_parcel_code", "reference_month", "reference_datetime", "commercialization_period"])
        .sort(["reference_datetime", "commercialization_period", "plant_parcel_code"])
        .limit(1)
        .collect()
    )
    if frame.height == 0:
        return None
    return {
        "plant_parcel_code": str(frame[0, "plant_parcel_code"]),
        "reference_month": str(frame[0, "reference_month"]),
        "reference_datetime": str(frame[0, "reference_datetime"]),
    }


def _manual_sample(
    *,
    tier: Tier,
    reference_month: str,
    plant_parcel_code: str,
    sample_datetime: str | None,
) -> dict[str, Any]:
    return {
        "label": f"manual_{tier}_{reference_month}_{plant_parcel_code}",
        "tier": tier,
        "reference_month": reference_month,
        "plant_parcel_code": plant_parcel_code,
        "sample_datetime": sample_datetime,
    }


def _auto_samples(
    manifest: dict[str, Any],
    *,
    hot_conn: sqlite3.Connection | None,
    cold_paths: dict[str, list[Path]],
    tier: str,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    selected_hot = [str(month) for month in manifest.get("selection", {}).get("hot_months", [])]
    selected_cold = [str(month) for month in manifest.get("selection", {}).get("cold_months", [])]

    if tier in {"all", "hot"} and hot_conn is not None:
        for month in selected_hot:
            sample = _first_sqlite_sample(hot_conn, month)
            if sample:
                samples.append(
                    {
                        "label": f"auto_hot_{month}_{sample['plant_parcel_code']}",
                        "tier": "hot",
                        "reference_month": month,
                        "plant_parcel_code": str(sample["plant_parcel_code"]),
                        "sample_datetime": str(sample["reference_datetime"]),
                    }
                )

    if tier in {"all", "cold"}:
        for month in selected_cold:
            sample = _first_cold_sample(cold_paths.get(month, []))
            if sample:
                samples.append(
                    {
                        "label": f"auto_cold_{month}_{sample['plant_parcel_code']}",
                        "tier": "cold",
                        "reference_month": month,
                        "plant_parcel_code": str(sample["plant_parcel_code"]),
                        "sample_datetime": str(sample["reference_datetime"]),
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


def _compare_sample(
    sample: dict[str, Any],
    *,
    manifest: dict[str, Any],
    raw_conn: sqlite3.Connection,
    hot_conn: sqlite3.Connection | None,
    cold_paths: dict[str, list[Path]],
    start_datetime: str | None,
    end_datetime: str | None,
    window_mode: WindowMode,
    limit: int,
    runs: int,
) -> dict[str, Any]:
    tier = str(sample["tier"])
    reference_month = str(sample["reference_month"])
    plant_parcel_code = str(sample["plant_parcel_code"])
    start_value, end_value, resolved_window_mode = _resolve_window(
        manifest=manifest,
        reference_month=reference_month,
        sample_datetime=sample.get("sample_datetime"),
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        window_mode=window_mode,
    )
    bounded_limit = max(1, int(limit or DEFAULT_LIMIT))

    raw = _timed_read(
        lambda: _rows_from_sqlite(
            raw_conn,
            plant_parcel_code=plant_parcel_code,
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
        candidate = _timed_read(
            lambda: _rows_from_sqlite(
                hot_conn,
                plant_parcel_code=plant_parcel_code,
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
        candidate = _timed_read(
            lambda: _read_cold_rows(
                part_paths,
                plant_parcel_code=plant_parcel_code,
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
    return {
        "label": sample.get("label"),
        "tier": tier,
        "reference_month": reference_month,
        "plant_parcel_code": plant_parcel_code,
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


def compare_hourly_read_paths(
    *,
    manifest_path: Path | None = None,
    prototype_dir: Path | None = None,
    database: Path | None = None,
    tier: str = "all",
    plant_parcel_code: str | None = None,
    reference_month: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    window_mode: WindowMode = "auto",
    limit: int = DEFAULT_LIMIT,
    runs: int = DEFAULT_RUNS,
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
    samples: list[dict[str, Any]]
    if plant_parcel_code and reference_month:
        manual_tiers = ["hot", "cold"] if tier == "all" else [tier]
        samples = [
            _manual_sample(
                tier=sample_tier,  # type: ignore[arg-type]
                reference_month=reference_month,
                plant_parcel_code=plant_parcel_code,
                sample_datetime=start_datetime,
            )
            for sample_tier in manual_tiers
            if sample_tier in {"hot", "cold"}
        ]
    else:
        with closing(_connect_readonly(hot_path)) as hot_conn:
            samples = _auto_samples(
                manifest,
                hot_conn=hot_conn,
                cold_paths=cold_paths,
                tier=tier,
            )

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    with closing(_connect_readonly(source_db)) as raw_conn:
        hot_conn_ctx = closing(_connect_readonly(hot_path))
        with hot_conn_ctx as hot_conn:
            for sample in samples:
                try:
                    results.append(
                        _compare_sample(
                            sample,
                            manifest=manifest,
                            raw_conn=raw_conn,
                            hot_conn=hot_conn,
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
                            "reference_month": sample.get("reference_month"),
                            "plant_parcel_code": sample.get("plant_parcel_code"),
                            "error": str(exc),
                        }
                    )

    source_after = _source_signature(source_db)
    source_unchanged = source_before == source_after
    matched = sum(1 for result in results if result.get("match") is True)
    mismatched = sum(1 for result in results if result.get("match") is False)
    validation_ok = bool(results and matched == len(results) and not errors and source_unchanged)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "phase5_hourly_read_path_comparison",
        "generated_at_utc": _utc_now(),
        "read_only_source": True,
        "manifest_path": str(resolved_manifest_path),
        "source_database": str(source_db),
        "source_signature_before": source_before,
        "source_signature_after": source_after,
        "source_unchanged": source_unchanged,
        "prototype": {
            "hot_sqlite_path": str(hot_path),
            "cold_partition_months": sorted(cold_paths),
        },
        "parameters": {
            "tier": tier,
            "plant_parcel_code": plant_parcel_code,
            "reference_month": reference_month,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "window_mode": window_mode,
            "limit": int(limit),
            "runs": int(runs),
        },
        "samples": results,
        "errors": errors,
        "summary": {
            "validation_ok": validation_ok,
            "sample_count": len(results),
            "error_count": len(errors),
            "matched": matched,
            "mismatched": mismatched,
            "hot_samples": sum(1 for result in results if result.get("tier") == "hot"),
            "cold_samples": sum(1 for result in results if result.get("tier") == "cold"),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare raw SQLite CCEE hourly reads with hot/cold prototype artifacts."
    )
    parser.add_argument("--manifest", help="Path to a hot/cold prototype manifest.json.")
    parser.add_argument("--prototype-dir", help="Prototype output directory containing manifest.json.")
    parser.add_argument("--database", help="Canonical source energy_kpis.db. Defaults to manifest source_database.")
    parser.add_argument(
        "--tier",
        choices=("all", "hot", "cold"),
        default="all",
        help="Which prototype tier to compare.",
    )
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
    parser.add_argument("--output", help="Optional JSON output path. Defaults to stdout only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = compare_hourly_read_paths(
        manifest_path=Path(args.manifest).expanduser().resolve() if args.manifest else None,
        prototype_dir=Path(args.prototype_dir).expanduser().resolve() if args.prototype_dir else None,
        database=Path(args.database).expanduser().resolve() if args.database else None,
        tier=args.tier,
        plant_parcel_code=args.plant_parcel_code,
        reference_month=args.reference_month,
        start_datetime=args.start_datetime,
        end_datetime=args.end_datetime,
        window_mode=args.window_mode,
        limit=args.limit,
        runs=args.runs,
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
