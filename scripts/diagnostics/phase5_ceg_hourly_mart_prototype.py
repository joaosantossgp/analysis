#!/usr/bin/env python3
"""Build a diagnostic CEG-level hourly aggregation mart.

This is a Phase 5 prototype artifact only. It opens the source
``energy_kpis.db`` read-only, writes a separate SQLite database, and records a
manifest. It does not migrate, compact, or modify source/runtime data.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import HOURLY_TABLE  # noqa: E402
from src.platform.settings import build_settings  # noqa: E402


SCHEMA_VERSION = 1
CEG_MART_TABLE = "ceg_hourly_generation_mart"
PLANT_PARCELS_TABLE = "ccee_plant_parcels"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_energy_db_path() -> Path:
    return build_settings(project_root=ROOT).paths.energy_kpi_db_path.expanduser().resolve()


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _load_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def _months_from_manifest(manifest: dict[str, Any] | None) -> list[str]:
    if manifest is None:
        return []
    selection = manifest.get("selection", {})
    months = [str(month) for month in selection.get("hot_months", [])]
    months.extend(str(month) for month in selection.get("cold_months", []))
    return list(dict.fromkeys(month for month in months if month.strip()))


def _source_db_from_manifest(manifest: dict[str, Any] | None) -> Path | None:
    if manifest is None or not manifest.get("source_database"):
        return None
    return Path(str(manifest["source_database"])).expanduser().resolve()


def _validate_output_path(output_path: Path, source_db: Path, *, replace_output: bool) -> None:
    output_path = output_path.expanduser().resolve()
    source_db = source_db.expanduser().resolve()
    if output_path == source_db:
        raise ValueError("Output mart path must not be the source database.")
    if output_path.exists():
        if not replace_output:
            raise FileExistsError(f"Output mart already exists: {output_path}. Use --replace-output.")
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE {CEG_MART_TABLE} (
            ceg TEXT NOT NULL,
            reference_month TEXT NOT NULL,
            reference_datetime TEXT NOT NULL,
            commercialization_period INTEGER NOT NULL,
            generation_mwh REAL,
            verified_generation_mwh REAL,
            verified_availability_mwh REAL,
            unavailability_mwh REAL,
            plant_parcel_count INTEGER NOT NULL
        )
        """
    )


def _insert_month(conn: sqlite3.Connection, reference_month: str) -> int:
    before = int(conn.execute(f"SELECT COUNT(*) FROM {CEG_MART_TABLE}").fetchone()[0])
    conn.execute(
        f"""
        INSERT INTO {CEG_MART_TABLE} (
            ceg,
            reference_month,
            reference_datetime,
            commercialization_period,
            generation_mwh,
            verified_generation_mwh,
            verified_availability_mwh,
            unavailability_mwh,
            plant_parcel_count
        )
        SELECT
            p.ceg AS ceg,
            h.reference_month AS reference_month,
            h.reference_datetime AS reference_datetime,
            h.commercialization_period AS commercialization_period,
            SUM(h.generation_center_of_gravity_mwh) AS generation_mwh,
            SUM(h.verified_generation_ons_mwh) AS verified_generation_mwh,
            SUM(h.verified_availability_mwh) AS verified_availability_mwh,
            SUM(h.unavailability_mwh) AS unavailability_mwh,
            COUNT(DISTINCT h.plant_parcel_code) AS plant_parcel_count
        FROM source.{HOURLY_TABLE} h
        JOIN source.{PLANT_PARCELS_TABLE} p ON p.plant_parcel_code = h.plant_parcel_code
        WHERE h.reference_month = ?
          AND p.ceg IS NOT NULL
          AND TRIM(p.ceg) <> ''
        GROUP BY p.ceg, h.reference_month, h.reference_datetime, h.commercialization_period
        """,
        (reference_month,),
    )
    after = int(conn.execute(f"SELECT COUNT(*) FROM {CEG_MART_TABLE}").fetchone()[0])
    return after - before


def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE UNIQUE INDEX idx_ceg_hourly_mart_lookup
        ON {CEG_MART_TABLE}(ceg, reference_month, reference_datetime, commercialization_period)
        """
    )
    conn.execute(
        f"""
        CREATE INDEX idx_ceg_hourly_mart_month
        ON {CEG_MART_TABLE}(reference_month, ceg)
        """
    )


def build_ceg_hourly_mart_prototype(
    *,
    database: Path | None = None,
    output_path: Path,
    reference_months: Iterable[str] | None = None,
    manifest_path: Path | None = None,
    replace_output: bool = False,
) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    source_db = (database or _source_db_from_manifest(manifest) or _default_energy_db_path()).expanduser().resolve()
    if not source_db.exists():
        raise FileNotFoundError(f"Source energy database does not exist: {source_db}")

    months = [str(month).strip() for month in (reference_months or []) if str(month).strip()]
    if not months:
        months = _months_from_manifest(manifest)
    months = list(dict.fromkeys(months))
    if not months:
        raise ValueError("At least one reference month is required.")

    output_path = output_path.expanduser().resolve()
    _validate_output_path(output_path, source_db, replace_output=replace_output)

    source_before = _source_signature(source_db)
    month_counts: dict[str, int] = {}
    start = time.perf_counter()
    with closing(sqlite3.connect(f"file:{output_path.as_posix()}?mode=rwc", uri=True)) as conn:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("ATTACH DATABASE ? AS source", (_sqlite_readonly_uri(source_db),))
        _create_schema(conn)
        for month in months:
            month_counts[month] = _insert_month(conn, month)
            conn.commit()
        _create_indexes(conn)
        conn.commit()
        quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        conn.execute("DETACH DATABASE source")
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    source_after = _source_signature(source_db)
    source_unchanged = source_before == source_after
    artifact = {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
        "months": months,
        "row_counts": month_counts,
        "total_rows": sum(month_counts.values()),
        "quick_check": quick_check,
        "elapsed_ms": elapsed_ms,
        "ok": quick_check.lower() == "ok" and all(count > 0 for count in month_counts.values()),
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "mode": "phase5_ceg_hourly_mart_prototype",
        "generated_at_utc": _utc_now(),
        "read_only_source": True,
        "source_database": str(source_db),
        "source_signature_before": source_before,
        "source_signature_after": source_after,
        "source_unchanged": source_unchanged,
        "artifact": artifact,
        "validation": {
            "ok": bool(source_unchanged and artifact["ok"]),
            "source_unchanged": source_unchanged,
            "artifact_ok": artifact["ok"],
        },
    }
    manifest_output_path = output_path.with_suffix(".manifest.json")
    result["artifact"]["manifest_path"] = str(manifest_output_path)
    manifest_output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a diagnostic CEG hourly aggregation mart.")
    parser.add_argument("--database", help="Canonical source energy_kpis.db. Defaults to manifest source or project DB.")
    parser.add_argument("--manifest", help="Optional hot/cold manifest to derive source DB and selected months.")
    parser.add_argument("--output", required=True, help="Output SQLite path for the diagnostic CEG mart.")
    parser.add_argument(
        "--reference-month",
        action="append",
        default=[],
        help="Reference month to aggregate, YYYY-MM. Repeat for multiple months.",
    )
    parser.add_argument("--replace-output", action="store_true", help="Replace an existing output mart.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_ceg_hourly_mart_prototype(
        database=Path(args.database).expanduser().resolve() if args.database else None,
        output_path=Path(args.output).expanduser().resolve(),
        reference_months=args.reference_month,
        manifest_path=Path(args.manifest).expanduser().resolve() if args.manifest else None,
        replace_output=args.replace_output,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["validation"]["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
