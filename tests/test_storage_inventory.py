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
            news_db_path=data / "db" / "news.db",
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
    assert any(db["id"] == "news" for db in inventory["databases"])


def test_storage_inventory_reports_news_db_as_separate_readable_database(tmp_path):
    settings = _settings(tmp_path)
    paths = settings.paths
    paths.db_dir.mkdir(parents=True)

    for db_path in (paths.db_path, paths.energy_kpi_db_path, paths.news_db_path):
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO sample(value) VALUES ('x')")

    manager = StorageInventoryManager(settings)
    inventory = manager.scan()
    databases = {db["id"]: db for db in inventory["databases"]}

    assert set(databases) >= {"cvm_financials", "energy_kpis", "news"}
    assert databases["news"]["label"] == "News"
    assert databases["news"]["segment_id"] == "news"
    assert databases["news"]["segment_label"] == "Financial news"
    assert databases["news"]["exists"] is True
    assert databases["news"]["readable"] is True
    assert databases["news"]["sqlite"]["page_size"] > 0


def test_storage_inventory_classifies_analytical_stores_and_backups(tmp_path):
    settings = _settings(tmp_path)
    paths = settings.paths
    hourly_store = paths.data_dir / "analytics" / "energy" / "ccee_plant_generation_hourly"
    backup_dir = paths.data_dir / "backup" / "energy_kpis_swap_20260629T142611Z"
    hourly_store.mkdir(parents=True)
    backup_dir.mkdir(parents=True)
    hourly_store.joinpath("manifest.json").write_bytes(b"a" * 10)
    hourly_store.joinpath("energy_hot.sqlite").write_bytes(b"b" * 20)
    backup_dir.joinpath("energy_kpis.db").write_bytes(b"c" * 30)

    manager = StorageInventoryManager(settings)
    inventory = manager.scan()

    categories = {row["id"]: row for row in inventory["categories"]}
    segments = {row["id"]: row for row in inventory["segments"]}
    assert categories["analytical_stores"]["logical_bytes"] == 30
    assert categories["backups"]["logical_bytes"] == 30
    assert segments["energy_macro"]["logical_bytes"] == 30
    assert segments["local_backups"]["logical_bytes"] == 30
    assert inventory["backup_candidates"] == [
        {
            "id": "energy_kpis_swap_20260629T142611Z",
            "label": "Energy KPI rollback backup",
            "path": str(backup_dir),
            "logical_bytes": 30,
            "file_count": 1,
            "modified_at": inventory["backup_candidates"][0]["modified_at"],
            "reclaimable_bytes": 30,
            "requires_confirmation": True,
            "destructive": True,
            "reason": "Rollback backup retained after a storage migration. Remove only after current data has been validated.",
        }
    ]


def test_storage_inventory_reports_managed_raw_snapshot_history(tmp_path):
    settings = _settings(tmp_path)
    paths = settings.paths
    base = paths.data_dir / "analytics" / "energy" / "fuel_distribution_sector_intake"
    raw_root = base / "raw"
    old_snapshot = raw_root / "fuel_distribution_20260630T120000Z"
    current_snapshot = raw_root / "fuel_distribution_20260701T120000Z"
    old_snapshot.mkdir(parents=True)
    current_snapshot.mkdir(parents=True)
    old_snapshot.joinpath("old.csv").write_bytes(b"a" * 10)
    current_snapshot.joinpath("current.csv").write_bytes(b"b" * 20)
    base.joinpath("manifest.json").write_text(
        '{"selection": {"import_batch_id": "fuel_distribution_20260701T120000Z"}}',
        encoding="utf-8",
    )

    manager = StorageInventoryManager(settings)
    inventory = manager.scan()

    history = inventory["managed_snapshot_history"]
    assert [row["snapshot_id"] for row in history] == [
        "fuel_distribution_20260701T120000Z",
        "fuel_distribution_20260630T120000Z",
    ]
    assert history[0]["dataset_id"] == "fuel_distribution_sector_intake"
    assert history[0]["domain"] == "energy"
    assert history[0]["logical_bytes"] == 20
    assert history[0]["file_count"] == 1
    assert history[0]["active_in_manifest"] is True
    assert history[0]["status"] == "current"
    assert history[1]["logical_bytes"] == 10
    assert history[1]["active_in_manifest"] is False
    assert history[1]["status"] == "retained_audit_snapshot"
    assert "not a cleanup action" in history[1]["reason"]


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
