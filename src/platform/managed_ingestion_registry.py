"""Registry for large local-first managed ingestion contracts."""
from __future__ import annotations

from src.energy_kpi.distribution.mmgd_store import MMGD_CONTRACT
from src.energy_kpi.hourly_store_ingest import CCEE_HOURLY_CONTRACT
from src.platform.managed_ingestion_contract import ManagedDatasetContract


def registered_managed_dataset_contracts() -> tuple[ManagedDatasetContract, ...]:
    """Return all implemented large-fact managed storage contracts."""
    return (
        CCEE_HOURLY_CONTRACT,
        MMGD_CONTRACT,
    )
