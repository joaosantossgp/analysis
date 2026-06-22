from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.diagnostics.phase5_compare_hourly_read_paths import compare_hourly_read_paths
from scripts.diagnostics.phase5_ceg_hourly_mart_prototype import build_ceg_hourly_mart_prototype
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
        conn.execute(
            """
            CREATE TABLE ccee_plant_parcels (
                plant_parcel_code TEXT PRIMARY KEY,
                ceg TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO ccee_plant_parcels (plant_parcel_code, ceg) VALUES (?, ?)",
            [("P1001", "CEG123"), ("P1002", "CEG123")],
        )
        rows = []
        for month in ("2026-01", "2026-02"):
            for parcel_idx, parcel_code in enumerate(("P1001", "P1002"), start=1):
                for day in (1, 2):
                    for period in (1, 2):
                        value = float(parcel_idx * 100 + day * 10 + period)
                        rows.append(
                            (
                                f"{month}-{day:02d}T{period - 1:02d}:00:00",
                                month,
                                period,
                                parcel_code,
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
                                f"hash-{month}-{parcel_code}-{day}-{period}",
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


def test_compare_hourly_read_paths_broadens_samples_and_aneel_aggregation(tmp_path: Path):
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
        samples_per_tier=2,
        aneel_samples_per_tier=2,
        include_aneel_aggregation=True,
    )

    assert report["summary"]["validation_ok"] is True
    assert report["summary"]["sample_count"] == 6
    assert report["summary"]["parcel_samples"] == 4
    assert report["summary"]["aneel_plant_samples"] == 2
    assert report["summary"]["hot_samples"] == 3
    assert report["summary"]["cold_samples"] == 3
    assert all(sample["match"] is True for sample in report["samples"])

    aneel_samples = [sample for sample in report["samples"] if sample["entity_type"] == "aneel_plant"]
    assert {sample["ceg"] for sample in aneel_samples} == {"CEG123"}
    assert all(sample["plant_parcel_count"] == 2 for sample in aneel_samples)
    assert all(sample["raw"]["row_count"] == sample["candidate"]["row_count"] == 4 for sample in aneel_samples)


def test_compare_hourly_read_paths_can_auto_sample_aneel_only(tmp_path: Path):
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
        aneel_samples_per_tier=2,
        auto_entity_type="aneel_plant",
    )

    assert report["summary"]["validation_ok"] is True
    assert report["summary"]["sample_count"] == 2
    assert report["summary"]["parcel_samples"] == 0
    assert report["summary"]["aneel_plant_samples"] == 2
    assert {sample["tier"] for sample in report["samples"]} == {"hot", "cold"}
    assert {sample["entity_type"] for sample in report["samples"]} == {"aneel_plant"}
    assert all(sample["plant_parcel_count"] == 2 for sample in report["samples"])
    assert all(sample["match"] is True for sample in report["samples"])


def test_compare_hourly_read_paths_can_compare_ceg_mart(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    prototype_dir = tmp_path / "prototype"
    ceg_mart_path = tmp_path / "ceg_hourly_mart.sqlite"
    _seed_energy_db(source_db)

    build_hot_cold_prototype(
        database=source_db,
        output_dir=prototype_dir,
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
    )
    mart_manifest = build_ceg_hourly_mart_prototype(
        database=source_db,
        output_path=ceg_mart_path,
        reference_months=["2026-01", "2026-02"],
    )

    report = compare_hourly_read_paths(
        manifest_path=prototype_dir / "manifest.json",
        database=source_db,
        ceg_mart_path=ceg_mart_path,
        runs=1,
        aneel_samples_per_tier=2,
        auto_entity_type="aneel_plant",
    )

    assert mart_manifest["validation"]["ok"] is True
    assert report["summary"]["validation_ok"] is True
    assert report["summary"]["ceg_mart_samples"] == 2
    assert report["summary"]["ceg_mart_matched"] == 2
    assert report["summary"]["ceg_mart_mismatched"] == 0
    assert all(sample["ceg_mart"]["rows_hash"] == sample["raw"]["rows_hash"] for sample in report["samples"])
    assert all(sample["ceg_mart_comparison"]["match"] is True for sample in report["samples"])


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
