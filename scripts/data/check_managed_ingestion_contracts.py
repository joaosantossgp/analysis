"""Validate registered managed-ingestion contracts and optional local manifests."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.platform.managed_ingestion_contract import (  # noqa: E402
    ManagedDatasetContract,
    ManagedStoreValidationError,
    managed_store_paths,
    validate_contract,
    validate_manifest_contract,
)
from src.platform.managed_ingestion_registry import (  # noqa: E402
    ManagedDatasetRegistration,
    ManagedSqliteTable,
    registered_managed_datasets,
    registered_sqlite_table_classifications,
)
from src.platform.settings import build_settings  # noqa: E402

DEFAULT_SQLITE_ROW_THRESHOLD = 250_000


def _issue(contract: ManagedDatasetContract, check: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": contract.dataset_id,
        "domain": contract.domain,
        "check": check,
        "message": message,
    }
    payload.update(extra)
    return payload


def _registration_from_contract(contract: ManagedDatasetContract) -> ManagedDatasetRegistration:
    return ManagedDatasetRegistration(
        status="implemented",
        contract=contract,
        manifest_required=True,
        sqlite_tables=(),
        notes="Compatibility registration for legacy contract-only validation.",
    )


def _sqlite_table_entry(table: ManagedSqliteTable) -> dict[str, Any]:
    return {
        "database": table.database,
        "table_name": table.table_name,
        "classification": table.classification,
        "notes": table.notes,
    }


def _registration_entry(
    *,
    registration: ManagedDatasetRegistration,
    manifest_path: Path,
    manifest_exists: bool,
) -> dict[str, Any]:
    contract = registration.contract
    return {
        "dataset_id": contract.dataset_id,
        "domain": contract.domain,
        "status": registration.status,
        "fact_grain": contract.fact_grain,
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_exists,
        "manifest_required": registration.manifest_required,
        "storage_layers": list(contract.storage_layers),
        "sqlite_tables": [_sqlite_table_entry(table) for table in registration.sqlite_tables],
        "notes": registration.notes,
    }


def _sqlite_paths_for_data_dir(data_dir: Path) -> tuple[Path, ...]:
    db_dir = data_dir / "db"
    if not db_dir.exists():
        return ()
    return tuple(sorted(path for path in db_dir.glob("*.db") if path.is_file()))


def _classification_lookup() -> dict[tuple[str, str], ManagedSqliteTable]:
    return {
        (table.database, table.table_name): table
        for table in registered_sqlite_table_classifications()
    }


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _scan_sqlite_large_tables(
    *,
    data_dir: Path,
    sqlite_database_paths: Iterable[Path] | None,
    sqlite_row_threshold: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    database_paths = tuple(sqlite_database_paths) if sqlite_database_paths is not None else _sqlite_paths_for_data_dir(data_dir)
    classifications = _classification_lookup()
    large_tables: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for raw_path in database_paths:
        db_path = Path(raw_path)
        if not db_path.exists():
            warnings.append(
                {
                    "database": db_path.name,
                    "check": "sqlite_database_missing",
                    "message": "SQLite database path does not exist.",
                    "path": str(db_path),
                }
            )
            continue

        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True) as conn:
                table_rows = conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                    """
                ).fetchall()
                for (table_name,) in table_rows:
                    row_count = int(
                        conn.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table_name)}").fetchone()[0]
                    )
                    if row_count < sqlite_row_threshold:
                        continue
                    classification = classifications.get((db_path.name, table_name))
                    entry = {
                        "database": db_path.name,
                        "path": str(db_path),
                        "table_name": table_name,
                        "row_count": row_count,
                        "classification": classification.classification if classification else None,
                        "notes": classification.notes if classification else None,
                    }
                    large_tables.append(entry)
                    if classification is None:
                        unclassified.append(entry)
        except sqlite3.Error as exc:
            warnings.append(
                {
                    "database": db_path.name,
                    "check": "sqlite_scan_failed",
                    "message": str(exc),
                    "path": str(db_path),
                }
            )

    return large_tables, unclassified, warnings


def build_managed_ingestion_contract_report(
    *,
    data_dir: Path,
    contracts: Iterable[ManagedDatasetContract] | None = None,
    registrations: Iterable[ManagedDatasetRegistration] | None = None,
    require_manifests: bool = False,
    scan_sqlite_large_tables: bool = False,
    sqlite_database_paths: Iterable[Path] | None = None,
    sqlite_row_threshold: int = DEFAULT_SQLITE_ROW_THRESHOLD,
) -> dict[str, Any]:
    """Build a validation report for managed ingestion contracts."""
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    implemented_entries: list[dict[str, Any]] = []
    planned_entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    if registrations is None:
        if contracts is None:
            registrations_to_check = registered_managed_datasets()
        else:
            registrations_to_check = tuple(_registration_from_contract(contract) for contract in contracts)
    else:
        registrations_to_check = tuple(registrations)

    for registration in registrations_to_check:
        contract = registration.contract
        paths = managed_store_paths(data_dir, domain=contract.domain, dataset_id=contract.dataset_id)
        entry = _registration_entry(
            registration=registration,
            manifest_path=paths.manifest_path,
            manifest_exists=paths.manifest_path.exists(),
        )
        if registration.status == "implemented":
            implemented_entries.append(entry)
        else:
            planned_entries.append(entry)

        if contract.dataset_id in seen:
            failures.append(_issue(contract, "duplicate_dataset_id", "Duplicate managed dataset contract id."))
            continue
        seen.add(contract.dataset_id)

        try:
            validate_contract(contract)
        except ManagedStoreValidationError as exc:
            failures.append(_issue(contract, "contract_invalid", str(exc)))
            continue

        if not paths.manifest_path.exists():
            if registration.manifest_required:
                issue = _issue(
                    contract,
                    "manifest_missing",
                    "Managed manifest is not present under the configured data root.",
                    manifest_path=str(paths.manifest_path),
                )
                (failures if require_manifests else warnings).append(issue)
            continue

        try:
            manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
            validate_manifest_contract(manifest, contract)
        except (json.JSONDecodeError, OSError, ManagedStoreValidationError) as exc:
            failures.append(
                _issue(
                    contract,
                    "manifest_invalid",
                    str(exc),
                    manifest_path=str(paths.manifest_path),
                )
            )

    sqlite_large_tables: list[dict[str, Any]] = []
    unclassified_large_tables: list[dict[str, Any]] = []
    if scan_sqlite_large_tables:
        sqlite_large_tables, unclassified_large_tables, sqlite_warnings = _scan_sqlite_large_tables(
            data_dir=data_dir,
            sqlite_database_paths=sqlite_database_paths,
            sqlite_row_threshold=sqlite_row_threshold,
        )
        warnings.extend(sqlite_warnings)
        for table in unclassified_large_tables:
            issue = {
                "database": table["database"],
                "table_name": table["table_name"],
                "check": "sqlite_large_table_unclassified",
                "message": (
                    "Large SQLite table is not classified as managed_externalized, "
                    "sqlite_mart, small_relational, or accepted_row_store."
                ),
                "row_count": table["row_count"],
                "path": table["path"],
            }
            (failures if require_manifests else warnings).append(issue)

    all_entries = implemented_entries + planned_entries
    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "summary": {
            "contracts": len(all_entries),
            "implemented_contracts": len(implemented_entries),
            "planned_contracts": len(planned_entries),
            "failures": len(failures),
            "warnings": len(warnings),
            "require_manifests": require_manifests,
            "scan_sqlite_large_tables": scan_sqlite_large_tables,
            "sqlite_row_threshold": sqlite_row_threshold,
            "data_dir": str(Path(data_dir)),
        },
        "contracts": all_entries,
        "implemented_contracts": implemented_entries,
        "planned_contracts": planned_entries,
        "sqlite_large_tables": sqlite_large_tables,
        "unclassified_large_tables": unclassified_large_tables,
        "failures": failures,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate managed-ingestion contracts and manifests.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Data root to inspect. Defaults to configured app data dir.")
    parser.add_argument("--require-manifests", action="store_true", help="Fail when implemented registered manifests are missing.")
    parser.add_argument(
        "--scan-sqlite-large-tables",
        action="store_true",
        help="Scan local SQLite databases and classify large tables.",
    )
    parser.add_argument(
        "--sqlite-row-threshold",
        type=int,
        default=DEFAULT_SQLITE_ROW_THRESHOLD,
        help="Row-count threshold for SQLite large-table classification.",
    )
    args = parser.parse_args(argv)

    settings = build_settings()
    data_dir = args.data_dir or settings.paths.data_dir
    report = build_managed_ingestion_contract_report(
        data_dir=data_dir,
        registrations=registered_managed_datasets(),
        require_manifests=bool(args.require_manifests),
        scan_sqlite_large_tables=bool(args.scan_sqlite_large_tables),
        sqlite_row_threshold=int(args.sqlite_row_threshold),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
