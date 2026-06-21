from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
        conn.execute(
            f"CREATE INDEX idx_cppe_ref_month ON {HOURLY_TABLE}(reference_month)"
        )
        rows = []
        for month in ("2026-01", "2026-02", "2026-03"):
            for idx in range(3):
                rows.append(
                    (
                        f"{month}-{idx + 1:02d}T00:00:00",
                        month,
                        1,
                        f"P{idx}",
                        "PLT",
                        "hydro",
                        "SE",
                        "UHE",
                        1.0 + idx,
                        2.0 + idx,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        "fixture",
                        f"hash-{month}-{idx}",
                        "snap-1",
                        "2026-06-21T00:00:00",
                    )
                )
        placeholders = ", ".join("?" for _ in rows[0])
        conn.executemany(
            f"INSERT INTO {HOURLY_TABLE} VALUES ({placeholders})",
            rows,
        )
        conn.commit()


def _fake_parquet_writer(
    source_conn,
    month: str,
    columns: list[str],
    month_dir: Path,
    row_limit: int | None,
    chunk_size: int,
):
    month_dir.mkdir(parents=True, exist_ok=True)
    limit_sql = "" if row_limit is None else " LIMIT ?"
    params = [month] if row_limit is None else [month, row_limit]
    rows = source_conn.execute(
        f"""
        SELECT {', '.join(columns)}
        FROM {HOURLY_TABLE}
        WHERE reference_month = ?
        ORDER BY reference_datetime, commercialization_period, plant_parcel_code
        {limit_sql}
        """,
        params,
    ).fetchall()
    part_path = month_dir / "part-0000.parquet"
    part_path.write_text(
        "\n".join(json.dumps(dict(row), sort_keys=True) for row in rows),
        encoding="utf-8",
    )
    return {
        "reference_month": month,
        "path": str(month_dir),
        "row_count": len(rows),
        "parts": [
            {
                "path": str(part_path),
                "row_count": len(rows),
                "size_bytes": part_path.stat().st_size,
            }
        ],
    }


def test_hot_cold_prototype_is_bounded_and_read_only(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    output_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)
    before = source_db.stat().st_mtime_ns

    manifest = build_hot_cold_prototype(
        database=source_db,
        output_dir=output_dir,
        hot_months=1,
        cold_months=["2026-01"],
        max_rows_per_month=2,
        chunk_size=1,
        parquet_writer=_fake_parquet_writer,
    )

    assert source_db.stat().st_mtime_ns == before
    assert manifest["validation"]["ok"] is True
    assert manifest["source_unchanged"] is True
    assert manifest["selection"]["hot_months"] == ["2026-03"]
    assert manifest["selection"]["cold_months"] == ["2026-01"]
    assert manifest["selection"]["row_limit_per_month"] == 2
    assert manifest["artifacts"]["hot"]["row_counts"] == {"2026-03": 2}
    assert manifest["artifacts"]["cold"]["partitions"][0]["row_count"] == 2

    hot_db = Path(manifest["artifacts"]["hot"]["path"])
    with closing(sqlite3.connect(hot_db)) as conn:
        assert conn.execute(f"SELECT COUNT(*) FROM {HOURLY_TABLE}").fetchone()[0] == 2
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["validation"]["ok"] is True


def test_hot_cold_prototype_full_months_copy_all_selected_rows(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    output_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)

    manifest = build_hot_cold_prototype(
        database=source_db,
        output_dir=output_dir,
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
        parquet_writer=_fake_parquet_writer,
    )

    assert manifest["selection"]["row_limit_per_month"] is None
    assert manifest["artifacts"]["hot"]["row_counts"] == {"2026-03": 3}
    assert manifest["artifacts"]["cold"]["partitions"][0]["row_count"] == 3


def test_hot_cold_prototype_refuses_existing_output_without_replace(tmp_path: Path):
    source_db = tmp_path / "energy_kpis.db"
    output_dir = tmp_path / "prototype"
    _seed_energy_db(source_db)
    output_dir.mkdir()

    try:
        build_hot_cold_prototype(
            database=source_db,
            output_dir=output_dir,
            parquet_writer=_fake_parquet_writer,
        )
    except FileExistsError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("Expected FileExistsError")
