"""Priority merge, derived KPI computation, and data quality status assignment.

v1: OWID-only. Ember path is stubbed.
All derivation is local — not from source.
"""
from __future__ import annotations

import logging

import pandas as pd

from src.energy_kpi.catalog import DERIVED_KPI_IDS, _ENERGY_CATALOG, _NS

logger = logging.getLogger(__name__)

# Threshold for OWID vs Ember conflict detection (for future Ember integration)
_CONFLICT_THRESHOLD_SHARE = 0.10  # 10 percentage-point difference for % KPIs
_CONFLICT_THRESHOLD_DEFAULT = 0.10  # 10% relative difference for volumes/intensities


def compute_derived_kpis(direct_df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived KPIs (yoy growth, 5y trend) from direct OWID series.

    Returns a new DataFrame of derived rows to concatenate with direct_df.
    Input: tidy DataFrame with columns kpi_id, iso_code, period, value, ...
    """
    derived_rows: list[pd.DataFrame] = []

    # ── derived_yoy: elec_demand_growth_yoy ──────────────────────────────────
    demand_kpi = f"{_NS}.elec_demand_total"
    demand = direct_df[direct_df["kpi_id"] == demand_kpi].copy()
    if not demand.empty:
        demand_sorted = demand.sort_values(["iso_code", "period"])
        demand_sorted["prev_value"] = demand_sorted.groupby("iso_code")["value"].shift(1)
        mask = demand_sorted["prev_value"].notna() & (demand_sorted["prev_value"] != 0)
        yoy = demand_sorted[mask].copy()
        yoy["value"] = (yoy["value"] / yoy["prev_value"] - 1) * 100
        yoy["kpi_id"] = f"{_NS}.elec_demand_growth_yoy"
        yoy["unit"] = "%"
        yoy["source_field"] = "electricity_demand"
        yoy = yoy.drop(columns=["prev_value"], errors="ignore")
        derived_rows.append(yoy[direct_df.columns])

    # ── derived_trend: elec_renewables_share_5y_chg ──────────────────────────
    renew_kpi = f"{_NS}.elec_renewables_share"
    renew = direct_df[direct_df["kpi_id"] == renew_kpi].copy()
    if not renew.empty:
        renew_sorted = renew.sort_values(["iso_code", "period"])
        renew_sorted["lag5_value"] = renew_sorted.groupby("iso_code")["value"].shift(5)
        mask5 = renew_sorted["lag5_value"].notna()
        trend = renew_sorted[mask5].copy()
        trend["value"] = trend["value"] - trend["lag5_value"]
        trend["kpi_id"] = f"{_NS}.elec_renewables_share_5y_chg"
        trend["unit"] = "pp"
        trend["source_field"] = "renewables_share_elec"
        trend = trend.drop(columns=["lag5_value"], errors="ignore")
        derived_rows.append(trend[direct_df.columns])

    if not derived_rows:
        return pd.DataFrame(columns=direct_df.columns)

    result = pd.concat(derived_rows, ignore_index=True)
    logger.info("Computed %d derived KPI rows", len(result))
    return result


def merge_sources(
    owid_df: pd.DataFrame,
    ember_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Merge OWID (priority 1) with optional Ember (priority 2).

    v1: Ember is always None (deferred). Ember path kept for future integration.
    Returns a unified tidy DataFrame ready for DQ status assignment + upsert.
    """
    if ember_df is None or ember_df.empty:
        # v1 path: OWID only
        merged = owid_df.copy()
        merged["value_owid"] = merged["value"]
        merged["value_ember"] = None
        merged["source_conflict"] = False
        merged["fallback_used"] = False
        return merged

    # Future Ember merge path (not reached in v1)
    merged = owid_df.copy()
    merged["value_owid"] = merged["value"]

    ember_index = ember_df.set_index(["kpi_id", "iso_code", "period"])["value"]
    merged["value_ember"] = merged.set_index(["kpi_id", "iso_code", "period"]).index.map(
        lambda idx: ember_index.get(idx)
    )

    # Detect conflicts
    has_both = merged["value_owid"].notna() & merged["value_ember"].notna()
    denom = merged[["value_owid", "value_ember"]].abs().max(axis=1).clip(lower=1e-9)
    rel_diff = ((merged["value_owid"] - merged["value_ember"]).abs() / denom)
    merged["source_conflict"] = has_both & (rel_diff > _CONFLICT_THRESHOLD_DEFAULT)
    merged["fallback_used"] = False

    # Fill OWID gaps from Ember where available
    gap = merged["value_owid"].isna() & merged["value_ember"].notna()
    merged.loc[gap, "value"] = merged.loc[gap, "value_ember"]
    merged.loc[gap, "source"] = "EMBER"
    merged.loc[gap, "source_priority"] = 2
    merged.loc[gap, "fallback_used"] = True

    return merged


def set_data_quality_status(
    df: pd.DataFrame,
    owid_fetched_at: str | None = None,
    stale_threshold_days: int = 90,
) -> pd.DataFrame:
    """Assign data_quality_status to each row.

    Possible values: 'ok', 'conflict', 'fallback_used', 'stale', 'missing'.
    Priority: conflict > fallback_used > stale > ok.
    'missing' is set for rows where value is null.
    """
    from datetime import datetime, timezone

    df = df.copy()
    df["data_quality_status"] = "ok"

    # Missing value
    df.loc[df["value"].isna(), "data_quality_status"] = "missing"

    # Fallback used
    if "fallback_used" in df.columns:
        df.loc[df["fallback_used"].astype(bool), "data_quality_status"] = "fallback_used"

    # Conflict (overwrites fallback_used — conflict is higher priority to surface)
    if "source_conflict" in df.columns:
        df.loc[df["source_conflict"].astype(bool), "data_quality_status"] = "conflict"

    # Stale — if owid_fetched_at is older than stale_threshold_days mark all ok/missing as stale
    if owid_fetched_at:
        try:
            fetched = datetime.fromisoformat(owid_fetched_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - fetched).days
            if age_days > stale_threshold_days:
                stale_mask = df["data_quality_status"].isin(("ok", "missing"))
                df.loc[stale_mask, "data_quality_status"] = "stale"
        except Exception:
            pass

    return df
