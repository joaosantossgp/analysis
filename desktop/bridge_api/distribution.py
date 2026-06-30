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
        from src.energy_kpi.distribution.catalog import ANEEL_RESOURCES  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        status = getattr(self, "_dist_refresh_state", {"status": "idle", "error": None}).copy()
        status["supported_years"] = sorted(list(ANEEL_RESOURCES.get("samp_mercado", {}).keys()))

        ingested_years = []
        try:
            engine = self._dist_svc()._engine()
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT DISTINCT source_version_label
                    FROM source_snapshots
                    WHERE source_version_label LIKE 'ANEEL:samp_mercado:%' AND status = 'ok'
                """)).fetchall()
                for r in rows:
                    parts = r[0].split(":")
                    if len(parts) == 3:
                        try:
                            ingested_years.append(int(parts[2]))
                        except ValueError:
                            pass
        except Exception:
            pass
        status["ingested_years"] = sorted(list(set(ingested_years)))
        return status

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

    def _log_resource_refresh(
        self,
        conn,
        source_id: str,
        started_at: str,
        finished_at: str,
        status: str,
        snap_record,  # DistributionSnapshotRecord
        elapsed_download_ms: int,
        elapsed_parse_ms: int,
        elapsed_publish_ms: int,
        stats: dict = None,
        error_msg: str = None
    ):
        import uuid
        from sqlalchemy import text
        from src.energy_kpi.distribution.ingest import PARSER_VERSION

        refresh_id = str(uuid.uuid4())
        stats = stats or {}

        query = """
            INSERT INTO energy_source_refresh_log (
                refresh_id, source_id, requested_by, started_at, finished_at, status,
                rows_downloaded, rows_inserted, rows_updated, error_message, local_file_path, checksum,
                downloaded_bytes, source_rows, parsed_rows, normalized_rows, file_size_bytes, file_type,
                canonical_rows, valid_domain_rows, missing_key_rows, invalid_value_rows,
                unresolved_identity_rows, non_distributor_entity_rows, exact_duplicate_rows,
                duplicate_groups, conflicting_logical_keys, conflict_rows, quarantined_rows,
                lead_kpi_rows, supporting_detail_rows, intentionally_excluded_rows, rejected_rows,
                rows_unchanged, rows_removed_deactivated, final_published_rows,
                elapsed_download_ms, elapsed_parse_ms, elapsed_publish_ms,
                elapsed_lock_wait_ms, peak_rss_mb, cpu_time_ms,
                parser_version, snapshot_id, final_source_status, elapsed_aggregate_ms
            ) VALUES (
                :refresh_id, :source_id, 'user', :started_at, :finished_at, :status,
                :rows_downloaded, :rows_inserted, :rows_updated, :error_message, :local_file_path, :checksum,
                :downloaded_bytes, :source_rows, :parsed_rows, :normalized_rows, :file_size_bytes, :file_type,
                :canonical_rows, :valid_domain_rows, :missing_key_rows, :invalid_value_rows,
                :unresolved_identity_rows, :non_distributor_entity_rows, :exact_duplicate_rows,
                :duplicate_groups, :conflicting_logical_keys, :conflict_rows, :quarantined_rows,
                :lead_kpi_rows, :supporting_detail_rows, :intentionally_excluded_rows, :rejected_rows,
                :rows_unchanged, :rows_removed_deactivated, :final_published_rows,
                :elapsed_download_ms, :elapsed_parse_ms, :elapsed_publish_ms,
                :elapsed_lock_wait_ms, :peak_rss_mb, :cpu_time_ms,
                :parser_version, :snapshot_id, :final_source_status, :elapsed_aggregate_ms
            )
        """

        local_path = str(snap_record.file_path) if snap_record else None
        checksum = snap_record.sha256 if snap_record else None
        snap_id = snap_record.snapshot_id if snap_record else None

        # Get file size if path exists
        file_size = None
        if snap_record and snap_record.file_path.exists():
            file_size = snap_record.file_path.stat().st_size

        conn.execute(
            text(query),
            {
                "refresh_id": refresh_id,
                "source_id": source_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "rows_downloaded": snap_record.row_count if snap_record else None,
                "rows_inserted": stats.get("rows_inserted"),
                "rows_updated": stats.get("rows_updated"),
                "error_message": error_msg,
                "local_file_path": local_path,
                "checksum": checksum,
                "downloaded_bytes": file_size,
                "source_rows": stats.get("source_rows", snap_record.row_count if snap_record else None),
                "parsed_rows": stats.get("parsed_rows"),
                "normalized_rows": stats.get("final_published_rows"),
                "file_size_bytes": file_size,
                "file_type": snap_record.file_path.suffix.lstrip(".") if snap_record else None,
                "canonical_rows": stats.get("canonical_rows"),
                "valid_domain_rows": stats.get("valid_domain_rows"),
                "missing_key_rows": stats.get("missing_key_rows"),
                "invalid_value_rows": stats.get("invalid_value_rows"),
                "unresolved_identity_rows": stats.get("unresolved_identity_rows"),
                "non_distributor_entity_rows": stats.get("non_distributor_entity_rows"),
                "exact_duplicate_rows": stats.get("exact_duplicate_rows"),
                "duplicate_groups": stats.get("duplicate_groups"),
                "conflicting_logical_keys": stats.get("conflicting_logical_keys"),
                "conflict_rows": stats.get("conflict_rows"),
                "quarantined_rows": stats.get("quarantined_rows"),
                "lead_kpi_rows": stats.get("lead_kpi_rows"),
                "supporting_detail_rows": stats.get("supporting_detail_rows"),
                "intentionally_excluded_rows": stats.get("intentionally_excluded_rows"),
                "rejected_rows": stats.get("rejected_rows"),
                "rows_unchanged": stats.get("rows_unchanged"),
                "rows_removed_deactivated": stats.get("rows_removed_deactivated"),
                "final_published_rows": stats.get("final_published_rows"),
                "elapsed_download_ms": elapsed_download_ms,
                "elapsed_parse_ms": elapsed_parse_ms,
                "elapsed_publish_ms": elapsed_publish_ms,
                "elapsed_lock_wait_ms": stats.get("elapsed_lock_wait_ms"),
                "peak_rss_mb": stats.get("peak_rss_mb"),
                "cpu_time_ms": stats.get("cpu_time_ms"),
                "parser_version": PARSER_VERSION,
                "snapshot_id": snap_id,
                "final_source_status": status,
                "elapsed_aggregate_ms": stats.get("elapsed_aggregate_ms"),
            }
        )

    def _run_and_log_step(
        self,
        engine,
        settings,
        source_id: str,
        domain: str,
        resource_key,
        parse_fn,
        upsert_fn,
        force: bool
    ) -> int:
        import gc
        import time
        from datetime import datetime, timezone
        from src.energy_kpi.distribution.ingest import fetch_distribution_resource

        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        
        snap = None
        stats = {}
        status = "success"
        error_msg = None
        elapsed_download_ms = 0
        elapsed_parse_ms = 0
        elapsed_publish_ms = 0
        elapsed_lock_wait_ms = 0
        rss_samples = [self._current_process_rss_mb()]
        cpu_start = time.process_time()
        
        try:
            # A. Download
            t0 = time.time()
            lock_start = time.time()
            with engine.begin() as conn:
                elapsed_lock_wait_ms += int((time.time() - lock_start) * 1000)
                snap = fetch_distribution_resource(
                    settings.paths, conn, domain, resource_key, force=force
                )
            elapsed_download_ms = int((time.time() - t0) * 1000)
            
            # B. Parse
            t0 = time.time()
            parsed_df = parse_fn(snap.file_path, format_type=snap.file_path.suffix.lstrip("."))
            elapsed_parse_ms = int((time.time() - t0) * 1000)
            rss_samples.append(self._current_process_rss_mb())
            
            # C. Publish
            t0 = time.time()
            lock_start = time.time()
            with engine.begin() as conn:
                elapsed_lock_wait_ms += int((time.time() - lock_start) * 1000)
                result = upsert_fn(conn, parsed_df, snap.snapshot_id)
                if hasattr(result, "stats"):
                    stats = result.stats
                else:
                    stats = {
                        "source_rows": parsed_df.height,
                        "parsed_rows": parsed_df.height,
                        "canonical_rows": parsed_df.height,
                        "final_published_rows": int(result),
                    }
            elapsed_publish_ms = int((time.time() - t0) * 1000)
            rss_samples.append(self._current_process_rss_mb())
            rss_values = [value for value in rss_samples if value is not None]
            if rss_values:
                stats["peak_rss_mb"] = max(rss_values)
            stats["cpu_time_ms"] = int((time.process_time() - cpu_start) * 1000)
            stats["elapsed_lock_wait_ms"] = elapsed_lock_wait_ms
            del parsed_df
            gc.collect()
            
        except Exception as exc:
            status = "failed"
            error_msg = str(exc)
            rss_samples.append(self._current_process_rss_mb())
            rss_values = [value for value in rss_samples if value is not None]
            if rss_values:
                stats["peak_rss_mb"] = max(rss_values)
            stats["cpu_time_ms"] = int((time.process_time() - cpu_start) * 1000)
            stats["elapsed_lock_wait_ms"] = elapsed_lock_wait_ms
            logger.exception("Failed to refresh %s (%s)", domain, resource_key)
            raise
        finally:
            finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with engine.begin() as conn:
                self._log_resource_refresh(
                    conn,
                    source_id=source_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    status=status,
                    snap_record=snap,
                    elapsed_download_ms=elapsed_download_ms,
                    elapsed_parse_ms=elapsed_parse_ms,
                    elapsed_publish_ms=elapsed_publish_ms,
                    stats=stats,
                    error_msg=error_msg
                )
        return stats.get("final_published_rows", 0)

    @staticmethod
    def _current_process_rss_mb() -> float | None:
        try:
            import ctypes
            import os
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, os.getpid())
            if not handle:
                return None
            try:
                ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                    handle,
                    ctypes.byref(counters),
                    counters.cb,
                )
                if not ok:
                    return None
                return round(float(counters.WorkingSetSize) / (1024 * 1024), 1)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return None

    def get_distribution_refresh_status(self, params=None) -> dict:
        return self._sanitize_for_json(self._dist_refresh_status())

    def refresh_distribution_data(self, params=None) -> dict:
        params = params or {}
        if not hasattr(self, "_dist_refresh_lock"):
            self._dist_refresh_lock = threading.Lock()
        state = self._dist_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}
        if not self._dist_refresh_lock.acquire(blocking=False):
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
            import gc
            import time
            try:
                from src.platform.settings import get_settings
                from src.energy_kpi.schema import get_energy_kpi_engine
                from src.energy_kpi.distribution.ingest import (
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
                from src.energy_kpi.distribution.aggregates import rebuild_distribution_aggregate_slices
                
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
                aggregate_slices: list[str] = []
                
                # 1. Consolidated SAMP Balanco
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_balance",
                    "message": "Processing ANEEL SAMP Balanco...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "samp_balanco", "samp_balanco", None,
                    parse_samp_balanco, upsert_samp_balanco_facts, force=params.get("force", False)
                )
                aggregate_slices.append("balance")
                
                # 2. Annual SAMP Mercado files
                failed_years = []
                for idx, year in enumerate(years_to_refresh):
                    step_idx += 1
                    self._dist_refresh_state.update({
                        "stage": "downloading_market",
                        "message": f"Processing ANEEL SAMP Mercado for year {year}...",
                        "progress_current": step_idx
                    })
                    try:
                        rows_inserted += self._run_and_log_step(
                            engine, settings, f"samp_mercado_{year}", "samp_mercado", year,
                            parse_samp_mercado, upsert_samp_mercado_facts, force=params.get("force", False)
                        )
                        if "market" not in aggregate_slices:
                            aggregate_slices.append("market")
                    except Exception as exc:
                        logger.error("Failed to process ANEEL SAMP Mercado for year %s: %s", year, exc, exc_info=True)
                        failed_years.append(year)

                # 3. Continuity limits
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_limits",
                    "message": "Processing ANEEL continuity limits...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "continuity_limits", "continuity_limits", None,
                    parse_continuity_limits, upsert_continuity_limits_facts, force=params.get("force", False)
                )
                aggregate_slices.append("continuity")

                # 4. Continuity actuals (by decade)
                for key in actuals_keys:
                    step_idx += 1
                    self._dist_refresh_state.update({
                        "stage": "downloading_actuals",
                        "message": f"Processing ANEEL continuity actuals for decade {key}...",
                        "progress_current": step_idx
                    })
                    rows_inserted += self._run_and_log_step(
                        engine, settings, f"continuity_actuals_{key}", "continuity_actuals", key,
                        parse_continuity_actuals, upsert_continuity_actuals_facts, force=params.get("force", False)
                    )
                    if "continuity" not in aggregate_slices:
                        aggregate_slices.append("continuity")

                # 5. Continuity compensations
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_compensations",
                    "message": "Processing ANEEL continuity compensations...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "continuity_compensation", "continuity_compensation", None,
                    parse_continuity_compensations, upsert_continuity_compensations_facts, force=params.get("force", False)
                )
                aggregate_slices.append("compensation")

                # 6. Homologated tariffs
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_tariffs",
                    "message": "Processing ANEEL homologated tariffs...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "tariffs", "tariffs", None,
                    parse_tariffs, upsert_tariffs_facts, force=params.get("force", False)
                )
                aggregate_slices.append("tariff")

                # 7. Delinquency
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_delinquency",
                    "message": "Processing ANEEL delinquency...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "delinquency", "delinquency", None,
                    parse_delinquency, upsert_delinquency_facts, force=params.get("force", False)
                )
                aggregate_slices.append("delinquency")
                
                # 8. MMGD
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "downloading_mmgd",
                    "message": "Processing ANEEL MMGD distributed generation...",
                    "progress_current": step_idx
                })
                rows_inserted += self._run_and_log_step(
                    engine, settings, "mmgd_projects", "mmgd_projects", None,
                    parse_mmgd,
                    lambda conn, frame, snapshot_id: upsert_mmgd_facts(
                        conn,
                        frame,
                        snapshot_id,
                        managed_data_dir=settings.paths.data_dir,
                    ),
                    force=params.get("force", False)
                )
                aggregate_slices.append("mmgd")
                
                # 9. Rebuild aggregates
                step_idx += 1
                self._dist_refresh_state.update({
                    "stage": "aggregating",
                    "message": "Rebuilding monthly and annual aggregates...",
                    "progress_current": step_idx
                })
                
                started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                t0 = time.time()
                try:
                    with engine.begin() as conn:
                        rebuild_distribution_aggregate_slices(conn, aggregate_slices)
                    status = "success"
                    error_msg = None
                except Exception as exc:
                    status = "failed"
                    error_msg = str(exc)
                    raise
                finally:
                    elapsed_aggregate_ms = int((time.time() - t0) * 1000)
                    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    with engine.begin() as conn:
                        self._log_resource_refresh(
                            conn,
                            source_id="rebuild_aggregates",
                            started_at=started_at,
                            finished_at=finished_at,
                            status=status,
                            snap_record=None,
                            elapsed_download_ms=0,
                            elapsed_parse_ms=0,
                            elapsed_publish_ms=0,
                            stats={"elapsed_aggregate_ms": elapsed_aggregate_ms},
                            error_msg=error_msg
                        )
 
                if failed_years:
                    self._dist_refresh_state = {
                        "status": "success",
                        "error": None,
                        "stage": "done",
                        "message": f"Refresh completed with warnings. Ingested {rows_inserted} rows. Failed years: {', '.join(map(str, failed_years))}",
                        "progress_current": step_idx,
                        "progress_total": step_idx
                    }
                else:
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
                self._dist_refresh_lock.release()
                gc.collect()
 
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

    def get_conglomerates(self, params=None) -> dict:
        try:
            from sqlalchemy import text  # noqa: PLC0415
            cvm_engine = self._svc().engine
            energy_engine = self._dist_svc()._engine()
            
            with cvm_engine.connect() as cvm_conn:
                companies = cvm_conn.execute(text("""
                    SELECT cd_cvm, company_name, ticker_b3, cnpj, setor_cvm, gics_sector 
                    FROM companies
                    WHERE is_active = 1
                """)).fetchall()
                
            company_dict = {
                c[0]: {
                    "cd_cvm": c[0],
                    "company_name": c[1],
                    "ticker_b3": c[2],
                    "cnpj": c[3],
                    "setor_cvm": c[4],
                    "gics_sector": c[5],
                    "distributors_count": 0,
                    "plants_count": 0,
                    "total_capacity_mw": 0.0,
                    "total_generation_mwmed": 0.0,
                    "is_listed": True
                }
                for c in companies
            }
            
            custom_dict = {}
            
            with energy_engine.connect() as energy_conn:
                mappings = energy_conn.execute(text("""
                    SELECT asset_id, asset_type, cd_cvm, custom_owner_name FROM conglomerate_asset_mappings
                """)).fetchall()
                
                plants_stats = energy_conn.execute(text("""
                    SELECT plant_parcel_code, capacity_mw, physical_guarantee_mwmed FROM ccee_plant_parcels
                """)).fetchall()
                plant_stats_dict = {p[0]: (p[1] or 0.0, p[2] or 0.0) for p in plants_stats}
                
            for m in mappings:
                asset_id, asset_type, cd_cvm, custom_owner = m
                if cd_cvm and cd_cvm in company_dict:
                    if asset_type == "distributor":
                        company_dict[cd_cvm]["distributors_count"] += 1
                    elif asset_type == "plant":
                        company_dict[cd_cvm]["plants_count"] += 1
                        if asset_id in plant_stats_dict:
                            cap, gen = plant_stats_dict[asset_id]
                            company_dict[cd_cvm]["total_capacity_mw"] += cap
                            company_dict[cd_cvm]["total_generation_mwmed"] += gen
                elif custom_owner and custom_owner.strip() != "":
                    owner_name = custom_owner.strip()
                    if owner_name not in custom_dict:
                        custom_dict[owner_name] = {
                            "cd_cvm": None,
                            "company_name": owner_name,
                            "ticker_b3": None,
                            "cnpj": None,
                            "setor_cvm": "Non-Listed Owner",
                            "gics_sector": "Non-Listed Group",
                            "distributors_count": 0,
                            "plants_count": 0,
                            "total_capacity_mw": 0.0,
                            "total_generation_mwmed": 0.0,
                            "is_listed": False
                        }
                    if asset_type == "distributor":
                        custom_dict[owner_name]["distributors_count"] += 1
                    elif asset_type == "plant":
                        custom_dict[owner_name]["plants_count"] += 1
                        if asset_id in plant_stats_dict:
                            cap, gen = plant_stats_dict[asset_id]
                            custom_dict[owner_name]["total_capacity_mw"] += cap
                            custom_dict[owner_name]["total_generation_mwmed"] += gen
                            
            result_items = []
            for cd_cvm, c in company_dict.items():
                has_assets = c["distributors_count"] > 0 or c["plants_count"] > 0
                is_utility = False
                sec = (c["setor_cvm"] or "").lower()
                gics = (c["gics_sector"] or "").lower()
                if "energia" in sec or "utilities" in gics or "educa" in sec:
                    is_utility = True
                    
                if has_assets or is_utility:
                    result_items.append(c)
            
            for owner_name, c in custom_dict.items():
                result_items.append(c)
                    
            result_items.sort(key=lambda x: x["company_name"].upper())
            
            return self._sanitize_for_json({
                "items": result_items,
                "count": len(result_items)
            })
        except Exception as exc:
            logger.error("Error in get_conglomerates: %s", exc, exc_info=True)
            return {"error": str(exc), "items": [], "count": 0}

    def get_asset_mappings(self, params=None) -> dict:
        try:
            from sqlalchemy import text  # noqa: PLC0415
            cvm_engine = self._svc().engine
            energy_engine = self._dist_svc()._engine()
            
            with cvm_engine.connect() as cvm_conn:
                companies = cvm_conn.execute(text("SELECT cd_cvm, company_name, ticker_b3 FROM companies")).fetchall()
            company_names = {c[0]: (c[1], c[2]) for c in companies}
            
            with energy_engine.connect() as energy_conn:
                mappings = energy_conn.execute(text("""
                    SELECT asset_id, asset_type, cd_cvm, custom_owner_name, mapping_source, review_notes FROM conglomerate_asset_mappings
                """)).fetchall()
                mapping_dict = {(m[0], m[1]): (m[2], m[3], m[4], m[5]) for m in mappings}
                
                dists = energy_conn.execute(text("""
                    SELECT distributor_id, canonical_name, normalized_cnpj, primary_uf FROM distribution_distributors
                """)).fetchall()
                
                plants = energy_conn.execute(text("""
                    SELECT plant_parcel_code, plant_name, agent_name, capacity_mw, uf FROM ccee_plant_parcels
                """)).fetchall()
                
            result_items = []
            
            for d in dists:
                dist_id, name, cnpj, uf = d
                mapped_cvm, custom_owner, source, notes = mapping_dict.get((dist_id, "distributor"), (None, None, "unmapped", None))
                
                co_name = ""
                ticker = ""
                if mapped_cvm:
                    co_name, ticker = company_names.get(mapped_cvm, ("", ""))
                elif custom_owner:
                    co_name = custom_owner
                    ticker = "Non-Listed"
                
                result_items.append({
                    "id": dist_id,
                    "type": "distributor",
                    "name": name,
                    "sub_name": f"CNPJ: {cnpj or '—'} · UF: {uf or '—'}",
                    "mapped_cvm": mapped_cvm,
                    "custom_owner_name": custom_owner,
                    "company_name": co_name,
                    "ticker": ticker,
                    "mapping_source": source,
                    "review_notes": notes,
                    "stats": "Distributor"
                })
                
            for p in plants:
                code, plant_name, agent_name, capacity, uf = p
                mapped_cvm, custom_owner, source, notes = mapping_dict.get((code, "plant"), (None, None, "unmapped", None))
                
                co_name = ""
                ticker = ""
                if mapped_cvm:
                    co_name, ticker = company_names.get(mapped_cvm, ("", ""))
                elif custom_owner:
                    co_name = custom_owner
                    ticker = "Non-Listed"
                
                result_items.append({
                    "id": code,
                    "type": "plant",
                    "name": plant_name,
                    "sub_name": f"Agent: {agent_name or '—'} · UF: {uf or '—'}",
                    "mapped_cvm": mapped_cvm,
                    "custom_owner_name": custom_owner,
                    "company_name": co_name,
                    "ticker": ticker,
                    "mapping_source": source,
                    "review_notes": notes,
                    "stats": f"{capacity or 0.0:.1f} MW Capacity"
                })
                
            result_items.sort(key=lambda x: x["name"].upper())
            
            return self._sanitize_for_json({
                "items": result_items,
                "count": len(result_items)
            })
        except Exception as exc:
            logger.error("Error in get_asset_mappings: %s", exc, exc_info=True)
            return {"error": str(exc), "items": [], "count": 0}

    def update_asset_mapping(self, params=None) -> dict:
        params = params or {}
        asset_id = params.get("asset_id")
        asset_type = params.get("asset_type")
        cd_cvm = params.get("cd_cvm")
        custom_owner_name = params.get("custom_owner_name")
        notes = params.get("review_notes")
        
        if not asset_id or not asset_type:
            return {"error": "asset_id and asset_type are required"}
        if asset_type not in ("distributor", "plant"):
            return {"error": "asset_type must be distributor or plant"}
            
        try:
            from sqlalchemy import text  # noqa: PLC0415
            energy_engine = self._dist_svc()._engine()
            t0 = datetime.utcnow().isoformat()
            
            with energy_engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM conglomerate_asset_mappings 
                    WHERE asset_id = :asset_id AND asset_type = :asset_type
                """), {"asset_id": asset_id, "asset_type": asset_type})
                
                if cd_cvm is not None and str(cd_cvm).strip() != "" and str(cd_cvm) != "0":
                    conn.execute(text("""
                        INSERT INTO conglomerate_asset_mappings (asset_id, asset_type, cd_cvm, custom_owner_name, mapping_source, review_notes, updated_at)
                        VALUES (:asset_id, :asset_type, :cd_cvm, NULL, 'manual', :notes, :updated_at)
                    """), {"asset_id": asset_id, "asset_type": asset_type, "cd_cvm": int(cd_cvm), "notes": notes, "updated_at": t0})
                elif custom_owner_name is not None and str(custom_owner_name).strip() != "":
                    conn.execute(text("""
                        INSERT INTO conglomerate_asset_mappings (asset_id, asset_type, cd_cvm, custom_owner_name, mapping_source, review_notes, updated_at)
                        VALUES (:asset_id, :asset_type, NULL, :custom_owner_name, 'manual', :notes, :updated_at)
                    """), {"asset_id": asset_id, "asset_type": asset_type, "custom_owner_name": str(custom_owner_name).strip(), "notes": notes, "updated_at": t0})
                else:
                    conn.execute(text("""
                        INSERT INTO conglomerate_asset_mappings (asset_id, asset_type, cd_cvm, custom_owner_name, mapping_source, review_notes, updated_at)
                        VALUES (:asset_id, :asset_type, NULL, NULL, 'manual', :notes, :updated_at)
                    """), {"asset_id": asset_id, "asset_type": asset_type, "notes": notes, "updated_at": t0})
            return {"status": "success", "error": None}
        except Exception as exc:
            logger.error("Error in update_asset_mapping: %s", exc, exc_info=True)
            return {"error": str(exc)}

    def run_automatic_mapping(self, params=None) -> dict:
        try:
            cvm_engine = self._svc().engine
            energy_engine = self._dist_svc()._engine()
            
            from src.energy_kpi.mappings import run_automatic_asset_mapping  # noqa: PLC0415
            
            with cvm_engine.connect() as cvm_conn:
                with energy_engine.begin() as energy_conn:
                    stats = run_automatic_asset_mapping(energy_conn, cvm_conn)
                    
            return self._sanitize_for_json(stats)
        except Exception as exc:
            logger.error("Error in run_automatic_mapping: %s", exc, exc_info=True)
            return {"error": str(exc), "status": "error"}

    def get_company_universe(self, params=None) -> dict:
        """Return all active CVM companies with data-source connection flags.

        Flags per company:
          has_financials  – company has at least one row in financial_reports
          mapped_distributors – count of distribution assets mapped to this CVM code
          mapped_plants       – count of generation plant assets mapped to this CVM code
          total_capacity_mw   – sum of capacity for mapped plants
        """
        try:
            from sqlalchemy import text  # noqa: PLC0415
            cvm_engine = self._svc().engine
            energy_engine = self._dist_svc()._engine()

            # 1. Fetch all active companies from CVM financials DB
            with cvm_engine.connect() as cvm_conn:
                companies = cvm_conn.execute(text("""
                    SELECT cd_cvm, company_name, ticker_b3, cnpj, setor_cvm, gics_sector
                    FROM companies
                    WHERE is_active = 1
                    ORDER BY company_name
                """)).fetchall()

                # 2. Which companies have financial report rows?
                companies_with_reports = set()
                try:
                    rows = cvm_conn.execute(text("""
                        SELECT DISTINCT "CD_CVM" FROM financial_reports
                    """)).fetchall()
                    companies_with_reports = {r[0] for r in rows}
                except Exception:
                    pass  # financial_reports may not exist yet

            # 3. Count energy asset mappings per CVM code
            mapped_dists: dict[int, int] = {}
            mapped_plants: dict[int, int] = {}
            plant_capacity: dict[int, float] = {}

            try:
                with energy_engine.connect() as energy_conn:
                    # Asset mapping counts grouped by cd_cvm
                    mappings = energy_conn.execute(text("""
                        SELECT asset_id, asset_type, cd_cvm
                        FROM conglomerate_asset_mappings
                        WHERE cd_cvm IS NOT NULL
                    """)).fetchall()

                    # Plant capacity stats
                    plants_stats = energy_conn.execute(text("""
                        SELECT plant_parcel_code, capacity_mw FROM ccee_plant_parcels
                    """)).fetchall()
                    plant_capacity_by_id = {p[0]: (p[1] or 0.0) for p in plants_stats}

                for asset_id, asset_type, cd_cvm in mappings:
                    if cd_cvm is None:
                        continue
                    if asset_type == "distributor":
                        mapped_dists[cd_cvm] = mapped_dists.get(cd_cvm, 0) + 1
                    elif asset_type == "plant":
                        mapped_plants[cd_cvm] = mapped_plants.get(cd_cvm, 0) + 1
                        plant_capacity[cd_cvm] = plant_capacity.get(cd_cvm, 0.0) + plant_capacity_by_id.get(asset_id, 0.0)

            except Exception:
                pass  # energy DB may not be initialized

            # 4. Build result
            result_items = []
            for row in companies:
                cd_cvm, company_name, ticker_b3, cnpj, setor_cvm, gics_sector = row
                result_items.append({
                    "cd_cvm": cd_cvm,
                    "company_name": company_name,
                    "ticker_b3": ticker_b3,
                    "cnpj": cnpj,
                    "setor_cvm": setor_cvm,
                    "gics_sector": gics_sector,
                    "has_financials": cd_cvm in companies_with_reports,
                    "mapped_distributors": mapped_dists.get(cd_cvm, 0),
                    "mapped_plants": mapped_plants.get(cd_cvm, 0),
                    "total_capacity_mw": round(plant_capacity.get(cd_cvm, 0.0), 2),
                })

            return self._sanitize_for_json({
                "items": result_items,
                "count": len(result_items),
            })
        except Exception as exc:
            logger.error("Error in get_company_universe: %s", exc, exc_info=True)
            return {"error": str(exc), "items": [], "count": 0}

    def get_company_connections(self, params=None) -> dict:
        """Return data-source connection flags for a single CVM company.

        Params:
          cd_cvm (int): the company's CVM code

        Returns a dict with:
          has_financials        – bool
          mapped_distributors   – int
          mapped_plants         – int
          total_capacity_mw     – float
        """
        params = params or {}
        cd_cvm = params.get("cd_cvm")
        if not cd_cvm:
            return {"error": "cd_cvm is required", "has_financials": False, "mapped_distributors": 0, "mapped_plants": 0, "total_capacity_mw": 0.0}
        try:
            from sqlalchemy import text  # noqa: PLC0415
            cvm_engine = self._svc().engine
            energy_engine = self._dist_svc()._engine()

            # 1. has_financials
            has_financials = False
            try:
                with cvm_engine.connect() as cvm_conn:
                    row = cvm_conn.execute(text("""
                        SELECT 1 FROM financial_reports WHERE "CD_CVM" = :cd LIMIT 1
                    """), {"cd": int(cd_cvm)}).fetchone()
                    has_financials = row is not None
            except Exception:
                pass

            # 2. Energy asset mappings for this company
            mapped_dists = 0
            mapped_plants = 0
            total_capacity_mw = 0.0
            try:
                with energy_engine.connect() as energy_conn:
                    mappings = energy_conn.execute(text("""
                        SELECT asset_id, asset_type FROM conglomerate_asset_mappings
                        WHERE cd_cvm = :cd
                    """), {"cd": int(cd_cvm)}).fetchall()

                    plant_ids = [m[0] for m in mappings if m[1] == "plant"]
                    for m in mappings:
                        if m[1] == "distributor":
                            mapped_dists += 1
                        elif m[1] == "plant":
                            mapped_plants += 1

                    if plant_ids:
                        placeholders = ",".join(f":p{i}" for i in range(len(plant_ids)))
                        bind = {f"p{i}": pid for i, pid in enumerate(plant_ids)}
                        row = energy_conn.execute(text(f"""
                            SELECT COALESCE(SUM(capacity_mw), 0.0)
                            FROM ccee_plant_parcels
                            WHERE plant_parcel_code IN ({placeholders})
                        """), bind).fetchone()
                        total_capacity_mw = float(row[0]) if row else 0.0

            except Exception:
                pass

            return self._sanitize_for_json({
                "has_financials": has_financials,
                "mapped_distributors": mapped_dists,
                "mapped_plants": mapped_plants,
                "total_capacity_mw": round(total_capacity_mw, 2),
            })
        except Exception as exc:
            logger.error("Error in get_company_connections: %s", exc, exc_info=True)
            return {"error": str(exc), "has_financials": False, "mapped_distributors": 0, "mapped_plants": 0, "total_capacity_mw": 0.0}
