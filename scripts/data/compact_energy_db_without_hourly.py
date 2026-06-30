#!/usr/bin/env python3
"""Create a compact Energy KPI DB copy after hourly facts move out of SQLite.

The source database is opened read-only. The output is a separate SQLite file.
No live database is replaced by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings  # noqa: E402

HOURLY_TABLE = "ccee_plant_parcel_hourly"
EXTERNAL_HOURLY_STORE_CATALOG = "external_hourly_store_catalog"
REQUIRED_MANIFEST_RELATIVE = Path("analytics") / "energy" / "ccee_plant_generation_hourly" / "manifest.json"


def _default_energy_db_path() -> Path:
    env_data_dir = os.environ.get("CVM_DATA_DIR")
    if env_data_dir:
        return Path(env_data_dir).expanduser().resolve() / "db" / "energy_kpis.db"
    documents_db = Path.home() / "Documents" / "CVMAnalytics" / "db" / "energy_kpis.db"
    if documents_db.exists():
        return documents_db.resolve()
    return Path(build_settings(project_root=ROOT).paths.energy_kpi_db_path).expanduser().resolve()


def _default_manifest_path(source_db: Path) -> Path:
    data_root = source_db.parent.parent
    return data_root / REQUIRED_MANIFEST_RELATIVE


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("validation", {}).get("ok") is not True:
        raise ValueError(f"Hourly store manifest is not valid: {path}")
    if payload.get("selection", {}).get("full_months") is not True:
        raise ValueError(f"Hourly store manifest is not a full-month export: {path}")
    return payload


def _manifest_row_counts(manifest: dict[str, Any]) -> dict[str, int]:
    rows = manifest.get("selection", {}).get("available_months") or []
    counts: dict[str, int] = {}
    for row in rows:
        month = str(row.get("reference_month") or "").strip()
        if month:
            counts[month] = int(row.get("row_count") or 0)
    return counts


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_external_hourly_catalog(
    conn: sqlite3.Connection,
    *,
    source: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> None:
    counts = _manifest_row_counts(manifest)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EXTERNAL_HOURLY_STORE_CATALOG} (
            dataset TEXT PRIMARY KEY,
            manifest_path TEXT NOT NULL,
            manifest_fingerprint TEXT NOT NULL,
            source_database TEXT NOT NULL,
            full_months INTEGER NOT NULL,
            manifest_row_count INTEGER NOT NULL,
            available_months_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        f"""
        INSERT OR REPLACE INTO {EXTERNAL_HOURLY_STORE_CATALOG}
            (dataset, manifest_path, manifest_fingerprint, source_database, full_months,
             manifest_row_count, available_months_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            HOURLY_TABLE,
            str(manifest_path),
            _manifest_fingerprint(manifest),
            str(source),
            1 if manifest.get("selection", {}).get("full_months") is True else 0,
            sum(counts.values()),
            json.dumps(counts, sort_keys=True, separators=(",", ":")),
        ),
    )


def _external_hourly_catalog_matches(conn: sqlite3.Connection, manifest: dict[str, Any]) -> bool:
    if not _table_exists(conn, EXTERNAL_HOURLY_STORE_CATALOG):
        return False
    row = conn.execute(
        f"""
        SELECT manifest_fingerprint, full_months, manifest_row_count, available_months_json
        FROM {EXTERNAL_HOURLY_STORE_CATALOG}
        WHERE dataset = ?
        """,
        (HOURLY_TABLE,),
    ).fetchone()
    if row is None:
        return False
    counts = _manifest_row_counts(manifest)
    try:
        catalog_counts = json.loads(str(row["available_months_json"] or "{}"))
    except json.JSONDecodeError:
        return False
    normalized_counts = {str(month): int(count or 0) for month, count in dict(catalog_counts).items()}
    return (
        str(row["manifest_fingerprint"]) == _manifest_fingerprint(manifest)
        and int(row["full_months"] or 0) == 1
        and int(row["manifest_row_count"] or 0) == sum(counts.values())
        and normalized_counts == counts
    )


def _daily_mart_counts(conn: sqlite3.Connection) -> dict[str, int]:
    if not _table_exists(conn, "plant_parcel_daily_generation_mart"):
        return {}
    rows = conn.execute(
        """
        SELECT reference_month, SUM(hourly_observations) AS row_count
        FROM plant_parcel_daily_generation_mart
        GROUP BY reference_month
        ORDER BY reference_month
        """
    ).fetchall()
    return {str(row["reference_month"]): int(row["row_count"] or 0) for row in rows}


def _table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row["name"])
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]


def _schema_rows(conn: sqlite3.Connection, object_type: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type=?
          AND sql IS NOT NULL
        ORDER BY name
        """,
        (object_type,),
    ).fetchall()


def _create_schema(source_conn: sqlite3.Connection, output_conn: sqlite3.Connection) -> None:
    for row in _schema_rows(source_conn, "table"):
        table_name = str(row["name"])
        if table_name == HOURLY_TABLE:
            continue
        output_conn.execute(str(row["sql"]))
    for row in _schema_rows(source_conn, "index"):
        if str(row["tbl_name"]) == HOURLY_TABLE:
            continue
        output_conn.execute(str(row["sql"]))
    for object_type in ("view", "trigger"):
        for row in _schema_rows(source_conn, object_type):
            if str(row["tbl_name"]) == HOURLY_TABLE:
                continue
            output_conn.execute(str(row["sql"]))


def _copy_table(source_conn: sqlite3.Connection, output_conn: sqlite3.Connection, table_name: str) -> int:
    columns = [
        str(row["name"])
        for row in source_conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    ]
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    output_conn.execute(
        f"""
        INSERT INTO {_quote_identifier(table_name)} ({quoted_columns})
        SELECT {quoted_columns}
        FROM src.{_quote_identifier(table_name)}
        """
    )
    return int(output_conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}").fetchone()[0])


def _sqlite_counts(conn: sqlite3.Connection, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in table_names:
        counts[table_name] = int(
            conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}").fetchone()[0]
        )
    return counts


def _validate(
    source: Path,
    output: Path,
    manifest: dict[str, Any],
    *,
    integrity_check: bool,
) -> dict[str, Any]:
    with closing(_connect_readonly(source)) as source_conn, closing(_connect_readonly(output)) as output_conn:
        output_system_tables = {EXTERNAL_HOURLY_STORE_CATALOG}
        source_tables = [table for table in _table_names(source_conn) if table != HOURLY_TABLE]
        output_tables = [table for table in _table_names(output_conn) if table not in output_system_tables]
        source_counts = _sqlite_counts(source_conn, source_tables)
        output_counts = _sqlite_counts(output_conn, output_tables)
        manifest_counts = _manifest_row_counts(manifest)
        mart_counts = _daily_mart_counts(output_conn)
        mismatches: list[dict[str, Any]] = []
        if sorted(source_tables) != sorted(output_tables):
            mismatches.append({"tables": {"source": sorted(source_tables), "output": sorted(output_tables)}})
        for table_name, source_count in source_counts.items():
            output_count = output_counts.get(table_name)
            if source_count != output_count:
                mismatches.append({"table": table_name, "source_count": source_count, "output_count": output_count})
        if _table_exists(output_conn, HOURLY_TABLE):
            mismatches.append({"table": HOURLY_TABLE, "error": "hourly table exists in compact output"})
        if not _external_hourly_catalog_matches(output_conn, manifest):
            mismatches.append({"table": EXTERNAL_HOURLY_STORE_CATALOG, "error": "catalog missing or mismatched"})
        if manifest_counts != mart_counts:
            mismatches.append({"hourly_manifest_counts": manifest_counts, "daily_mart_counts": mart_counts})
        quick_check = None
        if integrity_check:
            quick_check = str(output_conn.execute("PRAGMA integrity_check").fetchone()[0])
            if quick_check.lower() != "ok":
                mismatches.append({"integrity_check": quick_check})
    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "source_size_bytes": source.stat().st_size,
        "output_size_bytes": output.stat().st_size,
        "size_reduction_bytes": source.stat().st_size - output.stat().st_size,
        "integrity_check": quick_check or "not_run",
        "manifest_hourly_rows": sum(_manifest_row_counts(manifest).values()),
        "output_daily_mart_hourly_rows": sum(mart_counts.values()),
    }


def create_compact_without_hourly(
    *,
    source: Path,
    output: Path,
    manifest_path: Path,
    replace_output: bool,
    integrity_check: bool,
) -> dict[str, Any]:
    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    if output == source:
        raise ValueError("Output must be different from source.")
    if output.exists():
        if not replace_output:
            raise FileExistsError(f"Output exists: {output}")
        output.unlink()
    if output.with_suffix(output.suffix + "-wal").exists():
        output.with_suffix(output.suffix + "-wal").unlink()
    if output.with_suffix(output.suffix + "-shm").exists():
        output.with_suffix(output.suffix + "-shm").unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(manifest_path)
    start = time.perf_counter()
    with closing(_connect_readonly(source)) as source_conn:
        source_mart_counts = _daily_mart_counts(source_conn)
        manifest_counts = _manifest_row_counts(manifest)
        if source_mart_counts != manifest_counts:
            raise ValueError("Manifest hourly row counts do not match source daily mart coverage.")
        with sqlite3.connect(str(output), timeout=30, uri=True) as output_conn:
            output_conn.row_factory = sqlite3.Row
            output_conn.execute("PRAGMA foreign_keys = OFF")
            output_conn.execute("PRAGMA journal_mode = OFF")
            output_conn.execute("PRAGMA synchronous = OFF")
            output_conn.execute(f"ATTACH DATABASE ? AS src", (f"file:{source.as_posix()}?mode=ro",))
            try:
                _create_schema(source_conn, output_conn)
                copied: dict[str, int] = {}
                for table_name in _table_names(source_conn):
                    if table_name == HOURLY_TABLE:
                        continue
                    copied[table_name] = _copy_table(source_conn, output_conn, table_name)
                _write_external_hourly_catalog(
                    output_conn,
                    source=source,
                    manifest_path=manifest_path,
                    manifest=manifest,
                )
                output_conn.commit()
                output_conn.execute("DETACH DATABASE src")
                output_conn.execute("VACUUM")
            finally:
                try:
                    output_conn.execute("DETACH DATABASE src")
                except Exception:
                    pass
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    validation = _validate(source, output, manifest, integrity_check=integrity_check)
    validation.update(
        {
            "source_database": str(source),
            "output_database": str(output),
            "manifest_path": str(manifest_path),
            "elapsed_ms": elapsed_ms,
        }
    )
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a compact energy_kpis.db copy without raw CCEE hourly facts.")
    parser.add_argument("--database", help="Source energy_kpis.db. Defaults to configured Documents database.")
    parser.add_argument("--manifest", help="Validated hourly store manifest. Defaults to the managed hourly store manifest.")
    parser.add_argument("--output", required=True, help="Destination candidate database path.")
    parser.add_argument("--replace-output", action="store_true", help="Replace an existing output candidate.")
    parser.add_argument("--integrity-check", action="store_true", help="Run full PRAGMA integrity_check on the output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.database).expanduser().resolve() if args.database else _default_energy_db_path()
    manifest = Path(args.manifest).expanduser().resolve() if args.manifest else _default_manifest_path(source)
    result = create_compact_without_hourly(
        source=source,
        output=Path(args.output),
        manifest_path=manifest,
        replace_output=bool(args.replace_output),
        integrity_check=bool(args.integrity_check),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
