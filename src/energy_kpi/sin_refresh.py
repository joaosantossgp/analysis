"""User-triggered refresh job for SIN subsystem KPIs."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

import pandas as pd
from sqlalchemy import text

from src.energy_kpi.schema import get_energy_kpi_engine
from src.energy_kpi.sin_ingest import (
    ONS_DATASETS,
    fetch_ccee_pld_snapshot,
    fetch_ons_snapshot,
    parse_ccee_pld,
    parse_ons_balanco,
    parse_ons_cmo,
    parse_ons_ear,
    parse_ons_ena,
    persist_sin_snapshot_record,
    seed_sin_kpi_catalog,
    seed_sin_kpi_sources,
    seed_subsystem_dimension,
    upsert_subsystem_kpi_values,
)
from src.settings import AppSettings

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int], None]

_PARSERS = {
    "balanco_energia_subsistema": parse_ons_balanco,
    "ear_diario_subsistema": parse_ons_ear,
    "ena_diario_subsistema": parse_ons_ena,
    "cmo_semihorario": parse_ons_cmo,
    "pld_horario": parse_ccee_pld,
}


class SINKPIRefreshJob:
    """Refresh SIN subsystem KPIs from ONS and optionally CCEE.

    Network access occurs only inside this explicit job. Reads remain offline.
    """

    def __init__(
        self,
        settings: AppSettings,
        stage_callback: StageCallback | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self._stage_cb = stage_callback or (lambda stage, msg: None)
        self._progress_cb = progress_callback or (lambda done, total: None)
        self._run_id = str(uuid.uuid4())

    def _stage(self, name: str, message: str = "") -> None:
        logger.info("[%s] %s %s", self._run_id[:8], name, message)
        self._stage_cb(name, message)

    def run(
        self,
        *,
        triggered_by: str = "user",
        years: list[int] | None = None,
        include_ccee: bool = True,
    ) -> dict:
        now = datetime.now(timezone.utc)
        selected_years = sorted(set(int(y) for y in (years or [now.year - 1, now.year])))
        datasets = list(ONS_DATASETS.keys()) + (["pld_horario"] if include_ccee else [])
        total_steps = max(1, len(selected_years) * len(datasets))

        engine = get_energy_kpi_engine(self.settings)
        started_at = now.isoformat(timespec="seconds")
        errors: list[dict[str, str]] = []
        frames: list[pd.DataFrame] = []
        snapshots = 0
        done = 0

        with engine.begin() as conn:
            seed_sin_kpi_sources(conn)
            seed_subsystem_dimension(conn)
            seed_sin_kpi_catalog(conn)
            conn.execute(
                text("""
                    INSERT INTO kpi_refresh_log
                        (run_id, started_at, source, status, triggered_by)
                    VALUES (:run_id, :started_at, 'SIN', 'running', :triggered_by)
                """),
                {
                    "run_id": self._run_id,
                    "started_at": started_at,
                    "triggered_by": triggered_by,
                },
            )

        for year in selected_years:
            for dataset in datasets:
                self._stage(dataset.upper(), f"Fetching {dataset} {year}")
                self._progress_cb(done, total_steps)
                try:
                    if dataset == "pld_horario":
                        snapshot = fetch_ccee_pld_snapshot(self.settings.paths, year)
                    else:
                        snapshot = fetch_ons_snapshot(self.settings.paths, dataset, year)
                    parser = _PARSERS[dataset]
                    frame = parser(snapshot)
                    with engine.begin() as conn:
                        persist_sin_snapshot_record(conn, snapshot)
                    snapshots += 1
                    if not frame.empty:
                        frames.append(frame)
                except Exception as exc:
                    logger.warning("SIN refresh failed for %s %s: %s", dataset, year, exc)
                    errors.append({
                        "dataset": dataset,
                        "year": str(year),
                        "error": str(exc),
                    })
                finally:
                    done += 1
                    self._progress_cb(done, total_steps)

        rows_inserted = 0
        rows_read = int(sum(len(frame) for frame in frames))
        if frames:
            all_df = pd.concat(frames, ignore_index=True)
            with engine.begin() as conn:
                rows_inserted = upsert_subsystem_kpi_values(conn, all_df)
                self._insert_quality_rows(conn, errors, rows_read, rows_inserted)
        else:
            with engine.begin() as conn:
                self._insert_quality_rows(conn, errors, rows_read, rows_inserted)

        if rows_inserted > 0 and errors:
            status = "partial"
        elif rows_inserted > 0:
            status = "success"
        else:
            status = "error"

        error_text = json.dumps(errors, ensure_ascii=False) if errors else None
        finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE kpi_refresh_log
                    SET finished_at=:finished_at, status=:status,
                        rows_ingested=:rows_inserted, rows_conflict=0,
                        error=:error
                    WHERE run_id=:run_id
                """),
                {
                    "finished_at": finished_at,
                    "status": status,
                    "rows_inserted": rows_inserted,
                    "error": error_text,
                    "run_id": self._run_id,
                },
            )

        return {
            "run_id": self._run_id,
            "status": status,
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "snapshots": snapshots,
            "errors": errors,
            "error": error_text,
            "started_at": started_at,
            "finished_at": finished_at,
        }

    def _insert_quality_rows(
        self,
        conn,
        errors: list[dict[str, str]],
        rows_read: int,
        rows_inserted: int,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows = [
            {
                "check_id": str(uuid.uuid4()),
                "run_id": self._run_id,
                "check_name": "sin_refresh_summary",
                "severity": "info",
                "passed": 1,
                "details": json.dumps(
                    {
                        "rows_read": rows_read,
                        "rows_inserted": rows_inserted,
                        "source_failures": len(errors),
                    },
                    ensure_ascii=False,
                ),
                "created_at": created_at,
            }
        ]
        for error in errors:
            rows.append({
                "check_id": str(uuid.uuid4()),
                "run_id": self._run_id,
                "check_name": f"sin_source_failure:{error['dataset']}:{error['year']}",
                "severity": "warn" if error["dataset"] == "pld_horario" else "error",
                "passed": 0,
                "details": json.dumps(error, ensure_ascii=False),
                "created_at": created_at,
            })
        conn.execute(
            text("""
                INSERT INTO data_quality_checks
                    (check_id, run_id, check_name, severity, passed, details_json, created_at)
                VALUES
                    (:check_id, :run_id, :check_name, :severity, :passed, :details, :created_at)
            """),
            rows,
        )
