# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("desktop.bridge")


class CoverageBridgeMixin:
    def _coverage_svc(self):
        # Dynamically import and build the service to avoid startup circular imports
        from src.companies.coverage import CoverageUniverseService  # noqa: PLC0415
        return CoverageUniverseService(self._svc().engine)

    def get_coverage_universes(self, params=None) -> list[dict[str, Any]] | dict[str, Any]:
        try:
            return self._sanitize_for_json(self._coverage_svc().list_universes())
        except Exception as exc:
            logger.exception("Error in get_coverage_universes")
            return {"error": str(exc)}

    def get_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("id") or p.get("universe_id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            u = self._coverage_svc().get_universe(str(u_id))
            if not u:
                return {"error": "Universe not found"}
            return self._sanitize_for_json(u)
        except Exception as exc:
            logger.exception("Error in get_coverage_universe")
            return {"error": str(exc)}

    def create_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        name = p.get("name")
        purpose = p.get("purpose")
        analysis_type = p.get("analysis_type", "Equity")
        benchmark = p.get("benchmark")
        if not name:
            return {"error": "Missing name parameter"}
        try:
            u_id = self._coverage_svc().create_universe(
                name=str(name),
                purpose=purpose,
                analysis_type=analysis_type,
                benchmark=benchmark,
            )
            return {"universe_id": u_id}
        except Exception as exc:
            logger.exception("Error in create_coverage_universe")
            return {"error": str(exc)}

    def update_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("id") or p.get("universe_id")
        name = p.get("name")
        purpose = p.get("purpose")
        benchmark = p.get("benchmark")
        status = p.get("status", "draft")
        assumptions = p.get("assumptions")
        if not u_id or not name:
            return {"error": "Missing id or name parameter"}
        try:
            self._coverage_svc().update_universe(
                universe_id=str(u_id),
                name=str(name),
                purpose=purpose,
                benchmark=benchmark,
                status=str(status),
                assumptions=assumptions,
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in update_coverage_universe")
            return {"error": str(exc)}

    def delete_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("id") or p.get("universe_id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            self._coverage_svc().delete_universe(str(u_id))
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in delete_coverage_universe")
            return {"error": str(exc)}

    def duplicate_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("id") or p.get("universe_id")
        new_name = p.get("name") or p.get("new_name")
        copy_companies = bool(p.get("copy_companies", True))
        copy_checklists = bool(p.get("copy_checklists", False))
        if not u_id or not new_name:
            return {"error": "Missing universe_id or name parameter"}
        try:
            new_uid = self._coverage_svc().duplicate_universe(
                universe_id=str(u_id),
                new_name=str(new_name),
                copy_companies=copy_companies,
                copy_checklists=copy_checklists,
            )
            return {"universe_id": new_uid}
        except Exception as exc:
            logger.exception("Error in duplicate_coverage_universe")
            return {"error": str(exc)}

    def bulk_update_companies_in_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        company_ids_raw = p.get("company_ids")
        tier = p.get("tier")
        rationale = p.get("rationale", "")
        if not u_id or company_ids_raw is None or tier is None:
            return {"error": "Missing universe_id, company_ids, or tier parameter"}
        if not rationale:
            return {"error": "Rationale is mandatory for all coverage decisions"}
        try:
            company_ids = [int(x) for x in company_ids_raw]
            self._coverage_svc().bulk_update_companies_in_universe(
                universe_id=str(u_id),
                company_ids=company_ids,
                tier=str(tier),
                rationale=str(rationale),
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in bulk_update_companies_in_coverage_universe")
            return {"error": str(exc)}



    def add_company_to_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        tier = p.get("tier", "watchlist")
        rationale = p.get("rationale", "")
        owner = p.get("owner")
        holding_pct = p.get("holding_pct")
        if not u_id or not cd_cvm:
            return {"error": "Missing universe_id or cd_cvm parameter"}
        if not rationale:
            return {"error": "Rationale is mandatory for all coverage decisions"}
        try:
            holding_val = float(holding_pct) if holding_pct is not None else None
            self._coverage_svc().add_company_to_universe(
                universe_id=str(u_id),
                cd_cvm=int(cd_cvm),
                tier=str(tier),
                rationale=str(rationale),
                owner=owner,
                holding_pct=holding_val,
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in add_company_to_coverage_universe")
            return {"error": str(exc)}

    def remove_company_from_coverage_universe(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        rationale = p.get("rationale", "")
        if not u_id or not cd_cvm:
            return {"error": "Missing universe_id or cd_cvm parameter"}
        if not rationale:
            return {"error": "Rationale is mandatory for all coverage decisions"}
        try:
            self._coverage_svc().remove_company_from_universe(
                universe_id=str(u_id),
                cd_cvm=int(cd_cvm),
                rationale=str(rationale),
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in remove_company_from_coverage_universe")
            return {"error": str(exc)}

    def calculate_coverage_priority_scores(self, params=None) -> dict[str, Any] | list[dict[str, Any]]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        t0 = time.perf_counter()
        try:
            items = self._coverage_svc().calculate_priority_scores(str(u_id))
            payload = {"items": items, "_bridge_ms": round((time.perf_counter() - t0) * 1000, 3)}
            return self._sanitize_for_json(payload)
        except Exception as exc:
            logger.exception("Error in calculate_coverage_priority_scores")
            return {"error": str(exc)}

    def save_manual_score_override(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        override = p.get("override")
        rationale = p.get("rationale", "")
        if not u_id or not cd_cvm:
            return {"error": "Missing universe_id or cd_cvm parameter"}
        if not rationale:
            return {"error": "Rationale is mandatory for all coverage overrides"}
        try:
            override_val = float(override) if override is not None else None
            self._coverage_svc().save_manual_score_override(
                universe_id=str(u_id),
                cd_cvm=int(cd_cvm),
                override=override_val,
                rationale=str(rationale),
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in save_manual_score_override")
            return {"error": str(exc)}

    def get_company_coverage_checklists(self, params=None) -> dict[str, Any] | list[dict[str, Any]]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        if not u_id or not cd_cvm:
            return {"error": "Missing universe_id or cd_cvm parameter"}
        try:
            items = self._coverage_svc().get_coverage_checklists(str(u_id), int(cd_cvm))
            return self._sanitize_for_json({"items": items})
        except Exception as exc:
            logger.exception("Error in get_company_coverage_checklists")
            return {"error": str(exc)}

    def update_company_coverage_checklist_item(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        item_key = p.get("item_key")
        is_completed = bool(p.get("is_completed", False))
        comments = p.get("comments")
        rationale = p.get("rationale", "")
        if not u_id or not cd_cvm or not item_key:
            return {"error": "Missing universe_id, cd_cvm, or item_key parameter"}
        if not rationale:
            return {"error": "Rationale is mandatory for all checklist updates"}
        try:
            self._coverage_svc().update_checklist_item(
                universe_id=str(u_id),
                cd_cvm=int(cd_cvm),
                item_key=str(item_key),
                is_completed=is_completed,
                comments=comments,
                rationale=str(rationale),
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in update_company_coverage_checklist_item")
            return {"error": str(exc)}

    def get_coverage_work_queue(self, params=None) -> dict[str, Any] | list[dict[str, Any]]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            items = self._coverage_svc().get_work_queue(str(u_id))
            return self._sanitize_for_json({"items": items})
        except Exception as exc:
            logger.exception("Error in get_coverage_work_queue")
            return {"error": str(exc)}

    def get_coverage_capacity_data(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            data = self._coverage_svc().get_capacity_data(str(u_id))
            return self._sanitize_for_json(data)
        except Exception as exc:
            logger.exception("Error in get_coverage_capacity_data")
            return {"error": str(exc)}

    def save_coverage_capacity_scenario(self, params=None) -> dict[str, Any]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        available_hours = p.get("available_hours")
        tier_hours = p.get("tier_hours")
        if not u_id or available_hours is None or not tier_hours:
            return {"error": "Missing universe_id, available_hours, or tier_hours parameter"}
        try:
            self._coverage_svc().save_capacity_scenario(
                universe_id=str(u_id),
                available_hours=float(available_hours),
                tier_hours=tier_hours,
            )
            return {"success": True}
        except Exception as exc:
            logger.exception("Error in save_coverage_capacity_scenario")
            return {"error": str(exc)}

    def get_coverage_decision_history(self, params=None) -> dict[str, Any] | list[dict[str, Any]]:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        cd_cvm = p.get("cd_cvm")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            cd_cvm_val = int(cd_cvm) if cd_cvm is not None else None
            items = self._coverage_svc().get_decision_history(str(u_id), cd_cvm_val)
            return self._sanitize_for_json({"items": items})
        except Exception as exc:
            logger.exception("Error in get_coverage_decision_history")
            return {"error": str(exc)}

    def download_coverage_universe_excel(self, params=None) -> dict:
        p = params or {}
        u_id = p.get("universe_id") or p.get("id")
        if not u_id:
            return {"error": "Missing universe_id parameter"}
        try:
            payload = self._coverage_svc().export_coverage_universe_excel(str(u_id))
            universe = self._coverage_svc().get_universe(str(u_id))
            filename = f"Coverage_Universe_{universe['name'].replace(' ', '_')}.xlsx"
            import base64
            return self._sanitize_for_json({
                "filename": filename,
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_base64": base64.b64encode(payload).decode("ascii"),
            })
        except Exception as exc:
            logger.exception("Error in download_coverage_universe_excel")
            return {"error": str(exc)}
