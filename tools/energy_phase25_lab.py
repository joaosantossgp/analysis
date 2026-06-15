from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOURLY_TABLE = "ccee_plant_parcel_hourly"
HOURLY_PK = ("plant_parcel_code", "reference_datetime", "commercialization_period")
HOURLY_QUERY_COLUMNS = [
    "plant_parcel_code",
    "reference_datetime",
    "reference_month",
    "commercialization_period",
    "generation_center_of_gravity_mwh",
    "verified_generation_ons_mwh",
    "verified_availability_mwh",
    "unavailability_mwh",
    "generation_source",
    "submarket",
    "plant_type",
    "source_dataset",
    "snapshot_id",
    "raw_payload_hash",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    sidecars = {}
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{path}{suffix}")
        sidecars[suffix] = {
            "exists": sidecar.exists(),
            "size": sidecar.stat().st_size if sidecar.exists() else 0,
            "mtime_ns": sidecar.stat().st_mtime_ns if sidecar.exists() else None,
        }
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sidecars": sidecars}


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def connect_writable(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def sqlite_cli_csv(sqlite_bin: Path, db_path: Path, sql: str) -> list[dict[str, str]]:
    command = [
        str(sqlite_bin),
        "-readonly",
        "-csv",
        "-header",
        str(db_path),
        sql,
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return list(csv.DictReader(completed.stdout.splitlines()))


def exact_dbstat(sqlite_bin: Path, db_path: Path) -> dict[str, Any]:
    page_rows = sqlite_cli_csv(
        sqlite_bin,
        db_path,
        """
        SELECT
          name,
          pagetype,
          COUNT(*) AS pages,
          SUM(pgsize) AS bytes
        FROM dbstat
        GROUP BY name, pagetype
        ORDER BY name, pagetype;
        """,
    )
    object_rows = sqlite_cli_csv(
        sqlite_bin,
        db_path,
        """
        SELECT
          name,
          COUNT(*) AS pages,
          SUM(pgsize) AS bytes,
          SUM(CASE WHEN pagetype='leaf' THEN 1 ELSE 0 END) AS leaf_pages,
          SUM(CASE WHEN pagetype='internal' THEN 1 ELSE 0 END) AS internal_pages,
          SUM(CASE WHEN pagetype='overflow' THEN 1 ELSE 0 END) AS overflow_pages
        FROM dbstat
        GROUP BY name
        ORDER BY bytes DESC;
        """,
    )
    return {"page_breakdown": page_rows, "objects": object_rows}


def index_metadata(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    out = {}
    for idx in conn.execute(f"PRAGMA index_list({safe_identifier(table_name)})"):
        name = str(idx["name"])
        cols = [
            str(row["name"])
            for row in conn.execute(f"PRAGMA index_xinfo({safe_identifier(name)})")
            if row["name"] is not None and int(row["key"] or 0) == 1
        ]
        out[name] = {
            "columns": cols,
            "unique": bool(idx["unique"]),
            "origin": idx["origin"],
            "partial": bool(idx["partial"]),
        }
    return out


def table_kind(name: str) -> str:
    if name.endswith(("_facts", "_values", "_hourly", "_monthly")):
        return "historical_fact"
    if "snapshot" in name:
        return "snapshot"
    if "refresh_log" in name or name.endswith("_log"):
        return "log"
    if "quality" in name or "conflict" in name:
        return "quality"
    if name in {"ccee_plant_parcels", "aneel_siga_plants"}:
        return "current_state"
    if name in {"energy_sources", "kpi_sources"}:
        return "dimension"
    return "metadata"


def attribution_report(sqlite_bin: Path, db_path: Path) -> dict[str, Any]:
    dbstat = exact_dbstat(sqlite_bin, db_path)
    by_name = {row["name"]: row for row in dbstat["objects"]}
    db_size = db_path.stat().st_size
    with connect_readonly(db_path) as conn:
        table_names = [
            str(row["name"])
            for row in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        ]
        table_reports = []
        index_reports = []
        for table in table_names:
            table_stats = by_name.get(table, {})
            idx_meta = index_metadata(conn, table)
            idx_names = list(idx_meta)
            idx_bytes = sum(int(by_name.get(idx, {}).get("bytes") or 0) for idx in idx_names)
            count = int(scalar(conn, f"SELECT COUNT(*) FROM {safe_identifier(table)}") or 0)
            table_bytes = int(table_stats.get("bytes") or 0)
            period_cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({safe_identifier(table)})")]
            period_col = next((c for c in ("reference_month", "reference_datetime", "period", "validity_year") if c in period_cols), None)
            min_period = max_period = None
            if period_col and count:
                min_period = scalar(conn, f"SELECT MIN({safe_identifier(period_col)}) FROM {safe_identifier(table)}")
                max_period = scalar(conn, f"SELECT MAX({safe_identifier(period_col)}) FROM {safe_identifier(table)}")
            table_reports.append(
                {
                    "name": table,
                    "kind": table_kind(table),
                    "row_count": count,
                    "table_bytes": table_bytes,
                    "index_bytes": idx_bytes,
                    "total_bytes": table_bytes + idx_bytes,
                    "table_pct": table_bytes / db_size if db_size else None,
                    "total_pct": (table_bytes + idx_bytes) / db_size if db_size else None,
                    "avg_table_bytes_per_row": table_bytes / count if count else None,
                    "avg_total_bytes_per_row": (table_bytes + idx_bytes) / count if count else None,
                    "leaf_pages": int(table_stats.get("leaf_pages") or 0),
                    "internal_pages": int(table_stats.get("internal_pages") or 0),
                    "overflow_pages": int(table_stats.get("overflow_pages") or 0),
                    "total_pages": int(table_stats.get("pages") or 0),
                    "column_count": len(period_cols),
                    "indexes": idx_names,
                    "earliest_period": min_period,
                    "latest_period": max_period,
                }
            )
            for idx_name, meta in idx_meta.items():
                idx_stats = by_name.get(idx_name, {})
                idx_bytes_exact = int(idx_stats.get("bytes") or 0)
                index_reports.append(
                    {
                        "name": idx_name,
                        "table": table,
                        "columns": meta["columns"],
                        "unique": meta["unique"],
                        "origin": meta["origin"],
                        "partial": meta["partial"],
                        "bytes": idx_bytes_exact,
                        "pages": int(idx_stats.get("pages") or 0),
                        "pct_database": idx_bytes_exact / db_size if db_size else None,
                        "pct_table_total": idx_bytes_exact / (table_bytes + idx_bytes) if (table_bytes + idx_bytes) else None,
                    }
                )
    return {
        "dbstat_tool": str(sqlite_bin),
        "database_size": db_size,
        "tables": sorted(table_reports, key=lambda row: row["total_bytes"], reverse=True),
        "indexes": sorted(index_reports, key=lambda row: row["bytes"], reverse=True),
        "raw_dbstat": dbstat,
    }


def choose_sample_scope(prod: sqlite3.Connection, parcels_per_source: int) -> dict[str, Any]:
    months = [row[0] for row in prod.execute(f"SELECT DISTINCT reference_month FROM {HOURLY_TABLE} ORDER BY reference_month")]
    chosen_months = sorted({months[0], months[len(months) // 2], months[-1]}) if months else []
    parcel_rows = rows(
        prod,
        f"""
        WITH ranked AS (
          SELECT plant_parcel_code, generation_source, COUNT(*) AS rows_in_scope,
                 ROW_NUMBER() OVER (PARTITION BY generation_source ORDER BY COUNT(*) DESC, plant_parcel_code) AS rn
          FROM {HOURLY_TABLE}
          WHERE reference_month IN ({",".join("?" for _ in chosen_months)})
          GROUP BY generation_source, plant_parcel_code
        )
        SELECT plant_parcel_code, generation_source, rows_in_scope
        FROM ranked
        WHERE rn <= ?
        ORDER BY generation_source, plant_parcel_code
        """,
        tuple(chosen_months) + (parcels_per_source,),
    )
    return {"months": chosen_months, "parcels": parcel_rows}


def create_sample_db(prod_db: Path, sample_db: Path, parcels_per_source: int) -> dict[str, Any]:
    if sample_db.exists():
        sample_db.unlink()
    with connect_readonly(prod_db) as prod:
        scope = choose_sample_scope(prod, parcels_per_source)
        parcel_codes = [row["plant_parcel_code"] for row in scope["parcels"]]
        with connect_writable(sample_db) as out:
            out.execute(f"ATTACH DATABASE ? AS prod", (f"file:{prod_db.resolve().as_posix()}?mode=ro",))
            out.execute(f"CREATE TABLE {HOURLY_TABLE} AS SELECT * FROM prod.{HOURLY_TABLE} WHERE 0")
            placeholders_months = ",".join("?" for _ in scope["months"])
            placeholders_parcels = ",".join("?" for _ in parcel_codes)
            out.execute(
                f"""
                INSERT INTO {HOURLY_TABLE}
                SELECT * FROM prod.{HOURLY_TABLE}
                WHERE reference_month IN ({placeholders_months})
                  AND plant_parcel_code IN ({placeholders_parcels})
                """,
                tuple(scope["months"]) + tuple(parcel_codes),
            )
            out.execute(f"CREATE UNIQUE INDEX idx_sample_hourly_pk ON {HOURLY_TABLE}({','.join(HOURLY_PK)})")
            out.execute(f"CREATE INDEX idx_cppe_parcel_ref ON {HOURLY_TABLE}(plant_parcel_code, reference_datetime)")
            out.execute(f"CREATE INDEX idx_cppe_ref ON {HOURLY_TABLE}(reference_datetime)")
            out.execute(f"CREATE INDEX idx_cppe_ref_month ON {HOURLY_TABLE}(reference_month)")
            out.execute(f"CREATE INDEX idx_cppe_submarket ON {HOURLY_TABLE}(submarket)")
            out.execute(f"CREATE INDEX idx_cppe_source ON {HOURLY_TABLE}(generation_source)")
            out.commit()
            row_count = scalar(out, f"SELECT COUNT(*) FROM {HOURLY_TABLE}")
    return {"sample_db": str(sample_db), "row_count": row_count, "scope": scope, "size": sample_db.stat().st_size}


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    sql: str
    params: tuple[Any, ...]


def benchmark_cases(conn: sqlite3.Connection) -> list[BenchmarkCase]:
    parcel = scalar(conn, f"SELECT plant_parcel_code FROM {HOURLY_TABLE} GROUP BY plant_parcel_code ORDER BY COUNT(*) DESC LIMIT 1")
    months = [row[0] for row in conn.execute(f"SELECT DISTINCT reference_month FROM {HOURLY_TABLE} ORDER BY reference_month")]
    month = months[-1]
    first_month = months[0]
    return [
        BenchmarkCase(
            "one_parcel_one_month",
            f"SELECT {','.join(HOURLY_QUERY_COLUMNS)} FROM {HOURLY_TABLE} WHERE plant_parcel_code=? AND reference_month=? ORDER BY reference_datetime, commercialization_period",
            (parcel, month),
        ),
        BenchmarkCase(
            "one_parcel_multi_month",
            f"SELECT reference_datetime, commercialization_period, verified_generation_ons_mwh FROM {HOURLY_TABLE} WHERE plant_parcel_code=? AND reference_month BETWEEN ? AND ? ORDER BY reference_datetime, commercialization_period",
            (parcel, first_month, month),
        ),
        BenchmarkCase(
            "several_parcels_one_month",
            f"SELECT plant_parcel_code, reference_datetime, commercialization_period, verified_generation_ons_mwh FROM {HOURLY_TABLE} WHERE reference_month=? AND plant_parcel_code IN (SELECT plant_parcel_code FROM {HOURLY_TABLE} GROUP BY plant_parcel_code ORDER BY COUNT(*) DESC LIMIT 10) ORDER BY plant_parcel_code, reference_datetime, commercialization_period",
            (month,),
        ),
        BenchmarkCase(
            "aggregate_by_month",
            f"SELECT reference_month, generation_source, SUM(verified_generation_ons_mwh) AS generation FROM {HOURLY_TABLE} GROUP BY reference_month, generation_source ORDER BY reference_month, generation_source",
            (),
        ),
        BenchmarkCase(
            "latest_reference",
            f"SELECT MAX(reference_datetime) FROM {HOURLY_TABLE}",
            (),
        ),
        BenchmarkCase(
            "available_periods",
            f"SELECT DISTINCT reference_month FROM {HOURLY_TABLE} ORDER BY reference_month",
            (),
        ),
    ]


def run_query_benchmark(conn: sqlite3.Connection, case: BenchmarkCase, runs: int) -> dict[str, Any]:
    plan = [row["detail"] for row in conn.execute(f"EXPLAIN QUERY PLAN {case.sql}", case.params)]
    timings = []
    returned = 0
    for _ in range(runs):
        start = time.perf_counter()
        result = conn.execute(case.sql, case.params).fetchall()
        timings.append((time.perf_counter() - start) * 1000)
        returned = len(result)
    return {
        "id": case.id,
        "params_shape": [type(value).__name__ for value in case.params],
        "returned_rows": returned,
        "plan": plan,
        "median_ms": statistics.median(timings),
        "p95_ms": max(timings) if len(timings) < 20 else statistics.quantiles(timings, n=20)[18],
        "runs": runs,
    }


def copy_db(src: Path, dst: Path) -> None:
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)


def sqlite_experiments(sample_db: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    configs = {
        "current": [],
        "candidate_composite": [f"CREATE INDEX idx_exp_parcel_month_time ON {HOURLY_TABLE}(plant_parcel_code, reference_month, reference_datetime, commercialization_period)"],
        "candidate_drop_overlap": [
            "DROP INDEX idx_cppe_parcel_ref",
            f"CREATE INDEX idx_exp_parcel_month_time ON {HOURLY_TABLE}(plant_parcel_code, reference_month, reference_datetime, commercialization_period)",
        ],
    }
    results = []
    for config_id, statements in configs.items():
        db_path = output_dir / f"sqlite_{config_id}.db"
        copy_db(sample_db, db_path)
        index_build_ms = 0.0
        with connect_writable(db_path) as conn:
            for statement in statements:
                start = time.perf_counter()
                conn.execute(statement)
                conn.commit()
                index_build_ms += (time.perf_counter() - start) * 1000
            cases = benchmark_cases(conn)
            bench = [run_query_benchmark(conn, case, runs=5) for case in cases]
        results.append({"config": config_id, "db_size": db_path.stat().st_size, "index_build_ms": index_build_ms, "benchmarks": bench})
    return {"results": results}


def parquet_experiments(sample_db: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    import pyarrow as pa
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    with connect_readonly(sample_db) as conn:
        frame = pd.read_sql_query(f"SELECT {','.join(HOURLY_QUERY_COLUMNS)} FROM {HOURLY_TABLE}", conn)
    frame["year"] = frame["reference_month"].str.slice(0, 4)
    frame["month"] = frame["reference_month"].str.slice(5, 7)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    strategies = {
        "year_month": ["year", "month"],
        "reference_month": ["reference_month"],
        "reference_month_source_dataset": ["reference_month", "source_dataset"],
    }
    compressions = ["snappy", "zstd"]
    results = []
    parcel = str(frame["plant_parcel_code"].iloc[0])
    ref_month = str(frame["reference_month"].max())
    for strategy_id, partition_cols in strategies.items():
        for compression in compressions:
            path = output_dir / f"parquet_{strategy_id}_{compression}"
            if path.exists():
                shutil.rmtree(path)
            start = time.perf_counter()
            pq.write_to_dataset(table, root_path=path, partition_cols=partition_cols, compression=compression)
            write_ms = (time.perf_counter() - start) * 1000
            files = list(path.rglob("*.parquet"))
            total_size = sum(p.stat().st_size for p in files)
            dataset = ds.dataset(path, format="parquet", partitioning="hive")
            query_results = []
            filters = [
                ("one_parcel_one_month", (ds.field("plant_parcel_code") == parcel) & (ds.field("reference_month") == ref_month)),
                ("one_parcel_multi_month", ds.field("plant_parcel_code") == parcel),
                ("available_periods", None),
            ]
            for query_id, filt in filters:
                timings = []
                count = 0
                for _ in range(5):
                    start = time.perf_counter()
                    scanner = dataset.scanner(filter=filt, columns=HOURLY_QUERY_COLUMNS)
                    count = scanner.count_rows()
                    timings.append((time.perf_counter() - start) * 1000)
                query_results.append({"id": query_id, "rows": count, "median_ms": statistics.median(timings), "p95_ms": max(timings)})
            results.append(
                {
                    "strategy": strategy_id,
                    "compression": compression,
                    "partition_columns": partition_cols,
                    "write_ms": write_ms,
                    "file_count": len(files),
                    "total_size": total_size,
                    "queries": query_results,
                }
            )
    return {"input_rows": len(frame), "results": results}


def hot_cold_and_manifest(sample_db: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    import pyarrow.parquet as pq

    manifest_db = output_dir / "manifest.db"
    if manifest_db.exists():
        manifest_db.unlink()
    parquet_root = output_dir / "manifest_partitions"
    if parquet_root.exists():
        shutil.rmtree(parquet_root)
    parquet_root.mkdir(parents=True)
    with connect_readonly(sample_db) as conn:
        frame = pd.read_sql_query(f"SELECT * FROM {HOURLY_TABLE}", conn)
    months = sorted(frame["reference_month"].dropna().unique().tolist())
    selected_hot = {}
    for window in (6, 12, 18, 24):
        hot_months = set(months[-min(window, len(months)):])
        hot_rows = int(frame["reference_month"].isin(hot_months).sum())
        cold_rows = int((~frame["reference_month"].isin(hot_months)).sum())
        selected_hot[str(window)] = {"hot_rows": hot_rows, "cold_rows": cold_rows}
    cold_month = months[0]
    cold_frame = frame[frame["reference_month"] == cold_month].copy()
    active_path = parquet_root / f"dataset=ccee_hourly" / f"reference_month={cold_month}" / "part-000.parquet"
    temp_path = parquet_root / "_tmp" / f"{cold_month}.parquet"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa_table_from_pandas(cold_frame), temp_path, compression="zstd")
    row_count = len(cold_frame)
    key_count = len(cold_frame[list(HOURLY_PK)].drop_duplicates())
    checksum = file_sha256(temp_path)
    if row_count != key_count:
        raise RuntimeError("sample partition has duplicate primary keys")
    os.replace(temp_path, active_path)
    with connect_writable(manifest_db) as conn:
        conn.execute(
            """
            CREATE TABLE hourly_partitions (
              partition_id TEXT PRIMARY KEY,
              dataset_id TEXT NOT NULL,
              period_start TEXT NOT NULL,
              period_end TEXT NOT NULL,
              relative_file_path TEXT NOT NULL,
              storage_format TEXT NOT NULL,
              compression TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              row_count INTEGER NOT NULL,
              file_size INTEGER NOT NULL,
              checksum_sha256 TEXT NOT NULL,
              active INTEGER NOT NULL,
              replaced_partition_id TEXT,
              validation_status TEXT NOT NULL,
              imported_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO hourly_partitions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"ccee_hourly:{cold_month}:1",
                "ccee_hourly",
                cold_month,
                cold_month,
                str(active_path.relative_to(parquet_root)),
                "parquet",
                "zstd",
                1,
                row_count,
                active_path.stat().st_size,
                checksum,
                1,
                None,
                "valid",
                utc_now(),
            ),
        )
        conn.commit()
    with connect_readonly(sample_db) as conn:
        sqlite_keys = set(tuple(row) for row in conn.execute(f"SELECT {','.join(HOURLY_PK)} FROM {HOURLY_TABLE} WHERE reference_month=?", (cold_month,)))
    parquet_keys = set(tuple(row) for row in cold_frame[list(HOURLY_PK)].itertuples(index=False, name=None))
    return {
        "hot_windows": selected_hot,
        "manifest_db": str(manifest_db),
        "partition_file": str(active_path),
        "partition_rows": row_count,
        "partition_size": active_path.stat().st_size,
        "cross_boundary_parity": {
            "cold_month": cold_month,
            "sqlite_key_count": len(sqlite_keys),
            "parquet_key_count": len(parquet_keys),
            "missing_in_parquet": len(sqlite_keys - parquet_keys),
            "extra_in_parquet": len(parquet_keys - sqlite_keys),
        },
    }


def pa_table_from_pandas(frame: Any) -> Any:
    import pyarrow as pa

    return pa.Table.from_pandas(frame, preserve_index=False)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_reports(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "energy_phase25_results.json"
    md_path = output_dir / "energy_phase25_audit.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def markdown(report: dict[str, Any]) -> str:
    hourly = next((row for row in report["attribution"]["tables"] if row["name"] == HOURLY_TABLE), {})
    lines = [
        "# Energy Database Phase 2.5 Audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Production database: `{report['production_db']}`",
        f"- Production unchanged: `{report['production_unchanged']}`",
        f"- SQLite dbstat tool: `{report['attribution']['dbstat_tool']}`",
        "",
        "## Exact Hourly Attribution",
        "",
        f"- Table bytes: `{hourly.get('table_bytes')}`",
        f"- Index bytes: `{hourly.get('index_bytes')}`",
        f"- Total bytes: `{hourly.get('total_bytes')}`",
        f"- Rows: `{hourly.get('row_count')}`",
        f"- Table bytes per row: `{hourly.get('avg_table_bytes_per_row')}`",
        f"- Total bytes per row: `{hourly.get('avg_total_bytes_per_row')}`",
        "",
        "## Top Tables",
        "",
        "| Table | Rows | Table bytes | Index bytes | Total bytes |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in report["attribution"]["tables"][:12]:
        lines.append(f"| `{row['name']}` | {row['row_count']} | {row['table_bytes']} | {row['index_bytes']} | {row['total_bytes']} |")
    lines.extend(["", "## Top Indexes", "", "| Index | Table | Columns | Bytes |", "|---|---|---|---:|"])
    for row in report["attribution"]["indexes"][:12]:
        lines.append(f"| `{row['name']}` | `{row['table']}` | {', '.join(row['columns'])} | {row['bytes']} |")
    lines.extend(["", "## SQLite Experiments"])
    for config in report["sqlite_experiments"]["results"]:
        lines.append(f"- `{config['config']}`: size `{config['db_size']}`, index build `{config['index_build_ms']:.2f}` ms")
        for bench in config["benchmarks"]:
            lines.append(f"  - `{bench['id']}`: median `{bench['median_ms']:.2f}` ms, p95 `{bench['p95_ms']:.2f}` ms, rows `{bench['returned_rows']}`")
    lines.extend(["", "## Parquet Experiments"])
    for item in report["parquet_experiments"]["results"]:
        lines.append(f"- `{item['strategy']}` / `{item['compression']}`: `{item['total_size']}` bytes, files `{item['file_count']}`, write `{item['write_ms']:.2f}` ms")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2.5 Energy DB optimization lab. Production DB is read-only.")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--sqlite", type=Path, required=True, help="Path to sqlite3.exe with ENABLE_DBSTAT_VTAB.")
    parser.add_argument("--output-dir", type=Path, default=Path("docs") / "diagnostics" / "energy-phase25")
    parser.add_argument("--work-dir", type=Path, default=None, help="Disposable artifact directory. Defaults outside the repo.")
    parser.add_argument("--parcels-per-source", type=int, default=12)
    args = parser.parse_args()
    if args.db is None:
        from src.platform.settings import get_settings

        args.db = Path(get_settings().paths.energy_kpi_db_path)
    work_dir = args.work_dir or Path(tempfile.mkdtemp(prefix="cvma_energy_phase25_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    before = file_signature(args.db)
    with connect_readonly(args.db) as conn:
        production_checks = {
            "schema_version": scalar(conn, "PRAGMA schema_version"),
            "page_count": scalar(conn, "PRAGMA page_count"),
            "hourly_rows": scalar(conn, f"SELECT COUNT(*) FROM {HOURLY_TABLE}"),
            "sample_months": rows(conn, f"SELECT reference_month, COUNT(*) AS rows FROM {HOURLY_TABLE} GROUP BY reference_month ORDER BY reference_month"),
        }
    attribution = attribution_report(args.sqlite, args.db)
    sample = create_sample_db(args.db, work_dir / "energy_hourly_sample.db", args.parcels_per_source)
    sqlite_results = sqlite_experiments(Path(sample["sample_db"]), work_dir)
    parquet_results = parquet_experiments(Path(sample["sample_db"]), work_dir)
    hot_cold_results = hot_cold_and_manifest(Path(sample["sample_db"]), work_dir)
    after = file_signature(args.db)
    report = {
        "generated_at": utc_now(),
        "production_db": str(args.db),
        "work_dir": str(work_dir),
        "production_before": before,
        "production_after": after,
        "production_unchanged": before == after,
        "production_checks": production_checks,
        "attribution": attribution,
        "sample": sample,
        "sqlite_experiments": sqlite_results,
        "parquet_experiments": parquet_results,
        "hot_cold_manifest": hot_cold_results,
        "runtime": {
            "python": sys.executable,
            "platform": sys.platform,
            "sqlite3_module": sqlite3.sqlite_version,
        },
    }
    paths = write_reports(report, args.output_dir)
    print(json.dumps({"reports": paths, "work_dir": str(work_dir), "production_unchanged": before == after}, indent=2))


if __name__ == "__main__":
    main()
