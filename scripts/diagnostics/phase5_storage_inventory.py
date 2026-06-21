#!/usr/bin/env python3
"""Read-only local storage inventory for Phase 5 planning.

This diagnostic intentionally opens SQLite databases in read-only mode and
collects filesystem/database metadata for planning. It does not compact,
checkpoint, analyze, migrate, or modify live data.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings  # noqa: E402


SCHEMA_VERSION = 1
DBSTAT_TABLE = "dbstat"
DEFAULT_MAX_FOLDER_FILES = 50_000
DEFAULT_MAX_FOLDER_DEPTH = 8

SAFE_COUNT_TABLES_BY_DB: dict[str, set[str]] = {
    "cvm_financials": {
        "companies",
        "company_refresh_status",
        "company_financial_directory_mart",
        "company_financial_period_mart",
        "company_kpi_account_mart",
        "financial_mart_builds",
        "market_cap_snapshots",
        "market_history_refresh_status",
    },
    "energy_kpis": {
        "energy_mart_builds",
        "plant_parcel_daily_generation_mart",
        "plant_parcel_hourly_preview_mart",
        "plant_parcel_source_submarket_monthly_mart",
        "source_snapshots",
    },
    "news": {
        "news_sources",
        "news_articles",
        "news_refresh_status",
        "news_classification_rules",
    },
}

NEVER_DEFAULT_COUNT_TABLES = {
    "ccee_plant_parcel_hourly",
    "financial_reports",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _mtime_utc(path: Path) -> str | None:
    if not path.exists():
        return None
    return (
        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _default_data_dir() -> Path:
    return build_settings().paths.data_dir.expanduser().resolve()


def _resolve_paths(data_dir_arg: str | None) -> tuple[Path, dict[str, Path], dict[str, Path]]:
    if data_dir_arg:
        data_dir = Path(data_dir_arg).expanduser().resolve()
        db_dir = data_dir / "db"
        databases = {
            "cvm_financials": db_dir / "cvm_financials.db",
            "energy_kpis": db_dir / "energy_kpis.db",
            "news": db_dir / "news.db",
        }
    else:
        settings = build_settings()
        data_dir = settings.paths.data_dir.expanduser().resolve()
        databases = {
            "cvm_financials": settings.paths.db_path.expanduser().resolve(),
            "energy_kpis": settings.paths.energy_kpi_db_path.expanduser().resolve(),
            "news": settings.paths.news_db_path.expanduser().resolve(),
        }

    folders = {
        "data_root": data_dir,
        "db": data_dir / "db",
        "input_raw": data_dir / "input" / "raw",
        "input_processed": data_dir / "input" / "processed",
        "raw": data_dir / "raw",
        "cache": data_dir / "cache",
        "metadata": data_dir / "metadata",
        "output": data_dir / "output",
        "logs": data_dir / "logs",
    }
    return data_dir, databases, folders


def _sqlite_readonly_uri(path: Path) -> str:
    return f"file:{path.as_posix()}?mode=ro"


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(_sqlite_readonly_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _file_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "size_bytes": 0,
            "mtime_utc": None,
        }
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime_utc": _mtime_utc(path),
    }


def _sidecar_summary(db_path: Path) -> dict[str, Any]:
    wal = Path(str(db_path) + "-wal")
    shm = Path(str(db_path) + "-shm")
    wal_summary = _file_summary(wal)
    shm_summary = _file_summary(shm)
    return {
        "wal": wal_summary,
        "shm": shm_summary,
        "total_size_bytes": int(wal_summary["size_bytes"]) + int(shm_summary["size_bytes"]),
    }


def _sqlite_page_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    return {
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "estimated_free_bytes": page_size * freelist_count,
    }


def _sqlite_master_inventory(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT type, name, tbl_name, rootpage, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'view', 'trigger')
        ORDER BY type, name
        """
    ).fetchall()
    inventory: dict[str, list[dict[str, Any]]] = {
        "tables": [],
        "indexes": [],
        "views": [],
        "triggers": [],
    }
    for row in rows:
        item = {
            "name": row["name"],
            "table": row["tbl_name"],
            "rootpage": row["rootpage"],
            "sql": row["sql"],
        }
        if row["type"] == "table":
            inventory["tables"].append(item)
        elif row["type"] == "index":
            inventory["indexes"].append(item)
        elif row["type"] == "view":
            inventory["views"].append(item)
        elif row["type"] == "trigger":
            inventory["triggers"].append(item)
    return inventory


def _collect_dbstat(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = conn.execute(
            f"""
            SELECT name,
                   SUM(pgsize) AS bytes,
                   COUNT(*) AS pages,
                   SUM(payload) AS payload_bytes,
                   SUM(unused) AS unused_bytes
            FROM {DBSTAT_TABLE}
            GROUP BY name
            ORDER BY bytes DESC, name
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        return {
            "available": False,
            "error": str(exc),
            "source": "python_sqlite",
            "objects": [],
        }

    return {
        "available": True,
        "error": None,
        "source": "python_sqlite",
        "objects": [
            {
                "name": row["name"],
                "bytes": int(row["bytes"] or 0),
                "pages": int(row["pages"] or 0),
                "payload_bytes": int(row["payload_bytes"] or 0),
                "unused_bytes": int(row["unused_bytes"] or 0),
            }
            for row in rows
        ],
    }


def _resolve_sqlite_cli(sqlite_cli: str | None) -> str | None:
    if not sqlite_cli:
        return None
    candidate = Path(sqlite_cli).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    return shutil.which(sqlite_cli)


def _collect_external_dbstat(
    db_path: Path,
    sqlite_cli: str | None,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    sqlite_cli_path = _resolve_sqlite_cli(sqlite_cli)
    if not sqlite_cli_path:
        return {
            "available": False,
            "error": "sqlite_cli_unavailable",
            "source": "external_sqlite_cli",
            "sqlite_cli": sqlite_cli,
            "objects": [],
        }

    query = """
        SELECT name,
               SUM(pgsize) AS bytes,
               COUNT(*) AS pages,
               SUM(payload) AS payload_bytes,
               SUM(unused) AS unused_bytes
        FROM dbstat
        GROUP BY name
        ORDER BY bytes DESC, name;
    """
    command = [
        sqlite_cli_path,
        "-batch",
        "-readonly",
        "-cmd",
        "PRAGMA query_only = ON",
        "-separator",
        "\t",
        _sqlite_readonly_uri(db_path),
        query,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "error": str(exc),
            "source": "external_sqlite_cli",
            "sqlite_cli": sqlite_cli_path,
            "objects": [],
        }

    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        return {
            "available": False,
            "error": error or f"sqlite_cli_exit_{completed.returncode}",
            "source": "external_sqlite_cli",
            "sqlite_cli": sqlite_cli_path,
            "objects": [],
        }

    objects: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) != 5:
            return {
                "available": False,
                "error": f"unexpected_sqlite_cli_output: {line!r}",
                "source": "external_sqlite_cli",
                "sqlite_cli": sqlite_cli_path,
                "objects": [],
            }
        name, bytes_value, pages, payload_bytes, unused_bytes = parts
        objects.append(
            {
                "name": name,
                "bytes": int(bytes_value or 0),
                "pages": int(pages or 0),
                "payload_bytes": int(payload_bytes or 0),
                "unused_bytes": int(unused_bytes or 0),
            }
        )

    return {
        "available": True,
        "error": None,
        "source": "external_sqlite_cli",
        "sqlite_cli": sqlite_cli_path,
        "objects": objects,
    }


def _is_safe_count_table(db_key: str, table_name: str) -> bool:
    if table_name in NEVER_DEFAULT_COUNT_TABLES:
        return False
    if table_name in SAFE_COUNT_TABLES_BY_DB.get(db_key, set()):
        return True
    return table_name.endswith("_mart") or table_name.endswith("_builds")


def _row_count_inventory(
    conn: sqlite3.Connection,
    db_key: str,
    tables: list[dict[str, Any]],
    *,
    exact_counts: bool,
) -> dict[str, dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for table in tables:
        table_name = str(table["name"])
        if table_name.startswith("sqlite_"):
            continue

        safe = _is_safe_count_table(db_key, table_name)
        if not exact_counts and not safe:
            reason = (
                "requires_exact_counts_flag"
                if table_name == "ccee_plant_parcel_hourly"
                else "not_in_safe_count_set"
            )
            counts[table_name] = {
                "row_count": None,
                "counted": False,
                "reason": reason,
            }
            continue

        try:
            count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}"
                ).fetchone()[0]
            )
        except sqlite3.Error as exc:
            counts[table_name] = {
                "row_count": None,
                "counted": False,
                "reason": f"count_failed: {exc}",
            }
            continue

        counts[table_name] = {
            "row_count": count,
            "counted": True,
            "reason": "exact_counts_flag" if exact_counts and not safe else "safe_count",
        }
    return counts


def collect_database_inventory(
    db_key: str,
    db_path: Path,
    *,
    exact_counts: bool = False,
    sqlite_cli: str | None = None,
    sqlite_cli_timeout_seconds: int = 300,
) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    summary: dict[str, Any] = {
        "path": str(db_path),
        "exists": db_path.exists(),
        "file": _file_summary(db_path),
        "sidecars": _sidecar_summary(db_path),
        "read_only": True,
        "sqlite": None,
        "sqlite_master": {
            "tables": [],
            "indexes": [],
            "views": [],
            "triggers": [],
        },
        "dbstat_available": False,
        "dbstat": {
            "available": False,
            "error": None,
            "source": None,
            "objects": [],
        },
        "row_counts": {},
        "errors": [],
    }
    if not db_path.exists():
        summary["errors"].append("database_missing")
        return summary

    try:
        with _connect_readonly(db_path) as conn:
            summary["sqlite"] = _sqlite_page_stats(conn)
            summary["sqlite_master"] = _sqlite_master_inventory(conn)
            dbstat = _collect_dbstat(conn)
            if not dbstat["available"] and sqlite_cli:
                dbstat = _collect_external_dbstat(
                    db_path,
                    sqlite_cli,
                    timeout_seconds=sqlite_cli_timeout_seconds,
                )
            summary["dbstat_available"] = bool(dbstat["available"])
            summary["dbstat"] = dbstat
            summary["row_counts"] = _row_count_inventory(
                conn,
                db_key,
                summary["sqlite_master"]["tables"],
                exact_counts=exact_counts,
            )
    except sqlite3.Error as exc:
        summary["errors"].append(str(exc))
    return summary


def summarize_folder(
    path: Path,
    *,
    max_files: int = DEFAULT_MAX_FOLDER_FILES,
    max_depth: int = DEFAULT_MAX_FOLDER_DEPTH,
) -> dict[str, Any]:
    path = path.expanduser().resolve()
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": 0,
        "file_count": 0,
        "dir_count": 0,
        "max_depth": max_depth,
        "max_files": max_files,
        "truncated": False,
        "errors": [],
    }
    if not path.exists():
        return result

    stack: list[tuple[Path, int]] = [(path, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            result["truncated"] = True
            continue
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            result["dir_count"] += 1
                            stack.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            result["file_count"] += 1
                            result["size_bytes"] += int(entry.stat(follow_symlinks=False).st_size)
                            if result["file_count"] >= max_files:
                                result["truncated"] = True
                                return result
                    except OSError as exc:
                        result["errors"].append(f"{entry.path}: {exc}")
        except OSError as exc:
            result["errors"].append(f"{current}: {exc}")
    return result


def collect_inventory(
    *,
    data_dir: str | None = None,
    exact_counts: bool = False,
    max_folder_files: int = DEFAULT_MAX_FOLDER_FILES,
    max_folder_depth: int = DEFAULT_MAX_FOLDER_DEPTH,
    sqlite_cli: str | None = None,
    sqlite_cli_timeout_seconds: int = 300,
) -> dict[str, Any]:
    resolved_data_dir, databases, folders = _resolve_paths(data_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": _utc_now(),
        "mode": "read_only_diagnostic",
        "data_dir": str(resolved_data_dir),
        "exact_counts": bool(exact_counts),
        "limits": {
            "max_folder_files": int(max_folder_files),
            "max_folder_depth": int(max_folder_depth),
            "sqlite_cli_timeout_seconds": int(sqlite_cli_timeout_seconds),
        },
        "databases": {
            key: collect_database_inventory(
                key,
                path,
                exact_counts=exact_counts,
                sqlite_cli=sqlite_cli,
                sqlite_cli_timeout_seconds=sqlite_cli_timeout_seconds,
            )
            for key, path in databases.items()
        },
        "folders": {
            key: summarize_folder(
                path,
                max_files=max_folder_files,
                max_depth=max_folder_depth,
            )
            for key, path in folders.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect a read-only Phase 5 local storage inventory."
    )
    parser.add_argument(
        "--data-dir",
        help="CVMAnalytics data root. Defaults to the configured Documents data root.",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path. JSON is always printed to stdout.",
    )
    parser.add_argument(
        "--exact-counts",
        action="store_true",
        help="Count every table, including large raw tables such as ccee_plant_parcel_hourly.",
    )
    parser.add_argument(
        "--sqlite-cli",
        help=(
            "Optional sqlite3 CLI path or command name used as a dbstat fallback. "
            "When omitted, no external CLI dbstat scan is attempted."
        ),
    )
    parser.add_argument(
        "--sqlite-cli-timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each optional external sqlite3 dbstat scan.",
    )
    parser.add_argument(
        "--max-folder-files",
        type=int,
        default=DEFAULT_MAX_FOLDER_FILES,
        help="Maximum files to scan per folder summary before marking it truncated.",
    )
    parser.add_argument(
        "--max-folder-depth",
        type=int,
        default=DEFAULT_MAX_FOLDER_DEPTH,
        help="Maximum folder depth to scan before marking it truncated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = collect_inventory(
        data_dir=args.data_dir,
        exact_counts=args.exact_counts,
        max_folder_files=max(1, int(args.max_folder_files)),
        max_folder_depth=max(0, int(args.max_folder_depth)),
        sqlite_cli=args.sqlite_cli,
        sqlite_cli_timeout_seconds=max(1, int(args.sqlite_cli_timeout)),
    )
    payload = json.dumps(inventory, indent=2, ensure_ascii=False)
    print(payload)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
