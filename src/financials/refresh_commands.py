"""Explicit refresh commands; composed into the public CVMReadService facade."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from sqlalchemy import text

from src.companies.catalog import CompanyCatalogUnavailableError
from src.companies.gics_manual_mapping import resolve_gics_classification
from src.platform.contracts import (
    RankedRefreshQueueItem, RankedRefreshQueueResult, RefreshDispatchDTO,
    RefreshRequest, default_incremental_refresh_policy,
)
from src.financials.read_service_refresh_selection import RefreshAlreadyActiveError
from src.companies.sector_taxonomy import canonical_sector_name
from src.financials.utils import now_iso_seconds


class RefreshCommandsMixin:
    def _ensure_company_catalog_metadata(self, cd_cvm: int) -> bool:
        if self.query_layer.get_company_info(cd_cvm):
            return False

        try:
            catalog_entry = self.company_catalog.lookup_company(cd_cvm)
        except CompanyCatalogUnavailableError:
            # This method is called only by the explicit single-company refresh command.
            self.company_catalog.refresh()
            catalog_entry = self.company_catalog.lookup_company(cd_cvm)
        if catalog_entry is None:
            return False

        now_iso = now_iso_seconds()
        gics = resolve_gics_classification(
            sector_name=canonical_sector_name(None, catalog_entry.setor_cvm),
            setor_analitico=None,
            setor_cvm=catalog_entry.setor_cvm,
        )
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO companies (
                        cd_cvm,
                        company_name,
                        nome_comercial,
                        cnpj,
                        setor_cvm,
                        gics_sector,
                        gics_sector_slug,
                        gics_industry_group,
                        gics_industry,
                        gics_sub_industry,
                        company_type,
                        ticker_b3,
                        is_active,
                        updated_at
                    ) VALUES (
                        :cd_cvm,
                        :company_name,
                        :nome_comercial,
                        :cnpj,
                        :setor_cvm,
                        :gics_sector,
                        :gics_sector_slug,
                        :gics_industry_group,
                        :gics_industry,
                        :gics_sub_industry,
                        :company_type,
                        :ticker_b3,
                        :is_active,
                        :updated_at
                    )
                    ON CONFLICT(cd_cvm) DO UPDATE SET
                        company_name = excluded.company_name,
                        nome_comercial = COALESCE(excluded.nome_comercial, companies.nome_comercial),
                        cnpj = COALESCE(excluded.cnpj, companies.cnpj),
                        setor_cvm = COALESCE(excluded.setor_cvm, companies.setor_cvm),
                        gics_sector = COALESCE(excluded.gics_sector, companies.gics_sector),
                        gics_sector_slug = COALESCE(excluded.gics_sector_slug, companies.gics_sector_slug),
                        gics_industry_group = COALESCE(excluded.gics_industry_group, companies.gics_industry_group),
                        gics_industry = COALESCE(excluded.gics_industry, companies.gics_industry),
                        gics_sub_industry = COALESCE(excluded.gics_sub_industry, companies.gics_sub_industry),
                        company_type = COALESCE(excluded.company_type, companies.company_type),
                        ticker_b3 = COALESCE(excluded.ticker_b3, companies.ticker_b3),
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "cd_cvm": int(catalog_entry.cd_cvm),
                    "company_name": catalog_entry.company_name,
                    "nome_comercial": catalog_entry.nome_comercial,
                    "cnpj": catalog_entry.cnpj,
                    "setor_cvm": catalog_entry.setor_cvm,
                    "gics_sector": gics.gics_sector if gics else None,
                    "gics_sector_slug": gics.gics_sector_slug if gics else None,
                    "gics_industry_group": gics.gics_industry_group if gics else None,
                    "gics_industry": gics.gics_industry if gics else None,
                    "gics_sub_industry": gics.gics_sub_industry if gics else None,
                    "company_type": "comercial",
                    "ticker_b3": catalog_entry.ticker_b3,
                    "is_active": 1 if catalog_entry.is_active else 0,
                    "updated_at": now_iso,
                },
            )
        return True

    def request_company_refresh(
        self,
        cd_cvm: int,
        *,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> RefreshDispatchDTO:
        """Enqueue internal on-demand ingest for one company.

        When ``start_year``/``end_year`` are omitted, falls back to the
        historical default window (2010..current). When provided, the
        caller can narrow the ingest to a specific period — the dispatch
        still flows through ``refresh_job_repository`` so that
        ``company_refresh_status`` reflects the running job for polling.
        """
        from src.platform.api_errors import NotFoundError

        bootstrapped = self._ensure_company_catalog_metadata(cd_cvm)
        requested_start = int(start_year) if start_year is not None else 2010
        requested_end = int(end_year) if end_year is not None else None
        start_year, end_year = self._resolve_refresh_range(
            start_year=requested_start,
            end_year=requested_end,
        )
        company_info = self.get_company_info(cd_cvm)
        if company_info is None:
            raise NotFoundError(f"Company cd_cvm={cd_cvm} not found")

        source_scope = "on_demand_bootstrap" if bootstrapped else "on_demand"
        request = RefreshRequest(
            companies=(str(cd_cvm),),
            start_year=start_year,
            end_year=end_year,
            policy=default_incremental_refresh_policy(),
        )
        planned_companies, _, _ = self.refresh_service.build_company_year_plan(request)

        active_job = self.refresh_job_repository.get_active_job_for_company(cd_cvm)
        if active_job is not None:
            raise RefreshAlreadyActiveError(
                f"Refresh already active for cd_cvm={cd_cvm}"
            )

        if not planned_companies:
            projection = self.refresh_job_repository.mark_already_current(
                cd_cvm=cd_cvm,
                company_name=company_info.company_name,
                source_scope=source_scope,
                start_year=start_year,
                end_year=end_year,
                message=(
                    "Company already up to date for "
                    f"{start_year}-{end_year}."
                ),
            )
            return RefreshDispatchDTO(
                status="already_current",
                cd_cvm=int(cd_cvm),
                job_id=None,
                accepted_at=str(projection["accepted_at"]),
                message=str(projection["message"]),
                status_reason_code="already_current",
                status_reason_message=(
                    "This company was already up to date for the default window."
                ),
                is_retry_allowed=False,
            )

        job = self.refresh_job_repository.enqueue_job(
            cd_cvm=cd_cvm,
            company_name=company_info.company_name,
            source_scope=source_scope,
            start_year=start_year,
            end_year=end_year,
        )
        if job is None:
            raise RefreshAlreadyActiveError(
                f"Refresh already active for cd_cvm={cd_cvm}"
            )

        return RefreshDispatchDTO(
            status="queued",
            cd_cvm=int(cd_cvm),
            job_id=str(job.id),
            accepted_at=str(job.requested_at),
            message=str(
                job.progress_message
                or "Request queued for internal processing."
            ),
            status_reason_code="refresh_queued",
            status_reason_message=(
                "Request accepted and awaiting internal processing."
            ),
            is_retry_allowed=False,
        )

    def request_top_ranked_historical_refresh(
        self,
        *,
        limit: int = 80,
        start_year: int = 2010,
        end_year: int | None = None,
    ) -> RankedRefreshQueueResult:
        resolved_start_year, resolved_end_year = self._resolve_refresh_range(
            start_year=start_year,
            end_year=end_year,
        )
        backlog = self._build_ranked_backlog(
            limit=int(limit),
            start_year=resolved_start_year,
            end_year=resolved_end_year,
        )

        queue_window = timedelta(hours=self.PRIORITIZED_BACKLOG_STALE_HOURS)
        items: list[RankedRefreshQueueItem] = []
        counters = {
            "queued_count": 0,
            "already_queued_count": 0,
            "no_data_excluded_count": 0,
            "already_complete_count": 0,
            "dispatch_failed_count": 0,
        }

        for row in backlog["items"]:
            status = str(row["recommended_action"])
            note = str(row["reason"])

            if status == "queue_historical_backfill":
                dispatch_result = self._dispatch_refresh_request(
                    cd_cvm=int(row["cd_cvm"]),
                    start_year=resolved_start_year,
                    end_year=resolved_end_year,
                    source_scope="ranked_backfill",
                    already_queued_window=queue_window,
                )
                if dispatch_result == "dispatched":
                    status = "queued"
                    note = (
                        f"Workflow queued for annual backfill between "
                        f"{resolved_start_year} and {resolved_end_year}."
                    )
                    counters["queued_count"] += 1
                elif dispatch_result == "already_queued":
                    status = "already_queued"
                    note = "A recent run is already queued for this company."
                    counters["already_queued_count"] += 1
                else:
                    status = "dispatch_failed"
                    note = "Failed to dispatch the historical backfill workflow."
                    counters["dispatch_failed_count"] += 1
            elif status == "await_existing_queue":
                status = "already_queued"
                counters["already_queued_count"] += 1
            elif status == "skip_no_data":
                status = "no_data_excluded"
                counters["no_data_excluded_count"] += 1
            else:
                status = "already_complete"
                counters["already_complete_count"] += 1

            items.append(
                RankedRefreshQueueItem(
                    cd_cvm=int(row["cd_cvm"]),
                    company_name=str(row["company_name"]),
                    coverage_rank=(
                        int(row["coverage_rank"])
                        if row.get("coverage_rank") is not None
                        else None
                    ),
                    status=status,
                    last_status=(
                        str(row["last_status"])
                        if row.get("last_status") is not None
                        else None
                    ),
                    missing_years_count=int(row["missing_years_count"]),
                    years_missing=tuple(int(year) for year in row["years_missing"]),
                    note=note,
                )
            )

        return RankedRefreshQueueResult(
            start_year=resolved_start_year,
            end_year=resolved_end_year,
            requested_limit=int(limit),
            total_ranked=int(backlog["summary"]["total_ranked"]),
            queued_count=int(counters["queued_count"]),
            already_queued_count=int(counters["already_queued_count"]),
            no_data_excluded_count=int(counters["no_data_excluded_count"]),
            already_complete_count=int(counters["already_complete_count"]),
            dispatch_failed_count=int(counters["dispatch_failed_count"]),
            items=tuple(items),
        )

    def _dispatch_refresh_request(
        self,
        *,
        cd_cvm: int,
        start_year: int,
        end_year: int,
        source_scope: str,
        already_queued_window: timedelta,
    ) -> str:
        from src.platform.api_errors import NotFoundError
        from src.refresh.github_dispatch import dispatch_on_demand_ingest

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self.engine.begin() as conn:
            self._ensure_refresh_status_table(conn)
            company_row = conn.execute(
                text(
                    """
                    SELECT c.company_name, crs.last_status, crs.last_attempt_at
                    FROM companies c
                    LEFT JOIN company_refresh_status crs ON crs.cd_cvm = c.cd_cvm
                    WHERE c.cd_cvm = :cd_cvm
                    """
                ),
                {"cd_cvm": int(cd_cvm)},
            ).mappings().fetchone()
            if company_row is None:
                raise NotFoundError(f"Company cd_cvm={cd_cvm} not found")
            if self._is_recently_queued(company_row, window=already_queued_window):
                return "already_queued"

            company_name = str(company_row.get("company_name") or cd_cvm)
            conn.execute(
                text(
                    """
                    INSERT INTO company_refresh_status (
                        cd_cvm,
                        company_name,
                        source_scope,
                        last_attempt_at,
                        last_status,
                        last_error,
                        last_start_year,
                        last_end_year,
                        updated_at
                    ) VALUES (
                        :cd_cvm,
                        :company_name,
                        :source_scope,
                        :now,
                        'queued',
                        NULL,
                        :start_year,
                        :end_year,
                        :now
                    )
                    ON CONFLICT (cd_cvm) DO UPDATE SET
                        company_name = excluded.company_name,
                        source_scope = excluded.source_scope,
                        last_attempt_at = excluded.last_attempt_at,
                        last_status = excluded.last_status,
                        last_error = excluded.last_error,
                        last_start_year = excluded.last_start_year,
                        last_end_year = excluded.last_end_year,
                        updated_at = excluded.updated_at
                    """
                ),
                {
                    "cd_cvm": int(cd_cvm),
                    "company_name": company_name,
                    "source_scope": str(source_scope),
                    "start_year": int(start_year),
                    "end_year": int(end_year),
                    "now": now_iso,
                },
            )

        ok, error_msg = dispatch_on_demand_ingest(
            int(cd_cvm),
            start_year=int(start_year),
            end_year=int(end_year),
        )
        if not ok:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE company_refresh_status
                        SET last_status = 'dispatch_failed',
                            last_error = :error_msg,
                            last_start_year = :start_year,
                            last_end_year = :end_year,
                            updated_at = :now
                        WHERE cd_cvm = :cd_cvm
                        """
                    ),
                    {
                        "cd_cvm": int(cd_cvm),
                        "error_msg": error_msg,
                        "start_year": int(start_year),
                        "end_year": int(end_year),
                        "now": now_iso,
                    },
                )
            return "dispatch_failed"

        return "dispatched"
