#!/usr/bin/env python3
"""Check CVMAnalytics local storage against release/storage budgets."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from desktop.storage_inventory import StorageInventoryManager  # noqa: E402
from src.platform.settings import build_settings  # noqa: E402

GIB = 1024**3


@dataclass(frozen=True)
class StorageBudget:
    max_main_db_bytes: int
    max_database_category_bytes: int
    max_active_local_bytes: int
    fail_on_backups: bool = False


def _format_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(value)
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def _category_bytes(inventory: dict[str, Any], category_id: str) -> int:
    for row in inventory.get("categories") or []:
        if row.get("id") == category_id:
            return int(row.get("logical_bytes") or 0)
    return 0


def _backup_bytes(inventory: dict[str, Any]) -> int:
    candidates = inventory.get("backup_candidates") or []
    if candidates:
        return sum(int(row.get("reclaimable_bytes") or row.get("logical_bytes") or 0) for row in candidates)
    return _category_bytes(inventory, "backups")


def evaluate_storage_budget(inventory: dict[str, Any], budget: StorageBudget) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for db in inventory.get("databases") or []:
        size = int(db.get("logical_bytes") or 0)
        if size > budget.max_main_db_bytes:
            failures.append({
                "check": "main_database_size",
                "id": db.get("id"),
                "label": db.get("label"),
                "actual_bytes": size,
                "limit_bytes": budget.max_main_db_bytes,
                "message": (
                    f"{db.get('label') or db.get('id') or 'database'} is {_format_bytes(size)}, "
                    f"above the {_format_bytes(budget.max_main_db_bytes)} main-DB budget."
                ),
            })

    database_category_bytes = _category_bytes(inventory, "databases")
    if database_category_bytes > budget.max_database_category_bytes:
        failures.append({
            "check": "database_category_size",
            "actual_bytes": database_category_bytes,
            "limit_bytes": budget.max_database_category_bytes,
            "message": (
                f"All main databases total {_format_bytes(database_category_bytes)}, "
                f"above the {_format_bytes(budget.max_database_category_bytes)} budget."
            ),
        })

    total_bytes = int(inventory.get("logical_bytes_total") or 0)
    backup_bytes = _backup_bytes(inventory)
    active_bytes = max(0, total_bytes - backup_bytes)
    if active_bytes > budget.max_active_local_bytes:
        failures.append({
            "check": "active_local_storage_size",
            "actual_bytes": active_bytes,
            "limit_bytes": budget.max_active_local_bytes,
            "message": (
                f"Active local storage excluding rollback backups is {_format_bytes(active_bytes)}, "
                f"above the {_format_bytes(budget.max_active_local_bytes)} budget."
            ),
        })

    if backup_bytes > 0:
        row = {
            "check": "rollback_backups_present",
            "actual_bytes": backup_bytes,
            "limit_bytes": 0,
            "message": (
                f"Rollback backups can reclaim {_format_bytes(backup_bytes)} after validation. "
                "They are excluded from active-storage budget by default."
            ),
        }
        if budget.fail_on_backups:
            failures.append(row)
        else:
            warnings.append(row)

    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "summary": {
            "total_bytes": total_bytes,
            "backup_bytes": backup_bytes,
            "active_bytes_excluding_backups": active_bytes,
            "database_category_bytes": database_category_bytes,
            "max_main_db_bytes": budget.max_main_db_bytes,
            "max_database_category_bytes": budget.max_database_category_bytes,
            "max_active_local_bytes": budget.max_active_local_bytes,
            "fail_on_backups": budget.fail_on_backups,
        },
        "failures": failures,
        "warnings": warnings,
    }


def _load_inventory(path: Path | None, *, scan: bool) -> dict[str, Any]:
    if scan:
        return StorageInventoryManager(build_settings()).scan()
    if path is not None:
        return json.loads(path.read_text(encoding="utf-8"))
    manager = StorageInventoryManager(build_settings())
    latest = manager.latest()
    if latest.get("status") == "unknown" and not latest.get("scanned_at"):
        raise FileNotFoundError(f"No cached storage inventory at {manager.snapshot_path}. Run with --scan first.")
    return latest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail when CVMAnalytics local storage exceeds configured budgets.")
    parser.add_argument("--inventory-json", type=Path, help="Existing storage_inventory_v1.json to check.")
    parser.add_argument("--scan", action="store_true", help="Run a fresh storage scan instead of reading the cached inventory.")
    parser.add_argument("--max-main-db-gib", type=float, default=12.0, help="Maximum size for any one main SQLite database.")
    parser.add_argument("--max-database-category-gib", type=float, default=16.0, help="Maximum total size for main SQLite databases.")
    parser.add_argument("--max-active-local-gib", type=float, default=32.0, help="Maximum total local storage excluding rollback backups.")
    parser.add_argument("--fail-on-backups", action="store_true", help="Treat retained rollback backups as a failure instead of a warning.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    budget = StorageBudget(
        max_main_db_bytes=int(float(args.max_main_db_gib) * GIB),
        max_database_category_bytes=int(float(args.max_database_category_gib) * GIB),
        max_active_local_bytes=int(float(args.max_active_local_gib) * GIB),
        fail_on_backups=bool(args.fail_on_backups),
    )
    result = evaluate_storage_budget(
        _load_inventory(args.inventory_json, scan=bool(args.scan)),
        budget,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
