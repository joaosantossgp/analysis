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
    _pick_model_periods,
    _period_sort_key,
    is_financial_company_info,
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


class ReadServiceExportMixin:
    @functools.lru_cache(maxsize=10)
    def get_available_export_periods(self, cd_cvm: int) -> dict:
        """Returns annual DFP years and ITR-only years for export.

        Delegates to ``QueryLayer.get_available_export_periods``.  Result is
        cached per company for the lifetime of the service instance (same
        cache-clear policy as ``get_available_years``).
        """
        return self.query_layer.get_available_export_periods(cd_cvm)

    def resolve_excel_export_scope(self, cd_cvm: int, period_scope: str) -> dict:
        """Map a period_scope string to the concrete years and window needed.

        Parameters
        ----------
        cd_cvm : int
        period_scope : str
            One of ``last_3_years``, ``last_5_years``, ``last_10_years``,
            ``full_history``.

        Returns
        -------
        dict with keys:
          all_export_years  — list[int] to pass as ``years`` when loading data
          period_window     — (annuals, quarters_per_year) for ExcelExporter
          scope_label       — human-readable string for workbook metadata
          itr_only_years    — list[int] of ITR-only years included
        """
        _SCOPE_LABELS = {
            "last_3_years":  "Last 3 years",
            "last_5_years":  "Last 5 years",
            "last_10_years": "Last 10 years",
            "full_history":  "Full history",
        }
        _SCOPE_N = {
            "last_3_years":  3,
            "last_5_years":  5,
            "last_10_years": 10,
        }

        if period_scope not in self.VALID_PERIOD_SCOPES:
            raise ValueError(
                f"Invalid period_scope: {period_scope!r}. "
                f"Must be one of: {', '.join(sorted(self.VALID_PERIOD_SCOPES))}"
            )

        periods = self.get_available_export_periods(cd_cvm)
        annual_years: list[int] = periods["annual_years"]
        itr_only_years: list[int] = periods["itr_only_years"]

        scope_label = _SCOPE_LABELS.get(period_scope, period_scope)

        if period_scope == "full_history":
            n_annuals = len(annual_years)
        else:
            n_annuals = _SCOPE_N.get(period_scope, 5)

        # Slice the last N annual years according to scope.
        selected_annual_years = annual_years[-n_annuals:] if n_annuals > 0 else annual_years

        # Always include ITR-only years that are newer than the latest selected
        # annual year — this is the core "current-year ITR inclusion" guarantee.
        max_selected_annual = max(selected_annual_years, default=0)
        included_itr_only = [y for y in itr_only_years if y > max_selected_annual]

        all_export_years = sorted(set(selected_annual_years) | set(included_itr_only))

        # period_window controls how _pick_model_periods slices the data.
        # annuals = number of annual periods to show; quarters_per_year = 4.
        # When there are no annual years (ITR-only company), use 0 so
        # _pick_model_periods falls through to the ITR-only branch.
        annuals_for_window = n_annuals if annual_years else 0

        return {
            "all_export_years": all_export_years,
            "period_window": (annuals_for_window, 4),
            "scope_label": scope_label,
            "itr_only_years": included_itr_only,
        }

    def resolve_excel_model_mapping(
        self,
        cd_cvm: int,
        preset_id: str | None = None,
    ) -> ModelMappingDefinition:
        company_info = self.get_company_info_dict(cd_cvm)
        selected_preset_id = (
            str(preset_id).strip()
            if preset_id
            else self.excel_mapping_repository.get_company_default_preset_id(cd_cvm)
        )
        if not selected_preset_id or selected_preset_id == SYSTEM_DEFAULT_PRESET_ID:
            return build_default_model_mapping(company_info)

        stored = self.excel_mapping_repository.load_preset(selected_preset_id)
        if stored is None:
            raise ValueError(f"Mapping preset not found: {selected_preset_id}")
        return stored

    def get_excel_mapping_workspace(
        self,
        cd_cvm: int,
        preset_id: str | None = None,
        period_scope: str = "last_5_years",
    ) -> dict[str, Any]:
        company_info = self.get_company_info_dict(cd_cvm)
        if not company_info:
            raise ValueError(f"Company {cd_cvm} not found.")

        company_default_preset_id = (
            self.excel_mapping_repository.get_company_default_preset_id(cd_cvm)
            or SYSTEM_DEFAULT_PRESET_ID
        )
        is_financial = is_financial_company_info(company_info)
        from src.financials.formulas import get_formula_definitions
        formula_defs = get_formula_definitions(is_financial)

        active_preset_id = preset_id or company_default_preset_id
        mapping = self.resolve_excel_model_mapping(cd_cvm, active_preset_id)
        scope = self.resolve_excel_export_scope(cd_cvm, period_scope)
        raw_statements = self._load_export_statement_frames(cd_cvm, period_scope)
        issues = self.validate_excel_model_mapping(mapping, raw_statements, company_id=cd_cvm, engine=self.engine)
        preview_periods = self._mapping_preview_periods(
            raw_statements,
            period_window=scope["period_window"],
        )
        mapped_targets = self._mapping_source_targets(mapping)

        preview_rows = self._model_preview_rows(
            mapping,
            raw_statements,
            preview_periods,
            issues,
            is_financial,
            engine=self.engine,
            company_id=cd_cvm,
            company_sector=company_info.get("setor_analitico"),
        )

        # Compute period resolutions DTO
        raw_rows_dict = []
        for stmt_type, df in raw_statements.items():
            if df is not None and not df.empty:
                df_copied = df.copy()
                df_copied["STATEMENT_TYPE"] = stmt_type
                raw_rows_dict.extend(df_copied.to_dict("records"))

        from src.financials.resolver import ModelResolver
        resolver = ModelResolver(self.engine)
        overrides = resolver.get_overrides(cd_cvm) if self.engine else {}
        aliases = resolver.get_aliases() if self.engine else []
        is_user_preset = mapping.origin == "user"

        resolutions_dto = []
        for entry in mapping.entries:
            for period in preview_periods:
                res = resolver.resolve_entry_for_period(
                    company_id=cd_cvm,
                    entry=entry,
                    period=period,
                    raw_statement_rows=raw_rows_dict,
                    overrides=overrides,
                    aliases=aliases,
                    company_sector=company_info.get("setor_analitico"),
                    restrict_to_sources=is_user_preset,
                )
                resolutions_dto.append(res)

        return {
            "ok": True,
            "company": company_info,
            "period_scope_label": scope["scope_label"],
            "presets": self.excel_mapping_repository.list_presets(
                company_default_preset_id=company_default_preset_id
            ),
            "active_preset_id": mapping.preset_id,
            "company_default_preset_id": company_default_preset_id,
            "mapping": mapping.to_dict(),
            "formula_definitions": formula_defs,
            "is_financial": is_financial,
            "preview_periods": preview_periods,
            "model_preview_rows": preview_rows,
            "resolutions": resolutions_dto,
            "raw_lines": self._raw_mapping_lines(
                raw_statements,
                preview_periods=preview_periods,
                mapped_targets=mapped_targets,
            ),
            "validation": [issue.to_dict() for issue in issues],
        }

    def save_excel_mapping_preset(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_mapping = payload.get("mapping") if "mapping" in payload else payload
        if not isinstance(raw_mapping, dict):
            raise ValueError("Mapping payload is required.")
        mapping = ModelMappingDefinition.from_payload(raw_mapping)
        saved = self.excel_mapping_repository.save_preset(mapping)
        return {
            "ok": True,
            "preset": saved.to_dict(),
            "presets": self.excel_mapping_repository.list_presets(),
        }

    def set_company_excel_mapping_default(self, cd_cvm: int, preset_id: str) -> dict[str, Any]:
        if preset_id != SYSTEM_DEFAULT_PRESET_ID and self.excel_mapping_repository.load_preset(preset_id) is None:
            raise ValueError(f"Mapping preset not found: {preset_id}")
        self.excel_mapping_repository.set_company_default_preset(cd_cvm, preset_id)
        return {
            "ok": True,
            "cd_cvm": int(cd_cvm),
            "preset_id": preset_id,
        }

    def save_excel_mapping_override(
        self,
        company_id: int,
        target_id: str,
        period_label: str,
        source_code: str,
        source_desc: Optional[str] = None,
        sign: int = 1,
    ) -> dict[str, Any]:
        from src.financials.resolver import ModelResolver
        resolver = ModelResolver(self.engine)
        resolver.save_override(
            company_id=company_id,
            target_id=target_id,
            period_label=period_label,
            source_code=source_code,
            source_desc=source_desc,
            sign=sign,
        )
        return {"ok": True}

    def delete_excel_mapping_override(
        self,
        company_id: int,
        target_id: str,
        period_label: str,
    ) -> dict[str, Any]:
        from src.financials.resolver import ModelResolver
        resolver = ModelResolver(self.engine)
        resolver.delete_override(
            company_id=company_id,
            target_id=target_id,
            period_label=period_label,
        )
        return {"ok": True}

    def validate_excel_model_mapping(
        self,
        mapping: ModelMappingDefinition,
        statements: dict[str, pd.DataFrame],
        company_id: int = 0,
        engine: Optional[Any] = None,
    ) -> list[MappingValidationIssue]:
        issues: list[MappingValidationIssue] = []
        raw_keys: set[tuple[str, str]] = set()
        raw_by_stmt: dict[str, set[str]] = {}
        periods: set[str] = set()
        meta_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
        for stmt_type, df in statements.items():
            if df is None or df.empty or "LINE_ID_BASE" not in df.columns:
                raw_by_stmt[stmt_type] = set()
                continue
            ids = {
                str(value).strip()
                for value in df["LINE_ID_BASE"].tolist()
                if str(value).strip()
            }
            raw_by_stmt[stmt_type] = ids
            raw_keys.update((stmt_type, line_id) for line_id in ids)
            periods.update(str(col) for col in df.columns if col not in meta_cols)

        source_usage: dict[tuple[str, str], list[str]] = {}
        mapped_raw_keys: set[tuple[str, str]] = set()
        for entry in mapping.entries:
            if not entry.target_id:
                issues.append(MappingValidationIssue(
                    "error", "target_id_missing", "A model row is missing its target id."
                ))
            if entry.operation not in VALID_MAPPING_OPERATIONS:
                issues.append(MappingValidationIssue(
                    "error",
                    "invalid_operation",
                    f"Invalid operation: {entry.operation}",
                    target_id=entry.target_id,
                ))
            if entry.required and not entry.sources:
                issues.append(MappingValidationIssue(
                    "warning",
                    "required_mapping_empty",
                    f"Required model line has no source mapping: {entry.target_label}",
                    target_id=entry.target_id,
                ))
            for source in entry.sources:
                source_id = f"{source.statement_type}:{source.line_id_base}"
                if source.statement_type != entry.statement_type:
                    issues.append(MappingValidationIssue(
                        "error",
                        "statement_type_mismatch",
                        f"{source_id} is mapped into {entry.statement_type}.",
                        target_id=entry.target_id,
                        source_id=source_id,
                    ))
                key = (source.statement_type, source.line_id_base)
                source_usage.setdefault(key, []).append(entry.target_id)
                mapped_raw_keys.add(key)
                if key not in raw_keys:
                    issues.append(MappingValidationIssue(
                        "warning",
                        "source_missing_for_company",
                        f"Source line is not present for this company: {source_id}",
                        target_id=entry.target_id,
                        source_id=source_id,
                    ))

        for key, targets in source_usage.items():
            if len(set(targets)) > 1:
                source_id = f"{key[0]}:{key[1]}"
                issues.append(MappingValidationIssue(
                    "warning",
                    "source_mapped_multiple_times",
                    f"Source line is mapped to multiple model rows: {source_id}",
                    source_id=source_id,
                ))

        for stmt_type, line_ids in raw_by_stmt.items():
            unused_count = len({(stmt_type, line_id) for line_id in line_ids} - mapped_raw_keys)
            if unused_count > 0:
                issues.append(MappingValidationIssue(
                    "warning",
                    "raw_lines_unmapped",
                    f"{unused_count} raw {stmt_type} line(s) are not used by the active mapping.",
                ))

        # Perform period-level validation using ModelResolver
        if engine and company_id:
            from src.financials.resolver import ModelResolver
            resolver = ModelResolver(engine)
            overrides = resolver.get_overrides(company_id)
            aliases = resolver.get_aliases()
            
            raw_rows_dict = []
            for stmt_type, df in statements.items():
                if df is not None and not df.empty:
                    df_copied = df.copy()
                    df_copied["STATEMENT_TYPE"] = stmt_type
                    raw_rows_dict.extend(df_copied.to_dict("records"))
            
            is_user_preset = mapping.origin == "user"
            for entry in mapping.entries:
                for period in sorted(periods):
                    res = resolver.resolve_entry_for_period(
                        company_id=company_id,
                        entry=entry,
                        period=period,
                        raw_statement_rows=raw_rows_dict,
                        overrides=overrides,
                        aliases=aliases,
                        restrict_to_sources=is_user_preset,
                    )
                    status = res.get("status")
                    if status == "ambiguous":
                        issues.append(MappingValidationIssue(
                            "warning",
                            "ambiguous_mapping",
                            f"Ambiguous mapping for {entry.target_label} in period {period}: {res.get('selected_source_label')}. "
                            f"{'; '.join(res.get('warnings', []))}",
                            target_id=entry.target_id,
                            source_id=res.get("selected_source_id"),
                        ))
                    elif status == "conflict":
                        issues.append(MappingValidationIssue(
                            "error",
                            "conflict_mapping",
                            f"Mapping conflict for {entry.target_label} in period {period}: {res.get('selected_source_label')}. "
                            f"{'; '.join(res.get('warnings', []))}",
                            target_id=entry.target_id,
                            source_id=res.get("selected_source_id"),
                        ))
                    elif status == "unresolved" and entry.required:
                        stmt_has_data = False
                        stmt_df = statements.get(entry.statement_type)
                        if stmt_df is not None and not stmt_df.empty and period in stmt_df.columns:
                            if stmt_df[period].notna().any():
                                stmt_has_data = True
                        if stmt_has_data:
                            issues.append(MappingValidationIssue(
                                "error",
                                "unresolved_required_mapping",
                                f"Required model line {entry.target_label} is unresolved for period {period}.",
                                target_id=entry.target_id,
                            ))

        return issues

    def _load_export_statement_frames(
        self,
        cd_cvm: int,
        period_scope: str,
    ) -> dict[str, pd.DataFrame]:
        if period_scope not in self.VALID_PERIOD_SCOPES:
            raise ValueError(
                f"Invalid period_scope: {period_scope!r}. "
                f"Must be one of: {', '.join(sorted(self.VALID_PERIOD_SCOPES))}"
            )
        scope = self.resolve_excel_export_scope(cd_cvm, period_scope)
        years: list[int] = scope["all_export_years"]
        if not years:
            return {}
        all_stmts = {
            stmt_type: self.get_statement_dataframe(cd_cvm, years, stmt_type)
            for stmt_type in EXPORT_STATEMENT_TYPES
        }
        return {
            stmt_type: df
            for stmt_type, df in all_stmts.items()
            if df is not None and not df.empty
        }

    @staticmethod
    def _mapping_preview_periods(
        statements: dict[str, pd.DataFrame],
        *,
        period_window: tuple[int, int],
    ) -> list[str]:
        all_periods: set[str] = set()
        meta_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
        for df in statements.values():
            if df is None or df.empty:
                continue
            all_periods.update(str(col) for col in df.columns if col not in meta_cols)
        return _pick_model_periods(
            sorted(all_periods, key=_period_sort_key),
            annuals=period_window[0],
            quarters_per_year=period_window[1],
        )

    @staticmethod
    def _mapping_source_targets(mapping: ModelMappingDefinition) -> dict[tuple[str, str], list[dict[str, str]]]:
        targets: dict[tuple[str, str], list[dict[str, str]]] = {}
        for entry in mapping.entries:
            for source in entry.sources:
                key = (source.statement_type, source.line_id_base)
                targets.setdefault(key, []).append({
                    "target_id": entry.target_id,
                    "target_label": entry.target_label,
                    "group": entry.group,
                })
        return targets

    @staticmethod
    def _statement_indexes(statements: dict[str, pd.DataFrame]) -> dict[str, dict[str, dict[str, Any]]]:
        indexes: dict[str, dict[str, dict[str, Any]]] = {}
        for stmt_type, df in statements.items():
            if df is None or df.empty:
                indexes[stmt_type] = {"line_id": {}, "cd": {}, "label": {}}
                continue
            line_id: dict[str, Any] = {}
            cd: dict[str, Any] = {}
            label: dict[str, Any] = {}
            for _, row in df.iterrows():
                line_value = str(row.get("LINE_ID_BASE") or "").strip()
                cd_value = str(row.get("CD_CONTA") or "").strip()
                standard_name = str(row.get("STANDARD_NAME") or "").strip()
                ds_conta = str(row.get("DS_CONTA") or "").strip()
                if line_value and line_value not in line_id:
                    line_id[line_value] = row
                if cd_value and cd_value not in cd:
                    cd[cd_value] = row
                for label_value in (standard_name, ds_conta):
                    if label_value and label_value not in label:
                        label[label_value] = row
            indexes[stmt_type] = {"line_id": line_id, "cd": cd, "label": label}
        return indexes

    @staticmethod
    def _resolve_mapping_source_row(
        source: ModelMappingSource,
        indexes: dict[str, dict[str, dict[str, Any]]],
    ) -> Any | None:
        stmt_index = indexes.get(source.statement_type)
        if not stmt_index:
            return None
        row = stmt_index.get("line_id", {}).get(source.line_id_base)
        if row is not None:
            return row
        cd_value = source.cd_conta or source.line_id_base
        row = stmt_index.get("cd", {}).get(cd_value)
        if row is not None:
            return row
        if source.label_snapshot:
            return stmt_index.get("label", {}).get(source.label_snapshot)
        return None

    @staticmethod
    def _model_preview_value(
        entry: ModelMappingEntry,
        period: str,
        indexes: dict[str, dict[str, dict[str, Any]]],
    ) -> float | None:
        if entry.operation not in VALID_MAPPING_OPERATIONS:
            return None
        sources = entry.sources[:1] if entry.operation == "direct" else entry.sources
        if not sources:
            return None
        total = 0.0
        for source in sources:
            row = ReadServiceExportMixin._resolve_mapping_source_row(source, indexes)
            if row is None:
                return None
            value = row.get(period)
            if pd.isna(value):
                return None
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            sign = -1 if entry.operation == "sum_with_sign" and source.sign < 0 else 1
            total += sign * numeric
        return total / 1000.0

    @staticmethod
    def _model_preview_rows(
        mapping: ModelMappingDefinition,
        statements: dict[str, pd.DataFrame],
        preview_periods: list[str],
        issues: list[MappingValidationIssue],
        is_financial: bool = False,
        engine: Optional[Any] = None,
        company_id: int = 0,
        company_sector: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        # Convert statements DataFrames to dict records for database-free resolution
        raw_rows_dict = []
        for stmt_type, df in statements.items():
            if df is not None and not df.empty:
                df_copied = df.copy()
                df_copied["STATEMENT_TYPE"] = stmt_type
                raw_rows_dict.extend(df_copied.to_dict("records"))

        from src.financials.resolver import ModelResolver
        resolver = ModelResolver(engine)
        overrides = resolver.get_overrides(company_id) if (engine and company_id) else {}
        aliases = resolver.get_aliases() if engine else []
        is_user_preset = mapping.origin == "user"

        values_by_target_period: dict[str, dict[str, float | None]] = {}
        for entry in mapping.entries:
            values_by_target_period[entry.target_id] = {}
            for period in preview_periods:
                res = resolver.resolve_entry_for_period(
                    company_id=company_id,
                    entry=entry,
                    period=period,
                    raw_statement_rows=raw_rows_dict,
                    overrides=overrides,
                    aliases=aliases,
                    company_sector=company_sector,
                    restrict_to_sources=is_user_preset,
                )
                values_by_target_period[entry.target_id][period] = res["resolved_value"]

        # 2. Evaluate formulas dynamically
        from src.financials.formulas import evaluate_formulas
        values_by_target_period, check_statuses, formula_issues = evaluate_formulas(
            is_financial=is_financial,
            entries=list(mapping.entries),
            periods=preview_periods,
            values_by_target_period=values_by_target_period,
        )
        
        # 3. Append formula warning issues to the validation issues list
        issues.extend(formula_issues)

        # 4. Count validation issues per target row
        issue_counts: dict[str, dict[str, int]] = {}
        for issue in issues:
            if not issue.target_id:
                continue
            counts = issue_counts.setdefault(issue.target_id, {"errors": 0, "warnings": 0})
            if issue.severity == "error":
                counts["errors"] += 1
            else:
                counts["warnings"] += 1

        # 5. Build final row payloads
        rows: list[dict[str, Any]] = []
        for entry in mapping.entries:
            counts = issue_counts.get(entry.target_id, {"errors": 0, "warnings": 0})
            row_check_statuses = check_statuses.get(entry.target_id, {})
            rows.append({
                "target_id": entry.target_id,
                "target_label": entry.target_label,
                "group": entry.group,
                "statement_type": entry.statement_type,
                "display_order": entry.display_order,
                "indent_level": entry.indent_level,
                "required": entry.required,
                "operation": entry.operation,
                "is_subtotal": entry.is_subtotal,
                "source_count": len(entry.sources),
                "warning_count": counts["warnings"],
                "error_count": counts["errors"],
                "values_by_period": values_by_target_period.get(entry.target_id, {}),
                "check_status": row_check_statuses,
            })
        return rows

    @staticmethod
    def _raw_mapping_lines(
        statements: dict[str, pd.DataFrame],
        *,
        preview_periods: list[str] | None = None,
        mapped_targets: dict[tuple[str, str], list[dict[str, str]]] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        preview_periods = preview_periods or []
        mapped_targets = mapped_targets or {}
        for stmt_type, df in statements.items():
            if df is None or df.empty:
                continue
            meta_cols = {"CD_CONTA", "DS_CONTA", "STANDARD_NAME", "LINE_ID_BASE"}
            period_cols = [str(col) for col in df.columns if col not in meta_cols]
            for _, row in df.iterrows():
                line_id = str(row.get("LINE_ID_BASE") or "").strip()
                if not line_id:
                    continue
                ds_conta = str(row.get("DS_CONTA") or "").strip()
                standard_name = str(row.get("STANDARD_NAME") or "").strip()
                cd_conta = str(row.get("CD_CONTA") or "").strip()
                label = standard_name or ds_conta or cd_conta or line_id
                sample_values: dict[str, float | None] = {}
                for period in preview_periods:
                    value = row.get(period)
                    if pd.isna(value):
                        sample_values[period] = None
                    else:
                        try:
                            sample_values[period] = float(value) / 1000.0
                        except (TypeError, ValueError):
                            sample_values[period] = None
                rows.append({
                    "statement_type": stmt_type,
                    "line_id_base": line_id,
                    "cd_conta": cd_conta or None,
                    "ds_conta": ds_conta or None,
                    "standard_name": standard_name or None,
                    "label": label,
                    "normalized_label": normalize_account_name(label),
                    "periods_present": [
                        period
                        for period in period_cols
                        if pd.notna(row.get(period))
                    ],
                    "sample_values_by_period": sample_values,
                    "mapped_targets": mapped_targets.get((stmt_type, line_id), []),
                })
        return rows

    def build_company_excel_export(
        self,
        cd_cvm: int,
        statement_type: Optional[str] = None,
        period_scope: str = "last_5_years",
        mapping_preset_id: Optional[str] = None,
    ) -> tuple[str, bytes]:
        """Build the Excel workbook for a company.

        Parameters
        ----------
        cd_cvm : int
        statement_type : str, optional
            If set, builds a single-statement scoped workbook.
        period_scope : str
            One of ``last_3_years``, ``last_5_years``, ``last_10_years``,
            ``full_history``.  Defaults to ``last_5_years``.  Current-year
            ITR-only periods (e.g. 1Q26 when 2026 DFP is not yet filed) are
            always appended regardless of scope.
        mapping_preset_id : str, optional
            User mapping preset id.  When omitted, the company default preset
            is used if one exists; otherwise the system default mapping is used.
        """
        if period_scope not in self.VALID_PERIOD_SCOPES:
            raise ValueError(
                f"Invalid period_scope: {period_scope!r}. "
                f"Must be one of: {', '.join(sorted(self.VALID_PERIOD_SCOPES))}"
            )

        company_info = self.get_company_info_dict(cd_cvm)
        if not company_info:
            raise ValueError(f"Empresa {cd_cvm} nao encontrada.")

        scope = self.resolve_excel_export_scope(cd_cvm, period_scope)
        years: list[int] = scope["all_export_years"]
        period_window: tuple[int, int] = scope["period_window"]
        scope_label: str = scope["scope_label"]
        itr_only_years: list[int] = scope["itr_only_years"]

        if not years:
            raise ValueError(
                f"Empresa {cd_cvm} nao possui periodos disponiveis para exportacao."
            )

        if statement_type:
            df = self.get_statement_dataframe(cd_cvm, years, statement_type)
            exportable_statements = {
                statement_type: df
            } if df is not None and not df.empty else {}
            extra_sheets = [statement_type] if statement_type == "DMPL" else []
            kpis_df = pd.DataFrame()
        else:
            all_stmts = {
                stmt_type: self.get_statement_dataframe(cd_cvm, years, stmt_type)
                for stmt_type in EXPORT_STATEMENT_TYPES
            }
            exportable_statements = {
                stmt_type: df
                for stmt_type, df in all_stmts.items()
                if df is not None and not df.empty
            }
            extra_sheets = [
                stmt_type
                for stmt_type in ("DMPL",)
                if stmt_type in exportable_statements
            ]
            kpis_df = self.get_kpi_bundle(cd_cvm, years).quarterly_dataframe()

        model_mapping = None
        mapping_issues: list[MappingValidationIssue] = []
        if not statement_type:
            model_mapping = self.resolve_excel_model_mapping(cd_cvm, mapping_preset_id)
            mapping_issues = self.validate_excel_model_mapping(
                model_mapping,
                exportable_statements,
                company_id=cd_cvm,
                engine=self.engine,
            )
            blocking = [issue for issue in mapping_issues if issue.severity == "error"]
            if blocking:
                first = blocking[0]
                raise ValueError(f"Invalid Excel mapping: {first.message}")

        exporter = ExcelExporter(
            company_info=company_info,
            statements=exportable_statements,
            kpis_df=kpis_df,
            extra_sheets=extra_sheets,
            statement_type=statement_type,
            period_window=period_window,
            period_scope_label=scope_label,
            itr_only_years=itr_only_years,
            model_mapping=model_mapping,
            mapping_validation_issues=mapping_issues,
            engine=self.engine,
        )
        return (
            build_excel_filename(company_info, statement_type=statement_type),
            exporter.export(statement_type=statement_type)
        )
