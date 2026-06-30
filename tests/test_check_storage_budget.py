from __future__ import annotations

from scripts.data.check_storage_budget import GIB, StorageBudget, evaluate_storage_budget


def _inventory(*, energy_db_bytes: int, backup_bytes: int = 0, total_bytes: int | None = None):
    database_bytes = energy_db_bytes + 1 * GIB
    categories = [
        {"id": "databases", "logical_bytes": database_bytes},
    ]
    backup_candidates = []
    if backup_bytes:
        categories.append({"id": "backups", "logical_bytes": backup_bytes})
        backup_candidates.append({
            "id": "energy_kpis_swap_test",
            "logical_bytes": backup_bytes,
            "reclaimable_bytes": backup_bytes,
        })
    return {
        "logical_bytes_total": total_bytes if total_bytes is not None else database_bytes + backup_bytes,
        "categories": categories,
        "backup_candidates": backup_candidates,
        "databases": [
            {"id": "cvm_financials", "label": "CVM financials", "logical_bytes": 1 * GIB},
            {"id": "energy_kpis", "label": "Energy KPIs", "logical_bytes": energy_db_bytes},
        ],
    }


def test_storage_budget_fails_oversized_main_database():
    result = evaluate_storage_budget(
        _inventory(energy_db_bytes=13 * GIB),
        StorageBudget(
            max_main_db_bytes=12 * GIB,
            max_database_category_bytes=20 * GIB,
            max_active_local_bytes=32 * GIB,
        ),
    )

    assert result["ok"] is False
    assert result["failures"][0]["check"] == "main_database_size"
    assert result["failures"][0]["id"] == "energy_kpis"


def test_storage_budget_excludes_rollback_backups_by_default():
    result = evaluate_storage_budget(
        _inventory(energy_db_bytes=5 * GIB, backup_bytes=29 * GIB),
        StorageBudget(
            max_main_db_bytes=12 * GIB,
            max_database_category_bytes=20 * GIB,
            max_active_local_bytes=10 * GIB,
        ),
    )

    assert result["ok"] is True
    assert result["summary"]["active_bytes_excluding_backups"] == 6 * GIB
    assert result["warnings"][0]["check"] == "rollback_backups_present"


def test_storage_budget_can_fail_when_backups_are_not_allowed():
    result = evaluate_storage_budget(
        _inventory(energy_db_bytes=5 * GIB, backup_bytes=1 * GIB),
        StorageBudget(
            max_main_db_bytes=12 * GIB,
            max_database_category_bytes=20 * GIB,
            max_active_local_bytes=10 * GIB,
            fail_on_backups=True,
        ),
    )

    assert result["ok"] is False
    assert result["failures"][0]["check"] == "rollback_backups_present"
