#!/usr/bin/env python3
"""Smoke-test CCEE hourly ingestion against the managed hot/cold store."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.energy_kpi.plant_parcel_ingest import SOURCE_CCEE_HOURLY  # noqa: E402
from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob  # noqa: E402
from src.energy_kpi.schema import _build_energy_kpi_engine  # noqa: E402
from src.platform.settings import AppSettings, build_settings  # noqa: E402

HOURLY_TABLE = "ccee_plant_parcel_hourly"
CATALOG_TABLE = "external_hourly_store_catalog"
STORE_RELATIVE_PATH = Path("analytics") / "energy" / "ccee_plant_generation_hourly"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in manifest.get("selection", {}).get("available_months") or []:
        month = str(row.get("reference_month") or "").strip()
        if month:
            counts[month] = int(row.get("row_count") or 0)
    return counts


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return conn.execute(sql, params).fetchone()[0]


def _raw_hourly_count(db_path: Path) -> int:
    with closing(_connect(db_path)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (HOURLY_TABLE,),
        ).fetchone()
        if exists is None:
            return 0
        return int(_scalar(conn, f"SELECT COUNT(*) FROM {HOURLY_TABLE}"))


def _hot_count(manifest_path: Path, reference_month: str) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hot_path = Path(str(manifest.get("artifacts", {}).get("hot", {}).get("path"))).expanduser().resolve()
    with closing(_connect(hot_path)) as conn:
        return int(_scalar(
            conn,
            f"SELECT COUNT(*) FROM {HOURLY_TABLE} WHERE reference_month = ?",
            (reference_month,),
        ))


def _cold_count(manifest_path: Path, reference_month: str) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for partition in manifest.get("artifacts", {}).get("cold", {}).get("partitions", []):
        if str(partition.get("reference_month") or "") == reference_month:
            return int(partition.get("row_count") or 0)
    return 0


def _manifest_location(manifest: dict[str, Any], reference_month: str) -> str | None:
    if reference_month in {str(month) for month in manifest.get("selection", {}).get("hot_months", [])}:
        return "hot_sqlite"
    if reference_month in {str(month) for month in manifest.get("selection", {}).get("cold_months", [])}:
        return "cold_parquet"
    return None


def _daily_mart_observations(db_path: Path, reference_month: str) -> int:
    with closing(_connect(db_path)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='plant_parcel_daily_generation_mart'",
        ).fetchone()
        if exists is None:
            return 0
        value = _scalar(
            conn,
            """
            SELECT COALESCE(SUM(hourly_observations), 0)
            FROM plant_parcel_daily_generation_mart
            WHERE reference_month = ?
            """,
            (reference_month,),
        )
        return int(value or 0)


def _update_catalog(db_path: Path, manifest_path: Path, source_db: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = _manifest_counts(manifest)
    with closing(_connect(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {CATALOG_TABLE} (
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
            INSERT OR REPLACE INTO {CATALOG_TABLE}
                (dataset, manifest_path, manifest_fingerprint, source_database, full_months,
                 manifest_row_count, available_months_json)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (
                HOURLY_TABLE,
                str(manifest_path),
                _manifest_fingerprint(manifest),
                str(source_db),
                sum(counts.values()),
                json.dumps(counts, sort_keys=True, separators=(",", ":")),
            ),
        )
        conn.commit()


def _remove_duplicate_import_log(db_path: Path, source_hash: str) -> int:
    with closing(_connect(db_path)) as conn:
        before = int(_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM energy_source_refresh_log
            WHERE source_id = ? AND status = 'success'
              AND (checksum = ? OR file_hash = ?)
            """,
            (SOURCE_CCEE_HOURLY, source_hash, source_hash),
        ))
        conn.execute(
            """
            DELETE FROM energy_source_refresh_log
            WHERE source_id = ? AND status = 'success'
              AND (checksum = ? OR file_hash = ?)
            """,
            (SOURCE_CCEE_HOURLY, source_hash, source_hash),
        )
        conn.commit()
        return before


def _rewrite_manifest_for_sandbox(
    *,
    live_manifest_path: Path,
    sandbox_manifest_path: Path,
    sandbox_hot_path: Path,
    sandbox_db_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(live_manifest_path.read_text(encoding="utf-8"))
    manifest["source_database"] = str(sandbox_db_path)
    manifest["source_signature_before"] = {"path": str(sandbox_db_path)}
    manifest["source_signature_after"] = {"path": str(sandbox_db_path)}
    manifest["source_unchanged"] = True
    manifest.setdefault("artifacts", {})["output_dir"] = str(sandbox_manifest_path.parent)
    manifest["artifacts"]["manifest_path"] = str(sandbox_manifest_path)
    manifest.setdefault("artifacts", {}).setdefault("hot", {})["path"] = str(sandbox_hot_path)
    sandbox_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def prepare_sandbox(*, live_settings: AppSettings, work_dir: Path) -> tuple[AppSettings, Path]:
    live_db = Path(live_settings.paths.energy_kpi_db_path).expanduser().resolve()
    live_manifest = Path(live_settings.paths.data_dir) / STORE_RELATIVE_PATH / "manifest.json"
    if not live_db.exists():
        raise FileNotFoundError(f"Live energy DB not found: {live_db}")
    if not live_manifest.exists():
        raise FileNotFoundError(f"Managed hourly manifest not found: {live_manifest}")

    live_manifest_payload = json.loads(live_manifest.read_text(encoding="utf-8"))
    live_hot = Path(str(live_manifest_payload.get("artifacts", {}).get("hot", {}).get("path"))).expanduser().resolve()
    if not live_hot.exists():
        raise FileNotFoundError(f"Managed hourly hot SQLite store not found: {live_hot}")

    sandbox_root = work_dir / "sandbox"
    sandbox_settings = build_settings(project_root=sandbox_root)
    sandbox_db = Path(sandbox_settings.paths.energy_kpi_db_path)
    sandbox_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_db, sandbox_db)

    sandbox_store = Path(sandbox_settings.paths.data_dir) / STORE_RELATIVE_PATH
    sandbox_hot = sandbox_store / "hot" / "energy_hot.sqlite"
    sandbox_hot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(live_hot, sandbox_hot)

    sandbox_manifest = sandbox_store / "manifest.json"
    _rewrite_manifest_for_sandbox(
        live_manifest_path=live_manifest,
        sandbox_manifest_path=sandbox_manifest,
        sandbox_hot_path=sandbox_hot,
        sandbox_db_path=sandbox_db,
    )
    _update_catalog(sandbox_db, sandbox_manifest, sandbox_db)
    return sandbox_settings, sandbox_manifest


def run_smoke(
    *,
    settings: AppSettings,
    source_file: Path,
    reference_month: str,
    sandbox: bool,
    force_reimport: bool,
) -> dict[str, Any]:
    db_path = Path(settings.paths.energy_kpi_db_path)
    manifest_path = Path(settings.paths.data_dir) / STORE_RELATIVE_PATH / "manifest.json"
    if not source_file.exists():
        raise FileNotFoundError(f"CCEE hourly source file not found: {source_file}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Managed hourly manifest not found: {manifest_path}")
    source_hash = _sha256(source_file)
    deleted_duplicate_logs = _remove_duplicate_import_log(db_path, source_hash) if force_reimport else 0

    before_raw_rows = _raw_hourly_count(db_path)
    before_hot_rows = _hot_count(manifest_path, reference_month)
    before_cold_rows = _cold_count(manifest_path, reference_month)
    before_db_size = db_path.stat().st_size
    result = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_HOURLY,
        file_path=source_file,
        triggered_by="smoke-test",
        expected_period=reference_month,
    )
    _build_energy_kpi_engine.cache_clear()
    after_raw_rows = _raw_hourly_count(db_path)
    after_hot_rows = _hot_count(manifest_path, reference_month)
    after_cold_rows = _cold_count(manifest_path, reference_month)
    after_db_size = db_path.stat().st_size
    after_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_counts = _manifest_counts(after_manifest)
    daily_observations = _daily_mart_observations(db_path, reference_month)
    managed_rows_for_month = after_hot_rows + after_cold_rows
    imported_rows = int(result.get("rows_inserted") or 0)

    ok = (
        result.get("status") == "success"
        and before_raw_rows == 0
        and after_raw_rows == 0
        and managed_rows_for_month == imported_rows
        and manifest_counts.get(reference_month) == managed_rows_for_month
        and daily_observations == managed_rows_for_month
    )
    return {
        "ok": ok,
        "sandbox": sandbox,
        "source_file": str(source_file),
        "source_sha256": source_hash,
        "reference_month": reference_month,
        "database": str(db_path),
        "manifest_path": str(manifest_path),
        "deleted_duplicate_logs": deleted_duplicate_logs,
        "before": {
            "main_raw_hourly_rows": before_raw_rows,
            "hot_rows_for_month": before_hot_rows,
            "cold_rows_for_month": before_cold_rows,
            "database_size_bytes": before_db_size,
        },
        "after": {
            "main_raw_hourly_rows": after_raw_rows,
            "hot_rows_for_month": after_hot_rows,
            "cold_rows_for_month": after_cold_rows,
            "managed_rows_for_month": managed_rows_for_month,
            "daily_mart_observations_for_month": daily_observations,
            "manifest_rows_for_month": manifest_counts.get(reference_month),
            "manifest_location_for_month": _manifest_location(after_manifest, reference_month),
            "database_size_bytes": after_db_size,
        },
        "import_result": result,
        "storage_telemetry": result.get("storage_telemetry"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a CCEE hourly ingestion smoke test. Defaults to a sandbox copy of the "
            "Documents DB and managed hot store; use --apply only for an intentional live import."
        )
    )
    parser.add_argument("--source-file", required=True, type=Path, help="Official CCEE hourly .csv or .csv.gz file.")
    parser.add_argument("--reference-month", required=True, help="Expected reference month, YYYY-MM.")
    parser.add_argument("--work-dir", type=Path, help="Sandbox work directory. Defaults to a temporary directory.")
    parser.add_argument("--keep-work-dir", action="store_true", help="Keep the temporary sandbox after the run.")
    parser.add_argument("--apply", action="store_true", help="Run against the live configured Documents data root.")
    parser.add_argument(
        "--allow-duplicate-skip",
        action="store_true",
        help="Do not remove duplicate import logs in sandbox mode. This may skip the actual ingestion write.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_file = args.source_file.expanduser().resolve()
    live_settings = build_settings()

    if args.apply:
        report = run_smoke(
            settings=live_settings,
            source_file=source_file,
            reference_month=str(args.reference_month),
            sandbox=False,
            force_reimport=False,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    if args.work_dir:
        work_dir = args.work_dir.expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        settings, _manifest = prepare_sandbox(live_settings=live_settings, work_dir=work_dir)
        report = run_smoke(
            settings=settings,
            source_file=source_file,
            reference_month=str(args.reference_month),
            sandbox=True,
            force_reimport=not bool(args.allow_duplicate_skip),
        )
        report["work_dir"] = str(work_dir)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    if args.keep_work_dir:
        work_dir = Path(tempfile.mkdtemp(prefix="cvm-hourly-ingestion-smoke-"))
        settings, _manifest = prepare_sandbox(live_settings=live_settings, work_dir=work_dir)
        report = run_smoke(
            settings=settings,
            source_file=source_file,
            reference_month=str(args.reference_month),
            sandbox=True,
            force_reimport=not bool(args.allow_duplicate_skip),
        )
        report["work_dir"] = str(work_dir)
        report["work_dir_retained"] = True
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2

    with tempfile.TemporaryDirectory(prefix="cvm-hourly-ingestion-smoke-") as tmp:
        work_dir = Path(tmp)
        settings, _manifest = prepare_sandbox(live_settings=live_settings, work_dir=work_dir)
        report = run_smoke(
            settings=settings,
            source_file=source_file,
            reference_month=str(args.reference_month),
            sandbox=True,
            force_reimport=not bool(args.allow_duplicate_skip),
        )
        report["work_dir"] = str(work_dir)
        report["work_dir_retained"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
