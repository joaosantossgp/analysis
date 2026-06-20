# -*- coding: utf-8 -*-
"""Create and validate a compact copy of the local Energy KPI SQLite database.

This script is intentionally non-destructive: it writes a separate database
with SQLite VACUUM INTO and never swaps it into the live data root.

Examples:
    python scripts/data/compact_energy_db.py --output %TEMP%\\energy_kpis.compact.db
    python scripts/data/compact_energy_db.py --database C:\\path\\energy_kpis.db --output C:\\path\\energy_kpis.compact.db
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings


KEY_TABLES = (
    "plant_parcel_daily_generation_mart",
    "plant_parcel_hourly_preview_mart",
    "energy_mart_builds",
    "source_snapshots",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a compact, validated copy of energy_kpis.db."
    )
    parser.add_argument(
        "--database",
        help="Source energy_kpis.db path. Defaults to the configured Energy KPI database.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Destination compact database path. The destination must not already exist unless --replace-output is used.",
    )
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help="Delete an existing output file before compacting. Never deletes the source database.",
    )
    parser.add_argument(
        "--full-integrity-check",
        action="store_true",
        help="Run PRAGMA integrity_check on the compacted output. This can be very slow on large databases.",
    )
    parser.add_argument(
        "--skip-integrity-check",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--exact-hourly-count",
        action="store_true",
        help="Also exact-count ccee_plant_parcel_hourly in source and output. This can be slow on large databases.",
    )
    return parser.parse_args()


def _default_energy_db_path() -> Path:
    env_data_dir = os.environ.get("CVM_DATA_DIR")
    if env_data_dir:
        return Path(env_data_dir).expanduser().resolve() / "db" / "energy_kpis.db"

    documents_db = (
        Path.home()
        / "Documents"
        / "CVMAnalytics"
        / "db"
        / "energy_kpis.db"
    )
    if documents_db.exists():
        return documents_db.resolve()

    settings = build_settings(project_root=ROOT)
    return Path(settings.paths.energy_kpi_db_path).expanduser().resolve()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _safe_count(conn: sqlite3.Connection, table_name: str) -> int | None:
    if not _table_exists(conn, table_name):
        return None
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _page_stats(conn: sqlite3.Connection, path: Path) -> dict[str, Any]:
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "free_bytes": page_size * freelist_count,
    }


def _indexes(conn: sqlite3.Connection) -> list[str]:
    if not _table_exists(conn, "ccee_plant_parcel_hourly"):
        return []
    return [
        str(row[1])
        for row in conn.execute("PRAGMA index_list(ccee_plant_parcel_hourly)").fetchall()
    ]


def _hourly_signature(conn: sqlite3.Connection, *, exact_count: bool) -> dict[str, Any] | None:
    if not _table_exists(conn, "ccee_plant_parcel_hourly"):
        return None
    signature = dict(conn.execute("""
        SELECT MAX(rowid) AS max_rowid,
               MIN(reference_datetime) AS first_reference_datetime,
               MAX(reference_datetime) AS last_reference_datetime,
               MIN(reference_month) AS first_reference_month,
               MAX(reference_month) AS last_reference_month
        FROM ccee_plant_parcel_hourly
    """).fetchone())
    if exact_count:
        signature["exact_row_count"] = int(
            conn.execute("SELECT COUNT(*) FROM ccee_plant_parcel_hourly").fetchone()[0]
        )
    return signature


def _summarize(path: Path, *, exact_hourly_count: bool) -> dict[str, Any]:
    with _connect_readonly(path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            "pages": _page_stats(conn, path),
            "key_table_counts": {
                table_name: _safe_count(conn, table_name)
                for table_name in KEY_TABLES
            },
            "hourly_signature": _hourly_signature(conn, exact_count=exact_hourly_count),
            "hourly_indexes": _indexes(conn),
        }


def _validate_output(
    source: Path,
    output: Path,
    *,
    full_integrity_check: bool,
    exact_hourly_count: bool,
) -> dict[str, Any]:
    source_summary = _summarize(source, exact_hourly_count=exact_hourly_count)
    output_summary = _summarize(output, exact_hourly_count=exact_hourly_count)
    mismatches: list[dict[str, Any]] = []

    for table_name in KEY_TABLES:
        source_count = source_summary["key_table_counts"].get(table_name)
        output_count = output_summary["key_table_counts"].get(table_name)
        if source_count != output_count:
            mismatches.append({
                "table": table_name,
                "source_count": source_count,
                "output_count": output_count,
            })
    if source_summary["hourly_signature"] != output_summary["hourly_signature"]:
        mismatches.append({
            "table": "ccee_plant_parcel_hourly",
            "source_signature": source_summary["hourly_signature"],
            "output_signature": output_summary["hourly_signature"],
        })

    integrity = "not_run"
    if full_integrity_check:
        with _connect_readonly(output) as conn:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            mismatches.append({"integrity_check": integrity})

    source_size = int(source_summary["pages"]["size_bytes"])
    output_size = int(output_summary["pages"]["size_bytes"])
    return {
        "source": source_summary,
        "output": output_summary,
        "integrity_check": integrity,
        "size_delta_bytes": output_size - source_size,
        "size_reduction_bytes": source_size - output_size,
        "mismatches": mismatches,
        "ok": not mismatches,
    }


def main() -> int:
    args = parse_args()
    source = Path(args.database).expanduser().resolve() if args.database else _default_energy_db_path()
    output = Path(args.output).expanduser().resolve()

    if not source.exists():
        raise SystemExit(f"Source database does not exist: {source}")
    if output == source:
        raise SystemExit("Output path must be different from the source database.")
    if output.exists():
        if not args.replace_output:
            raise SystemExit(f"Output already exists: {output}. Use --replace-output to overwrite it.")
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    source_size = source.stat().st_size
    free_space = shutil.disk_usage(output.parent).free
    required_space = int(source_size * 1.05)
    if free_space < required_space:
        raise SystemExit(
            f"Not enough free space in {output.parent}. "
            f"Need at least {required_space} bytes, found {free_space} bytes."
        )

    start = time.perf_counter()
    with _connect_readonly(source) as conn:
        conn.execute("VACUUM INTO ?", (str(output),))
    elapsed_ms = (time.perf_counter() - start) * 1000

    result = _validate_output(
        source,
        output,
        full_integrity_check=args.full_integrity_check and not args.skip_integrity_check,
        exact_hourly_count=args.exact_hourly_count,
    )
    result["elapsed_ms"] = round(elapsed_ms, 2)
    result["source_database"] = str(source)
    result["output_database"] = str(output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
