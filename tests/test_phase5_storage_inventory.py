from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.diagnostics import phase5_storage_inventory as inventory


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE companies(cd_cvm INTEGER PRIMARY KEY, name TEXT)")
        conn.execute(
            "CREATE TABLE ccee_plant_parcel_hourly(reference_datetime TEXT, value REAL)"
        )
        conn.execute(
            "CREATE TABLE plant_parcel_daily_generation_mart(reference_date TEXT, value REAL)"
        )
        conn.execute("CREATE INDEX idx_companies_name ON companies(name)")
        conn.executemany(
            "INSERT INTO companies(cd_cvm, name) VALUES (?, ?)",
            [(1, "A"), (2, "B")],
        )
        conn.executemany(
            "INSERT INTO ccee_plant_parcel_hourly VALUES (?, ?)",
            [("2026-01-01T00:00:00", 1.0), ("2026-01-01T01:00:00", 2.0)],
        )
        conn.execute(
            "INSERT INTO plant_parcel_daily_generation_mart VALUES (?, ?)",
            ("2026-01-01", 3.0),
        )


def test_missing_databases_are_reported_without_failure(tmp_path: Path):
    report = inventory.collect_inventory(data_dir=str(tmp_path))

    assert report["schema_version"] == 1
    assert report["mode"] == "read_only_diagnostic"
    assert report["databases"]["cvm_financials"]["exists"] is False
    assert report["databases"]["cvm_financials"]["errors"] == ["database_missing"]
    assert report["folders"]["data_root"]["exists"] is True


def test_database_inventory_uses_read_only_connection(tmp_path: Path):
    db_path = tmp_path / "db" / "cvm_financials.db"
    _init_db(db_path)
    before = db_path.stat().st_mtime_ns

    db_report = inventory.collect_database_inventory("cvm_financials", db_path)

    after = db_path.stat().st_mtime_ns
    assert before == after
    assert db_report["read_only"] is True
    assert db_report["sqlite"]["page_count"] >= 1
    assert any(
        table["name"] == "companies"
        for table in db_report["sqlite_master"]["tables"]
    )
    assert db_report["row_counts"]["companies"]["row_count"] == 2


def test_dbstat_unavailable_is_marked_false(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "db" / "cvm_financials.db"
    _init_db(db_path)
    monkeypatch.setattr(inventory, "DBSTAT_TABLE", "__missing_dbstat__")

    db_report = inventory.collect_database_inventory("cvm_financials", db_path)

    assert db_report["dbstat_available"] is False
    assert db_report["dbstat"]["available"] is False
    assert db_report["dbstat"]["objects"] == []
    assert db_report["dbstat"]["error"]


def test_large_hourly_count_is_skipped_unless_exact_counts_requested(tmp_path: Path):
    db_path = tmp_path / "db" / "energy_kpis.db"
    _init_db(db_path)

    default_report = inventory.collect_database_inventory("energy_kpis", db_path)
    exact_report = inventory.collect_database_inventory(
        "energy_kpis",
        db_path,
        exact_counts=True,
    )

    hourly_default = default_report["row_counts"]["ccee_plant_parcel_hourly"]
    assert hourly_default["counted"] is False
    assert hourly_default["row_count"] is None
    assert hourly_default["reason"] == "requires_exact_counts_flag"
    assert (
        default_report["row_counts"]["plant_parcel_daily_generation_mart"]["row_count"]
        == 1
    )

    hourly_exact = exact_report["row_counts"]["ccee_plant_parcel_hourly"]
    assert hourly_exact["counted"] is True
    assert hourly_exact["row_count"] == 2


def test_inventory_json_schema_is_stable(tmp_path: Path):
    db_path = tmp_path / "db" / "cvm_financials.db"
    _init_db(db_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "sample.json").write_text("{}", encoding="utf-8")

    report = inventory.collect_inventory(data_dir=str(tmp_path))
    encoded = json.dumps(report, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert set(decoded) == {
        "schema_version",
        "generated_at_utc",
        "mode",
        "data_dir",
        "exact_counts",
        "limits",
        "databases",
        "folders",
    }
    assert set(decoded["databases"]) == {"cvm_financials", "energy_kpis", "news"}
    assert {"data_root", "db", "cache", "output", "logs"}.issubset(
        decoded["folders"]
    )
    assert decoded["folders"]["cache"]["file_count"] == 1
