from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.diagnostics.phase5_compare_hourly_read_paths import compare_hourly_read_paths
from scripts.diagnostics.phase5_hot_cold_hourly_prototype import (
    HOURLY_TABLE,
    build_hot_cold_prototype,
)


def _seed_energy_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            f"""
            CREATE TABLE {HOURLY_TABLE} (
                reference_datetime TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                commercialization_period INTEGER NOT NULL,
                plant_parcel_code TEXT NOT NULL,
                plant_acronym TEXT,
                generation_source TEXT,
                submarket TEXT,
                plant_type TEXT,
                generation_center_of_gravity_mwmed REAL,
                generation_center_of_gravity_mwh REAL,
                internal_loss_factor_pct REAL,
                loss_generation_apportionment_factor_mwh REAL,
                energy_security_generation_mwh REAL,
                constrained_on_generation_mwh REAL,
                adjusted_restriction_charge_energy_mwmed REAL,
                unavailability_mwh REAL,
                declared_cost_mwh REAL,
                hydraulic_displacement_factor_mwh REAL,
                verified_generation_ons_mwh REAL,
                verified_availability_mwh REAL,
                inflexible_generation_mwmed REAL,
                substitute_unavailability_generation_mwh REAL,
                reserve_power_generation_mwh REAL,
                unit_commitment_generation_mwmed REAL,
                final_merit_order_generation_mwh REAL,
                adjusted_physical_guarantee_mwh REAL,
                source_dataset TEXT NOT NULL,
                raw_payload_hash TEXT NOT NULL,
                snapshot_id TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (reference_datetime, commercialization_period, plant_parcel_code)
            )
            """
        )
        conn.execute(
            f"CREATE INDEX idx_cppe_parcel_ref ON {HOURLY_TABLE}(plant_parcel_code, reference_datetime)"
        )
        conn.execute(f"CREATE INDEX idx_cppe_ref_month ON {HOURLY_TABLE}(reference_month)")
        rows = []
        for month in ("2026-01", "2026-02"):
            for day in (1, 2):
                for period in (1, 2):
                    value = float(day * 10 + period)
                    rows.append(
                        (
                            f"{month}-{day:02d}T{period - 1:02d}:00:00",
                            month,
                            period,
                            "P1001",
                            "PLT",
                            "hydro",
                            "SE",
                            "UHE",
                            value,
                            value,
                            None,
                            None,
                            None,
                            None,
                            None,
                            value / 10,
                            None,
                            None,
                            value - 1,
                            value + 1,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            "fixture",
                            f"hash-{month}-{day}-{period}",
                            "snap-1",
                            "2026-06-21T00:00:00",
                        )
                    )
        placeholders = ", ".join("?" for _ in rows[0])
        conn.executemany(f"INSERT INTO {HOURLY_TABLE} VALUES ({placeholders})", rows)
        conn.commit()


def test_compare_hourly_read_paths_matches_hot_and_cold_full_months(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    prototype_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)

    build_hot_cold_prototype(
        database=source_db,
        output_dir=prototype_dir,
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
    )

    report = compare_hourly_read_paths(
        manifest_path=prototype_dir / "manifest.json",
        database=source_db,
        runs=1,
    )

    assert report["summary"]["validation_ok"] is True
    assert report["summary"]["sample_count"] == 2
    assert report["summary"]["hot_samples"] == 1
    assert report["summary"]["cold_samples"] == 1
    assert report["source_unchanged"] is True
    assert {sample["tier"] for sample in report["samples"]} == {"hot", "cold"}
    assert all(sample["match"] is True for sample in report["samples"])
    assert all(sample["raw"]["rows_hash"] == sample["candidate"]["rows_hash"] for sample in report["samples"])
    assert all(sample["window_mode"] == "month" for sample in report["samples"])


def test_compare_hourly_read_paths_uses_sample_window_for_bounded_manifest(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    prototype_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)

    build_hot_cold_prototype(
        database=source_db,
        output_dir=prototype_dir,
        hot_months=1,
        cold_months=["2026-01"],
        max_rows_per_month=1,
        chunk_size=1,
    )

    report = compare_hourly_read_paths(
        manifest_path=prototype_dir / "manifest.json",
        database=source_db,
        runs=1,
    )

    assert report["summary"]["validation_ok"] is True
    assert all(sample["window_mode"] == "sample_datetime" for sample in report["samples"])
    assert all(sample["raw"]["row_count"] == sample["candidate"]["row_count"] == 1 for sample in report["samples"])


def test_compare_hourly_read_paths_detects_candidate_mismatch(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    prototype_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)
    manifest = build_hot_cold_prototype(
        database=source_db,
        output_dir=prototype_dir,
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
    )

    hot_db = Path(manifest["artifacts"]["hot"]["path"])
    with closing(sqlite3.connect(hot_db)) as conn:
        conn.execute(
            f"""
            UPDATE {HOURLY_TABLE}
            SET generation_center_of_gravity_mwh = generation_center_of_gravity_mwh + 99
            WHERE plant_parcel_code = 'P1001'
              AND reference_month = '2026-02'
              AND commercialization_period = 1
            """
        )
        conn.commit()

    report = compare_hourly_read_paths(
        manifest_path=prototype_dir / "manifest.json",
        database=source_db,
        tier="hot",
        runs=1,
    )

    assert report["summary"]["validation_ok"] is False
    assert report["summary"]["mismatched"] == 1
    assert report["samples"][0]["match"] is False
    assert report["samples"][0]["differences"][0]["type"] == "value"
