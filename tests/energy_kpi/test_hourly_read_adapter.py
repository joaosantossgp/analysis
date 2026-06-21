from __future__ import annotations

import os
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import build_hot_cold_prototype
from src.energy_kpi.hourly_read_adapter import (
    HOURLY_TABLE,
    HourlyReadRequest,
    read_hourly_from_hot_cold,
)


def _seed_source_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
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
        conn.execute(f"CREATE INDEX idx_cppe_ref_month ON {HOURLY_TABLE}(reference_month)")
        conn.execute(
            f"CREATE INDEX idx_cppe_parcel_ref ON {HOURLY_TABLE}(plant_parcel_code, reference_datetime)"
        )
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

        rows: list[tuple[Any, ...]] = []
        for month in ("2026-01", "2026-02"):
            rows.extend(
                [
                    _hourly_row(month, "00", 1, "P1001", 10.0, 9.0, 8.0, None),
                    _hourly_row(month, "00", 1, "P1002", 1.0, None, 2.0, 0.5),
                    _hourly_row(month, "01", 2, "P1001", 20.0, None, None, None),
                    _hourly_row(month, "01", 2, "P1002", 2.0, None, None, None),
                    _hourly_row(month, "02", 3, "P1001", 30.0, 29.0, 28.0, 0.0),
                    _hourly_row(month, "02", 3, "P1002", 3.0, 2.0, 1.0, 0.1),
                ]
            )
        placeholders = ", ".join("?" for _ in rows[0])
        conn.executemany(f"INSERT INTO {HOURLY_TABLE} VALUES ({placeholders})", rows)
        conn.commit()


def _hourly_row(
    month: str,
    hour: str,
    period: int,
    parcel: str,
    generation: float | None,
    verified_generation: float | None,
    verified_availability: float | None,
    unavailability: float | None,
) -> tuple[Any, ...]:
    return (
        f"{month}-01T{hour}:00:00",
        month,
        period,
        parcel,
        "PLT",
        "hydro",
        "SE",
        "UHE",
        generation,
        generation,
        None,
        None,
        None,
        None,
        None,
        unavailability,
        None,
        None,
        verified_generation,
        verified_availability,
        None,
        None,
        None,
        None,
        None,
        None,
        "fixture",
        f"hash-{month}-{parcel}-{period}",
        "snap-1",
        "2026-06-21T00:00:00",
    )


def _build_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source_db = tmp_path / "energy_kpis.db"
    output_dir = tmp_path / "prototype"
    _seed_source_db(source_db)
    build_hot_cold_prototype(
        database=source_db,
        output_dir=output_dir,
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
    )
    return source_db, output_dir / "manifest.json"


def _request(entity_id: str, entity_type: str, month: str, *, limit: int = 5) -> HourlyReadRequest:
    return HourlyReadRequest(
        entity_id=entity_id,
        entity_type=entity_type,  # type: ignore[arg-type]
        reference_month=month,
        start_datetime=f"{month}-01T00:00:00",
        end_datetime=f"{month}-01T23:59:59",
        limit=limit,
    )


def _raw_parcel_rows(source_db: Path, parcel: str, month: str, *, limit: int = 5) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(source_db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT reference_datetime, commercialization_period,
                   generation_center_of_gravity_mwh AS generation_mwh,
                   verified_generation_ons_mwh AS verified_generation_mwh,
                   verified_availability_mwh AS verified_availability_mwh,
                   unavailability_mwh AS unavailability_mwh
            FROM {HOURLY_TABLE}
            WHERE plant_parcel_code = ?
              AND reference_month = ?
            ORDER BY reference_datetime ASC, commercialization_period ASC
            LIMIT ?
            """,
            (parcel, month, limit),
        ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _raw_ceg_rows(source_db: Path, ceg: str, month: str, *, limit: int = 5) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(source_db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT h.reference_datetime, h.commercialization_period,
                   SUM(h.generation_center_of_gravity_mwh) AS generation_mwh,
                   SUM(h.verified_generation_ons_mwh) AS verified_generation_mwh,
                   SUM(h.verified_availability_mwh) AS verified_availability_mwh,
                   SUM(h.unavailability_mwh) AS unavailability_mwh
            FROM {HOURLY_TABLE} h
            JOIN ccee_plant_parcels p ON p.plant_parcel_code = h.plant_parcel_code
            WHERE p.ceg = ?
              AND h.reference_month = ?
            GROUP BY h.reference_datetime, h.commercialization_period
            ORDER BY h.reference_datetime ASC, h.commercialization_period ASC
            LIMIT ?
            """,
            (ceg, month, limit),
        ).fetchall()
    return [_normalize_row(dict(row)) for row in rows]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["commercialization_period"] = int(normalized["commercialization_period"])
    for column in ("generation_mwh", "verified_generation_mwh", "verified_availability_mwh", "unavailability_mwh"):
        if normalized.get(column) is not None:
            normalized[column] = float(normalized[column])
    return normalized


def _assert_rows_close(actual: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    assert len(actual) == len(expected)
    for actual_row, expected_row in zip(actual, expected):
        assert actual_row["reference_datetime"] == expected_row["reference_datetime"]
        assert actual_row["commercialization_period"] == expected_row["commercialization_period"]
        for column in ("generation_mwh", "verified_generation_mwh", "verified_availability_mwh", "unavailability_mwh"):
            if expected_row[column] is None:
                assert actual_row[column] is None
            else:
                assert actual_row[column] == pytest.approx(expected_row[column])


def test_hourly_adapter_reads_hot_and_cold_parcel_rows_equal_to_raw(tmp_path: Path):
    source_db, manifest = _build_fixture(tmp_path)

    hot = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("P1001", "ccee_plant_parcel", "2026-02", limit=2),
    )
    cold = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("P1001", "ccee_plant_parcel", "2026-01", limit=2),
    )

    assert hot.ok is True
    assert hot.read_path == "hot_sqlite"
    assert cold.ok is True
    assert cold.read_path == "cold_parquet"
    _assert_rows_close(hot.rows, _raw_parcel_rows(source_db, "P1001", "2026-02", limit=2))
    _assert_rows_close(cold.rows, _raw_parcel_rows(source_db, "P1001", "2026-01", limit=2))
    assert [row["reference_datetime"] for row in hot.rows] == ["2026-02-01T00:00:00", "2026-02-01T01:00:00"]


def test_hourly_adapter_reads_hot_and_cold_ceg_aggregation_equal_to_raw(tmp_path: Path):
    source_db, manifest = _build_fixture(tmp_path)

    hot = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("CEG123", "aneel_plant", "2026-02", limit=5),
    )
    cold = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("CEG123", "aneel_plant", "2026-01", limit=5),
    )

    assert hot.ok is True
    assert hot.read_path == "hot_sqlite"
    assert cold.ok is True
    assert cold.read_path == "cold_parquet"
    _assert_rows_close(hot.rows, _raw_ceg_rows(source_db, "CEG123", "2026-02", limit=5))
    _assert_rows_close(cold.rows, _raw_ceg_rows(source_db, "CEG123", "2026-01", limit=5))
    assert hot.rows[1]["unavailability_mwh"] is None
    assert cold.rows[1]["unavailability_mwh"] is None


def test_hourly_adapter_missing_manifest_returns_fallback_reason(tmp_path: Path):
    source_db, _manifest = _build_fixture(tmp_path)

    result = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=tmp_path / "missing-manifest.json",
        request=_request("P1001", "ccee_plant_parcel", "2026-02"),
    )

    assert result.ok is False
    assert result.rows == []
    assert result.fallback_reason == "manifest_missing"


def test_hourly_adapter_stale_source_signature_returns_fallback_reason(tmp_path: Path):
    source_db, manifest = _build_fixture(tmp_path)
    future = time.time() + 10
    os.utime(source_db, (future, future))

    result = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("P1001", "ccee_plant_parcel", "2026-02"),
    )

    assert result.ok is False
    assert result.rows == []
    assert result.fallback_reason == "source_signature_mismatch"
    assert result.source_signature_ok is False


def test_hourly_adapter_missing_cold_part_returns_fallback_reason(tmp_path: Path):
    source_db, manifest = _build_fixture(tmp_path)
    cold_part = next((tmp_path / "prototype" / "cold").rglob("*.parquet"))
    cold_part.unlink()

    result = read_hourly_from_hot_cold(
        source_db_path=source_db,
        manifest_path=manifest,
        request=_request("P1001", "ccee_plant_parcel", "2026-01"),
    )

    assert result.ok is False
    assert result.rows == []
    assert result.fallback_reason.startswith("cold_part_missing:")
