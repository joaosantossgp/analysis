"""EnergyKPIRefreshJob — orchestrates the full energy KPI refresh pipeline.

Stages: FETCH → NORMALIZE → MERGE → VALIDATE → UPSERT
Atomic: on failure keeps prior data and logs the error.
User-triggered only — never called on app startup.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from src.energy_kpi.ingest_owid import (
    fetch_owid_snapshot,
    normalize_owid,
    persist_snapshot_record,
    seed_country_dimension,
    seed_kpi_catalog,
    seed_kpi_sources,
    upsert_country_kpi_values,
)
from src.energy_kpi.merge import (
    compute_derived_kpis,
    merge_sources,
    set_data_quality_status,
)
from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)

StageCallback = Callable[[str, str], None]  # (stage_name, message)
ProgressCallback = Callable[[int, int], None]  # (done, total)

STAGES = ["FETCH", "NORMALIZE", "MERGE", "VALIDATE", "UPSERT"]


class EnergyKPIRefreshJob:
    """Orchestrates a single energy KPI refresh run.

    Usage:
        job = EnergyKPIRefreshJob(settings)
        result = job.run()

    Callbacks are optional; useful for bridge progress updates.
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

    def _stage(self, name: str, msg: str = "") -> None:
        logger.info("[%s] %s %s", self._run_id[:8], name, msg)
        self._stage_cb(name, msg)

    def run(self, triggered_by: str = "user") -> dict:
        """Execute the full pipeline. Returns a result dict."""
        engine = get_energy_kpi_engine(self.settings)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rows_ingested = 0
        rows_conflict = 0
        error: str | None = None

        # Log run start
        with engine.begin() as conn:
            conn.execute(
                __import__("sqlalchemy").text("""
                    INSERT INTO kpi_refresh_log
                        (run_id, started_at, source, status, triggered_by)
                    VALUES (:rid, :sat, 'OWID', 'running', :tby)
                """),
                {"rid": self._run_id, "sat": started_at, "tby": triggered_by},
            )
            # Ensure reference data is seeded
            seed_kpi_sources(conn)
            seed_country_dimension(conn)
            seed_kpi_catalog(conn)

        try:
            # ── FETCH ─────────────────────────────────────────────────────────
            self._stage("FETCH", "Downloading OWID energy dataset")
            self._progress_cb(0, len(STAGES))
            snapshot = fetch_owid_snapshot(self.settings.paths)

            with engine.begin() as conn:
                persist_snapshot_record(conn, snapshot)

            # ── NORMALIZE ─────────────────────────────────────────────────────
            self._stage("NORMALIZE", "Normalizing OWID data")
            self._progress_cb(1, len(STAGES))
            direct_df = normalize_owid(snapshot)

            # ── MERGE ─────────────────────────────────────────────────────────
            self._stage("MERGE", "Computing derived KPIs and merging sources")
            self._progress_cb(2, len(STAGES))
            derived_df = compute_derived_kpis(direct_df)

            import pandas as pd
            all_df = pd.concat([direct_df, derived_df], ignore_index=True) if not derived_df.empty else direct_df
            merged_df = merge_sources(all_df, ember_df=None)
            merged_df = set_data_quality_status(
                merged_df,
                owid_fetched_at=snapshot.fetched_at,
            )

            rows_conflict = int(merged_df.get("source_conflict", pd.Series(False)).sum())

            # ── VALIDATE ──────────────────────────────────────────────────────
            self._stage("VALIDATE", "Running quality checks")
            self._progress_cb(3, len(STAGES))
            from src.energy_kpi.quality import run_quality_checks
            with engine.begin() as conn:
                dq_results = run_quality_checks(conn, self._run_id, merged_df)
            errors_found = [r for r in dq_results if r.severity == "error" and not r.passed]
            if errors_found:
                logger.warning(
                    "%d DQ error(s) in run %s: %s",
                    len(errors_found),
                    self._run_id[:8],
                    [r.check_name for r in errors_found],
                )

            # ── UPSERT ────────────────────────────────────────────────────────
            self._stage("UPSERT", "Persisting KPI values")
            self._progress_cb(4, len(STAGES))
            with engine.begin() as conn:
                rows_ingested = upsert_country_kpi_values(conn, merged_df)

        except Exception as exc:
            error = str(exc)
            logger.exception("EnergyKPIRefreshJob %s failed: %s", self._run_id[:8], exc)
        finally:
            finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            status = "error" if error else "success"
            self._progress_cb(len(STAGES), len(STAGES))
            with engine.begin() as conn:
                conn.execute(
                    __import__("sqlalchemy").text("""
                        UPDATE kpi_refresh_log
                        SET finished_at=:fat, status=:st,
                            rows_ingested=:ri, rows_conflict=:rc, error=:err
                        WHERE run_id=:rid
                    """),
                    {
                        "fat": finished_at,
                        "st": status,
                        "ri": rows_ingested,
                        "rc": rows_conflict,
                        "err": error,
                        "rid": self._run_id,
                    },
                )

        return {
            "run_id": self._run_id,
            "status": status,
            "rows_ingested": rows_ingested,
            "rows_conflict": rows_conflict,
            "error": error,
            "started_at": started_at,
            "finished_at": finished_at,
        }
