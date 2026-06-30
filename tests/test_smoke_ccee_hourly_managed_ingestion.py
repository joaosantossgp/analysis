from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from scripts.data.smoke_ccee_hourly_managed_ingestion import run_smoke
from scripts.diagnostics.phase5_hot_cold_hourly_prototype import build_hot_cold_prototype
from src.energy_kpi.plant_parcel_ingest import (
    SOURCE_CCEE_HOURLY,
    SOURCE_CCEE_MONTHLY,
    PlantSnapshotRecord,
    parse_ccee_hourly,
    parse_ccee_monthly,
    seed_plant_sources,
    upsert_ccee_hourly,
    upsert_ccee_monthly,
)
from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import build_settings


HOURLY_TABLE = "ccee_plant_parcel_hourly"


def _write_csv(path: Path, columns: list[str], rows: list[list[object]]) -> Path:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, sep=";")
    return path


def _snapshot(path: Path, source_id: str, dataset: str) -> PlantSnapshotRecord:
    return PlantSnapshotRecord(
        snapshot_id=f"test-{source_id}",
        source_id=source_id,
        provider="CCEE",
        dataset_name=dataset,
        fetched_at="2026-06-01T00:00:00+00:00",
        file_path=path,
        sha256="deadbeef",
        row_count=1,
        source_url="https://example.test/source.csv",
        source_version_label=f"{dataset}:test",
    )


def _manifest_fingerprint(manifest: dict) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_counts(manifest: dict) -> dict[str, int]:
    return {
        str(row["reference_month"]): int(row["row_count"])
        for row in manifest.get("selection", {}).get("available_months", [])
    }


def _seed_external_catalog(conn, manifest_path: Path, source_db: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = _manifest_counts(manifest)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS external_hourly_store_catalog (
            dataset TEXT PRIMARY KEY,
            manifest_path TEXT NOT NULL,
            manifest_fingerprint TEXT NOT NULL,
            source_database TEXT NOT NULL,
            full_months INTEGER NOT NULL,
            manifest_row_count INTEGER NOT NULL,
            available_months_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(
        text("""
            INSERT OR REPLACE INTO external_hourly_store_catalog
                (dataset, manifest_path, manifest_fingerprint, source_database, full_months,
                 manifest_row_count, available_months_json)
            VALUES
                (:dataset, :manifest_path, :manifest_fingerprint, :source_database, 1,
                 :manifest_row_count, :available_months_json)
        """),
        {
            "dataset": HOURLY_TABLE,
            "manifest_path": str(manifest_path),
            "manifest_fingerprint": _manifest_fingerprint(manifest),
            "source_database": str(source_db),
            "manifest_row_count": sum(counts.values()),
            "available_months_json": json.dumps(counts, sort_keys=True, separators=(",", ":")),
        },
    )


def test_smoke_ccee_hourly_managed_ingestion_runs_against_compacted_store(tmp_path: Path):
    settings = build_settings(project_root=tmp_path)
    engine = get_energy_kpi_engine(settings)
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
    seed_hourly_path = _write_csv(
        tmp_path / "geracao_horaria_usina_202601.csv",
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
        [["202601", "01/01/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "5", "4", "3", "0"]],
    )
    import_path = _write_csv(
        tmp_path / "geracao_horaria_usina_202602.csv",
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
        [["202602", "02/02/2026", 1, "1001", "PLT1", "Hidraulica", "SE/CO", "10", "9", "8", "1"]],
    )

    with engine.begin() as conn:
        seed_plant_sources(conn)
        upsert_ccee_monthly(
            conn,
            parse_ccee_monthly(_snapshot(monthly_path, SOURCE_CCEE_MONTHLY, "PARCELA_USINA_MONTANTE_MENSAL")),
        )
        upsert_ccee_hourly(
            conn,
            parse_ccee_hourly(_snapshot(seed_hourly_path, SOURCE_CCEE_HOURLY, "GERACAO_HORARIA_USINA")),
        )

    store_dir = settings.paths.data_dir / "analytics" / "energy" / "ccee_plant_generation_hourly"
    manifest = build_hot_cold_prototype(
        database=settings.paths.energy_kpi_db_path,
        output_dir=store_dir,
        hot_months=1,
        cold_months=[],
        full_months=True,
    )
    manifest_path = Path(manifest["artifacts"]["manifest_path"])
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {HOURLY_TABLE}"))
        _seed_external_catalog(conn, manifest_path, settings.paths.energy_kpi_db_path)

    report = run_smoke(
        settings=settings,
        source_file=import_path,
        reference_month="2026-02",
        sandbox=True,
        force_reimport=True,
    )

    assert report["ok"] is True
    assert report["before"]["main_raw_hourly_rows"] == 0
    assert report["after"]["main_raw_hourly_rows"] == 0
    assert report["after"]["hot_rows_for_month"] == 1
    assert report["after"]["cold_rows_for_month"] == 0
    assert report["after"]["managed_rows_for_month"] == 1
    assert report["after"]["daily_mart_observations_for_month"] == 1
    assert report["storage_telemetry"]["after"]["manifest_row_count"] == 2
