from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from scripts.data.swap_energy_kpi_compact_db import _manifest_fingerprint, swap_candidate


def _write_manifest(path: Path) -> dict:
    manifest = {
        "validation": {"ok": True},
        "selection": {
            "full_months": True,
            "available_months": [{"reference_month": "2026-01", "row_count": 2}],
            "hot_months": ["2026-01"],
            "cold_months": [],
        },
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def _write_live_db(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE keep_me (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO keep_me (value) VALUES ('old-live-db');
            """
        )
        conn.commit()


def _write_candidate_db(path: Path, manifest: dict, *, raw_hourly_rows: bool = False) -> None:
    counts = {
        str(row["reference_month"]): int(row["row_count"])
        for row in manifest["selection"]["available_months"]
    }
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE ccee_plant_parcel_hourly (
                reference_datetime TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                commercialization_period INTEGER NOT NULL,
                plant_parcel_code TEXT NOT NULL,
                PRIMARY KEY(reference_datetime, commercialization_period, plant_parcel_code)
            );
            CREATE TABLE plant_parcel_daily_generation_mart (
                plant_parcel_code TEXT NOT NULL,
                reference_date TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                hourly_observations INTEGER NOT NULL,
                PRIMARY KEY(plant_parcel_code, reference_date)
            );
            CREATE TABLE external_hourly_store_catalog (
                dataset TEXT PRIMARY KEY,
                manifest_path TEXT NOT NULL,
                manifest_fingerprint TEXT NOT NULL,
                source_database TEXT NOT NULL,
                full_months INTEGER NOT NULL,
                manifest_row_count INTEGER NOT NULL,
                available_months_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO plant_parcel_daily_generation_mart
                (plant_parcel_code, reference_date, reference_month, hourly_observations)
            VALUES ('P1', '2026-01-01', '2026-01', 2);
            """
        )
        if raw_hourly_rows:
            conn.execute(
                """
                INSERT INTO ccee_plant_parcel_hourly
                    (reference_datetime, reference_month, commercialization_period, plant_parcel_code)
                VALUES ('2026-01-01T00:00:00', '2026-01', 1, 'P1')
                """
            )
        conn.execute(
            """
            INSERT INTO external_hourly_store_catalog
                (dataset, manifest_path, manifest_fingerprint, source_database, full_months,
                 manifest_row_count, available_months_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ccee_plant_parcel_hourly",
                "manifest.json",
                _manifest_fingerprint(manifest),
                "energy_kpis.db",
                1,
                2,
                json.dumps(counts, sort_keys=True, separators=(",", ":")),
            ),
        )
        conn.commit()


def test_swap_candidate_dry_run_does_not_move_files(tmp_path: Path):
    live = tmp_path / "energy_kpis.db"
    candidate = tmp_path / "energy_kpis.without_hourly.candidate.db"
    manifest_path = tmp_path / "manifest.json"
    manifest = _write_manifest(manifest_path)
    _write_live_db(live)
    _write_candidate_db(candidate, manifest)

    report = swap_candidate(
        live_db=live,
        candidate=candidate,
        manifest_path=manifest_path,
        backup_dir=tmp_path / "backup",
        apply=False,
    )

    assert report["ok"] is True
    assert report["applied"] is False
    assert live.exists()
    assert candidate.exists()
    assert not (tmp_path / "backup").exists()


def test_swap_candidate_apply_moves_live_to_backup_and_candidate_to_live(tmp_path: Path):
    live = tmp_path / "energy_kpis.db"
    candidate = tmp_path / "energy_kpis.without_hourly.candidate.db"
    manifest_path = tmp_path / "manifest.json"
    backup_dir = tmp_path / "backup"
    manifest = _write_manifest(manifest_path)
    _write_live_db(live)
    _write_candidate_db(candidate, manifest)

    report = swap_candidate(
        live_db=live,
        candidate=candidate,
        manifest_path=manifest_path,
        backup_dir=backup_dir,
        apply=True,
    )

    assert report["ok"] is True
    assert report["applied"] is True
    assert live.exists()
    assert not candidate.exists()
    assert (backup_dir / "energy_kpis.db").exists()
    with sqlite3.connect(live) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM external_hourly_store_catalog WHERE dataset='ccee_plant_parcel_hourly'"
        ).fetchone()[0] == 1
    with sqlite3.connect(backup_dir / "energy_kpis.db") as conn:
        assert conn.execute("SELECT value FROM keep_me").fetchone()[0] == "old-live-db"


def test_swap_candidate_rejects_candidate_with_raw_hourly_rows(tmp_path: Path):
    live = tmp_path / "energy_kpis.db"
    candidate = tmp_path / "energy_kpis.without_hourly.candidate.db"
    manifest_path = tmp_path / "manifest.json"
    manifest = _write_manifest(manifest_path)
    _write_live_db(live)
    _write_candidate_db(candidate, manifest, raw_hourly_rows=True)

    report = swap_candidate(
        live_db=live,
        candidate=candidate,
        manifest_path=manifest_path,
        backup_dir=tmp_path / "backup",
        apply=True,
    )

    assert report["ok"] is False
    assert report["applied"] is False
    assert report["validation"]["errors"]
    assert live.exists()
    assert candidate.exists()
