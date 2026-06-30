#!/usr/bin/env python3
"""Create an Energy KPI DB candidate with MMGD detail externalized to Parquet."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.energy_kpi.distribution.mmgd_store import (  # noqa: E402
    MMGD_DATASET_ID,
    ensure_mmgd_managed_tables,
    persist_mmgd_snapshot_to_managed_store,
)
from src.platform.settings import build_settings  # noqa: E402

PROJECTS_TABLE = "distribution_mmgd_projects"
SNAPSHOTS_TABLE = "distribution_mmgd_project_snapshots"


def _default_live_db_path() -> Path:
    settings = build_settings()
    return Path(settings.paths.energy_kpi_db_path).expanduser().resolve()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _count_rows(conn: sqlite3.Connection, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0] or 0)


def _load_mmgd_detail(conn: sqlite3.Connection) -> pl.DataFrame:
    if not _table_exists(conn, PROJECTS_TABLE) or not _table_exists(conn, SNAPSHOTS_TABLE):
        return pl.DataFrame()
    query = """
        SELECT
            p.distributor_id,
            p.project_id,
            p.municipality,
            p.uf,
            NULL AS consumer_class,
            NULL AS tariff_subgroup,
            NULL AS project_modality,
            NULL AS enabled_modality,
            p.generation_type,
            p.generation_source,
            p.size_category,
            p.latitude,
            p.longitude,
            p.connection_date,
            s.reference_month,
            s.installed_capacity_kw,
            s.beneficiary_units_count,
            s.source_row_hash,
            s.snapshot_id
        FROM distribution_mmgd_project_snapshots s
        JOIN distribution_mmgd_projects p ON s.project_id = p.project_id
        ORDER BY s.reference_month, p.project_id
    """
    return pl.read_database(query, conn)


def _connect_sqlalchemy_sqlite(db_path: Path):
    return create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})


def _vacuum(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("VACUUM")


def _copy_sqlite_database(source_db: Path, output_db: Path) -> None:
    with closing(sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(output_db)) as dst:
            src.backup(dst)


def create_compact_without_mmgd(
    *,
    source_db: Path,
    output_db: Path,
    data_dir: Path,
) -> dict[str, Any]:
    source_db = Path(source_db).expanduser().resolve()
    output_db = Path(output_db).expanduser().resolve()
    data_dir = Path(data_dir).expanduser().resolve()
    if source_db == output_db:
        raise ValueError("source_db and output_db must be different")
    if not source_db.exists():
        raise FileNotFoundError(f"source DB not found: {source_db}")

    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists():
        output_db.unlink()
    _copy_sqlite_database(source_db, output_db)

    with closing(sqlite3.connect(source_db)) as source_conn:
        source_projects = _count_rows(source_conn, PROJECTS_TABLE)
        source_snapshots = _count_rows(source_conn, SNAPSHOTS_TABLE)

    with closing(sqlite3.connect(output_db)) as read_conn:
        detail = _load_mmgd_detail(read_conn)

    managed_result: dict[str, Any] = {"row_count": 0, "partitions": []}
    if detail.height > 0:
        engine = _connect_sqlalchemy_sqlite(output_db)
        with engine.begin() as conn:
            managed_result = persist_mmgd_snapshot_to_managed_store(
                data_dir=data_dir,
                conn=conn,
                frame=detail,
                snapshot_id="legacy-mmgd-migration",
            )
            conn.execute(text(f"DELETE FROM {SNAPSHOTS_TABLE}"))
            conn.execute(text(f"DELETE FROM {PROJECTS_TABLE}"))
        engine.dispose()
        _vacuum(output_db)
    else:
        engine = _connect_sqlalchemy_sqlite(output_db)
        with engine.begin() as conn:
            ensure_mmgd_managed_tables(conn)
        engine.dispose()

    with closing(sqlite3.connect(output_db)) as output_conn:
        output_projects = _count_rows(output_conn, PROJECTS_TABLE)
        output_snapshots = _count_rows(output_conn, SNAPSHOTS_TABLE)
        catalog_row = None
        if _table_exists(output_conn, "managed_dataset_catalog"):
            catalog_row = output_conn.execute(
                "SELECT manifest_path, row_count FROM managed_dataset_catalog WHERE dataset_id=?",
                (MMGD_DATASET_ID,),
            ).fetchone()

    errors: list[str] = []
    if source_projects and output_projects:
        errors.append("output still contains MMGD project detail rows")
    if source_snapshots and output_snapshots:
        errors.append("output still contains MMGD snapshot detail rows")
    if source_snapshots and int(managed_result.get("row_count") or 0) != source_snapshots:
        errors.append("managed row count does not match source snapshot rows")
    if source_snapshots and catalog_row is None:
        errors.append("managed dataset catalog row missing")

    report = {
        "ok": not errors,
        "errors": errors,
        "source_database": str(source_db),
        "output_database": str(output_db),
        "data_dir": str(data_dir),
        "source_mmgd_project_rows": source_projects,
        "source_mmgd_snapshot_rows": source_snapshots,
        "output_mmgd_project_rows": output_projects,
        "output_mmgd_snapshot_rows": output_snapshots,
        "managed_row_count": int(managed_result.get("row_count") or 0),
        "managed_manifest_path": managed_result.get("manifest_path"),
        "output_size_bytes": output_db.stat().st_size,
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a compact Energy KPI DB candidate without SQLite MMGD detail rows."
    )
    parser.add_argument("--source-db", help="Source energy_kpis.db. Defaults to the configured runtime DB.")
    parser.add_argument("--output-db", help="Candidate DB path. Defaults beside source DB.")
    parser.add_argument("--data-dir", help="CVMAnalytics data root. Defaults to the configured runtime data root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = build_settings()
    source_db = Path(args.source_db).expanduser().resolve() if args.source_db else _default_live_db_path()
    output_db = (
        Path(args.output_db).expanduser().resolve()
        if args.output_db
        else source_db.with_name("energy_kpis.without_mmgd.candidate.db")
    )
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else Path(settings.paths.data_dir)
    report = create_compact_without_mmgd(source_db=source_db, output_db=output_db, data_dir=data_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
