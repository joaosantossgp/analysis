from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.profile_energy_db import profile_database


def test_energy_db_profile_read_only_report(tmp_path: Path):
    db_path = tmp_path / "energy_kpis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE ccee_plant_parcel_hourly(reference_datetime TEXT, reference_month TEXT, plant_parcel_code TEXT, generation_source TEXT, value REAL)")
        conn.execute("CREATE INDEX idx_cppe_ref_month ON ccee_plant_parcel_hourly(reference_month)")
        conn.execute("CREATE INDEX idx_cppe_parcel_ref ON ccee_plant_parcel_hourly(plant_parcel_code, reference_datetime)")
        conn.executemany(
            "INSERT INTO ccee_plant_parcel_hourly VALUES (?, ?, ?, ?, ?)",
            [
                ("2026-01-01T00:00:00", "2026-01", "P1", "hydro", 1.0),
                ("2026-01-01T01:00:00", "2026-01", "P1", "hydro", 2.0),
                ("2026-02-01T00:00:00", "2026-02", "P2", "wind", 3.0),
            ],
        )

    before = db_path.stat().st_mtime_ns
    report = profile_database(db_path, output_dir=tmp_path / "out", expensive=True)
    after = db_path.stat().st_mtime_ns

    assert before == after
    assert report["read_only"] is True
    assert report["tables"][0]["row_count"] == 3
    assert report["json_report_path"]
    assert report["markdown_report_path"]
    assert "ccee_plant_parcel_hourly" in report["distributions"]
    assert report["before_signature"] == report["after_signature"]
