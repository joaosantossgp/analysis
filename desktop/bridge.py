"""
CVMBridge — funções Python expostas ao JS via window.pywebview.api.*

Convenção pywebview: objetos JS chegam como dict posicional (params=None),
não como kwargs. Use sempre `def method(self, params=None)` + `params.get(...)`.
"""

from __future__ import annotations

import dataclasses
import base64
import json
import logging
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("desktop.bridge")


class CVMBridge:
    DATA_UPDATE_PRESETS = {"top_100", "top_200", "top_500", "all"}
    DATA_UPDATE_BATCH_SIZES = {50, 100, 200, 500}
    DATA_UPDATE_SETTING_KEYS = {
        "data_update_universe_preset",
        "data_update_batch_size",
        "data_update_retry_failed",
        "data_update_recompute_coverage",
        "data_update_start_year",
        "data_update_end_year",
    }
    CVM_MIN_YEAR = 2010

    def __init__(self) -> None:
        self._service = None
        self._refresh_manager = None
        self._onboarding_service = None
        self._company_info_cache: dict[int, dict[str, Any]] = {}
        self._company_info_pending: set[int] = set()
        self._company_info_lock = threading.RLock()
        # auto-updater state
        self._update_info: dict | None = None
        self._latest_update_status: dict | None = None
        self._update_progress: dict = {"status": "idle", "percent": 0, "error": None}
        self._update_lock = threading.Lock()

    def _svc(self):
        if self._service is None:
            from src.read_service import CVMReadService  # noqa: PLC0415
            self._service = CVMReadService()
        return self._service

    def _refresh(self):
        if self._refresh_manager is None:
            from desktop.services import DesktopRefreshJobManager  # noqa: PLC0415

            self._refresh_manager = DesktopRefreshJobManager(read_service=self._svc())
        return self._refresh_manager

    def _onboarding(self):
        if self._onboarding_service is None:
            from src.company_universe import CompanyUniverseService  # noqa: PLC0415

            svc = self._svc()
            self._onboarding_service = CompanyUniverseService(
                settings=svc.settings,
                read_service=svc,
            )
        return self._onboarding_service

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    @staticmethod
    def _bounded_int(
        value: Any,
        *,
        default: int,
        minimum: int = 1,
        maximum: int = 100,
    ) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(default)
        return max(int(minimum), min(int(maximum), parsed))

    @staticmethod
    def _sanitize_for_json(value: Any) -> Any:
        """Recursively replace non-finite floats with None for strict JSON."""
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, dict):
            return {key: CVMBridge._sanitize_for_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [CVMBridge._sanitize_for_json(item) for item in value]
        if isinstance(value, tuple):
            return [CVMBridge._sanitize_for_json(item) for item in value]
        return value

    def _append_runtime_log(self, message: str) -> None:
        """Append bridge diagnostics to the packaged runtime log surface."""
        try:
            raw_data_dir = os.environ.get("CVM_DATA_DIR")
            data_dir = (
                Path(raw_data_dir)
                if raw_data_dir
                else Path(self._svc().settings.paths.data_dir)
            )
            data_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with (data_dir / "recovery.log").open("a", encoding="utf-8") as fh:
                fh.write(f"[{stamp}] {message}\n")
        except Exception:
            logger.debug("failed to append runtime log", exc_info=True)

    def ping(self, params=None) -> dict:
        return self._sanitize_for_json({"pong": True, "ts": time.time()})

    # ------------------------------------------------------------------
    # Diretório de empresas
    # ------------------------------------------------------------------

    def get_companies(self, params=None) -> dict:
        p = params or {}
        t0 = time.perf_counter()
        try:
            result = self._svc().list_companies(
                search=str(p.get("search", "")),
                sector_slug=p.get("sector_slug") or p.get("sector") or None,
                page=self._bounded_int(p.get("page", 1), default=1, maximum=10_000),
                page_size=self._bounded_int(
                    p.get("page_size", p.get("pageSize", 20)),
                    default=20,
                    maximum=100,
                ),
            )
            payload = dataclasses.asdict(result)
            payload["_bridge_ms"] = round((time.perf_counter() - t0) * 1000, 3)
            return self._sanitize_for_json(payload)
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def get_company_filters(self, params=None) -> dict:
        try:
            result = self._svc().get_company_filters()
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "sectors": []}

    def get_company_suggestions(self, params=None) -> dict:
        p = params or {}
        try:
            items = self._svc().suggest_companies(
                q=str(p.get("q", "")),
                limit=self._bounded_int(p.get("limit", 6), default=6, maximum=100),
                ready_only=bool(p.get("ready_only", False)),
            )
            return self._sanitize_for_json({"items": [dataclasses.asdict(i) for i in items]})
        except Exception as exc:
            return {"error": str(exc), "items": []}

    def get_populares(self, params=None) -> dict:
        try:
            result = self._svc().get_populares_companies()
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def get_em_destaque(self, params=None) -> dict:
        p = params or {}
        try:
            result = self._svc().get_em_destaque_companies(
                limit=int(p.get("limit", 10))
            )
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": [], "pagination": {}}

    def track_company_view(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if cd_cvm:
                if not self._is_write_allowed():
                    return {"ok": True, "skipped": True, "reason": "read_only"}
                self._svc().record_company_view(cd_cvm)
            return {"ok": True}
        except Exception:
            return {"ok": False}

    # ------------------------------------------------------------------
    # Detalhe de empresa
    # ------------------------------------------------------------------

    def get_company_info(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            result = self._svc().get_company_info(
                cd_cvm,
                allow_catalog_lookup=True,
            )
            if result is None:
                cached = self._get_cached_company_info(cd_cvm)
                if cached is not None:
                    return self._sanitize_for_json(cached)
                self._queue_company_info_lookup(cd_cvm)
                return {"not_found": True, "catalog_lookup_pending": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def _get_cached_company_info(self, cd_cvm: int) -> dict[str, Any] | None:
        with self._company_info_lock:
            cached = self._company_info_cache.get(int(cd_cvm))
            return dict(cached) if cached is not None else None

    def _queue_company_info_lookup(self, cd_cvm: int) -> None:
        code = int(cd_cvm)
        with self._company_info_lock:
            if code in self._company_info_pending:
                return
            self._company_info_pending.add(code)

        def worker() -> None:
            try:
                result = self._svc().get_company_info(code)
                payload = dataclasses.asdict(result) if result is not None else None
                with self._company_info_lock:
                    if payload is not None:
                        self._company_info_cache[code] = payload
            finally:
                with self._company_info_lock:
                    self._company_info_pending.discard(code)

        threading.Thread(
            target=worker,
            name=f"desktop-company-catalog-{code}",
            daemon=True,
        ).start()

    def get_company_years(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years = self._svc().get_available_years(cd_cvm)
            return self._sanitize_for_json({"years": years})
        except Exception as exc:
            return {"error": str(exc), "years": []}

    def get_company_kpis(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years_raw = p.get("years", [])
            if isinstance(years_raw, str):
                years = [int(y) for y in years_raw.split(",") if y.strip()]
            else:
                years = [int(y) for y in years_raw]
            result = self._svc().get_kpi_bundle(cd_cvm, years)
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_company_historical_indicators(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if not cd_cvm:
                return {"error": "cd_cvm is required", "yearly_data": []}
                
            svc = self._svc()
            
            # Fetch from SQLite via engine
            import pandas as pd  # noqa: PLC0415
            from sqlalchemy import text  # noqa: PLC0415
            
            where_parts = [
                'fr."CD_CVM" = :cd_cvm',
                'fr."PERIOD_LABEL" = CAST(fr."REPORT_YEAR" AS TEXT)',
                'fr."QA_CONFLICT" = false',
                "fr.\"CD_CONTA\" IN ('3.01', '3.05', '3.11', '2.03')",
            ]
            
            df = pd.read_sql(
                text(f"""
                SELECT
                    fr."REPORT_YEAR" AS report_year,
                    fr."CD_CONTA" AS cd_conta,
                    SUM(fr."VL_CONTA") AS account_value
                FROM financial_reports fr
                WHERE {" AND ".join(where_parts)}
                GROUP BY fr."REPORT_YEAR", fr."CD_CONTA"
                """),
                svc.engine,
                params={"cd_cvm": cd_cvm}
            )
            
            metrics_by_year = {}
            if not df.empty:
                pivot = df.pivot(
                    index="report_year",
                    columns="cd_conta",
                    values="account_value"
                ).reset_index()
                
                for col in ("3.01", "3.05", "3.11", "2.03"):
                    if col not in pivot.columns:
                        pivot[col] = pd.NA
                        
                for _, row in pivot.iterrows():
                    yr = int(row["report_year"])
                    receita = float(row["3.01"]) if pd.notna(row["3.01"]) and row["3.01"] != 0 else None
                    ebit = float(row["3.05"]) if pd.notna(row["3.05"]) else None
                    lucro_liq = float(row["3.11"]) if pd.notna(row["3.11"]) else None
                    pl = float(row["2.03"]) if pd.notna(row["2.03"]) and row["2.03"] != 0 else None
                    
                    mg_ebit = ebit / receita if receita and ebit is not None else None
                    mg_liq = lucro_liq / receita if receita and lucro_liq is not None else None
                    roe = lucro_liq / pl if pl and lucro_liq is not None else None
                    
                    metrics_by_year[yr] = {
                        "roe": roe,
                        "mg_ebit": mg_ebit,
                        "mg_liq": mg_liq,
                    }
                    
            # 2. Fetch stock price history from Yahoo Finance
            from src.market_cap import MarketCapService  # noqa: PLC0415
            mkt_cap_svc = MarketCapService(settings=svc.settings, read_service=svc)
            
            # Resolve ticker
            ticker = None
            info = svc.query_layer.get_company_info(cd_cvm)
            if info:
                ticker = info.get("ticker_b3")
            if not ticker:
                from src.ticker_map import TICKER_MAP  # noqa: PLC0415
                ticker = TICKER_MAP.get(cd_cvm)
                
            prices_by_year = {}
            if ticker:
                prices_by_year = mkt_cap_svc.fetch_yahoo_price_history(ticker)
                
            # 3. Merge
            all_years = sorted(list(set(metrics_by_year.keys()) | set(prices_by_year.keys())))
            yearly_data = []
            for yr in all_years:
                m = metrics_by_year.get(yr, {})
                p = prices_by_year.get(yr)
                yearly_data.append({
                    "year": yr,
                    "roe": m.get("roe"),
                    "mg_ebit": m.get("mg_ebit"),
                    "mg_liq": m.get("mg_liq"),
                    "stock_price": p,
                })
                
            return self._sanitize_for_json({
                "ok": True,
                "cd_cvm": cd_cvm,
                "ticker_b3": ticker,
                "yearly_data": yearly_data
            })
            
        except Exception as exc:
            return {"error": str(exc), "yearly_data": []}

    def get_company_statement(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            years_raw = p.get("years", [])
            if isinstance(years_raw, str):
                years = [int(y) for y in years_raw.split(",") if y.strip()]
            else:
                years = [int(y) for y in years_raw]
            stmt = str(p.get("stmt", "bpa"))
            result = self._svc().get_statement_matrix(cd_cvm, years, stmt)
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def download_company_excel(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            filename, payload = self._svc().build_company_excel_export(cd_cvm)
            return self._sanitize_for_json({
                "filename": filename,
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_base64": base64.b64encode(payload).decode("ascii"),
            })
        except Exception as exc:
            return {"error": str(exc)}

    def save_company_excel(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            filename, payload = self._svc().build_company_excel_export(cd_cvm)
            saved_path = self._save_bytes_to_downloads(filename, payload)
            reveal = bool(p.get("reveal", True))
            revealed = self._reveal_in_file_explorer(saved_path) if reveal else False
            return self._sanitize_for_json({
                "filename": filename,
                "saved_path": saved_path,
                "revealed": revealed,
            })
        except Exception as exc:
            return {"error": str(exc)}

    def export_company_excel(self, params=None) -> dict:
        """Phase 3E — write the company workbook into the persistent
        ``output/`` folder under the runtime data root (Documents/CVMAnalytics
        in packaged mode). Distinct from ``save_company_excel``, which
        writes to ``~/Downloads`` for the old browser download flow.

        Returns the absolute output file path, the generated filename, and
        a flag indicating whether the file explorer reveal succeeded.
        Collisions are resolved by suffixing `` (1)``, `` (2)``, ... so an
        existing export is never overwritten.
        """
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("export_company_excel"))
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if cd_cvm <= 0:
                return self._sanitize_for_json({
                    "ok": False,
                    "error": "cd_cvm ausente ou invalido",
                })
            statement_type = p.get("statement_type")
            if statement_type:
                statement_type = str(statement_type).upper()
                if statement_type not in ("DRE", "BPA", "BPP", "DFC", "DVA", "DMPL"):
                    return self._sanitize_for_json({
                        "ok": False,
                        "error": f"Invalid statement type: {statement_type}",
                    })
            period_scope = str(p.get("period_scope") or "last_5_years")
            _VALID_PERIOD_SCOPES = {"last_3_years", "last_5_years", "last_10_years", "full_history"}
            if period_scope not in _VALID_PERIOD_SCOPES:
                return self._sanitize_for_json({
                    "ok": False,
                    "error": (
                        f"Invalid period_scope: {period_scope!r}. "
                        f"Must be one of: {', '.join(sorted(_VALID_PERIOD_SCOPES))}"
                    ),
                })
            mapping_preset_id = str(p.get("mapping_preset_id") or "").strip() or None
            svc = self._svc()
            filename, payload = svc.build_company_excel_export(
                cd_cvm,
                statement_type=statement_type,
                period_scope=period_scope,
                mapping_preset_id=mapping_preset_id,
            )
            output_dir = Path(svc.settings.paths.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            target = self._unique_output_path(output_dir, filename)
            target.write_bytes(payload)
            reveal = bool(p.get("reveal", False))
            revealed = self._reveal_in_file_explorer(str(target)) if reveal else False
            return self._sanitize_for_json({
                "ok": True,
                "file_path": str(target),
                "file_name": target.name,
                "output_dir": str(output_dir),
                "size_bytes": int(target.stat().st_size),
                "revealed": revealed,
            })
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def get_excel_mapping_workspace(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            preset_id = str(p.get("preset_id") or "").strip() or None
            period_scope = str(p.get("period_scope") or "last_5_years")
            result = self._svc().get_excel_mapping_workspace(
                cd_cvm,
                preset_id=preset_id,
                period_scope=period_scope,
            )
            return self._sanitize_for_json(result)
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def save_excel_mapping_preset(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("save_excel_mapping_preset"))
        try:
            result = self._svc().save_excel_mapping_preset(params or {})
            return self._sanitize_for_json(result)
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def set_company_excel_mapping_default(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_company_excel_mapping_default"))
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            preset_id = str(p.get("preset_id") or "system:default").strip()
            result = self._svc().set_company_excel_mapping_default(cd_cvm, preset_id)
            return self._sanitize_for_json(result)
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def get_output_dir(self, params=None) -> dict:
        """Return the absolute path of the persistent output folder so the
        Vite UI can show users where exports will land."""
        try:
            svc = self._svc()
            output_dir = Path(svc.settings.paths.output_dir)
            return self._sanitize_for_json({
                "path": str(output_dir),
                "exists": output_dir.exists(),
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "path": None,
                "exists": False,
                "error": str(exc),
            })

    @staticmethod
    def _unique_output_path(output_dir: Path, filename: str) -> Path:
        safe_name = Path(str(filename or "export.xlsx")).name
        stem = Path(safe_name).stem or "export"
        suffix = Path(safe_name).suffix or ".xlsx"
        candidate = output_dir / safe_name
        counter = 1
        while candidate.exists():
            candidate = output_dir / f"{stem} ({counter}){suffix}"
            counter += 1
        return candidate

    @staticmethod
    def _save_bytes_to_downloads(filename: str, payload: bytes) -> str:
        downloads_dir = Path.home() / "Downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(str(filename or "download.bin")).name
        stem = Path(safe_name).stem or "download"
        suffix = Path(safe_name).suffix
        target = downloads_dir / safe_name
        counter = 1
        while target.exists():
            target = downloads_dir / f"{stem} ({counter}){suffix}"
            counter += 1
        target.write_bytes(payload)
        return str(target)

    @staticmethod
    def _reveal_in_file_explorer(saved_path: str) -> bool:
        path = Path(saved_path)
        try:
            if os.name == "nt":
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
                return True
            subprocess.Popen(["xdg-open", str(path.parent)])
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Setores
    # ------------------------------------------------------------------

    def get_sectors(self, params=None) -> dict:
        try:
            p = params or {}
            result = self._svc().list_sectors(group_by=str(p.get("group_by") or "sector"))
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc), "items": []}

    def get_sector_detail(self, params=None) -> dict:
        p = params or {}
        try:
            slug = str(p.get("sector_slug", ""))
            year = p.get("year")
            year_int = int(year) if year is not None else None
            result = self._svc().get_sector_detail(slug, year_int)
            if result is None:
                return {"not_found": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_sub_sector_detail(self, params=None) -> dict:
        p = params or {}
        try:
            sector_slug = str(p.get("sector_slug", ""))
            sub_industry_slug = str(p.get("sub_industry_slug", ""))
            year = p.get("year")
            year_int = int(year) if year is not None else None
            result = self._svc().get_sub_sector_detail(
                sector_slug=sector_slug,
                sub_industry_slug=sub_industry_slug,
                year=year_int,
            )
            if result is None:
                return {"not_found": True}
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def get_refresh_status(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._refresh().get_refresh_status(params or {}))
        except Exception as exc:
            return self._sanitize_for_json({
                "state": "error",
                "processed": 0,
                "failures": 1,
                "current_cvm": None,
                "log_lines": [str(exc)],
                "error": str(exc),
            })

    def request_refresh(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("request_refresh"))
        p = params or {}
        # Single-company refresh (from no-data company page) routes through the
        # same code path as the HTTP API (`service.request_company_refresh`),
        # which does a full incremental backfill (2010..current). The batch
        # manager defaults to mode="missing" with fast_lane=True, which would
        # only fetch the last 2 years.
        batch_signals = (
            "company_ids",
            "sector_slug",
            "gics_sub_industry",
            "cvm_range",
            "mode",
        )
        is_single_company = (
            p.get("cd_cvm") is not None
            and not any(p.get(key) for key in batch_signals)
        )
        if is_single_company:
            try:
                import dataclasses  # noqa: PLC0415
                cd_cvm = int(p.get("cd_cvm"))
                start_year_raw = p.get("start_year")
                end_year_raw = p.get("end_year")
                start_year = int(start_year_raw) if start_year_raw is not None else None
                end_year = int(end_year_raw) if end_year_raw is not None else None
                result = self._svc().request_company_refresh(
                    cd_cvm,
                    start_year=start_year,
                    end_year=end_year,
                )
                self._svc().invalidate_read_caches()
                return self._sanitize_for_json(dataclasses.asdict(result))
            except Exception as exc:
                return self._sanitize_for_json({
                    "status": "error",
                    "job_id": None,
                    "message": str(exc),
                    "status_reason_code": "desktop_refresh_error",
                    "status_reason_message": str(exc),
                    "is_retry_allowed": True,
                })

        try:
            result = self._refresh().request_refresh(p)
            self._svc().invalidate_read_caches()
            return self._sanitize_for_json(result)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "desktop_refresh_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

    def cancel_refresh(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._refresh().cancel_job(params or {}))
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "message": str(exc)})

    # ------------------------------------------------------------------
    # First-run onboarding
    # ------------------------------------------------------------------

    def get_onboarding_state(self, params=None) -> dict:
        try:
            state = self._onboarding().get_onboarding_state()
            job_id = state.get("refresh_job_id")
            if job_id:
                state["refresh_job"] = self._refresh().get_refresh_status({"job_id": job_id})
            return self._sanitize_for_json(state)
        except Exception as exc:
            return self._sanitize_for_json({
                "first_run_completed": False,
                "should_show": True,
                "setup_status": "error",
                "error": str(exc),
            })

    def start_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("start_onboarding_setup"))
        p = params or {}
        preset = str(p.get("preset") or "").strip().lower()
        try:
            selection = self._onboarding().get_company_universe_by_preset(preset)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "company_universe_unavailable",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

        refresh_params: dict[str, Any] = {
            "mode": "missing",
            "company_ids": list(selection.company_ids),
        }
        for key in ("start_year", "end_year"):
            if p.get(key) not in (None, ""):
                refresh_params[key] = p.get(key)

        try:
            dispatch = self._refresh().request_refresh(refresh_params)
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "desktop_refresh_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
                "selection": selection.to_dict(),
            })

        if str(dispatch.get("status") or "").lower() in {"error", "already_running"}:
            dispatch["selection"] = selection.to_dict()
            return self._sanitize_for_json(dispatch)

        job_id = dispatch.get("job_id")
        self._onboarding().mark_setup_started(
            selection,
            refresh_job_id=str(job_id) if job_id else None,
        )
        if not job_id:
            self._onboarding().mark_setup_completed(status=str(dispatch.get("status") or "success"))
        self._svc().invalidate_read_caches()
        return self._sanitize_for_json({
            **dispatch,
            "selection": selection.to_dict(),
        })

    def complete_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("complete_onboarding_setup"))
        try:
            status = str((params or {}).get("status") or "success")
            return self._sanitize_for_json(self._onboarding().mark_setup_completed(status=status))
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def skip_onboarding_setup(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("skip_onboarding_setup"))
        try:
            return self._sanitize_for_json(self._onboarding().skip_setup())
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    # ------------------------------------------------------------------
    # Market Cap List
    # ------------------------------------------------------------------

    def get_market_cap_list(self, params=None) -> dict:
        try:
            from src.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            entries = market_cap_service.read_snapshot()
            return self._sanitize_for_json({
                "ok": True,
                "items": [e.to_dict() for e in entries]
            })
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc), "items": []})

    def import_market_cap_snapshot(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("import_market_cap_snapshot"))
        p = params or {}
        csv_content = p.get("csv_content")
        file_path = p.get("file_path")
        try:
            from src.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            if csv_content:
                import io  # noqa: PLC0415
                res = market_cap_service.import_snapshot(io.StringIO(str(csv_content)))
            elif file_path:
                res = market_cap_service.import_snapshot(Path(str(file_path)))
            else:
                return self._sanitize_for_json({
                    "ok": False,
                    "error": "Either csv_content or file_path must be provided."
                })
            self._svc().invalidate_read_caches()
            return self._sanitize_for_json({"ok": True, "status": res})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def get_market_cap_status(self, params=None) -> dict:
        try:
            from src.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            status = market_cap_service.get_status()
            return self._sanitize_for_json(status)
        except Exception as exc:
            return self._sanitize_for_json({
                "available": False,
                "row_count": 0,
                "error": str(exc)
            })

    def fetch_latest_market_cap(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("fetch_latest_market_cap"))
        try:
            from src.market_cap import MarketCapService  # noqa: PLC0415
            svc = self._svc()
            market_cap_service = MarketCapService(settings=svc.settings, read_service=svc)
            status = market_cap_service.fetch_from_yahoo_finance()
            self._svc().invalidate_read_caches()
            return self._sanitize_for_json({"ok": True, "status": status})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    # ------------------------------------------------------------------
    # Central data update settings / operations
    # ------------------------------------------------------------------

    def get_data_update_settings(self, params=None) -> dict:
        try:
            return self._sanitize_for_json(self._resolve_data_update_settings())
        except Exception as exc:
            return self._sanitize_for_json({
                **self._default_data_update_settings(),
                "error": str(exc),
            })

    def save_data_update_settings(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("save_data_update_settings"))
        p = params or {}
        try:
            settings = self._normalize_data_update_settings(p)
            self._write_app_settings(settings)
            return self._sanitize_for_json(settings)
        except Exception as exc:
            return self._sanitize_for_json({
                **self._default_data_update_settings(),
                "error": str(exc),
            })

    def get_company_universe_selection(self, params=None) -> dict:
        p = params or {}
        try:
            settings = self._resolve_data_update_settings()
            preset = str(p.get("preset") or settings["universe_preset"]).strip().lower()
            if preset not in self.DATA_UPDATE_PRESETS:
                raise ValueError(f"Universo de empresas invalido: {preset}")
            selection = self._onboarding().get_company_universe_by_preset(preset)
            return self._sanitize_for_json(selection.to_dict())
        except Exception as exc:
            return self._sanitize_for_json({
                "preset": str((params or {}).get("preset") or ""),
                "selected_count": 0,
                "company_ids": [],
                "source": None,
                "source_date": None,
                "warning": None,
                "companies": [],
                "error": str(exc),
            })

    def start_data_update(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("start_data_update"))
        from src.company_universe import CompanyUniverseUnavailableError  # noqa: PLC0415

        p = params or {}
        try:
            current_settings = self._resolve_data_update_settings()
            settings = self._normalize_data_update_settings({
                **current_settings,
                **p,
            })
            mode = str(p.get("mode") or "missing").strip().lower()
            if mode not in {"missing", "full", "outdated", "failed"}:
                raise ValueError(f"Invalid update mode: {mode}")

            selection = self._onboarding().get_company_universe_by_preset(
                str(settings["universe_preset"])
            )
            refresh_params: dict[str, Any] = {
                "mode": mode,
                "company_ids": list(selection.company_ids),
                # The current backend processes one queue per request. This is
                # the safe per-run cap exposed as "empresas por lote" in the UI.
                "limit": int(settings["batch_size"]),
                "start_year": int(settings["start_year"]),
                "end_year": int(settings["end_year"]),
            }

            dispatch = self._refresh().request_refresh(refresh_params)
            if str(dispatch.get("status") or "").lower() not in {
                "error",
                "already_running",
            }:
                self._write_app_settings(settings)
            self._svc().invalidate_read_caches()
            return self._sanitize_for_json({
                **dispatch,
                "selection": selection.to_dict(),
                "settings": settings,
            })
        except CompanyUniverseUnavailableError as exc:
            # Universe unavailable — try an inline market-cap fetch when auto-refresh
            # is enabled and the provider is yahoo_finance.  This covers the first-run
            # case where no snapshot exists yet: the refresh job would create one, but
            # it needs the universe to start.  Fetching here breaks the chicken-and-egg.
            svc_settings = self._svc().settings
            if (
                svc_settings.market_cap_auto_refresh
                and svc_settings.market_cap_provider in ("yahoo_finance", "yfinance")
            ):
                try:
                    logger.info(
                        "start_data_update: universe unavailable, fetching market-cap snapshot inline"
                    )
                    from src.market_cap import MarketCapService  # noqa: PLC0415
                    from src.read_service import CVMReadService  # noqa: PLC0415

                    _rs = CVMReadService(settings=svc_settings)
                    MarketCapService(settings=svc_settings, read_service=_rs).fetch_from_yahoo_finance()
                    # Retry universe resolution with the freshly created snapshot
                    self._svc().invalidate_read_caches()
                    selection = self._onboarding().get_company_universe_by_preset(
                        str(settings["universe_preset"])
                    )
                    refresh_params["company_ids"] = list(selection.company_ids)
                    dispatch = self._refresh().request_refresh(refresh_params)
                    if str(dispatch.get("status") or "").lower() not in {
                        "error",
                        "already_running",
                    }:
                        self._write_app_settings(settings)
                    self._svc().invalidate_read_caches()
                    return self._sanitize_for_json({
                        **dispatch,
                        "selection": selection.to_dict(),
                        "settings": settings,
                    })
                except Exception as fetch_exc:
                    logger.warning(
                        "start_data_update: inline market-cap fetch failed: %s", fetch_exc
                    )
                    # Fall through to the blocked response below

            logger.warning("start_data_update blocked: company universe unavailable: %s", exc)
            self._append_runtime_log(
                f"start_data_update blocked: company_universe_unavailable: {exc}"
            )
            return self._sanitize_for_json({
                "status": "blocked",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "company_universe_unavailable",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })
        except Exception as exc:
            logger.exception("start_data_update failed")
            self._append_runtime_log(f"start_data_update failed: {exc}")
            return self._sanitize_for_json({
                "status": "error",
                "job_id": None,
                "message": str(exc),
                "status_reason_code": "data_update_error",
                "status_reason_message": str(exc),
                "is_retry_allowed": True,
            })

    def reset_local_database(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("reset_local_database"))
        p = params or {}
        action = str(p.get("action") or "").strip().lower()
        expected = "RESET" if action == "restart_current" else "REBUILD"
        if action not in {"restart_current", "recreate_local"}:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": "Invalid reset action.",
            })
        if str(p.get("confirm") or "") != expected:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": f"Type {expected} to confirm.",
            })

        try:
            active_job = self._active_refresh_job()
            if active_job is not None:
                return self._sanitize_for_json({
                    "ok": False,
                    "action": action,
                    "error": "An update is in progress. Cancel or wait for it to finish before resetting the database.",
                    "active_job_id": active_job.get("job_id"),
                })

            if action == "restart_current":
                result = self._restart_current_database_state()
            else:
                result = self._recreate_local_database()
            self._reset_bridge_runtime()
            return self._sanitize_for_json({
                "ok": True,
                "action": action,
                **result,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "action": action,
                "error": str(exc),
            })

    def _default_data_update_settings(self) -> dict[str, Any]:
        preset = "top_200"
        try:
            state = self._onboarding().get_onboarding_state()
            selected = str(state.get("selected_company_universe") or "").strip().lower()
            if selected in self.DATA_UPDATE_PRESETS:
                preset = selected
        except Exception:
            pass
        current_year = datetime.now(timezone.utc).year
        return {
            "universe_preset": preset,
            "batch_size": 100,
            "retry_failed": True,
            "recompute_coverage": True,
            "start_year": current_year - 4,
            "end_year": current_year,
        }

    def _resolve_data_update_settings(self) -> dict[str, Any]:
        defaults = self._default_data_update_settings()
        stored = self._read_app_settings(self.DATA_UPDATE_SETTING_KEYS)
        raw = {
            "universe_preset": stored.get("data_update_universe_preset", defaults["universe_preset"]),
            "batch_size": stored.get("data_update_batch_size", defaults["batch_size"]),
            "retry_failed": stored.get("data_update_retry_failed", defaults["retry_failed"]),
            "recompute_coverage": stored.get("data_update_recompute_coverage", defaults["recompute_coverage"]),
            "start_year": stored.get("data_update_start_year", defaults["start_year"]),
            "end_year": stored.get("data_update_end_year", defaults["end_year"]),
        }
        return self._normalize_data_update_settings(raw)

    def _normalize_data_update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        preset = str(
            payload.get("universe_preset")
            or payload.get("preset")
            or payload.get("selected_company_universe")
            or "top_200"
        ).strip().lower()
        if preset not in self.DATA_UPDATE_PRESETS:
            raise ValueError(f"Universo de empresas invalido: {preset}")

        try:
            batch_size = int(payload.get("batch_size") or 100)
        except (TypeError, ValueError) as exc:
            raise ValueError("Empresas por lote deve ser 50, 100, 200 ou 500.") from exc
        if batch_size not in self.DATA_UPDATE_BATCH_SIZES:
            raise ValueError("Empresas por lote deve ser 50, 100, 200 ou 500.")

        current_year = datetime.now(timezone.utc).year
        default_start = current_year - 4
        default_end = current_year
        try:
            start_year = int(payload.get("start_year") or default_start)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ano inicial deve ser um numero inteiro.") from exc
        try:
            end_year = int(payload.get("end_year") or default_end)
        except (TypeError, ValueError) as exc:
            raise ValueError("Ano final deve ser um numero inteiro.") from exc
        if start_year < self.CVM_MIN_YEAR:
            raise ValueError(f"Ano inicial minimo permitido: {self.CVM_MIN_YEAR}.")
        if end_year > current_year:
            raise ValueError(f"Ano final maximo permitido: {current_year}.")
        if start_year > end_year:
            raise ValueError(f"Ano inicial ({start_year}) nao pode ser maior que o ano final ({end_year}).")

        return {
            "universe_preset": preset,
            "batch_size": batch_size,
            "retry_failed": self._coerce_bool(payload.get("retry_failed"), default=True),
            "recompute_coverage": self._coerce_bool(
                payload.get("recompute_coverage"),
                default=True,
            ),
            "start_year": start_year,
            "end_year": end_year,
        }

    @staticmethod
    def _coerce_bool(value: Any, *, default: bool) -> bool:
        if value is None:
            return bool(default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim", "on"}
        return bool(value)

    def _read_app_settings(self, keys: set[str]) -> dict[str, Any]:
        from sqlalchemy import bindparam, text  # noqa: PLC0415
        from src.company_universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415

        with self._svc().engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            rows = conn.execute(
                text("SELECT key, value FROM app_settings WHERE key IN :keys")
                .bindparams(bindparam("keys", expanding=True)),
                {"keys": sorted(keys)},
            ).mappings().all()

        parsed: dict[str, Any] = {}
        for row in rows:
            key = str(row["key"])
            raw = row.get("value")
            try:
                parsed[key] = json.loads(raw) if raw is not None else None
            except Exception:
                parsed[key] = raw
        return parsed

    def _write_app_settings(self, settings: dict[str, Any]) -> None:
        from sqlalchemy import text  # noqa: PLC0415
        from src.company_universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415

        values = {
            "data_update_universe_preset": settings["universe_preset"],
            "data_update_batch_size": int(settings["batch_size"]),
            "data_update_retry_failed": bool(settings["retry_failed"]),
            "data_update_recompute_coverage": bool(settings["recompute_coverage"]),
            "data_update_start_year": int(settings["start_year"]),
            "data_update_end_year": int(settings["end_year"]),
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._svc().engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            for key, value in values.items():
                conn.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": key})
                conn.execute(
                    text(
                        """
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (:key, :value, :updated_at)
                        """
                    ),
                    {
                        "key": key,
                        "value": json.dumps(value, ensure_ascii=True),
                        "updated_at": now,
                    },
                )

    def _active_refresh_job(self) -> dict[str, Any] | None:
        try:
            response = self._refresh().get_refresh_status({})
            for item in response.get("items", []):
                if str(item.get("state") or "").lower() in {"queued", "running"}:
                    return dict(item)
        except Exception:
            return None
        return None

    def _restart_current_database_state(self) -> dict[str, Any]:
        from sqlalchemy import text  # noqa: PLC0415
        from src.company_universe import ensure_company_universe_tables_for_connection  # noqa: PLC0415
        from src.refresh_jobs import ensure_refresh_runtime_tables_for_connection  # noqa: PLC0415

        svc = self._svc()
        removed: list[str] = []
        settings_snapshot = self._resolve_data_update_settings()

        blank: dict[str, Any] = {
            "first_run_completed": False,
            "should_show": True,
            "selected_company_universe": None,
            "company_universe_source": None,
            "company_universe_source_date": None,
            "setup_status": None,
            "selected_company_count": 0,
            "refresh_job_id": None,
            "warning": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        onboarding = self._onboarding()
        onboarding._write_state(blank)  # type: ignore[attr-defined]

        with svc.engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)
            ensure_refresh_runtime_tables_for_connection(conn)
            conn.execute(text("DELETE FROM company_universe"))
            conn.execute(text("DELETE FROM refresh_jobs"))
            conn.execute(text("DELETE FROM company_refresh_status"))
            conn.execute(
                text(
                    """
                    DELETE FROM app_settings
                    WHERE key IN (
                        'first_run_completed',
                        'selected_company_universe',
                        'company_universe_source',
                        'company_universe_source_date',
                        'download_status',
                        'refresh_job_id'
                    )
                    """
                )
            )
        removed.extend(["company_universe", "refresh_jobs", "company_refresh_status", "onboarding_state"])
        self._remove_runtime_state_files(removed)
        self._write_app_settings(settings_snapshot)
        svc.invalidate_read_caches()
        return {
            "backup_path": None,
            "removed": removed,
            "message": "Setup state and update history cleared. Local financial data was preserved.",
        }

    def _recreate_local_database(self) -> dict[str, Any]:
        from src.database import init_db_tables  # noqa: PLC0415
        from src.db import build_engine  # noqa: PLC0415

        svc = self._svc()
        if svc.settings.database_url:
            raise RuntimeError("Automatic rebuild is only supported for local SQLite databases.")

        settings_snapshot = self._resolve_data_update_settings()
        db_path = Path(svc.settings.paths.db_path)
        data_dir = Path(svc.settings.paths.data_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = data_dir / "backup" / f"db-reset-{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        backup_items = self._backup_database_artifacts(db_path, backup_dir)

        try:
            svc.engine.dispose()
        except Exception:
            pass

        removed: list[str] = []
        for candidate in (db_path, db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
            if candidate.exists():
                candidate.unlink()
                removed.append(str(candidate))
        self._remove_runtime_state_files(removed)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = build_engine(svc.settings)
        try:
            init_db_tables(engine)
        finally:
            engine.dispose()

        self._reset_bridge_runtime()
        self._write_app_settings(settings_snapshot)
        return {
            "backup_path": str(backup_dir),
            "backup_items": backup_items,
            "removed": removed,
            "message": "Local SQLite database rebuilt. Start an update to populate the database.",
        }

    def _backup_database_artifacts(self, db_path: Path, backup_dir: Path) -> list[str]:
        copied: list[str] = []
        if db_path.exists():
            target = backup_dir / db_path.name
            src_uri = f"file:{db_path.as_posix()}?mode=ro"
            src = sqlite3.connect(src_uri, uri=True)
            try:
                dst = sqlite3.connect(str(target))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            copied.append(str(target))

        for source in (
            db_path.with_name(db_path.name + "-wal"),
            db_path.with_name(db_path.name + "-shm"),
            Path(self._svc().settings.paths.data_dir) / "refresh_jobs.json",
            Path(self._svc().settings.paths.onboarding_state_path),
            Path(self._svc().settings.paths.base_health_snapshot_path),
        ):
            if source.exists():
                target = backup_dir / source.name
                shutil.copy2(source, target)
                copied.append(str(target))
        return copied

    def _remove_runtime_state_files(self, removed: list[str]) -> None:
        svc = self._svc()
        for path in (
            Path(svc.settings.paths.data_dir) / "refresh_jobs.json",
            Path(svc.settings.paths.onboarding_state_path),
            Path(svc.settings.paths.base_health_snapshot_path),
        ):
            if path.exists():
                path.unlink()
                removed.append(str(path))

    def _reset_bridge_runtime(self) -> None:
        for service in (self._service,):
            try:
                if service is not None:
                    service.engine.dispose()
            except Exception:
                pass
        self._service = None
        self._refresh_manager = None
        self._onboarding_service = None
        self._company_info_cache.clear()
        self._company_info_pending.clear()

    # ------------------------------------------------------------------
    # Dev tools — only callable from /dev/data-ops (DEV build + flag)
    # Never add user-visible entry points to these methods.
    # ------------------------------------------------------------------

    def dev_reset_onboarding(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_onboarding"))
        try:
            svc = self._onboarding()
            blank: dict = {
                "first_run_completed": False,
                "should_show": True,
                "selected_company_universe": None,
                "company_universe_source": None,
                "company_universe_source_date": None,
                "setup_status": None,
                "selected_company_count": 0,
                "refresh_job_id": None,
                "warning": None,
            }
            svc._write_state(blank)  # type: ignore[attr-defined]
            svc._write_app_settings(blank)  # type: ignore[attr-defined]
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_reset_universe(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_universe"))
        try:
            from sqlalchemy import text  # noqa: PLC0415
            with self._svc().engine.begin() as conn:
                conn.execute(text("DELETE FROM company_universe"))
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_reset_jobs(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_reset_jobs"))
        try:
            from sqlalchemy import text  # noqa: PLC0415
            with self._svc().engine.begin() as conn:
                conn.execute(text("DELETE FROM refresh_jobs"))
                conn.execute(text("DELETE FROM company_refresh_status"))
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    def dev_simulate_refresh(self, params=None) -> dict:  # noqa: C901
        """Insert synthetic job rows so UI can exercise all terminal states."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_simulate_refresh"))
        import threading  # noqa: PLC0415
        import uuid  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415
        from src.refresh_jobs import ensure_refresh_runtime_tables  # noqa: PLC0415

        mode = str((params or {}).get("mode") or "success").lower()
        engine = self._svc().engine
        ensure_refresh_runtime_tables(engine)

        _MOCK_CVM = 99999999
        _MOCK_NAME = "DEV_MOCK_COMPANY"
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        def _upsert(job_id: str, state: str, stage: str | None = None,
                    cur: int = 0, tot: int = 10, err: str | None = None,
                    finished: bool = False) -> None:
            fin = now if finished else None
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM refresh_jobs WHERE id = :id"), {"id": job_id})
                conn.execute(
                    text(
                        "INSERT INTO refresh_jobs "
                        "(id, cd_cvm, company_name, source_scope, start_year, end_year, "
                        " state, stage, requested_at, started_at, finished_at, "
                        " progress_current, progress_total, error_message) "
                        "VALUES (:id, :cvm, :name, 'dev_mock', 2024, 2024, "
                        ":state, :stage, :now, :now, :fin, :cur, :tot, :err)"
                    ),
                    {
                        "id": job_id, "cvm": _MOCK_CVM, "name": _MOCK_NAME,
                        "state": state, "stage": stage, "now": now, "fin": fin,
                        "cur": cur, "tot": tot, "err": err,
                    },
                )

        if mode in ("success", "partial", "fail"):
            jid = str(uuid.uuid4())
            if mode == "success":
                _upsert(jid, "success", "finalizing", 10, 10, finished=True)
            elif mode == "fail":
                _upsert(jid, "error", None, 0, 10,
                        err="[dev_simulate] Simulated failure", finished=True)
            else:  # partial
                _upsert(str(uuid.uuid4()), "success", "finalizing", 10, 10, finished=True)
                _upsert(str(uuid.uuid4()), "error", None, 3, 10,
                        err="[dev_simulate] Simulated partial failure", finished=True)
            return self._sanitize_for_json({"ok": True, "mode": mode, "job_id": jid})

        # slow — advance through stages in background; worker ignores RUNNING rows
        jid = str(uuid.uuid4())
        _upsert(jid, "running", "planning", 0, 10)

        def _advance() -> None:
            import time as _t  # noqa: PLC0415
            stages = [
                ("download_extract", 2, 10),
                ("process_data", 5, 10),
                ("persist_reports", 8, 10),
                ("finalizing", 9, 10),
            ]
            for stage, cur, tot in stages:
                _t.sleep(3)
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE refresh_jobs SET stage=:stage, progress_current=:cur, "
                            "progress_total=:tot WHERE id=:id"
                        ),
                        {"stage": stage, "cur": cur, "tot": tot, "id": jid},
                    )
            _t.sleep(2)
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE refresh_jobs SET state='success', stage='finalizing', "
                        "progress_current=10, progress_total=10, "
                        "finished_at=:now WHERE id=:id"
                    ),
                    {"now": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"), "id": jid},
                )

        threading.Thread(target=_advance, daemon=True).start()
        return self._sanitize_for_json({"ok": True, "mode": "slow", "job_id": jid})

    def dev_start_small_setup(self, params=None) -> dict:
        """Run request_refresh against the first N companies already in the local DB."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("dev_start_small_setup"))
        count = min(int((params or {}).get("count") or 5), 10)
        try:
            page = self._svc().list_companies(page=1, page_size=count, search="")
            cd_cvms = [int(c["cd_cvm"]) for c in page.get("items", [])]
            if not cd_cvms:
                return self._sanitize_for_json({
                    "status": "error",
                    "message": "No companies in local DB yet. Run a preset first.",
                })
            return self._sanitize_for_json(
                self._refresh().request_refresh({
                    "mode": "missing",
                    "company_ids": cd_cvms,
                })
            )
        except Exception as exc:
            return self._sanitize_for_json({"status": "error", "message": str(exc)})

    def dev_get_raw_state(self, params=None) -> dict:
        """Return raw app_settings and recent refresh_jobs for the dev inspector."""
        try:
            from sqlalchemy import text  # noqa: PLC0415
            engine = self._svc().engine
            with engine.connect() as conn:
                settings_rows = [
                    {"key": str(r[0]), "value": str(r[1]) if r[1] is not None else None,
                     "updated_at": str(r[2]) if r[2] is not None else None}
                    for r in conn.execute(
                        text("SELECT key, value, updated_at FROM app_settings ORDER BY key")
                    )
                ]
                jobs_rows = [
                    {
                        "id": str(r[0]), "cd_cvm": int(r[1]),
                        "company_name": r[2],
                        "state": str(r[3]), "stage": r[4],
                        "progress_current": r[5], "progress_total": r[6],
                        "error_message": r[7],
                        "requested_at": r[8], "started_at": r[9], "finished_at": r[10],
                    }
                    for r in conn.execute(
                        text(
                            "SELECT id, cd_cvm, company_name, state, stage, "
                            "progress_current, progress_total, error_message, "
                            "requested_at, started_at, finished_at "
                            "FROM refresh_jobs ORDER BY requested_at DESC LIMIT 30"
                        )
                    )
                ]
            return self._sanitize_for_json({
                "app_settings": settings_rows,
                "refresh_jobs": jobs_rows,
            })
        except Exception as exc:
            return self._sanitize_for_json({"error": str(exc)})

    # ------------------------------------------------------------------
    # Internal refresh worker (drena jobs enfileirados em refresh_jobs)
    # ------------------------------------------------------------------

    def _start_refresh_worker(self) -> None:
        """Called from a daemon thread in app.py after window creation.

        Jobs enfileirados via ``CVMReadService.request_company_refresh``
        (caminho single-company com período) ficam pendentes na tabela
        ``refresh_jobs``. Sem este worker, eles nunca rodam no .exe.
        """
        try:
            from src.refresh_job_worker import (  # noqa: PLC0415
                RefreshJobWorker,
                RefreshWorkerConfig,
            )
            from src.refresh_service import HeadlessRefreshService  # noqa: PLC0415

            svc = self._svc()
            # Reusa o repository já inicializado pelo CVMReadService
            # (mesmo engine sqlite local, esquema já garantido).
            repository = svc.refresh_job_repository
            try:
                repository.ensure_schema()
            except Exception:
                pass

            refresh_service = HeadlessRefreshService(settings=svc.settings)
            worker = RefreshJobWorker(
                settings=svc.settings,
                repository=repository,
                refresh_service=refresh_service,
                config=RefreshWorkerConfig(),
            )
            worker.run_forever()
        except Exception:
            # Worker é best-effort: se falhar, o usuário ainda vê o status
            # "queued" no UI mas não trava o app.
            pass

    # ------------------------------------------------------------------
    # Auto-updater
    # ------------------------------------------------------------------

    def _start_update_check(self) -> None:
        """Called from a daemon thread in app.py after window creation."""
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop.updater import UpdateChecker  # noqa: PLC0415
            checker = UpdateChecker()
            info = checker.check_for_update(__version__)
            with self._update_lock:
                self._update_info = info
        except Exception:
            pass

    def check_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
        if not info:
            return self._sanitize_for_json({"available": False})
        return self._sanitize_for_json({
            "available": True,
            "version": info["version"],
            "zip_url": info["zip_url"],
        })

    def apply_update(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("apply_update"))
        with self._update_lock:
            info = self._update_info
            if not info:
                return self._sanitize_for_json({"error": "no_update_available"})
            if self._update_progress.get("status") == "downloading":
                return self._sanitize_for_json({"error": "already_in_progress"})
            self._update_progress = {"status": "downloading", "percent": 0, "error": None}

        def _run() -> None:
            try:
                from desktop.updater import UpdateChecker, _log as _update_log  # noqa: PLC0415
                _update_log(
                    f"apply_update invoked: version={info.get('version')} "
                    f"tag={info.get('tag')} zip_url={info.get('zip_url')}"
                )
                checker = UpdateChecker()

                def _progress(status: str, percent: int) -> None:
                    with self._update_lock:
                        self._update_progress = {"status": status, "percent": percent, "error": None}

                staged = checker.download_and_stage(info, _progress)

                with self._update_lock:
                    self._update_progress = {"status": "swapping", "percent": 100, "error": None}

                checker.spawn_helper_and_exit(staged)

                import webview  # noqa: PLC0415
                for w in webview.windows:
                    w.destroy()

            except Exception as exc:
                try:
                    from desktop.updater import _log as _update_log  # noqa: PLC0415
                    _update_log(f"ERROR apply_update failed: {exc}")
                except Exception:
                    pass
                with self._update_lock:
                    self._update_progress = {"status": "error", "percent": 0, "error": str(exc)}

        threading.Thread(target=_run, name="desktop-apply-update", daemon=True).start()
        return self._sanitize_for_json({"started": True})

    def get_update_progress(self, params=None) -> dict:
        with self._update_lock:
            return self._sanitize_for_json(dict(self._update_progress))

    def snooze_update(self, params=None) -> dict:
        with self._update_lock:
            info = self._update_info
        if not info:
            return self._sanitize_for_json({"ok": False, "error": "no_update_info"})
        try:
            from desktop.updater import UpdateChecker  # noqa: PLC0415
            UpdateChecker().snooze(info["tag"])
            return self._sanitize_for_json({"ok": True})
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "error": str(exc)})

    # ------------------------------------------------------------------
    # App status / Health / diagnostico
    # ------------------------------------------------------------------

    def get_app_status(self, params=None) -> dict:
        """Compact local runtime status for the packaged Vite UI."""
        p = params or {}
        force_update_check = self._truthy(p.get("force_update_check", False))
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415

            svc = self._svc()
            paths = svc.settings.paths
            path_map = self._status_path_map()
            database = self.get_database_diagnostics({})
            update = self._get_software_update_status(force=force_update_check)
            diagnostics = self._runtime_diagnostics_summary(paths)
            recent = self._collect_recent_diagnostics(paths, database)
            from desktop import lockfile as _lockfile  # noqa: PLC0415

            build_commit, build_time = self._build_provenance()

            return self._sanitize_for_json({
                "runtime": {
                    "version": __version__,
                    "build_commit": build_commit,
                    "build_time": build_time,
                    "runtime_mode": self._runtime_mode(),
                    "bridge_status": "ready",
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "desktop_shell": "pywebview/WebView2",
                    "local_first": True,
                    "using_release_data_dir": self._using_release_data_dir(),
                    "write_mode": "read-write" if self._is_write_allowed() else "read-only",
                    "lock_status": _lockfile.get_status(),
                },
                "paths": {
                    key: self._path_payload(key, value)
                    for key, value in path_map.items()
                },
                "database": database,
                "update": update,
                "diagnostics": diagnostics,
                "recent": recent,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "runtime": {
                    "version": "unknown",
                    "runtime_mode": self._runtime_mode(),
                    "bridge_status": "error",
                    "frozen": bool(getattr(sys, "frozen", False)),
                    "desktop_shell": "pywebview/WebView2",
                    "local_first": True,
                    "using_release_data_dir": self._using_release_data_dir(),
                },
                "paths": {},
                "database": None,
                "update": None,
                "diagnostics": {
                    "ok": False,
                    "errors": [str(exc)],
                    "warnings": [],
                },
                "recent": [],
                "error": str(exc),
            })

    def open_status_path(self, params=None) -> dict:
        """Open one of the known local diagnostics folders.

        Deliberately accepts only symbolic path kinds; the UI cannot pass an
        arbitrary filesystem path to this method.
        """
        p = params or {}
        kind = str(p.get("kind") or "").strip().lower()
        try:
            path_map = self._status_path_map()
            if kind not in path_map:
                return self._sanitize_for_json({
                    "ok": False,
                    "kind": kind,
                    "path": None,
                    "error": "unsupported_path_kind",
                })
            target = Path(path_map[kind])
            if kind == "database":
                target = target.parent
            if kind in {"data", "output", "logs", "cache"}:
                target.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                return self._sanitize_for_json({
                    "ok": False,
                    "kind": kind,
                    "path": str(target),
                    "error": "path_not_found",
                })
            self._open_local_folder(target)
            return self._sanitize_for_json({
                "ok": True,
                "kind": kind,
                "path": str(target),
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "kind": kind,
                "path": None,
                "error": str(exc),
            })

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim", "on"}
        return bool(value)

    @staticmethod
    def _build_provenance() -> tuple[str | None, str | None]:
        """Return (build_commit, build_time) written by build_desktop.ps1.

        Generated builds ship desktop/_build_info.py. Dev runs have no such
        file, so a missing module reports (None, None) rather than failing.
        """
        try:
            from desktop._build_info import build_commit, build_time  # noqa: PLC0415

            return (build_commit or None, build_time or None)
        except Exception:
            return (None, None)

    @staticmethod
    def _runtime_mode() -> str:
        argv = {str(arg).lower() for arg in sys.argv}
        if "--dev" in argv and not getattr(sys, "frozen", False):
            use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
                "1", "true", "yes",
            }
            return "vite-dev-release-data" if use_release else "vite-dev"
        return "vite"

    @staticmethod
    def _using_release_data_dir() -> bool:
        if getattr(sys, "frozen", False):
            return True
        return os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _is_write_allowed() -> bool:
        """Returns True if destructive/write operations are safe in this mode."""
        if getattr(sys, "frozen", False):
            return True
        use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
            "1", "true", "yes",
        }
        if not use_release:
            return True
        # Concurrent lock detected — block writes unconditionally.
        if os.environ.get("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "").strip() == "1":
            return False
        # Allow writes only when explicitly opted in.
        return os.environ.get("CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES", "").strip().lower() in {
            "1", "true", "yes",
        }

    @staticmethod
    def _write_blocked_response(op_name: str = "operation") -> dict:
        concurrent = os.environ.get("CVMANALYTICS_CONCURRENT_LOCK_DETECTED", "").strip() == "1"
        if concurrent:
            msg = (
                f"Write blocked: release data directory is in use by another CVMAnalytics process. "
                "Close the packaged app before running write operations from dev mode."
            )
            code = "concurrent_lock_conflict"
        else:
            msg = (
                f"Write blocked: dev mode is using the release data directory. "
                "Set CVMANALYTICS_ALLOW_RELEASE_DATA_WRITES=1 to enable writes, "
                "or use isolated dev data (omit CVMANALYTICS_USE_RELEASE_DATA)."
            )
            code = "release_data_write_blocked"
        return {
            "ok": False,
            "status": "blocked",
            "error": msg,
            "status_reason_code": code,
            "status_reason_message": msg,
            "is_retry_allowed": False,
        }

    def _status_path_map(self) -> dict[str, Path]:
        paths = self._svc().settings.paths
        return {
            "data": Path(paths.data_dir),
            "database": Path(paths.db_path),
            "output": Path(paths.output_dir),
            "logs": Path(paths.logs_dir),
            "cache": Path(paths.cache_dir),
        }

    @staticmethod
    def _path_payload(kind: str, path: Path) -> dict:
        path = Path(path)
        return {
            "kind": kind,
            "path": str(path),
            "exists": path.exists(),
            "is_file": path.is_file(),
            "is_dir": path.is_dir(),
        }

    @staticmethod
    def _open_local_folder(target: Path) -> None:
        if os.name == "nt":
            os.startfile(str(target))  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
            return
        subprocess.Popen(["xdg-open", str(target)])

    def _get_software_update_status(self, *, force: bool = False) -> dict:
        with self._update_lock:
            cached_status = dict(self._latest_update_status or {})
            cached_info = dict(self._update_info or {})
            progress = dict(self._update_progress)
        if cached_status and not force:
            return self._sanitize_for_json({
                **cached_status,
                "progress": progress,
                "apply_supported": True,
            })
        try:
            from desktop.__version__ import __version__  # noqa: PLC0415
            from desktop.updater import UpdateChecker  # noqa: PLC0415
 
            checker = UpdateChecker()
            status = checker.get_latest_release_status(__version__)
            if status.get("update_available") and status.get("zip_url"):
                update_info = {
                    "version": status.get("latest_version"),
                    "tag": status.get("latest_tag"),
                    "zip_url": status.get("zip_url"),
                    "sha256_url": status.get("sha256_url"),
                }
                with self._update_lock:
                    self._update_info = update_info
            elif status.get("status") == "check_failed" and cached_info:
                status = {
                    **status,
                    "status": "available_cached",
                    "latest_version": cached_info.get("version"),
                    "latest_tag": cached_info.get("tag"),
                    "zip_url": cached_info.get("zip_url"),
                    "sha256_url": cached_info.get("sha256_url"),
                    "update_available": True,
                    "error": status.get("error"),
                }
            with self._update_lock:
                self._latest_update_status = dict(status)
                progress = dict(self._update_progress)
            return self._sanitize_for_json({
                **status,
                "progress": progress,
                "apply_supported": True,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "current_version": None,
                "latest_version": None,
                "latest_tag": None,
                "update_available": False,
                "release_url": None,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": "check_failed",
                "error": f"Could not check GitHub Releases: {exc}",
                "progress": progress,
                "apply_supported": True,
            })

    @staticmethod
    def _runtime_diagnostics_summary(paths: Any) -> dict:
        warnings: list[str] = []
        errors: list[str] = []
        # Warn when dev mode is running against the real release data directory.
        if not getattr(sys, "frozen", False):
            use_release = os.environ.get("CVMANALYTICS_USE_RELEASE_DATA", "").strip().lower() in {
                "1", "true", "yes",
            }
            if use_release:
                warnings.append(
                    "Dev mode is using the release data directory "
                    f"({paths.data_dir}). Destructive actions affect real user data."
                )
        try:
            from desktop.__version__ import __version__ as app_version  # noqa: PLC0415
        except Exception:
            app_version = "unknown"
        dotnet_status = "unavailable"
        webview2_version = None
        try:
            from desktop import app as desktop_app  # noqa: PLC0415

            release = desktop_app._detect_net_framework_release()
            min_release = desktop_app._NET_FRAMEWORK_48_RELEASE_KEY
            if release is None:
                dotnet_status = "not_detected"
                warnings.append(".NET Framework 4.8 registry key was not detected.")
            elif int(release) < int(min_release):
                dotnet_status = f"pre_4_8:{release}"
                warnings.append(f".NET Framework release {release} is below {min_release}.")
            else:
                dotnet_status = f"ok:{release}"
            webview2_version = desktop_app._detect_webview2_runtime()
            if not webview2_version:
                warnings.append("Microsoft Edge WebView2 Runtime was not detected.")
        except Exception as exc:
            warnings.append(f"Runtime prerequisite probe failed: {exc}")

        pythonnet_status = "unknown"
        try:
            import clr  # noqa: F401, PLC0415

            pythonnet_status = "ok"
        except Exception as exc:
            pythonnet_status = f"error:{type(exc).__name__}"
            errors.append(f"pythonnet import failed: {exc}")

        sqlite_status = "unknown"
        try:
            import sqlite3  # noqa: PLC0415

            db_path = Path(paths.db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(db_path)) as conn:
                row = conn.execute("SELECT sqlite_version()").fetchone()
            sqlite_status = f"ok:{row[0] if row else 'unknown'}"
        except Exception as exc:
            sqlite_status = f"error:{type(exc).__name__}"
            errors.append(f"SQLite probe failed: {exc}")

        return {
            "ok": len(errors) == 0,
            "version": app_version,
            "dotnet_status": dotnet_status,
            "webview2_version": webview2_version,
            "pythonnet_status": pythonnet_status,
            "sqlite_status": sqlite_status,
            "db_path": str(paths.db_path),
            "data_root": str(paths.data_dir),
            "errors": errors,
            "warnings": warnings,
        }

    def _collect_recent_diagnostics(self, paths: Any, database: dict | None) -> list[dict]:
        entries: list[dict] = []

        latest_error = (database or {}).get("latest_error") if isinstance(database, dict) else None
        if latest_error:
            entries.append({
                "source": "company_refresh_status",
                "severity": "error",
                "timestamp": (database or {}).get("latest_attempt_at"),
                "message": str(latest_error),
            })

        recovery_log = Path(paths.data_dir) / "recovery.log"
        for line in self._tail_text_lines(recovery_log, limit=4):
            entries.append({
                "source": "recovery.log",
                "severity": "warning" if "failed" in line.lower() else "info",
                "timestamp": self._parse_bracket_timestamp(line),
                "message": self._trim_log_line(line),
            })

        update_log = Path(os.environ.get("LOCALAPPDATA") or Path(paths.data_dir)) / "CVMAnalytics" / "update_error.log"
        for line in self._tail_text_lines(update_log, limit=4):
            entries.append({
                "source": "update_error.log",
                "severity": "error" if "error" in line.lower() else "info",
                "timestamp": self._parse_bracket_timestamp(line),
                "message": self._trim_log_line(line),
            })

        refresh_log = Path(paths.logs_dir) / "refresh_runs.jsonl"
        for line in self._tail_text_lines(refresh_log, limit=6):
            entry = self._refresh_log_entry(line)
            if entry:
                entries.append(entry)

        entries.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return entries[:12]

    @staticmethod
    def _tail_text_lines(path: Path, *, limit: int) -> list[str]:
        try:
            if not path.exists() or not path.is_file():
                return []
            size = path.stat().st_size
            with path.open("rb") as fh:
                fh.seek(max(0, size - 65536))
                data = fh.read().decode("utf-8", errors="replace")
            return [line for line in data.splitlines() if line.strip()][-limit:]
        except Exception:
            return []

    @staticmethod
    def _parse_bracket_timestamp(line: str) -> str | None:
        if not line.startswith("[") or "]" not in line:
            return None
        return line[1:line.find("]")]

    @staticmethod
    def _trim_log_line(line: str, *, max_len: int = 320) -> str:
        text = " ".join(str(line).split())
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "..."

    def _refresh_log_entry(self, line: str) -> dict | None:
        try:
            payload = json.loads(line)
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            return None
        status = str(payload.get("status") or payload.get("state") or "refresh")
        message = (
            payload.get("message")
            or payload.get("error")
            or payload.get("latest_error")
            or f"Refresh result: {status}"
        )
        timestamp = (
            payload.get("finished_at")
            or payload.get("completed_at")
            or payload.get("started_at")
            or payload.get("accepted_at")
        )
        lower = f"{status} {message}".lower()
        severity = "error" if "error" in lower or "failed" in lower else "info"
        return {
            "source": "refresh_runs.jsonl",
            "severity": severity,
            "timestamp": timestamp,
            "message": self._trim_log_line(str(message)),
        }

    def set_company_ignored(self, params=None) -> dict:
        """Toggle the per-company `ignored` flag in company_refresh_status."""
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("set_company_ignored"))
        import sqlite3  # noqa: PLC0415
        from datetime import datetime as _dt  # noqa: PLC0415

        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm") or 0)
        except Exception:
            return self._sanitize_for_json({
                "ok": False,
                "error": "cd_cvm invalido",
            })
        if cd_cvm <= 0:
            return self._sanitize_for_json({
                "ok": False,
                "error": "cd_cvm obrigatorio",
            })
        ignored_flag = 1 if self._truthy(p.get("ignored", True)) else 0
        reason_raw = p.get("reason")
        reason = str(reason_raw).strip() if reason_raw else None
        now_iso = _dt.now().isoformat(timespec="seconds")

        try:
            from src.refresh_jobs import (  # noqa: PLC0415
                ensure_refresh_runtime_tables_for_connection,
            )
            from sqlalchemy import text as _text  # noqa: PLC0415

            svc = self._svc()
            with svc.engine.begin() as conn:
                ensure_refresh_runtime_tables_for_connection(conn)
                # INSERT-or-UPDATE so flipping ignored on a company that has
                # never been touched by the refresh pipeline still works.
                conn.execute(
                    _text(
                        """
                        INSERT INTO company_refresh_status (
                            cd_cvm, company_name, source_scope,
                            last_attempt_at, last_status, last_start_year, last_end_year,
                            updated_at, ignored, ignored_at, ignored_reason
                        ) VALUES (
                            :cd_cvm, :company_name, 'local',
                            NULL, NULL, NULL, NULL,
                            :updated_at, :ignored, :ignored_at, :ignored_reason
                        )
                        ON CONFLICT(cd_cvm) DO UPDATE SET
                            ignored = excluded.ignored,
                            ignored_at = excluded.ignored_at,
                            ignored_reason = excluded.ignored_reason,
                            updated_at = excluded.updated_at
                        """
                    ),
                    {
                        "cd_cvm": int(cd_cvm),
                        "company_name": str(p.get("company_name") or cd_cvm),
                        "updated_at": now_iso,
                        "ignored": int(ignored_flag),
                        "ignored_at": now_iso if ignored_flag else None,
                        "ignored_reason": reason if ignored_flag else None,
                    },
                )
            svc.invalidate_read_caches()
            return self._sanitize_for_json({
                "ok": True,
                "cd_cvm": int(cd_cvm),
                "ignored": bool(ignored_flag),
                "ignored_at": now_iso if ignored_flag else None,
                "ignored_reason": reason if ignored_flag else None,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "ok": False,
                "error": str(exc),
            })

    def get_data_coverage(self, params=None) -> dict:
        """Data Coverage / Missing Data report for the active CVM universe.

        Joins three sources:
          1. Active company universe (cached CVM catalog).
          2. `financial_reports` — latest DFP (PERIOD_LABEL == REPORT_YEAR)
             and latest ITR (interim) per cd_cvm.
          3. `company_refresh_status` — last update status + error.
          4. TICKER_MAP — ticker resolution.

        Returns rows with a derived `status` and per-filter boolean flags so
        the frontend can render summary cards, filter chips, and the table
        from a single payload.
        """
        import sqlite3  # noqa: PLC0415
        from datetime import datetime as _dt  # noqa: PLC0415

        try:
            from src.ticker_map import TICKER_MAP  # noqa: PLC0415
            from desktop.services import IntelligentSelectorService  # noqa: PLC0415

            svc = self._svc()
            selector = IntelligentSelectorService(settings=svc.settings)
            universe = selector._load_active_universe()
            db_path = svc.settings.paths.db_path
            db_exists = db_path.exists()
            now_year = _dt.now().year
            stale_cutoff_year = now_year - 2

            latest_dfp: dict[int, int] = {}
            latest_itr: dict[int, str] = {}
            company_rows: dict[int, dict[str, Any]] = {}
            refresh_rows: dict[int, dict[str, Any]] = {}

            if db_exists:
                with sqlite3.connect(str(db_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                    present = {row[0] for row in cur.fetchall()}

                    if "financial_reports" in present:
                        try:
                            cur.execute(
                                'SELECT "CD_CVM" AS cd_cvm, MAX("REPORT_YEAR") AS y '
                                'FROM "financial_reports" '
                                'WHERE "CD_CVM" IS NOT NULL '
                                '  AND "PERIOD_LABEL" = CAST("REPORT_YEAR" AS TEXT) '
                                'GROUP BY "CD_CVM"'
                            )
                            for row in cur.fetchall():
                                if row["cd_cvm"] is not None and row["y"] is not None:
                                    latest_dfp[int(row["cd_cvm"])] = int(row["y"])
                        except Exception:
                            pass
                        try:
                            cur.execute(
                                'SELECT "CD_CVM" AS cd_cvm, MAX("PERIOD_LABEL") AS p '
                                'FROM "financial_reports" '
                                'WHERE "CD_CVM" IS NOT NULL '
                                '  AND "PERIOD_LABEL" IS NOT NULL '
                                '  AND "PERIOD_LABEL" <> CAST("REPORT_YEAR" AS TEXT) '
                                'GROUP BY "CD_CVM"'
                            )
                            for row in cur.fetchall():
                                if row["cd_cvm"] is not None and row["p"]:
                                    latest_itr[int(row["cd_cvm"])] = str(row["p"])
                        except Exception:
                            pass

                    if "companies" in present:
                        try:
                            cur.execute(
                                "SELECT cd_cvm, company_name, updated_at "
                                'FROM "companies" WHERE cd_cvm IS NOT NULL'
                            )
                            for row in cur.fetchall():
                                company_rows[int(row["cd_cvm"])] = dict(row)
                        except Exception:
                            pass

                    if "company_refresh_status" in present:
                        crs_cols: set[str] = set()
                        try:
                            cur.execute('PRAGMA table_info("company_refresh_status")')
                            crs_cols = {str(r[1]).lower() for r in cur.fetchall()}
                        except Exception:
                            crs_cols = set()
                        has_ignored = "ignored" in crs_cols
                        ignored_select = ", ignored" if has_ignored else ""
                        ignored_reason_select = (
                            ", ignored_reason" if "ignored_reason" in crs_cols else ""
                        )
                        try:
                            cur.execute(
                                "SELECT cd_cvm, last_status, last_attempt_at, "
                                "last_success_at, last_error"
                                + ignored_select
                                + ignored_reason_select
                                + ' FROM "company_refresh_status" '
                                + "WHERE cd_cvm IS NOT NULL"
                            )
                            for row in cur.fetchall():
                                refresh_rows[int(row["cd_cvm"])] = dict(row)
                        except Exception:
                            pass

            rows: list[dict[str, Any]] = []
            summary = {
                "total": 0,
                "complete": 0,
                "partial": 0,
                "no_financial": 0,
                "failed": 0,
                "stale": 0,
                "unmapped": 0,
                "ignored": 0,
            }
            filter_counts: dict[str, int] = {
                "all": 0,
                "no_dfp": 0,
                "no_itr": 0,
                "no_financial": 0,
                "stale": 0,
                "failed": 0,
                "ticker_unmapped": 0,
                "cvm_unmapped": 0,
                "no_registry": 0,
                "ignored": 0,
            }

            for item in universe:
                try:
                    cd = int(item["cd_cvm"])
                except Exception:
                    continue
                company_name = str(item.get("company_name") or f"CVM {cd}")
                ticker = TICKER_MAP.get(cd)
                ticker_mapped = bool(ticker)
                cvm_valid = cd > 0
                has_registry = cd in company_rows
                if has_registry:
                    reg = company_rows[cd]
                    if reg.get("company_name"):
                        company_name = str(reg["company_name"])
                dfp_year = latest_dfp.get(cd)
                itr_period = latest_itr.get(cd)
                has_dfp = dfp_year is not None
                has_itr = itr_period is not None
                refresh = refresh_rows.get(cd, {})
                last_status = str(refresh.get("last_status") or "").strip().lower()
                last_error = refresh.get("last_error") or None
                last_attempt_at = refresh.get("last_attempt_at") or None
                last_success_at = refresh.get("last_success_at") or None
                ignored = bool(int(refresh.get("ignored") or 0))
                ignored_reason = refresh.get("ignored_reason") or None
                update_failed = last_status in {"error", "failed", "dispatch_failed"}
                is_stale = has_dfp and int(dfp_year) < stale_cutoff_year

                if ignored:
                    status = "ignored"
                elif update_failed:
                    status = "failed"
                elif not has_dfp and not has_itr:
                    status = "no_financial"
                elif not ticker_mapped or not has_registry:
                    status = "unmapped"
                elif not has_dfp or not has_itr or is_stale:
                    status = "partial"
                else:
                    status = "complete"

                summary["total"] += 1
                if status == "complete":
                    summary["complete"] += 1
                elif status == "partial":
                    summary["partial"] += 1
                elif status == "no_financial":
                    summary["no_financial"] += 1
                elif status == "failed":
                    summary["failed"] += 1
                elif status == "unmapped":
                    summary["unmapped"] += 1
                elif status == "ignored":
                    summary["ignored"] += 1
                if is_stale and not ignored:
                    summary["stale"] += 1

                # `all` is "everything with an open issue" — exclude ignored rows
                # so the operator's hidden list stays out of the default view.
                if not ignored and status != "complete":
                    filter_counts["all"] += 1
                if not ignored and not has_dfp:
                    filter_counts["no_dfp"] += 1
                if not ignored and not has_itr:
                    filter_counts["no_itr"] += 1
                if not ignored and not has_dfp and not has_itr:
                    filter_counts["no_financial"] += 1
                if not ignored and is_stale:
                    filter_counts["stale"] += 1
                if not ignored and update_failed:
                    filter_counts["failed"] += 1
                if not ignored and not ticker_mapped:
                    filter_counts["ticker_unmapped"] += 1
                if not ignored and not cvm_valid:
                    filter_counts["cvm_unmapped"] += 1
                if not ignored and not has_registry:
                    filter_counts["no_registry"] += 1
                if ignored:
                    filter_counts["ignored"] += 1

                rows.append({
                    "cd_cvm": cd,
                    "company_name": company_name,
                    "ticker": ticker,
                    "ticker_mapped": ticker_mapped,
                    "cvm_valid": cvm_valid,
                    "has_registry": has_registry,
                    "has_dfp": has_dfp,
                    "has_itr": has_itr,
                    "latest_dfp_year": dfp_year,
                    "latest_itr_period": itr_period,
                    "last_status": last_status or None,
                    "last_attempt_at": last_attempt_at,
                    "last_success_at": last_success_at,
                    "last_error": last_error,
                    "update_failed": update_failed,
                    "is_stale": is_stale,
                    "ignored": ignored,
                    "ignored_reason": str(ignored_reason) if ignored_reason else None,
                    "status": status,
                })

            rows.sort(
                key=lambda r: (
                    {
                        "failed": 0,
                        "no_financial": 1,
                        "partial": 2,
                        "unmapped": 3,
                        "complete": 4,
                        "ignored": 6,
                    }.get(str(r.get("status")), 5),
                    str(r.get("company_name") or "").upper(),
                )
            )

            return self._sanitize_for_json({
                "generated_at": _dt.now().isoformat(timespec="seconds"),
                "stale_cutoff_year": int(stale_cutoff_year),
                "summary": summary,
                "filter_counts": filter_counts,
                "rows": rows,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "generated_at": None,
                "stale_cutoff_year": None,
                "summary": {
                    "total": 0,
                    "complete": 0,
                    "partial": 0,
                    "no_financial": 0,
                    "failed": 0,
                    "stale": 0,
                    "unmapped": 0,
                },
                "filter_counts": {},
                "rows": [],
                "error": str(exc),
            })

    def get_base_health(self, params=None) -> dict:
        p = params or {}
        try:
            start_year = int(p.get("start_year"))
            end_year = int(p.get("end_year"))
            force_raw = p.get("force_refresh", False)
            force_refresh = (
                force_raw.strip().lower() in {"1", "true", "yes", "sim"}
                if isinstance(force_raw, str)
                else bool(force_raw)
            )
            result = self._svc().get_health_snapshot(
                start_year=start_year,
                end_year=end_year,
                force_refresh=force_refresh,
            )
            return self._sanitize_for_json(dataclasses.asdict(result))
        except Exception as exc:
            return {"error": str(exc)}

    def get_health(self, params=None) -> dict:
        try:
            svc = self._svc()
            # Faz uma consulta leve para checar DB
            svc.list_companies(page=1, page_size=1)
            return self._sanitize_for_json({
                "status": "ok",
                "version": "desktop",
                "database_dialect": "sqlite",
                "required_tables": [],
                "warnings": [],
                "errors": [],
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "status": "degraded",
                "version": "desktop",
                "database_dialect": "sqlite",
                "required_tables": [],
                "warnings": [],
                "errors": [{"severity": "error", "code": "db_error",
                            "message": str(exc), "path": None}],
            })

    def get_database_diagnostics(self, params=None) -> dict:
        """Real local SQLite database diagnostics for the Update Base UI.

        Returns explicit row counts for the tables an operator needs to see
        when verifying that a refresh actually populated the runtime DB.
        Distinct from `get_base_health`, which compares against the CVM
        active universe (not local row counts).
        """
        import sqlite3  # noqa: PLC0415

        try:
            svc = self._svc()
            db_path = svc.settings.paths.db_path
            data_dir = svc.settings.paths.data_dir
            db_path_str = str(db_path)
            data_root_str = str(data_dir)
            db_exists = db_path.exists()
            db_size_bytes = int(db_path.stat().st_size) if db_exists else 0

            counts: dict[str, int | None] = {
                "companies": None,
                "financial_reports": None,
                "refresh_jobs": None,
                "company_refresh_status": None,
                "qa_logs": None,
            }
            latest_success_at: str | None = None
            latest_attempt_at: str | None = None
            latest_error: str | None = None
            latest_report_year: int | None = None
            latest_period_label: str | None = None
            refresh_errors_count: int | None = None

            if db_exists:
                try:
                    with sqlite3.connect(db_path_str) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        present = {row[0] for row in cur.fetchall()}
                        for table in counts.keys():
                            if table not in present:
                                counts[table] = 0
                                continue
                            try:
                                cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                                counts[table] = int(cur.fetchone()[0] or 0)
                            except Exception:
                                counts[table] = None
                        if "financial_reports" in present:
                            try:
                                cur.execute(
                                    'SELECT "REPORT_YEAR", "PERIOD_LABEL" '
                                    'FROM "financial_reports" '
                                    'WHERE "REPORT_YEAR" IS NOT NULL '
                                    'ORDER BY "REPORT_YEAR" DESC, "PERIOD_LABEL" DESC '
                                    "LIMIT 1"
                                )
                                row = cur.fetchone()
                                if row:
                                    latest_report_year = int(row[0]) if row[0] is not None else None
                                    latest_period_label = str(row[1]) if row[1] else None
                            except Exception:
                                pass
                        if "company_refresh_status" in present:
                            try:
                                cur.execute(
                                    "SELECT MAX(last_success_at), MAX(last_attempt_at) "
                                    'FROM "company_refresh_status"'
                                )
                                row = cur.fetchone() or (None, None)
                                latest_success_at = str(row[0]) if row[0] else None
                                latest_attempt_at = str(row[1]) if row[1] else None
                            except Exception:
                                pass
                            try:
                                cur.execute(
                                    "SELECT last_error FROM \"company_refresh_status\" "
                                    "WHERE last_error IS NOT NULL AND last_error <> '' "
                                    "ORDER BY last_attempt_at DESC LIMIT 1"
                                )
                                row = cur.fetchone()
                                if row and row[0]:
                                    latest_error = str(row[0])
                            except Exception:
                                pass
                            try:
                                cur.execute(
                                    "SELECT COUNT(*) FROM \"company_refresh_status\" "
                                    "WHERE last_error IS NOT NULL AND last_error <> ''"
                                )
                                row = cur.fetchone()
                                refresh_errors_count = int(row[0] or 0) if row else 0
                            except Exception:
                                pass
                except Exception as exc:
                    return self._sanitize_for_json({
                        "db_path": db_path_str,
                        "data_root": data_root_str,
                        "db_exists": db_exists,
                        "db_size_bytes": db_size_bytes,
                        "is_empty": True,
                        "row_counts": counts,
                        "latest_success_at": None,
                        "latest_attempt_at": None,
                        "latest_error": None,
                        "latest_report_year": None,
                        "latest_period_label": None,
                        "refresh_errors_count": None,
                        "error": f"sqlite_open_failed: {exc}",
                    })

            is_empty = (
                not db_exists
                or (counts.get("companies") or 0) == 0
                or (counts.get("financial_reports") or 0) == 0
            )

            return self._sanitize_for_json({
                "db_path": db_path_str,
                "data_root": data_root_str,
                "db_exists": db_exists,
                "db_size_bytes": db_size_bytes,
                "is_empty": is_empty,
                "row_counts": counts,
                "latest_success_at": latest_success_at,
                "latest_attempt_at": latest_attempt_at,
                "latest_error": latest_error,
                "latest_report_year": latest_report_year,
                "latest_period_label": latest_period_label,
                "refresh_errors_count": refresh_errors_count,
            })
        except Exception as exc:
            return self._sanitize_for_json({
                "db_path": None,
                "data_root": None,
                "db_exists": False,
                "db_size_bytes": 0,
                "is_empty": True,
                "row_counts": {
                    "companies": None,
                    "financial_reports": None,
                    "refresh_jobs": None,
                    "company_refresh_status": None,
                    "qa_logs": None,
                },
                "latest_success_at": None,
                "latest_attempt_at": None,
                "latest_error": None,
                "latest_report_year": None,
                "latest_period_label": None,
                "refresh_errors_count": None,
                "error": str(exc),
            })

    # ── Energy KPI methods ────────────────────────────────────────────────────

    def _energy_svc(self):
        if not hasattr(self, "_energy_read_service") or self._energy_read_service is None:
            from src.energy_kpi.read import EnergyKPIReadService  # noqa: PLC0415
            from src.settings import get_settings  # noqa: PLC0415
            self._energy_read_service = EnergyKPIReadService(get_settings())
        return self._energy_read_service

    def _energy_refresh_status(self) -> dict:
        return getattr(self, "_energy_refresh_state", {"status": "idle", "error": None})

    def _sin_refresh_status(self) -> dict:
        return getattr(self, "_sin_refresh_state", {"status": "idle", "error": None})

    def _plant_parcel_refresh_status(self) -> dict:
        return getattr(self, "_plant_parcel_refresh_state", {"status": "idle", "error": None})

    def get_kpi_catalog(self, params=None) -> dict:
        params = params or {}
        try:
            entries = self._energy_svc().get_kpi_catalog(
                sector=params.get("sector"),
                v1_status=params.get("v1_status"),
                dashboard_priority=params.get("dashboard_priority"),
                excel_export_priority=params.get("excel_export_priority"),
                macro_category=params.get("macro_category"),
                source_verification_status=params.get("source_verification_status"),
            )
            return self._sanitize_for_json({
                "entries": [e.to_dict() for e in entries],
                "count": len(entries),
            })
        except Exception as exc:
            return {"error": str(exc), "entries": [], "count": 0}

    def get_country_kpi_series(self, params=None) -> dict:
        params = params or {}
        try:
            values = self._energy_svc().get_country_kpi_series(
                kpi_ids=params.get("kpi_ids"),
                iso_codes=params.get("iso_codes"),
                years=params.get("years"),
            )
            return self._sanitize_for_json({
                "values": [v.to_dict() for v in values],
                "count": len(values),
            })
        except Exception as exc:
            return {"error": str(exc), "values": [], "count": 0}

    def get_country_kpi_compare(self, params=None) -> dict:
        params = params or {}
        try:
            kpi_id = params.get("kpi_id", "")
            year = int(params.get("year", 0))
            values = self._energy_svc().get_country_kpi_compare(kpi_id=kpi_id, year=year)
            return self._sanitize_for_json({
                "kpi_id": kpi_id,
                "year": year,
                "values": [v.to_dict() for v in values],
            })
        except Exception as exc:
            return {"error": str(exc), "values": []}

    def get_energy_kpi_health(self, params=None) -> dict:
        try:
            health = self._energy_svc().get_energy_kpi_health()
            result = self._sanitize_for_json(health.to_dict())
            result["refresh_running"] = self._energy_refresh_status().get("status") == "running"
            result["refresh_error"] = self._energy_refresh_status().get("error")
            return result
        except Exception as exc:
            return {"error": str(exc), "refresh_running": False, "refresh_error": None}

    def refresh_energy_kpis(self, params=None) -> dict:
        params = params or {}
        state = self._energy_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}

        self._energy_refresh_state = {"status": "running", "error": None}

        def _run():
            try:
                from src.energy_kpi.refresh import EnergyKPIRefreshJob  # noqa: PLC0415
                from src.settings import get_settings  # noqa: PLC0415
                job = EnergyKPIRefreshJob(get_settings())
                result = job.run(triggered_by=params.get("triggered_by", "user"))
                self._energy_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "rows_ingested": result.get("rows_ingested", 0),
                }
            except Exception as exc:
                self._energy_refresh_state = {"status": "error", "error": str(exc)}
            finally:
                # Invalidate read service so next read sees fresh data
                self._energy_read_service = None

        threading.Thread(target=_run, name="energy-kpi-refresh", daemon=True).start()
        return {"status": "started", "error": None}

    def export_country_kpis_excel(self, params=None) -> dict:
        params = params or {}
        try:
            from src.energy_kpi.excel import export_country_kpis  # noqa: PLC0415
            from src.settings import get_settings  # noqa: PLC0415
            settings = get_settings()
            output_path = export_country_kpis(
                settings=settings,
                iso_codes=params.get("iso_codes"),
                kpi_ids=params.get("kpi_ids"),
            )
            return {"path": str(output_path), "error": None}
        except Exception as exc:
            return {"error": str(exc), "path": None}

    def get_sin_kpi_dashboard(self, params=None) -> dict:
        try:
            dashboard = self._energy_svc().get_sin_kpi_dashboard()
            result = self._sanitize_for_json(dashboard.to_dict())
            result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
            result["refresh_error"] = self._sin_refresh_status().get("error")
            return result
        except Exception as exc:
            return {
                "error": str(exc),
                "observations": [],
                "source_statuses": [],
                "refresh_running": False,
                "refresh_error": None,
            }

    def get_sin_kpi_series(self, params=None) -> dict:
        params = params or {}
        try:
            values = self._energy_svc().get_sin_kpi_series(
                kpi_ids=params.get("kpi_ids"),
                subsystem_codes=params.get("subsystem_codes"),
                start_datetime=params.get("start_datetime"),
                end_datetime=params.get("end_datetime"),
                limit=params.get("limit"),
            )
            return self._sanitize_for_json({
                "values": [v.to_dict() for v in values],
                "count": len(values),
            })
        except Exception as exc:
            return {"error": str(exc), "values": [], "count": 0}

    def get_sin_kpi_health(self, params=None) -> dict:
        try:
            health = self._energy_svc().get_sin_kpi_health()
            result = self._sanitize_for_json(health.to_dict())
            result["refresh_running"] = self._sin_refresh_status().get("status") == "running"
            result["refresh_error"] = self._sin_refresh_status().get("error")
            return result
        except Exception as exc:
            return {"error": str(exc), "refresh_running": False, "refresh_error": None}

    def refresh_sin_kpis(self, params=None) -> dict:
        params = params or {}
        state = self._sin_refresh_status()
        if state.get("status") == "running":
            return {"status": "already_running", "error": None}

        self._sin_refresh_state = {"status": "running", "error": None}

        def _run():
            try:
                from src.energy_kpi.sin_refresh import SINKPIRefreshJob  # noqa: PLC0415
                from src.settings import get_settings  # noqa: PLC0415
                years = params.get("years")
                if years is not None:
                    years = [int(y) for y in years]
                include_ccee = bool(params.get("include_ccee", True))
                job = SINKPIRefreshJob(get_settings())
                result = job.run(
                    triggered_by=params.get("triggered_by", "user"),
                    years=years,
                    include_ccee=include_ccee,
                )
                self._sin_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "rows_inserted": result.get("rows_inserted", 0),
                }
            except Exception as exc:
                self._sin_refresh_state = {"status": "error", "error": str(exc)}
            finally:
                self._energy_read_service = None

        threading.Thread(target=_run, name="sin-kpi-refresh", daemon=True).start()
        return {"status": "started", "error": None}

    def get_plant_parcel_source_statuses(self, params=None) -> dict:
        try:
            result = self._energy_svc().get_plant_parcel_source_statuses()
            result = self._sanitize_for_json(result)
            refresh_state = self._plant_parcel_refresh_status()
            result["refresh_running"] = refresh_state.get("status") == "running"
            result["refresh_status"] = refresh_state.get("status")
            result["refresh_error"] = refresh_state.get("error")
            result["refresh_warning"] = refresh_state.get("warning")
            result["refresh_source_id"] = refresh_state.get("source_id")
            return result
        except Exception as exc:
            return {
                "error": str(exc),
                "source_statuses": [],
                "count": 0,
                "refresh_running": False,
                "refresh_error": None,
                "refresh_source_id": None,
            }

    def get_plant_parcel_catalog(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._energy_svc().get_plant_parcel_catalog(
                    search=params.get("search"),
                    entity_type=params.get("entity_type"),
                    generation_source=params.get("generation_source"),
                    submarket=params.get("submarket"),
                    uf=params.get("uf"),
                    limit=int(params.get("limit", 100) or 100),
                    offset=int(params.get("offset", 0) or 0),
                )
            )
        except Exception as exc:
            return {"error": str(exc), "records": [], "count": 0, "total": 0}

    def get_plant_parcel_detail(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._energy_svc().get_plant_parcel_detail(
                    entity_id=str(params.get("entity_id") or ""),
                    entity_type=params.get("entity_type"),
                )
            )
        except Exception as exc:
            return {"error": str(exc), "metrics": [], "monthly_series": [], "hourly_preview": []}

    def get_plant_parcel_chart_data(self, params=None) -> dict:
        params = params or {}
        try:
            return self._sanitize_for_json(
                self._energy_svc().get_plant_parcel_chart_data(
                    entity_id=str(params.get("entity_id") or ""),
                    entity_type=params.get("entity_type"),
                    frequency=str(params.get("frequency") or "monthly"),
                    year_month=params.get("year_month"),
                )
            )
        except Exception as exc:
            return {"error": str(exc), "series": [], "periods": []}

    def select_plant_parcel_import_file(self, params=None) -> dict:
        params = params or {}
        source_id = str(params.get("source_id") or "")
        try:
            import webview  # noqa: PLC0415

            file_types = _plant_parcel_import_file_types(source_id)
            if not webview.windows:
                return {"ok": False, "canceled": False, "error": "Desktop window is not ready."}
            try:
                selected = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=True,
                    file_types=file_types,
                )
            except TypeError:
                selected = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=True,
                )
            if not selected:
                return {"ok": False, "canceled": True, "error": None}
            selected_paths = [
                Path(str(item))
                for item in (selected if isinstance(selected, (list, tuple)) else [selected])
            ]
            selected_path = selected_paths[0]
            return self._sanitize_for_json({
                "ok": True,
                "canceled": False,
                "file_path": str(selected_path),
                "file_name": selected_path.name,
                "file_paths": [str(path) for path in selected_paths],
                "file_names": [path.name for path in selected_paths],
            })
        except Exception as exc:
            return self._sanitize_for_json({"ok": False, "canceled": False, "error": str(exc)})

    def import_plant_parcel_source_file(self, params=None) -> dict:
        if not self._is_write_allowed():
            return self._sanitize_for_json(self._write_blocked_response("import_plant_parcel_source_file"))
        params = params or {}
        source_id = str(params.get("source_id") or "")
        if not source_id:
            return {"status": "failed", "error": "source_id is required"}

        temp_path: Path | None = None
        file_path_value = params.get("file_path")
        try:
            from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob  # noqa: PLC0415
            from src.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            original_file_name = str(params.get("original_file_name") or "")
            if not file_path_value and params.get("file_content_base64"):
                safe_name = Path(original_file_name or "manual-import.csv").name
                temp_dir = settings.paths.energy_kpi_raw_dir / "manual_uploads_tmp"
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_path = temp_dir / f"{uuid.uuid4()}-{safe_name}"
                temp_path.write_bytes(base64.b64decode(str(params.get("file_content_base64"))))
                file_path_value = str(temp_path)
            if not file_path_value:
                return {
                    "status": "failed",
                    "error": "Either file_path or file_content_base64 must be provided.",
                }

            self._plant_parcel_refresh_state = {
                "status": "running",
                "error": None,
                "warning": None,
                "source_id": source_id,
            }
            job = PlantParcelRefreshJob(settings)
            result = job.run_manual_file_import(
                source_id=source_id,
                file_path=Path(str(file_path_value)),
                triggered_by=str(params.get("triggered_by") or "user"),
                expected_period=params.get("expected_period"),
                original_file_name=original_file_name or None,
            )
            self._plant_parcel_refresh_state = {
                "status": result.get("status", "success"),
                "error": result.get("error"),
                "warning": result.get("warning"),
                "source_id": source_id,
                "rows_inserted": result.get("rows_inserted", 0),
                "refresh_id": result.get("refresh_id"),
            }
            self._energy_read_service = None
            return self._sanitize_for_json(result)
        except Exception as exc:
            self._plant_parcel_refresh_state = {
                "status": "error",
                "error": str(exc),
                "source_id": source_id,
            }
            return self._sanitize_for_json({"status": "failed", "error": str(exc), "source_id": source_id})
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    logger.debug("failed to remove temporary manual upload", exc_info=True)


    def refresh_plant_parcel_source(self, params=None) -> dict:
        params = params or {}
        source_id = str(params.get("source_id") or "")
        if not source_id:
            return {"status": "error", "error": "source_id is required"}
        state = self._plant_parcel_refresh_status()
        if state.get("status") == "running":
            return {
                "status": "already_running",
                "error": None,
                "source_id": state.get("source_id"),
            }

        self._plant_parcel_refresh_state = {
            "status": "running",
            "error": None,
            "source_id": source_id,
        }

        def _run():
            try:
                from src.energy_kpi.plant_parcel_refresh import PlantParcelRefreshJob  # noqa: PLC0415
                from src.settings import get_settings  # noqa: PLC0415
                job = PlantParcelRefreshJob(get_settings())
                result = job.run(
                    source_id=source_id,
                    triggered_by=params.get("triggered_by", "user"),
                    year=int(params["year"]) if params.get("year") else None,
                    year_month=params.get("year_month"),
                    use_daily_aneel=bool(params.get("use_daily_aneel", False)),
                )
                self._plant_parcel_refresh_state = {
                    "status": result.get("status", "success"),
                    "error": result.get("error"),
                    "warning": result.get("warning"),
                    "source_id": source_id,
                    "rows_inserted": result.get("rows_inserted", 0),
                    "refresh_id": result.get("refresh_id"),
                }
            except Exception as exc:
                self._plant_parcel_refresh_state = {
                    "status": "error",
                    "error": str(exc),
                    "source_id": source_id,
                }
            finally:
                self._energy_read_service = None

        threading.Thread(target=_run, name="plant-parcel-refresh", daemon=True).start()
        return {"status": "started", "error": None, "source_id": source_id}


def _plant_parcel_import_file_types(source_id: str) -> tuple[str, ...]:
    if source_id == "ccee_plant_parcel_monthly":
        return ("CSV files (*.csv)", "All files (*.*)")
    if source_id == "ccee_plant_generation_hourly":
        return ("GZIP files (*.gz;*.gzip)", "CSV files (*.csv)", "All files (*.*)")
    return ("All files (*.*)",)


def _serialize(obj: Any) -> Any:
    """Converte dataclasses e tuples para tipos serializáveis por pywebview."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, tuple):
        return list(obj)
    return obj
