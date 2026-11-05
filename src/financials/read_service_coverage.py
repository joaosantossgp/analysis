from __future__ import annotations

import functools
import json
import time
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Callable

import pandas as pd
from sqlalchemy import bindparam, inspect, text

from src.companies.catalog import (
    CompanyCatalogEntry,
    CompanyCatalogUnavailableError,
    CompanyCatalogService,
)
from src.companies.gics_manual_mapping import (
    GICS_11_SECTORS,
    gics_sector_sort_key,
    resolve_gics_classification,
    resolve_gics_sector_name,
)
from src.platform.contracts import CompanyDirectoryAppliedFilters, CompanyDirectoryPage, CompanyDirectoryPagination, CompanyFiltersDTO, CompanyInfoDTO, CompanySectorFilterOption, CompanySearchResult, CompanySuggestionDTO, HealthSnapshot, KPIBundle, RefreshBatchSelection, RefreshStatusDTO, SectorCompanyMetricDTO, SectorDetailDTO, SectorDirectoryDTO, SectorDirectoryItemDTO, SectorSnapshotDTO, SubIndustryCountDTO, SectorYearOverviewDTO, StatementMatrix, StatementSummaryDTO, SummaryBlockDTO, TabularData
from src.refresh.jobs import (
    REFRESH_STAGE_ORDER,
    REFRESH_STAGE_WEIGHTS,
    RefreshJobRepository,
    ensure_refresh_runtime_tables_for_connection,
)
from src.refresh.service import HeadlessRefreshService
from src.financials.statement_summary import build_general_summary_blocks
from src.platform.db import build_engine
from src.financials.excel_exporter import (
    ExcelExporter,
    build_default_model_mapping,
    build_excel_filename,
    _is_annual_period,
    _period_sort_key,
)
from src.financials.excel_mapping import (
    SYSTEM_DEFAULT_PRESET_ID,
    VALID_MAPPING_OPERATIONS,
    ExcelMappingRepository,
    MappingValidationIssue,
    ModelMappingDefinition,
    ModelMappingEntry,
    ModelMappingSource,
)
from src.financials.kpi_engine import compute_all_kpis, compute_quarterly_kpis
from src.financials.query_layer import CVMQueryLayer
from src.companies.sector_taxonomy import canonical_sector_name, sector_slugify
from src.platform.settings import AppSettings, get_settings
from src.financials.utils import current_reporting_year_cap, normalize_account_name, now_iso_seconds

from src.financials.read_service_refresh_selection import BATCH_REFRESH_FAILED_STATES, BATCH_REFRESH_MAX_PAGE_SIZE, EXPORT_STATEMENT_TYPES, POPULARES_CVM_IDS, _parse_years, resolve_refresh_batch_selection, resolve_refresh_year_range


class ReadServiceCoverageMixin:
    def get_health_snapshot(
        self,
        start_year: int,
        end_year: int,
        *,
        force_refresh: bool = False,
    ) -> HealthSnapshot:
        resolved_start_year, resolved_end_year = self._resolve_refresh_range(
            start_year=start_year,
            end_year=end_year,
        )
        if force_refresh:
            self.invalidate_read_caches()
        else:
            self._ensure_read_cache_fresh()
            cached = self._health_snapshot_cache.get((resolved_start_year, resolved_end_year))
            if cached is not None:
                return cached
            persisted = self._load_base_health_persistent_cache(
                start_year=resolved_start_year,
                end_year=resolved_end_year,
            )
            if persisted is not None:
                self._health_snapshot_cache[(resolved_start_year, resolved_end_year)] = persisted
                return persisted

        payload = self._build_db_health_snapshot(
            start_year=resolved_start_year,
            end_year=resolved_end_year,
        )
        snapshot = HealthSnapshot.from_payload(payload)
        self._health_snapshot_cache[(resolved_start_year, resolved_end_year)] = snapshot
        self._write_base_health_persistent_cache(
            start_year=resolved_start_year,
            end_year=resolved_end_year,
            payload=payload,
        )
        return snapshot

    def list_refresh_status(self, cd_cvm: int | None = None) -> list[RefreshStatusDTO]:
        self.refresh_job_repository.ensure_schema()

        query = text(
            """
            SELECT
                cd_cvm,
                company_name,
                source_scope,
                job_id,
                stage,
                queue_position,
                last_attempt_at,
                last_success_at,
                last_status,
                last_error,
                last_start_year,
                last_end_year,
                last_rows_inserted,
                progress_current,
                progress_total,
                progress_message,
                started_at,
                heartbeat_at,
                finished_at,
                read_model_updated_at,
                updated_at
            FROM company_refresh_status
            WHERE (:cd_cvm IS NULL OR cd_cvm = :cd_cvm)
            ORDER BY company_name
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"cd_cvm": int(cd_cvm) if cd_cvm is not None else None}).mappings().all()
        cd_cvms = [int(row["cd_cvm"]) for row in rows]
        active_jobs = self._load_active_refresh_jobs_map(cd_cvms)
        readable_years_map = (
            self.query_layer.get_company_years_map(cd_cvms)
            if cd_cvms
            else {}
        )
        read_model_state_map = self._load_company_read_model_state_map(
            cd_cvms,
            precomputed_years_map=readable_years_map,
        )
        duration_profile = (
            self._estimate_refresh_duration_profile()
            if any(
                str(row.get("last_status") or "").strip().lower()
                in self.ACTIVE_REFRESH_STATUSES
                for row in rows
            ) or active_jobs
            else None
        )
        return [
            self._build_refresh_status_dto(
                row,
                duration_profile=duration_profile,
                active_job=active_jobs.get(int(row["cd_cvm"])),
                read_model_state=read_model_state_map.get(
                    int(row["cd_cvm"]),
                    {},
                ),
            )
            for row in rows
        ]

    def _load_company_read_model_state_map(
        self,
        cd_cvms: list[int] | tuple[int, ...],
        *,
        precomputed_years_map: dict[int, Any] | None = None,
    ) -> dict[int, dict[str, Any]]:
        unique_ids = sorted({int(cd_cvm) for cd_cvm in cd_cvms})
        if not unique_ids:
            return {}

        years_map = (
            precomputed_years_map
            if precomputed_years_map is not None
            else self.query_layer.get_company_years_map(unique_ids)
        )
        projection_updated_at: dict[int, str] = {}
        company_updated_at: dict[int, str] = {}

        with self.engine.connect() as conn:
            if inspect(conn).has_table("company_refresh_status"):
                status_columns = {
                    str(column.get("name") or "").lower()
                    for column in inspect(conn).get_columns("company_refresh_status")
                }
                if "read_model_updated_at" in status_columns:
                    rows = conn.execute(
                        text(
                            """
                            SELECT cd_cvm, read_model_updated_at
                            FROM company_refresh_status
                            WHERE cd_cvm IN :cd_cvms
                            """
                        ).bindparams(bindparam("cd_cvms", expanding=True)),
                        {"cd_cvms": unique_ids},
                    ).mappings().all()
                    projection_updated_at = {
                        int(row["cd_cvm"]): str(row["read_model_updated_at"])
                        for row in rows
                        if row.get("read_model_updated_at") is not None
                    }
            if inspect(conn).has_table("companies"):
                company_rows = conn.execute(
                    text(
                        """
                        SELECT cd_cvm, updated_at
                        FROM companies
                        WHERE cd_cvm IN :cd_cvms
                        """
                    ).bindparams(bindparam("cd_cvms", expanding=True)),
                    {"cd_cvms": unique_ids},
                ).mappings().all()
                company_updated_at = {
                    int(row["cd_cvm"]): str(row["updated_at"])
                    for row in company_rows
                    if row.get("updated_at") is not None
                }

        state_map: dict[int, dict[str, Any]] = {}
        for cd_cvm in unique_ids:
            readable_years = tuple(
                sorted(int(year) for year in years_map.get(int(cd_cvm), ()))
            )
            has_readable_data = bool(readable_years)
            state_map[int(cd_cvm)] = {
                "has_readable_current_data": has_readable_data,
                "readable_years_count": len(readable_years),
                "latest_readable_year": (
                    int(readable_years[-1]) if readable_years else None
                ),
                "read_model_updated_at": (
                    projection_updated_at.get(int(cd_cvm))
                    or (
                        company_updated_at.get(int(cd_cvm))
                        if has_readable_data
                        else None
                    )
                ),
            }
        return state_map

    def _build_refresh_status_dto(
        self,
        row: dict[str, Any],
        *,
        duration_profile: dict[str, Any] | None,
        active_job: dict[str, Any] | None,
        read_model_state: dict[str, Any],
    ) -> RefreshStatusDTO:
        readable_years_count = int(
            read_model_state.get("readable_years_count") or 0
        )
        has_readable_current_data = bool(
            read_model_state.get("has_readable_current_data")
        )
        latest_readable_year = read_model_state.get("latest_readable_year")
        latest_attempt_outcome = self._normalize_refresh_status(row.get("last_status")) or None
        tracking_state = self._resolve_refresh_tracking_state(
            row,
            active_job=active_job,
            duration_profile=duration_profile,
            has_readable_current_data=has_readable_current_data,
        )
        estimate = self._estimate_refresh_runtime(
            row,
            duration_profile=duration_profile,
            active_job=active_job,
            tracking_state=tracking_state,
        )
        status_reason_code, status_reason_message = self._build_refresh_status_reason(
            row,
            tracking_state=tracking_state,
            active_job=active_job,
            has_readable_current_data=has_readable_current_data,
        )
        read_availability = self._build_read_availability_summary(
            has_readable_current_data=has_readable_current_data,
            readable_years_count=readable_years_count,
            latest_readable_year=(
                int(latest_readable_year)
                if latest_readable_year is not None
                else None
            ),
        )
        latest_attempt_reason = self._build_latest_attempt_reason(
            row,
            tracking_state=tracking_state,
            active_job=active_job,
            has_readable_current_data=has_readable_current_data,
        )
        freshness_summary = self._build_freshness_summary(
            row,
            tracking_state=tracking_state,
            has_readable_current_data=has_readable_current_data,
            status_reason_code=status_reason_code,
            status_reason_message=status_reason_message,
            latest_attempt_reason=latest_attempt_reason,
        )
        return RefreshStatusDTO(
            cd_cvm=int(row["cd_cvm"]),
            company_name=str(row["company_name"] or ""),
            source_scope=row.get("source_scope"),
            job_id=row.get("job_id"),
            stage=row.get("stage"),
            queue_position=(
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else None
            ),
            last_attempt_at=row.get("last_attempt_at"),
            last_success_at=row.get("last_success_at"),
            last_status=row.get("last_status"),
            last_error=row.get("last_error"),
            last_start_year=(
                int(row["last_start_year"])
                if row.get("last_start_year") is not None
                else None
            ),
            last_end_year=(
                int(row["last_end_year"])
                if row.get("last_end_year") is not None
                else None
            ),
            last_rows_inserted=(
                int(row["last_rows_inserted"])
                if row.get("last_rows_inserted") is not None
                else None
            ),
            progress_current=(
                int(row["progress_current"])
                if row.get("progress_current") is not None
                else None
            ),
            progress_total=(
                int(row["progress_total"])
                if row.get("progress_total") is not None
                else None
            ),
            progress_message=row.get("progress_message"),
            started_at=row.get("started_at"),
            heartbeat_at=row.get("heartbeat_at"),
            finished_at=row.get("finished_at"),
            updated_at=row.get("updated_at"),
            read_model_updated_at=(
                str(read_model_state["read_model_updated_at"])
                if read_model_state.get("read_model_updated_at") is not None
                else row.get("read_model_updated_at")
            ),
            estimated_progress_pct=estimate["estimated_progress_pct"],
            estimated_eta_seconds=estimate["estimated_eta_seconds"],
            estimated_total_seconds=estimate["estimated_total_seconds"],
            elapsed_seconds=estimate["elapsed_seconds"],
            estimated_completion_at=estimate["estimated_completion_at"],
            estimate_confidence=estimate["estimate_confidence"],
            tracking_state=tracking_state,
            progress_mode=estimate["progress_mode"],
            is_retry_allowed=self._is_refresh_retry_allowed(
                tracking_state=tracking_state,
                active_job=active_job,
            ),
            status_reason_code=status_reason_code,
            status_reason_message=status_reason_message,
            has_readable_current_data=has_readable_current_data,
            readable_years_count=int(readable_years_count or 0),
            latest_readable_year=(
                int(latest_readable_year)
                if latest_readable_year is not None
                else None
            ),
            latest_attempt_outcome=latest_attempt_outcome,
            latest_attempt_reason_code=latest_attempt_reason["code"],
            latest_attempt_reason_message=latest_attempt_reason["message"],
            latest_attempt_retryable=bool(latest_attempt_reason["retryable"]),
            read_availability_code=read_availability["code"],
            read_availability_message=read_availability["message"],
            freshness_summary_code=freshness_summary["code"],
            freshness_summary_message=freshness_summary["message"],
            freshness_summary_severity=freshness_summary["severity"],
            source_label=self._build_refresh_source_label(
                row.get("source_scope"),
                has_readable_current_data=has_readable_current_data,
            ),
        )


    def _build_db_health_snapshot(self, *, start_year: int, end_year: int) -> dict[str, Any]:
        active_rows = self._load_active_company_rows()
        years_scope = list(range(int(start_year), int(end_year) + 1))
        company_codes = [int(row["cd_cvm"]) for row in active_rows]
        complete_years_map = self._load_complete_annual_years_map(
            company_codes,
            start_year=start_year,
            end_year=end_year,
        )
        all_years_map = self.query_layer.get_company_years_map(company_codes)
        companies_with_historical_data = sum(
            1 for cd_cvm in company_codes if all_years_map.get(int(cd_cvm))
        )
        status_map = self._load_refresh_status_map(company_codes)
        any_local_cd_set = self._cd_cvms_with_any_financial_report_row(company_codes)
        companies_with_any_local_financial_report = sum(
            1 for cd_cvm in company_codes if cd_cvm in any_local_cd_set
        )
        companies_partial_local = sum(
            1
            for cd_cvm in company_codes
            if cd_cvm in any_local_cd_set and not all_years_map.get(int(cd_cvm))
        )
        companies_with_refresh_status_recorded = sum(
            1 for cd_cvm in company_codes if cd_cvm in status_map
        )
        companies_with_last_refresh_error = sum(
            1
            for cd_cvm in company_codes
            if self._normalize_refresh_status(
                status_map.get(cd_cvm, {}).get("last_status"),
            )
            in BATCH_REFRESH_FAILED_STATES
        )

        per_year_buckets = {
            int(year): {
                "year": int(year),
                "total_companies": int(len(active_rows)),
                "completed": 0,
            }
            for year in years_scope
        }
        company_rows: list[dict[str, Any]] = []
        leader_completed = 0
        companies_fully_updated = 0

        for row in active_rows:
            cd_cvm = int(row["cd_cvm"])
            completed_years = set(complete_years_map.get(cd_cvm, ()))
            years_completed = [year for year in years_scope if year in completed_years]
            years_missing = [year for year in years_scope if year not in completed_years]
            if not years_missing:
                companies_fully_updated += 1
            leader_completed = max(leader_completed, len(years_completed))
            for year in years_completed:
                per_year_buckets[int(year)]["completed"] += 1
            company_rows.append(
                {
                    "cd_cvm": cd_cvm,
                    "company_name": str(row["company_name"]),
                    "coverage_rank": (
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    "years_completed": years_completed,
                    "years_missing": years_missing,
                    "completed_years_count": len(years_completed),
                    "missing_years_count": len(years_missing),
                    "last_status": status_map.get(cd_cvm, {}).get("last_status"),
                }
            )

        total_cells = int(len(active_rows) * len(years_scope))
        completed_cells = int(sum(bucket["completed"] for bucket in per_year_buckets.values()))
        missing_cells = max(0, total_cells - completed_cells)
        pct = (100.0 * completed_cells / total_cells) if total_cells else 0.0

        throughput = self._estimate_refresh_throughput()
        throughput_per_hour = throughput.get("per_hour")
        remaining_companies = sum(
            1 for row in company_rows if int(row["missing_years_count"]) > 0
        )
        eta_hours = (
            float(remaining_companies) / float(throughput_per_hour)
            if throughput_per_hour
            else None
        )

        per_year = []
        for year in years_scope:
            completed = int(per_year_buckets[int(year)]["completed"])
            total_companies = int(per_year_buckets[int(year)]["total_companies"])
            missing = max(0, total_companies - completed)
            per_year.append(
                {
                    "year": int(year),
                    "total_companies": total_companies,
                    "completed": completed,
                    "missing": missing,
                    "pct": (100.0 * completed / total_companies) if total_companies else 0.0,
                    "eta_hours": (
                        float(missing) / float(throughput_per_hour)
                        if throughput_per_hour
                        else None
                    ),
                }
            )

        ranked_backlog = self._build_ranked_backlog(
            limit=80,
            start_year=start_year,
            end_year=end_year,
            complete_years_map=complete_years_map,
            refresh_status_map=status_map,
        )

        prioritized_companies: list[dict[str, Any]] = []
        for row in ranked_backlog["items"]:
            gap_to_leader = max(
                0,
                int(leader_completed) - int(row["completed_years_count"]),
            )
            prioritized_companies.append(
                {
                    "cd_cvm": int(row["cd_cvm"]),
                    "company_name": str(row["company_name"]),
                    "coverage_rank": (
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    "last_status": (
                        str(row["last_status"])
                        if row.get("last_status") is not None
                        else None
                    ),
                    "excluded_from_queue": bool(row["excluded_from_queue"]),
                    "risk_level": str(row["risk_level"]),
                    "priority_score": int(row["priority_score"]),
                    "missing_years_count": int(row["missing_years_count"]),
                    "gap_to_leader_years": int(gap_to_leader),
                    "years_missing": list(int(year) for year in row["years_missing"]),
                    "recommended_action": str(row["recommended_action"]),
                    "reason": str(row["reason"]),
                }
            )

        throughput_confidence = str(throughput.get("confidence") or "low")
        if throughput_per_hour:
            throughput_score = {
                "high": 100.0,
                "medium": 75.0,
                "low": 55.0,
            }.get(throughput_confidence, 55.0)
        else:
            throughput_score = {
                "high": 70.0,
                "medium": 50.0,
                "low": 30.0,
            }.get(throughput_confidence, 30.0)

        latest_year_pct = float(per_year[-1]["pct"]) if per_year else pct
        health_score = max(
            0.0,
            min(
                100.0,
                (0.6 * float(pct))
                + (0.2 * float(latest_year_pct))
                + (0.2 * float(throughput_score)),
            ),
        )

        return {
            "generated_at": now_iso_seconds(),
            "start_year": int(start_year),
            "end_year": int(end_year),
            "scope": "database_backed",
            "required_package": list(self.REQUIRED_PACKAGE_STATEMENTS),
            "ranked_backlog": dict(ranked_backlog["summary"]),
            "active_companies": int(len(active_rows)),
            "company_inventory": {
                "total_companies": int(len(active_rows)),
                "companies_with_historical_data": int(companies_with_historical_data),
                "companies_without_historical_data": max(
                    0,
                    int(len(active_rows)) - int(companies_with_historical_data),
                ),
                "companies_with_any_local_financial_report": int(
                    companies_with_any_local_financial_report
                ),
                "companies_partial_local": int(companies_partial_local),
                "companies_fully_updated": int(companies_fully_updated),
                "companies_with_refresh_status_recorded": int(
                    companies_with_refresh_status_recorded
                ),
                "companies_with_last_refresh_error": int(companies_with_last_refresh_error),
            },
            "global": {
                "total_cells": int(total_cells),
                "completed_cells": int(completed_cells),
                "missing_cells": int(missing_cells),
                "pct": float(pct),
                "active_universe": int(len(active_rows)),
                "companies_with_historical_data": int(companies_with_historical_data),
                "remaining_companies": int(remaining_companies),
                "eta_hours": eta_hours,
            },
            "throughput": throughput,
            "per_year": per_year,
            "health_score": round(float(health_score), 2),
            "health_status": self._health_status_from_score(health_score),
            "prioritized_companies": prioritized_companies,
        }

    def _build_ranked_backlog(
        self,
        *,
        limit: int,
        start_year: int,
        end_year: int,
        complete_years_map: dict[int, tuple[int, ...]] | None = None,
        refresh_status_map: dict[int, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ranked_rows = self._load_ranked_company_rows(limit)
        company_codes = [int(row["cd_cvm"]) for row in ranked_rows]
        years_scope = list(range(int(start_year), int(end_year) + 1))
        complete_map = complete_years_map or self._load_complete_annual_years_map(
            company_codes,
            start_year=start_year,
            end_year=end_year,
        )
        status_map = refresh_status_map or self._load_refresh_status_map(company_codes)
        leader_completed = max(
            (len(complete_map.get(code, ())) for code in company_codes),
            default=0,
        )

        items: list[dict[str, Any]] = []
        companies_with_some_data = 0
        fully_covered_companies = 0
        queue_eligible_companies = 0
        queued_companies = 0
        no_data_excluded_companies = 0

        for row in ranked_rows:
            cd_cvm = int(row["cd_cvm"])
            coverage_rank = (
                int(row["coverage_rank"])
                if row.get("coverage_rank") is not None
                else None
            )
            completed_years = set(int(year) for year in complete_map.get(cd_cvm, ()))
            years_completed = [year for year in years_scope if year in completed_years]
            years_missing = [year for year in years_scope if year not in completed_years]
            status_row = status_map.get(cd_cvm, {})
            last_status = (
                str(status_row.get("last_status")).strip().lower()
                if status_row.get("last_status") is not None
                else None
            )
            excluded_from_queue = last_status == "no_data"
            already_queued = self._is_recently_queued(
                status_row,
                window=timedelta(hours=self.PRIORITIZED_BACKLOG_STALE_HOURS),
            )

            if years_completed:
                companies_with_some_data += 1
            if not years_missing:
                fully_covered_companies += 1
            elif excluded_from_queue:
                no_data_excluded_companies += 1
            elif already_queued:
                queued_companies += 1
            else:
                queue_eligible_companies += 1

            if not years_missing:
                recommended_action = "already_complete"
                reason = "Cobertura anual completa na janela solicitada."
            elif excluded_from_queue:
                recommended_action = "skip_no_data"
                reason = "Empresa marcada como no_data; backlog automatico nao reenfileira."
            elif already_queued:
                recommended_action = "await_existing_queue"
                reason = "Ja existe refresh recente em fila para esta empresa."
            elif years_completed:
                recommended_action = "queue_historical_backfill"
                reason = "Empresa com dados parciais; falta backfill anual dos anos ausentes."
            else:
                recommended_action = "queue_historical_backfill"
                reason = "Empresa sem cobertura anual na janela; elegivel para ingestao historica."

            gap_to_leader = max(0, leader_completed - len(years_completed))
            items.append(
                {
                    "cd_cvm": cd_cvm,
                    "company_name": str(row["company_name"]),
                    "coverage_rank": coverage_rank,
                    "last_status": last_status,
                    "excluded_from_queue": excluded_from_queue,
                    "completed_years_count": len(years_completed),
                    "missing_years_count": len(years_missing),
                    "years_missing": years_missing,
                    "priority_score": self._priority_score(
                        coverage_rank=coverage_rank,
                        missing_years_count=len(years_missing),
                        gap_to_leader_years=gap_to_leader,
                    ),
                    "risk_level": self._risk_level(
                        coverage_rank=coverage_rank,
                        missing_years_count=len(years_missing),
                        excluded_from_queue=excluded_from_queue,
                    ),
                    "recommended_action": recommended_action,
                    "reason": reason,
                }
            )

        return {
            "summary": {
                "total_ranked": int(len(ranked_rows)),
                "companies_with_some_data": int(companies_with_some_data),
                "fully_covered_companies": int(fully_covered_companies),
                "queue_eligible_companies": int(queue_eligible_companies),
                "already_queued_companies": int(queued_companies),
                "no_data_excluded_companies": int(no_data_excluded_companies),
            },
            "items": items,
        }


    def _resolve_refresh_range(
        self,
        *,
        start_year: int,
        end_year: int | None,
    ) -> tuple[int, int]:
        from src.financials import read_service as read_service_module  # noqa: PLC0415

        reporting_year_cap = getattr(
            read_service_module,
            "current_reporting_year_cap",
            current_reporting_year_cap,
        )
        resolved_start_year = int(start_year)
        resolved_end_year = (
            int(end_year)
            if end_year is not None
            else max(2010, reporting_year_cap())
        )
        if resolved_start_year > resolved_end_year:
            raise ValueError("start_year must be <= end_year")
        return resolved_start_year, resolved_end_year

    def _load_active_company_rows(self) -> list[dict[str, Any]]:
        local_rows = self._load_local_active_company_rows()
        if len(local_rows) >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES:
            return local_rows

        local_by_code = {int(row["cd_cvm"]): row for row in local_rows}
        try:
            entries = [entry for entry in self.company_catalog.list_entries() if entry.is_active]
        except CompanyCatalogUnavailableError:
            return local_rows
        if not entries:
            return local_rows

        rows: list[dict[str, Any]] = []
        for entry in entries:
            local = local_by_code.get(int(entry.cd_cvm), {})
            rows.append(
                {
                    "cd_cvm": int(entry.cd_cvm),
                    "company_name": str(local.get("company_name") or entry.company_name),
                    "coverage_rank": local.get("coverage_rank"),
                }
            )
        rows.sort(
            key=lambda row: (
                1 if row.get("coverage_rank") is None else 0,
                int(row.get("coverage_rank") or 999999),
                str(row.get("company_name") or "").upper(),
            )
        )
        return rows

    def _load_local_company_universe_results(self, *, include_years: bool = True) -> list[CompanySearchResult]:
        if include_years:
            rows_df, _ = self.query_layer.get_companies_directory_page(
                search="",
                sector_name=None,
                page=1,
                page_size=None,
            )
        else:
            rows_df = self.query_layer.get_companies_directory_light()
        if include_years and not rows_df.empty:
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df = rows_df.copy()
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        return self._build_company_results(rows_df)

    def _load_local_active_company_rows(self) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT cd_cvm, company_name, coverage_rank
            FROM companies
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY
                CASE WHEN coverage_rank IS NULL THEN 1 ELSE 0 END,
                coverage_rank ASC,
                company_name ASC
            """
        )
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(query).mappings().all()]

    def _load_ranked_company_rows(self, limit: int) -> list[dict[str, Any]]:
        query = text(
            """
            SELECT cd_cvm, company_name, coverage_rank
            FROM companies
            WHERE COALESCE(is_active, 1) = 1
              AND coverage_rank IS NOT NULL
            ORDER BY coverage_rank ASC, company_name ASC
            LIMIT :limit
            """
        )
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(query, {"limit": int(limit)}).mappings().all()
            ]

    def _load_complete_annual_years_map(
        self,
        cd_cvms: list[int],
        *,
        start_year: int,
        end_year: int,
    ) -> dict[int, tuple[int, ...]]:
        if not cd_cvms or not inspect(self.engine).has_table("financial_reports"):
            return {}

        query = text(
            """
            SELECT "CD_CVM" AS cd_cvm, "REPORT_YEAR" AS report_year
            FROM financial_reports
            WHERE "CD_CVM" IN :cd_cvms
              AND "REPORT_YEAR" BETWEEN :start_year AND :end_year
              AND "STATEMENT_TYPE" IN :statement_types
              AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT)
            GROUP BY "CD_CVM", "REPORT_YEAR"
            HAVING COUNT(DISTINCT "STATEMENT_TYPE") >= :required_count
            ORDER BY "CD_CVM", "REPORT_YEAR"
            """
        ).bindparams(
            bindparam("cd_cvms", expanding=True),
            bindparam("statement_types", expanding=True),
        )

        params = {
            "cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms],
            "start_year": int(start_year),
            "end_year": int(end_year),
            "statement_types": list(self.REQUIRED_PACKAGE_STATEMENTS),
            "required_count": len(self.REQUIRED_PACKAGE_STATEMENTS),
        }
        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        years_map: dict[int, list[int]] = defaultdict(list)
        for row in rows:
            years_map[int(row["cd_cvm"])].append(int(row["report_year"]))
        return {
            int(cd_cvm): tuple(sorted(set(years)))
            for cd_cvm, years in years_map.items()
        }

    def _cd_cvms_with_any_financial_report_row(self, cd_cvms: list[int]) -> set[int]:
        """Companies with at least one row in financial_reports (any period / tipo)."""
        if not cd_cvms:
            return set()
        if not inspect(self.engine).has_table("financial_reports"):
            return set()
        unique_ids = sorted({int(cd_cvm) for cd_cvm in cd_cvms})
        query = text(
            """
            SELECT DISTINCT "CD_CVM" AS cd_cvm
            FROM financial_reports
            WHERE "CD_CVM" IN :cd_cvms
            """
        ).bindparams(bindparam("cd_cvms", expanding=True))
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"cd_cvms": unique_ids}).mappings().all()
        return {int(row["cd_cvm"]) for row in rows}

    @staticmethod
    def _normalize_refresh_status(value: Any) -> str:
        return str(value or "").strip().lower()

    def _resolve_refresh_tracking_state(
        self,
        row: dict[str, Any],
        *,
        active_job: dict[str, Any] | None,
        duration_profile: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> str:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        if last_status in {"success", "no_data", "error"}:
            return last_status

        active_state = (
            self._normalize_refresh_status(active_job.get("state"))
            if active_job is not None
            else ""
        )
        if active_state in self.ACTIVE_REFRESH_STATUSES:
            if self._is_refresh_tracking_stalled(
                row,
                active_job=active_job,
                duration_profile=duration_profile,
                active_state=active_state,
            ):
                return "stalled"
            return active_state

        if last_status in self.ACTIVE_REFRESH_STATUSES:
            return "stalled"

        return "success" if has_readable_current_data else "idle"

    def _is_refresh_tracking_stalled(
        self,
        row: dict[str, Any],
        *,
        active_job: dict[str, Any] | None,
        duration_profile: dict[str, Any] | None,
        active_state: str,
    ) -> bool:
        now = datetime.now(timezone.utc)
        if active_state == "running":
            activity_at = (
                self._parse_timestamp(active_job.get("heartbeat_at"))
                or self._parse_timestamp(active_job.get("started_at"))
                or self._parse_timestamp(row.get("heartbeat_at"))
                or self._parse_timestamp(row.get("started_at"))
                or self._parse_timestamp(active_job.get("requested_at"))
                or self._parse_timestamp(row.get("last_attempt_at"))
            )
            if activity_at is None:
                return False
            return (
                now - activity_at
            ).total_seconds() >= self.REFRESH_RUNNING_STALL_SECONDS

        if active_state == "queued":
            requested_at = (
                self._parse_timestamp(active_job.get("requested_at"))
                or self._parse_timestamp(row.get("last_attempt_at"))
            )
            if requested_at is None:
                return False
            queue_position = (
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else 0
            )
            typical_total_seconds = int(
                round(
                    float(
                        (duration_profile or {}).get("typical_total_seconds")
                        or self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS
                    )
                )
            )
            threshold_seconds = max(
                self.REFRESH_QUEUE_STALL_SECONDS,
                typical_total_seconds
                + 120
                + (min(max(queue_position, 0), 5) * self.REFRESH_QUEUE_POSITION_STEP_SECONDS),
            )
            return (
                now - requested_at
            ).total_seconds() >= threshold_seconds

        return False

    @staticmethod
    def _build_read_availability_summary(
        *,
        has_readable_current_data: bool,
        readable_years_count: int,
        latest_readable_year: int | None,
    ) -> dict[str, str]:
        if has_readable_current_data:
            if latest_readable_year is not None:
                return {
                    "code": "readable_history_available",
                    "message": (
                        f"Leitura anual disponivel ate {int(latest_readable_year)}."
                    ),
                }
            return {
                "code": "readable_history_available",
                "message": "Leitura anual disponivel nesta pagina.",
            }

        return {
            "code": "no_readable_annual_history",
            "message": (
                "Ainda nao ha historico anual legivel para esta companhia."
            ),
        }

    def _build_latest_attempt_reason(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> dict[str, Any]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        progress_message = self._clean_optional_text(row.get("progress_message"))
        last_error = self._clean_optional_text(row.get("last_error"))
        normalized_progress_message = str(progress_message or "").lower()
        normalized_last_error = str(last_error or "").lower()

        if tracking_state == "queued":
            return {
                "code": "refresh_queued",
                "message": (
                    "Solicitacao recebida e aguardando processamento interno."
                ),
                "retryable": False,
            }

        if tracking_state == "running":
            return {
                "code": "refresh_running",
                "message": (
                    "Os demonstrativos desta companhia estao sendo atualizados agora."
                ),
                "retryable": False,
            }

        if tracking_state == "stalled":
            if active_job is None and last_status in self.ACTIVE_REFRESH_STATUSES:
                return {
                    "code": "refresh_tracking_lost",
                    "message": (
                        "A ultima solicitacao nao aparece mais como ativa."
                    ),
                    "retryable": True,
                }
            return {
                "code": "refresh_stalled",
                "message": (
                    "A solicitacao esta acima do esperado e sem sinais recentes de progresso."
                ),
                "retryable": active_job is None,
            }

        if last_status == "success":
            if "ja atualizada" in normalized_progress_message:
                return {
                    "code": "already_current",
                    "message": (
                        "Esta empresa ja estava atualizada para a janela padrao."
                    ),
                    "retryable": False,
                }
            if has_readable_current_data:
                return {
                    "code": "refresh_completed",
                    "message": "Dados prontos para leitura nesta pagina.",
                    "retryable": False,
                }
            return {
                "code": "refresh_completed_without_readable_data",
                "message": (
                    "A ultima atualizacao terminou, mas a leitura anual ainda nao ficou disponivel."
                ),
                "retryable": False,
            }

        if last_status == "no_data":
            if has_readable_current_data:
                return {
                    "code": "no_new_financial_history",
                    "message": (
                        "A ultima tentativa nao encontrou novos demonstrativos."
                    ),
                    "retryable": True,
                }
            return {
                "code": "no_annual_history",
                "message": (
                    "Nenhuma serie anual legivel foi encontrada para esta companhia."
                ),
                "retryable": True,
            }

        if last_status == "error":
            if "expirou" in normalized_progress_message:
                return {
                    "code": "refresh_expired",
                    "message": (
                        "A solicitacao expirou antes de terminar."
                    ),
                    "retryable": True,
                }
            if "no financial rows found" in normalized_last_error:
                return {
                    "code": "no_annual_history",
                    "message": (
                        "Nenhuma serie anual legivel foi encontrada para esta companhia."
                    ),
                    "retryable": True,
                }
            return {
                "code": "refresh_failed_retryable",
                "message": (
                    "Nao foi possivel concluir a atualizacao desta empresa agora."
                ),
                "retryable": True,
            }

        if has_readable_current_data:
            return {
                "code": "local_data_ready",
                "message": "Leitura local pronta para consulta.",
                "retryable": False,
            }

        return {
            "code": "no_local_history_yet",
            "message": (
                "Esta empresa ainda nao tem historico anual processado na base local."
            ),
            "retryable": False,
        }

    def _build_freshness_summary(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        has_readable_current_data: bool,
        status_reason_code: str,
        status_reason_message: str,
        latest_attempt_reason: dict[str, Any],
    ) -> dict[str, str]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        attempt_code = str(latest_attempt_reason.get("code") or "")

        if tracking_state in {"queued", "running"}:
            return {
                "code": status_reason_code,
                "message": status_reason_message,
                "severity": "info",
            }

        if tracking_state == "stalled":
            if has_readable_current_data:
                return {
                    "code": "mixed_refresh_stalled_readable",
                    "message": (
                        "A leitura atual continua disponivel, mas a ultima solicitacao esta sem sinais recentes."
                    ),
                    "severity": "warning",
                }
            return {
                "code": "refresh_stalled_no_readable",
                "message": (
                    "A solicitacao esta sem sinais recentes e ainda nao ha leitura anual disponivel."
                ),
                "severity": "warning",
            }

        if last_status == "success":
            if attempt_code == "already_current":
                return {
                    "code": "already_current",
                    "message": (
                        "A leitura local ja estava atualizada para a janela padrao."
                    ),
                    "severity": "success",
                }
            if has_readable_current_data:
                return {
                    "code": "refresh_completed_readable",
                    "message": "Dados prontos para leitura nesta pagina.",
                    "severity": "success",
                }
            return {
                "code": "refresh_completed_no_readable",
                "message": (
                    "A atualizacao terminou, mas a leitura anual ainda nao esta disponivel."
                ),
                "severity": "warning",
            }

        if last_status == "no_data":
            if has_readable_current_data:
                return {
                    "code": "mixed_no_new_data_readable",
                    "message": (
                        "A ultima tentativa nao encontrou novos demonstrativos; a leitura atual continua disponivel."
                    ),
                    "severity": "info",
                }
            return {
                "code": "no_annual_history",
                "message": (
                    "Nenhuma serie anual legivel foi encontrada para esta companhia."
                ),
                "severity": "info",
            }

        if last_status == "error":
            if has_readable_current_data:
                return {
                    "code": "mixed_retryable_error_readable",
                    "message": (
                        "A leitura atual continua disponivel, mas a ultima atualizacao falhou e pode ser tentada novamente."
                    ),
                    "severity": "warning",
                }
            return {
                "code": "refresh_failed_retryable",
                "message": (
                    "A ultima atualizacao falhou e ainda nao ha leitura anual disponivel."
                ),
                "severity": "error",
            }

        if has_readable_current_data:
            return {
                "code": "readable_history_available",
                "message": "Leitura local pronta para consulta.",
                "severity": "success",
            }

        return {
            "code": "no_readable_annual_history",
            "message": (
                "Ainda nao ha historico anual legivel para esta companhia."
            ),
            "severity": "info",
        }

    def _build_refresh_status_reason(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
        has_readable_current_data: bool,
    ) -> tuple[str, str]:
        last_status = self._normalize_refresh_status(row.get("last_status"))
        progress_message = self._clean_optional_text(row.get("progress_message"))
        last_error = self._clean_optional_text(row.get("last_error"))
        normalized_progress_message = str(progress_message or "").lower()
        normalized_last_error = str(last_error or "").lower()

        if tracking_state == "queued":
            return (
                "refresh_queued",
                "Solicitacao recebida e aguardando processamento interno.",
            )

        if tracking_state == "running":
            return (
                "refresh_running",
                "Os demonstrativos desta companhia estao sendo atualizados agora.",
            )

        if tracking_state == "stalled":
            if active_job is None and last_status in self.ACTIVE_REFRESH_STATUSES:
                return (
                    "refresh_tracking_lost",
                    "A ultima solicitacao nao aparece mais como ativa. Atualize o status ou tente novamente.",
                )
            return (
                "refresh_stalled",
                "A solicitacao esta acima do esperado e sem sinais recentes de progresso.",
            )

        if last_status == "success":
            if "ja atualizada" in normalized_progress_message:
                return (
                    "already_current",
                    "Esta empresa ja estava atualizada para a janela padrao.",
                )
            if has_readable_current_data:
                return (
                    "refresh_completed",
                    "Dados prontos para leitura nesta pagina.",
                )
            return ("refresh_completed", "Processamento concluido.")

        if last_status == "no_data":
            if has_readable_current_data:
                return (
                    "no_new_financial_history",
                    "A ultima tentativa nao encontrou novos demonstrativos, mas a leitura atual continua disponivel.",
                )
            return (
                "no_financial_history_found",
                "Ainda nao foi encontrada uma serie anual suficiente para liberar esta leitura.",
            )

        if last_status == "error":
            if "expirou" in normalized_progress_message:
                return (
                    "refresh_stalled",
                    "A solicitacao expirou antes de terminar. Voce pode tentar novamente.",
                )
            if "no financial rows found" in normalized_last_error:
                return (
                    "no_financial_history_found",
                    "Nenhuma serie anual utilizavel foi encontrada para esta empresa.",
                )
            return (
                "refresh_failed",
                "Nao foi possivel concluir a atualizacao desta empresa agora.",
            )

        if has_readable_current_data:
            return ("local_data_ready", "Leitura local pronta para consulta.")

        return (
            "no_local_history_yet",
            "Esta empresa ainda nao tem historico anual processado na base local.",
        )

    @staticmethod
    def _build_refresh_source_label(
        source_scope: Any,
        *,
        has_readable_current_data: bool,
    ) -> str:
        normalized_scope = str(source_scope or "").strip().lower()
        if normalized_scope == "local":
            return (
                "Base local materializada"
                if has_readable_current_data
                else "Base local"
            )
        if normalized_scope == "on_demand":
            return "Solicitacao on-demand"
        if normalized_scope == "on_demand_bootstrap":
            return "Primeira carga on-demand"
        if normalized_scope == "ranked_backfill":
            return "Backfill historico"
        return "Leitura CVM processada"

    @staticmethod
    def _is_refresh_retry_allowed(
        *,
        tracking_state: str,
        active_job: dict[str, Any] | None,
    ) -> bool:
        if tracking_state in {"no_data", "error"}:
            return True
        return tracking_state == "stalled" and active_job is None

    def _load_refresh_status_map(
        self,
        cd_cvms: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        if not inspect(self.engine).has_table("company_refresh_status"):
            return {}

        if cd_cvms:
            query = text(
                """
                SELECT *
                FROM company_refresh_status
                WHERE cd_cvm IN :cd_cvms
                """
            ).bindparams(bindparam("cd_cvms", expanding=True))
            params = {"cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms]}
        else:
            query = text("SELECT * FROM company_refresh_status")
            params = {}

        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()
        return {int(row["cd_cvm"]): dict(row) for row in rows}

    def _load_active_refresh_jobs_map(
        self,
        cd_cvms: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        if not inspect(self.engine).has_table("refresh_jobs"):
            return {}

        if cd_cvms:
            query = text(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state IN ('queued', 'running')
                  AND cd_cvm IN :cd_cvms
                ORDER BY
                    CASE WHEN state = 'running' THEN 0 ELSE 1 END,
                    requested_at ASC,
                    id ASC
                """
            ).bindparams(bindparam("cd_cvms", expanding=True))
            params = {"cd_cvms": [int(cd_cvm) for cd_cvm in cd_cvms]}
        else:
            query = text(
                """
                SELECT *
                FROM refresh_jobs
                WHERE state IN ('queued', 'running')
                ORDER BY
                    CASE WHEN state = 'running' THEN 0 ELSE 1 END,
                    requested_at ASC,
                    id ASC
                """
            )
            params = {}

        with self.engine.connect() as conn:
            rows = conn.execute(query, params).mappings().all()

        active_jobs: dict[int, dict[str, Any]] = {}
        for row in rows:
            cd_cvm = int(row["cd_cvm"])
            if cd_cvm not in active_jobs:
                active_jobs[cd_cvm] = dict(row)
        return active_jobs

    def _default_refresh_year_span(self) -> int:
        start_year, end_year = self._resolve_refresh_range(
            start_year=2010,
            end_year=None,
        )
        return max(1, int(end_year) - int(start_year) + 1)

    def _refresh_year_span(self, row: dict[str, Any]) -> int:
        start_year = row.get("last_start_year")
        end_year = row.get("last_end_year")
        if start_year is None or end_year is None:
            return self._default_refresh_year_span()
        try:
            year_span = int(end_year) - int(start_year) + 1
        except (TypeError, ValueError):
            return self._default_refresh_year_span()
        return max(1, year_span)

    def _estimate_refresh_duration_profile(self) -> dict[str, Any]:
        typical_year_span = float(self._default_refresh_year_span())
        year_span_samples = 0

        if inspect(self.engine).has_table("company_refresh_status"):
            query = text(
                """
                SELECT last_start_year, last_end_year
                FROM company_refresh_status
                WHERE last_status = 'success'
                  AND last_start_year IS NOT NULL
                  AND last_end_year IS NOT NULL
                ORDER BY last_success_at DESC
                LIMIT 200
                """
            )
            with self.engine.connect() as conn:
                rows = conn.execute(query).mappings().all()

            year_spans = []
            for row in rows:
                try:
                    year_span = int(row["last_end_year"]) - int(row["last_start_year"]) + 1
                except (TypeError, ValueError):
                    continue
                if year_span > 0:
                    year_spans.append(year_span)

            if year_spans:
                typical_year_span = float(median(year_spans))
                year_span_samples = len(year_spans)

        throughput = self._estimate_refresh_throughput()
        per_hour = throughput.get("per_hour")
        typical_total_seconds = (
            max(60.0, 3600.0 / float(per_hour))
            if per_hour
            else float(self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS)
        )

        return {
            "typical_year_span": max(1.0, typical_year_span),
            "typical_total_seconds": float(typical_total_seconds),
            "sample_size": max(
                int(throughput.get("sample_size") or 0),
                int(year_span_samples),
            ),
            "confidence": str(throughput.get("confidence") or "low"),
        }

    def _estimate_refresh_runtime(
        self,
        row: dict[str, Any],
        *,
        duration_profile: dict[str, Any] | None,
        active_job: dict[str, Any] | None,
        tracking_state: str,
    ) -> dict[str, Any]:
        active_state = (
            self._normalize_refresh_status(active_job.get("state"))
            if active_job is not None
            else self._normalize_refresh_status(row.get("last_status"))
        )
        if tracking_state not in {"queued", "running", "stalled"}:
            return {
                "estimated_progress_pct": None,
                "estimated_eta_seconds": None,
                "estimated_total_seconds": None,
                "elapsed_seconds": None,
                "estimated_completion_at": None,
                "estimate_confidence": None,
                "progress_mode": "none",
            }

        real_progress_estimate = self._estimate_refresh_runtime_from_real_progress(
            row,
            tracking_state=tracking_state,
        )
        if real_progress_estimate is not None:
            return real_progress_estimate

        attempted_at = (
            self._parse_timestamp(row.get("started_at"))
            or self._parse_timestamp(row.get("last_attempt_at"))
            or (
                self._parse_timestamp(active_job.get("requested_at"))
                if active_job is not None
                else None
            )
        )
        now = datetime.now(timezone.utc)
        elapsed_seconds = (
            max(0, int(round((now - attempted_at).total_seconds())))
            if attempted_at is not None
            else None
        )

        if active_state == "queued" and tracking_state != "running":
            queue_position = (
                int(row["queue_position"])
                if row.get("queue_position") is not None
                else 0
            )
            estimated_progress_pct = min(
                32.0,
                self.REFRESH_QUEUE_PROGRESS_BASE
                + (min(max(queue_position, 0), 4) * self.REFRESH_QUEUE_PROGRESS_STEP),
            )
            if tracking_state == "stalled":
                estimated_progress_pct = max(estimated_progress_pct, 22.0)
            return {
                "estimated_progress_pct": round(float(estimated_progress_pct), 1),
                "estimated_eta_seconds": None,
                "estimated_total_seconds": None,
                "elapsed_seconds": elapsed_seconds,
                "estimated_completion_at": None,
                "estimate_confidence": "low",
                "progress_mode": "stalled" if tracking_state == "stalled" else "queue",
            }

        profile = duration_profile or self._estimate_refresh_duration_profile()
        typical_year_span = max(
            1.0,
            float(profile.get("typical_year_span") or self._default_refresh_year_span()),
        )
        current_year_span = float(self._refresh_year_span(row))
        typical_total_seconds = max(
            60.0,
            float(
                profile.get("typical_total_seconds")
                or self.REFRESH_ESTIMATE_DEFAULT_TOTAL_SECONDS
            ),
        )
        estimated_total_seconds = max(
            60,
            int(round(typical_total_seconds * (current_year_span / typical_year_span))),
        )
        estimated_completion_at = (
            (
                attempted_at + timedelta(seconds=estimated_total_seconds)
                if attempted_at is not None
                else now + timedelta(seconds=estimated_total_seconds)
            )
            .replace(microsecond=0)
            .isoformat()
        )

        if elapsed_seconds is None:
            estimated_progress_pct = self.REFRESH_ESTIMATE_PROGRESS_FLOOR
            estimated_eta_seconds = estimated_total_seconds
        else:
            ratio = float(elapsed_seconds) / float(estimated_total_seconds)
            estimated_progress_pct = self.REFRESH_ESTIMATE_PROGRESS_FLOOR + (
                min(1.0, ratio)
                * (
                    self.REFRESH_ESTIMATE_PROGRESS_CEILING
                    - self.REFRESH_ESTIMATE_PROGRESS_FLOOR
                )
            )
            if ratio > 1.0:
                estimated_progress_pct = min(
                    self.REFRESH_RUNNING_PROGRESS_CAP,
                    estimated_progress_pct + min(6.0, (ratio - 1.0) * 10.0),
                )
            estimated_eta_seconds = max(0, estimated_total_seconds - elapsed_seconds)

        if active_state == "running":
            estimated_progress_pct = max(estimated_progress_pct, 28.0)

        if tracking_state == "stalled":
            return {
                "estimated_progress_pct": round(float(estimated_progress_pct), 1),
                "estimated_eta_seconds": None,
                "estimated_total_seconds": int(estimated_total_seconds),
                "elapsed_seconds": elapsed_seconds,
                "estimated_completion_at": None,
                "estimate_confidence": str(profile.get("confidence") or "low"),
                "progress_mode": "stalled",
            }

        return {
            "estimated_progress_pct": round(float(estimated_progress_pct), 1),
            "estimated_eta_seconds": int(estimated_eta_seconds),
            "estimated_total_seconds": int(estimated_total_seconds),
            "elapsed_seconds": elapsed_seconds,
            "estimated_completion_at": estimated_completion_at,
            "estimate_confidence": str(profile.get("confidence") or "low"),
            "progress_mode": "time_window",
        }

    def _estimate_refresh_runtime_from_real_progress(
        self,
        row: dict[str, Any],
        *,
        tracking_state: str,
    ) -> dict[str, Any] | None:
        stage = str(row.get("stage") or "").strip().lower()
        if stage not in REFRESH_STAGE_WEIGHTS:
            return None

        raw_total = row.get("progress_total")
        raw_current = row.get("progress_current")
        total = max(1, int(raw_total or 1))
        current = max(0, min(total, int(raw_current or 0)))

        completed_before_stage = 0.0
        for stage_name in REFRESH_STAGE_ORDER:
            if stage_name == stage:
                break
            completed_before_stage += float(REFRESH_STAGE_WEIGHTS[stage_name])

        stage_weight = float(REFRESH_STAGE_WEIGHTS[stage])
        stage_ratio = min(1.0, max(0.0, float(current) / float(total)))
        progress_pct = completed_before_stage + (stage_weight * stage_ratio)
        progress_pct = max(0.0, min(100.0, progress_pct))

        started_at = self._parse_timestamp(row.get("started_at")) or self._parse_timestamp(
            row.get("last_attempt_at")
        )
        now = datetime.now(timezone.utc)
        elapsed_seconds = (
            max(0, int(round((now - started_at).total_seconds())))
            if started_at is not None
            else None
        )

        estimated_total_seconds: int | None = None
        estimated_eta_seconds: int | None = None
        estimated_completion_at: str | None = None
        if elapsed_seconds is not None and progress_pct > 0.0:
            progress_ratio = min(1.0, max(0.0001, progress_pct / 100.0))
            if progress_ratio >= 1.0:
                estimated_total_seconds = elapsed_seconds
                estimated_eta_seconds = 0
                estimated_completion_at = now.replace(microsecond=0).isoformat()
            else:
                estimated_total_seconds = max(
                    elapsed_seconds,
                    int(round(float(elapsed_seconds) / progress_ratio)),
                )
                estimated_eta_seconds = max(
                    0,
                    int(estimated_total_seconds) - int(elapsed_seconds),
                )
                estimated_completion_at = (
                    started_at + timedelta(seconds=int(estimated_total_seconds))
                ).replace(microsecond=0).isoformat()

        if tracking_state == "stalled":
            estimated_eta_seconds = None
            estimated_completion_at = None

        return {
            "estimated_progress_pct": round(float(progress_pct), 1),
            "estimated_eta_seconds": estimated_eta_seconds,
            "estimated_total_seconds": estimated_total_seconds,
            "elapsed_seconds": elapsed_seconds,
            "estimated_completion_at": estimated_completion_at,
            "estimate_confidence": "high",
            "progress_mode": (
                "stalled" if tracking_state == "stalled" else "real_progress"
            ),
        }

    def _estimate_refresh_throughput(self) -> dict[str, Any]:
        if not inspect(self.engine).has_table("company_refresh_status"):
            return {"per_hour": None, "sample_size": 0, "confidence": "low"}

        query = text(
            """
            SELECT last_success_at
            FROM company_refresh_status
            WHERE last_status = 'success'
              AND last_success_at IS NOT NULL
            ORDER BY last_success_at DESC
            LIMIT 200
            """
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()

        parsed = [
            timestamp
            for timestamp in (
                self._parse_timestamp(row.get("last_success_at"))
                for row in rows
            )
            if timestamp is not None
        ]
        if not parsed:
            return {"per_hour": None, "sample_size": 0, "confidence": "low"}

        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=self.THROUGHPUT_WINDOW_HOURS)
        recent = sorted(timestamp for timestamp in parsed if timestamp >= recent_cutoff)
        if len(recent) < self.THROUGHPUT_MIN_SUCCESS_SAMPLES:
            return {"per_hour": None, "sample_size": len(recent), "confidence": "low"}

        span_hours = (recent[-1] - recent[0]).total_seconds() / 3600.0
        if span_hours <= 0:
            return {"per_hour": None, "sample_size": len(recent), "confidence": "low"}

        per_hour = max(0.0, (len(recent) - 1) / span_hours)
        confidence = "high" if len(recent) >= 12 and span_hours >= 6 else "medium"
        return {
            "per_hour": float(per_hour) if per_hour > 0 else None,
            "sample_size": len(recent),
            "confidence": confidence if per_hour > 0 else "low",
        }

    def _ensure_refresh_status_table(self, conn) -> None:
        ensure_refresh_runtime_tables_for_connection(conn)

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        raw_value = str(value).strip()
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_recently_queued(
        self,
        status_row: dict[str, Any] | Any,
        *,
        window: timedelta,
    ) -> bool:
        if not status_row:
            return False
        last_status = (
            str(status_row.get("last_status") or "").strip().lower()
            if hasattr(status_row, "get")
            else str(getattr(status_row, "last_status", "") or "").strip().lower()
        )
        if last_status != "queued":
            return False
        last_attempt_at = (
            status_row.get("last_attempt_at")
            if hasattr(status_row, "get")
            else getattr(status_row, "last_attempt_at", None)
        )
        attempted_at = self._parse_timestamp(last_attempt_at)
        if attempted_at is None:
            return False
        return (datetime.now(timezone.utc) - attempted_at) < window

    def _priority_score(
        self,
        *,
        coverage_rank: int | None,
        missing_years_count: int,
        gap_to_leader_years: int,
    ) -> int:
        normalized_rank = coverage_rank if coverage_rank is not None else 999
        rank_score = max(0, 81 - int(normalized_rank)) * 100
        return int(rank_score + (int(missing_years_count) * 25) + (int(gap_to_leader_years) * 10))

    def _risk_level(
        self,
        *,
        coverage_rank: int | None,
        missing_years_count: int,
        excluded_from_queue: bool,
    ) -> str:
        if excluded_from_queue:
            return "alto"
        if missing_years_count <= 0:
            return "baixo"
        if coverage_rank is not None and coverage_rank <= 20:
            return "alto"
        if coverage_rank is not None and coverage_rank <= 50:
            return "medio"
        if missing_years_count >= 3:
            return "medio"
        return "baixo"

    def _health_status_from_score(self, score: float) -> str:
        if score >= self.BASE_HEALTH_OK_THRESHOLD:
            return "ok"
        if score >= self.BASE_HEALTH_CRITICAL_THRESHOLD:
            return "atencao"
        return "critico"

    def _build_company_results(self, df: pd.DataFrame) -> list[CompanySearchResult]:
        results = []
        if df is None or df.empty:
            return results

        for row in df.to_dict(orient="records"):
            setor_analitico = self._clean_optional_text(row.get("setor_analitico"))
            setor_cvm = self._clean_optional_text(row.get("setor_cvm"))
            raw_sector_name = self._clean_optional_text(row.get("sector_name"))
            sector_name = raw_sector_name or canonical_sector_name(setor_analitico, setor_cvm)
            gics = resolve_gics_classification(
                sector_name=sector_name,
                setor_analitico=setor_analitico,
                setor_cvm=setor_cvm,
                gics_sector=row.get("persisted_gics_sector"),
                gics_sector_slug=row.get("persisted_gics_sector_slug"),
                gics_industry_group=row.get("persisted_gics_industry_group"),
                gics_industry=row.get("persisted_gics_industry"),
                gics_sub_industry=row.get("persisted_gics_sub_industry"),
            )
            raw_coverage_rank = row.get("coverage_rank")
            anos = _parse_years(row.get("anos_disponiveis"))
            has_data = bool(int(row.get("has_financial_data") or 0))
            raw_status = str(row.get("data_status") or "").strip()
            # Precedence: failed > unmapped > explicit status > heuristic
            # "complete" only when coverage_rank confirms the company is tracked with data.
            # Heuristic year count is intentionally NOT used to claim "complete".
            if raw_status == "failed":
                data_status = "failed"
            elif raw_status == "unmapped":
                data_status = "unmapped"
            elif raw_status in ("no_history", "partial", "complete"):
                data_status = raw_status
            elif not has_data:
                data_status = "no_history"
            elif raw_coverage_rank is not None and str(raw_coverage_rank) not in ("", "nan"):
                data_status = "complete"
            else:
                data_status = "partial"
            results.append(
                CompanySearchResult(
                    cd_cvm=int(row["cd_cvm"]),
                    company_name=str(row["company_name"]),
                    ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                    setor_analitico=setor_analitico,
                    setor_cvm=setor_cvm,
                    sector_name=sector_name,
                    sector_slug=sector_slugify(sector_name),
                    anos_disponiveis=anos,
                    total_rows=int(row.get("total_rows") or 0),
                    has_financial_data=has_data,
                    coverage_rank=int(raw_coverage_rank) if raw_coverage_rank is not None and str(raw_coverage_rank) != "nan" else None,
                    gics_sector=gics.gics_sector if gics else None,
                    gics_sector_slug=gics.gics_sector_slug if gics else None,
                    gics_industry_group=gics.gics_industry_group if gics else None,
                    gics_industry=gics.gics_industry if gics else None,
                    gics_sub_industry=gics.gics_sub_industry if gics else None,
                    data_status=data_status,
                )
            )
        return results

    def _merge_catalog_with_db(self, *, include_years: bool = True) -> list[CompanySearchResult]:
        """Full catalog × DB merge — always returns all active catalog companies.

        For each catalog entry the local DB row is used when present (has
        financial-data counts, GICS, coverage_rank).  Catalog-only entries get
        a lightweight stub (name, ticker, legacy sector).

        Unlike _list_company_universe_results this method is never gated by the
        CATALOG_FALLBACK_MIN_LOCAL_COMPANIES threshold, so it always exposes the
        full known universe regardless of how many companies have been downloaded.
        """
        cached = (
            self._merged_company_catalog_cache
            if include_years
            else self._merged_company_catalog_light_cache
        )
        if cached is not None:
            return list(cached)

        def _cache_and_return(items: list[CompanySearchResult]) -> list[CompanySearchResult]:
            if include_years:
                self._merged_company_catalog_cache = tuple(items)
                return list(self._merged_company_catalog_cache)
            self._merged_company_catalog_light_cache = tuple(items)
            return list(self._merged_company_catalog_light_cache)

        local_items = self._load_local_company_universe_results(include_years=include_years)
        try:
            catalog_entries = [entry for entry in self.company_catalog.list_entries() if entry.is_active]
        except CompanyCatalogUnavailableError:
            return _cache_and_return(local_items)
        if not catalog_entries:
            return _cache_and_return(local_items)

        page_codes = [int(entry.cd_cvm) for entry in catalog_entries]
        local_results_by_code: dict[int, CompanySearchResult] = {}
        if page_codes:
            local_rows = (
                self.query_layer.get_companies_by_cvm_ids(page_codes)
                if include_years
                else self.query_layer.get_companies_by_cvm_ids_light(page_codes)
            )
            if not local_rows.empty:
                local_rows = local_rows.copy()
                if include_years:
                    years_map = self.query_layer.get_company_years_map(local_rows["cd_cvm"].tolist())
                    local_rows["anos_disponiveis"] = local_rows["cd_cvm"].map(
                        lambda cd_cvm: years_map.get(int(cd_cvm), ())
                    )
                local_results_by_code = {
                    int(item.cd_cvm): item for item in self._build_company_results(local_rows)
                }

        # Also include DB-only companies not present in the catalog
        catalog_codes = {int(entry.cd_cvm) for entry in catalog_entries}
        items: list[CompanySearchResult] = []
        seen: set[int] = set()

        for entry in catalog_entries:
            cd = int(entry.cd_cvm)
            seen.add(cd)
            local_result = local_results_by_code.get(cd)
            if local_result is not None:
                items.append(local_result)
                continue
            legacy_sector = canonical_sector_name(None, entry.setor_cvm)
            items.append(
                CompanySearchResult(
                    cd_cvm=cd,
                    company_name=entry.company_name,
                    ticker_b3=entry.ticker_b3,
                    setor_analitico=None,
                    setor_cvm=entry.setor_cvm,
                    sector_name=legacy_sector,
                    sector_slug=sector_slugify(legacy_sector),
                    anos_disponiveis=(),
                    total_rows=0,
                    has_financial_data=False,
                    coverage_rank=None,
                    gics_sector=None,
                    gics_sector_slug=None,
                    gics_industry_group=None,
                    gics_industry=None,
                    gics_sub_industry=None,
                )
            )

        # Append any local DB companies not in catalog (custom/imported entities)
        for item in local_items:
            if item.cd_cvm not in seen:
                items.append(item)

        return _cache_and_return(items)

    def _list_company_universe_results(self) -> list[CompanySearchResult]:
        self._ensure_read_cache_fresh()
        if self._company_universe_cache is not None:
            return list(self._company_universe_cache)

        def _cache_and_return(items: list[CompanySearchResult]) -> list[CompanySearchResult]:
            self._company_universe_cache = tuple(items)
            return list(self._company_universe_cache)

        local_items = self._load_local_company_universe_results()
        if len(local_items) >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES:
            return _cache_and_return(local_items)

        merged = self._merge_catalog_with_db()
        return _cache_and_return(merged)

    def _list_company_universe_results_light(self) -> list[CompanySearchResult]:
        self._ensure_read_cache_fresh()
        if self._company_universe_light_cache is not None:
            return list(self._company_universe_light_cache)

        def _cache_and_return(items: list[CompanySearchResult]) -> list[CompanySearchResult]:
            self._company_universe_light_cache = tuple(items)
            return list(self._company_universe_light_cache)

        local_items = self._load_local_company_universe_results(include_years=False)
        if len(local_items) >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES:
            return _cache_and_return(local_items)

        merged = self._merge_catalog_with_db(include_years=False)
        return _cache_and_return(merged)

    def _sector_company_preview(
        self,
        items: list[CompanySearchResult],
        limit: int = 12,
    ) -> tuple[SectorCompanyMetricDTO, ...]:
        ordered = sorted(
            items,
            key=lambda item: (
                0 if item.has_financial_data else 1,
                item.company_name.upper(),
            ),
        )
        return tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(item.cd_cvm),
                company_name=str(item.company_name),
                ticker_b3=item.ticker_b3,
                gics_sub_industry=item.gics_sub_industry,
                roe=None,
                mg_ebit=None,
                mg_liq=None,
            )
            for item in ordered[: int(limit)]
        )

    @staticmethod
    def _clean_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        if pd.isna(value):
            return None
        text_value = str(value).strip()
        return text_value or None

    def _resolve_sector_slug(self, sector_slug: str | None) -> str | None:
        if not sector_slug:
            return None
        normalized_slug = str(sector_slug).strip().lower()
        if not normalized_slug:
            return None
        for option in self.get_company_filters().sectors:
            if option.sector_slug == normalized_slug:
                return option.sector_name
        
        # Fallback to CVM sectors
        for item in self._list_company_universe_results_light():
            if item.sector_name:
                slug = sector_slugify(item.sector_name)
                if slug == normalized_slug:
                    return item.sector_name
            if item.setor_cvm:
                slug = sector_slugify(item.setor_cvm)
                if slug == normalized_slug:
                    return item.setor_cvm
        return None

    @staticmethod
    def _file_cache_stat(path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return {"path": str(path), "exists": False}
        except Exception:
            return {"path": str(path), "exists": None}
        return {
            "path": str(path),
            "exists": True,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    @staticmethod
    def _table_cache_fingerprint(
        conn: Any,
        table_name: str,
        *,
        max_columns: tuple[str, ...] = (),
        include_count: bool = False,
    ) -> dict[str, Any]:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            return {"exists": False}

        fingerprint: dict[str, Any] = {"exists": True}
        safe_table = str(table_name).replace('"', '""')
        if include_count:
            fingerprint["row_count"] = conn.exec_driver_sql(
                f'SELECT COUNT(*) FROM "{safe_table}"'
            ).scalar()
        fingerprint["max_rowid"] = conn.exec_driver_sql(
            f'SELECT MAX(rowid) FROM "{safe_table}"'
        ).scalar()
        for column in max_columns:
            safe_column = str(column).replace('"', '""')
            fingerprint[str(column)] = conn.exec_driver_sql(
                f'SELECT MAX("{safe_column}") FROM "{safe_table}"'
            ).scalar()
        return fingerprint

    def _cvm_data_cache_signature(self) -> dict[str, Any]:
        db_path = Path(self.settings.paths.db_path)
        if not db_path.exists():
            return {"database": str(db_path), "exists": False}
        try:
            with self.engine.connect() as conn:
                return {
                    "database": str(db_path.resolve()),
                    "exists": True,
                    "financial_reports": self._table_cache_fingerprint(
                        conn,
                        "financial_reports",
                        max_columns=("REPORT_YEAR",),
                    ),
                    "companies": self._table_cache_fingerprint(
                        conn,
                        "companies",
                        include_count=True,
                    ),
                    "company_refresh_status": self._table_cache_fingerprint(
                        conn,
                        "company_refresh_status",
                        max_columns=("updated_at", "last_success_at", "last_attempt_at"),
                        include_count=True,
                    ),
                }
        except Exception:
            return {"database": str(db_path), "exists": None}

    @classmethod
    def _sqlite_cache_signature(cls, db_path: Path) -> list[dict[str, Any]]:
        return [
            cls._file_cache_stat(db_path),
            cls._file_cache_stat(Path(f"{db_path}-wal")),
        ]

    def _base_health_cache_path(self) -> Path:
        return self.settings.paths.cache_dir / (
            f"base_health_db_snapshot_v{self.BASE_HEALTH_CACHE_SCHEMA_VERSION}.json"
        )

    def _base_health_cache_signature(self, *, start_year: int, end_year: int) -> list[Any] | None:
        if self.engine.dialect.name != "sqlite":
            return None
        db_path = Path(self.settings.paths.db_path)
        return [
            "base_health",
            self.BASE_HEALTH_CACHE_SCHEMA_VERSION,
            int(start_year),
            int(end_year),
            self._cvm_data_cache_signature(),
            self._file_cache_stat(Path(self.settings.paths.active_universe_cache_path)),
        ]

    def _load_base_health_persistent_cache(
        self,
        *,
        start_year: int,
        end_year: int,
    ) -> HealthSnapshot | None:
        signature = self._base_health_cache_signature(
            start_year=start_year,
            end_year=end_year,
        )
        if signature is None:
            return None

        try:
            raw_payload = json.loads(self._base_health_cache_path().read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw_payload, dict):
            return None
        if raw_payload.get("schema_version") != self.BASE_HEALTH_CACHE_SCHEMA_VERSION:
            return None
        if raw_payload.get("signature") != signature:
            return None
        payload = raw_payload.get("data")
        if not isinstance(payload, dict):
            return None
        try:
            return HealthSnapshot.from_payload(payload)
        except Exception:
            return None

    def _write_base_health_persistent_cache(
        self,
        *,
        start_year: int,
        end_year: int,
        payload: dict[str, Any],
    ) -> None:
        signature = self._base_health_cache_signature(
            start_year=start_year,
            end_year=end_year,
        )
        if signature is None:
            return
        cache_path = self._base_health_cache_path()
        raw_payload = {
            "schema_version": self.BASE_HEALTH_CACHE_SCHEMA_VERSION,
            "signature": signature,
            "data": payload,
        }
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
            tmp_path.write_text(json.dumps(raw_payload, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(cache_path)
        except Exception:
            return

    def _clear_base_health_persistent_cache(self) -> None:
        try:
            cache_path = self._base_health_cache_path()
            cache_path.unlink(missing_ok=True)
        except Exception:
            return

    def _sector_directory_cache_path(self, group_by: str) -> Path:
        if group_by == "sub_sector":
            safe_group = "sub_sector"
        elif group_by == "cvm_sector":
            safe_group = "cvm_sector"
        else:
            safe_group = "sector"
        return self.settings.paths.cache_dir / f"sector_directory_{safe_group}_v1.json"

    def _sector_directory_cache_signature(self) -> dict[str, Any] | None:
        if self.engine.dialect.name != "sqlite":
            return None
        db_path = Path(self.settings.paths.db_path)
        if not db_path.exists():
            return None
        return {
            "database": str(db_path.resolve()),
            "tables": self._cvm_data_cache_signature(),
        }

    def _load_sector_directory_persistent_cache(self, group_by: str) -> SectorDirectoryDTO | None:
        signature = self._sector_directory_cache_signature()
        if signature is None:
            return None

        cache_path = self._sector_directory_cache_path(group_by)
        try:
            raw_payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if raw_payload.get("schema_version") != self.SECTOR_DIRECTORY_CACHE_SCHEMA_VERSION:
                return None
            if raw_payload.get("group_by") != group_by:
                return None
            if raw_payload.get("signature") != signature:
                return None
            return self._sector_directory_from_payload(raw_payload.get("data") or {})
        except Exception:
            return None

    def _write_sector_directory_persistent_cache(
        self,
        group_by: str,
        result: SectorDirectoryDTO,
    ) -> None:
        signature = self._sector_directory_cache_signature()
        if signature is None:
            return

        cache_path = self._sector_directory_cache_path(group_by)
        payload = {
            "schema_version": self.SECTOR_DIRECTORY_CACHE_SCHEMA_VERSION,
            "group_by": group_by,
            "signature": signature,
            "data": result.to_dict(),
        }
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp_path.replace(cache_path)
        except Exception:
            return

    def _clear_sector_directory_persistent_cache(self) -> None:
        try:
            cache_dir = self.settings.paths.cache_dir
            for cache_path in cache_dir.glob("sector_directory_*_v1.json"):
                cache_path.unlink(missing_ok=True)
        except Exception:
            return

    def _sector_directory_from_payload(self, payload: dict[str, Any]) -> SectorDirectoryDTO:
        items: list[SectorDirectoryItemDTO] = []
        for raw_item in payload.get("items") or []:
            raw_snapshot = raw_item.get("snapshot") or {}
            raw_breakdown = raw_item.get("sub_industry_breakdown") or ()
            raw_companies = raw_item.get("companies") or ()

            items.append(
                SectorDirectoryItemDTO(
                    sector_name=str(raw_item["sector_name"]),
                    sector_slug=str(raw_item["sector_slug"]),
                    company_count=int(raw_item["company_count"]),
                    latest_year=(
                        int(raw_item["latest_year"])
                        if raw_item.get("latest_year") is not None
                        else None
                    ),
                    snapshot=SectorSnapshotDTO(
                        roe=self._coerce_optional_float(raw_snapshot.get("roe")),
                        mg_ebit=self._coerce_optional_float(raw_snapshot.get("mg_ebit")),
                        mg_liq=self._coerce_optional_float(raw_snapshot.get("mg_liq")),
                    ),
                    sub_industries=tuple(str(value) for value in raw_item.get("sub_industries") or ()),
                    sub_industry_breakdown=tuple(
                        SubIndustryCountDTO(
                            name=str(row["name"]),
                            count=int(row["count"]),
                        )
                        for row in raw_breakdown
                    ),
                    group_type=str(raw_item.get("group_type") or "sector"),
                    parent_sector_name=self._clean_optional_text(raw_item.get("parent_sector_name")),
                    parent_sector_slug=self._clean_optional_text(raw_item.get("parent_sector_slug")),
                    companies=tuple(
                        SectorCompanyMetricDTO(
                            cd_cvm=int(row["cd_cvm"]),
                            company_name=str(row["company_name"]),
                            ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                            gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                            roe=self._coerce_optional_float(row.get("roe")),
                            mg_ebit=self._coerce_optional_float(row.get("mg_ebit")),
                            mg_liq=self._coerce_optional_float(row.get("mg_liq")),
                        )
                        for row in raw_companies
                    ),
                )
            )
        return SectorDirectoryDTO(items=tuple(items))

    @staticmethod
    def _extract_years_from_company_rows(df: pd.DataFrame) -> list[int]:
        years: set[int] = set()
        if df is None or df.empty:
            return []
        for raw_years in df.get("anos_disponiveis", []):
            years.update(_parse_years(raw_years))
        return sorted(years)

    def _get_sector_metric_rows(
        self,
        *,
        sector_name: str | None = None,
        years: list[int] | None = None,
        cd_cvms: list[int] | None = None,
    ) -> pd.DataFrame:
        if sector_name is None and not years and cd_cvms is None:
            if self._sector_metric_rows_cache is None:
                self._sector_metric_rows_cache = self.query_layer.get_sector_metric_rows()
            return self._sector_metric_rows_cache
        return self.query_layer.get_sector_metric_rows(
            sector_name=sector_name,
            years=years,
            cd_cvms=cd_cvms,
        )

    @staticmethod
    def _aggregate_sector_yearly_metrics(metric_rows: pd.DataFrame) -> pd.DataFrame:
        if metric_rows is None or metric_rows.empty:
            return pd.DataFrame(columns=["sector_name", "year", "roe", "mg_ebit", "mg_liq"])

        aggregated = (
            metric_rows.groupby(["sector_name", "report_year"], dropna=False)[["roe", "mg_ebit", "mg_liq"]]
            .mean()
            .reset_index()
            .rename(columns={"report_year": "year"})
        )
        return aggregated

    @staticmethod
    def _coerce_optional_float(value: Any) -> float | None:
        if value is None or pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _empty_company_page(
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        return CompanyDirectoryPage(
            items=(),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=0,
                total_pages=1,
                has_next=False,
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )
