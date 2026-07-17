"""Tests for SIN subsystem KPI ingestion/read paths."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from desktop.bridge_api.energy import EnergyBridgeMixin
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


def _insert_sin_series_rows(db_engine, rows: list[tuple[str, str, str]]) -> None:
    with db_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO subsystem_kpi_values (
                    kpi_id, subsystem_code, reference_datetime,
                    source_value, normalized_value, unit, source,
                    source_dataset, source_field, source_hash, snapshot_id
                ) VALUES (
                    :kpi_id, :subsystem_code, :reference_datetime,
                    :value, :value, 'BRL/MWh', 'ONS',
                    'cmo_semihorario', 'val_cmo', :source_hash, 'test-snapshot'
                )
            """),
            [
                {
                    "kpi_id": kpi_id,
                    "subsystem_code": subsystem_code,
                    "reference_datetime": reference_datetime,
                    "value": float(index),
                    "source_hash": f"row-{index}",
                }
                for index, (kpi_id, subsystem_code, reference_datetime) in enumerate(rows, start=1)
            ],
        )


def _insert_sin_observation(
    conn,
    *,
    dataset: str,
    source: str,
    kpi_id: str,
    subsystem_code: str,
    reference_datetime: str,
    snapshot_id: str,
    value: float | None = 100.0,
    unit: str = "MWmed",
    source_field: str = "fixture",
    data_quality_status: str = "ok",
) -> None:
    conn.execute(
        text("""
            INSERT INTO subsystem_kpi_values (
                kpi_id, subsystem_code, reference_datetime,
                source_value, normalized_value, unit, source,
                source_dataset, source_field, source_hash, snapshot_id,
                data_quality_status
            ) VALUES (
                :kpi_id, :subsystem_code, :reference_datetime,
                :value, :value, :unit, :source,
                :dataset, :source_field, :source_hash, :snapshot_id,
                :data_quality_status
            )
        """),
        {
            "kpi_id": kpi_id,
            "subsystem_code": subsystem_code,
            "reference_datetime": reference_datetime,
            "value": value,
            "source": source,
            "dataset": dataset,
            "unit": unit,
            "source_field": source_field,
            "source_hash": f"{dataset}:{kpi_id}:{subsystem_code}:{reference_datetime}:{unit}:{source_field}:{snapshot_id}",
            "snapshot_id": snapshot_id,
            "data_quality_status": data_quality_status,
        },
    )


def _insert_sin_snapshot(
    conn,
    *,
    dataset: str,
    source: str,
    fetched_at: str,
    snapshot_id: str | None = None,
    row_count: int = 1,
) -> str:
    snapshot_id = snapshot_id or f"snapshot-{dataset}-{uuid.uuid4()}"
    conn.execute(
        text("""
            INSERT INTO source_snapshots (
                snapshot_id, source, fetched_at, file_path, sha256,
                row_count, source_version_label, status
            ) VALUES (
                :snapshot_id, :source, :fetched_at, :file_path, 'deadbeef',
                :row_count, :source_version_label, 'ok'
            )
        """),
        {
            "snapshot_id": snapshot_id,
            "source": source,
            "fetched_at": fetched_at,
            "file_path": f"/tmp/{dataset}.csv",
            "row_count": row_count,
            "source_version_label": f"{dataset}:2026",
        },
    )
    return snapshot_id


def _insert_sin_failure(
    conn,
    *,
    dataset: str,
    created_at: str,
    error: str,
    status: str = "partial",
) -> None:
    run_id = f"run-{dataset}-{uuid.uuid4()}"
    conn.execute(
        text("""
            INSERT INTO kpi_refresh_log (
                run_id, started_at, finished_at, source, status,
                rows_ingested, rows_conflict, error, triggered_by
            ) VALUES (
                :run_id, :started_at, :finished_at, 'SIN', :status,
                0, 0, :error_text, 'test'
            )
        """),
        {
            "run_id": run_id,
            "started_at": created_at,
            "finished_at": created_at,
            "status": status,
            "error_text": json.dumps([{"dataset": dataset, "year": "2026", "error": error}]),
        },
    )
    conn.execute(
        text("""
            INSERT INTO data_quality_checks (
                check_id, run_id, check_name, severity, passed, details_json, created_at
            ) VALUES (
                :check_id, :run_id, :check_name, 'warn', 0, :details_json, :created_at
            )
        """),
        {
            "check_id": f"dq-{dataset}-{uuid.uuid4()}",
            "run_id": run_id,
            "check_name": f"sin_source_failure:{dataset}:2026",
            "details_json": json.dumps({"dataset": dataset, "year": "2026", "error": error}),
            "created_at": created_at,
        },
    )


def _sin_series_keys(values) -> list[tuple[str, str, str]]:
    return [
        (value.reference_datetime, value.subsystem_code, value.kpi_id)
        for value in values
    ]


def _source_status_by_dataset(dashboard):
    return {status.dataset: status for status in dashboard.source_statuses}


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


def test_sin_source_statuses_are_dataset_specific_when_pld_fails(
    db_engine, monkeypatch
):
    load = f"{SIN_NS}.load_mwmed"
    ear = f"{SIN_NS}.ear_stored_pct"
    ena = f"{SIN_NS}.ena_gross_mwmed"
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        seed_subsystem_dimension(conn)
        for dataset, source, kpi_id, reference_datetime in [
            ("balanco_energia_subsistema", "ONS", load, "2999-01-01T00:00:00"),
            ("ear_diario_subsistema", "ONS", ear, "2999-01-01T00:00:00"),
            ("ena_diario_subsistema", "ONS", ena, "2999-01-01T00:00:00"),
            ("cmo_semihorario", "ONS", cmo, "2999-01-01T00:30:00"),
        ]:
            snapshot_id = _insert_sin_snapshot(
                conn,
                dataset=dataset,
                source=source,
                fetched_at="2999-01-01T01:00:00+00:00",
                row_count=4,
            )
            _insert_sin_observation(
                conn,
                dataset=dataset,
                source=source,
                kpi_id=kpi_id,
                subsystem_code="S",
                reference_datetime=reference_datetime,
                snapshot_id=snapshot_id,
            )
        _insert_sin_failure(
            conn,
            dataset="pld_horario",
            created_at="2999-01-02T01:05:00+00:00",
            error="HTTP 403 Forbidden",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: pytest.fail("network call on read"))

    dashboard = svc.get_sin_kpi_dashboard()
    by_dataset = _source_status_by_dataset(dashboard)

    assert dashboard.to_dict().keys() >= {
        "last_successful_update",
        "latest_reference_datetime",
        "is_empty",
        "is_stale",
        "observations",
        "source_statuses",
    }
    for dataset in [
        "balanco_energia_subsistema",
        "ear_diario_subsistema",
        "ena_diario_subsistema",
        "cmo_semihorario",
    ]:
        status = by_dataset[dataset]
        assert status.last_status == "success"
        assert status.health_state == "success"
        assert status.last_error is None
        assert status.local_records_count == 1
        assert status.latest_reference_datetime is not None
        assert status.is_missing is False

    pld = by_dataset["pld_horario"]
    assert pld.last_status == "failed"
    assert pld.health_state == "failed"
    assert pld.latest_attempt_status == "failed"
    assert pld.latest_attempt_at == "2999-01-02T01:05:00+00:00"
    assert pld.latest_successful_snapshot_at is None
    assert pld.latest_reference_datetime is None
    assert pld.local_records_count == 0
    assert pld.is_missing is True
    assert pld.is_stale is False
    assert pld.last_error == "HTTP 403 Forbidden"


def test_sin_source_status_cached_rows_plus_newer_failure_is_partial(
    db_engine, monkeypatch
):
    pld = f"{SIN_NS}.pld_brl_mwh"
    with db_engine.begin() as conn:
        snapshot_id = _insert_sin_snapshot(
            conn,
            dataset="pld_horario",
            source="CCEE",
            fetched_at="2999-01-01T00:00:00+00:00",
            row_count=1,
        )
        _insert_sin_observation(
            conn,
            dataset="pld_horario",
            source="CCEE",
            kpi_id=pld,
            subsystem_code="SE_CO",
            reference_datetime="2999-01-01T00:00:00",
            snapshot_id=snapshot_id,
            value=150.0,
        )
        _insert_sin_failure(
            conn,
            dataset="pld_horario",
            created_at="2999-01-02T00:00:00+00:00",
            error="HTTP 403 Forbidden",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    pld_status = _source_status_by_dataset(svc.get_sin_kpi_dashboard())["pld_horario"]

    assert pld_status.health_state == "partial"
    assert pld_status.last_status == "partial"
    assert pld_status.local_records_count == 1
    assert pld_status.latest_reference_datetime == "2999-01-01T00:00:00"
    assert pld_status.latest_successful_snapshot_at == "2999-01-01T00:00:00+00:00"
    assert pld_status.latest_attempt_at == "2999-01-02T00:00:00+00:00"
    assert pld_status.latest_attempt_status == "failed"
    assert pld_status.is_missing is False
    assert pld_status.is_stale is False
    assert pld_status.last_error == "HTTP 403 Forbidden"


def test_sin_source_status_successful_snapshot_without_rows_is_partial_missing(
    db_engine, monkeypatch
):
    with db_engine.begin() as conn:
        _insert_sin_snapshot(
            conn,
            dataset="pld_horario",
            source="CCEE",
            fetched_at="2999-01-01T00:00:00+00:00",
            row_count=0,
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    pld_status = _source_status_by_dataset(svc.get_sin_kpi_dashboard())["pld_horario"]

    assert pld_status.health_state == "partial"
    assert pld_status.last_status == "partial"
    assert pld_status.local_records_count == 0
    assert pld_status.latest_successful_snapshot_at == "2999-01-01T00:00:00+00:00"
    assert pld_status.is_missing is True
    assert pld_status.is_stale is False


def test_sin_source_status_stale_cached_rows_plus_newer_failure_is_partial_and_stale(
    db_engine, monkeypatch
):
    pld = f"{SIN_NS}.pld_brl_mwh"
    with db_engine.begin() as conn:
        snapshot_id = _insert_sin_snapshot(
            conn,
            dataset="pld_horario",
            source="CCEE",
            fetched_at="2000-01-01T00:00:00+00:00",
            row_count=1,
        )
        _insert_sin_observation(
            conn,
            dataset="pld_horario",
            source="CCEE",
            kpi_id=pld,
            subsystem_code="SE_CO",
            reference_datetime="2000-01-01T00:00:00",
            snapshot_id=snapshot_id,
            value=150.0,
        )
        _insert_sin_failure(
            conn,
            dataset="pld_horario",
            created_at="2000-01-02T00:00:00+00:00",
            error="HTTP 403 Forbidden",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    pld_status = _source_status_by_dataset(svc.get_sin_kpi_dashboard())["pld_horario"]

    assert pld_status.health_state == "partial"
    assert pld_status.last_status == "partial"
    assert pld_status.local_records_count == 1
    assert pld_status.is_missing is False
    assert pld_status.is_stale is True
    assert pld_status.last_error == "HTTP 403 Forbidden"


def test_sin_source_status_newer_success_clears_older_failure(db_engine, monkeypatch):
    pld = f"{SIN_NS}.pld_brl_mwh"
    with db_engine.begin() as conn:
        _insert_sin_failure(
            conn,
            dataset="pld_horario",
            created_at="2026-07-01T00:00:00+00:00",
            error="HTTP 403 Forbidden",
            status="error",
        )
        snapshot_id = _insert_sin_snapshot(
            conn,
            dataset="pld_horario",
            source="CCEE",
            fetched_at="2999-01-01T00:00:00+00:00",
            row_count=1,
        )
        _insert_sin_observation(
            conn,
            dataset="pld_horario",
            source="CCEE",
            kpi_id=pld,
            subsystem_code="SE_CO",
            reference_datetime="2999-01-01T00:00:00",
            snapshot_id=snapshot_id,
            value=151.0,
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    pld_status = _source_status_by_dataset(svc.get_sin_kpi_dashboard())["pld_horario"]

    assert pld_status.health_state == "success"
    assert pld_status.last_status == "success"
    assert pld_status.latest_attempt_status == "success"
    assert pld_status.latest_attempt_at == "2999-01-01T00:00:00+00:00"
    assert pld_status.last_error is None
    assert pld_status.latest_failure_at == "2026-07-01T00:00:00+00:00"
    assert pld_status.is_missing is False
    assert pld_status.is_stale is False


def test_sin_source_status_missing_dataset_has_no_false_success(db_engine, monkeypatch):
    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    status = _source_status_by_dataset(svc.get_sin_kpi_dashboard())["pld_horario"]

    assert status.health_state == "missing"
    assert status.last_status == "missing"
    assert status.latest_attempt_status is None
    assert status.latest_reference_datetime is None
    assert status.latest_successful_snapshot_at is None
    assert status.latest_failure_at is None
    assert status.is_missing is True
    assert status.is_stale is False
    assert status.last_error is None


def test_sin_source_status_stale_state_is_per_dataset(db_engine, monkeypatch):
    load = f"{SIN_NS}.load_mwmed"
    pld = f"{SIN_NS}.pld_brl_mwh"
    with db_engine.begin() as conn:
        stale_snapshot = _insert_sin_snapshot(
            conn,
            dataset="balanco_energia_subsistema",
            source="ONS",
            fetched_at="2000-01-01T00:00:00+00:00",
        )
        _insert_sin_observation(
            conn,
            dataset="balanco_energia_subsistema",
            source="ONS",
            kpi_id=load,
            subsystem_code="S",
            reference_datetime="2000-01-01T00:00:00",
            snapshot_id=stale_snapshot,
        )
        current_snapshot = _insert_sin_snapshot(
            conn,
            dataset="pld_horario",
            source="CCEE",
            fetched_at="2999-01-01T00:00:00+00:00",
        )
        _insert_sin_observation(
            conn,
            dataset="pld_horario",
            source="CCEE",
            kpi_id=pld,
            subsystem_code="SE_CO",
            reference_datetime="2999-01-01T00:00:00",
            snapshot_id=current_snapshot,
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)
    by_dataset = _source_status_by_dataset(svc.get_sin_kpi_dashboard())

    assert by_dataset["balanco_energia_subsistema"].health_state == "stale"
    assert by_dataset["balanco_energia_subsistema"].is_missing is False
    assert by_dataset["balanco_energia_subsistema"].is_stale is True
    assert by_dataset["pld_horario"].health_state == "success"
    assert by_dataset["pld_horario"].is_missing is False
    assert by_dataset["pld_horario"].is_stale is False
    assert by_dataset["balanco_energia_subsistema"].latest_reference_datetime == "2000-01-01T00:00:00"
    assert by_dataset["pld_horario"].latest_reference_datetime == "2999-01-01T00:00:00"


def test_sin_source_status_failure_survives_service_recreation(db_engine, monkeypatch):
    with db_engine.begin() as conn:
        _insert_sin_failure(
            conn,
            dataset="pld_horario",
            created_at="2026-07-10T01:05:00+00:00",
            error="HTTP 403 Forbidden",
            status="error",
        )

    first = EnergyKPIReadService(build_settings())
    second = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(first, "_engine", lambda: db_engine)
    monkeypatch.setattr(second, "_engine", lambda: db_engine)

    assert _source_status_by_dataset(first.get_sin_kpi_dashboard())["pld_horario"].last_error == "HTTP 403 Forbidden"
    recreated = _source_status_by_dataset(second.get_sin_kpi_dashboard())["pld_horario"]
    assert recreated.health_state == "failed"
    assert recreated.last_error == "HTTP 403 Forbidden"


def test_sin_series_positive_limit_returns_newest_global_rows_in_ascending_order(
    db_engine, monkeypatch
):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    load = f"{SIN_NS}.load_mwmed"
    rows = [
        (cmo, "S", "2026-01-01T00:00:00"),
        (load, "N", "2026-01-02T00:00:00"),
        (cmo, "S", "2026-01-03T00:00:00"),
        (cmo, "N", "2026-01-04T00:00:00"),
        (load, "N", "2026-01-04T00:00:00"),
        (cmo, "S", "2026-01-04T00:00:00"),
        (load, "S", "2026-01-04T00:00:00"),
    ]
    _insert_sin_series_rows(db_engine, rows)
    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    values = svc.get_sin_kpi_series(limit=4)

    assert _sin_series_keys(values) == [
        ("2026-01-04T00:00:00", "N", cmo),
        ("2026-01-04T00:00:00", "N", load),
        ("2026-01-04T00:00:00", "S", cmo),
        ("2026-01-04T00:00:00", "S", load),
    ]
    assert len(values) == 4
    assert max(value.reference_datetime for value in values) == "2026-01-04T00:00:00"
    assert "2026-01-01T00:00:00" not in {value.reference_datetime for value in values}


def test_sin_series_applies_kpi_subsystem_and_date_filters_before_limit(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    load = f"{SIN_NS}.load_mwmed"
    rows = [
        (cmo, "S", "2026-01-01T00:00:00"),
        (cmo, "S", "2026-01-02T00:00:00"),
        (cmo, "S", "2026-01-03T00:00:00"),
        (cmo, "S", "2026-01-04T00:00:00"),
        (cmo, "S", "2026-01-05T00:00:00"),
        (load, "S", "2026-01-06T00:00:00"),
        (cmo, "N", "2026-01-07T00:00:00"),
    ]
    _insert_sin_series_rows(db_engine, rows)
    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    window_values = svc.get_sin_kpi_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-01-02T00:00:00",
        end_datetime="2026-01-04T00:00:00",
    )
    values = svc.get_sin_kpi_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-01-02T00:00:00",
        end_datetime="2026-01-04T00:00:00",
        limit=2,
    )

    assert [value.reference_datetime for value in window_values] == [
        "2026-01-02T00:00:00",
        "2026-01-03T00:00:00",
        "2026-01-04T00:00:00",
    ]
    assert _sin_series_keys(values) == [
        ("2026-01-03T00:00:00", "S", cmo),
        ("2026-01-04T00:00:00", "S", cmo),
    ]


@pytest.mark.parametrize("limit", [None, 0, -1])
def test_sin_series_non_positive_or_missing_limit_remains_unbounded(limit, db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    rows = [
        (cmo, "S", "2026-01-03T00:00:00"),
        (cmo, "S", "2026-01-01T00:00:00"),
        (cmo, "S", "2026-01-02T00:00:00"),
    ]
    _insert_sin_series_rows(db_engine, rows)
    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    values = svc.get_sin_kpi_series(limit=limit)

    assert [value.reference_datetime for value in values] == [
        "2026-01-01T00:00:00",
        "2026-01-02T00:00:00",
        "2026-01-03T00:00:00",
    ]


def test_sin_series_below_limit_result_is_unchanged(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    rows = [
        (cmo, "S", "2026-01-02T00:00:00"),
        (cmo, "S", "2026-01-01T00:00:00"),
    ]
    _insert_sin_series_rows(db_engine, rows)
    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    unbounded = svc.get_sin_kpi_series()
    bounded = svc.get_sin_kpi_series(limit=10)

    assert bounded == unbounded


def test_sin_daily_chart_series_preserves_daily_mean_missingness_and_lineage(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        seed_sin_kpi_catalog(conn)
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-01-01T00:00:00",
            snapshot_id="snapshot-a",
            value=10.0,
            unit="R$/MWh",
            source_field="price_a",
        )
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-01-01T12:00:00",
            snapshot_id="snapshot-a",
            value=30.0,
            unit="R$/MWh",
            source_field="price_a",
            data_quality_status="warning",
        )
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-01-02T00:00:00",
            snapshot_id="snapshot-c",
            value=None,
            unit="R$/MWh",
            source_field="price_a",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    result = svc.get_sin_kpi_daily_chart_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-01-01T00:00:00",
        end_datetime="2026-01-02T23:59:59",
    )

    assert result.count == 2
    assert result.raw_row_count == 3
    assert result.requested_kpi_ids == (cmo,)
    assert result.requested_subsystem_codes == ("S",)
    assert result.coverage_start_date == "2026-01-01"
    assert result.coverage_end_date == "2026-01-02"

    first, missing = result.values
    assert first.reference_date == "2026-01-01"
    assert first.value == pytest.approx(20.0)
    assert first.frequency == "semi-hourly"
    assert first.raw_row_count == 2
    assert first.contributing_observation_count == 2
    assert first.sources == ("ONS",)
    assert first.source_datasets == ("cmo_semihorario",)
    assert first.source_fields == ("price_a",)
    assert first.data_quality_statuses == ("ok", "warning")
    assert first.snapshot_ids == ("snapshot-a",)
    assert first.aggregation == "daily_mean_non_null"
    assert first.raw_drilldown.method == "get_sin_kpi_series"
    assert first.raw_drilldown.kpi_ids == (cmo,)
    assert first.raw_drilldown.subsystem_codes == ("S",)
    assert first.raw_drilldown.start_datetime == "2026-01-01T00:00:00"
    assert first.raw_drilldown.end_datetime == "2026-01-01T23:59:59.999999"
    assert first.raw_drilldown.raw_reader_row_count == 2

    assert missing.reference_date == "2026-01-02"
    assert missing.value is None
    assert missing.raw_row_count == 1
    assert missing.contributing_observation_count == 0


def test_sin_daily_chart_series_keeps_different_units_as_distinct_daily_values(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-01T00:00:00",
            snapshot_id="snapshot-brl",
            value=100.0,
            unit="R$/MWh",
        )
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-01T12:00:00",
            snapshot_id="snapshot-usd",
            value=20.0,
            unit="USD/MWh",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    result = svc.get_sin_kpi_daily_chart_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-02-01T00:00:00",
        end_datetime="2026-02-01T23:59:59",
    )

    assert [(row.reference_date, row.unit, row.value) for row in result.values] == [
        ("2026-02-01", "R$/MWh", 100.0),
        ("2026-02-01", "USD/MWh", 20.0),
    ]
    assert [row.raw_row_count for row in result.values] == [1, 1]
    assert [row.raw_drilldown.raw_reader_row_count for row in result.values] == [2, 2]


def test_sin_daily_chart_series_never_averages_different_sources(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-02T00:00:00",
            snapshot_id="snapshot-ons",
            value=10.0,
            unit="R$/MWh",
            source_field="val_cmo",
        )
        _insert_sin_observation(
            conn,
            dataset="pld_horario",
            source="CCEE",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-02T12:00:00",
            snapshot_id="snapshot-ccee",
            value=30.0,
            unit="R$/MWh",
            source_field="PLD_HORA",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    result = svc.get_sin_kpi_daily_chart_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-02-02T00:00:00",
        end_datetime="2026-02-02T23:59:59",
    )

    assert result.count == 2
    assert {(row.sources, row.source_datasets, row.value) for row in result.values} == {
        (("ONS",), ("cmo_semihorario",), 10.0),
        (("CCEE",), ("pld_horario",), 30.0),
    }


def test_sin_daily_chart_raw_drilldown_intersects_partial_day_request(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-03T00:00:00",
            snapshot_id="snapshot-ons",
            value=10.0,
            unit="R$/MWh",
            source_field="val_cmo",
        )
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-02-03T12:00:00",
            snapshot_id="snapshot-ons",
            value=30.0,
            unit="R$/MWh",
            source_field="val_cmo",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    result = svc.get_sin_kpi_daily_chart_series(
        kpi_ids=[cmo],
        subsystem_codes=["S"],
        start_datetime="2026-02-03T12:00:00",
        end_datetime="2026-02-03T12:30:00",
    )

    assert result.count == 1
    point = result.values[0]
    assert point.value == 30.0
    assert point.raw_drilldown.start_datetime == "2026-02-03T12:00:00"
    assert point.raw_drilldown.end_datetime == "2026-02-03T12:30:00"
    assert point.raw_drilldown.raw_reader_row_count == 1


def test_sin_daily_chart_bridge_exposes_json_payload_and_rejects_limit(db_engine, monkeypatch):
    cmo = f"{SIN_NS}.cmo_brl_mwh"
    with db_engine.begin() as conn:
        _insert_sin_observation(
            conn,
            dataset="cmo_semihorario",
            source="ONS",
            kpi_id=cmo,
            subsystem_code="S",
            reference_datetime="2026-03-01T00:00:00",
            snapshot_id="snapshot-bridge",
            value=42.0,
            unit="R$/MWh",
        )

    svc = EnergyKPIReadService(build_settings())
    monkeypatch.setattr(svc, "_engine", lambda: db_engine)

    class TestEnergyBridge(EnergyBridgeMixin):
        def _energy_svc(self):
            return svc

        def _retry_energy_read(self, fn, *, attempts: int = 4):
            return fn()

        def _sanitize_for_json(self, value):
            return value

    bridge = TestEnergyBridge()
    payload = bridge.get_sin_kpi_daily_chart_series({
        "kpi_ids": [cmo],
        "subsystem_codes": ["S"],
        "start_datetime": "2026-03-01T00:00:00",
        "end_datetime": "2026-03-01T23:59:59",
    })

    assert payload["count"] == 1
    assert payload["raw_row_count"] == 1
    assert payload["values"][0]["value"] == 42.0
    assert payload["values"][0]["raw_drilldown"]["method"] == "get_sin_kpi_series"
    rejected = bridge.get_sin_kpi_daily_chart_series({"limit": 50_000})
    assert "does not accept limit" in rejected["error"]


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
