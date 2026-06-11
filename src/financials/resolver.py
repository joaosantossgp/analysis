from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text

from src.financials.excel_mapping import ModelMappingDefinition, ModelMappingEntry, ModelMappingSource
from src.financials.utils import normalize_account_name

logger = logging.getLogger(__name__)


class ModelResolver:
    """
    Resolves canonical financial targets to physical CVM source rows.
    Supports manual overrides, automatic alias/code matching, period-level coalescing,
    and audit trail evidence.
    """

    def __init__(self, engine: Any):
        self.engine = engine

    def get_overrides(self, company_id: int) -> dict[str, dict[str, Any]]:
        """
        Loads user mapping overrides for a company.
        Returns a dict: target_id -> {period_label: override_dict}
        """
        overrides: dict[str, dict[str, Any]] = {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT target_id, period_label, source_code, source_desc, sign, updated_at
                    FROM excel_mapping_overrides
                    WHERE company_id = :company_id
                    """
                ),
                {"company_id": int(company_id)},
            ).mappings().all()

        for row in rows:
            target_id = str(row["target_id"])
            period = str(row["period_label"])
            overrides.setdefault(target_id, {})[period] = {
                "source_code": row["source_code"],
                "source_desc": row["source_desc"],
                "sign": int(row["sign"]),
                "updated_at": row["updated_at"],
            }
        return overrides

    def save_override(
        self,
        company_id: int,
        target_id: str,
        period_label: str,
        source_code: str,
        source_desc: Optional[str] = None,
        sign: int = 1,
    ) -> None:
        """Saves a manual override for a target and period (or 'GLOBAL')."""
        now = datetime.utcnow().isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM excel_mapping_overrides
                    WHERE company_id = :company_id AND target_id = :target_id AND period_label = :period_label
                    """
                ),
                {"company_id": int(company_id), "target_id": target_id, "period_label": period_label},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO excel_mapping_overrides (company_id, target_id, period_label, source_code, source_desc, sign, updated_at)
                    VALUES (:company_id, :target_id, :period_label, :source_code, :source_desc, :sign, :updated_at)
                    """
                ),
                {
                    "company_id": int(company_id),
                    "target_id": target_id,
                    "period_label": period_label,
                    "source_code": source_code,
                    "source_desc": source_desc,
                    "sign": int(sign),
                    "updated_at": now,
                },
            )

    def delete_override(self, company_id: int, target_id: str, period_label: str) -> None:
        """Deletes a manual override."""
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM excel_mapping_overrides
                    WHERE company_id = :company_id AND target_id = :target_id AND period_label = :period_label
                    """
                ),
                {"company_id": int(company_id), "target_id": target_id, "period_label": period_label},
            )

    def get_aliases(self, target_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Loads aliases from the registry."""
        query = "SELECT target_id, normalized_phrase, match_type, scope FROM excel_mapping_aliases"
        params = {}
        if target_id:
            query += " WHERE target_id = :target_id"
            params["target_id"] = target_id

        with self.engine.begin() as conn:
            rows = conn.execute(text(query), params).mappings().all()

        return [dict(row) for row in rows]

    def add_alias(self, target_id: str, phrase: str, match_type: str = "positive", scope: str = "global") -> None:
        """Adds a positive or negative alias to the registry."""
        norm = normalize_account_name(phrase)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO excel_mapping_aliases (target_id, normalized_phrase, match_type, scope)
                    VALUES (:target_id, :norm, :match_type, :scope)
                    """
                ),
                {"target_id": target_id, "norm": norm, "match_type": match_type, "scope": scope},
            )

    def score_candidate(
        self,
        candidate_row: dict[str, Any],
        target_id: str,
        target_label: str,
        aliases: list[dict[str, Any]],
        company_sector: Optional[str] = None,
        mapped_sources: Optional[tuple[ModelMappingSource, ...]] = None,
    ) -> tuple[float, list[str], list[str]]:
        """
        Computes a match score from 0.0 to 100.0 for a candidate row against a target.
        Returns: (score, list of evidence strings, list of warnings/rejections)
        """
        evidence: list[str] = []
        warnings: list[str] = []

        cd_conta = str(candidate_row.get("CD_CONTA") or "").strip()
        line_id = str(candidate_row.get("LINE_ID_BASE") or "").strip()
        ds_conta = str(candidate_row.get("DS_CONTA") or "").strip()
        std_name = str(candidate_row.get("STANDARD_NAME") or "").strip()
        
        target_stmt, target_code = target_id.split(":", 1)
        norm_ds = normalize_account_name(ds_conta)
        norm_std = normalize_account_name(std_name)
        norm_target_lbl = normalize_account_name(target_label)

        # Exclusions/Negative matching checking
        for alias in aliases:
            if alias["target_id"] == target_id and alias["match_type"] == "negative":
                phrase = alias["normalized_phrase"]
                if phrase in norm_ds or phrase in norm_std:
                    warnings.append(f"Rejected: candidate contains excluded phrase '{phrase}'")
                    return 0.0, [], warnings

        # Rule 0: Explicitly mapped source in preset
        if mapped_sources:
            for source in mapped_sources:
                match_line = source.line_id_base
                match_cd = source.cd_conta or source.line_id_base
                if line_id == match_line or cd_conta == match_cd:
                    evidence.append(f"Explicitly mapped source in preset: '{match_line}'")
                    return 98.0, evidence, warnings
                if source.label_snapshot and (source.label_snapshot == ds_conta or source.label_snapshot == std_name):
                    evidence.append(f"Explicitly mapped source description in preset: '{source.label_snapshot}'")
                    return 95.0, evidence, warnings

        # Rule 1: Exact target code match
        if cd_conta == target_code or line_id == target_code:
            evidence.append(f"Exact account code match on '{target_code}'")
            return 95.0, evidence, warnings

        # Rule 2: Alias Registry Match (positive aliases)
        target_aliases = [
            a["normalized_phrase"]
            for a in aliases
            if a["target_id"] == target_id and a["match_type"] == "positive"
            and (a["scope"] == "global" or a["scope"] == company_sector)
        ]
        
        for alias_phrase in target_aliases:
            if alias_phrase == norm_ds or alias_phrase == norm_std:
                evidence.append(f"Exact match on positive alias registry phrase '{alias_phrase}'")
                return 85.0, evidence, warnings
            if alias_phrase in norm_ds or alias_phrase in norm_std:
                evidence.append(f"Substring match on positive alias phrase '{alias_phrase}'")
                return 75.0, evidence, warnings

        # Rule 3: Code prefix match (child of the target code)
        if cd_conta.startswith(target_code + ".") or line_id.startswith(target_code + "."):
            # Lower score because it is a sub-line
            evidence.append(f"Account '{cd_conta}' is a child of target '{target_code}'")
            score = 60.0
            
            # If description is a close match, boost the score
            if norm_target_lbl in norm_ds or norm_target_lbl in norm_std:
                score += 15.0
                evidence.append("Child code matched with target label substring overlap")
            return score, evidence, warnings

        # Rule 4: Normalised Label Word-Overlap Jaccard similarity
        target_words = set(norm_target_lbl.split())
        candidate_words = set(norm_ds.split()) | set(norm_std.split())
        
        if target_words and candidate_words:
            intersection = target_words.intersection(candidate_words)
            union = target_words.union(candidate_words)
            jaccard = len(intersection) / len(union)
            if jaccard >= 0.5:
                evidence.append(f"Label word-overlap Jaccard similarity: {jaccard:.2f}")
                return 50.0 + (jaccard * 20.0), evidence, warnings

        return 0.0, [], []

    def resolve_entry_for_period(
        self,
        company_id: int,
        entry: ModelMappingEntry,
        period: str,
        raw_statement_rows: list[dict[str, Any]],
        overrides: dict[str, dict[str, Any]],
        aliases: list[dict[str, Any]],
        company_sector: Optional[str] = None,
        restrict_to_sources: bool = False,
    ) -> dict[str, Any]:
        """Resolves a single ModelMappingEntry to a source line for a specific period."""
        target_id = entry.target_id
        
        # 1. Evaluate overrides
        target_overrides = overrides.get(target_id, {})
        period_override = target_overrides.get(period) or target_overrides.get("GLOBAL")
        
        if period_override:
            source_code = period_override["source_code"]
            # Locate matching raw row
            matching_row = None
            for row in raw_statement_rows:
                if str(row.get("CD_CONTA") or "").strip() == source_code or str(row.get("LINE_ID_BASE") or "").strip() == source_code:
                    matching_row = row
                    break
            
            if matching_row:
                val = matching_row.get(period)
                resolved_val = float(val) / 1000.0 if val is not None and not pd.isna(val) else None
                return {
                    "target_id": target_id,
                    "period": period,
                    "selected_source_id": f"{entry.statement_type}:{source_code}",
                    "selected_source_label": period_override["source_desc"] or matching_row.get("DS_CONTA"),
                    "status": "manually_confirmed",
                    "score": 100.0,
                    "confidence_margin": 100.0,
                    "resolved_value": resolved_val,
                    "evidence": ["Manual user mapping override applied"],
                    "warnings": [],
                }

        # 2. Compute candidate scores
        candidates = []
        for row in raw_statement_rows:
            # Filter by matching statement type
            row_stmt = str(row.get("STATEMENT_TYPE") or entry.statement_type).upper()
            if row_stmt != entry.statement_type:
                continue

            # If restrict_to_sources is True, verify this row matches one of entry.sources
            if restrict_to_sources and entry.sources:
                matched_source = None
                cd_val = str(row.get("CD_CONTA") or "").strip()
                line_val = str(row.get("LINE_ID_BASE") or "").strip()
                ds_val = str(row.get("DS_CONTA") or "").strip()
                std_val = str(row.get("STANDARD_NAME") or "").strip()
                for s in entry.sources:
                    s_cd = s.cd_conta or s.line_id_base
                    if line_val == s.line_id_base or cd_val == s_cd:
                        matched_source = s
                        break
                    if s.label_snapshot and (s.label_snapshot == ds_val or s.label_snapshot == std_val):
                        matched_source = s
                        break
                if not matched_source:
                    continue

            score, evidence, warnings = self.score_candidate(
                row, target_id, entry.target_label, aliases, company_sector,
                mapped_sources=entry.sources if entry.sources else None
            )
            if score > 0:
                candidates.append({
                    "row": row,
                    "score": score,
                    "evidence": evidence,
                    "warnings": warnings,
                })

        if not candidates:
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": None,
                "selected_source_label": None,
                "status": "unresolved",
                "score": 0.0,
                "confidence_margin": 0.0,
                "resolved_value": None,
                "evidence": ["No matching candidates found"],
                "warnings": [],
            }

        # Sort candidates descending by score
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # 3. Resolve best candidate with value present
        if entry.operation in ("sum", "sum_with_sign"):
            active_cands = []
            total_val = 0.0
            any_val = False
            for cand in candidates:
                val = cand["row"].get(period)
                if val is not None and not pd.isna(val):
                    active_cands.append(cand)
                    source_sign = 1
                    if entry.operation == "sum_with_sign" and entry.sources:
                        cd_val = str(cand["row"].get("CD_CONTA") or "").strip()
                        line_val = str(cand["row"].get("LINE_ID_BASE") or "").strip()
                        for s in entry.sources:
                            s_cd = s.cd_conta or s.line_id_base
                            if line_val == s.line_id_base or cd_val == s_cd:
                                source_sign = s.sign
                                break
                    total_val += (float(val) / 1000.0) * source_sign
                    any_val = True

            if not any_val:
                return {
                    "target_id": target_id,
                    "period": period,
                    "selected_source_id": None,
                    "selected_source_label": None,
                    "status": "unresolved",
                    "score": 0.0,
                    "confidence_margin": 0.0,
                    "resolved_value": None,
                    "evidence": ["No active sum candidates found"],
                    "warnings": [],
                }

            labels = [str(c["row"].get("DS_CONTA")) for c in active_cands]
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": f"sum({len(active_cands)})",
                "selected_source_label": " + ".join(labels),
                "status": "auto_accepted",
                "score": 98.0,
                "confidence_margin": 100.0,
                "resolved_value": total_val,
                "evidence": [f"Summed {len(active_cands)} lines"],
                "warnings": [],
            }

        selected_cand = None
        alternatives = []
        for cand in candidates:
            val = cand["row"].get(period)
            if val is not None and not pd.isna(val):
                if not selected_cand:
                    selected_cand = cand
                else:
                    alternatives.append(cand)

        if not selected_cand:
            # Try to return the highest scoring candidate even if it has no value for this period
            best_cand = candidates[0]
            source_code = best_cand["row"].get("LINE_ID_BASE") or best_cand["row"].get("CD_CONTA")
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": f"{entry.statement_type}:{source_code}",
                "selected_source_label": best_cand["row"].get("DS_CONTA"),
                "status": "unresolved",
                "score": best_cand["score"],
                "confidence_margin": 0.0,
                "resolved_value": None,
                "evidence": best_cand["evidence"] + ["Candidate found but contains no value in this period"],
                "warnings": best_cand["warnings"],
            }

        # 4. Status determination & margin computation
        status = "auto_accepted" if selected_cand["score"] >= 70.0 else "suggested"
        margin = 100.0
        warnings = list(selected_cand["warnings"])

        if alternatives:
            next_best = alternatives[0]
            margin = selected_cand["score"] - next_best["score"]
            if margin < 15.0 and selected_cand["score"] < 90.0:
                status = "ambiguous"
                warnings.append(
                    f"Ambiguous match. Next best candidate is '{next_best['row'].get('DS_CONTA')}' with score {next_best['score']:.1f}"
                )

        source_code = selected_cand["row"].get("LINE_ID_BASE") or selected_cand["row"].get("CD_CONTA")
        val = selected_cand["row"].get(period)
        resolved_val = float(val) / 1000.0 if val is not None else None

        return {
            "target_id": target_id,
            "period": period,
            "selected_source_id": f"{entry.statement_type}:{source_code}",
            "selected_source_label": selected_cand["row"].get("DS_CONTA"),
            "status": status,
            "score": selected_cand["score"],
            "confidence_margin": margin,
            "resolved_value": resolved_val,
            "evidence": selected_cand["evidence"],
            "warnings": warnings,
        }

    def create_resolution_context(
        self,
        company_id: int,
        raw_statement_rows: list[dict[str, Any]],
        overrides: dict[str, dict[str, Any]],
        aliases: list[dict[str, Any]],
        company_sector: Optional[str] = None,
    ) -> ResolutionContext:
        return ResolutionContext(
            self,
            company_id=company_id,
            raw_statement_rows=raw_statement_rows,
            overrides=overrides,
            aliases=aliases,
            company_sector=company_sector,
        )


class ResolutionContext:
    def __init__(
        self,
        resolver: ModelResolver,
        company_id: int,
        raw_statement_rows: list[dict[str, Any]],
        overrides: dict[str, dict[str, Any]],
        aliases: list[dict[str, Any]],
        company_sector: Optional[str] = None,
    ):
        self.resolver = resolver
        self.company_id = company_id
        self.overrides = overrides
        self.company_sector = company_sector

        # Index aliases by target_id
        self.aliases_by_target: dict[str, list[dict[str, Any]]] = {}
        for alias in aliases:
            self.aliases_by_target.setdefault(alias["target_id"], []).append(alias)

        # Index raw rows by statement type
        self.rows_by_statement: dict[str, list[dict[str, Any]]] = {}
        # Index raw rows by (statement_type, code) for fast override lookup
        # where code is CD_CONTA or LINE_ID_BASE
        self.row_by_code: dict[tuple[str, str], dict[str, Any]] = {}

        for row in raw_statement_rows:
            stmt_type = str(row.get("STATEMENT_TYPE") or "").upper()
            if not stmt_type:
                continue
            self.rows_by_statement.setdefault(stmt_type, []).append(row)
            
            cd_conta = str(row.get("CD_CONTA") or "").strip()
            line_id = str(row.get("LINE_ID_BASE") or "").strip()
            if cd_conta:
                self.row_by_code[(stmt_type, cd_conta)] = row
            if line_id:
                self.row_by_code[(stmt_type, line_id)] = row

        # Cache scored candidates per entry: (target_id, restrict_to_sources) -> list of candidates
        self.scored_candidates_cache: dict[tuple[str, bool], list[dict[str, Any]]] = {}

    def get_ranked_candidates(self, entry: ModelMappingEntry, restrict_to_sources: bool) -> list[dict[str, Any]]:
        target_id = entry.target_id
        cache_key = (target_id, restrict_to_sources)
        if cache_key in self.scored_candidates_cache:
            return self.scored_candidates_cache[cache_key]

        stmt_type = entry.statement_type
        rows = self.rows_by_statement.get(stmt_type, [])
        
        # If restrict_to_sources is True, we filter rows by matching entry.sources
        if restrict_to_sources and entry.sources:
            # Let's index sources for fast matching
            source_codes = set()
            source_labels = set()
            for s in entry.sources:
                if s.line_id_base:
                    source_codes.add(s.line_id_base)
                if s.cd_conta:
                    source_codes.add(s.cd_conta)
                if s.label_snapshot:
                    source_labels.add(s.label_snapshot)

            filtered_rows = []
            for row in rows:
                cd_val = str(row.get("CD_CONTA") or "").strip()
                line_val = str(row.get("LINE_ID_BASE") or "").strip()
                ds_val = str(row.get("DS_CONTA") or "").strip()
                std_val = str(row.get("STANDARD_NAME") or "").strip()
                
                matched = False
                if cd_val in source_codes or line_val in source_codes:
                    matched = True
                elif ds_val in source_labels or std_val in source_labels:
                    matched = True
                
                if matched:
                    filtered_rows.append(row)
            rows = filtered_rows

        candidates = []
        aliases_for_target = self.aliases_by_target.get(target_id, [])
        
        for row in rows:
            score, evidence, warnings = self.resolver.score_candidate(
                row,
                target_id,
                entry.target_label,
                aliases_for_target,
                self.company_sector,
                mapped_sources=entry.sources if entry.sources else None,
            )
            if score > 0:
                candidates.append({
                    "row": row,
                    "score": score,
                    "evidence": evidence,
                    "warnings": warnings,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        self.scored_candidates_cache[cache_key] = candidates
        return candidates

    def resolve_entry_for_period(
        self,
        entry: ModelMappingEntry,
        period: str,
        restrict_to_sources: bool = False,
    ) -> dict[str, Any]:
        target_id = entry.target_id
        
        # 1. Evaluate overrides
        target_overrides = self.overrides.get(target_id, {})
        period_override = target_overrides.get(period) or target_overrides.get("GLOBAL")
        
        if period_override:
            source_code = period_override["source_code"]
            # Locate matching raw row
            matching_row = self.row_by_code.get((entry.statement_type, source_code))
            
            if matching_row:
                val = matching_row.get(period)
                resolved_val = float(val) / 1000.0 if val is not None and not pd.isna(val) else None
                return {
                    "target_id": target_id,
                    "period": period,
                    "selected_source_id": f"{entry.statement_type}:{source_code}",
                    "selected_source_label": period_override["source_desc"] or matching_row.get("DS_CONTA"),
                    "status": "manually_confirmed",
                    "score": 100.0,
                    "confidence_margin": 100.0,
                    "resolved_value": resolved_val,
                    "evidence": ["Manual user mapping override applied"],
                    "warnings": [],
                }

        # 2. Get ranked candidates
        candidates = self.get_ranked_candidates(entry, restrict_to_sources)

        if not candidates:
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": None,
                "selected_source_label": None,
                "status": "unresolved",
                "score": 0.0,
                "confidence_margin": 0.0,
                "resolved_value": None,
                "evidence": ["No matching candidates found"],
                "warnings": [],
            }

        # 3. Resolve best candidate with value present
        if entry.operation in ("sum", "sum_with_sign"):
            active_cands = []
            total_val = 0.0
            any_val = False
            for cand in candidates:
                val = cand["row"].get(period)
                if val is not None and not pd.isna(val):
                    active_cands.append(cand)
                    source_sign = 1
                    if entry.operation == "sum_with_sign" and entry.sources:
                        cd_val = str(cand["row"].get("CD_CONTA") or "").strip()
                        line_val = str(cand["row"].get("LINE_ID_BASE") or "").strip()
                        for s in entry.sources:
                            s_cd = s.cd_conta or s.line_id_base
                            if line_val == s.line_id_base or cd_val == s_cd:
                                source_sign = s.sign
                                break
                    total_val += (float(val) / 1000.0) * source_sign
                    any_val = True

            if not any_val:
                return {
                    "target_id": target_id,
                    "period": period,
                    "selected_source_id": None,
                    "selected_source_label": None,
                    "status": "unresolved",
                    "score": 0.0,
                    "confidence_margin": 0.0,
                    "resolved_value": None,
                    "evidence": ["No active sum candidates found"],
                    "warnings": [],
                }

            labels = [str(c["row"].get("DS_CONTA")) for c in active_cands]
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": f"sum({len(active_cands)})",
                "selected_source_label": " + ".join(labels),
                "status": "auto_accepted",
                "score": 98.0,
                "confidence_margin": 100.0,
                "resolved_value": total_val,
                "evidence": [f"Summed {len(active_cands)} lines"],
                "warnings": [],
            }

        selected_cand = None
        alternatives = []
        for cand in candidates:
            val = cand["row"].get(period)
            if val is not None and not pd.isna(val):
                if not selected_cand:
                    selected_cand = cand
                else:
                    alternatives.append(cand)

        if not selected_cand:
            # Try to return the highest scoring candidate even if it has no value for this period
            best_cand = candidates[0]
            source_code = best_cand["row"].get("LINE_ID_BASE") or best_cand["row"].get("CD_CONTA")
            return {
                "target_id": target_id,
                "period": period,
                "selected_source_id": f"{entry.statement_type}:{source_code}",
                "selected_source_label": best_cand["row"].get("DS_CONTA"),
                "status": "unresolved",
                "score": best_cand["score"],
                "confidence_margin": 0.0,
                "resolved_value": None,
                "evidence": best_cand["evidence"] + ["Candidate found but contains no value in this period"],
                "warnings": best_cand["warnings"],
            }

        # 4. Status determination & margin computation
        status = "auto_accepted" if selected_cand["score"] >= 70.0 else "suggested"
        margin = 100.0
        warnings = list(selected_cand["warnings"])

        if alternatives:
            next_best = alternatives[0]
            margin = selected_cand["score"] - next_best["score"]
            if margin < 15.0 and selected_cand["score"] < 90.0:
                status = "ambiguous"
                warnings.append(
                    f"Ambiguous match. Next best candidate is '{next_best['row'].get('DS_CONTA')}' with score {next_best['score']:.1f}"
                )

        source_code = selected_cand["row"].get("LINE_ID_BASE") or selected_cand["row"].get("CD_CONTA")
        val = selected_cand["row"].get(period)
        resolved_val = float(val) / 1000.0 if val is not None else None

        return {
            "target_id": target_id,
            "period": period,
            "selected_source_id": f"{entry.statement_type}:{source_code}",
            "selected_source_label": selected_cand["row"].get("DS_CONTA"),
            "status": status,
            "score": selected_cand["score"],
            "confidence_margin": margin,
            "resolved_value": resolved_val,
            "evidence": selected_cand["evidence"],
            "warnings": warnings,
        }

