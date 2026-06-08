"""Tests for SIN subsystem KPI ingestion/read paths."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from src.energy_kpi.read import EnergyKPIReadService
from src.energy_kpi.sin_catalog import SIN_NS
from src.energy_kpi.sin_ingest import (
    SINSnapshotRecord,
    normalize_subsystem_code,
    parse_ccee_pld,
    parse_ons_balanco,
    parse_ons_cmo,
    parse_ons_ear,
    parse_ons_ena,
    seed_sin_kpi_catalog,
    seed_sin_kpi_sources,
    seed_subsystem_dimension,
    upsert_subsystem_kpi_values,
)
from src.platform.settings import build_settings


def _snapshot(path: Path, dataset: str, source: str = "ONS") -> SINSnapshotRecord:
    return SINSnapshotRecord(
        snapshot_id=f"test-{dataset}",
        source=source,
        source_dataset=dataset,
        fetched_at="2026-06-01T00:00:00+00:00",
        file_path=path,
        sha256="deadbeef",
        row_count=1,
        source_url="https://example.test/source.csv",
        source_version_label=f"{dataset}:2026",
    )


def _write_csv(path: Path, columns: list[str], rows: list[list[object]], sep: str = ";") -> Path:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, sep=sep)
    return path


def test_normalize_subsystem_code_variants():
    assert normalize_subsystem_code("SUL") == "S"
    assert normalize_subsystem_code("SE") == "SE_CO"
    assert normalize_subsystem_code("SE/CO") == "SE_CO"
    assert normalize_subsystem_code("Sudeste/Centro-Oeste") == "SE_CO"
    assert normalize_subsystem_code("NORDESTE") == "NE"
    assert normalize_subsystem_code("NORTE") == "N"
    assert normalize_subsystem_code("unknown") is None


def test_parse_ons_balanco_creates_generation_mix_and_load(tmp_path: Path):
    path = _write_csv(
        tmp_path / "balanco.csv",
        [
            "id_subsistema",
            "nom_subsistema",
            "din_instante",
            "val_gerhidraulica",
            "val_gertermica",
            "val_gereolica",
            "val_gersolar",
            "val_carga",
            "val_intercambio",
        ],
        [["NE", "NORDESTE", "2026-01-01 00:00:00", 100, 20, 30, 50, 250, 10]],
    )
    df = parse_ons_balanco(_snapshot(path, "balanco_energia_subsistema"))
    assert f"{SIN_NS}.load_mwmed" in set(df["kpi_id"])
    assert f"{SIN_NS}.mix_solar_pct" in set(df["kpi_id"])
    solar = df[df["kpi_id"] == f"{SIN_NS}.mix_solar_pct"].iloc[0]
    assert solar["subsystem_code"] == "NE"
    assert solar["normalized_value"] == pytest.approx(25.0)


def test_parse_ons_ear_ena_cmo(tmp_path: Path):
    ear_path = _write_csv(
        tmp_path / "ear.csv",
        ["id_subsistema", "nom_subsistema", "ear_data", "ear_max_subsistema", "ear_verif_subsistema_mwmes", "ear_verif_subsistema_percentual"],
        [["N", "NORTE", "2026-01-01", 1000, 500, 50]],
    )
    ena_path = _write_csv(
        tmp_path / "ena.csv",
        [
            "id_subsistema",
            "nom_subsistema",
            "ena_data",
            "ena_bruta_regiao_mwmed",
            "ena_bruta_regiao_percentualmlt",
            "ena_armazenavel_regiao_mwmed",
            "ena_armazenavel_regiao_percentualmlt",
        ],
        [["SE", "SUDESTE", "2026-01-01", 100, 80, 90, 70]],
    )
    cmo_path = _write_csv(
        tmp_path / "cmo.csv",
        ["id_subsistema", "nom_subsistema", "din_instante", "val_cmo"],
        [["S", "SUL", "2026-01-01 00:30:00", 123.45]],
    )

    ear = parse_ons_ear(_snapshot(ear_path, "ear_diario_subsistema"))
    ena = parse_ons_ena(_snapshot(ena_path, "ena_diario_subsistema"))
    cmo = parse_ons_cmo(_snapshot(cmo_path, "cmo_semihorario"))

    assert f"{SIN_NS}.ear_stored_pct" in set(ear["kpi_id"])
    assert f"{SIN_NS}.ena_gross_mwmed" in set(ena["kpi_id"])
    assert f"{SIN_NS}.cmo_brl_mwh" in set(cmo["kpi_id"])
    assert ena.iloc[0]["subsystem_code"] == "SE_CO"


def test_parse_ccee_pld_fixture(tmp_path: Path):
    path = _write_csv(
        tmp_path / "pld.csv",
        ["MES_REFERENCIA", "SUBMERCADO", "DIA", "HORA", "PLD_HORA"],
        [["2026-01", "SE/CO", 2, 1, "150,25"]],
    )
    df = parse_ccee_pld(_snapshot(path, "pld_horario", source="CCEE"))
    row = df.iloc[0]
    assert row["kpi_id"] == f"{SIN_NS}.pld_brl_mwh"
    assert row["subsystem_code"] == "SE_CO"
    assert row["reference_datetime"] == "2026-01-02T00:00:00"
    assert row["normalized_value"] == pytest.approx(150.25)


def test_seed_catalog_and_idempotent_upsert(tmp_path: Path, db_conn):
    path = _write_csv(
        tmp_path / "cmo.csv",
        ["id_subsistema", "nom_subsistema", "din_instante", "val_cmo"],
        [["S", "SUL", "2026-01-01 00:30:00", 123.45]],
    )
    df = parse_ons_cmo(_snapshot(path, "cmo_semihorario"))
    seed_sin_kpi_sources(db_conn)
    seed_subsystem_dimension(db_conn)
    seed_sin_kpi_catalog(db_conn)
    count = db_conn.execute(
        text("SELECT COUNT(*) FROM kpi_catalog WHERE kpi_id LIKE 'energy_utilities.sin.%'")
    ).scalar()
    assert count >= 10

    upsert_subsystem_kpi_values(db_conn, df)
    upsert_subsystem_kpi_values(db_conn, df)
    row_count = db_conn.execute(text("SELECT COUNT(*) FROM subsystem_kpi_values")).scalar()
    assert row_count == len(df)


def test_sin_read_path_is_offline(tmp_path: Path, db_engine, monkeypatch):
    path = _write_csv(
        tmp_path / "cmo.csv",
        ["id_subsistema", "nom_subsistema", "din_instante", "val_cmo"],
        [["S", "SUL", "2026-01-01 00:30:00", 123.45]],
    )
    df = parse_ons_cmo(_snapshot(path, "cmo_semihorario"))
    with db_engine.begin() as conn:
        seed_sin_kpi_sources(conn)
        seed_subsystem_dimension(conn)
        seed_sin_kpi_catalog(conn)
        upsert_subsystem_kpi_values(conn, df)

    settings = build_settings()
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    def fail_network(*args, **kwargs):
        raise AssertionError("network call on read path")

    monkeypatch.setattr("requests.get", fail_network)
    dashboard = svc.get_sin_kpi_dashboard()
    assert dashboard.observations
    assert dashboard.source_statuses


def test_sin_refresh_partial_when_ccee_fails(tmp_path: Path, monkeypatch):
    from src.energy_kpi import sin_refresh
    from src.energy_kpi.sin_refresh import SINKPIRefreshJob

    settings = build_settings(project_root=tmp_path)

    def fake_fetch_ons(paths, dataset, year, timeout=120):
        csv_path = tmp_path / f"{dataset}-{year}.csv"
        csv_path.write_text("placeholder\n", encoding="utf-8")
        return _snapshot(csv_path, dataset)

    def fake_parser(snapshot):
        return pd.DataFrame([
            {
                "kpi_id": f"{SIN_NS}.load_mwmed",
                "subsystem_code": "S",
                "reference_datetime": "2026-01-01T00:00:00",
                "source_value": 100.0,
                "normalized_value": 100.0,
                "unit": "MWmed",
                "source": "ONS",
                "source_dataset": snapshot.source_dataset,
                "source_field": "fixture",
                "source_hash": f"hash-{snapshot.source_dataset}",
                "snapshot_id": snapshot.snapshot_id,
                "ingestion_batch_id": snapshot.snapshot_id,
                "data_quality_status": "ok",
            }
        ])

    monkeypatch.setattr(sin_refresh, "fetch_ons_snapshot", fake_fetch_ons)
    monkeypatch.setattr(sin_refresh, "fetch_ccee_pld_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("403 Forbidden")))
    monkeypatch.setitem(sin_refresh._PARSERS, "balanco_energia_subsistema", fake_parser)
    monkeypatch.setitem(sin_refresh._PARSERS, "ear_diario_subsistema", fake_parser)
    monkeypatch.setitem(sin_refresh._PARSERS, "ena_diario_subsistema", fake_parser)
    monkeypatch.setitem(sin_refresh._PARSERS, "cmo_semihorario", fake_parser)

    result = SINKPIRefreshJob(settings).run(years=[2026], include_ccee=True)
    assert result["status"] == "partial"
    assert result["rows_inserted"] > 0
    assert "pld_horario" in (result["error"] or "")
