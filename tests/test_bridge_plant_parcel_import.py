from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from desktop.bridge import CVMBridge
from src.settings import build_settings


def _write_hourly_csv(path: Path) -> Path:
    pd.DataFrame(
        [[
            "2026-05",
            "2026-05-01",
            1,
            "PU1",
            "UTE1",
            "TERMICA",
            "SE",
            10.0,
            0.0,
        ]],
        columns=[
            "MES_REFERENCIA",
            "DATA",
            "PERIODO_COMERCIALIZACAO",
            "CODIGO_PARCELA_USINA",
            "SIGLA_USINA",
            "FONTE_PRIMARIA",
            "SUBMERCADO",
            "GERACAO_CENTRO_GRAVIDADE",
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        ],
    ).to_csv(path, index=False, sep=";")
    return path


def test_manual_plant_parcel_import_returns_started_and_finishes_in_background(tmp_path, monkeypatch):
    settings = build_settings(tmp_path)
    monkeypatch.setattr("src.settings.get_settings", lambda: settings)
    hourly_path = _write_hourly_csv(tmp_path / "geracao_horaria_usina_202605.csv")
    bridge = CVMBridge()

    result = bridge.import_plant_parcel_source_file({
        "source_id": "ccee_plant_generation_hourly",
        "files": [{"file_path": str(hourly_path), "original_file_name": hourly_path.name}],
    })

    assert result["status"] == "started"
    deadline = time.time() + 5
    state = bridge._plant_parcel_refresh_status()
    while state.get("status") == "running" and time.time() < deadline:
        time.sleep(0.05)
        state = bridge._plant_parcel_refresh_status()

    assert state["status"] == "success"
    assert state["rows_inserted"] == 1
