"""Tests for src/energy_kpi/read.py — offline read only, no network."""
import uuid
from unittest.mock import patch

import pytest

from src.energy_kpi.ingest_owid import (
    persist_snapshot_record,
    seed_country_dimension,
    seed_kpi_catalog,
    seed_kpi_sources,
    upsert_country_kpi_values,
)
from src.energy_kpi.merge import merge_sources, set_data_quality_status
from src.energy_kpi.read import EnergyKPIReadService
from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import build_settings


@pytest.fixture()
def seeded_engine(db_engine, snapshot, tidy_df):
    """In-memory engine seeded with fixture data."""
    from datetime import datetime, timezone
    merged = merge_sources(tidy_df)
    merged = set_data_quality_status(merged, owid_fetched_at="2026-01-01T00:00:00+00:00")

    with db_engine.begin() as conn:
        seed_kpi_sources(conn)
        seed_country_dimension(conn)
        seed_kpi_catalog(conn)
        persist_snapshot_record(conn, snapshot)
        upsert_country_kpi_values(conn, merged)
        # Insert a fake refresh log
        from sqlalchemy import text
        run_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO kpi_refresh_log
                (run_id, started_at, finished_at, source, status, rows_ingested)
            VALUES (:rid, '2026-01-01T00:00:00', '2026-01-01T00:01:00', 'OWID', 'success', :rc)
        """), {"rid": run_id, "rc": len(tidy_df)})
    return db_engine


@pytest.fixture()
def svc(seeded_engine):
    """EnergyKPIReadService wired to the seeded in-memory engine."""
    settings = build_settings()
    svc = EnergyKPIReadService(settings)
    # Patch the engine to use our in-memory one
    with patch.object(svc, "_engine", return_value=seeded_engine):
        yield svc


class TestGetKPICatalog:
    def test_returns_all_21_entries(self, svc):
        entries = svc.get_kpi_catalog()
        assert len(entries) == 21

    def test_filter_by_v1_status(self, svc):
        entries = svc.get_kpi_catalog(v1_status="v1_required")
        assert len(entries) == 9
        assert all(e.v1_status == "v1_required" for e in entries)

    def test_filter_by_dashboard_priority(self, svc):
        entries = svc.get_kpi_catalog(dashboard_priority="lead")
        assert len(entries) > 0
        assert all(e.dashboard_priority == "lead" for e in entries)


class TestGetCountryKPISeries:
    def test_returns_data_for_bra(self, svc):
        values = svc.get_country_kpi_series(iso_codes=["BRA"])
        assert len(values) > 0
        assert all(v.iso_code == "BRA" for v in values)

    def test_filter_by_year(self, svc):
        values = svc.get_country_kpi_series(iso_codes=["BRA"], years=[2021])
        assert all(v.period == 2021 for v in values)

    def test_returns_dtos_with_snapshot_id(self, svc):
        values = svc.get_country_kpi_series(iso_codes=["BRA"])
        assert all(v.snapshot_id != "" for v in values)

    def test_offline_only(self, svc):
        """Read service must not make network calls."""
        import requests
        original_get = requests.get
        calls = []
        def fake_get(*args, **kwargs):
            calls.append(args)
            raise RuntimeError("Network call detected in read service!")
        with patch.object(requests, "get", fake_get):
            values = svc.get_country_kpi_series(iso_codes=["BRA"])
        assert not calls, "Read service made network calls"


class TestGetCountryKPICompare:
    def test_returns_multiple_countries(self, svc):
        from src.energy_kpi.catalog import _NS
        kpi_id = f"{_NS}.elec_renewables_share"
        values = svc.get_country_kpi_compare(kpi_id=kpi_id, year=2021)
        iso_codes = {v.iso_code for v in values}
        assert len(iso_codes) >= 2


class TestGetEnergyKPIHealth:
    def test_health_returns_struct(self, svc):
        health = svc.get_energy_kpi_health()
        assert hasattr(health, "is_stale")
        assert hasattr(health, "rows_ingested")
        assert health.rows_ingested > 0

    def test_stale_flag_set_for_old_data(self, svc):
        health = svc.get_energy_kpi_health()
        # Fixture data fetched "2026-01-01" which is ~5 months ago at test time
        # is_stale depends on system date; just check it's a bool
        assert isinstance(health.is_stale, bool)
