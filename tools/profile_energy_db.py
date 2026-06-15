from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> tuple[list[dict[str, Any]], float]:
    start = time.perf_counter()
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    return rows, (time.perf_counter() - start) * 1000


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, float]:
    start = time.perf_counter()
    row = conn.execute(sql, params).fetchone()
    return (row[0] if row else None), (time.perf_counter() - start) * 1000


def _explain(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[str]:
    try:
        return [str(row["detail"]) for row in conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()]
    except Exception as exc:
        return [f"EXPLAIN unavailable: {exc}"]


def _safe_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_kind(name: str) -> str:
    if name.startswith("sqlite_"):
        return "internal"
    if name.endswith("_facts") or name.endswith("_values") or name.endswith("_hourly") or name.endswith("_monthly"):
        return "historical_fact"
    if name.endswith("_aggregates"):
        return "aggregate"
    if "refresh_log" in name or name.endswith("_log"):
        return "log"
    if "snapshot" in name:
        return "snapshot"
    if "quality" in name or "conflict" in name:
        return "quality"
    if "dimension" in name or name in {"energy_sources", "kpi_sources"}:
        return "dimension"
    if name in {"ccee_plant_parcels", "aneel_siga_plants"}:
        return "current_state"
    return "metadata"


def _index_columns(conn: sqlite3.Connection, index_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA index_xinfo({_safe_identifier(index_name)})").fetchall()
    return [str(row["name"]) for row in rows if row["name"] is not None and int(row["key"] or 0) == 1]


def _table_index_metadata(conn: sqlite3.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(f"PRAGMA index_list({_safe_identifier(table_name)})").fetchall()
    return {
        str(row["name"]): {
            "unique": bool(row["unique"]),
            "origin": row["origin"],
            "partial": bool(row["partial"]),
        }
        for row in rows
    }


def _has_dbstat(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name LIMIT 1").fetchall()
        return True
    except sqlite3.DatabaseError:
        return False


def _dbstat_sizes(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    rows = conn.execute("""
        SELECT name, SUM(pgsize) AS bytes, COUNT(*) AS pages
        FROM dbstat
        GROUP BY name
    """).fetchall()
    return {str(row["name"]): {"bytes": int(row["bytes"] or 0), "pages": int(row["pages"] or 0)} for row in rows}


def _period_columns(columns: list[str]) -> list[str]:
    preferred = [
        "reference_month",
        "reference_year",
        "reference_datetime",
        "period",
        "validity_year",
        "valid_from",
        "started_at",
        "created_at",
    ]
    return [col for col in preferred if col in columns]


def _source_columns(columns: list[str]) -> list[str]:
    preferred = ["source_dataset", "source", "source_id", "dataset_name", "metric_name", "generation_source"]
    return [col for col in preferred if col in columns]


def _period_expr(column: str) -> str:
    if column in {"period", "reference_year", "validity_year"}:
        return f"CAST({column} AS TEXT)"
    if column in {"reference_datetime", "started_at", "created_at", "valid_from"}:
        return f"substr({column}, 1, 7)"
    return column


REPRESENTATIVE_QUERIES = [
    {
        "id": "plant_parcel_detail_latest",
        "owner": "EnergyKPIReadService.get_plant_parcel_detail",
        "sql": "SELECT * FROM ccee_plant_parcels WHERE plant_parcel_code = (SELECT plant_parcel_code FROM ccee_plant_parcels LIMIT 1)",
    },
    {
        "id": "plant_monthly_series_by_parcel",
        "owner": "EnergyKPIReadService.get_plant_parcel_chart_data monthly",
        "sql": "SELECT reference_month, capacity_mw, physical_guarantee_mwmed, generation_center_of_gravity_mwmed FROM ccee_plant_parcel_monthly WHERE plant_parcel_code = (SELECT plant_parcel_code FROM ccee_plant_parcel_monthly LIMIT 1) ORDER BY reference_month ASC",
    },
    {
        "id": "plant_hourly_series_by_parcel_month",
        "owner": "EnergyKPIReadService.get_plant_parcel_chart_data hourly",
        "sql": "SELECT reference_datetime, commercialization_period, generation_center_of_gravity_mwh, verified_generation_ons_mwh, verified_availability_mwh, unavailability_mwh FROM ccee_plant_parcel_hourly WHERE plant_parcel_code = (SELECT plant_parcel_code FROM ccee_plant_parcel_hourly LIMIT 1) AND reference_month = (SELECT reference_month FROM ccee_plant_parcel_hourly LIMIT 1) ORDER BY reference_datetime ASC, commercialization_period ASC",
    },
    {
        "id": "sin_latest_reference",
        "owner": "EnergyKPIReadService.get_sin_kpi_health",
        "sql": "SELECT MAX(reference_datetime) FROM subsystem_kpi_values",
    },
    {
        "id": "distribution_distributor_series",
        "owner": "DistributionReadService.get_series",
        "sql": "SELECT reference_month, metric_name, normalized_value FROM distribution_market_facts WHERE distributor_id = (SELECT distributor_id FROM distribution_market_facts LIMIT 1) ORDER BY reference_month",
    },
]


def profile_database(db_path: Path, *, output_dir: Path, expensive: bool) -> dict[str, Any]:
    before = _file_signature(db_path)
    with _connect_readonly(db_path) as conn:
        dbstat_available = _has_dbstat(conn)
        dbstat = _dbstat_sizes(conn) if dbstat_available else {}
        sqlite_version, sqlite_version_ms = _scalar(conn, "SELECT sqlite_version()")
        pragmas = {}
        for name in ("journal_mode", "page_size", "page_count", "freelist_count", "schema_version", "user_version"):
            value, elapsed = _scalar(conn, f"PRAGMA {name}")
            pragmas[name] = {"value": value, "elapsed_ms": elapsed}

        tables_raw, _ = _query(conn, "SELECT name, sql FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        indexes_raw, _ = _query(conn, "SELECT name, tbl_name, sql FROM sqlite_schema WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name")
        index_by_table: dict[str, list[dict[str, Any]]] = {}
        for idx in indexes_raw:
            table_name = str(idx["tbl_name"])
            metadata = _table_index_metadata(conn, table_name).get(str(idx["name"]), {})
            idx["columns"] = _index_columns(conn, str(idx["name"]))
            idx["unique"] = metadata.get("unique")
            idx["origin"] = metadata.get("origin")
            idx["partial"] = metadata.get("partial")
            idx["bytes"] = dbstat.get(str(idx["name"]), {}).get("bytes")
            idx["pages"] = dbstat.get(str(idx["name"]), {}).get("pages")
            index_by_table.setdefault(table_name, []).append(idx)

        tables: list[dict[str, Any]] = []
        distributions: dict[str, Any] = {}
        for table in tables_raw:
            name = str(table["name"])
            columns = [dict(row) for row in conn.execute(f"PRAGMA table_info({_safe_identifier(name)})").fetchall()]
            indexes = index_by_table.get(name, [])
            row_count, row_count_ms = _scalar(conn, f"SELECT COUNT(*) FROM {_safe_identifier(name)}")
            table_bytes = int(dbstat.get(name, {}).get("bytes") or 0) if dbstat_available else None
            index_bytes = sum(int(idx.get("bytes") or 0) for idx in indexes) if dbstat_available else None
            total_bytes = (table_bytes or 0) + (index_bytes or 0) if dbstat_available else None
            row_count_int = int(row_count or 0)
            tables.append({
                "name": name,
                "kind": _table_kind(name),
                "row_count": row_count_int,
                "row_count_elapsed_ms": row_count_ms,
                "table_bytes": table_bytes,
                "index_bytes": index_bytes,
                "total_bytes": total_bytes,
                "avg_table_bytes_per_row": (table_bytes / row_count_int) if table_bytes is not None and row_count_int else None,
                "columns": [{"name": col["name"], "type": col["type"], "pk": col["pk"]} for col in columns],
                "column_count": len(columns),
                "indexes": [idx["name"] for idx in indexes],
                "index_count": len(indexes),
                "create_sql": table["sql"],
            })
            if row_count_int and (expensive or row_count_int < 5_000_000):
                col_names = [str(col["name"]) for col in columns]
                distributions[name] = _table_distributions(conn, name, col_names)

        indexes = []
        for idx in indexes_raw:
            name = str(idx["name"])
            table_name = str(idx["tbl_name"])
            indexes.append({
                "name": name,
                "table": table_name,
                "columns": idx.get("columns") or [],
                "unique": idx.get("unique"),
                "origin": idx.get("origin"),
                "partial": idx.get("partial"),
                "bytes": dbstat.get(name, {}).get("bytes") if dbstat_available else None,
                "pages": dbstat.get(name, {}).get("pages") if dbstat_available else None,
                "create_sql": idx.get("sql"),
                "overlap_candidates": _overlap_candidates(name, table_name, idx.get("columns") or [], index_by_table),
            })

        query_profiles = []
        for case in REPRESENTATIVE_QUERIES:
            plan = _explain(conn, case["sql"])
            try:
                rows, elapsed = _query(conn, case["sql"])
                query_profiles.append({
                    **case,
                    "plan": plan,
                    "elapsed_ms": elapsed,
                    "returned_rows": len(rows),
                    "error": None,
                })
            except Exception as exc:
                query_profiles.append({
                    **case,
                    "plan": plan,
                    "elapsed_ms": None,
                    "returned_rows": 0,
                    "error": str(exc),
                })

    after = _file_signature(db_path)
    report = {
        "contract_version": 1,
        "generated_at": _utc_now(),
        "database_path": str(db_path.resolve()),
        "before_signature": before,
        "after_signature": after,
        "read_only": True,
        "sqlite_version": sqlite_version,
        "sqlite_version_elapsed_ms": sqlite_version_ms,
        "dbstat_available": dbstat_available,
        "pragmas": pragmas,
        "tables": sorted(tables, key=lambda row: int(row.get("total_bytes") or row.get("row_count") or 0), reverse=True),
        "indexes": sorted(indexes, key=lambda row: int(row.get("bytes") or 0), reverse=True),
        "distributions": distributions,
        "query_profiles": query_profiles,
        "notes": [
            "Connection uses SQLite URI mode=ro.",
            "No VACUUM, REINDEX, schema change, temporary table, checkpoint, or write pragma is executed.",
            "dbstat bytes are exact page attribution when dbstat is available.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "energy_db_profile.json"
    md_path = output_dir / "energy_db_profile.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    report["json_report_path"] = str(json_path)
    report["markdown_report_path"] = str(md_path)
    return report


def _table_distributions(conn: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"plans": {}}
    for col in _period_columns(columns)[:1]:
        expr = _period_expr(col)
        sql = f"SELECT {expr} AS period, COUNT(*) AS rows FROM {_safe_identifier(table)} GROUP BY {expr} ORDER BY period"
        out["plans"][f"period:{col}"] = _explain(conn, sql)
        rows, elapsed = _query(conn, sql)
        out["period"] = {"column": col, "elapsed_ms": elapsed, "rows": rows[:500], "truncated": len(rows) > 500}
    for col in _source_columns(columns)[:2]:
        sql = f"SELECT {_safe_identifier(col)} AS value, COUNT(*) AS rows FROM {_safe_identifier(table)} GROUP BY {_safe_identifier(col)} ORDER BY rows DESC LIMIT 50"
        out["plans"][f"source:{col}"] = _explain(conn, sql)
        rows, elapsed = _query(conn, sql)
        out.setdefault("sources", []).append({"column": col, "elapsed_ms": elapsed, "rows": rows})
    return out


def _overlap_candidates(index_name: str, table_name: str, columns: list[str], by_table: dict[str, list[dict[str, Any]]]) -> list[str]:
    candidates = []
    if not columns:
        return candidates
    for other in by_table.get(table_name, []):
        other_name = str(other["name"])
        other_cols = list(other.get("columns") or [])
        if other_name == index_name or len(other_cols) <= len(columns):
            continue
        if other_cols[: len(columns)] == columns:
            candidates.append(other_name)
    return candidates


def _file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    sidecars = {}
    for suffix in ("-wal", "-shm", "-journal"):
        p = Path(f"{path}{suffix}")
        sidecars[suffix] = {"exists": p.exists(), "size": p.stat().st_size if p.exists() else 0, "mtime_ns": p.stat().st_mtime_ns if p.exists() else None}
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sidecars": sidecars}


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Energy Database Profile",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Database: `{report['database_path']}`",
        f"- Read-only: `{report['read_only']}`",
        f"- dbstat available: `{report['dbstat_available']}`",
        f"- File size: `{report['before_signature']['size']}` bytes",
        "",
        "## Top Tables",
        "",
        "| Table | Kind | Rows | Table bytes | Index bytes | Total bytes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["tables"][:20]:
        lines.append(f"| `{row['name']}` | {row['kind']} | {row['row_count']} | {row['table_bytes']} | {row['index_bytes']} | {row['total_bytes']} |")
    lines.extend(["", "## Top Indexes", "", "| Index | Table | Columns | Bytes | Overlap candidates |", "|---|---|---|---:|---|"])
    for row in report["indexes"][:30]:
        lines.append(f"| `{row['name']}` | `{row['table']}` | {', '.join(row['columns'])} | {row['bytes']} | {', '.join(row['overlap_candidates']) or ''} |")
    lines.extend(["", "## Query Profiles", "", "| Query | Owner | Rows | Elapsed ms | Plan |", "|---|---|---:|---:|---|"])
    for row in report["query_profiles"]:
        plan = "<br>".join(row["plan"])
        elapsed = row["elapsed_ms"]
        elapsed_text = "" if elapsed is None else f"{elapsed:.2f}"
        if row.get("error"):
            plan = f"{plan}<br>Error: {row['error']}"
        lines.append(f"| `{row['id']}` | {row['owner']} | {row['returned_rows']} | {elapsed_text} | {plan} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only profile of CVMAnalytics energy_kpis.db")
    parser.add_argument("--db", type=Path, default=None, help="Path to energy_kpis.db. Defaults to resolved AppSettings path.")
    parser.add_argument("--output-dir", type=Path, default=Path("docs") / "diagnostics" / "energy-db-profile")
    parser.add_argument("--expensive", action="store_true", help="Run period/source distributions for all non-empty tables.")
    args = parser.parse_args()
    if args.db is None:
        from src.platform.settings import get_settings
        args.db = Path(get_settings().paths.energy_kpi_db_path)
    report = profile_database(args.db, output_dir=args.output_dir, expensive=args.expensive)
    print(json.dumps({
        "json_report_path": report["json_report_path"],
        "markdown_report_path": report["markdown_report_path"],
        "database_size": report["before_signature"]["size"],
        "dbstat_available": report["dbstat_available"],
        "tables": len(report["tables"]),
        "indexes": len(report["indexes"]),
    }, indent=2))


if __name__ == "__main__":
    main()
