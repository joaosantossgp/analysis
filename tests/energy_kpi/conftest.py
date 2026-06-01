"""Shared fixtures for energy_kpi tests."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from src.energy_kpi.catalog import _ENERGY_CATALOG, _NS
from src.energy_kpi.ingest_owid import SnapshotRecord
from src.energy_kpi.schema import ensure_energy_kpi_tables_for_connection


# ── OWID CSV fixture ──────────────────────────────────────────────────────────

_OWID_COUNTRIES = [
    ("Brazil",         "BRA", 2020, 83.0, 16.0, 66.0,  2.0, 5.0,  0.0, 0.0, 0.0, 600.0, 580.0, 3000.0, 65.0, -1.0, -0.2, 78.0, 18.0,  48.0, 12.0),
    ("Brazil",         "BRA", 2021, 84.0, 15.0, 64.0,  3.0, 5.0,  0.0, 0.0, 0.0, 620.0, 600.0, 3100.0, 60.0, -1.0, -0.2, 79.0, 17.0,  49.0, 12.0),
    ("Brazil",         "BRA", 2022, 85.0, 14.0, 62.0,  4.0, 4.5,  0.0, 0.0, 0.0, 640.0, 620.0, 3200.0, 58.0, -1.0, -0.2, 80.0, 16.0,  51.0, 13.0),
    ("United States",  "USA", 2020, 21.0, 79.0,  6.0,  2.0,40.0, 24.0, 8.0, 2.0,4200.0,4100.0, 12600.0,400.0,  5.0,  0.1, 20.0, 78.0, None, None),
    ("United States",  "USA", 2021, 22.0, 78.0,  6.0,  2.0,39.0, 23.0, 9.0, 2.0,4300.0,4150.0, 12900.0,390.0,  5.0,  0.1, 21.0, 77.0, None, None),
    ("China",          "CHN", 2020, 28.0, 72.0,  5.0,  1.5,10.0, 50.0, 4.0, 5.0,7500.0,7400.0, 5300.0, 520.0,  3.0,  0.0, 15.0, 83.0, None, None),
]

_OWID_COLS = [
    "country", "iso_code", "year",
    "renewables_share_elec", "fossil_share_elec", "hydro_share_elec",
    "solar_share_elec", "gas_share_elec", "coal_share_elec",
    "wind_share_elec", "nuclear_share_elec",
    "electricity_generation", "electricity_demand",
    "electricity_demand_per_capita",
    "carbon_intensity_elec", "net_elec_imports", "net_elec_imports_share_demand",
    "renewables_share_energy", "fossil_share_energy",
    "low_carbon_share_elec", "greenhouse_gas_emissions",
]


def _build_owid_df() -> pd.DataFrame:
    return pd.DataFrame(_OWID_COUNTRIES, columns=_OWID_COLS)


@pytest.fixture()
def owid_csv_path(tmp_path: Path) -> Path:
    """Write a minimal OWID CSV to a temp file and return the path."""
    df = _build_owid_df()
    p = tmp_path / "owid-energy-data.csv"
    df.to_csv(p, index=False)
    return p


@pytest.fixture()
def snapshot(owid_csv_path: Path, tmp_path: Path) -> SnapshotRecord:
    snap_id = str(uuid.uuid4())
    codebook_path = tmp_path / "owid-energy-codebook.csv"
    codebook_path.write_text("column,description\nrename_share_elec,test\n")
    return SnapshotRecord(
        snapshot_id=snap_id,
        source="OWID",
        fetched_at="2026-01-01T00:00:00+00:00",
        csv_path=owid_csv_path,
        codebook_path=codebook_path,
        sha256="deadbeef",
        row_count=len(_OWID_COUNTRIES),
        source_version_label="2026-01-01",
    )


# ── In-memory SQLite engine ───────────────────────────────────────────────────

@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine with energy KPI tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        ensure_energy_kpi_tables_for_connection(conn)
    return engine


@pytest.fixture()
def db_conn(db_engine):
    """Return an open connection; closes after test."""
    with db_engine.begin() as conn:
        yield conn


# ── Tidy DataFrame with known data ───────────────────────────────────────────

@pytest.fixture()
def tidy_df(snapshot) -> pd.DataFrame:
    """Pre-normalized tidy DataFrame for 3 countries × required KPIs."""
    from src.energy_kpi.ingest_owid import normalize_owid
    from src.energy_kpi.ingest_owid import V1_ISO_CODES
    # Use the fixture snapshot (already has CSV written)
    return normalize_owid(snapshot, iso_filter=frozenset({"BRA", "USA", "CHN"}))
