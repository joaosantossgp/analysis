from __future__ import annotations

import base64
import dataclasses
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


class CompanyBridgeMixin:
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

            # 2. Fetch stock price history from Yahoo Finance or local cache
            from src.companies.market_cap import MarketCapService  # noqa: PLC0415
            mkt_cap_svc = MarketCapService(settings=svc.settings, read_service=svc)

            # Resolve ticker
            ticker = None
            info = svc.query_layer.get_company_info(cd_cvm)
            if info:
                ticker = info.get("ticker_b3")
            if not ticker:
                from src.companies.ticker_map import TICKER_MAP  # noqa: PLC0415
                ticker = TICKER_MAP.get(cd_cvm)

            prices_by_year = {}
            if ticker:
                try:
                    # Try local cache first
                    with svc.engine.connect() as conn:
                        rows = conn.execute(
                            text(
                                """
                                SELECT date, adjusted_close
                                FROM market_history
                                WHERE cd_cvm = :cd_cvm
                                ORDER BY date ASC
                                """
                            ),
                            {"cd_cvm": cd_cvm},
                        ).fetchall()
                    if rows:
                        for r_date, r_close in rows:
                            if r_close is not None:
                                yr = datetime.strptime(r_date, "%Y-%m-%d").year
                                prices_by_year[yr] = float(r_close)
                    else:
                        prices_by_year = mkt_cap_svc.fetch_yahoo_price_history(ticker)
                except Exception:
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

    def get_company_market_history_status(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if not cd_cvm:
                return {"error": "cd_cvm is required"}
            ticker = p.get("ticker")
            from src.companies.market_history import MarketHistoryService  # noqa: PLC0415
            svc = self._svc()
            mkt_svc = MarketHistoryService(settings=svc.settings, read_service=svc)
            return self._sanitize_for_json(mkt_svc.get_market_history_status(cd_cvm, ticker=ticker))
        except Exception as exc:
            return {"error": str(exc)}

    def get_company_market_history(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if not cd_cvm:
                return {"error": "cd_cvm is required"}
            ticker = p.get("ticker")
            start_date = p.get("start_date")
            end_date = p.get("end_date")
            period = p.get("period")
            interval = p.get("interval", "1d")
            from src.companies.market_history import MarketHistoryService  # noqa: PLC0415
            svc = self._svc()
            mkt_svc = MarketHistoryService(settings=svc.settings, read_service=svc)
            result = mkt_svc.get_market_history(
                cd_cvm,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                period=period,
                interval=interval,
            )
            return self._sanitize_for_json(result)
        except Exception as exc:
            return {"error": str(exc)}

    def refresh_company_market_history(self, params=None) -> dict:
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if not cd_cvm:
                return {"error": "cd_cvm is required"}
            ticker = p.get("ticker")
            from src.companies.market_history import MarketHistoryService  # noqa: PLC0415
            svc = self._svc()
            mkt_svc = MarketHistoryService(settings=svc.settings, read_service=svc)
            result = mkt_svc.refresh_market_history(cd_cvm, ticker=ticker)
            svc.invalidate_read_caches()
            return self._sanitize_for_json(result)
        except Exception as exc:
            return {"error": str(exc)}

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
                if statement_type not in ("DRE", "BPA", "BPP", "DFC", "DMPL"):
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

    def export_company_market_history_excel(self, params=None) -> dict:
        """Write the currently selected market-history dataset to output/."""
        p = params or {}
        try:
            cd_cvm = int(p.get("cd_cvm", 0))
            if cd_cvm <= 0:
                return self._sanitize_for_json({"ok": False, "error": "cd_cvm is required"})

            selected_series_raw = p.get("selected_series") or []
            if not isinstance(selected_series_raw, (list, tuple)):
                selected_series_raw = []

            from src.companies.market_history import MarketHistoryService  # noqa: PLC0415
            from src.companies.market_history_exporter import build_market_history_export  # noqa: PLC0415

            svc = self._svc()
            market_service = MarketHistoryService(settings=svc.settings, read_service=svc)
            filename, payload, export_info = build_market_history_export(
                service=market_service,
                read_service=svc,
                cd_cvm=cd_cvm,
                ticker=p.get("ticker"),
                period=str(p.get("period") or "1Y"),
                custom_start=p.get("custom_start"),
                custom_end=p.get("custom_end"),
                interval=str(p.get("interval") or "1d"),
                view=str(p.get("view") or "price"),
                selected_series=[str(item) for item in selected_series_raw],
                value_mode=str(p.get("value_mode") or "") or None,
                chart_type=str(p.get("chart_type") or "") or None,
            )
            output_dir = Path(svc.settings.paths.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            target = self._unique_output_path(output_dir, filename)
            target.write_bytes(payload)
            return self._sanitize_for_json({
                "ok": True,
                "file_path": str(target),
                "file_name": target.name,
                "output_dir": str(output_dir),
                "size_bytes": int(target.stat().st_size),
                "revealed": False,
                "observation_count": export_info.get("observation_count"),
                "first_observation_date": export_info.get("first_observation_date"),
                "last_observation_date": export_info.get("last_observation_date"),
            })
        except Exception as exc:
            logger.exception("Market history Excel export failed")
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

    def get_sectors(self, params=None) -> dict:
        try:
            p = params or {}
            raw_include_snapshots = p.get("include_snapshots", True)
            include_snapshots = not (
                raw_include_snapshots is False
                or str(raw_include_snapshots).strip().lower() in {"0", "false", "no"}
            )
            result = self._svc().list_sectors(
                group_by=str(p.get("group_by") or "sector"),
                include_snapshots=include_snapshots,
            )
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
