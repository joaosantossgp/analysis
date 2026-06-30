#!/usr/bin/env python3
"""Safely swap a compact energy_kpis.db candidate into the live data root."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.platform.settings import build_settings  # noqa: E402

HOURLY_TABLE = "ccee_plant_parcel_hourly"
CATALOG_TABLE = "external_hourly_store_catalog"
REQUIRED_MANIFEST_RELATIVE = Path("analytics") / "energy" / "ccee_plant_generation_hourly" / "manifest.json"


def _default_live_db_path() -> Path:
    env_db = os.environ.get("CVM_ENERGY_KPI_DB")
    if env_db:
        return Path(env_db).expanduser().resolve()
    documents_db = Path.home() / "Documents" / "CVMAnalytics" / "db" / "energy_kpis.db"
    if documents_db.exists():
        return documents_db.resolve()
    return Path(build_settings(project_root=ROOT).paths.energy_kpi_db_path).expanduser().resolve()


def _default_manifest_path(live_db: Path) -> Path:
    return live_db.parent.parent / REQUIRED_MANIFEST_RELATIVE


def _default_candidate_path(live_db: Path) -> Path:
    return live_db.with_name("energy_kpis.without_hourly.candidate.db")


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


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


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_row_counts(manifest: dict[str, Any]) -> dict[str, int]:
    rows = manifest.get("selection", {}).get("available_months") or []
    counts: dict[str, int] = {}
    for row in rows:
        month = str(row.get("reference_month") or "").strip()
        if month:
            counts[month] = int(row.get("row_count") or 0)
    return counts


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


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [
        db_path.with_name(db_path.name + suffix)
        for suffix in ("-wal", "-shm", "-journal")
        if db_path.with_name(db_path.name + suffix).exists()
    ]


def _validate_candidate(candidate: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    expected_counts = _manifest_row_counts(manifest)
    errors: list[dict[str, Any]] = []
    if not expected_counts:
        errors.append({"manifest": "no available_months row counts"})

    with closing(_connect_readonly(candidate)) as conn:
        if _table_exists(conn, HOURLY_TABLE):
            has_hourly_rows = conn.execute(f"SELECT 1 FROM {HOURLY_TABLE} LIMIT 1").fetchone() is not None
            if has_hourly_rows:
                errors.append({"table": HOURLY_TABLE, "error": "candidate still contains raw hourly rows"})
        if not _table_exists(conn, CATALOG_TABLE):
            errors.append({"table": CATALOG_TABLE, "error": "catalog table missing"})
        else:
            row = conn.execute(
                f"""
                SELECT manifest_fingerprint, full_months, manifest_row_count, available_months_json
                FROM {CATALOG_TABLE}
                WHERE dataset = ?
                """,
                (HOURLY_TABLE,),
            ).fetchone()
            if row is None:
                errors.append({"table": CATALOG_TABLE, "error": "hourly catalog row missing"})
            else:
                try:
                    catalog_counts = json.loads(str(row["available_months_json"] or "{}"))
                except json.JSONDecodeError:
                    catalog_counts = {}
                    errors.append({"table": CATALOG_TABLE, "error": "catalog month JSON invalid"})
                normalized_counts = {
                    str(month): int(count or 0) for month, count in dict(catalog_counts).items()
                }
                if str(row["manifest_fingerprint"]) != _manifest_fingerprint(manifest):
                    errors.append({"table": CATALOG_TABLE, "error": "manifest fingerprint mismatch"})
                if int(row["full_months"] or 0) != 1:
                    errors.append({"table": CATALOG_TABLE, "error": "catalog is not marked full-month"})
                if int(row["manifest_row_count"] or 0) != sum(expected_counts.values()):
                    errors.append({"table": CATALOG_TABLE, "error": "catalog row count mismatch"})
                if normalized_counts != expected_counts:
                    errors.append({"table": CATALOG_TABLE, "error": "catalog month counts mismatch"})
        mart_counts = _daily_mart_counts(conn)
        if mart_counts != expected_counts:
            errors.append({"daily_mart_counts": mart_counts, "manifest_counts": expected_counts})

    return {
        "ok": not errors,
        "errors": errors,
        "candidate_database": str(candidate),
        "manifest_path": str(manifest_path),
        "manifest_hourly_rows": sum(expected_counts.values()),
        "candidate_size_bytes": candidate.stat().st_size,
    }


def _move_existing(path: Path, backup_dir: Path, moved: list[tuple[Path, Path]]) -> None:
    if not path.exists():
        return
    destination = backup_dir / path.name
    os.replace(path, destination)
    moved.append((path, destination))


def _restore_backup(live_db: Path, backup_dir: Path, moved: list[tuple[Path, Path]]) -> None:
    failed_live = backup_dir / f"failed-new-{live_db.name}"
    if live_db.exists():
        os.replace(live_db, failed_live)
    for original, backup in reversed(moved):
        if backup.exists():
            os.replace(backup, original)


def swap_candidate(
    *,
    live_db: Path,
    candidate: Path,
    manifest_path: Path,
    backup_dir: Path,
    apply: bool,
) -> dict[str, Any]:
    live_db = live_db.expanduser().resolve()
    candidate = candidate.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    backup_dir = backup_dir.expanduser().resolve()

    if live_db == candidate:
        raise ValueError("Candidate and live database paths must be different.")
    if not live_db.exists():
        raise FileNotFoundError(f"Live database not found: {live_db}")
    if not candidate.exists():
        raise FileNotFoundError(f"Candidate database not found: {candidate}")
    if live_db.drive.lower() != candidate.drive.lower() or live_db.drive.lower() != backup_dir.drive.lower():
        raise ValueError("Live database, candidate, and backup directory must be on the same drive.")

    validation = _validate_candidate(candidate, manifest_path)
    sidecars = _sidecar_paths(live_db)
    report: dict[str, Any] = {
        "ok": validation["ok"],
        "applied": False,
        "live_database": str(live_db),
        "candidate_database": str(candidate),
        "backup_dir": str(backup_dir),
        "sidecars_to_backup": [str(path) for path in sidecars],
        "validation": validation,
        "live_size_bytes_before": live_db.stat().st_size,
        "candidate_size_bytes": candidate.stat().st_size,
    }
    if not validation["ok"]:
        return report
    if not apply:
        report["planned_operations"] = [
            f"move {live_db} -> {backup_dir / live_db.name}",
            *[f"move {path} -> {backup_dir / path.name}" for path in sidecars],
            f"move {candidate} -> {live_db}",
        ]
        return report

    moved: list[tuple[Path, Path]] = []
    backup_dir.mkdir(parents=True, exist_ok=False)
    try:
        _move_existing(live_db, backup_dir, moved)
        for sidecar in sidecars:
            _move_existing(sidecar, backup_dir, moved)
        os.replace(candidate, live_db)
        post_validation = _validate_candidate(live_db, manifest_path)
        if not post_validation["ok"]:
            report["post_validation"] = post_validation
            raise RuntimeError("Post-swap candidate validation failed.")
        report.update(
            {
                "ok": True,
                "applied": True,
                "post_validation": post_validation,
                "live_size_bytes_after": live_db.stat().st_size,
                "backup_size_bytes": (backup_dir / live_db.name).stat().st_size,
            }
        )
        (backup_dir / "swap_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report
    except Exception as exc:
        rollback_error = None
        if moved:
            try:
                _restore_backup(live_db, backup_dir, moved)
            except Exception as rollback_exc:
                rollback_error = str(rollback_exc)
        report["ok"] = False
        report["applied"] = False
        report["rollback_attempted"] = True
        report["error"] = str(exc)
        if rollback_error is not None:
            report["rollback_error"] = rollback_error
        return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up live energy_kpis.db and swap in a validated compact candidate."
    )
    parser.add_argument("--live-db", help="Live energy_kpis.db. Defaults to the configured Documents database.")
    parser.add_argument("--candidate", help="Compact candidate DB. Defaults to energy_kpis.without_hourly.candidate.db.")
    parser.add_argument("--manifest", help="Managed hourly store manifest. Defaults to the data-root manifest.")
    parser.add_argument("--backup-dir", help="Backup directory. Defaults to data-root/backup/energy_kpis_swap_<timestamp>.")
    parser.add_argument("--apply", action="store_true", help="Perform the swap. Without this, only prints a dry run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    live_db = Path(args.live_db).expanduser().resolve() if args.live_db else _default_live_db_path()
    candidate = Path(args.candidate).expanduser().resolve() if args.candidate else _default_candidate_path(live_db)
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else _default_manifest_path(live_db)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = (
        Path(args.backup_dir).expanduser().resolve()
        if args.backup_dir
        else live_db.parent.parent / "backup" / f"energy_kpis_swap_{timestamp}"
    )
    report = swap_candidate(
        live_db=live_db,
        candidate=candidate,
        manifest_path=manifest_path,
        backup_dir=backup_dir,
        apply=bool(args.apply),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
