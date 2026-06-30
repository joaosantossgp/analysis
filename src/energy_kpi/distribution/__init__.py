"""Electricity distribution analytics domain module."""
from src.energy_kpi.distribution.catalog import seed_distribution_static_data, ANEEL_RESOURCES
from src.energy_kpi.distribution.quality import normalize_cnpj, check_ownership_overlaps
from src.energy_kpi.distribution.ingest import (
    fetch_distribution_resource,
    parse_samp_mercado,
    upsert_samp_mercado_facts,
    parse_samp_balanco,
    upsert_samp_balanco_facts,
    parse_continuity_actuals,
    upsert_continuity_actuals_facts,
    parse_continuity_limits,
    upsert_continuity_limits_facts,
    parse_continuity_compensations,
    upsert_continuity_compensations_facts,
    parse_tariffs,
    upsert_tariffs_facts,
    parse_delinquency,
    upsert_delinquency_facts,
    parse_mmgd,
    upsert_mmgd_facts,
    DistributionSnapshotRecord,
)
from src.energy_kpi.distribution.aggregates import (
    rebuild_distribution_aggregate_slices,
    rebuild_distribution_aggregates,
)
from src.energy_kpi.distribution.read import DistributionReadService

__all__ = [
    "seed_distribution_static_data",
    "normalize_cnpj",
    "check_ownership_overlaps",
    "fetch_distribution_resource",
    "parse_samp_mercado",
    "upsert_samp_mercado_facts",
    "parse_samp_balanco",
    "upsert_samp_balanco_facts",
    "parse_continuity_actuals",
    "upsert_continuity_actuals_facts",
    "parse_continuity_limits",
    "upsert_continuity_limits_facts",
    "parse_continuity_compensations",
    "upsert_continuity_compensations_facts",
    "parse_tariffs",
    "upsert_tariffs_facts",
    "parse_delinquency",
    "upsert_delinquency_facts",
    "parse_mmgd",
    "upsert_mmgd_facts",
    "rebuild_distribution_aggregates",
    "rebuild_distribution_aggregate_slices",
    "DistributionReadService",
    "ANEEL_RESOURCES",
    "DistributionSnapshotRecord",
]
