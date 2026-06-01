"""Tests for src/energy_kpi/ingest_owid.py"""
import pytest
import pandas as pd

from src.energy_kpi.catalog import _NS, V1_REQUIRED_IDS
from src.energy_kpi.ingest_owid import (
    V1_ISO_CODES,
    _DIRECT_SOURCE_FIELDS,
    normalize_owid,
    persist_snapshot_record,
    seed_country_dimension,
    seed_kpi_catalog,
    seed_kpi_sources,
    upsert_country_kpi_values,
)


class TestNormalizeOwid:
    def test_output_columns(self, snapshot):
        df = normalize_owid(snapshot)
        expected = {"kpi_id", "iso_code", "country_name", "period", "value",
                    "source_field", "unit", "source", "source_priority", "snapshot_id"}
        assert expected == set(df.columns)

    def test_filters_to_v1_countries(self, snapshot):
        df = normalize_owid(snapshot)
        assert set(df["iso_code"].unique()).issubset(V1_ISO_CODES)

    def test_filters_to_subset(self, snapshot):
        df = normalize_owid(snapshot, iso_filter=frozenset({"BRA"}))
        assert set(df["iso_code"].unique()) == {"BRA"}

    def test_kpi_ids_are_namespaced(self, snapshot):
        df = normalize_owid(snapshot)
        assert all(kid.startswith("energy_utilities.country.") for kid in df["kpi_id"])

    def test_source_column(self, snapshot):
        df = normalize_owid(snapshot)
        assert (df["source"] == "OWID").all()

    def test_source_priority_is_1(self, snapshot):
        df = normalize_owid(snapshot)
        assert (df["source_priority"] == 1).all()

    def test_snapshot_id_propagated(self, snapshot):
        df = normalize_owid(snapshot)
        assert (df["snapshot_id"] == snapshot.snapshot_id).all()

    def test_no_nulls_in_required_id_cols(self, snapshot):
        df = normalize_owid(snapshot)
        for col in ("kpi_id", "iso_code", "period"):
            assert df[col].notna().all(), f"nulls in {col}"

    def test_period_is_int(self, snapshot):
        df = normalize_owid(snapshot)
        assert pd.api.types.is_integer_dtype(df["period"])

    def test_required_kpis_present(self, snapshot):
        df = normalize_owid(snapshot)
        found_ids = set(df["kpi_id"].unique())
        # Required direct KPIs (not derived) should be present
        from src.energy_kpi.catalog import _ENERGY_CATALOG
        required_direct = {k.kpi_id for k in _ENERGY_CATALOG
                           if k.v1_status == "v1_required" and k.calculation_method == "direct"}
        # At minimum the ones present in our fixture CSV
        for kpi_id in required_direct:
            assert kpi_id in found_ids, f"required KPI {kpi_id} missing from normalized output"


class TestPersistence:
    def test_persist_snapshot_record(self, snapshot, db_conn):
        persist_snapshot_record(db_conn, snapshot)
        from sqlalchemy import text
        row = db_conn.execute(
            text("SELECT snapshot_id, source, sha256 FROM source_snapshots WHERE snapshot_id=:sid"),
            {"sid": snapshot.snapshot_id},
        ).fetchone()
        assert row is not None
        assert row[0] == snapshot.snapshot_id
        assert row[1] == "OWID"
        assert row[2] == "deadbeef"

    def test_upsert_country_kpi_values(self, snapshot, tidy_df, db_conn):
        from src.energy_kpi.merge import merge_sources, set_data_quality_status
        merged = merge_sources(tidy_df)
        merged = set_data_quality_status(merged)
        count = upsert_country_kpi_values(db_conn, merged)
        assert count > 0

    def test_seed_kpi_sources(self, db_conn):
        seed_kpi_sources(db_conn)
        from sqlalchemy import text
        rows = db_conn.execute(text("SELECT source FROM kpi_sources")).fetchall()
        sources = {r[0] for r in rows}
        assert "OWID" in sources

    def test_seed_country_dimension(self, db_conn):
        seed_country_dimension(db_conn)
        from sqlalchemy import text
        rows = db_conn.execute(
            text("SELECT iso_code FROM country_dimension WHERE is_v1_scope=1")
        ).fetchall()
        iso_codes = {r[0] for r in rows}
        assert "BRA" in iso_codes
        assert len(iso_codes) == 6

    def test_seed_kpi_catalog(self, db_conn):
        seed_kpi_catalog(db_conn)
        from sqlalchemy import text
        count = db_conn.execute(text("SELECT COUNT(*) FROM kpi_catalog")).scalar()
        assert count == 21
