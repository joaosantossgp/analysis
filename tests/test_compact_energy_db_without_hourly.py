from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.data.compact_energy_db_without_hourly import create_compact_without_hourly
from src.energy_kpi.hourly_read_adapter import (
    HourlyReadRequest,
    read_hourly_from_hot_cold,
)


def test_compact_without_hourly_preserves_metadata_and_manifest_reads(tmp_path: Path):
    source = tmp_path / "energy_kpis.db"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "energy_kpis.compact.db"
    hot = tmp_path / "hot.sqlite"

    with sqlite3.connect(source) as conn:
        conn.executescript(
            """
            CREATE TABLE ccee_plant_parcel_hourly (
                reference_datetime TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                commercialization_period INTEGER NOT NULL,
                plant_parcel_code TEXT NOT NULL,
                generation_center_of_gravity_mwh REAL,
                verified_generation_ons_mwh REAL,
                verified_availability_mwh REAL,
                unavailability_mwh REAL,
                PRIMARY KEY(reference_datetime, commercialization_period, plant_parcel_code)
            );
            CREATE TABLE ccee_plant_parcels (
                plant_parcel_code TEXT PRIMARY KEY,
                ceg TEXT
            );
            CREATE TABLE plant_parcel_daily_generation_mart (
                plant_parcel_code TEXT NOT NULL,
                reference_date TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                hourly_observations INTEGER NOT NULL,
                PRIMARY KEY(plant_parcel_code, reference_date)
            );
            CREATE TABLE source_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                source TEXT NOT NULL
            );
            INSERT INTO ccee_plant_parcel_hourly
                (reference_datetime, reference_month, commercialization_period, plant_parcel_code,
                 generation_center_of_gravity_mwh, verified_generation_ons_mwh,
                 verified_availability_mwh, unavailability_mwh)
            VALUES
                ('2026-01-01T00:00:00', '2026-01', 1, 'P1', 10, 9, 8, 0),
                ('2026-01-01T01:00:00', '2026-01', 2, 'P1', 12, 11, 10, 0);
            INSERT INTO ccee_plant_parcels VALUES ('P1', 'CEG1');
            INSERT INTO plant_parcel_daily_generation_mart VALUES ('P1', '2026-01-01', '2026-01', 2);
            INSERT INTO source_snapshots VALUES ('snap-1', 'CCEE');
            """
        )
    with sqlite3.connect(hot) as conn:
        conn.executescript(
            """
            CREATE TABLE ccee_plant_parcel_hourly (
                reference_datetime TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                commercialization_period INTEGER NOT NULL,
                plant_parcel_code TEXT NOT NULL,
                generation_center_of_gravity_mwh REAL,
                verified_generation_ons_mwh REAL,
                verified_availability_mwh REAL,
                unavailability_mwh REAL,
                PRIMARY KEY(reference_datetime, commercialization_period, plant_parcel_code)
            );
            INSERT INTO ccee_plant_parcel_hourly
                (reference_datetime, reference_month, commercialization_period, plant_parcel_code,
                 generation_center_of_gravity_mwh, verified_generation_ons_mwh,
                 verified_availability_mwh, unavailability_mwh)
            VALUES
                ('2026-01-01T00:00:00', '2026-01', 1, 'P1', 10, 9, 8, 0),
                ('2026-01-01T01:00:00', '2026-01', 2, 'P1', 12, 11, 10, 0);
            """
        )
    stat = source.stat()
    manifest.write_text(
        json.dumps(
            {
                "validation": {"ok": True},
                "source_unchanged": True,
                "source_signature_after": {
                    "path": str(source),
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                },
                "selection": {
                    "full_months": True,
                    "available_months": [{"reference_month": "2026-01", "row_count": 2}],
                    "hot_months": ["2026-01"],
                    "cold_months": [],
                },
                "artifacts": {
                    "hot": {"path": str(hot)},
                    "cold": {"partitions": []},
                },
            }
        ),
        encoding="utf-8",
    )

    result = create_compact_without_hourly(
        source=source,
        output=output,
        manifest_path=manifest,
        replace_output=False,
        integrity_check=True,
    )

    assert result["ok"] is True
    with sqlite3.connect(output) as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ccee_plant_parcel_hourly'"
        ).fetchone() is None
        assert conn.execute(
            "SELECT COUNT(*) FROM external_hourly_store_catalog WHERE dataset='ccee_plant_parcel_hourly'"
        ).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0] == 1
    read = read_hourly_from_hot_cold(
        source_db_path=output,
        manifest_path=manifest,
        request=HourlyReadRequest(
            entity_id="P1",
            entity_type="ccee_plant_parcel",
            reference_month="2026-01",
            start_datetime="2026-01-01T00:00:00",
            end_datetime="2026-01-01T01:00:00",
            limit=10,
        ),
    )
    assert read.ok is True
    assert read.read_path == "hot_sqlite"
    assert len(read.rows) == 2
