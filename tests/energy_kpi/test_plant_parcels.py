"""Tests for plant and plant-parcel energy indicator paths."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from src.energy_kpi.metrics import (
    capacity_factor,
    hours_in_month,
    mwh_to_gwh,
    mwh_to_mwmed,
    mwh_to_twh,
    mwmed_to_mwh,
)
from src.energy_kpi.plant_parcel_ingest import (
    SOURCE_ANEEL_SIGA,
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
    PlantSnapshotRecord,
    parse_aneel_siga,
    parse_ccee_hourly,
    parse_ccee_monthly,
    seed_plant_sources,
    upsert_aneel_siga_plants,
    upsert_ccee_hourly,
    upsert_ccee_monthly,
)
from src.energy_kpi.read import EnergyKPIReadService
from src.settings import build_settings


def _snapshot(path: Path, source_id: str, provider: str, dataset: str) -> PlantSnapshotRecord:
    return PlantSnapshotRecord(
        snapshot_id=f"test-{source_id}",
        source_id=source_id,
        provider=provider,
        dataset_name=dataset,
        fetched_at="2026-06-01T00:00:00+00:00",
        file_path=path,
        sha256="deadbeef",
        row_count=1,
        source_url="https://example.test/source.csv",
        source_version_label=f"{dataset}:test",
    )


def _write_csv(path: Path, columns: list[str], rows: list[list[object]], sep: str = ";") -> Path:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, sep=sep)
    return path


def test_energy_metric_conversions_handle_units_and_leap_years():
    assert mwh_to_gwh(1_500) == pytest.approx(1.5)
    assert mwh_to_twh(1_500_000) == pytest.approx(1.5)
    assert hours_in_month(2024, 2) == 696
    assert mwmed_to_mwh(10, 696) == pytest.approx(6_960)
    assert mwh_to_mwmed(6_960, 696) == pytest.approx(10)
    assert capacity_factor(360, 10, 72) == pytest.approx(0.5)
    assert capacity_factor(360, 0, 72) is None
    assert capacity_factor(360, None, 72) is None


def test_parse_aneel_siga_and_missing_required_columns(tmp_path: Path):
    path = _write_csv(
        tmp_path / "siga.csv",
        [
            "DatGeracaoConjuntoDados",
            "CodCEG",
            "IdeNucleoCEG",
            "NomEmpreendimento",
            "SigUFPrincipal",
            "DscFaseUsina",
            "DscFonteCombustivel",
            "SigTipoGeracao",
            "DscTipoOutorga",
            "DatEntradaOperacao",
            "MdaPotenciaOutorgadaKw",
            "MdaPotenciaFiscalizadaKw",
            "MdaGarantiaFisicaKw",
        ],
        [[
            "01/06/2026",
            "CEG123",
            "NUC123",
            "Test Plant",
            "SP",
            "Operacao",
            "Hidraulica",
            "UHE",
            "Concessao",
            "01/01/2020",
            "10000,0",
            "9000,0",
            "8000,0",
        ]],
    )
    df = parse_aneel_siga(_snapshot(path, SOURCE_ANEEL_SIGA, "ANEEL", "siga-empreendimentos-geracao.csv"))
    assert df.iloc[0]["ceg"] == "CEG123"
    assert df.iloc[0]["authorized_capacity_kw"] == pytest.approx(10_000)

    bad_path = _write_csv(tmp_path / "bad.csv", ["only"], [["x"]])
    with pytest.raises(RuntimeError, match="missing required columns"):
        parse_aneel_siga(_snapshot(bad_path, SOURCE_ANEEL_SIGA, "ANEEL", "siga-empreendimentos-geracao.csv"))


def test_ccee_monthly_and_hourly_idempotent_upserts(tmp_path: Path, db_conn):
    monthly_path = _write_csv(
        tmp_path / "monthly.csv",
        [
            "MES_REFERENCIA",
            "COD_PARCELA_USINA",
            "SIGLA_PARCELA_USINA",
            "CEG",
            "NOME_EMPRESARIAL",
            "SUBMERCADO",
            "FONTE_ENERGIA_PRIMARIA",
            "ESTADO_UF",
            "CAP_T",
            "GARANTIA_FISICA",
            "GERACAO_CENTRO_GRAVIDADE",
        ],
        [["2026-02", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "40"]],
    )
    hourly_path = _write_csv(
        tmp_path / "hourly.csv",
        [
            "MES_REFERENCIA",
            "DATA",
            "PERIODO_COMERCIALIZACAO",
            "CODIGO_PARCELA_USINA",
            "SIGLA_USINA",
            "FONTE_PRIMARIA",
            "SUBMERCADO",
            "GERACAO_CENTRO_GRAVIDADE",
            "GERACAO_VERIFICADA_ONS",
            "DISPONIBILIDADE_VERIFICADA_UG",
        ],
        [["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8"]],
    )

    monthly = parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "CCEE", "PARCELA_USINA_MONTANTE_MENSAL"))
    hourly = parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA"))

    seed_plant_sources(db_conn)
    upsert_ccee_monthly(db_conn, monthly)
    upsert_ccee_monthly(db_conn, monthly)
    upsert_ccee_hourly(db_conn, hourly)
    upsert_ccee_hourly(db_conn, hourly)

    assert db_conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_monthly")).scalar() == 1
    assert db_conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcels")).scalar() == 1
    assert db_conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_hourly")).scalar() == 1


def test_plant_parcel_read_detail_is_offline_and_derives_metrics(tmp_path: Path, db_engine, monkeypatch):
    monthly_path = _write_csv(
        tmp_path / "monthly.csv",
        [
            "MES_REFERENCIA",
            "COD_PARCELA_USINA",
            "SIGLA_PARCELA_USINA",
            "CEG",
            "NOME_EMPRESARIAL",
            "SUBMERCADO",
            "FONTE_ENERGIA_PRIMARIA",
            "ESTADO_UF",
            "CAP_T",
            "GARANTIA_FISICA",
            "GERACAO_CENTRO_GRAVIDADE",
        ],
        [["2026-02", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "40"]],
    )
    aneel_path = _write_csv(
        tmp_path / "siga.csv",
        [
            "DatGeracaoConjuntoDados",
            "CodCEG",
            "NomEmpreendimento",
            "SigUFPrincipal",
            "DscFaseUsina",
            "DscFonteCombustivel",
            "MdaPotenciaOutorgadaKw",
            "MdaPotenciaFiscalizadaKw",
        ],
        [["01/06/2026", "CEG123", "Test Plant", "SP", "Operacao", "Hidraulica", "120000", "110000"]],
    )

    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_monthly(
            conn,
            parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "CCEE", "PARCELA_USINA_MONTANTE_MENSAL")),
        )
        upsert_aneel_siga_plants(
            conn,
            parse_aneel_siga(_snapshot(aneel_path, SOURCE_ANEEL_SIGA, "ANEEL", "siga-empreendimentos-geracao.csv")),
        )

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call")))

    catalog = svc.get_plant_parcel_catalog(search="1001")
    assert catalog["total"] == 1
    detail = svc.get_plant_parcel_detail(entity_id="1001", entity_type="ccee_plant_parcel")
    metric_ids = {m["metric_id"] for m in detail["metrics"]}
    assert "generation_center_of_gravity_gwh" in metric_ids
    assert "capacity_factor_pct" in metric_ids
    assert detail["metadata"]["caveats"]
