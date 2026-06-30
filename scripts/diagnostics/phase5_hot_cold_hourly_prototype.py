#!/usr/bin/env python3
"""Build a bounded hot/cold prototype for CCEE hourly storage.

This is a diagnostic prototype, not a migration. It reads the source
``energy_kpis.db`` with a read-only SQLite connection, writes a separate hot
SQLite database for selected recent months, writes selected cold months as
partitioned Parquet, and records a manifest with validation counts.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from contextlib import closing
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings  # noqa: E402


SCHEMA_VERSION = 1
HOURLY_TABLE = "ccee_plant_parcel_hourly"
DEFAULT_HOT_MONTHS = 1
DEFAULT_COLD_MONTH_LIMIT = 1
DEFAULT_MAX_ROWS_PER_MONTH = 100_000
DEFAULT_CHUNK_SIZE = 50_000
ORDER_COLUMNS = (
    "reference_datetime",
    "commercialization_period",
    "plant_parcel_code",
)
HOT_STORE_EXTRA_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_cppe_hot_parcel_month_datetime
    ON ccee_plant_parcel_hourly (
        plant_parcel_code,
        reference_month,
        reference_datetime,
        commercialization_period
    )
    """,
)
ParquetWriter = Callable[
    [sqlite3.Connection, str, list[str], Path, int | None, int],
    dict[str, Any],
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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

    return build_settings(project_root=ROOT).paths.energy_kpi_db_path.expanduser().resolve()


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _source_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    if row is None or not row["sql"]:
        raise ValueError(f"Table not found or has no SQL: {table_name}")
    return str(row["sql"])


def _index_sql(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type='index' AND tbl_name=? AND sql IS NOT NULL
        ORDER BY name
        """,
        (table_name,),
    ).fetchall()
    return [str(row["sql"]) for row in rows if row["sql"]]


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    return [str(row["name"]) for row in rows]


def _month_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT reference_month, COUNT(*) AS row_count
        FROM {_quote_identifier(HOURLY_TABLE)}
        GROUP BY reference_month
        ORDER BY reference_month
        """
    ).fetchall()
    return [
        {
            "reference_month": str(row["reference_month"]),
            "row_count": int(row["row_count"]),
        }
        for row in rows
    ]


def _select_months(
    month_counts: list[dict[str, Any]],
    *,
    hot_months: int,
    cold_months: Iterable[str] | None,
    cold_month_limit: int,
) -> tuple[list[str], list[str]]:
    months = [row["reference_month"] for row in month_counts]
    hot_selection = months[-max(0, hot_months):] if hot_months else []

    if cold_months:
        requested = [str(month).strip() for month in cold_months if str(month).strip()]
        missing = [month for month in requested if month not in months]
        if missing:
            raise ValueError(f"Cold month(s) not available in source: {', '.join(missing)}")
        cold_selection = requested
    else:
        hot_set = set(hot_selection)
        candidates = [month for month in months if month not in hot_set]
        cold_selection = candidates[:max(0, cold_month_limit)]
    return hot_selection, cold_selection


def _validate_output_dir(output_dir: Path, source_db: Path, *, replace_output: bool) -> None:
    output_dir = output_dir.resolve()
    source_db = source_db.resolve()
    if output_dir == source_db or output_dir == source_db.parent:
        raise ValueError("Output directory must not be the source database or its DB directory.")
    if output_dir in source_db.parents:
        raise ValueError("Output directory must not be an ancestor of the source database.")

    if output_dir.exists():
        if not replace_output:
            raise FileExistsError(
                f"Output directory already exists: {output_dir}. Use --replace-output to overwrite it."
            )
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)


def _iter_month_rows(
    conn: sqlite3.Connection,
    month: str,
    columns: list[str],
    *,
    row_limit: int | None,
    chunk_size: int,
) -> Iterable[list[sqlite3.Row]]:
    selected_cols = ", ".join(_quote_identifier(column) for column in columns)
    order_cols = ", ".join(_quote_identifier(column) for column in ORDER_COLUMNS)
    limit_clause = "" if row_limit is None else " LIMIT ?"
    params: list[Any] = [month]
    if row_limit is not None:
        params.append(int(row_limit))
    cursor = conn.execute(
        f"""
        SELECT {selected_cols}
        FROM {_quote_identifier(HOURLY_TABLE)}
        WHERE reference_month = ?
        ORDER BY {order_cols}
        {limit_clause}
        """,
        params,
    )
    while True:
        rows = cursor.fetchmany(max(1, int(chunk_size)))
        if not rows:
            break
        yield rows


def _selected_expected(source_count: int, row_limit: int | None) -> int:
    return int(source_count) if row_limit is None else min(int(source_count), int(row_limit))


def _copy_hot_months(
    source_conn: sqlite3.Connection,
    hot_db_path: Path,
    *,
    table_sql: str,
    index_sql: list[str],
    columns: list[str],
    month_counts: dict[str, int],
    hot_months: list[str],
    row_limit: int | None,
    chunk_size: int,
) -> dict[str, Any]:
    hot_db_path.parent.mkdir(parents=True, exist_ok=True)
    if hot_db_path.exists():
        hot_db_path.unlink()

    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f"INSERT INTO {_quote_identifier(HOURLY_TABLE)} "
        f"({', '.join(_quote_identifier(column) for column in columns)}) "
        f"VALUES ({placeholders})"
    )
    counts: dict[str, int] = {}
    start = time.perf_counter()
    with closing(sqlite3.connect(hot_db_path)) as hot_conn:
        hot_conn.execute(table_sql)
        for month in hot_months:
            copied = 0
            for rows in _iter_month_rows(
                source_conn,
                month,
                columns,
                row_limit=row_limit,
                chunk_size=chunk_size,
            ):
                hot_conn.executemany(insert_sql, [tuple(row[column] for column in columns) for row in rows])
                copied += len(rows)
            counts[month] = copied
        for sql in index_sql:
            hot_conn.execute(sql)
        for sql in HOT_STORE_EXTRA_INDEXES:
            hot_conn.execute(sql)
        hot_conn.commit()
        quick_check = str(hot_conn.execute("PRAGMA quick_check").fetchone()[0])
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    expected_counts = {
        month: _selected_expected(month_counts[month], row_limit)
        for month in hot_months
    }
    return {
        "path": str(hot_db_path),
        "size_bytes": hot_db_path.stat().st_size if hot_db_path.exists() else 0,
        "months": hot_months,
        "row_counts": counts,
        "expected_row_counts": expected_counts,
        "quick_check": quick_check,
        "elapsed_ms": elapsed_ms,
        "ok": quick_check.lower() == "ok" and counts == expected_counts,
    }


def _default_parquet_writer(
    source_conn: sqlite3.Connection,
    month: str,
    columns: list[str],
    month_dir: Path,
    row_limit: int | None,
    chunk_size: int,
) -> dict[str, Any]:
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires polars. Install project requirements or pass a test writer."
        ) from exc

    month_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    parts: list[dict[str, Any]] = []
    for part_idx, rows in enumerate(
        _iter_month_rows(
            source_conn,
            month,
            columns,
            row_limit=row_limit,
            chunk_size=chunk_size,
        )
    ):
        tuples = [tuple(row[column] for column in columns) for row in rows]
        frame = pl.DataFrame(
            tuples,
            schema=columns,
            orient="row",
            infer_schema_length=None,
        )
        part_path = month_dir / f"part-{part_idx:04d}.parquet"
        frame.write_parquet(part_path)
        written += len(rows)
        parts.append(
            {
                "path": str(part_path),
                "row_count": len(rows),
                "size_bytes": part_path.stat().st_size,
            }
        )
    return {
        "reference_month": month,
        "path": str(month_dir),
        "row_count": written,
        "parts": parts,
    }


def _write_cold_months(
    source_conn: sqlite3.Connection,
    cold_root: Path,
    *,
    columns: list[str],
    month_counts: dict[str, int],
    cold_months: list[str],
    row_limit: int | None,
    chunk_size: int,
    parquet_writer: ParquetWriter | None,
) -> dict[str, Any]:
    writer = parquet_writer or _default_parquet_writer
    partitions: list[dict[str, Any]] = []
    start = time.perf_counter()
    for month in cold_months:
        month_dir = cold_root / HOURLY_TABLE / f"reference_month={month}"
        partition = writer(source_conn, month, columns, month_dir, row_limit, chunk_size)
        partition["expected_row_count"] = _selected_expected(month_counts[month], row_limit)
        partition["ok"] = int(partition["row_count"]) == int(partition["expected_row_count"])
        partitions.append(partition)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "path": str(cold_root),
        "months": cold_months,
        "partitions": partitions,
        "elapsed_ms": elapsed_ms,
        "ok": all(partition["ok"] for partition in partitions),
    }


def build_hot_cold_prototype(
    *,
    database: Path | None = None,
    output_dir: Path,
    hot_months: int = DEFAULT_HOT_MONTHS,
    cold_months: Iterable[str] | None = None,
    cold_month_limit: int = DEFAULT_COLD_MONTH_LIMIT,
    max_rows_per_month: int = DEFAULT_MAX_ROWS_PER_MONTH,
    full_months: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    replace_output: bool = False,
    parquet_writer: ParquetWriter | None = None,
) -> dict[str, Any]:
    source_db = (database or _default_energy_db_path()).expanduser().resolve()
    if not source_db.exists():
        raise FileNotFoundError(f"Source energy database does not exist: {source_db}")

    output_dir = output_dir.expanduser().resolve()
    _validate_output_dir(output_dir, source_db, replace_output=replace_output)

    source_before = _source_signature(source_db)
    row_limit = None if full_months else max(1, int(max_rows_per_month))
    with closing(_connect_readonly(source_db)) as source_conn:
        if not _table_exists(source_conn, HOURLY_TABLE):
            raise ValueError(f"Missing source table: {HOURLY_TABLE}")
        table_sql = _table_sql(source_conn, HOURLY_TABLE)
        index_sql = _index_sql(source_conn, HOURLY_TABLE)
        columns = _table_columns(source_conn, HOURLY_TABLE)
        counts_list = _month_counts(source_conn)
        month_count_map = {
            row["reference_month"]: int(row["row_count"])
            for row in counts_list
        }
        selected_hot_months, selected_cold_months = _select_months(
            counts_list,
            hot_months=max(0, int(hot_months)),
            cold_months=cold_months,
            cold_month_limit=max(0, int(cold_month_limit)),
        )
        hot = _copy_hot_months(
            source_conn,
            output_dir / "hot" / "energy_hot.sqlite",
            table_sql=table_sql,
            index_sql=index_sql,
            columns=columns,
            month_counts=month_count_map,
            hot_months=selected_hot_months,
            row_limit=row_limit,
            chunk_size=chunk_size,
        )
        cold = _write_cold_months(
            source_conn,
            output_dir / "cold",
            columns=columns,
            month_counts=month_count_map,
            cold_months=selected_cold_months,
            row_limit=row_limit,
            chunk_size=chunk_size,
            parquet_writer=parquet_writer,
        )

    source_after = _source_signature(source_db)
    source_unchanged = source_before == source_after
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "mode": "copy_based_hot_cold_hourly_prototype",
        "generated_at_utc": _utc_now(),
        "read_only_source": True,
        "source_database": str(source_db),
        "source_signature_before": source_before,
        "source_signature_after": source_after,
        "source_unchanged": source_unchanged,
        "selection": {
            "available_months": counts_list,
            "hot_months": selected_hot_months,
            "cold_months": selected_cold_months,
            "row_limit_per_month": row_limit,
            "full_months": bool(full_months),
            "chunk_size": int(chunk_size),
        },
        "artifacts": {
            "output_dir": str(output_dir),
            "hot": hot,
            "cold": cold,
        },
        "validation": {
            "ok": bool(source_unchanged and hot["ok"] and cold["ok"]),
            "source_unchanged": source_unchanged,
            "hot_ok": hot["ok"],
            "cold_ok": cold["ok"],
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["artifacts"]["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a bounded CCEE hourly hot/cold storage prototype from a read-only source DB."
    )
    parser.add_argument(
        "--database",
        help="Source energy_kpis.db. Defaults to the configured Documents database.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Prototype output directory. Must not be the source DB directory.",
    )
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help="Replace an existing prototype output directory. Never deletes the source database.",
    )
    parser.add_argument(
        "--hot-months",
        type=int,
        default=DEFAULT_HOT_MONTHS,
        help="Number of latest months to copy into the hot SQLite prototype.",
    )
    parser.add_argument(
        "--cold-month",
        action="append",
        default=[],
        help="Specific cold month to export, YYYY-MM. Can repeat. Defaults to oldest available month.",
    )
    parser.add_argument(
        "--cold-month-limit",
        type=int,
        default=DEFAULT_COLD_MONTH_LIMIT,
        help="Number of oldest non-hot months to export when --cold-month is omitted.",
    )
    parser.add_argument(
        "--max-rows-per-month",
        type=int,
        default=DEFAULT_MAX_ROWS_PER_MONTH,
        help="Bounded prototype row cap per selected month. Ignored with --full-months.",
    )
    parser.add_argument(
        "--full-months",
        action="store_true",
        help="Copy/export full selected months. Use only with enough disk space and time.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Rows per SQLite fetch/write chunk.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_hot_cold_prototype(
        database=Path(args.database).expanduser().resolve() if args.database else None,
        output_dir=Path(args.output_dir),
        hot_months=args.hot_months,
        cold_months=args.cold_month or None,
        cold_month_limit=args.cold_month_limit,
        max_rows_per_month=args.max_rows_per_month,
        full_months=args.full_months,
        chunk_size=args.chunk_size,
        replace_output=args.replace_output,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0 if manifest["validation"]["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
