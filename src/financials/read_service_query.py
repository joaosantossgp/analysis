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
from src.platform.contracts import (
    CompanyDirectoryAppliedFilters,
    CompanyDirectoryPage,
    CompanyDirectoryPagination,
    CompanyFiltersDTO,
    CompanyFinancialPeriodDTO,
    CompanyFinancialReadinessDTO,
    CompanyInfoDTO,
    CompanySectorFilterOption,
    CompanySearchResult,
    CompanySuggestionDTO,
    HealthSnapshot,
    KPIBundle,
    RankedRefreshQueueItem,
    RankedRefreshQueueResult,
    RefreshBatchSelection,
    RefreshDispatchDTO,
    RefreshRequest,
    RefreshStatusDTO,
    SectorCompanyMetricDTO,
    SectorDetailDTO,
    SectorDirectoryDTO,
    SectorDirectoryItemDTO,
    SectorSnapshotDTO,
    SubIndustryCountDTO,
    SectorYearOverviewDTO,
    StatementMatrix,
    StatementSummaryDTO,
    SummaryBlockDTO,
    TabularData,
    default_incremental_refresh_policy,
)
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

from src.financials.read_service_refresh_selection import (
    BATCH_REFRESH_FAILED_STATES,
    BATCH_REFRESH_MAX_PAGE_SIZE,
    EXPORT_STATEMENT_TYPES,
    POPULARES_CVM_IDS,
    RefreshAlreadyActiveError,
    _parse_years,
    resolve_refresh_batch_selection,
    resolve_refresh_year_range,
)


class ReadServiceQueryMixin:
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()
        self.engine = build_engine(self.settings)
        self.query_layer = CVMQueryLayer(engine=self.engine)
        self.refresh_job_repository = RefreshJobRepository(self.engine)
        self.excel_mapping_repository = ExcelMappingRepository(self.engine)
        self._company_catalog = None
        self._operational_service = None
        self._refresh_service = None
        self._read_cache_data_version: int | None = None
        self._read_cache_checked_at = 0.0
        self._company_universe_cache: tuple[CompanySearchResult, ...] | None = None
        self._company_universe_light_cache: tuple[CompanySearchResult, ...] | None = None
        self._merged_company_catalog_cache: tuple[CompanySearchResult, ...] | None = None
        self._merged_company_catalog_light_cache: tuple[CompanySearchResult, ...] | None = None
        self._company_page_cache: dict[tuple[str, str | None, int, int], CompanyDirectoryPage] = {}
        self._market_cap_page_cache: dict[tuple[str, str | None, int, int], CompanyDirectoryPage] = {}
        self._local_company_catalog_is_sufficient_cache: bool | None = None
        self._company_filters_cache: CompanyFiltersDTO | None = None
        self._market_cap_index_cache: tuple[dict[int, Any], dict[str, Any], list[Any]] | None = None
        self._market_cap_index_mtime: float | None = None
        self._sector_directory_cache: dict[tuple[str, bool], SectorDirectoryDTO] = {}
        self._sector_metric_rows_cache: pd.DataFrame | None = None
        self._health_snapshot_cache: dict[tuple[int, int], HealthSnapshot] = {}

    def invalidate_read_caches(self) -> None:
        self._company_universe_cache = None
        self._company_universe_light_cache = None
        self._merged_company_catalog_cache = None
        self._merged_company_catalog_light_cache = None
        self._company_page_cache.clear()
        self._market_cap_page_cache.clear()
        self._local_company_catalog_is_sufficient_cache = None
        self._company_filters_cache = None
        self._market_cap_index_cache = None
        self._market_cap_index_mtime = None
        self._sector_directory_cache.clear()
        self._sector_metric_rows_cache = None
        self._clear_sector_directory_persistent_cache()
        self._clear_base_health_persistent_cache()
        self._health_snapshot_cache.clear()
        self._read_cache_data_version = None
        self._read_cache_checked_at = 0.0
        self.get_available_years.cache_clear()
        self.get_available_export_periods.cache_clear()
        self.suggest_companies.cache_clear()
        self.query_layer.get_sector_years_map.cache_clear()

    def _current_read_cache_data_version(self) -> int:
        if self.engine.dialect.name != "sqlite":
            return -1
        try:
            with self.engine.connect() as conn:
                value = conn.exec_driver_sql("PRAGMA data_version").scalar()
        except Exception:
            return -1
        return int(value or 0)

    def _ensure_read_cache_fresh(self) -> None:
        now = time.monotonic()
        if (
            self._read_cache_data_version is not None
            and now - self._read_cache_checked_at < self.READ_CACHE_VERSION_CHECK_SECONDS
        ):
            return

        data_version = self._current_read_cache_data_version()
        self._read_cache_checked_at = now
        if self._read_cache_data_version is None:
            self._read_cache_data_version = data_version
            return
        if data_version == self._read_cache_data_version:
            return
        self.invalidate_read_caches()
        self._read_cache_data_version = data_version

    @property
    def operational_service(self):
        if self._operational_service is None:
            from desktop.services import IntelligentSelectorService
            self._operational_service = IntelligentSelectorService(settings=self.settings)
        return self._operational_service

    @property
    def refresh_service(self) -> HeadlessRefreshService:
        if self._refresh_service is None:
            self._refresh_service = HeadlessRefreshService(settings=self.settings)
        return self._refresh_service

    @property
    def company_catalog(self) -> CompanyCatalogService:
        if self._company_catalog is None:
            self._company_catalog = CompanyCatalogService(
                timeout=self.settings.company_list_timeout
            )
        return self._company_catalog

    def resolve_batch_refresh_selection(
        self,
        params: dict[str, Any] | None = None,
        *,
        mode: str = "missing",
        default_start_year: int = 2010,
        max_page_size: int = BATCH_REFRESH_MAX_PAGE_SIZE,
    ) -> RefreshBatchSelection:
        return resolve_refresh_batch_selection(
            self,
            params,
            mode=mode,
            default_start_year=default_start_year,
            max_page_size=max_page_size,
        )

    def search_companies(self, search: str = "") -> list[CompanySearchResult]:
        df = self.query_layer.get_companies(search)
        return self._build_company_results(df)

    def search_companies_df(self, search: str = "") -> pd.DataFrame:
        rows = [row.to_dict() for row in self.search_companies(search)]
        return pd.DataFrame(rows)

    def get_company_info(
        self,
        cd_cvm: int,
        *,
        allow_catalog_lookup: bool = True,
    ) -> CompanyInfoDTO | None:
        payload = self.query_layer.get_company_info_with_read_model_state(cd_cvm)
        if payload:
            payload = self._enrich_company_identity_fallback(payload, default_cd_cvm=cd_cvm)
            return self._apply_company_read_model_state(
                self._build_company_info_dto(payload, default_cd_cvm=cd_cvm),
                payload,
            )

        if not allow_catalog_lookup:
            return None

        catalog_entry = self.company_catalog.lookup_company(cd_cvm)
        if catalog_entry is None:
            return None
        return self._with_company_read_model_state(
            self._build_company_info_dto(
                self._enrich_company_identity_fallback(
                    self._company_catalog_payload(catalog_entry),
                    default_cd_cvm=cd_cvm,
                ),
                default_cd_cvm=cd_cvm,
            )
        )

    def get_company_info_dict(self, cd_cvm: int) -> dict[str, Any]:
        info = self.get_company_info(cd_cvm)
        return info.to_dict() if info else {}

    def get_company_financial_readiness(
        self,
        cd_cvm: int,
    ) -> CompanyFinancialReadinessDTO:
        code = int(cd_cvm)
        state = self.query_layer.get_company_info_with_read_model_state(code)
        refresh_record = self._get_company_financial_refresh_record(code)
        has_local_reports = bool(state.get("has_local_financial_reports"))

        complete_periods = (
            self.query_layer.get_company_complete_periods(code)
            if has_local_reports
            else []
        )
        available_periods = tuple(
            CompanyFinancialPeriodDTO(
                period_label=str(period["period_label"]),
                period_display=str(period["period_display"]),
                period_type=str(period["period_type"]),
                period_year=int(period["period_year"]),
                period_quarter=(
                    int(period["period_quarter"])
                    if period.get("period_quarter") is not None
                    else None
                ),
            )
            for period in complete_periods
        )

        export_periods = (
            self.query_layer.get_available_export_periods(code)
            if has_local_reports
            else {"all_export_years": []}
        )
        exportable_years = tuple(
            int(year) for year in export_periods.get("all_export_years", [])
        )
        availability_state = self._financial_availability_state(
            has_local_reports=has_local_reports,
            complete_periods=available_periods,
        )
        refresh_state = self._financial_refresh_state(refresh_record)
        freshness_state = self._financial_freshness_state(
            availability_state=availability_state,
            refresh_state=refresh_state,
        )
        local_read_model_updated_at = self._none_if_blank(
            state.get("read_model_updated_at")
        )
        last_successful_refresh_at = self._none_if_blank(
            refresh_record.get("last_success_at")
        )

        return CompanyFinancialReadinessDTO(
            cd_cvm=code,
            source_class="official_reported",
            source_label="CVM DFP/ITR filings",
            availability_state=availability_state,
            freshness_state=freshness_state,
            refresh_state=refresh_state,
            has_local_financial_reports=has_local_reports,
            available_periods=available_periods,
            local_read_model_updated_at=local_read_model_updated_at,
            last_successful_refresh_at=last_successful_refresh_at,
            latest_local_evidence_at=self._latest_iso_timestamp(
                local_read_model_updated_at,
                last_successful_refresh_at,
            ),
            last_refresh_error=self._none_if_blank(refresh_record.get("last_error")),
            financial_export_eligible=bool(exportable_years),
            exportable_years=exportable_years,
        )

    def _get_company_financial_refresh_record(self, cd_cvm: int) -> dict[str, Any]:
        inspector = inspect(self.engine)
        if not inspector.has_table("company_refresh_status"):
            return {}

        columns = {
            str(column.get("name") or "").lower()
            for column in inspector.get_columns("company_refresh_status")
        }
        select_columns = [
            "last_status" if "last_status" in columns else "NULL AS last_status",
            "last_error" if "last_error" in columns else "NULL AS last_error",
            (
                "last_success_at"
                if "last_success_at" in columns
                else "NULL AS last_success_at"
            ),
        ]
        sql = text(
            f"""
            SELECT {", ".join(select_columns)}
            FROM company_refresh_status
            WHERE cd_cvm = :cd_cvm
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"cd_cvm": int(cd_cvm)}).mappings().first()
        return dict(row) if row is not None else {}

    @staticmethod
    def _financial_availability_state(
        *,
        has_local_reports: bool,
        complete_periods: tuple[CompanyFinancialPeriodDTO, ...],
    ) -> str:
        if complete_periods:
            return "ready"
        if has_local_reports:
            return "partial"
        return "missing"

    @staticmethod
    def _financial_refresh_state(refresh_record: dict[str, Any]) -> str:
        raw_status = str(refresh_record.get("last_status") or "").strip().lower()
        if not raw_status:
            return "not_recorded"
        if raw_status == "success":
            return "successful"
        if raw_status in BATCH_REFRESH_FAILED_STATES:
            return "failed"
        if raw_status in {"queued", "running", "in_progress"}:
            return "in_progress"
        if raw_status == "no_data":
            return "no_data"
        return raw_status

    @staticmethod
    def _financial_freshness_state(
        *,
        availability_state: str,
        refresh_state: str,
    ) -> str:
        if availability_state != "ready":
            return "unknown"
        if refresh_state in {"failed", "no_data"}:
            return "stale"
        if refresh_state == "successful":
            return "fresh"
        return "unknown"

    @staticmethod
    def _none_if_blank(value: Any) -> str | None:
        if value is None:
            return None
        text_value = str(value).strip()
        return text_value or None

    @classmethod
    def _latest_iso_timestamp(cls, *values: str | None) -> str | None:
        candidates = [value for value in values if value]
        if not candidates:
            return None

        def parse(value: str) -> datetime | None:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        parsed = [(value, parse(value)) for value in candidates]
        if all(dt is not None for _, dt in parsed):
            return max(parsed, key=lambda item: item[1] or datetime.min)[0]
        return candidates[0]

    @functools.lru_cache(maxsize=10)
    def get_available_years(self, cd_cvm: int) -> list[int]:
        return self.query_layer.get_available_years(cd_cvm)

    def get_available_statements(self, cd_cvm: int) -> list[str]:
        return self.query_layer.get_available_statements(cd_cvm)

    @staticmethod
    def _company_catalog_payload(entry: CompanyCatalogEntry) -> dict[str, Any]:
        return {
            "cd_cvm": int(entry.cd_cvm),
            "company_name": entry.company_name,
            "nome_comercial": entry.nome_comercial,
            "cnpj": entry.cnpj,
            "setor_cvm": entry.setor_cvm,
            "setor_analitico": None,
            "company_type": "comercial",
            "ticker_b3": entry.ticker_b3,
        }

    @staticmethod
    def _is_synthetic_company_name(value: object, cd_cvm: int) -> bool:
        return isinstance(value, str) and value.strip().casefold() == f"cvm_{cd_cvm}".casefold()

    def _enrich_company_identity_fallback(
        self,
        payload: dict[str, Any],
        *,
        default_cd_cvm: int,
    ) -> dict[str, Any]:
        resolved_cd_cvm = int(payload.get("cd_cvm") or default_cd_cvm)
        has_synthetic_name = self._is_synthetic_company_name(
            payload.get("company_name"),
            resolved_cd_cvm,
        )
        if payload.get("ticker_b3") and payload.get("cnpj") and not has_synthetic_name:
            return payload
        try:
            from src.companies.identity import CompanyIdentityResolver  # noqa: PLC0415

            identity = CompanyIdentityResolver(engine=self.engine).resolve(
                resolved_cd_cvm
            )
        except Exception:
            identity = None

        enriched = dict(payload)
        if has_synthetic_name:
            try:
                catalog_identity = self.company_catalog.lookup_company(resolved_cd_cvm)
            except Exception:
                catalog_identity = None
            catalog_name = str(getattr(catalog_identity, "company_name", "") or "").strip()
            if catalog_name:
                enriched["company_name"] = catalog_name

        if identity is None:
            return enriched

        if not enriched.get("ticker_b3") and identity.ticker_b3:
            ticker = str(identity.ticker_b3).strip().upper()
            if ticker.endswith(".SA"):
                ticker = ticker[:-3]
            if ticker and not ticker.isdigit():
                enriched["ticker_b3"] = ticker
        if not enriched.get("cnpj") and identity.cnpj:
            enriched["cnpj"] = identity.cnpj
        return enriched

    @staticmethod
    def _build_company_info_dto(
        payload: dict[str, Any],
        *,
        default_cd_cvm: int,
    ) -> CompanyInfoDTO:
        sector_name = canonical_sector_name(
            payload.get("setor_analitico"),
            payload.get("setor_cvm"),
        )
        company_name = str(payload.get("company_name") or "").strip() or f"CVM_{default_cd_cvm}"
        company_type = str(payload.get("company_type") or "comercial").strip() or "comercial"
        gics = resolve_gics_classification(
            sector_name=sector_name,
            setor_analitico=payload.get("setor_analitico"),
            setor_cvm=payload.get("setor_cvm"),
            gics_sector=payload.get("gics_sector"),
            gics_sector_slug=payload.get("gics_sector_slug"),
            gics_industry_group=payload.get("gics_industry_group"),
            gics_industry=payload.get("gics_industry"),
            gics_sub_industry=payload.get("gics_sub_industry"),
        )
        return CompanyInfoDTO(
            cd_cvm=int(payload.get("cd_cvm") or default_cd_cvm),
            company_name=company_name,
            nome_comercial=payload.get("nome_comercial"),
            cnpj=payload.get("cnpj"),
            setor_cvm=payload.get("setor_cvm"),
            setor_analitico=payload.get("setor_analitico"),
            sector_name=sector_name,
            sector_slug=sector_slugify(sector_name),
            company_type=company_type,
            ticker_b3=payload.get("ticker_b3"),
            is_active=bool(payload.get("is_active") if payload.get("is_active") is not None else 1),
            gics_sector=gics.gics_sector if gics else None,
            gics_sector_slug=gics.gics_sector_slug if gics else None,
            gics_industry_group=gics.gics_industry_group if gics else None,
            gics_industry=gics.gics_industry if gics else None,
            gics_sub_industry=gics.gics_sub_industry if gics else None,
        )

    def _with_company_read_model_state(self, dto: CompanyInfoDTO) -> CompanyInfoDTO:
        state = self._load_company_read_model_state_map([dto.cd_cvm]).get(
            int(dto.cd_cvm),
            {},
        )
        return self._apply_company_read_model_state(dto, state)

    def _apply_company_read_model_state(
        self,
        dto: CompanyInfoDTO,
        state: dict[str, Any],
    ) -> CompanyInfoDTO:
        readable_years_count = int(state.get("readable_years_count") or 0)
        latest_readable_year = (
            int(state["latest_readable_year"])
            if state.get("latest_readable_year") is not None
            else None
        )
        latest_financial_period_year = (
            int(state["latest_financial_period_year"])
            if state.get("latest_financial_period_year") is not None
            else None
        )
        latest_financial_period_quarter = (
            int(state["latest_financial_period_quarter"])
            if state.get("latest_financial_period_quarter") is not None
            else None
        )
        read_availability = self._build_read_availability_summary(
            has_readable_current_data=bool(state.get("has_readable_current_data")),
            readable_years_count=readable_years_count,
            latest_readable_year=latest_readable_year,
        )
        raw_local = state.get("has_local_financial_reports")
        has_local_financial_reports = (
            bool(raw_local) if raw_local is not None else dto.has_local_financial_reports
        )
        return replace(
            dto,
            read_model_updated_at=state.get("read_model_updated_at"),
            has_local_financial_reports=has_local_financial_reports,
            has_readable_current_data=bool(state.get("has_readable_current_data")),
            readable_years_count=readable_years_count,
            latest_readable_year=latest_readable_year,
            readable_financial_periods_count=int(
                state.get("readable_financial_periods_count") or 0
            ),
            latest_financial_period_label=state.get("latest_financial_period_label"),
            latest_financial_period_display=state.get("latest_financial_period_display"),
            latest_financial_period_type=state.get("latest_financial_period_type"),
            latest_financial_period_year=latest_financial_period_year,
            latest_financial_period_quarter=latest_financial_period_quarter,
            read_availability_code=read_availability["code"],
            read_availability_message=read_availability["message"],
        )

    def _ensure_company_catalog_metadata(self, cd_cvm: int) -> bool:
        if self.query_layer.get_company_info(cd_cvm):
            return False

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

    def _load_market_cap_index(
        self,
    ) -> tuple[dict[int, Any], dict[str, Any], list[Any]] | None:
        """Load snapshot into (by_cd_cvm, by_ticker_stripped, all_entries).

        Returns None when no snapshot exists, the file is malformed, or any
        error occurs — callers must gracefully fall back to existing sort.
        File mtime gates re-parsing so parsing is skipped on repeated calls
        with an unchanged CSV.
        """
        from pathlib import Path as _Path  # noqa: PLC0415

        snapshot_path = _Path(self.settings.paths.company_universe_snapshot_path)
        if not snapshot_path.exists():
            return None
        try:
            mtime = snapshot_path.stat().st_mtime
        except OSError:
            return None

        if (
            self._market_cap_index_cache is not None
            and self._market_cap_index_mtime == mtime
        ):
            return self._market_cap_index_cache

        try:
            from src.companies.market_cap import MarketCapService  # noqa: PLC0415

            entries = MarketCapService(settings=self.settings).read_snapshot()
        except Exception as exc:
            import logging as _logging  # noqa: PLC0415
            _logging.getLogger(__name__).warning(
                "market-cap index load failed, skipping sort: %s", exc
            )
            return None

        if not entries:
            return None

        by_cd_cvm: dict[int, Any] = {}
        by_ticker: dict[str, Any] = {}
        for entry in entries:
            if entry.cd_cvm is not None:
                by_cd_cvm[entry.cd_cvm] = entry
            if entry.ticker:
                # Strip .SA suffix so "PETR4.SA" → "PETR4" matches ticker_b3 "PETR4"
                by_ticker[entry.ticker.replace(".SA", "").upper()] = entry

        self._market_cap_index_cache = (by_cd_cvm, by_ticker, entries)
        self._market_cap_index_mtime = mtime
        return self._market_cap_index_cache

    def _list_companies_with_market_cap_sort(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage | None:
        """Return a Companies page sorted by market-cap descending.

        Uses the local snapshot — no network calls.  Falls back (returns None)
        when the snapshot is unavailable or unreadable so the caller can
        transparently use the existing sort path.
        """
        normalized_search = str(search or "").strip().lower()
        normalized_sector_slug = str(sector_slug or "").strip().lower() or None
        cache_key = (
            normalized_search,
            normalized_sector_slug,
            int(page),
            int(page_size),
        )
        cached = self._market_cap_page_cache.get(cache_key)
        if cached is not None:
            return cached

        idx = self._load_market_cap_index()
        if idx is None:
            return None

        by_cd_cvm, by_ticker, all_entries = idx
        use_local_universe = (
            not normalized_search
            and normalized_sector_slug is None
            and self._has_sufficient_local_company_catalog()
        )
        all_items = (
            self._list_company_universe_results_light()
            if use_local_universe
            else self._merge_catalog_with_db(include_years=False)
        )

        # Filter DB companies
        filtered: list[CompanySearchResult] = []
        for item in all_items:
            if normalized_sector_slug and item.sector_slug != normalized_sector_slug:
                continue
            if normalized_search:
                tokens = [
                    item.company_name.lower(),
                    (item.ticker_b3 or "").lower(),
                    str(item.cd_cvm),
                ]
                if not any(normalized_search in t for t in tokens if t):
                    continue
            filtered.append(item)

        # Enrich DB companies with market cap; also fill ticker from snapshot when DB
        # has none (DFP import does not carry B3 ticker data).
        enriched: list[CompanySearchResult] = []
        mapped_count = 0
        for item in filtered:
            identity_payload = self._enrich_company_identity_fallback(
                {
                    "cd_cvm": item.cd_cvm,
                    "company_name": item.company_name,
                    "ticker_b3": item.ticker_b3,
                },
                default_cd_cvm=item.cd_cvm,
            )
            item = replace(
                item,
                company_name=str(identity_payload.get("company_name") or item.company_name),
                ticker_b3=identity_payload.get("ticker_b3") or item.ticker_b3,
            )
            entry = by_cd_cvm.get(item.cd_cvm)
            if entry is None and item.ticker_b3:
                # DB may store ticker with or without .SA suffix — normalise
                ticker_key = item.ticker_b3.upper().replace(".SA", "")
                entry = by_ticker.get(ticker_key)
            if entry is not None:
                mapped_count += 1
                snap_ticker = (
                    entry.ticker.replace(".SA", "").upper()
                    if entry.ticker
                    else None
                )
                item = replace(
                    item,
                    # Use snapshot ticker as fallback when DB ticker is null
                    ticker_b3=item.ticker_b3 or snap_ticker,
                    market_cap_brl=entry.market_cap_brl,
                    market_cap_rank=entry.rank,
                    market_cap_as_of_date=entry.as_of_date,
                    market_cap_source=entry.source,
                    market_cap_provider_status=entry.provider_status,
                    dividend_yield=entry.dividend_yield,
                    pe_ratio=entry.pe_ratio,
                    pb_ratio=entry.pb_ratio,
                    beta=entry.beta,
                )
            enriched.append(item)

        # Sort:
        #  1. Mapped companies → market_cap_brl DESC
        #  2. Unmapped but has financial data → matches old "data-first" UX
        #  3. Unmapped / no data → company_name ASC
        # Tier 2 preserves the pre-existing sort for companies not in the snapshot
        # (they have tickers/sectors; pure catalog stubs usually don't).
        enriched.sort(
            key=lambda c: (
                0 if c.market_cap_brl is not None else 1,
                -(c.market_cap_brl or 0.0),
                0 if c.has_financial_data else 1,
                c.company_name.lower(),
            )
        )

        # Snapshot-level metadata (from first entry — all share same date/source)
        meta = None
        if all_entries and len(all_entries) > 0:
            e0 = all_entries[0]
            from src.platform.contracts import MarketCapSortMeta  # noqa: PLC0415

            meta = MarketCapSortMeta(
                as_of_date=e0.as_of_date,
                source=e0.source,
                provider_status=e0.provider_status,
                mapped_count=len(all_entries),
                total_in_snapshot=len(all_entries),
            )

        # Paginate
        total_items = len(enriched)
        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        total_pages = max(1, ((total_items - 1) // int(page_size)) + 1) if total_items else 1
        page_items = enriched[start:end]
        page_years_map = self.query_layer.get_company_years_map(
            [int(item.cd_cvm) for item in page_items]
        )
        page_items = [
            replace(
                item,
                anos_disponiveis=tuple(page_years_map.get(int(item.cd_cvm), ())),
            )
            for item in page_items
        ]
        result = CompanyDirectoryPage(
            items=tuple(page_items),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=total_items,
                total_pages=total_pages,
                has_next=int(page) < total_pages,
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
            market_cap_sort_meta=meta,
        )
        self._market_cap_page_cache[cache_key] = result
        return result

    def list_companies(
        self,
        *,
        search: str = "",
        sector_slug: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CompanyDirectoryPage:
        self._ensure_read_cache_fresh()
        resolved_sector_name = self._resolve_sector_slug(sector_slug)
        if sector_slug and resolved_sector_name is None:
            return self._empty_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )
        if resolved_sector_name in GICS_11_SECTORS:
            return self._list_companies_by_gics_sector(
                search=search,
                sector_slug=sector_slug,
                gics_sector=resolved_sector_name,
                page=page,
                page_size=page_size,
            )

        # Try market-cap-sorted path when local snapshot is available.
        # Falls back transparently when snapshot is missing, malformed, or empty.
        mkt_page = self._list_companies_with_market_cap_sort(
            search=search,
            sector_slug=sector_slug,
            page=page,
            page_size=page_size,
        )
        if mkt_page is not None:
            return mkt_page

        catalog_page = self._list_companies_from_catalog(
            search=search,
            sector_slug=sector_slug,
            page=page,
            page_size=page_size,
        )
        if catalog_page is not None:
            return catalog_page

        rows_df, total_items = self.query_layer.get_companies_directory_page(
            search=search,
            sector_name=resolved_sector_name,
            page=page,
            page_size=page_size,
        )
        years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist()) if not rows_df.empty else {}
        if not rows_df.empty:
            rows_df = rows_df.copy()
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd_cvm: years_map.get(int(cd_cvm), ()))
            try:
                from sqlalchemy import text as _sa_text  # noqa: PLC0415
                import pandas as _pd  # noqa: PLC0415
                failed_df = _pd.read_sql(
                    _sa_text(
                        "SELECT cd_cvm FROM company_refresh_status "
                        "WHERE last_status IN ('error', 'failed', 'dispatch_failed')"
                    ),
                    self.query_layer.engine,
                )
                if not failed_df.empty:
                    failed_set = frozenset(int(x) for x in failed_df["cd_cvm"].dropna())
                    rows_df.loc[rows_df["cd_cvm"].isin(failed_set), "data_status"] = "failed"
            except Exception:
                pass

        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1) if total_items else 1
        pagination = CompanyDirectoryPagination(
            page=int(page),
            page_size=int(page_size),
            total_items=int(total_items),
            total_pages=int(total_pages),
            has_next=int(page) < int(total_pages),
            has_previous=int(page) > 1,
        )
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=pagination,
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def _list_companies_from_catalog(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage | None:
        normalized_search = str(search or "").strip().lower()
        normalized_sector_slug = str(sector_slug or "").strip().lower() or None
        if normalized_sector_slug is None and self._has_sufficient_local_company_catalog():
            local_page = self._list_local_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )
            return local_page

        universe_items = self._list_company_universe_results()
        if not universe_items:
            return None

        filtered: list[CompanySearchResult] = []
        for item in universe_items:
            current_sector_slug = item.sector_slug
            if normalized_sector_slug and current_sector_slug != normalized_sector_slug:
                continue

            if normalized_search:
                tokens = [
                    item.company_name.lower(),
                    (item.ticker_b3 or "").lower(),
                    str(item.cd_cvm),
                ]
                if not any(normalized_search in token for token in tokens if token):
                    continue
            filtered.append(item)

        filtered.sort(key=lambda item: (0 if item.has_financial_data else 1, item.company_name.lower()))
        total_items = len(filtered)
        if total_items == 0:
            return self._empty_company_page(
                search=search,
                sector_slug=sector_slug,
                page=page,
                page_size=page_size,
            )

        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        page_items = tuple(filtered[start:end])
        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1)
        return CompanyDirectoryPage(
            items=page_items,
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def _list_local_company_page(
        self,
        *,
        search: str,
        sector_slug: str | None,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        cache_key = (
            str(search or "").strip().lower(),
            str(sector_slug).strip().lower() if sector_slug else None,
            int(page),
            int(page_size),
        )
        cached = self._company_page_cache.get(cache_key)
        if cached is not None:
            return cached

        rows_df, total_items = self.query_layer.get_companies_directory_page(
            search=search,
            sector_name=None,
            page=page,
            page_size=page_size,
        )
        if not rows_df.empty:
            rows_df = rows_df.copy()
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        total_pages = max(1, ((int(total_items) - 1) // int(page_size)) + 1) if total_items else 1
        result = CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )
        self._company_page_cache[cache_key] = result
        return result

    def _has_sufficient_local_company_catalog(self) -> bool:
        if self._local_company_catalog_is_sufficient_cache is None:
            self._local_company_catalog_is_sufficient_cache = (
                len(self._load_local_active_company_rows())
                >= self.CATALOG_FALLBACK_MIN_LOCAL_COMPANIES
            )
        return self._local_company_catalog_is_sufficient_cache

    def get_populares_companies(self) -> CompanyDirectoryPage:
        """Returns top-10 B3 companies by market cap in static rank order.

        The ranking is maintained in POPULARES_CVM_IDS. Companies missing from
        the local DB (e.g. during seeding) are silently omitted.
        """
        ids = list(POPULARES_CVM_IDS)
        rows_df = self.query_layer.get_companies_by_cvm_ids(ids)
        if not rows_df.empty:
            order_map = {cd: i for i, cd in enumerate(ids)}
            rows_df = rows_df.copy()
            rows_df["_order"] = rows_df["cd_cvm"].map(lambda x: order_map.get(int(x), 999))
            rows_df = rows_df.sort_values("_order").drop(columns=["_order"]).reset_index(drop=True)
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd: years_map.get(int(cd), ()))
        n = len(rows_df)
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=1, page_size=n, total_items=n,
                total_pages=1, has_next=False, has_previous=False,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(search="", sector=None),
        )

    def get_em_destaque_companies(self, limit: int = 10) -> CompanyDirectoryPage:
        """Returns companies most visited globally, ordered by view_count DESC.

        Falls back gracefully to coverage_rank ordering when the company_views
        table is empty (e.g. immediately after deployment).
        """
        rows_df = self.query_layer.get_top_viewed_companies(limit=limit)
        if not rows_df.empty:
            rows_df = rows_df.copy()
            years_map = self.query_layer.get_company_years_map(rows_df["cd_cvm"].tolist())
            rows_df["anos_disponiveis"] = rows_df["cd_cvm"].map(lambda cd: years_map.get(int(cd), ()))
        n = len(rows_df)
        return CompanyDirectoryPage(
            items=tuple(self._build_company_results(rows_df)),
            pagination=CompanyDirectoryPagination(
                page=1, page_size=n, total_items=n,
                total_pages=1, has_next=False, has_previous=False,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(search="", sector=None),
        )

    def record_company_view(self, cd_cvm: int) -> None:
        """Increments the global view counter for a company.

        Uses an upsert so the call is idempotent and safe under concurrent
        writes. Silently ignores unknown cd_cvm values (FK constraint skips
        the insert rather than raising).
        """
        now_iso = now_iso_seconds()
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO company_views (cd_cvm, view_count, last_viewed_at)
                        VALUES (:cd, 1, :now)
                        ON CONFLICT(cd_cvm) DO UPDATE SET
                            view_count     = company_views.view_count + 1,
                            last_viewed_at = :now
                    """),
                    {"cd": int(cd_cvm), "now": now_iso},
                )
        except Exception:
            # Analytics must never break the API — log and continue
            import logging
            logging.getLogger(__name__).warning(
                "record_company_view failed for cd_cvm=%s", cd_cvm, exc_info=True
            )

    def get_company_filters(self) -> CompanyFiltersDTO:
        self._ensure_read_cache_fresh()
        if self._company_filters_cache is not None:
            return self._company_filters_cache

        sector_counts: dict[str, int] = defaultdict(int)
        for item in self._list_company_universe_results_light():
            if item.gics_sector and item.gics_sector in GICS_11_SECTORS:
                sector_counts[item.gics_sector] += 1

        sectors_list: list[CompanySectorFilterOption] = []
        for sector_name, company_count in sorted(sector_counts.items(), key=lambda item: gics_sector_sort_key(item[0])):
            sectors_list.append(
                CompanySectorFilterOption(
                    sector_name=sector_name,
                    sector_slug=sector_slugify(sector_name),
                    company_count=int(company_count),
                    gics_sector=sector_name,
                    gics_sector_slug=sector_slugify(sector_name),
                )
            )
        sectors = tuple(sectors_list)
        self._company_filters_cache = CompanyFiltersDTO(sectors=sectors)
        return self._company_filters_cache

    @staticmethod
    def _histogram_bucket_from_directory_row(row: pd.Series) -> str:
        """Align with query_layer._sector_bucket_expression_sql (persisted GICS over canonical setor)."""
        persisted_raw = row.get("persisted_gics_sector")
        canonical_raw = row.get("sector_name")
        persisted = None if persisted_raw is None or pd.isna(persisted_raw) else str(persisted_raw).strip()
        canonical = None if canonical_raw is None or pd.isna(canonical_raw) else str(canonical_raw).strip()
        if persisted:
            return persisted
        return canonical or "Nao classificado"

    @staticmethod
    def _hub_gics_key_for_histogram_bucket(bucket_label: str) -> str | None:
        """Histogram bucket label -> GICS 11 hub key (same resolution as filters / sector routing)."""
        return resolve_gics_sector_name(
            sector_name=bucket_label,
            setor_analitico=bucket_label,
            setor_cvm=bucket_label,
        )

    def _filter_directory_rows_by_hub_gics(
        self,
        rows_df: pd.DataFrame,
        hub_gics_sector: str,
    ) -> pd.DataFrame:
        if rows_df.empty:
            return rows_df

        def _row_matches(row: pd.Series) -> bool:
            bucket = self._histogram_bucket_from_directory_row(row)
            hub_key = self._hub_gics_key_for_histogram_bucket(bucket)
            return hub_key == hub_gics_sector

        mask = rows_df.apply(_row_matches, axis=1)
        return rows_df.loc[mask].reset_index(drop=True)

    @functools.lru_cache(maxsize=128)
    def suggest_companies(
        self,
        q: str,
        limit: int,
        *,
        ready_only: bool = False,
    ) -> tuple[CompanySuggestionDTO, ...]:
        df = self.query_layer.get_company_suggestions(
            q=q,
            limit=limit,
            ready_only=ready_only,
        )
        def _clean_gics(value: object) -> str | None:
            if value is None:
                return None
            text_value = str(value).strip()
            return text_value or None

        local_items = tuple(
            CompanySuggestionDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=str(row["ticker_b3"]) if row["ticker_b3"] else None,
                sector_slug=sector_slugify(str(row["sector_name"])),
                gics_sector=_clean_gics(row.get("gics_sector")),
                gics_sector_slug=_clean_gics(row.get("gics_sector_slug")),
            )
            for _, row in df.iterrows()
        )
        if ready_only or not str(q or "").strip() or len(local_items) >= int(limit):
            return local_items[: int(limit)]

        seen_codes = {item.cd_cvm for item in local_items}
        try:
            catalog_items = self.company_catalog.search_companies(
                q=q,
                limit=max(0, int(limit) - len(local_items)),
                exclude_codes=seen_codes,
            )
        except CompanyCatalogUnavailableError:
            return local_items[: int(limit)]

        fallback_items = tuple(
            CompanySuggestionDTO(
                cd_cvm=int(entry.cd_cvm),
                company_name=entry.company_name,
                ticker_b3=entry.ticker_b3,
                sector_slug=sector_slugify(
                    canonical_sector_name(None, entry.setor_cvm)
                ),
            )
            for entry in catalog_items
        )
        return (local_items + fallback_items)[: int(limit)]

    def resolve_sector_slug(self, sector_slug: str | None) -> str | None:
        return self._resolve_sector_slug(sector_slug)

    def list_sectors(self, group_by: str = "sector", *, include_snapshots: bool = True) -> SectorDirectoryDTO:
        self._ensure_read_cache_fresh()
        normalized_group_by = str(group_by or "sector").strip().lower()
        if normalized_group_by in {"sub_sector", "subsector", "sub-sector", "sub_setor", "sub-setor"}:
            normalized_group_by = "sub_sector"
        elif normalized_group_by in {"cvm_sector", "cvm-sector", "cvm_setor", "cvm-setor", "cvm"}:
            normalized_group_by = "cvm_sector"
        else:
            normalized_group_by = "sector"
        cache_key = (normalized_group_by, bool(include_snapshots))
        cached = self._sector_directory_cache.get(cache_key)
        if cached is not None:
            return cached
        if include_snapshots:
            persisted = self._load_sector_directory_persistent_cache(normalized_group_by)
            if persisted is not None:
                self._sector_directory_cache[cache_key] = persisted
                return persisted

        # Full unpaged directory so hub counts match the entire `companies` universe (not capped at
        # BATCH_REFRESH_MAX_PAGE_SIZE used for refresh batching).
        company_items = self._list_company_universe_results_light()
        companies_by_gics: dict[str, list[CompanySearchResult]] = defaultdict(list)
        companies_by_sub_sector: dict[str, list[CompanySearchResult]] = defaultdict(list)
        hub_counts: dict[str, int] = defaultdict(int)
        sub_industries_by_gics: dict[str, set[str]] = defaultdict(set)
        sub_industry_counts_by_gics: dict[str, Counter] = defaultdict(Counter)
        unclassified_items: list[CompanySearchResult] = []
        for item in company_items:
            sector_hub = item.gics_sector
            if not sector_hub or sector_hub not in GICS_11_SECTORS:
                unclassified_items.append(item)
                continue
            hub_counts[sector_hub] += 1
            companies_by_gics[sector_hub].append(item)
            if item.gics_sub_industry:
                sub_industries_by_gics[sector_hub].add(item.gics_sub_industry)
                sub_industry_counts_by_gics[sector_hub][item.gics_sub_industry] += 1
                companies_by_sub_sector[item.gics_sub_industry].append(item)

        metric_rows = self._get_sector_metric_rows() if include_snapshots else pd.DataFrame()
        if metric_rows is not None and not metric_rows.empty and company_items:
            gics_by_cd_cvm = {
                int(item.cd_cvm): item.gics_sector
                for item in company_items
                if item.gics_sector
            }
            metric_rows = metric_rows.copy()
            metric_rows["sector_name"] = metric_rows["cd_cvm"].map(
                lambda code: gics_by_cd_cvm.get(int(code))
            )
            metric_rows = metric_rows.dropna(subset=["sector_name"])
        yearly = self._aggregate_sector_yearly_metrics(metric_rows)

        latest_snapshot_by_sector: dict[str, tuple[int, pd.Series]] = {}
        if not yearly.empty:
            for sector_name, group_df in yearly.groupby("sector_name", dropna=False):
                if group_df.empty:
                    continue
                latest_idx = group_df["year"].astype(int).idxmax()
                latest_row = group_df.loc[latest_idx]
                latest_snapshot_by_sector[str(sector_name)] = (
                    int(latest_row["year"]),
                    latest_row,
                )

        items: list[SectorDirectoryItemDTO] = []

        if normalized_group_by == "sub_sector":
            for sub_sector_name, sub_items in sorted(companies_by_sub_sector.items(), key=lambda item: item[0]):
                parent_counts = Counter(item.gics_sector for item in sub_items if item.gics_sector)
                parent_sector_name = str(parent_counts.most_common(1)[0][0]) if parent_counts else None
                latest_year, snapshot_row = latest_snapshot_by_sector.get(
                    parent_sector_name or "",
                    (None, None),
                )
                items.append(
                    SectorDirectoryItemDTO(
                        sector_name=sub_sector_name,
                        sector_slug=sector_slugify(sub_sector_name),
                        company_count=len(sub_items),
                        latest_year=latest_year,
                        snapshot=SectorSnapshotDTO(
                            roe=self._coerce_optional_float(snapshot_row["roe"]) if snapshot_row is not None else None,
                            mg_ebit=self._coerce_optional_float(snapshot_row["mg_ebit"]) if snapshot_row is not None else None,
                            mg_liq=self._coerce_optional_float(snapshot_row["mg_liq"]) if snapshot_row is not None else None,
                        ),
                        group_type="sub_sector",
                        parent_sector_name=parent_sector_name,
                        parent_sector_slug=sector_slugify(parent_sector_name) if parent_sector_name else None,
                        companies=self._sector_company_preview(sub_items),
                    )
                )
        elif normalized_group_by == "cvm_sector":
            companies_by_cvm: dict[str, list[CompanySearchResult]] = defaultdict(list)
            for item in company_items:
                cvm_name = item.sector_name or item.setor_cvm or "Nao classificado"
                companies_by_cvm[cvm_name].append(item)
            for cvm_name, cvm_items in sorted(companies_by_cvm.items(), key=lambda x: x[0]):
                items.append(
                    SectorDirectoryItemDTO(
                        sector_name=cvm_name,
                        sector_slug=sector_slugify(cvm_name),
                        company_count=len(cvm_items),
                        latest_year=None,
                        snapshot=SectorSnapshotDTO(
                            roe=None,
                            mg_ebit=None,
                            mg_liq=None,
                        ),
                        group_type="cvm_sector",
                        companies=self._sector_company_preview(cvm_items),
                    )
                )
        else:
            candidate_sector_names = sorted(
                {name for name, count in hub_counts.items() if count > 0 and name in GICS_11_SECTORS},
                key=gics_sector_sort_key,
            )
            for sector_name in candidate_sector_names:
                latest_year, snapshot_row = latest_snapshot_by_sector.get(
                    sector_name,
                    (None, None),
                )
                company_count = int(hub_counts.get(sector_name, 0))
                breakdown_counter = sub_industry_counts_by_gics.get(sector_name, Counter())
                breakdown = tuple(
                    SubIndustryCountDTO(name=name, count=int(count))
                    for name, count in sorted(
                        breakdown_counter.items(),
                        key=lambda item: (-int(item[1]), str(item[0])),
                    )
                )
                items.append(
                    SectorDirectoryItemDTO(
                        sector_name=sector_name,
                        sector_slug=sector_slugify(sector_name),
                        company_count=company_count,
                        latest_year=latest_year,
                        snapshot=SectorSnapshotDTO(
                            roe=self._coerce_optional_float(snapshot_row["roe"]) if snapshot_row is not None else None,
                            mg_ebit=self._coerce_optional_float(snapshot_row["mg_ebit"]) if snapshot_row is not None else None,
                            mg_liq=self._coerce_optional_float(snapshot_row["mg_liq"]) if snapshot_row is not None else None,
                        ),
                        sub_industries=tuple(sorted(sub_industries_by_gics.get(sector_name, ()))),
                        sub_industry_breakdown=breakdown,
                        group_type="sector",
                        companies=self._sector_company_preview(companies_by_gics.get(sector_name, [])),
                    )
                )

        if unclassified_items:
            items.append(
                SectorDirectoryItemDTO(
                    sector_name="Sem classificacao GICS",
                    sector_slug="sem-classificacao-gics",
                    company_count=len(unclassified_items),
                    latest_year=None,
                    snapshot=SectorSnapshotDTO(roe=None, mg_ebit=None, mg_liq=None),
                    group_type="unclassified",
                    companies=self._sector_company_preview(unclassified_items),
                )
            )

        items.sort(key=lambda item: gics_sector_sort_key(item.sector_name))
        result = SectorDirectoryDTO(items=tuple(items))
        self._sector_directory_cache[cache_key] = result
        if include_snapshots:
            self._write_sector_directory_persistent_cache(normalized_group_by, result)
        return result

    def _list_companies_by_gics_sector(
        self,
        *,
        search: str,
        sector_slug: str | None,
        gics_sector: str,
        page: int,
        page_size: int,
    ) -> CompanyDirectoryPage:
        normalized_search = str(search or "").strip().lower()
        filtered = [
            item
            for item in self._list_company_universe_results()
            if item.gics_sector == gics_sector
            and (
                not normalized_search
                or normalized_search in item.company_name.lower()
                or normalized_search in (item.ticker_b3 or "").lower()
                or normalized_search in str(item.cd_cvm)
            )
        ]
        total_items = len(filtered)
        start = max(0, (int(page) - 1) * int(page_size))
        end = start + int(page_size)
        total_pages = max(1, ((total_items - 1) // int(page_size)) + 1) if total_items else 1
        return CompanyDirectoryPage(
            items=tuple(filtered[start:end]),
            pagination=CompanyDirectoryPagination(
                page=int(page),
                page_size=int(page_size),
                total_items=int(total_items),
                total_pages=int(total_pages),
                has_next=int(page) < int(total_pages),
                has_previous=int(page) > 1,
            ),
            applied_filters=CompanyDirectoryAppliedFilters(
                search=str(search or ""),
                sector=sector_slug,
            ),
        )

    def get_sector_detail(self, sector_slug: str, year: int | None = None) -> SectorDetailDTO | None:
        resolved_sector_name = self._resolve_sector_slug(sector_slug)
        if resolved_sector_name is None:
            return None

        if resolved_sector_name in GICS_11_SECTORS:
            company_items = [
                item
                for item in self._list_company_universe_results_light()
                if item.gics_sector == resolved_sector_name
            ]
            if not company_items:
                return None
            total_items = len(company_items)
            company_codes = [int(item.cd_cvm) for item in company_items]
            years_map = self.query_layer.get_company_years_map(company_codes)
            company_rows = pd.DataFrame(
                [
                    {
                        "cd_cvm": int(item.cd_cvm),
                        "company_name": str(item.company_name),
                        "ticker_b3": item.ticker_b3,
                        "anos_disponiveis": years_map.get(int(item.cd_cvm), ()),
                        "gics_sub_industry": item.gics_sub_industry,
                    }
                    for item in company_items
                ]
            )
        else:
            return None

        if "anos_disponiveis" not in company_rows.columns:
            years_map = self.query_layer.get_company_years_map(company_rows["cd_cvm"].tolist())
            company_rows = company_rows.copy()
            company_rows["anos_disponiveis"] = company_rows["cd_cvm"].map(
                lambda cd_cvm: years_map.get(int(cd_cvm), ())
            )
        if "gics_sub_industry" not in company_rows.columns:
            company_rows = company_rows.copy()
            company_rows["gics_sub_industry"] = None
        available_years = self._extract_years_from_company_rows(company_rows)
        if not available_years:
            selected_year = int(year or datetime.now(timezone.utc).year - 1)
            return SectorDetailDTO(
                sector_name=resolved_sector_name,
                sector_slug=sector_slugify(resolved_sector_name),
                company_count=int(total_items),
                available_years=(),
                selected_year=selected_year,
                yearly_overview=(),
                companies=tuple(
                    SectorCompanyMetricDTO(
                        cd_cvm=int(row["cd_cvm"]),
                        company_name=str(row["company_name"]),
                        ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                        gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                        roe=None,
                        mg_ebit=None,
                        mg_liq=None,
                    )
                    for _, row in company_rows.sort_values("company_name").iterrows()
                ),
            )

        if year is None:
            selected_year = max(available_years)
        else:
            selected_year = int(year)
            if selected_year not in available_years:
                raise ValueError(
                    f"O parametro 'year' precisa ser um dos anos disponiveis do setor: {', '.join(str(value) for value in available_years)}."
                )

        if resolved_sector_name in GICS_11_SECTORS:
            metric_rows = self._get_sector_metric_rows(cd_cvms=company_rows["cd_cvm"].tolist())
            company_codes = {int(value) for value in company_rows["cd_cvm"].tolist()}
            if metric_rows is None or metric_rows.empty:
                metric_rows = pd.DataFrame(
                    columns=["cd_cvm", "report_year", "roe", "mg_ebit", "mg_liq", "sector_name"]
                )
            else:
                metric_rows = metric_rows[metric_rows["cd_cvm"].map(lambda code: int(code) in company_codes)].copy()
                metric_rows["sector_name"] = resolved_sector_name
        else:
            metric_rows = self._get_sector_metric_rows(sector_name=resolved_sector_name)
        yearly = self._aggregate_sector_yearly_metrics(metric_rows)
        yearly_overview = tuple(
            SectorYearOverviewDTO(
                year=int(row["year"]),
                roe=self._coerce_optional_float(row["roe"]),
                mg_ebit=self._coerce_optional_float(row["mg_ebit"]),
                mg_liq=self._coerce_optional_float(row["mg_liq"]),
            )
            for _, row in yearly[yearly["sector_name"] == resolved_sector_name]
            .sort_values("year")
            .iterrows()
        )

        company_metrics = metric_rows[metric_rows["report_year"] == selected_year].copy()
        selected_companies = company_rows[
            company_rows["anos_disponiveis"].map(lambda years: selected_year in years)
        ][["cd_cvm", "company_name", "ticker_b3", "gics_sub_industry"]].drop_duplicates()
        selected_companies = selected_companies.merge(
            company_metrics[
                ["cd_cvm", "roe", "mg_ebit", "mg_liq"]
            ],
            on="cd_cvm",
            how="left",
        )
        selected_companies["ticker_b3"] = selected_companies["ticker_b3"].replace("", None)
        selected_companies["sort_roe"] = pd.to_numeric(selected_companies["roe"], errors="coerce")
        selected_companies = selected_companies.sort_values(
            by=["sort_roe", "company_name"],
            ascending=[False, True],
            na_position="last",
        )

        companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=self._coerce_optional_float(row.get("roe")),
                mg_ebit=self._coerce_optional_float(row.get("mg_ebit")),
                mg_liq=self._coerce_optional_float(row.get("mg_liq")),
            )
            for _, row in selected_companies.iterrows()
        )

        return SectorDetailDTO(
            sector_name=resolved_sector_name,
            sector_slug=sector_slugify(resolved_sector_name),
            company_count=int(total_items),
            available_years=tuple(available_years),
            selected_year=int(selected_year),
            yearly_overview=yearly_overview,
            companies=companies,
        )

    def get_sub_sector_detail(
        self,
        *,
        sector_slug: str,
        sub_industry_slug: str,
        year: int | None = None,
    ) -> SectorDetailDTO | None:
        """Detail for a GICS sub-industry inside a parent GICS sector.

        Returns None if the sector slug is not one of the 11 GICS hubs or if
        no company in that sector has the requested sub-industry slug.
        """
        sector_name = self._resolve_sector_slug(sector_slug)
        if sector_name is None or sector_name not in GICS_11_SECTORS:
            return None

        normalized_sub_slug = str(sub_industry_slug or "").strip().lower()
        if not normalized_sub_slug:
            return None

        universe = self._list_company_universe_results_light()
        sub_industry_name: str | None = None
        matching: list[CompanySearchResult] = []
        for item in universe:
            if item.gics_sector != sector_name:
                continue
            if not item.gics_sub_industry:
                continue
            if sector_slugify(item.gics_sub_industry) != normalized_sub_slug:
                continue
            sub_industry_name = item.gics_sub_industry
            matching.append(item)

        if not matching or sub_industry_name is None:
            return None

        matching_codes = [int(item.cd_cvm) for item in matching]
        years_map = self.query_layer.get_company_years_map(matching_codes)
        company_rows = pd.DataFrame(
            [
                {
                    "cd_cvm": int(item.cd_cvm),
                    "company_name": str(item.company_name),
                    "ticker_b3": item.ticker_b3,
                    "anos_disponiveis": years_map.get(int(item.cd_cvm), ()),
                    "gics_sub_industry": item.gics_sub_industry,
                }
                for item in matching
            ]
        )
        total_items = len(company_rows)
        available_years = self._extract_years_from_company_rows(company_rows)
        parent_sector_slug = sector_slugify(sector_name)

        empty_companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=None,
                mg_ebit=None,
                mg_liq=None,
            )
            for _, row in company_rows.sort_values("company_name").iterrows()
        )

        if not available_years:
            selected_year = int(year or datetime.now(timezone.utc).year - 1)
            return SectorDetailDTO(
                sector_name=sub_industry_name,
                sector_slug=normalized_sub_slug,
                company_count=int(total_items),
                available_years=(),
                selected_year=selected_year,
                yearly_overview=(),
                companies=empty_companies,
                parent_sector_name=sector_name,
                parent_sector_slug=parent_sector_slug,
            )

        if year is None:
            selected_year = max(available_years)
        else:
            selected_year = int(year)
            if selected_year not in available_years:
                raise ValueError(
                    f"O parametro 'year' precisa ser um dos anos disponiveis do sub-setor: {', '.join(str(value) for value in available_years)}."
                )

        metric_rows = self._get_sector_metric_rows(cd_cvms=company_rows["cd_cvm"].tolist())
        company_codes = {int(value) for value in company_rows["cd_cvm"].tolist()}
        if metric_rows is None or metric_rows.empty:
            metric_rows = pd.DataFrame(
                columns=["cd_cvm", "report_year", "roe", "mg_ebit", "mg_liq", "sector_name"]
            )
        else:
            metric_rows = metric_rows[
                metric_rows["cd_cvm"].map(lambda code: int(code) in company_codes)
            ].copy()
            metric_rows["sector_name"] = sub_industry_name

        yearly = self._aggregate_sector_yearly_metrics(metric_rows)
        yearly_overview = tuple(
            SectorYearOverviewDTO(
                year=int(row["year"]),
                roe=self._coerce_optional_float(row["roe"]),
                mg_ebit=self._coerce_optional_float(row["mg_ebit"]),
                mg_liq=self._coerce_optional_float(row["mg_liq"]),
            )
            for _, row in yearly[yearly["sector_name"] == sub_industry_name]
            .sort_values("year")
            .iterrows()
        )

        company_metrics = metric_rows[metric_rows["report_year"] == selected_year].copy()
        selected_companies = company_rows[
            company_rows["anos_disponiveis"].map(lambda years: selected_year in years)
        ][["cd_cvm", "company_name", "ticker_b3", "gics_sub_industry"]].drop_duplicates()
        selected_companies = selected_companies.merge(
            company_metrics[["cd_cvm", "roe", "mg_ebit", "mg_liq"]],
            on="cd_cvm",
            how="left",
        )
        selected_companies["ticker_b3"] = selected_companies["ticker_b3"].replace("", None)
        selected_companies["sort_roe"] = pd.to_numeric(
            selected_companies["roe"], errors="coerce"
        )
        selected_companies = selected_companies.sort_values(
            by=["sort_roe", "company_name"],
            ascending=[False, True],
            na_position="last",
        )

        companies = tuple(
            SectorCompanyMetricDTO(
                cd_cvm=int(row["cd_cvm"]),
                company_name=str(row["company_name"]),
                ticker_b3=self._clean_optional_text(row.get("ticker_b3")),
                gics_sub_industry=self._clean_optional_text(row.get("gics_sub_industry")),
                roe=self._coerce_optional_float(row.get("roe")),
                mg_ebit=self._coerce_optional_float(row.get("mg_ebit")),
                mg_liq=self._coerce_optional_float(row.get("mg_liq")),
            )
            for _, row in selected_companies.iterrows()
        )

        return SectorDetailDTO(
            sector_name=sub_industry_name,
            sector_slug=normalized_sub_slug,
            company_count=int(total_items),
            available_years=tuple(available_years),
            selected_year=int(selected_year),
            yearly_overview=yearly_overview,
            companies=companies,
            parent_sector_name=sector_name,
            parent_sector_slug=parent_sector_slug,
        )

    def get_statement_matrix(
        self,
        cd_cvm: int,
        years: list[int],
        stmt_type: str,
        *,
        exclude_conflicts: bool = True,
    ) -> StatementMatrix:
        df = self.query_layer.get_statement(
            cd_cvm=cd_cvm,
            years=years,
            stmt_type=stmt_type,
            exclude_conflicts=exclude_conflicts,
        )
        return StatementMatrix(
            cd_cvm=int(cd_cvm),
            statement_type=str(stmt_type),
            years=tuple(int(year) for year in years),
            table=TabularData.from_dataframe(df),
            exclude_conflicts=bool(exclude_conflicts),
        )

    def get_statement_dataframe(
        self,
        cd_cvm: int,
        years: list[int],
        stmt_type: str,
        *,
        exclude_conflicts: bool = True,
    ) -> pd.DataFrame:
        return self.get_statement_matrix(
            cd_cvm,
            years,
            stmt_type,
            exclude_conflicts=exclude_conflicts,
        ).to_dataframe()

    def get_kpi_bundle(self, cd_cvm: int, years: list[int]) -> KPIBundle:
        accounts = self.query_layer.get_kpi_accounts(cd_cvm, years)
        da_series = self.query_layer.get_da_from_dfc(cd_cvm, years)
        annual = compute_all_kpis(accounts, da_series)

        quarterly_accounts = self.query_layer.get_kpi_accounts_all_periods(cd_cvm, years)
        quarterly_da = self.query_layer.get_da_all_periods(cd_cvm, years)
        quarterly = compute_quarterly_kpis(quarterly_accounts, quarterly_da)

        return KPIBundle(
            cd_cvm=int(cd_cvm),
            years=tuple(int(year) for year in years),
            annual=TabularData.from_dataframe(annual),
            quarterly=TabularData.from_dataframe(quarterly),
        )

    def get_statement_summary(self, cd_cvm: int, years: list[int]) -> StatementSummaryDTO:
        stmt_types = ["DRE", "BPA", "BPP", "DFC"]
        statements = {
            s: self.query_layer.get_statement(
                cd_cvm=cd_cvm,
                years=years,
                stmt_type=s,
                exclude_conflicts=True,
            )
            for s in stmt_types
        }
        raw_blocks = build_general_summary_blocks(statements)
        blocks = tuple(
            SummaryBlockDTO(
                stmt_type=b.stmt_type,
                title=b.title,
                table=TabularData.from_dataframe(b.rows),
            )
            for b in raw_blocks
        )
        return StatementSummaryDTO(
            cd_cvm=int(cd_cvm),
            years=tuple(sorted(int(y) for y in years)),
            blocks=blocks,
        )
