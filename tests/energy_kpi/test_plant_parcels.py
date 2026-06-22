"""Tests for plant and plant-parcel energy indicator paths."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, text

from scripts.diagnostics.phase5_hot_cold_hourly_prototype import build_hot_cold_prototype
from src.energy_kpi.metrics import (
    capacity_factor,
    hours_in_month,
    mwh_to_gwh,
    mwh_to_mwmed,
    mwh_to_twh,
    mwmed_to_mwh,
)
from src.energy_kpi.plant_marts import rebuild_plant_hourly_marts
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
from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob
from src.energy_kpi.read import EnergyKPIReadService
from src.energy_kpi.schema import (
    _build_energy_kpi_engine,
    ensure_energy_kpi_tables_for_connection,
    get_energy_kpi_engine,
)
from src.platform.settings import build_settings


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


def _write_csv_encoded(
    path: Path,
    columns: list[str],
    rows: list[list[object]],
    *,
    sep: str = ";",
    encoding: str,
) -> Path:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, sep=sep, encoding=encoding)
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


def test_parse_aneel_siga_accepts_cp1252_source(tmp_path: Path):
    path = _write_csv_encoded(
        tmp_path / "siga_cp1252.csv",
        [
            "DatGeracaoConjuntoDados",
            "CodCEG",
            "NomEmpreendimento",
            "SigUFPrincipal",
            "DscFaseUsina",
            "DscFonteCombustivel",
            "MdaPotenciaOutorgadaKw",
        ],
        [["2026-06-02", "CEG-JUPIA", "Jupiá", "SP", "Operação", "Hidráulica", "1000,0"]],
        encoding="cp1252",
    )

    df = parse_aneel_siga(_snapshot(path, SOURCE_ANEEL_SIGA, "ANEEL", "siga-empreendimentos-geracao.csv"))

    assert df.iloc[0]["plant_name"] == "Jupiá"
    assert df.iloc[0]["source_updated_at"] == "2026-06-02"
    assert df.attrs["detected_encoding"] == "cp1252"


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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"]],
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


def test_plant_daily_chart_uses_rebuilt_mart_not_raw_hourly_scan(tmp_path: Path, db_engine, monkeypatch):
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [
            ["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"],
            ["202602", "02/02/2026", 2, "1001", "PLT1", "Hidraulica", "SE/CO", "12", "11", "7", "1"],
        ],
    )

    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_monthly(
            conn,
            parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "CCEE", "PARCELA_USINA_MONTANTE_MENSAL")),
        )
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA")),
        )
        mart_result = rebuild_plant_hourly_marts(conn, reference_months=["2026-02"])

    assert mart_result["daily_rows"] == 1
    assert mart_result["preview_rows"] == 2
    assert mart_result["source_submarket_rows"] == 1
    with db_engine.connect() as conn:
        summary = conn.execute(text("""
            SELECT reference_month, generation_source, submarket,
                   plant_parcel_count, hourly_observations, generation_mwh,
                   verified_generation_mwh
            FROM plant_parcel_source_submarket_monthly_mart
        """)).mappings().one()
    assert summary["reference_month"] == "2026-02"
    assert summary["generation_source"] == "Hidraulica"
    assert summary["submarket"] == "SE/CO"
    assert summary["plant_parcel_count"] == 1
    assert summary["hourly_observations"] == 2
    assert summary["generation_mwh"] == pytest.approx(22.0)
    assert summary["verified_generation_mwh"] == pytest.approx(20.0)

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(str(statement).split()))

    event.listen(db_engine, "before_cursor_execute", capture_statement)
    try:
        chart = svc.get_plant_parcel_chart_data(
            entity_id="1001",
            entity_type="ccee_plant_parcel",
            frequency="daily",
            year_month="2026-02",
        )
    finally:
        event.remove(db_engine, "before_cursor_execute", capture_statement)

    assert chart.get("error") is None
    assert chart["metadata"]["data_source"] == "plant_parcel_daily_generation_mart"
    assert chart["periods"] == ["2026-02-02"]
    series = {row["id"]: row for row in chart["series"]}
    assert series["generation_mwh"]["points"] == [pytest.approx(22.0)]
    assert any("FROM plant_parcel_daily_generation_mart" in stmt for stmt in statements)
    assert not any("FROM ccee_plant_parcel_hourly" in stmt for stmt in statements)


def test_hourly_chart_requires_explicit_bounded_window(db_engine, monkeypatch):
    settings = build_settings()
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    result = svc.get_plant_parcel_chart_data(
        entity_id="1001",
        entity_type="ccee_plant_parcel",
        frequency="hourly",
        year_month="2026-02",
    )

    assert "requires explicit start_datetime and end_datetime" in result["error"]


def test_energy_mart_status_uses_fast_hourly_estimate(tmp_path: Path, db_engine, monkeypatch):
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [
            ["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"],
            ["202602", "02/02/2026", 2, "1001", "PLT1", "Hidraulica", "SE/CO", "12", "11", "7", "1"],
        ],
    )
    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA")),
        )
        rebuild_plant_hourly_marts(conn, reference_months=["2026-02"])

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(str(statement).split()))

    event.listen(db_engine, "before_cursor_execute", capture_statement)
    try:
        status = svc.get_energy_mart_status()
    finally:
        event.remove(db_engine, "before_cursor_execute", capture_statement)

    assert status["source"]["count_method"] == "MAX(rowid)"
    assert status["source"]["latest_reference_month"] == "2026-02"
    daily = status["marts"]["plant_parcel_daily_generation_mart"]
    assert daily["row_count_current"] == 1
    assert daily["source_observations_current"] == 2
    assert daily["is_current_for_latest_source_month"] is True
    source_submarket = status["marts"]["plant_parcel_source_submarket_monthly_mart"]
    assert source_submarket["row_count_current"] == 1
    assert source_submarket["generation_source_count_current"] == 1
    assert source_submarket["submarket_count_current"] == 1
    assert source_submarket["source_observations_current"] == 2
    assert not any("COUNT(*) FROM ccee_plant_parcel_hourly" in stmt for stmt in statements)


def test_source_submarket_summary_reads_mart_not_hourly(tmp_path: Path, db_engine, monkeypatch):
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [
            ["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"],
            ["202602", "02/02/2026", 2, "1001", "PLT1", "Hidraulica", "SE/CO", "12", "11", "7", "1"],
            ["202602", "02/02/2026", 1, "1002", "PLT2", "Eólica", "NORDESTE", "20", "18", "9", "0"],
        ],
    )
    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA")),
        )
        rebuild_plant_hourly_marts(
            conn,
            reference_months=["2026-02"],
            rebuild_daily=False,
            rebuild_preview=False,
            rebuild_source_submarket=True,
        )

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(str(statement).split()))

    event.listen(db_engine, "before_cursor_execute", capture_statement)
    try:
        summary = svc.get_plant_parcel_source_submarket_summary(reference_month="2026-02")
    finally:
        event.remove(db_engine, "before_cursor_execute", capture_statement)

    assert summary["data_source"] == "plant_parcel_source_submarket_monthly_mart"
    assert summary["total"] == 2
    assert summary["coverage"]["source_observations"] == 3
    by_group = {(row["generation_source"], row["submarket"]): row for row in summary["records"]}
    assert by_group[("Hidraulica", "SE/CO")]["hourly_observations"] == 2
    assert by_group[("Hidraulica", "SE/CO")]["plant_parcel_count"] == 1
    assert by_group[("Eólica", "NORDESTE")]["hourly_observations"] == 1
    assert any("FROM plant_parcel_source_submarket_monthly_mart" in stmt for stmt in statements)
    assert not any("FROM ccee_plant_parcel_hourly" in stmt for stmt in statements)


def test_plant_catalog_search_is_accent_insensitive(tmp_path: Path, db_engine, monkeypatch):
    aneel_path = _write_csv_encoded(
        tmp_path / "siga.csv",
        [
            "DatGeracaoConjuntoDados",
            "CodCEG",
            "NomEmpreendimento",
            "SigUFPrincipal",
            "DscFaseUsina",
            "DscFonteCombustivel",
            "MdaPotenciaOutorgadaKw",
        ],
        [["02/06/2026", "CEG-JUPIA", "Jupiá", "SP", "Operação", "Hidráulica", "1000,0"]],
        encoding="cp1252",
    )
    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_aneel_siga_plants(
            conn,
            parse_aneel_siga(_snapshot(aneel_path, SOURCE_ANEEL_SIGA, "ANEEL", "siga-empreendimentos-geracao.csv")),
        )

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    catalog = svc.get_plant_parcel_catalog(search="jupia")

    assert catalog["total"] == 1
    assert catalog["records"][0]["plant_name"] == "Jupiá"


def test_source_status_reports_never_refreshed_and_warning(tmp_path: Path, db_engine, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    initial = svc.get_plant_parcel_source_statuses()
    by_source = {row["source_id"]: row for row in initial["source_statuses"]}
    assert by_source[SOURCE_ANEEL_SIGA]["cache_status"] == "never_refreshed"

    with db_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO energy_source_refresh_log
                    (refresh_id, source_id, requested_by, started_at, finished_at,
                     status, rows_downloaded, rows_inserted, source_rows, parsed_rows,
                     normalized_rows, rows_skipped, warning_message)
                VALUES
                    ('warn-1', :source_id, 'test', '2026-06-01T00:00:00+00:00',
                     '2026-06-01T00:00:01+00:00', 'warning', 10, 0, 10, 0, 0, 10,
                     'Downloaded rows but no rows matched parser requirements.')
            """),
            {"source_id": SOURCE_ANEEL_SIGA},
        )

    warned = svc.get_plant_parcel_source_statuses()
    by_source = {row["source_id"]: row for row in warned["source_statuses"]}
    assert by_source[SOURCE_ANEEL_SIGA]["cache_status"] == "warning"
    assert by_source[SOURCE_ANEEL_SIGA]["last_warning"].startswith("Downloaded rows")


def test_source_status_is_read_only_during_sqlite_write_lock(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "energy_kpis.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 0.1},
    )
    with engine.begin() as conn:
        ensure_energy_kpi_tables_for_connection(conn)

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: engine)

    writer = sqlite3.connect(str(db_path), timeout=0.1)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")
    try:
        status = svc.get_plant_parcel_source_statuses()
    finally:
        writer.rollback()
        writer.close()

    by_source = {row["source_id"]: row for row in status["source_statuses"]}
    assert status["count"] == 3
    assert by_source[SOURCE_ANEEL_SIGA]["cache_status"] == "never_refreshed"
    assert by_source[SOURCE_CCEE_MONTHLY]["source_name"] == "CCEE Plant Parcel Monthly"
    with engine.connect() as conn:
        assert int(conn.execute(text("SELECT COUNT(*) FROM energy_sources")).scalar() or 0) == 0


def test_source_status_uses_fast_hourly_cache_presence(db_engine, monkeypatch):
    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        conn.execute(text("""
            INSERT INTO ccee_plant_parcel_hourly
                (reference_datetime, reference_month, commercialization_period, plant_parcel_code,
                 plant_acronym, generation_source, submarket, source_dataset, raw_payload_hash)
            VALUES
                ('2026-04-30T23:00:00', '2026-04', 1, '1001',
                 'PLT1', 'Hidraulica', 'SE/CO', 'GERACAO_HORARIA_USINA', 'hash-hourly')
        """))
        conn.execute(text("""
            INSERT INTO energy_source_refresh_log
                (refresh_id, source_id, requested_by, started_at, finished_at,
                 status, rows_inserted, source_rows, parsed_rows, normalized_rows)
            VALUES
                ('hourly-fast-1', :source_id, 'test', '2026-06-01T00:00:00+00:00',
                 '2026-06-01T00:00:01+00:00', 'success', 1, 1, 1, 1)
        """), {"source_id": SOURCE_CCEE_HOURLY})

    statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(str(statement).split()))

    event.listen(db_engine, "before_cursor_execute", capture_statement)
    try:
        settings = build_settings()
        svc = EnergyKPIReadService(settings)
        monkeypatch.setattr(svc, "_engine", lambda: db_engine)

        status = svc.get_plant_parcel_source_statuses(source_ids=[SOURCE_CCEE_HOURLY])
    finally:
        event.remove(db_engine, "before_cursor_execute", capture_statement)

    hourly = status["source_statuses"][0]
    assert hourly["source_id"] == SOURCE_CCEE_HOURLY
    assert hourly["local_records_count"] == 1
    assert hourly["latest_reference"] == "2026-04-30T23:00:00"
    assert not any("COUNT(*) FROM ccee_plant_parcel_hourly" in stmt for stmt in statements)


def test_energy_kpi_engine_first_access_tolerates_locked_pragma_setup(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    db_path = settings.paths.energy_kpi_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    seed_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    with seed_engine.begin() as conn:
        ensure_energy_kpi_tables_for_connection(conn)
    seed_engine.dispose()
    with sqlite3.connect(str(db_path), timeout=1.0) as conn:
        conn.execute("PRAGMA journal_mode = DELETE")

    _build_energy_kpi_engine.cache_clear()
    writer = sqlite3.connect(str(db_path), timeout=0.1, check_same_thread=False)
    writer.execute("BEGIN EXCLUSIVE")

    def release_lock() -> None:
        time.sleep(0.4)
        writer.rollback()
        writer.close()

    releaser = threading.Thread(target=release_lock)
    releaser.start()
    engine = None
    try:
        engine = get_energy_kpi_engine(settings)
        with engine.connect() as conn:
            assert int(conn.execute(text("SELECT COUNT(*) FROM kpi_catalog")).scalar() or 0) == 0
    finally:
        releaser.join(timeout=2)
        if engine is not None:
            engine.dispose()
        _build_energy_kpi_engine.cache_clear()


def test_source_status_can_be_limited_to_ccee_sources(db_engine, monkeypatch):
    with db_engine.begin() as conn:
        seed_plant_sources(conn)
    settings = build_settings()
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    status = svc.get_plant_parcel_source_statuses(
        source_ids=[SOURCE_CCEE_MONTHLY, SOURCE_CCEE_HOURLY],
    )

    assert status["count"] == 2
    assert [row["source_id"] for row in status["source_statuses"]] == [
        SOURCE_CCEE_MONTHLY,
        SOURCE_CCEE_HOURLY,
    ]


def test_refresh_job_marks_zero_insert_as_warning(tmp_path: Path, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    path = _write_csv(tmp_path / "empty.csv", ["CodCEG", "NomEmpreendimento"], [])
    snapshot = PlantSnapshotRecord(
        snapshot_id="empty-aneel",
        source_id=SOURCE_ANEEL_SIGA,
        provider="ANEEL",
        dataset_name="siga-empreendimentos-geracao.csv",
        fetched_at="2026-06-01T00:00:00+00:00",
        file_path=path,
        sha256="deadbeef",
        row_count=0,
        source_url="https://example.test/source.csv",
        source_version_label="SIGA:test",
    )
    empty_frame = pd.DataFrame(columns=[
        "ceg",
        "plant_name",
        "ceg_core",
        "generation_type",
        "generation_source",
        "uf",
        "phase",
        "operation_start_date",
        "grant_type",
        "authorized_capacity_kw",
        "inspected_capacity_kw",
        "physical_guarantee_kw",
        "agent_name",
        "ownership_description",
        "source_updated_at",
        "raw_payload_hash",
        "snapshot_id",
    ])
    empty_frame.attrs["source_row_count"] = 0
    empty_frame.attrs["parsed_rows"] = 0
    empty_frame.attrs["normalized_rows"] = 0
    empty_frame.attrs["detected_encoding"] = "utf-8-sig"

    monkeypatch.setattr("src.energy_kpi.plant_parcel_refresh.fetch_aneel_siga_snapshot", lambda *_, **__: snapshot)
    monkeypatch.setattr("src.energy_kpi.plant_parcel_refresh.parse_aneel_siga", lambda *_: empty_frame)

    result = PlantParcelRefreshJob(settings).run(source_id=SOURCE_ANEEL_SIGA, triggered_by="test")

    assert result["status"] == "warning"
    assert result["rows_inserted"] == 0
    assert "contained no rows" in result["warning"]


def test_manual_ccee_monthly_import_logs_metadata_and_keeps_cache_after_auto_failure(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    monthly_path = _write_csv(
        tmp_path / "parcela_usina_montante_mensal_2026.csv",
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
        [
            ["2026-01", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "40"],
            ["2026-02", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "45"],
        ],
    )

    first = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_MONTHLY,
        file_path=monthly_path,
        triggered_by="test",
        expected_period="2026",
    )
    second = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_MONTHLY,
        file_path=monthly_path,
        triggered_by="test",
        expected_period="2026",
    )

    assert first["status"] == "success"
    assert first["import_mode"] == "manual_file"
    assert first["rows_inserted"] == 2
    assert first["file_hash"]
    assert first["detected_period"] == "2026-01..2026-02"
    assert second["status"] == "success"

    engine = get_energy_kpi_engine(settings)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_monthly")).scalar() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcels")).scalar() == 1
        manual_log = conn.execute(
            text("""
                SELECT import_mode, original_file_name, file_hash, detected_period, source_page_url
                FROM energy_source_refresh_log
                WHERE refresh_id = :refresh_id
            """),
            {"refresh_id": first["refresh_id"]},
        ).mappings().one()
        assert manual_log["import_mode"] == "manual_file"
        assert manual_log["original_file_name"] == monthly_path.name
        assert manual_log["file_hash"] == first["file_hash"]
        assert manual_log["detected_period"] == "2026-01..2026-02"
        assert manual_log["source_page_url"] == "https://dadosabertos.ccee.org.br/dataset/parcela_usina_montante_mensal"
        conn.execute(
            text("""
                INSERT INTO energy_source_refresh_log
                    (refresh_id, source_id, requested_by, started_at, finished_at, status,
                     error_message, rows_inserted, import_mode)
                VALUES
                    ('auto-failed-after-manual', :source_id, 'test',
                     '2999-01-01T00:00:00+00:00', '2999-01-01T00:00:01+00:00',
                     'failed', '403 Forbidden', 0, 'automatic_refresh')
            """),
            {"source_id": SOURCE_CCEE_MONTHLY},
        )

    status = EnergyKPIReadService(settings).get_plant_parcel_source_statuses()
    by_source = {row["source_id"]: row for row in status["source_statuses"]}
    ccee_monthly = by_source[SOURCE_CCEE_MONTHLY]
    assert ccee_monthly["cache_status"] == "cached"
    assert ccee_monthly["last_status"] == "failed"
    assert ccee_monthly["last_manual_file_name"] == monthly_path.name
    assert ccee_monthly["last_manual_file_hash"] == first["file_hash"]


def test_manual_ccee_hourly_import_accepts_gzip_and_rejects_period_mismatch(tmp_path: Path, monkeypatch):
    settings = build_settings(project_root=tmp_path)
    hourly_path = _write_csv(
        tmp_path / "geracao_horaria_usina_202602.csv.gz",
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"]],
    )

    result = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_HOURLY,
        file_path=hourly_path,
        triggered_by="test",
        expected_period="2026-02",
    )
    mismatch = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_HOURLY,
        file_path=hourly_path,
        triggered_by="test",
        expected_period="2026-03",
    )

    assert result["status"] == "success"
    assert result["rows_inserted"] == 1
    assert result["file_type"] == "gzip"
    assert result["detected_period"] == "2026-02"
    assert mismatch["status"] == "failed"
    assert "does not match the selected CCEE hourly month" in str(mismatch["error"])

    monkeypatch.setattr(
        "src.energy_kpi.plant_parcel_refresh.upsert_ccee_hourly",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("duplicate import should skip upsert")),
    )
    duplicate = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_HOURLY,
        file_path=hourly_path,
        triggered_by="test",
        expected_period="2026-02",
    )
    assert duplicate["status"] == "success"
    assert duplicate["rows_inserted"] == 1

    engine = get_energy_kpi_engine(settings)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ccee_plant_parcel_hourly")).scalar() == 1


def test_manual_ccee_import_rejects_invalid_extension_and_missing_columns(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    txt_path = tmp_path / "parcela_usina_montante_mensal_2026.txt"
    txt_path.write_text("MES_REFERENCIA;COD_PARCELA_USINA\n2026-01;1001\n", encoding="utf-8")
    bad_csv = _write_csv(tmp_path / "parcela_usina_montante_mensal_2026.csv", ["only"], [["x"]])

    invalid_extension = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_MONTHLY,
        file_path=txt_path,
        triggered_by="test",
        expected_period="2026",
    )
    missing_columns = PlantParcelRefreshJob(settings).run_manual_file_import(
        source_id=SOURCE_CCEE_MONTHLY,
        file_path=bad_csv,
        triggered_by="test",
        expected_period="2026",
    )

    assert invalid_extension["status"] == "failed"
    assert "accepts annual .csv files" in str(invalid_extension["error"])
    assert missing_columns["status"] == "failed"
    assert "missing required columns" in str(missing_columns["error"])


def test_manual_import_retries_transient_sqlite_write_lock(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    engine = get_energy_kpi_engine(settings)
    with engine.begin() as conn:
        seed_plant_sources(conn)

    hourly_path = _write_csv(
        tmp_path / "geracao_horaria_usina_202607.csv",
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [["202607", "01/07/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"]],
    )

    writer = sqlite3.connect(str(settings.paths.energy_kpi_db_path), timeout=0.1, check_same_thread=False)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute("BEGIN IMMEDIATE")

    def release_lock() -> None:
        time.sleep(0.3)
        writer.rollback()
        writer.close()

    releaser = threading.Thread(target=release_lock)
    releaser.start()
    try:
        result = PlantParcelRefreshJob(settings).run_manual_file_import(
            source_id=SOURCE_CCEE_HOURLY,
            file_path=hourly_path,
            triggered_by="test",
            original_file_name=hourly_path.name,
        )
    finally:
        releaser.join(timeout=2)

    assert result["status"] == "success"
    assert result["rows_inserted"] == 1


def test_get_plant_parcel_chart_data(tmp_path: Path, db_engine, monkeypatch):
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
        [
            ["2026-01", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "40"],
            ["2026-02", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "45"],
        ],
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [
            ["202602", "01/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"],
            ["202602", "01/02/2026", 2, "1001", "PLT1", "Hidraulica", "SE/CO", "12", "10", "9", "0"],
        ],
    )

    with db_engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_monthly(
            conn,
            parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "CCEE", "PARCELA_USINA_MONTANTE_MENSAL")),
        )
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA")),
        )
        rebuild_plant_hourly_marts(conn, reference_months=["2026-02"])

    settings = build_settings(project_root=tmp_path)
    svc = EnergyKPIReadService(settings)
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    # 1. Test monthly chart
    monthly_chart = svc.get_plant_parcel_chart_data(entity_id="1001", entity_type="ccee_plant_parcel", frequency="monthly")
    assert monthly_chart["frequency"] == "monthly"
    assert "2026-01" in monthly_chart["periods"]
    assert "2026-02" in monthly_chart["periods"]
    assert len(monthly_chart["series"]) == 5
    
    # 2. Test daily chart
    daily_chart = svc.get_plant_parcel_chart_data(
        entity_id="1001",
        entity_type="ccee_plant_parcel",
        frequency="daily",
        year_month="2026-02"
    )
    assert daily_chart["frequency"] == "daily"
    assert "2026-02-01" in daily_chart["periods"]
    
    # 3. Test hourly chart
    hourly_chart = svc.get_plant_parcel_chart_data(
        entity_id="1001",
        entity_type="ccee_plant_parcel",
        frequency="hourly",
        year_month="2026-02",
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )
    assert hourly_chart["frequency"] == "hourly"
    assert len(hourly_chart["periods"]) == 2


def _seed_file_backed_hourly_chart_fixture(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    engine = get_energy_kpi_engine(settings)
    monthly_path = _write_csv(
        tmp_path / "monthly_for_adapter.csv",
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
        [
            ["2026-01", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "40"],
            ["2026-02", "1001", "PLT1", "CEG123", "Utility SA", "SE/CO", "Hidraulica", "SP", "100", "50", "45"],
        ],
    )
    hourly_path = _write_csv(
        tmp_path / "hourly_for_adapter.csv",
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
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
        [
            ["202601", "01/01/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "5", "4", "3", "0"],
            ["202602", "01/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "0"],
            ["202602", "01/02/2026", 2, "1001", "PLT1", "Hidraulica", "SE/CO", "12", "10", "9", "0"],
        ],
    )

    with engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_monthly(
            conn,
            parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "CCEE", "PARCELA_USINA_MONTANTE_MENSAL")),
        )
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(hourly_path, SOURCE_CCEE_HOURLY, "CCEE", "GERACAO_HORARIA_USINA")),
        )
        rebuild_plant_hourly_marts(conn, reference_months=["2026-01", "2026-02"])

    build_hot_cold_prototype(
        database=settings.paths.energy_kpi_db_path,
        output_dir=tmp_path / "hourly_hot_cold",
        hot_months=1,
        cold_months=["2026-01"],
        full_months=True,
        chunk_size=2,
    )
    return settings, tmp_path / "hourly_hot_cold" / "manifest.json"


def test_hourly_chart_routes_ceg_to_hot_cold_adapter_when_manifest_valid(tmp_path: Path, monkeypatch):
    settings, manifest_path = _seed_file_backed_hourly_chart_fixture(tmp_path)
    monkeypatch.setenv("CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST", str(manifest_path))

    svc = EnergyKPIReadService(settings)
    hot_chart = svc.get_plant_parcel_chart_data(
        entity_id="CEG123",
        entity_type="aneel_plant",
        frequency="hourly",
        year_month="2026-02",
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )
    hot_metadata = hot_chart["metadata"]["hourly_read_path"]

    assert hot_chart["metadata"]["data_source"] == "hot_sqlite"
    assert hot_metadata["attempted"] is True
    assert hot_metadata["selected"] == "hot_sqlite"
    assert hot_metadata["fallback_reason"] is None
    assert hot_chart["periods"] == ["00h", "01h"]
    assert hot_chart["series"][0]["points"] == [10.0, 12.0]

    cold_chart = svc.get_plant_parcel_chart_data(
        entity_id="CEG123",
        entity_type="aneel_plant",
        frequency="hourly",
        year_month="2026-01",
        start_datetime="2026-01-01T00:00:00",
        end_datetime="2026-01-01T23:59:59",
    )
    cold_metadata = cold_chart["metadata"]["hourly_read_path"]

    assert cold_chart["metadata"]["data_source"] == "cold_parquet"
    assert cold_metadata["attempted"] is True
    assert cold_metadata["selected"] == "cold_parquet"
    assert cold_metadata["fallback_reason"] is None
    assert cold_chart["periods"] == ["00h"]
    assert cold_chart["series"][0]["points"] == [5.0]


def test_hourly_chart_keeps_parcel_on_raw_sqlite_by_default_when_manifest_valid(tmp_path: Path, monkeypatch):
    settings, manifest_path = _seed_file_backed_hourly_chart_fixture(tmp_path)
    monkeypatch.setenv("CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST", str(manifest_path))

    svc = EnergyKPIReadService(settings)
    chart = svc.get_plant_parcel_chart_data(
        entity_id="1001",
        entity_type="ccee_plant_parcel",
        frequency="hourly",
        year_month="2026-02",
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )
    metadata = chart["metadata"]["hourly_read_path"]

    assert chart["metadata"]["data_source"] == "ccee_plant_parcel_hourly"
    assert metadata["attempted"] is False
    assert metadata["selected"] == "raw_sqlite"
    assert metadata["fallback_reason"] == "parcel_raw_sqlite_default"
    assert metadata["manifest_path"] == str(manifest_path)
    assert chart["periods"] == ["00h", "01h"]
    assert chart["series"][0]["points"] == [10.0, 12.0]


def test_hourly_chart_falls_back_to_raw_sqlite_when_manifest_missing(tmp_path: Path, monkeypatch):
    settings, _manifest_path = _seed_file_backed_hourly_chart_fixture(tmp_path)
    monkeypatch.setenv("CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST", str(tmp_path / "missing_manifest.json"))

    svc = EnergyKPIReadService(settings)
    chart = svc.get_plant_parcel_chart_data(
        entity_id="CEG123",
        entity_type="aneel_plant",
        frequency="hourly",
        year_month="2026-02",
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )
    metadata = chart["metadata"]["hourly_read_path"]

    assert chart["metadata"]["data_source"] == "ccee_plant_parcel_hourly"
    assert metadata["attempted"] is True
    assert metadata["selected"] == "raw_sqlite"
    assert metadata["fallback_reason"] == "manifest_missing"
    assert chart["periods"] == ["00h", "01h"]
    assert chart["series"][0]["points"] == [10.0, 12.0]


def test_hourly_chart_falls_back_to_raw_sqlite_when_manifest_stale(tmp_path: Path, monkeypatch):
    settings, manifest_path = _seed_file_backed_hourly_chart_fixture(tmp_path)
    future = time.time() + 10
    os.utime(settings.paths.energy_kpi_db_path, (future, future))
    monkeypatch.setenv("CVM_ENERGY_HOURLY_HOT_COLD_MANIFEST", str(manifest_path))

    svc = EnergyKPIReadService(settings)
    chart = svc.get_plant_parcel_chart_data(
        entity_id="CEG123",
        entity_type="aneel_plant",
        frequency="hourly",
        year_month="2026-02",
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )
    metadata = chart["metadata"]["hourly_read_path"]

    assert chart["metadata"]["data_source"] == "ccee_plant_parcel_hourly"
    assert metadata["attempted"] is True
    assert metadata["selected"] == "raw_sqlite"
    assert metadata["fallback_reason"] == "source_signature_mismatch"
    assert metadata["source_signature_ok"] is False
    assert chart["periods"] == ["00h", "01h"]
    assert chart["series"][0]["points"] == [10.0, 12.0]
