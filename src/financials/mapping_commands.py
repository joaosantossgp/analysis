"""Explicit Excel mapping persistence commands for CVMReadService."""
from __future__ import annotations

from typing import Any, Optional
from src.financials.excel_mapping import SYSTEM_DEFAULT_PRESET_ID, ModelMappingDefinition


class MappingCommandsMixin:
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
