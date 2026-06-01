"""Tests for src/energy_kpi/excel.py — 4-tab workbook verification."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.energy_kpi.excel import export_country_kpis
from src.energy_kpi.ingest_owid import (
    persist_snapshot_record,
    seed_country_dimension,
    seed_kpi_catalog,
    seed_kpi_sources,
    upsert_country_kpi_values,
)
from src.energy_kpi.merge import merge_sources, set_data_quality_status
from src.energy_kpi.read import EnergyKPIReadService
from src.settings import build_settings


@pytest.fixture()
def seeded_engine(db_engine, snapshot, tidy_df):
    merged = merge_sources(tidy_df)
    merged = set_data_quality_status(merged, owid_fetched_at="2026-01-01T00:00:00+00:00")
    with db_engine.begin() as conn:
        seed_kpi_sources(conn)
        seed_country_dimension(conn)
        seed_kpi_catalog(conn)
        persist_snapshot_record(conn, snapshot)
        upsert_country_kpi_values(conn, merged)
    return db_engine


def test_workbook_has_4_tabs(tmp_path, seeded_engine):
    """Export writes exactly 4 sheets."""
    import xlsxwriter
    settings = build_settings()
    settings = type(settings)(
        paths=type(settings.paths)(
            **{
                **{f.name: getattr(settings.paths, f.name)
                   for f in settings.paths.__dataclass_fields__.values()},
                "reports_dir": tmp_path,
            }
        ),
        **{f: getattr(settings, f) for f in settings.__dataclass_fields__ if f != "paths"},
    )

    svc = EnergyKPIReadService(settings)
    with patch.object(svc, "_engine", return_value=seeded_engine), \
         patch("src.energy_kpi.excel.EnergyKPIReadService", return_value=svc), \
         patch("src.energy_kpi.excel.get_energy_kpi_engine", return_value=seeded_engine):
        out_path = export_country_kpis(settings)

    import openpyxl
    wb = openpyxl.load_workbook(out_path)
    sheet_names = wb.sheetnames
    assert len(sheet_names) == 4
    assert "KPI Catalog" in sheet_names
    assert "Country KPIs" in sheet_names
    assert "Source Metadata" in sheet_names
    assert "Data Quality" in sheet_names


def test_catalog_tab_has_header_row(tmp_path, seeded_engine):
    """KPI Catalog sheet has correct header in row 1."""
    import xlsxwriter
    from src.energy_kpi.excel import _write_catalog_tab
    settings = build_settings()
    svc = EnergyKPIReadService(settings)

    with patch.object(svc, "_engine", return_value=seeded_engine):
        wb_path = tmp_path / "test_catalog.xlsx"
        with xlsxwriter.Workbook(str(wb_path)) as wb:
            _write_catalog_tab(wb, svc)

    import openpyxl
    wb = openpyxl.load_workbook(wb_path)
    ws = wb.active
    header = [ws.cell(1, c + 1).value for c in range(4)]
    assert "KPI ID" in header
    assert "Display Name" in header


def test_country_kpis_tab_has_data(tmp_path, seeded_engine, tidy_df, snapshot):
    """Country KPIs sheet contains data rows."""
    from src.energy_kpi.excel import _write_time_series_tab
    import xlsxwriter
    settings = build_settings()
    svc = EnergyKPIReadService(settings)
    with patch.object(svc, "_engine", return_value=seeded_engine):
        wb_path = tmp_path / "test_ts.xlsx"
        with xlsxwriter.Workbook(str(wb_path)) as wb:
            _write_time_series_tab(wb, svc)

    import openpyxl
    wb_r = openpyxl.load_workbook(wb_path)
    ws = wb_r.active
    # Check header row
    assert ws.cell(1, 1).value == "KPI ID"
    # Check at least one data row
    assert ws.cell(2, 1).value is not None


def test_snapshot_id_in_every_value_row(seeded_engine, tidy_df):
    """Every value in country_kpi_values has a non-null snapshot_id."""
    from sqlalchemy import text
    with seeded_engine.connect() as conn:
        null_snaps = conn.execute(
            text("SELECT COUNT(*) FROM country_kpi_values WHERE snapshot_id IS NULL OR snapshot_id=''")
        ).scalar()
    assert null_snaps == 0
