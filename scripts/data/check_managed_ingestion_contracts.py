"""Validate registered managed-ingestion contracts and optional local manifests."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Any

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
from src.platform.managed_ingestion_registry import registered_managed_dataset_contracts  # noqa: E402
from src.platform.settings import build_settings  # noqa: E402


def _issue(contract: ManagedDatasetContract, check: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": contract.dataset_id,
        "domain": contract.domain,
        "check": check,
        "message": message,
    }
    payload.update(extra)
    return payload


def build_managed_ingestion_contract_report(
    *,
    data_dir: Path,
    contracts: Iterable[ManagedDatasetContract],
    require_manifests: bool = False,
) -> dict[str, Any]:
    """Build a validation report for managed ingestion contracts."""
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for contract in contracts:
        paths = managed_store_paths(data_dir, domain=contract.domain, dataset_id=contract.dataset_id)
        entry = {
            "dataset_id": contract.dataset_id,
            "domain": contract.domain,
            "fact_grain": contract.fact_grain,
            "manifest_path": str(paths.manifest_path),
            "manifest_exists": paths.manifest_path.exists(),
            "storage_layers": list(contract.storage_layers),
        }
        entries.append(entry)

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

    return {
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "summary": {
            "contracts": len(entries),
            "failures": len(failures),
            "warnings": len(warnings),
            "require_manifests": require_manifests,
            "data_dir": str(Path(data_dir)),
        },
        "contracts": entries,
        "failures": failures,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate managed-ingestion contracts and manifests.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Data root to inspect. Defaults to configured app data dir.")
    parser.add_argument("--require-manifests", action="store_true", help="Fail when a registered manifest is missing.")
    args = parser.parse_args(argv)

    settings = build_settings()
    data_dir = args.data_dir or settings.paths.data_dir
    report = build_managed_ingestion_contract_report(
        data_dir=data_dir,
        contracts=registered_managed_dataset_contracts(),
        require_manifests=bool(args.require_manifests),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
