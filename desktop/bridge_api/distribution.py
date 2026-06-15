from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("desktop.bridge")


class DistributionBridgeMixin:
    def _dist_svc(self):
        if not hasattr(self, "_distribution_read_service") or self._distribution_read_service is None:
            from src.energy_kpi.distribution.read import DistributionReadService  # noqa: PLC0415
            from src.platform.settings import get_settings  # noqa: PLC0415
            self._distribution_read_service = DistributionReadService(get_settings())
        return self._distribution_read_service

    def _dist_refresh_status(self) -> dict:
        return getattr(self, "_dist_refresh_state", {"status": "idle", "error": None})

    def _retry_dist_read(self, fn, *, attempts: int = 4):
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                return fn()
            except Exception as exc:
                if "database is locked" not in str(exc).lower():
                    raise
                last_exc = exc
                self._distribution_read_service = None
                if attempt >= attempts - 1:
                    break
                import time
                time.sleep(0.2 * (attempt + 1))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("distribution read failed")

    def get_distribution_distributors(self, params=None) -> dict:
        params = params or {}
        try:
            dists = self._retry_dist_read(
                lambda: self._dist_svc().get_distributors(
                    search=params.get("search"),
                    economic_group_id=params.get("economic_group_id"),
                    uf=params.get("uf"),
                )
            )
            return self._sanitize_for_json({
                "items": dists,
                "count": len(dists)
            })
        except Exception as exc:
            logger.error("Error in get_distribution_distributors: %s", exc, exc_info=True)
            return {"error": str(exc), "items": [], "count": 0}

    def get_distribution_distributor_detail(self, params=None) -> dict:
        params = params or {}
        distributor_id = params.get("distributor_id")
        if not distributor_id:
            return {"error": "distributor_id is required"}
        try:
            detail = self._retry_dist_read(
                lambda: self._dist_svc().get_distributor_detail(distributor_id)
            )
            if detail is None:
                return {"error": f"Distributor {distributor_id} not found"}
            return self._sanitize_for_json(detail)
        except Exception as exc:
            logger.error("Error in get_distribution_distributor_detail: %s", exc, exc_info=True)
            return {"error": str(exc)}

    def get_distribution_series(self, params=None) -> dict:
        params = params or {}
        entity_type = params.get("entity_type")
        entity_id = params.get("entity_id")
        frequency = params.get("frequency", "monthly")
        if not entity_type or not entity_id:
            return {"error": "entity_type and entity_id are required"}
        try:
            series = self._retry_dist_read(
                lambda: self._dist_svc().get_series(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    frequency=frequency
                )
            )
            return self._sanitize_for_json({
                "series": series,
                "count": len(series)
            })
        except Exception as exc:
            logger.error("Error in get_distribution_series: %s", exc, exc_info=True)
            return {"error": str(exc), "series": [], "count": 0}

    def get_distribution_refresh_status(self, params=None) -> dict:
        return self._sanitize_for_json(self._dist_refresh_status())

    def refresh_distribution_data(self, params=None) -> dict:
        params = params or {}
        state = self._dist_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}

        # Set running status
        self._dist_refresh_state = {
            "status": "running",
            "error": None,
            "stage": "starting",
            "message": "Starting distribution data refresh...",
            "progress_current": 0,
            "progress_total": 4
        }

        def _run():
            try:
                from src.platform.settings import get_settings
                from src.energy_kpi.schema import get_energy_kpi_engine
                from src.energy_kpi.distribution.ingest import (
                    fetch_distribution_resource,
                    parse_samp_mercado,
                    upsert_samp_mercado_facts,
                    parse_samp_balanco,
                    upsert_samp_balanco_facts,
                    parse_continuity_actuals,
                    upsert_continuity_actuals_facts,
                    parse_continuity_limits,
                    upsert_continuity_limits_facts,
                    parse_continuity_compensations,
                    upsert_continuity_compensations_facts,
                    parse_tariffs,
                    upsert_tariffs_facts,
                    parse_delinquency,
                    upsert_delinquency_facts,
                    parse_mmgd,
                    upsert_mmgd_facts,
                )
                from src.energy_kpi.distribution.aggregates import rebuild_distribution_aggregates
                
                settings = get_settings()
                engine = get_energy_kpi_engine(settings)
                
                # Fetch default years (e.g. 2024, 2025, 2026 for now)
                years_to_refresh = params.get("years") or [2024, 2025, 2026]
                
                actuals_keys = []
                if any(2010 <= y <= 2019 for y in years_to_refresh):
                    actuals_keys.append("10_19")
                if any(2020 <= y <= 2029 for y in years_to_refresh):
                    actuals_keys.append("20_29")
                
                # Total steps: Balance (1) + Market (years) + limits (1) + actuals (len) + compensations (1) + tariffs (1) + delinquency (1) + mmgd (1) + rebuild (1)
                self._dist_refresh_state["progress_total"] = len(years_to_refresh) + len(actuals_keys) + 7
                
                rows_inserted = 0
                step_idx = 0
                
                # 1. Download and ingest consolidated SAMP Balanco dataset
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_balance",
                    "message": "Downloading ANEEL SAMP Balanco...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "samp_balanco", force=params.get("force", False)
                    )
                    
                    self._dist_refresh_state.update({
                        "stage": "parsing_balance",
                        "message": "Parsing and normalizing SAMP Balanco..."
                    })
                    parsed_df = parse_samp_balanco(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    
                    self._dist_refresh_state.update({
                        "stage": "publishing_balance",
                        "message": "Writing balance facts to database..."
                    })
                    rows_inserted += upsert_samp_balanco_facts(conn, parsed_df, snap.snapshot_id)
                
                # 2. Download and ingest annual SAMP Mercado files
                for idx, year in enumerate(years_to_refresh):
                    step_idx += 1
                    self._dist_refresh_state.update({
                        "stage": "downloading_market",
                        "message": f"Downloading ANEEL SAMP Mercado for year {year}...",
                        "progress_current": step_idx
                    })
                    
                    with engine.begin() as conn:
                        snap = fetch_distribution_resource(
                            settings.paths, conn, "samp_mercado", year, force=params.get("force", False)
                        )
                        
                        self._dist_refresh_state.update({
                            "stage": "parsing_market",
                            "message": f"Parsing and normalizing SAMP Mercado for year {year}..."
                        })
                        parsed_df = parse_samp_mercado(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                        
                        self._dist_refresh_state.update({
                            "stage": "publishing_market",
                            "message": f"Writing market facts to database for year {year}..."
                        })
                        rows_inserted += upsert_samp_mercado_facts(conn, parsed_df, snap.snapshot_id)

                # 3. Download and ingest continuity limits
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_limits",
                    "message": "Downloading ANEEL continuity limits...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "continuity_limits", force=params.get("force", False)
                    )
                    self._dist_refresh_state.update({
                        "stage": "parsing_limits",
                        "message": "Parsing and normalizing continuity limits..."
                    })
                    parsed_df = parse_continuity_limits(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    self._dist_refresh_state.update({
                        "stage": "publishing_limits",
                        "message": "Writing continuity limits to database..."
                    })
                    rows_inserted += upsert_continuity_limits_facts(conn, parsed_df, snap.snapshot_id)

                # 4. Download and ingest continuity actuals (by decade)
                for key in actuals_keys:
                    step_idx += 1
                    self._dist_refresh_state.update({
                        "stage": "downloading_actuals",
                        "message": f"Downloading ANEEL continuity actuals for decade {key}...",
                        "progress_current": step_idx
                    })
                    with engine.begin() as conn:
                        snap = fetch_distribution_resource(
                            settings.paths, conn, "continuity_actuals", key, force=params.get("force", False)
                        )
                        self._dist_refresh_state.update({
                            "stage": "parsing_actuals",
                            "message": f"Parsing and normalizing continuity actuals for decade {key}..."
                        })
                        parsed_df = parse_continuity_actuals(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                        self._dist_refresh_state.update({
                            "stage": "publishing_actuals",
                            "message": f"Writing continuity actuals to database for decade {key}..."
                        })
                        rows_inserted += upsert_continuity_actuals_facts(conn, parsed_df, snap.snapshot_id)

                # 5. Download and ingest continuity compensations
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_compensations",
                    "message": "Downloading ANEEL continuity compensations...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "continuity_compensation", force=params.get("force", False)
                    )
                    self._dist_refresh_state.update({
                        "stage": "parsing_compensations",
                        "message": "Parsing and normalizing continuity compensations..."
                    })
                    parsed_df = parse_continuity_compensations(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    self._dist_refresh_state.update({
                        "stage": "publishing_compensations",
                        "message": "Writing continuity compensations to database..."
                    })
                    rows_inserted += upsert_continuity_compensations_facts(conn, parsed_df, snap.snapshot_id)

                # 6. Download and ingest homologated tariffs
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_tariffs",
                    "message": "Downloading ANEEL homologated tariffs...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "tariffs", force=params.get("force", False)
                    )
                    self._dist_refresh_state.update({
                        "stage": "parsing_tariffs",
                        "message": "Parsing and normalizing tariffs..."
                    })
                    parsed_df = parse_tariffs(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    self._dist_refresh_state.update({
                        "stage": "publishing_tariffs",
                        "message": "Writing tariff facts to database..."
                    })
                    rows_inserted += upsert_tariffs_facts(conn, parsed_df, snap.snapshot_id)

                # 7. Download and ingest delinquency
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_delinquency",
                    "message": "Downloading ANEEL delinquency...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "delinquency", force=params.get("force", False)
                    )
                    self._dist_refresh_state.update({
                        "stage": "parsing_delinquency",
                        "message": "Parsing and normalizing delinquency..."
                    })
                    parsed_df = parse_delinquency(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    self._dist_refresh_state.update({
                        "stage": "publishing_delinquency",
                        "message": "Writing delinquency facts to database..."
                    })
                    rows_inserted += upsert_delinquency_facts(conn, parsed_df, snap.snapshot_id)
                
                # 8. Download and ingest MMGD
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_mmgd",
                    "message": "Downloading ANEEL MMGD distributed generation...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    snap = fetch_distribution_resource(
                        settings.paths, conn, "mmgd_projects", force=params.get("force", False)
                    )
                    self._dist_refresh_state.update({
                        "stage": "parsing_mmgd",
                        "message": "Parsing and normalizing MMGD..."
                    })
                    parsed_df = parse_mmgd(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
                    self._dist_refresh_state.update({
                        "stage": "publishing_mmgd",
                        "message": "Writing MMGD facts to database..."
                    })
                    rows_inserted += upsert_mmgd_facts(conn, parsed_df, snap.snapshot_id)
                
                # 9. Rebuild aggregates
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "aggregating",
                    "message": "Rebuilding monthly and annual aggregates...",
                    "progress_current": step_idx
                })
                with engine.begin() as conn:
                    rebuild_distribution_aggregates(conn)
 
                self._dist_refresh_state = {
                    "status": "success",
                    "error": None,
                    "stage": "done",
                    "message": f"Refresh completed successfully. Ingested {rows_inserted} rows.",
                    "progress_current": step_idx,
                    "progress_total": step_idx
                }
            except Exception as exc:
                logger.error("Error in distribution refresh run: %s", exc, exc_info=True)
                self._dist_refresh_state = {
                    "status": "error",
                    "error": str(exc),
                    "stage": "failed",
                    "message": f"Refresh failed: {exc}"
                }
            finally:
                self._distribution_read_service = None

        threading.Thread(target=_run, name="distribution-refresh", daemon=True).start()
        return {"status": "started", "error": None}

    def get_distribution_groups(self, params=None) -> dict:
        try:
            groups = self._retry_dist_read(
                lambda: self._dist_svc().get_groups()
            )
            return self._sanitize_for_json({
                "items": groups,
                "count": len(groups)
            })
        except Exception as exc:
            logger.error("Error in get_distribution_groups: %s", exc, exc_info=True)
            return {"error": str(exc), "items": [], "count": 0}

    def get_distribution_group_detail(self, params=None) -> dict:
        params = params or {}
        group_id = params.get("group_id")
        if not group_id:
            return {"error": "group_id is required"}
        try:
            detail = self._retry_dist_read(
                lambda: self._dist_svc().get_group_detail(group_id)
            )
            if detail is None:
                return {"error": f"Economic group {group_id} not found"}
            return self._sanitize_for_json(detail)
        except Exception as exc:
            logger.error("Error in get_distribution_group_detail: %s", exc, exc_info=True)
            return {"error": str(exc)}

    def export_distribution_excel(self, params=None) -> dict:
        params = params or {}
        entity_type = params.get("entity_type")
        entity_id = params.get("entity_id")
        if not entity_type or not entity_id:
            return {"error": "entity_type and entity_id are required", "path": None}
        try:
            from src.energy_kpi.distribution.excel import export_distribution_excel  # noqa: PLC0415
            from src.platform.settings import get_settings  # noqa: PLC0415
            settings = get_settings()
            output_path = export_distribution_excel(
                settings=settings,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            return {"path": str(output_path), "error": None}
        except Exception as exc:
            logger.error("Error in export_distribution_excel: %s", exc, exc_info=True)
            return {"error": str(exc), "path": None}

    def get_distribution_health(self, params=None) -> dict:
        try:
            health = self._retry_dist_read(
                lambda: self._dist_svc().get_health()
            )
            return self._sanitize_for_json(health)
        except Exception as exc:
            logger.error("Error in get_distribution_health: %s", exc, exc_info=True)
            return {"error": str(exc)}



