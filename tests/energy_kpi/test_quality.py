"""Tests for src/energy_kpi/quality.py — DQ check suite."""
import uuid

import pandas as pd
import pytest

from src.energy_kpi.catalog import _NS
from src.energy_kpi.ingest_owid import (
    seed_country_dimension,
    seed_kpi_catalog,
    seed_kpi_sources,
)
from src.energy_kpi.merge import merge_sources, set_data_quality_status
from src.energy_kpi.quality import (
    DQCheckResult,
    NON_NEGATIVE_KPIS,
    SHARE_KPIS,
    run_quality_checks,
)


def _run_checks(tidy_df, db_conn):
    run_id = str(uuid.uuid4())
    seed_kpi_sources(db_conn)
    seed_country_dimension(db_conn)
    seed_kpi_catalog(db_conn)
    results = run_quality_checks(db_conn, run_id, tidy_df)
    return results


def _find(results: list[DQCheckResult], check_name: str) -> DQCheckResult | None:
    return next((r for r in results if r.check_name == check_name), None)


class TestSchemaCheck:
    def test_passes_with_valid_data(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "schema_required_fields")
        assert r is not None and r.passed

    def test_fails_when_required_field_missing(self, snapshot, db_conn):
        import pandas as pd
        empty_df = pd.DataFrame(columns=["kpi_id", "iso_code", "period", "value", "unit",
                                          "source", "source_priority", "source_field", "snapshot_id"])
        results = _run_checks(empty_df, db_conn)
        r = _find(results, "schema_required_fields")
        assert r is not None and not r.passed


class TestRequiredFieldsCheck:
    def test_passes_with_no_nulls(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "required_fields_not_null")
        assert r is not None and r.passed

    def test_fails_when_iso_code_is_null(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        merged = merged.copy()
        merged.loc[merged.index[0], "iso_code"] = None
        results = _run_checks(merged, db_conn)
        r = _find(results, "required_fields_not_null")
        assert r is not None and not r.passed


class TestIsoValidityCheck:
    def test_passes_for_v1_countries(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "iso_validity")
        assert r is not None and r.passed

    def test_warns_for_unknown_country(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df).copy()
        extra = merged.iloc[0:1].copy()
        extra["iso_code"] = "XXX"
        import pandas as pd
        merged = pd.concat([merged, extra], ignore_index=True)
        results = _run_checks(merged, db_conn)
        r = _find(results, "iso_validity")
        assert r is not None and not r.passed
        assert "XXX" in r.details.get("unexpected_iso_codes", [])


class TestDuplicatePKCheck:
    def test_passes_with_unique_pk(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "duplicate_pk")
        assert r is not None and r.passed

    def test_fails_with_duplicate(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        import pandas as pd
        duped = pd.concat([merged, merged.iloc[0:1]], ignore_index=True)
        results = _run_checks(duped, db_conn)
        r = _find(results, "duplicate_pk")
        assert r is not None and not r.passed


class TestImpossibleNegativesCheck:
    def test_passes_with_clean_data(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "impossible_negatives")
        assert r is not None and r.passed

    def test_fails_when_share_is_negative(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df).copy()
        share_kpi = f"{_NS}.elec_renewables_share"
        merged.loc[merged["kpi_id"] == share_kpi, "value"] = -5.0
        results = _run_checks(merged, db_conn)
        r = _find(results, "impossible_negatives")
        assert r is not None and not r.passed


class TestShareBoundsCheck:
    def test_passes_with_valid_shares(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "share_bounds")
        assert r is not None and r.passed

    def test_fails_when_share_exceeds_100(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df).copy()
        share_kpi = f"{_NS}.elec_renewables_share"
        merged.loc[merged["kpi_id"] == share_kpi, "value"] = 105.0
        results = _run_checks(merged, db_conn)
        r = _find(results, "share_bounds")
        assert r is not None and not r.passed


class TestReproducibilityCheck:
    def test_passes_when_all_rows_have_snapshot_id(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        r = _find(results, "reproducibility")
        assert r is not None and r.passed

    def test_fails_when_snapshot_id_missing(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df).copy()
        merged.loc[merged.index[0], "snapshot_id"] = None
        results = _run_checks(merged, db_conn)
        r = _find(results, "reproducibility")
        assert r is not None and not r.passed


class TestAllChecksInsertedToDB:
    def test_all_checks_written_to_db(self, tidy_df, db_conn):
        merged = merge_sources(tidy_df)
        results = _run_checks(merged, db_conn)
        from sqlalchemy import text
        count = db_conn.execute(
            text("SELECT COUNT(*) FROM data_quality_checks")
        ).scalar()
        assert count == len(results)
