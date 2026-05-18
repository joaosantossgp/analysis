from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


def _coerce_int_tuple(values: list[int] | tuple[int, ...] | None) -> tuple[int, ...]:
    if not values:
        return ()
    return tuple(int(value) for value in values)


@dataclass(frozen=True)
class TabularData:
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame | None) -> "TabularData":
        if df is None or df.empty:
            return cls(columns=(), rows=())
        records = tuple(df.where(pd.notna(df), None).to_dict(orient="records"))
        return cls(columns=tuple(str(col) for col in df.columns), rows=records)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.columns:
            return pd.DataFrame()
        df = pd.DataFrame(list(self.rows))
        if df.empty:
            return pd.DataFrame(columns=list(self.columns))
        return df.reindex(columns=list(self.columns))

    def to_dict(self) -> dict[str, Any]:
        return {"columns": list(self.columns), "rows": list(self.rows)}


@dataclass(frozen=True)
class RefreshPolicy:
    skip_complete_company_years: bool = False
    enable_fast_lane: bool = False
    force_refresh: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_incremental_refresh_policy() -> RefreshPolicy:
    return RefreshPolicy(
        skip_complete_company_years=True,
        enable_fast_lane=False,
        force_refresh=False,
    )


@dataclass(frozen=True)
class RefreshRequest:
    companies: tuple[str, ...]
    start_year: int
    end_year: int
    report_type: str = "consolidated"
    max_workers: int = 2
    data_dir: str | None = None
    output_dir: str | None = None
    policy: RefreshPolicy = field(default_factory=RefreshPolicy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "companies", tuple(str(company) for company in self.companies))
        object.__setattr__(self, "start_year", int(self.start_year))
        object.__setattr__(self, "end_year", int(self.end_year))
        object.__setattr__(self, "max_workers", int(self.max_workers))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["companies"] = list(self.companies)
        return payload


@dataclass(frozen=True)
class RefreshBatchSelection:
    mode: str
    companies: tuple[str, ...]
    start_year: int
    end_year: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", str(self.mode).strip().lower())
        object.__setattr__(
            self,
            "companies",
            tuple(str(company) for company in self.companies),
        )
        object.__setattr__(self, "start_year", int(self.start_year))
        object.__setattr__(self, "end_year", int(self.end_year))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["companies"] = list(self.companies)
        return payload


@dataclass(frozen=True)
class CompanyRefreshResult:
    company_name: str
    cvm_code: int
    requested_years: tuple[int, ...]
    years_processed: tuple[int, ...]
    rows_inserted: int
    status: str
    attempts: int
    error: str | None = None
    traceback: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CompanyRefreshResult":
        return cls(
            company_name=str(payload.get("company_name") or ""),
            cvm_code=int(payload.get("cvm_code") or 0),
            requested_years=_coerce_int_tuple(payload.get("requested_years")),
            years_processed=_coerce_int_tuple(payload.get("years_processed")),
            rows_inserted=int(payload.get("rows_inserted") or 0),
            status=str(payload.get("status") or "error"),
            attempts=int(payload.get("attempts") or 0),
            error=payload.get("error"),
            traceback=payload.get("traceback"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["requested_years"] = list(self.requested_years)
        payload["years_processed"] = list(self.years_processed)
        return payload


@dataclass(frozen=True)
class RefreshResult:
    request: RefreshRequest
    companies: tuple[CompanyRefreshResult, ...]
    planning_stats: dict[str, int]
    synced_companies: int = 0
    cancelled: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for row in self.companies if row.status == "success")

    @property
    def no_data_count(self) -> int:
        return sum(1 for row in self.companies if row.status == "no_data")

    @property
    def error_count(self) -> int:
        return sum(1 for row in self.companies if row.status not in {"success", "no_data"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "planning_stats": dict(self.planning_stats),
            "synced_companies": int(self.synced_companies),
            "cancelled": bool(self.cancelled),
            "summary": {
                "success_count": self.success_count,
                "no_data_count": self.no_data_count,
                "error_count": self.error_count,
            },
            "companies": [row.to_dict() for row in self.companies],
        }


@dataclass(frozen=True)
class RefreshDispatchDTO:
    status: str
    cd_cvm: int
    job_id: str | None
    accepted_at: str
    message: str
    status_reason_code: str | None = None
    status_reason_message: str | None = None
    is_retry_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RefreshProgressUpdate:
    stage: str
    current: int
    total: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanySearchResult:
    cd_cvm: int
    company_name: str
    ticker_b3: str | None
    setor_analitico: str | None
    setor_cvm: str | None
    sector_name: str
    sector_slug: str
    anos_disponiveis: tuple[int, ...]
    total_rows: int
    has_financial_data: bool
    coverage_rank: int | None
    gics_sector: str | None = None
    gics_sector_slug: str | None = None
    gics_industry_group: str | None = None
    gics_industry: str | None = None
    gics_sub_industry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["anos_disponiveis"] = list(self.anos_disponiveis)
        return payload


@dataclass(frozen=True)
class CompanyInfoDTO:
    cd_cvm: int
    company_name: str
    nome_comercial: str | None
    cnpj: str | None
    setor_cvm: str | None
    setor_analitico: str | None
    company_type: str | None
    ticker_b3: str | None
    has_local_financial_reports: bool = False
    read_model_updated_at: str | None = None
    has_readable_current_data: bool = False
    readable_years_count: int = 0
    latest_readable_year: int | None = None
    read_availability_code: str | None = None
    read_availability_message: str | None = None
    gics_sector: str | None = None
    gics_sector_slug: str | None = None
    gics_industry_group: str | None = None
    gics_industry: str | None = None
    gics_sub_industry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanyDirectoryPagination:
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanyDirectoryAppliedFilters:
    search: str
    sector: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanyDirectoryPage:
    items: tuple[CompanySearchResult, ...]
    pagination: CompanyDirectoryPagination
    applied_filters: CompanyDirectoryAppliedFilters

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "pagination": self.pagination.to_dict(),
            "applied_filters": self.applied_filters.to_dict(),
        }


@dataclass(frozen=True)
class CompanySectorFilterOption:
    sector_name: str
    sector_slug: str
    company_count: int
    gics_sector: str | None = None
    gics_sector_slug: str | None = None
    gics_sub_industry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompanyFiltersDTO:
    sectors: tuple[CompanySectorFilterOption, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"sectors": [row.to_dict() for row in self.sectors]}


@dataclass(frozen=True)
class CompanySuggestionDTO:
    cd_cvm: int
    company_name: str
    ticker_b3: str | None
    sector_slug: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorSnapshotDTO:
    roe: float | None
    mg_ebit: float | None
    mg_liq: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SubIndustryCountDTO:
    name: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count}


@dataclass(frozen=True)
class SectorDirectoryItemDTO:
    sector_name: str
    sector_slug: str
    company_count: int
    latest_year: int | None
    snapshot: SectorSnapshotDTO
    sub_industries: tuple[str, ...] = ()
    sub_industry_breakdown: tuple[SubIndustryCountDTO, ...] = ()
    group_type: str = "sector"
    parent_sector_name: str | None = None
    parent_sector_slug: str | None = None
    companies: tuple[SectorCompanyMetricDTO, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["snapshot"] = self.snapshot.to_dict()
        payload["sub_industry_breakdown"] = [row.to_dict() for row in self.sub_industry_breakdown]
        payload["companies"] = [row.to_dict() for row in self.companies]
        return payload


@dataclass(frozen=True)
class SectorDirectoryDTO:
    items: tuple[SectorDirectoryItemDTO, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"items": [item.to_dict() for item in self.items]}


@dataclass(frozen=True)
class SectorYearOverviewDTO:
    year: int
    roe: float | None
    mg_ebit: float | None
    mg_liq: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorCompanyMetricDTO:
    cd_cvm: int
    company_name: str
    ticker_b3: str | None
    gics_sub_industry: str | None
    roe: float | None
    mg_ebit: float | None
    mg_liq: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorDetailDTO:
    sector_name: str
    sector_slug: str
    company_count: int
    available_years: tuple[int, ...]
    selected_year: int
    yearly_overview: tuple[SectorYearOverviewDTO, ...]
    companies: tuple[SectorCompanyMetricDTO, ...]
    # When this DTO represents a GICS sub-industry, parent_* carry the parent
    # GICS sector for breadcrumb/route rendering. None for top-level sectors.
    parent_sector_name: str | None = None
    parent_sector_slug: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_name": self.sector_name,
            "sector_slug": self.sector_slug,
            "company_count": self.company_count,
            "available_years": list(self.available_years),
            "selected_year": self.selected_year,
            "yearly_overview": [row.to_dict() for row in self.yearly_overview],
            "companies": [row.to_dict() for row in self.companies],
            "parent_sector_name": self.parent_sector_name,
            "parent_sector_slug": self.parent_sector_slug,
        }


@dataclass(frozen=True)
class StatementMatrix:
    cd_cvm: int
    statement_type: str
    years: tuple[int, ...]
    table: TabularData
    exclude_conflicts: bool = True

    def to_dataframe(self) -> pd.DataFrame:
        return self.table.to_dataframe()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["years"] = list(self.years)
        payload["table"] = self.table.to_dict()
        return payload


@dataclass(frozen=True)
class KPIBundle:
    cd_cvm: int
    years: tuple[int, ...]
    annual: TabularData
    quarterly: TabularData

    def annual_dataframe(self) -> pd.DataFrame:
        return self.annual.to_dataframe()

    def quarterly_dataframe(self) -> pd.DataFrame:
        return self.quarterly.to_dataframe()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cd_cvm": int(self.cd_cvm),
            "years": list(self.years),
            "annual": self.annual.to_dict(),
            "quarterly": self.quarterly.to_dict(),
        }


@dataclass(frozen=True)
class SummaryBlockDTO:
    stmt_type: str
    title: str
    table: TabularData

    def to_dict(self) -> dict[str, Any]:
        return {"stmt_type": self.stmt_type, "title": self.title, "table": self.table.to_dict()}


@dataclass(frozen=True)
class StatementSummaryDTO:
    cd_cvm: int
    years: tuple[int, ...]
    blocks: tuple[SummaryBlockDTO, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cd_cvm": int(self.cd_cvm),
            "years": list(self.years),
            "blocks": [b.to_dict() for b in self.blocks],
        }


@dataclass(frozen=True)
class RefreshStatusDTO:
    cd_cvm: int
    company_name: str
    source_scope: str | None = None
    job_id: str | None = None
    stage: str | None = None
    queue_position: int | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_start_year: int | None = None
    last_end_year: int | None = None
    last_rows_inserted: int | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_message: str | None = None
    started_at: str | None = None
    heartbeat_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
    read_model_updated_at: str | None = None
    estimated_progress_pct: float | None = None
    estimated_eta_seconds: int | None = None
    estimated_total_seconds: int | None = None
    elapsed_seconds: int | None = None
    estimated_completion_at: str | None = None
    estimate_confidence: str | None = None
    tracking_state: str | None = None
    progress_mode: str | None = None
    is_retry_allowed: bool = False
    status_reason_code: str | None = None
    status_reason_message: str | None = None
    has_readable_current_data: bool = False
    readable_years_count: int = 0
    latest_readable_year: int | None = None
    latest_attempt_outcome: str | None = None
    latest_attempt_reason_code: str | None = None
    latest_attempt_reason_message: str | None = None
    latest_attempt_retryable: bool = False
    read_availability_code: str | None = None
    read_availability_message: str | None = None
    freshness_summary_code: str | None = None
    freshness_summary_message: str | None = None
    freshness_summary_severity: str | None = None
    source_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankedRefreshQueueItem:
    cd_cvm: int
    company_name: str
    coverage_rank: int | None
    status: str
    last_status: str | None
    missing_years_count: int
    years_missing: tuple[int, ...]
    note: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["years_missing"] = list(self.years_missing)
        return payload


@dataclass(frozen=True)
class RankedRefreshQueueResult:
    start_year: int
    end_year: int
    requested_limit: int
    total_ranked: int
    queued_count: int
    already_queued_count: int
    no_data_excluded_count: int
    already_complete_count: int
    dispatch_failed_count: int
    items: tuple[RankedRefreshQueueItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_year": int(self.start_year),
            "end_year": int(self.end_year),
            "requested_limit": int(self.requested_limit),
            "total_ranked": int(self.total_ranked),
            "queued_count": int(self.queued_count),
            "already_queued_count": int(self.already_queued_count),
            "no_data_excluded_count": int(self.no_data_excluded_count),
            "already_complete_count": int(self.already_complete_count),
            "dispatch_failed_count": int(self.dispatch_failed_count),
            "items": [row.to_dict() for row in self.items],
        }


@dataclass(frozen=True)
class HealthYearCoverage:
    year: int
    total_companies: int
    completed: int
    missing: int
    pct: float
    eta_hours: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HealthPriority:
    cd_cvm: int
    company_name: str
    risk_level: str
    priority_score: int
    missing_years_count: int
    gap_to_leader_years: int
    years_missing: tuple[int, ...]
    recommended_action: str
    reason: str
    coverage_rank: int | None = None
    last_status: str | None = None
    excluded_from_queue: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HealthPriority":
        return cls(
            cd_cvm=int(payload.get("cd_cvm") or 0),
            company_name=str(payload.get("company_name") or ""),
            coverage_rank=(
                int(payload.get("coverage_rank"))
                if payload.get("coverage_rank") is not None
                else None
            ),
            last_status=(
                str(payload.get("last_status"))
                if payload.get("last_status") is not None
                else None
            ),
            excluded_from_queue=bool(payload.get("excluded_from_queue")),
            risk_level=str(payload.get("risk_level") or ""),
            priority_score=int(payload.get("priority_score") or 0),
            missing_years_count=int(payload.get("missing_years_count") or 0),
            gap_to_leader_years=int(payload.get("gap_to_leader_years") or 0),
            years_missing=_coerce_int_tuple(payload.get("years_missing")),
            recommended_action=str(payload.get("recommended_action") or ""),
            reason=str(payload.get("reason") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["years_missing"] = list(self.years_missing)
        return payload


@dataclass(frozen=True)
class HealthSnapshot:
    generated_at: str | None
    start_year: int
    end_year: int
    total_cells: int
    completed_cells: int
    missing_cells: int
    pct: float
    health_score: float
    health_status: str
    eta_hours: float | None
    throughput_per_hour: float | None
    throughput_confidence: str
    per_year: tuple[HealthYearCoverage, ...]
    prioritized_companies: tuple[HealthPriority, ...]
    raw: dict[str, Any]
    total_companies: int = 0
    companies_with_historical_data: int = 0
    companies_without_historical_data: int = 0
    companies_with_any_local_financial_report: int = 0
    companies_partial_local: int = 0
    companies_fully_updated: int = 0
    companies_with_refresh_status_recorded: int = 0
    companies_with_last_refresh_error: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "HealthSnapshot":
        global_stats = payload.get("global", {})
        throughput = payload.get("throughput", {})
        per_year_rows = tuple(
            HealthYearCoverage(
                year=int(row.get("year") or 0),
                total_companies=int(row.get("total_companies") or 0),
                completed=int(row.get("completed") or 0),
                missing=int(row.get("missing") or 0),
                pct=float(row.get("pct") or 0.0),
                eta_hours=(
                    float(row.get("eta_hours"))
                    if row.get("eta_hours") is not None
                    else None
                ),
            )
            for row in payload.get("per_year", [])
        )
        priorities = tuple(
            HealthPriority.from_payload(row)
            for row in payload.get("prioritized_companies", [])
        )
        company_inventory = payload.get("company_inventory", {})
        total_companies = int(
            company_inventory.get("total_companies")
            or global_stats.get("active_universe")
            or 0
        )
        companies_with_historical_data = int(
            company_inventory.get("companies_with_historical_data")
            or global_stats.get("companies_with_historical_data")
            or 0
        )
        companies_with_any_local_financial_report = int(
            company_inventory.get("companies_with_any_local_financial_report") or 0
        )
        companies_partial_local = int(company_inventory.get("companies_partial_local") or 0)
        companies_fully_updated = int(company_inventory.get("companies_fully_updated") or 0)
        companies_with_refresh_status_recorded = int(
            company_inventory.get("companies_with_refresh_status_recorded") or 0
        )
        companies_with_last_refresh_error = int(
            company_inventory.get("companies_with_last_refresh_error") or 0
        )
        return cls(
            generated_at=payload.get("generated_at"),
            start_year=int(payload.get("start_year") or 0),
            end_year=int(payload.get("end_year") or 0),
            total_cells=int(global_stats.get("total_cells") or 0),
            completed_cells=int(global_stats.get("completed_cells") or 0),
            missing_cells=int(global_stats.get("missing_cells") or 0),
            pct=float(global_stats.get("pct") or 0.0),
            health_score=float(payload.get("health_score") or 0.0),
            health_status=str(payload.get("health_status") or ""),
            eta_hours=(
                float(global_stats.get("eta_hours"))
                if global_stats.get("eta_hours") is not None
                else None
            ),
            throughput_per_hour=(
                float(throughput.get("per_hour"))
                if throughput.get("per_hour") is not None
                else None
            ),
            throughput_confidence=str(throughput.get("confidence") or "low"),
            per_year=per_year_rows,
            prioritized_companies=priorities,
            raw=dict(payload),
            total_companies=total_companies,
            companies_with_historical_data=companies_with_historical_data,
            companies_without_historical_data=max(
                0,
                total_companies - companies_with_historical_data,
            ),
            companies_with_any_local_financial_report=companies_with_any_local_financial_report,
            companies_partial_local=companies_partial_local,
            companies_fully_updated=companies_fully_updated,
            companies_with_refresh_status_recorded=companies_with_refresh_status_recorded,
            companies_with_last_refresh_error=companies_with_last_refresh_error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "total_cells": self.total_cells,
            "completed_cells": self.completed_cells,
            "missing_cells": self.missing_cells,
            "pct": self.pct,
            "health_score": self.health_score,
            "health_status": self.health_status,
            "eta_hours": self.eta_hours,
            "throughput_per_hour": self.throughput_per_hour,
            "throughput_confidence": self.throughput_confidence,
            "per_year": [row.to_dict() for row in self.per_year],
            "prioritized_companies": [row.to_dict() for row in self.prioritized_companies],
            "raw": dict(self.raw),
            "total_companies": self.total_companies,
            "companies_with_historical_data": self.companies_with_historical_data,
            "companies_without_historical_data": self.companies_without_historical_data,
            "companies_with_any_local_financial_report": self.companies_with_any_local_financial_report,
            "companies_partial_local": self.companies_partial_local,
            "companies_fully_updated": self.companies_fully_updated,
            "companies_with_refresh_status_recorded": self.companies_with_refresh_status_recorded,
            "companies_with_last_refresh_error": self.companies_with_last_refresh_error,
        }
