from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

from desktop.storage_inventory import StorageInventoryManager


def _settings(root: Path):
    data = root / "data"
    output = root / "output"
    return SimpleNamespace(
        paths=SimpleNamespace(
            data_dir=data,
            input_dir=data / "input",
            raw_dir=data / "input" / "raw",
            processed_dir=data / "input" / "processed",
            output_dir=output,
            reports_dir=output / "reports",
            logs_dir=data / "logs",
            cache_dir=data / "cache",
            metadata_dir=data / "metadata",
            db_dir=data / "db",
            db_path=data / "db" / "cvm_financials.db",
            energy_kpi_db_path=data / "db" / "energy_kpis.db",
            energy_kpi_raw_dir=data / "raw" / "energy",
        )
    )


def test_storage_inventory_deduplicates_nested_roots_and_counts_sidecars(tmp_path):
    settings = _settings(tmp_path)
    paths = settings.paths
    paths.db_dir.mkdir(parents=True)
    paths.raw_dir.mkdir(parents=True)
    paths.cache_dir.mkdir(parents=True)

    paths.raw_dir.joinpath("dfp.zip").write_bytes(b"a" * 100)
    paths.cache_dir.joinpath("market.json").write_bytes(b"b" * 50)
    db_path = paths.db_path
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES ('x')")
    Path(f"{db_path}-wal").write_bytes(b"w" * 25)
    Path(f"{db_path}-shm").write_bytes(b"s" * 10)

    manager = StorageInventoryManager(settings)
    inventory = manager.scan()

    assert inventory["logical_bytes_total"] >= 185
    assert inventory["file_count"] >= 4
    assert any(row["id"] == "databases" for row in inventory["categories"])
    assert any(row["id"] == "database_sidecars" for row in inventory["categories"])
    assert any(item["reason"].startswith("nested under") for item in inventory["excluded_roots"])
    assert inventory["performance"]["full_database_table_scans"] is False
    assert inventory["largest_items"]

    cvm_db = next(db for db in inventory["databases"] if db["id"] == "cvm_financials")
    assert cvm_db["exists"] is True
    assert cvm_db["logical_bytes"] > 0
    assert cvm_db["wal_bytes"] == 25
    assert cvm_db["shm_bytes"] == 10
    assert cvm_db["sqlite"]["page_size"] > 0
    assert cvm_db["sqlite"]["estimated_internal_free_bytes"] >= 0


def test_storage_inventory_persists_latest_snapshot_and_bounded_history(tmp_path):
    settings = _settings(tmp_path)
    settings.paths.data_dir.mkdir(parents=True)
    settings.paths.data_dir.joinpath("sample.txt").write_bytes(b"x" * 12)

    manager = StorageInventoryManager(settings)
    inventory = manager.scan()
    manager._write_snapshot(inventory)

    latest = manager.latest()
    assert latest["is_cached"] is True
    assert latest["logical_bytes_total"] >= 12
    assert latest["history"]

    for day in range(110):
        payload = dict(inventory)
        payload["scanned_at"] = f"2026-01-{(day % 28) + 1:02d}T00:00:00Z"
        payload["logical_bytes_total"] = day
        manager._write_snapshot(payload)

    assert len(manager.latest()["history"]) <= 90


def test_storage_inventory_rejects_concurrent_scan(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    settings.paths.data_dir.mkdir(parents=True)
    manager = StorageInventoryManager(settings)

    def slow_scan():
        time.sleep(0.2)
        return {
            "contract_version": 1,
            "status": "healthy",
            "generated_at": "2026-01-01T00:00:00Z",
            "scanned_at": "2026-01-01T00:00:00Z",
            "logical_bytes_total": 0,
            "file_count": 0,
            "directory_count": 0,
            "skipped_count": 0,
            "elapsed_ms": 200,
            "roots": [],
            "excluded_roots": [],
            "volumes": [],
            "categories": [],
            "segments": [],
            "databases": [],
            "largest_items": [],
            "growth": {},
            "history": [],
            "warnings": [],
            "errors": [],
            "measurement_notes": [],
        }

    monkeypatch.setattr(manager, "scan", slow_scan)

    first = manager.start_scan(persist=False)
    second = manager.start_scan(persist=False)

    assert first["started"] is True
    assert second["started"] is False
    assert second["scan_status"]["status"] == "running"
