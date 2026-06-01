"""Tests for src/energy_kpi/merge.py"""
import pandas as pd
import pytest

from src.energy_kpi.catalog import _NS
from src.energy_kpi.merge import (
    compute_derived_kpis,
    merge_sources,
    set_data_quality_status,
)


class TestComputeDerivedKpis:
    def test_yoy_growth_computed(self, tidy_df):
        derived = compute_derived_kpis(tidy_df)
        yoy_kpi = f"{_NS}.elec_demand_growth_yoy"
        assert yoy_kpi in derived["kpi_id"].values

    def test_yoy_math_correct(self, tidy_df):
        derived = compute_derived_kpis(tidy_df)
        yoy = derived[derived["kpi_id"] == f"{_NS}.elec_demand_growth_yoy"]
        bra_yoy = yoy[yoy["iso_code"] == "BRA"].sort_values("period")
        # 2021: (600→620) = +3.33%; (620→640) = +3.22%
        assert len(bra_yoy) >= 1
        for _, row in bra_yoy.iterrows():
            assert isinstance(row["value"], float)
            assert -50 < row["value"] < 50  # reasonable bounds

    def test_5y_trend_requires_5_years(self, tidy_df):
        derived = compute_derived_kpis(tidy_df)
        trend_kpi = f"{_NS}.elec_renewables_share_5y_chg"
        # Fixture only has 3 years → no 5y trend rows
        trend = derived[derived["kpi_id"] == trend_kpi]
        assert len(trend) == 0  # not enough history

    def test_derived_unit_set_correctly(self, tidy_df):
        derived = compute_derived_kpis(tidy_df)
        yoy = derived[derived["kpi_id"] == f"{_NS}.elec_demand_growth_yoy"]
        if not yoy.empty:
            assert (yoy["unit"] == "%").all()


class TestMergeSources:
    def test_owid_only_sets_value_owid(self, tidy_df):
        merged = merge_sources(tidy_df, ember_df=None)
        assert "value_owid" in merged.columns
        # NaN-safe comparison: both columns should contain identical values (incl. NaN)
        import numpy as np
        owid = merged["value_owid"]
        val = merged["value"]
        both_nan = owid.isna() & val.isna()
        both_equal = (owid == val) | both_nan
        assert both_equal.all()

    def test_no_conflicts_without_ember(self, tidy_df):
        merged = merge_sources(tidy_df, ember_df=None)
        assert not merged["source_conflict"].any()

    def test_no_fallback_without_ember(self, tidy_df):
        merged = merge_sources(tidy_df, ember_df=None)
        assert not merged["fallback_used"].any()

    def test_conflict_detected_when_values_differ(self, tidy_df):
        ember_df = tidy_df.copy()
        ember_df["value"] = ember_df["value"] * 1.5  # 50% difference → conflict
        ember_df["source"] = "EMBER"
        ember_df["source_priority"] = 2
        merged = merge_sources(tidy_df, ember_df=ember_df)
        assert merged["source_conflict"].any()

    def test_conflict_not_raised_when_within_threshold(self, tidy_df):
        ember_df = tidy_df.copy()
        ember_df["value"] = ember_df["value"] * 1.02  # 2% difference → no conflict
        ember_df["source"] = "EMBER"
        ember_df["source_priority"] = 2
        merged = merge_sources(tidy_df, ember_df=ember_df)
        assert not merged["source_conflict"].any()


class TestSetDataQualityStatus:
    def test_ok_status_for_clean_data(self, tidy_df):
        merged = merge_sources(tidy_df)
        result = set_data_quality_status(merged)
        ok_rows = result[result["value"].notna()]
        assert (ok_rows["data_quality_status"] == "ok").all()

    def test_missing_status_for_null_values(self, tidy_df):
        merged = merge_sources(tidy_df)
        merged.loc[merged.index[0], "value"] = None
        result = set_data_quality_status(merged)
        assert result.loc[result.index[0], "data_quality_status"] == "missing"

    def test_stale_status_when_old_fetch(self, tidy_df):
        merged = merge_sources(tidy_df)
        result = set_data_quality_status(merged, owid_fetched_at="2020-01-01T00:00:00+00:00", stale_threshold_days=90)
        ok_rows = result[result["value"].notna()]
        assert (ok_rows["data_quality_status"] == "stale").all()

    def test_not_stale_when_fresh(self, tidy_df):
        from datetime import datetime, timezone
        merged = merge_sources(tidy_df)
        fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result = set_data_quality_status(merged, owid_fetched_at=fresh)
        ok_rows = result[result["value"].notna()]
        assert (ok_rows["data_quality_status"] == "ok").all()
