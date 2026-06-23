# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import uuid
from typing import Any, Literal
from sqlalchemy import text, Engine

from src.financials.utils import now_iso_seconds

# Tiers available in the Coverage Universe
CoverageTier = Literal["must_cover", "core", "watchlist", "opportunistic", "excluded", "inappropriate"]

# Analysis types available
AnalysisType = Literal["Equity", "Credit", "IB", "Portfolio Monitoring", "Sector Watch"]

DEFAULT_WEIGHTS = {
    "market_cap_weight": 0.3,
    "volume_weight": 0.3,
    "holding_weight": 0.2,
    "sector_weight": 0.2,
}

DEFAULT_TIER_HOURS = {
    "must_cover": 120.0,
    "core": 80.0,
    "watchlist": 30.0,
    "opportunistic": 45.0,
    "excluded": 5.0,
    "inappropriate": 5.0,
}

# Canonical GICS slugs considered high-complexity for capacity estimation.
# Do NOT use Portuguese sector names — use gics_sector_slug from the companies table.
COMPLEX_GICS_SLUGS = frozenset({"utilities", "financials", "energy"})

MIN_LIQUIDITY_OBSERVATIONS = 5


def _clean_b3_ticker(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip().upper()
    if text_value.endswith(".SA"):
        text_value = text_value[:-3]
    if not text_value or text_value.isdigit():
        return None
    return text_value


def normalize_market_cap_source(source_str: str | None) -> str:
    if not source_str:
        return "unknown"
    s = source_str.strip().lower()
    if s in ("b3", "b3_official", "official_b3", "official-b3"):
        return "official_b3"
    if s in ("cvm", "cvm_official", "official_cvm", "official-cvm"):
        return "official_cvm"
    if s in ("imported_official", "official_imported", "official-imported"):
        return "imported_official"
    if s in ("imported", "imported_user_data", "imported_market_cap", "csv_import", "user", "user_data", "csv"):
        return "imported_user_data"
    if s in ("yahoo", "yahoo_finance", "yfinance", "yahoo finance", "yfinance_api"):
        return "yahoo_finance"
    return "unknown"


NORMALIZED_SOURCE_PRIORITY = {
    "official_b3": 6,
    "official_cvm": 5,
    "imported_official": 4,
    "yahoo_finance": 3,
    "imported_user_data": 2,
    "unknown": 1
}


def _resolve_canonical_market_caps(snapshot_entries: list[Any]) -> dict[int, Any]:
    # Group by cd_cvm
    grouped: dict[int, list[Any]] = {}
    for entry in snapshot_entries:
        if entry.cd_cvm is None or entry.market_cap_brl is None or entry.market_cap_brl <= 0:
            continue
        grouped.setdefault(entry.cd_cvm, []).append(entry)
        
    resolved: dict[int, Any] = {}
    for cd_cvm, entries in grouped.items():
        # Sort ascending so the best one is at the end
        sorted_entries = sorted(entries, key=lambda e: (
            NORMALIZED_SOURCE_PRIORITY.get(normalize_market_cap_source(e.source), 1),
            (e.as_of_date or "").strip(),
            (e.downloaded_at or "").strip(),
            -(e.rank if e.rank is not None else 0),
            e.company_name or ""
        ))
        
        best_entry = sorted_entries[-1]
        best_norm_src = normalize_market_cap_source(best_entry.source)
        best_prio = NORMALIZED_SOURCE_PRIORITY.get(best_norm_src, 1)
        best_as_of = (best_entry.as_of_date or "").strip()
        best_downloaded = (best_entry.downloaded_at or "").strip()
        
        top_candidates = [
            e for e in sorted_entries
            if normalize_market_cap_source(e.source) == best_norm_src
            and (e.as_of_date or "").strip() == best_as_of
            and (e.downloaded_at or "").strip() == best_downloaded
        ]
        
        unique_caps = set(round(e.market_cap_brl, 2) for e in top_candidates)
        if len(unique_caps) > 1:
            resolved[cd_cvm] = (best_entry, top_candidates)
        else:
            resolved[cd_cvm] = (best_entry, None)
            
    return resolved



def ensure_coverage_tables_for_connection(conn: Any) -> None:
    """Creates the tables required for Coverage Universe management in SQLite/PostgreSQL."""
    # 1. coverage_universes table
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS coverage_universes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT,
                analysis_type TEXT NOT NULL,
                benchmark TEXT,
                status TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )

    # 2. universe_companies table
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS universe_companies (
                universe_id TEXT NOT NULL,
                cd_cvm INTEGER NOT NULL,
                tier TEXT NOT NULL,
                manual_score_override REAL,
                owner_analyst TEXT,
                holding_pct REAL DEFAULT 0.0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (universe_id, cd_cvm),
                FOREIGN KEY (universe_id) REFERENCES coverage_universes(id) ON DELETE CASCADE
            )
            """
        )
    )

    # 3. coverage_checklists table
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS coverage_checklists (
                universe_id TEXT NOT NULL,
                cd_cvm INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                is_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                comments TEXT,
                PRIMARY KEY (universe_id, cd_cvm, item_key),
                FOREIGN KEY (universe_id, cd_cvm) REFERENCES universe_companies(universe_id, cd_cvm) ON DELETE CASCADE
            )
            """
        )
    )

    # 4. coverage_decision_history table
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS coverage_decision_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                universe_id TEXT NOT NULL,
                cd_cvm INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                previous_value TEXT,
                new_value TEXT,
                rationale TEXT NOT NULL,
                author TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (universe_id) REFERENCES coverage_universes(id) ON DELETE CASCADE
            )
            """
        )
    )

    # 5. coverage_capacity_scenarios table
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS coverage_capacity_scenarios (
                id TEXT PRIMARY KEY,
                universe_id TEXT NOT NULL,
                name TEXT NOT NULL,
                available_hours REAL NOT NULL,
                tier_weights_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (universe_id) REFERENCES coverage_universes(id) ON DELETE CASCADE
            )
            """
        )
    )


class CoverageUniverseService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _ensure_schema(self) -> None:
        with self.engine.begin() as conn:
            ensure_coverage_tables_for_connection(conn)

    # --- Universe CRUD ---

    def list_universes(self) -> list[dict[str, Any]]:
        self._ensure_schema()
        query = """
            SELECT u.id, u.name, u.purpose, u.analysis_type, u.benchmark, u.status, u.created_at, u.updated_at,
                   (SELECT COUNT(*) FROM universe_companies WHERE universe_id = u.id) as company_count
            FROM coverage_universes u
            ORDER BY u.updated_at DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(query)).fetchall()
            return [dict(row._mapping) for row in rows]

    def get_universe(self, universe_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        query = "SELECT * FROM coverage_universes WHERE id = :id"
        with self.engine.connect() as conn:
            row = conn.execute(text(query), {"id": universe_id}).fetchone()
            if not row:
                return None
            res = dict(row._mapping)
            res["assumptions"] = json.loads(res["assumptions_json"])
            return res

    def create_universe(self, name: str, purpose: str | None, analysis_type: AnalysisType, benchmark: str | None) -> str:
        self._ensure_schema()
        u_id = str(uuid.uuid4())
        now = now_iso_seconds()
        assumptions = {
            "weights": DEFAULT_WEIGHTS,
            "tier_hours": DEFAULT_TIER_HOURS,
        }
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_universes (id, name, purpose, analysis_type, benchmark, status, assumptions_json, created_at, updated_at)
                    VALUES (:id, :name, :purpose, :analysis_type, :benchmark, :status, :assumptions_json, :created_at, :updated_at)
                    """
                ),
                {
                    "id": u_id,
                    "name": name,
                    "purpose": purpose,
                    "analysis_type": analysis_type,
                    "benchmark": benchmark,
                    "status": "draft",
                    "assumptions_json": json.dumps(assumptions),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            # Create a default capacity scenario
            scenario_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_capacity_scenarios (id, universe_id, name, available_hours, tier_weights_json, is_active)
                    VALUES (:id, :universe_id, :name, :available_hours, :tier_weights_json, 1)
                    """
                ),
                {
                    "id": scenario_id,
                    "universe_id": u_id,
                    "name": "Default Capacity Setup",
                    "available_hours": 1600.0,
                    "tier_weights_json": json.dumps(DEFAULT_TIER_HOURS),
                },
            )
        return u_id

    def update_universe(self, universe_id: str, name: str, purpose: str | None, benchmark: str | None, status: str, assumptions: dict[str, Any] | None = None) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        
        # Build update fields dynamically
        fields = ["name = :name", "purpose = :purpose", "benchmark = :benchmark", "status = :status", "updated_at = :updated_at"]
        params = {
            "id": universe_id,
            "name": name,
            "purpose": purpose,
            "benchmark": benchmark,
            "status": status,
            "updated_at": now,
        }
        
        if assumptions is not None:
            fields.append("assumptions_json = :assumptions_json")
            params["assumptions_json"] = json.dumps(assumptions)

        query = f"UPDATE coverage_universes SET {', '.join(fields)} WHERE id = :id"
        with self.engine.begin() as conn:
            conn.execute(text(query), params)

    def delete_universe(self, universe_id: str) -> None:
        self._ensure_schema()
        # Explicit deletion of child rows in safe dependency order inside one transaction:
        with self.engine.begin() as conn:
            # 1. coverage_checklists
            conn.execute(
                text("DELETE FROM coverage_checklists WHERE universe_id = :u_id"),
                {"u_id": universe_id}
            )
            # 2. universe_companies
            conn.execute(
                text("DELETE FROM universe_companies WHERE universe_id = :u_id"),
                {"u_id": universe_id}
            )
            # 3. coverage_decision_history
            conn.execute(
                text("DELETE FROM coverage_decision_history WHERE universe_id = :u_id"),
                {"u_id": universe_id}
            )
            # 4. coverage_capacity_scenarios
            conn.execute(
                text("DELETE FROM coverage_capacity_scenarios WHERE universe_id = :u_id"),
                {"u_id": universe_id}
            )
            # 5. coverage_universes (parent table)
            conn.execute(
                text("DELETE FROM coverage_universes WHERE id = :u_id"),
                {"u_id": universe_id}
            )

    def duplicate_universe(self, universe_id: str, new_name: str, copy_companies: bool = True, copy_checklists: bool = False) -> str:
        self._ensure_schema()
        u = self.get_universe(universe_id)
        if not u:
            raise ValueError("Universe not found")
        
        new_uid = str(uuid.uuid4())
        now = now_iso_seconds()
        
        with self.engine.begin() as conn:
            # 1. Insert duplicated universe
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_universes (id, name, purpose, analysis_type, benchmark, status, assumptions_json, created_at, updated_at)
                    VALUES (:id, :name, :purpose, :analysis_type, :benchmark, :status, :assumptions_json, :created_at, :updated_at)
                    """
                ),
                {
                    "id": new_uid,
                    "name": new_name,
                    "purpose": u.get("purpose"),
                    "analysis_type": u.get("analysis_type", "Equity"),
                    "benchmark": u.get("benchmark"),
                    "status": "draft",
                    "assumptions_json": u.get("assumptions_json") or json.dumps(u.get("assumptions")),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            
            # 2. Duplicate active capacity scenarios for this universe
            scen_row = conn.execute(
                text("SELECT name, available_hours, tier_weights_json FROM coverage_capacity_scenarios WHERE universe_id = :u_id AND is_active = 1"),
                {"u_id": universe_id}
            ).fetchone()
            
            scen_name = scen_row[0] if scen_row else "Default Capacity Setup"
            avail_hours = scen_row[1] if scen_row else 1600.0
            weights_json = scen_row[2] if scen_row else json.dumps(u.get("assumptions", {}).get("tier_hours", DEFAULT_TIER_HOURS))
            
            scenario_id = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_capacity_scenarios (id, universe_id, name, available_hours, tier_weights_json, is_active)
                    VALUES (:id, :universe_id, :name, :available_hours, :tier_weights_json, 1)
                    """
                ),
                {
                    "id": scenario_id,
                    "universe_id": new_uid,
                    "name": f"Copy of {scen_name}",
                    "available_hours": avail_hours,
                    "tier_weights_json": weights_json,
                },
            )

            # 3. Duplicate companies if requested
            if copy_companies:
                companies = conn.execute(
                    text("SELECT cd_cvm, tier, manual_score_override, owner_analyst, holding_pct FROM universe_companies WHERE universe_id = :u_id"),
                    {"u_id": universe_id}
                ).fetchall()
                
                for c_row in companies:
                    conn.execute(
                        text(
                            """
                            INSERT INTO universe_companies (universe_id, cd_cvm, tier, manual_score_override, owner_analyst, holding_pct, updated_at)
                            VALUES (:new_uid, :cd_cvm, :tier, :override, :owner, :holding, :updated_at)
                            """
                        ),
                        {
                            "new_uid": new_uid,
                            "cd_cvm": c_row.cd_cvm,
                            "tier": c_row.tier,
                            "override": c_row.manual_score_override,
                            "owner": c_row.owner_analyst,
                            "holding": c_row.holding_pct,
                            "updated_at": now,
                        }
                    )
                    
                    if copy_checklists:
                        checklists = conn.execute(
                            text("SELECT item_key, is_completed, completed_at, comments FROM coverage_checklists WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                            {"u_id": universe_id, "cd_cvm": c_row.cd_cvm}
                        ).fetchall()
                        for chk in checklists:
                            conn.execute(
                                text(
                                    """
                                    INSERT INTO coverage_checklists (universe_id, cd_cvm, item_key, is_completed, completed_at, comments)
                                    VALUES (:new_uid, :cd_cvm, :item_key, :is_completed, :completed_at, :comments)
                                    """
                                ),
                                {
                                    "new_uid": new_uid,
                                    "cd_cvm": c_row.cd_cvm,
                                    "item_key": chk.item_key,
                                    "is_completed": chk.is_completed,
                                    "completed_at": chk.completed_at,
                                    "comments": chk.comments,
                                }
                            )
                    else:
                        self._init_checklist_items(conn, new_uid, c_row.cd_cvm, c_row.tier)
                        
        return new_uid

    def bulk_update_companies_in_universe(self, universe_id: str, company_ids: list[int], tier: str, rationale: str) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            for cd_cvm in company_ids:
                if tier == "none":
                    existing = conn.execute(
                        text("SELECT tier FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                        {"u_id": universe_id, "cd_cvm": cd_cvm}
                    ).fetchone()
                    if not existing:
                        continue
                    prev_tier = existing[0]

                    conn.execute(
                        text("DELETE FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                        {"u_id": universe_id, "cd_cvm": cd_cvm}
                    )

                    conn.execute(
                        text(
                            """
                            INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                            VALUES (:u_id, :cd_cvm, 'tier_change', :prev, 'none', :rationale, :timestamp)
                            """
                        ),
                        {"u_id": universe_id, "cd_cvm": cd_cvm, "prev": prev_tier, "rationale": rationale, "timestamp": now}
                    )
                else:
                    existing = conn.execute(
                        text("SELECT tier, holding_pct FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                        {"u_id": universe_id, "cd_cvm": cd_cvm}
                    ).fetchone()

                    holding_val = 0.0

                    if existing:
                        prev_tier, prev_holding = existing
                        conn.execute(
                            text(
                                """
                                UPDATE universe_companies
                                SET tier = :tier, updated_at = :updated_at
                                WHERE universe_id = :u_id AND cd_cvm = :cd_cvm
                                """
                            ),
                            {"u_id": universe_id, "cd_cvm": cd_cvm, "tier": tier, "updated_at": now}
                        )
                        
                        if prev_tier != tier:
                            conn.execute(
                                text(
                                    """
                                    INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                                    VALUES (:u_id, :cd_cvm, 'tier_change', :prev, :new, :rationale, :timestamp)
                                    """
                                ),
                                {"u_id": universe_id, "cd_cvm": cd_cvm, "prev": prev_tier, "new": tier, "rationale": rationale, "timestamp": now}
                            )
                    else:
                        conn.execute(
                            text(
                                """
                                INSERT INTO universe_companies (universe_id, cd_cvm, tier, manual_score_override, owner_analyst, holding_pct, updated_at)
                                VALUES (:u_id, :cd_cvm, :tier, NULL, NULL, :holding, :updated_at)
                                """
                            ),
                            {"u_id": universe_id, "cd_cvm": cd_cvm, "tier": tier, "holding": holding_val, "updated_at": now}
                        )

                        self._init_checklist_items(conn, universe_id, cd_cvm, tier)

                        conn.execute(
                            text(
                                """
                                INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                                VALUES (:u_id, :cd_cvm, 'tier_change', 'none', :new, :rationale, :timestamp)
                                """
                            ),
                            {"u_id": universe_id, "cd_cvm": cd_cvm, "new": tier, "rationale": rationale, "timestamp": now}
                        )



    # --- Company Universe membership ---

    def add_company_to_universe(self, universe_id: str, cd_cvm: int, tier: CoverageTier, rationale: str, owner: str | None = None, holding_pct: float | None = None) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            # Check if company already in universe
            existing = conn.execute(
                text("SELECT tier, holding_pct FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            ).fetchone()

            holding_val = float(holding_pct) if holding_pct is not None else 0.0

            if existing:
                prev_tier, prev_holding = existing
                # Update tier, owner, and holdings
                conn.execute(
                    text(
                        """
                        UPDATE universe_companies
                        SET tier = :tier, owner_analyst = :owner, holding_pct = :holding, updated_at = :updated_at
                        WHERE universe_id = :u_id AND cd_cvm = :cd_cvm
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "tier": tier, "owner": owner, "holding": holding_val, "updated_at": now}
                )
                
                if prev_tier != tier:
                    conn.execute(
                        text(
                            """
                            INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                            VALUES (:u_id, :cd_cvm, 'tier_change', :prev, :new, :rationale, :timestamp)
                            """
                        ),
                        {"u_id": universe_id, "cd_cvm": cd_cvm, "prev": prev_tier, "new": tier, "rationale": rationale, "timestamp": now}
                    )
                
                if prev_holding != holding_val:
                    conn.execute(
                        text(
                            """
                            INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                            VALUES (:u_id, :cd_cvm, 'holding_change', :prev, :new, :rationale, :timestamp)
                            """
                        ),
                        {"u_id": universe_id, "cd_cvm": cd_cvm, "prev": str(prev_holding), "new": str(holding_val), "rationale": rationale, "timestamp": now}
                    )
            else:
                # Insert new entry
                conn.execute(
                    text(
                        """
                        INSERT INTO universe_companies (universe_id, cd_cvm, tier, manual_score_override, owner_analyst, holding_pct, updated_at)
                        VALUES (:u_id, :cd_cvm, :tier, NULL, :owner, :holding, :updated_at)
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "tier": tier, "owner": owner, "holding": holding_val, "updated_at": now}
                )

                # Initialize default checklist items for this tier
                self._init_checklist_items(conn, universe_id, cd_cvm, tier)

                # Log decision
                conn.execute(
                    text(
                        """
                        INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                        VALUES (:u_id, :cd_cvm, 'tier_change', 'none', :new, :rationale, :timestamp)
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "new": tier, "rationale": rationale, "timestamp": now}
                )


    def remove_company_from_universe(self, universe_id: str, cd_cvm: int, rationale: str) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT tier FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            ).fetchone()

            if not existing:
                return

            conn.execute(
                text("DELETE FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            )

            # Log decision
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                    VALUES (:u_id, :cd_cvm, 'company_removed', :prev, 'none', :rationale, :timestamp)
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "prev": existing[0], "rationale": rationale, "timestamp": now}
            )

    def _init_checklist_items(self, conn: Any, universe_id: str, cd_cvm: int, tier: CoverageTier) -> None:
        items = ["model_updated", "thesis_reviewed", "valuation_fresh"]
        if tier in ("must_cover", "core"):
            items.extend(["capital_structure_ok", "kpi_checked"])
        
        now = now_iso_seconds()
        for item in items:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO coverage_checklists (universe_id, cd_cvm, item_key, is_completed, completed_at, comments)
                    VALUES (:u_id, :cd_cvm, :key, 0, NULL, NULL)
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "key": item}
            )

    def update_company_owner_analyst(self, universe_id: str, cd_cvm: int, owner: str | None, rationale: str) -> None:
        """Set or clear the owner_analyst for a company in a universe. Logs to decision history."""
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT owner_analyst FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            ).fetchone()
            if not existing:
                raise ValueError("Company not in universe")
            prev_owner = existing[0]
            conn.execute(
                text(
                    """
                    UPDATE universe_companies
                    SET owner_analyst = :owner, updated_at = :updated_at
                    WHERE universe_id = :u_id AND cd_cvm = :cd_cvm
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "owner": owner, "updated_at": now}
            )
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_decision_history
                        (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                    VALUES (:u_id, :cd_cvm, 'owner_change', :prev, :new, :rationale, :timestamp)
                    """
                ),
                {
                    "u_id": universe_id,
                    "cd_cvm": cd_cvm,
                    "prev": prev_owner or "Unassigned",
                    "new": owner or "Unassigned",
                    "rationale": rationale,
                    "timestamp": now,
                }
            )

    def _get_news_workload_for_universe(self, universe_id: str) -> dict[int, dict[str, Any]]:
        """
        Returns per-cd_cvm news workload from the local news database.
        Uses a separate news engine; always local/offline — no network calls.
        Falls back gracefully if tables do not exist or news DB is unavailable.

        Returns:
            dict mapping cd_cvm -> {article_count_30d, article_count_60d, article_count_90d,
                                     latest_article_date, mapping_available}
            On failure: {"_unavailable": True, "reason": str}
        """
        try:
            from src.platform.settings import get_settings  # noqa: PLC0415
            from src.news.schema import get_news_engine  # noqa: PLC0415
            settings = get_settings()
            news_engine = get_news_engine(settings)
        except Exception as exc:
            return {"_unavailable": True, "reason": f"news engine unavailable: {exc}"}

        # Fetch all cd_cvm values in this universe to scope the news query
        try:
            with self.engine.connect() as conn:
                cvm_rows = conn.execute(
                    text("SELECT cd_cvm FROM universe_companies WHERE universe_id = :u_id"),
                    {"u_id": universe_id}
                ).fetchall()
        except Exception as exc:
            return {"_unavailable": True, "reason": f"failed reading universe companies: {exc}"}

        if not cvm_rows:
            return {}

        cd_cvms = [row[0] for row in cvm_rows]
        placeholders = ", ".join(str(c) for c in cd_cvms)

        # Query news DB directly — separate SQLite file, no cross-DB join
        # news_article_companies: (article_id, cd_cvm, match_method, match_reason, ...)
        # news_articles: (article_id, published_at, ...)
        try:
            with news_engine.connect() as nconn:
                rows = nconn.execute(
                    text(
                        f"""
                        SELECT
                            nac.cd_cvm,
                            COUNT(DISTINCT CASE WHEN a.published_at >= datetime('now', '-30 days')
                                               THEN a.article_id END) AS count_30d,
                            COUNT(DISTINCT CASE WHEN a.published_at >= datetime('now', '-60 days')
                                               THEN a.article_id END) AS count_60d,
                            COUNT(DISTINCT CASE WHEN a.published_at >= datetime('now', '-90 days')
                                               THEN a.article_id END) AS count_90d,
                            MAX(a.published_at) AS latest_article_date
                        FROM news_article_companies nac
                        JOIN news_articles a ON a.article_id = nac.article_id
                        WHERE nac.cd_cvm IN ({placeholders})
                        GROUP BY nac.cd_cvm
                        """
                    )
                ).fetchall()
        except Exception as exc:
            return {"_unavailable": True, "reason": f"news query failed: {exc}"}

        result: dict[int, dict[str, Any]] = {}
        for cd_cvm in cd_cvms:
            result[cd_cvm] = {
                "article_count_30d": 0,
                "article_count_60d": 0,
                "article_count_90d": 0,
                "latest_article_date": None,
                "mapping_available": False,
            }
        for row in rows:
            cd_cvm = row[0]
            if cd_cvm in result:
                result[cd_cvm] = {
                    "article_count_30d": row[1] or 0,
                    "article_count_60d": row[2] or 0,
                    "article_count_90d": row[3] or 0,
                    "latest_article_date": row[4],
                    "mapping_available": True,
                }
        return result

    def get_recommendation_summary(self, universe_id: str) -> dict[str, Any]:
        """
        Derives a recommendation package from existing priority scores.
        Does NOT auto-approve based on score. Returns proposed actions and risks
        for manager review. Decision status stored in universe assumptions_json.
        """
        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            return {"error": "Universe not found"}

        scores = self.calculate_priority_scores(universe_id)
        capacity = self.get_capacity_data(universe_id)

        keep: list[dict[str, Any]] = []
        review: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        excluded_tiers: list[dict[str, Any]] = []

        missing_market_cap = 0
        missing_gics = 0
        unassigned_owner = 0

        for s in scores:
            short = {
                "cd_cvm": s["cd_cvm"],
                "company_name": s.get("company_name"),
                "ticker_b3": s.get("ticker_b3"),
                "tier": s.get("tier"),
                "score_status": s.get("score_status"),
                "final_score": s.get("final_score"),
                "missing_factors": s.get("missing_factors", []),
                "owner": s.get("owner_analyst"),
            }
            if s.get("market_cap") is None:
                missing_market_cap += 1
            if not s.get("gics_sector") or s.get("gics_sector") == "Unknown":
                missing_gics += 1
            if not s.get("owner_analyst"):
                unassigned_owner += 1

            tier = s.get("tier", "")
            if tier in ("excluded", "inappropriate"):
                excluded_tiers.append(short)
            elif s.get("score_status") == "blocked":
                blocked.append(short)
            elif isinstance(s.get("final_score"), (int, float)) and s["final_score"] >= 50:
                keep.append(short)
            else:
                review.append(short)

        # Proposed actions — never auto-approve
        proposed_actions: list[str] = []
        if missing_market_cap > 0:
            proposed_actions.append(
                f"Resolve market cap for {missing_market_cap} company(ies) before finalizing priorities."
            )
        if missing_gics > 0:
            proposed_actions.append(
                f"Classify GICS sector for {missing_gics} company(ies) to enable complexity-adjusted capacity."
            )
        if unassigned_owner > 0:
            proposed_actions.append(
                f"Assign analyst owner to {unassigned_owner} unassigned company(ies)."
            )
        if blocked:
            proposed_actions.append(
                f"Review {len(blocked)} blocked company(ies): data gaps prevent scoring."
            )
        if capacity.get("capacity_utilization_pct", 0) > 90:
            proposed_actions.append(
                "Capacity utilization >90%. Consider reducing universe scope or increasing hours."
            )

        # Risks
        risks: list[str] = []
        if missing_market_cap > 0:
            risks.append(f"Market cap missing for {missing_market_cap} company(ies) — scores may be underweighted.")
        if missing_gics > 0:
            risks.append(f"GICS classification absent for {missing_gics} company(ies) — capacity estimate is understated.")
        if blocked:
            risks.append(f"{len(blocked)} company(ies) blocked — not ranked in prioritization.")

        # Manager decision status from assumptions_json
        assumptions = universe.get("assumptions", {})
        manager_decision = assumptions.get("manager_decision", {
            "status": "draft",
            "decided_at": None,
            "notes": None,
        })

        return {
            "universe_id": universe_id,
            "company_count": len(scores),
            "keep": keep,
            "review": review,
            "blocked": blocked,
            "excluded": excluded_tiers,
            "missing_data_risks": {
                "missing_market_cap_count": missing_market_cap,
                "missing_gics_count": missing_gics,
                "unassigned_owner_count": unassigned_owner,
            },
            "proposed_actions": proposed_actions,
            "risks": risks,
            "capacity_summary": {
                "available_hours": capacity.get("available_hours"),
                "required_hours": capacity.get("required_hours"),
                "utilization_pct": capacity.get("capacity_utilization_pct"),
            },
            "manager_decision": manager_decision,
        }

    # --- Prioritization Scoring
    def calculate_priority_scores(self, universe_id: str) -> list[dict[str, Any]]:
        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            return []

        weights = universe.get("assumptions", {}).get("weights", DEFAULT_WEIGHTS)
        
        query = """
            SELECT uc.cd_cvm, uc.tier, uc.manual_score_override, uc.owner_analyst, uc.holding_pct,
                   c.company_name, c.ticker_b3, c.setor_analitico, c.gics_sector, c.gics_sector_slug,
                   (SELECT COUNT(*) FROM coverage_checklists WHERE universe_id = uc.universe_id AND cd_cvm = uc.cd_cvm AND is_completed = 1) as completed_checklist_count,
                   (SELECT COUNT(*) FROM coverage_checklists WHERE universe_id = uc.universe_id AND cd_cvm = uc.cd_cvm) as total_checklist_count
            FROM universe_companies uc
            LEFT JOIN companies c ON uc.cd_cvm = c.cd_cvm
            WHERE uc.universe_id = :u_id
        """

        from src.platform.settings import get_settings  # noqa: PLC0415
        from src.companies.market_cap import MarketCapService  # noqa: PLC0415
        from src.companies.gics_manual_mapping import resolve_gics_classification  # noqa: PLC0415
        from src.companies.sector_taxonomy import sector_slugify  # noqa: PLC0415

        settings = get_settings()
        mcap_service = MarketCapService(settings=settings)
        try:
            snapshot_entries = mcap_service.read_snapshot()
            mcap_map = _resolve_canonical_market_caps(snapshot_entries)
        except Exception as exc:
            import logging as _logging  # noqa: PLC0415
            _logging.getLogger(__name__).warning("Failed to read market cap snapshot: %s", exc)
            mcap_map = {}

        with self.engine.connect() as conn:
            companies = conn.execute(text(query), {"u_id": universe_id}).fetchall()
            
            results = []

            for comp in companies:
                comp_data = dict(comp._mapping)
                cd_cvm = comp_data["cd_cvm"]
                
                # Fallbacks for catalog-only or missing companies
                identity = None
                if not comp_data.get("company_name") or not comp_data.get("ticker_b3"):
                    from src.companies.identity import CompanyIdentityResolver  # noqa: PLC0415
                    identity = CompanyIdentityResolver().resolve(cd_cvm)

                if not comp_data.get("company_name"):
                    comp_data["company_name"] = (identity.company_name if identity else None) or f"CVM {cd_cvm}"
                if not comp_data.get("ticker_b3"):
                    comp_data["ticker_b3"] = _clean_b3_ticker(identity.ticker_b3 if identity else None)
                if not comp_data.get("setor_analitico"):
                    comp_data["setor_analitico"] = "Unknown"
                
                gics_val = comp_data.get("gics_sector")
                gics_sector_slug = comp_data.get("gics_sector_slug")

                # 1. Market Cap (from canonical snapshot service with deterministic DB fallback)
                mkt_cap = None
                mcap_entry = None
                mcap_conflict_candidates = None
                
                resolved_tuple = mcap_map.get(cd_cvm)
                if resolved_tuple:
                    mcap_entry, mcap_conflict_candidates = resolved_tuple

                mcap_source = None
                mcap_source_normalized = "unknown"
                mcap_source_date = None
                mcap_downloaded_at = None
                mcap_method = None
                mcap_provider_status = None
                mcap_is_stale = False
                mcap_selection_origin = None
                mcap_preset = None
                mcap_conflict_metadata = None

                if mcap_conflict_candidates:
                    mkt_cap = None
                    mcap_source = mcap_entry.source if mcap_entry else None
                    mcap_source_normalized = normalize_market_cap_source(mcap_source)
                    mcap_source_date = mcap_entry.as_of_date if mcap_entry else None
                    mcap_downloaded_at = mcap_entry.downloaded_at if mcap_entry else None
                    mcap_method = "snapshot_conflict"
                    mcap_selection_origin = "snapshot_conflict"
                    mcap_conflict_metadata = {
                        "candidates": [
                            {"source": e.source, "as_of_date": e.as_of_date, "market_cap": e.market_cap_brl}
                            for e in mcap_conflict_candidates
                        ]
                    }
                elif mcap_entry:
                    mkt_cap = mcap_entry.market_cap_brl
                    mcap_source = mcap_entry.source
                    mcap_source_normalized = normalize_market_cap_source(mcap_source)
                    mcap_source_date = mcap_entry.as_of_date
                    mcap_downloaded_at = mcap_entry.downloaded_at
                    mcap_method = mcap_entry.method
                    mcap_provider_status = mcap_entry.provider_status
                    mcap_selection_origin = "snapshot"
                    mcap_preset = None
                    
                    # Check stale status
                    stale_days = settings.market_cap_cache_max_age_days
                    try:
                        from datetime import date as dt_date  # noqa: PLC0415
                        as_of = dt_date.fromisoformat(mcap_entry.as_of_date[:10])
                        today = dt_date.today()
                        if (today - as_of).days > stale_days:
                            mcap_is_stale = True
                    except Exception:
                        pass
                
                if mkt_cap is None and mcap_selection_origin != "snapshot_conflict":
                    db_query = """
                        SELECT market_cap, source, source_date, updated_at, selected_preset
                        FROM company_universe
                        WHERE cd_cvm = :cd_cvm AND market_cap IS NOT NULL AND market_cap > 0
                    """
                    rows = conn.execute(text(db_query), {"cd_cvm": cd_cvm}).fetchall()
                    if rows:
                        def db_row_key(r):
                            norm_src = normalize_market_cap_source(r[1])
                            prio = NORMALIZED_SOURCE_PRIORITY.get(norm_src, 1)
                            s_date = (r[2] or "").strip()
                            u_date = (r[3] or "").strip()
                            return (prio, s_date, u_date)
                            
                        sorted_rows = sorted(rows, key=db_row_key)
                        best_row = sorted_rows[-1]
                        best_norm_src = normalize_market_cap_source(best_row[1])
                        best_prio = NORMALIZED_SOURCE_PRIORITY.get(best_norm_src, 1)
                        best_s_date = (best_row[2] or "").strip()
                        best_u_date = (best_row[3] or "").strip()
                        
                        top_rows = [
                            r for r in sorted_rows
                            if normalize_market_cap_source(r[1]) == best_norm_src
                            and (r[2] or "").strip() == best_s_date
                            and (r[3] or "").strip() == best_u_date
                        ]
                        
                        unique_db_caps = set(round(r[0], 2) for r in top_rows)
                        if len(unique_db_caps) > 1:
                            mkt_cap = None
                            mcap_source = best_row[1]
                            mcap_source_normalized = best_norm_src
                            mcap_source_date = best_row[2]
                            mcap_downloaded_at = best_row[3]
                            mcap_method = "database_conflict"
                            mcap_selection_origin = "database_conflict"
                            mcap_preset = None
                            mcap_conflict_metadata = {
                                "candidates": [
                                    {"source": r[1], "as_of_date": r[2], "market_cap": r[0]}
                                    for r in top_rows
                                ]
                            }
                        else:
                            mkt_cap = best_row[0]
                            mcap_source = best_row[1]
                            mcap_source_normalized = best_norm_src
                            mcap_source_date = best_row[2]
                            mcap_downloaded_at = best_row[3]
                            mcap_method = "database_cache"
                            mcap_selection_origin = "database_cache"
                            mcap_preset = best_row[4] # selected_preset
                    else:
                        mcap_selection_origin = "missing"
                        mcap_preset = None

                # 2. Daily Traded BRL Volume Liquidity
                volume_query = """
                    SELECT date, ticker, volume, close
                    FROM market_history
                    WHERE cd_cvm = :cd_cvm AND date >= date('now', '-30 days')
                """
                vol_rows = conn.execute(text(volume_query), {"cd_cvm": cd_cvm}).fetchall()
                daily_values = {}
                daily_volume = {}
                for v_row in vol_rows:
                    v_date = v_row[0]
                    v_ticker = v_row[1]
                    v_vol = v_row[2]
                    v_close = v_row[3]
                    
                    if v_vol is None or v_close is None or v_vol <= 0 or v_close <= 0:
                        continue
                        
                    trade_val = v_vol * v_close
                    daily_values[v_date] = daily_values.get(v_date, 0.0) + trade_val
                    daily_volume[v_date] = daily_volume.get(v_date, 0.0) + v_vol
                
                num_obs = len(daily_values)
                avg_val = sum(daily_values.values()) / num_obs if num_obs > 0 else 0.0
                avg_vol = sum(daily_volume.values()) / num_obs if num_obs > 0 else 0.0

                liquidity_is_stale = False
                if daily_values:
                    max_date_str = max(daily_values.keys())
                    try:
                        from datetime import date as dt_date  # noqa: PLC0415
                        last_trade = dt_date.fromisoformat(max_date_str[:10])
                        today = dt_date.today()
                        if (today - last_trade).days > 10:
                            liquidity_is_stale = True
                    except Exception:
                        pass
                else:
                    liquidity_is_stale = True

                # Calculate Scores & Factor availability
                if mkt_cap is None or mkt_cap <= 0:
                    cap_score = None
                else:
                    cap_score = self._calc_log_score(mkt_cap, 7.0, 11.7) # 10M to 50B

                if num_obs < MIN_LIQUIDITY_OBSERVATIONS:
                    vol_score = None
                else:
                    vol_score = self._calc_log_score(avg_val, 4.0, 8.0) # 10k to 100M

                # 3. Holdings
                w_hold = weights.get("holding_weight", 0.2)
                holding_pct = comp_data.get("holding_pct")
                if w_hold > 0.0:
                    if holding_pct is None or holding_pct == 0.0:
                        holding_score = None
                    else:
                        holding_score = min(max(holding_pct, 0.0), 100.0)
                else:
                    holding_score = None

                # 4. Sector Complexity (uses canonical GICS identifiers)
                gics_class = resolve_gics_classification(gics_sector=gics_val, gics_sector_slug=gics_sector_slug)
                if gics_class is None:
                    sector_score = None
                    comp_data["gics_sector"] = "Unknown"
                else:
                    gics_slug = gics_class.gics_sector_slug
                    is_complex = gics_slug in ("utilities", "financials", "energy")
                    sector_score = 100.0 if is_complex else 50.0
                    comp_data["gics_sector"] = gics_class.gics_sector

                # Factor availability counting based ONLY on weights > 0
                w_cap = weights.get("market_cap_weight", 0.3)
                w_vol = weights.get("volume_weight", 0.3)
                w_hold = weights.get("holding_weight", 0.2)
                w_sect = weights.get("sector_weight", 0.2)

                available_factors = []
                missing_factors = []
                available_weights_sum = 0.0
                calculated_sum = 0.0

                if w_cap > 0:
                    if cap_score is not None:
                        available_factors.append("market_cap")
                        available_weights_sum += w_cap
                        calculated_sum += cap_score * w_cap
                    else:
                        missing_factors.append("market_cap")

                if w_vol > 0:
                    if vol_score is not None:
                        available_factors.append("volume")
                        available_weights_sum += w_vol
                        calculated_sum += vol_score * w_vol
                    else:
                        missing_factors.append("volume")

                if w_hold > 0:
                    if holding_score is not None:
                        available_factors.append("holding_pct")
                        available_weights_sum += w_hold
                        calculated_sum += holding_score * w_hold
                    else:
                        missing_factors.append("holding_pct")

                if w_sect > 0:
                    if sector_score is not None:
                        available_factors.append("sector_complexity")
                        available_weights_sum += w_sect
                        calculated_sum += sector_score * w_sect
                    else:
                        missing_factors.append("sector_complexity")

                active_weights_sum = w_cap + w_vol + w_hold + w_sect

                is_blocked = (
                    active_weights_sum == 0 or
                    available_weights_sum < 0.5 or 
                    len(available_factors) <= 1 or 
                    (len(available_factors) == 1 and available_factors[0] == "sector_complexity")
                )

                if is_blocked:
                    score_status = "blocked"
                    calc_score = None
                    final_score = None
                else:
                    score_status = "complete" if len(missing_factors) == 0 else "partial"
                    calc_score = calculated_sum / available_weights_sum
                    override = comp_data.get("manual_score_override") or 0.0
                    final_score = round(min(max(calc_score + override, 0.0), 100.0), 1)
                    calc_score = round(calc_score, 1)

                factor_details = {
                    "market_cap": {
                        "name": "Market Cap",
                        "original_weight": w_cap,
                        "effective_weight": round(w_cap / available_weights_sum, 4) if (w_cap > 0 and cap_score is not None and available_weights_sum > 0) else 0.0,
                        "raw_value": mkt_cap,
                        "score": round(cap_score, 1) if cap_score is not None else None,
                        "contribution": round((cap_score * w_cap) / available_weights_sum, 1) if (w_cap > 0 and cap_score is not None and available_weights_sum > 0) else 0.0,
                        "missing": w_cap > 0 and cap_score is None,
                        "weight_pct": round(w_cap * 100, 1),
                    },
                    "volume": {
                        "name": "Volume",
                        "original_weight": w_vol,
                        "effective_weight": round(w_vol / available_weights_sum, 4) if (w_vol > 0 and vol_score is not None and available_weights_sum > 0) else 0.0,
                        "raw_value": avg_val if vol_score is not None else None,
                        "score": round(vol_score, 1) if vol_score is not None else None,
                        "contribution": round((vol_score * w_vol) / available_weights_sum, 1) if (w_vol > 0 and vol_score is not None and available_weights_sum > 0) else 0.0,
                        "missing": w_vol > 0 and vol_score is None,
                        "weight_pct": round(w_vol * 100, 1),
                    },
                    "holding_pct": {
                        "name": "Holdings",
                        "original_weight": w_hold,
                        "effective_weight": round(w_hold / available_weights_sum, 4) if (w_hold > 0 and holding_score is not None and available_weights_sum > 0) else 0.0,
                        "raw_value": holding_pct if holding_score is not None else None,
                        "score": round(holding_score, 1) if holding_score is not None else None,
                        "contribution": round((holding_score * w_hold) / available_weights_sum, 1) if (w_hold > 0 and holding_score is not None and available_weights_sum > 0) else 0.0,
                        "missing": w_hold > 0 and holding_score is None,
                        "weight_pct": round(w_hold * 100, 1),
                    },
                    "sector_complexity": {
                        "name": "Sector",
                        "original_weight": w_sect,
                        "effective_weight": round(w_sect / available_weights_sum, 4) if (w_sect > 0 and sector_score is not None and available_weights_sum > 0) else 0.0,
                        "raw_value": gics_class.gics_sector if gics_class else None,
                        "score": round(sector_score, 1) if sector_score is not None else None,
                        "contribution": round((sector_score * w_sect) / available_weights_sum, 1) if (w_sect > 0 and sector_score is not None and available_weights_sum > 0) else 0.0,
                        "missing": w_sect > 0 and sector_score is None,
                        "weight_pct": round(w_sect * 100, 1),
                    }
                }

                comp_data.update({
                    "market_cap": mkt_cap,
                    "market_cap_source": mcap_source,
                    "market_cap_source_normalized": mcap_source_normalized,
                    "market_cap_source_date": mcap_source_date,
                    "market_cap_downloaded_at": mcap_downloaded_at,
                    "market_cap_method": mcap_method,
                    "market_cap_provider_status": mcap_provider_status,
                    "market_cap_currency": "BRL",
                    "market_cap_is_stale": mcap_is_stale,
                    "market_cap_selection_origin": mcap_selection_origin,
                    "market_cap_preset": mcap_preset,
                    "market_cap_conflict_metadata": mcap_conflict_metadata,
                    "avg_volume": avg_vol,
                    "avg_value_brl": avg_val,
                    "liquidity_observations": num_obs,
                    "liquidity_lookback_days": 30,
                    "liquidity_min_observations": MIN_LIQUIDITY_OBSERVATIONS,
                    "liquidity_is_stale": liquidity_is_stale,
                    "cap_score": round(cap_score, 1) if cap_score is not None else None,
                    "vol_score": round(vol_score, 1) if vol_score is not None else None,
                    "holding_score": round(holding_score, 1) if holding_score is not None else None,
                    "sector_score": round(sector_score, 1) if sector_score is not None else None,
                    "calculated_score": calc_score,
                    "final_score": final_score,
                    "score_status": score_status,
                    "score_completeness": round(available_weights_sum, 2),
                    "missing_factors": missing_factors,
                    "factor_details": factor_details,
                    "score_delta": None,
                    "score_baseline": None,
                    "next_pending_item": None,
                })

                # Derive next pending checklist item for 'Next Action' column
                next_action_row = conn.execute(
                    text(
                        """
                        SELECT item_key FROM coverage_checklists
                        WHERE universe_id = :u_id AND cd_cvm = :cd_cvm AND is_completed = 0
                        ORDER BY item_key LIMIT 1
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm},
                ).fetchone()
                comp_data["next_pending_item"] = next_action_row[0] if next_action_row else None

                results.append(comp_data)

            # Sort priority: non-blocked first, sorted by score DESC, then blocked.
            results.sort(key=lambda x: (
                x["score_status"] == "blocked",
                -(x["final_score"] if x["final_score"] is not None else -1.0),
                x.get("company_name", "")
            ))
            return results

    def _calc_log_score(self, val: float, min_log: float, max_log: float) -> float:
        if val <= 0:
            return 0.0
        log_val = math.log10(val)
        if log_val <= min_log:
            return 0.0
        if log_val >= max_log:
            return 100.0
        return ((log_val - min_log) / (max_log - min_log)) * 100.0

    def save_manual_score_override(self, universe_id: str, cd_cvm: int, override: float | None, rationale: str) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT manual_score_override FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            ).fetchone()

            if not existing:
                raise ValueError("Company not in universe")

            conn.execute(
                text(
                    """
                    UPDATE universe_companies
                    SET manual_score_override = :override, updated_at = :updated_at
                    WHERE universe_id = :u_id AND cd_cvm = :cd_cvm
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "override": override, "updated_at": now}
            )

            # Log override decision
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                    VALUES (:u_id, :cd_cvm, 'score_override', :prev, :new, :rationale, :timestamp)
                    """
                ),
                {
                    "u_id": universe_id,
                    "cd_cvm": cd_cvm,
                    "prev": str(existing[0]),
                    "new": str(override),
                    "rationale": rationale,
                    "timestamp": now,
                }
            )

    # --- Checklists & Tasks ---

    def get_coverage_checklists(self, universe_id: str, cd_cvm: int) -> list[dict[str, Any]]:
        self._ensure_schema()
        query = """
            SELECT item_key, is_completed, completed_at, comments
            FROM coverage_checklists
            WHERE universe_id = :u_id AND cd_cvm = :cd_cvm
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), {"u_id": universe_id, "cd_cvm": cd_cvm}).fetchall()
            return [dict(row._mapping) for row in rows]

    def update_checklist_item(self, universe_id: str, cd_cvm: int, item_key: str, is_completed: bool, comments: str | None, rationale: str) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        completed_at = now if is_completed else None
        completed_int = 1 if is_completed else 0

        with self.engine.begin() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT is_completed FROM coverage_checklists
                    WHERE universe_id = :u_id AND cd_cvm = :cd_cvm AND item_key = :key
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "key": item_key}
            ).fetchone()

            if not existing:
                conn.execute(
                    text(
                        """
                        INSERT INTO coverage_checklists (universe_id, cd_cvm, item_key, is_completed, completed_at, comments)
                        VALUES (:u_id, :cd_cvm, :key, :is_comp, :comp_at, :comments)
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "key": item_key, "is_comp": completed_int, "comp_at": completed_at, "comments": comments}
                )
                prev_val = "none"
            else:
                conn.execute(
                    text(
                        """
                        UPDATE coverage_checklists
                        SET is_completed = :is_comp, completed_at = :comp_at, comments = :comments
                        WHERE universe_id = :u_id AND cd_cvm = :cd_cvm AND item_key = :key
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "key": item_key, "is_comp": completed_int, "comp_at": completed_at, "comments": comments}
                )
                prev_val = "1" if existing[0] else "0"

            # Log checklist change
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                    VALUES (:u_id, :cd_cvm, 'checklist_change', :prev, :new, :rationale, :timestamp)
                    """
                ),
                {
                    "u_id": universe_id,
                    "cd_cvm": cd_cvm,
                    "prev": f"{item_key}:{prev_val}",
                    "new": f"{item_key}:{completed_int}",
                    "rationale": rationale,
                    "timestamp": now,
                }
            )

    def get_work_queue(self, universe_id: str) -> list[dict[str, Any]]:
        """
        Returns derived + checklist-based action tasks for a universe.
        Batch reads — no N+1 per-company queries.

        Performance note: For universes of ~500 companies this runs 4 SQL queries
        (company data batch, checklist batch, market cap batch, news batch) plus
        in-memory derivation. Expect ~200-500ms depending on disk speed.
        """
        self._ensure_schema()

        # --- 1. Batch: fetch all universe companies with key fields ---
        company_query = """
            SELECT
                uc.cd_cvm, uc.tier, uc.owner_analyst,
                c.company_name, c.ticker_b3, c.gics_sector, c.gics_sector_slug
            FROM universe_companies uc
            LEFT JOIN companies c ON uc.cd_cvm = c.cd_cvm
            WHERE uc.universe_id = :u_id
            ORDER BY uc.tier, c.company_name
        """

        # --- 2. Batch: incomplete checklist items ---
        checklist_query = """
            SELECT cc.cd_cvm, cc.item_key, cc.comments
            FROM coverage_checklists cc
            WHERE cc.universe_id = :u_id AND cc.is_completed = 0
        """

        # --- 3. Batch: market cap availability from DB cache ---
        mcap_query = """
            SELECT cd_cvm, MAX(market_cap) as market_cap
            FROM company_universe
            WHERE cd_cvm IN (
                SELECT cd_cvm FROM universe_companies WHERE universe_id = :u_id
            ) AND market_cap IS NOT NULL AND market_cap > 0
            GROUP BY cd_cvm
        """

        # --- 4. Batch: liquidity observation counts (last 30 days) ---
        liquidity_query = """
            SELECT cd_cvm, COUNT(DISTINCT date) as obs_count
            FROM market_history
            WHERE cd_cvm IN (
                SELECT cd_cvm FROM universe_companies WHERE universe_id = :u_id
            ) AND date >= date('now', '-30 days')
            AND volume IS NOT NULL AND volume > 0
            AND close IS NOT NULL AND close > 0
            GROUP BY cd_cvm
        """

        with self.engine.connect() as conn:
            companies = conn.execute(text(company_query), {"u_id": universe_id}).fetchall()
            checklists = conn.execute(text(checklist_query), {"u_id": universe_id}).fetchall()

            # market cap and liquidity may not exist in all installs
            try:
                mcap_rows = conn.execute(text(mcap_query), {"u_id": universe_id}).fetchall()
                mcap_set = {row[0] for row in mcap_rows if row[1]}
            except Exception:
                mcap_set = set()

            try:
                liq_rows = conn.execute(text(liquidity_query), {"u_id": universe_id}).fetchall()
                liq_map = {row[0]: row[1] for row in liq_rows}
            except Exception:
                liq_map = {}

        # --- 5. News workload batch (separate DB, local-only) ---
        news_map = self._get_news_workload_for_universe(universe_id)
        news_unavailable = isinstance(news_map, dict) and news_map.get("_unavailable") is True
        if news_unavailable:
            news_map = {}

        # --- 6. Build checklist task index: cd_cvm -> list of item_keys ---
        from collections import defaultdict  # noqa: PLC0415
        checklist_gaps: dict[int, list[str]] = defaultdict(list)
        for chk in checklists:
            checklist_gaps[chk[0]].append(chk[1])

        # --- 7. Derive tasks in memory ---
        tasks: list[dict[str, Any]] = []
        TIER_SEVERITY = {
            "must_cover": "high",
            "core": "high",
            "watchlist": "medium",
            "opportunistic": "medium",
            "excluded": "low",
            "inappropriate": "low",
        }

        for comp in companies:
            cd_cvm = comp[0]
            tier = comp[1]
            owner = comp[2]
            company_name = comp[3] or f"CVM {cd_cvm}"
            ticker_b3 = _clean_b3_ticker(comp[4]) or None
            gics_sector = comp[5]
            gics_sector_slug = comp[6]

            identifier = ticker_b3 or f"CVM {cd_cvm}"
            tier_sev = TIER_SEVERITY.get(tier, "low")

            def _task(reason: str, severity: str, task_type: str, suggested_action: str) -> dict[str, Any]:
                return {
                    "cd_cvm": cd_cvm,
                    "company_name": company_name,
                    "ticker_b3": ticker_b3,
                    "identifier": identifier,
                    "tier": tier,
                    "owner": owner,
                    "reason": reason,
                    "severity": severity,
                    "task_type": task_type,
                    "suggested_action": suggested_action,
                    "source": "derived",
                }

            # Blocked score (no market cap and no liquidity)
            has_mcap = cd_cvm in mcap_set
            liq_obs = liq_map.get(cd_cvm, 0)

            if not has_mcap:
                sev = "high" if tier_sev == "high" else "medium"
                tasks.append(_task(
                    reason="Market cap unavailable — score may be blocked or partial.",
                    severity=sev,
                    task_type="missing_market_cap",
                    suggested_action="Import or refresh market cap data for this company.",
                ))

            if liq_obs < MIN_LIQUIDITY_OBSERVATIONS:
                tasks.append(_task(
                    reason=f"Liquidity: only {liq_obs} trading day(s) in last 30 days (min: {MIN_LIQUIDITY_OBSERVATIONS}).",
                    severity="medium",
                    task_type="missing_liquidity",
                    suggested_action="Download market history or verify ticker mapping.",
                ))

            if not gics_sector or gics_sector == "Unknown" or not gics_sector_slug:
                tasks.append(_task(
                    reason="GICS sector not classified.",
                    severity="medium",
                    task_type="missing_gics",
                    suggested_action="Assign GICS sector via manual mapping or refresh company metadata.",
                ))

            if not owner:
                tasks.append(_task(
                    reason="No analyst owner assigned.",
                    severity="low",
                    task_type="unassigned_owner",
                    suggested_action="Assign an owner analyst to this company in the universe.",
                ))

            # Incomplete checklist items
            for item_key in checklist_gaps.get(cd_cvm, []):
                tasks.append({
                    "cd_cvm": cd_cvm,
                    "company_name": company_name,
                    "ticker_b3": ticker_b3,
                    "identifier": identifier,
                    "tier": tier,
                    "owner": owner,
                    "reason": f"Checklist item incomplete: {item_key.replace('_', ' ').title()}.",
                    "severity": "low",
                    "task_type": "incomplete_checklist",
                    "suggested_action": f"Complete required coverage task: {item_key}.",
                    "source": "checklist",
                })

            # News workload (local only, no network call)
            if not news_unavailable:
                news = news_map.get(cd_cvm, {})
                if not news.get("mapping_available"):
                    tasks.append(_task(
                        reason="Company not yet mapped to any local news articles.",
                        severity="low",
                        task_type="news_mapping_unavailable",
                        suggested_action="Review news mapping configuration for this company.",
                    ))
                elif news.get("article_count_30d", 0) == 0 and tier in ("must_cover", "core"):
                    tasks.append(_task(
                        reason="No local news articles in the last 30 days for a high-priority company.",
                        severity="medium",
                        task_type="news_gap",
                        suggested_action="Verify news sources cover this company or check RSS configuration.",
                    ))

        # If news DB was entirely unavailable, add a single banner task
        if news_unavailable and any(True for comp in companies):
            tasks.append({
                "cd_cvm": None,
                "company_name": None,
                "ticker_b3": None,
                "identifier": None,
                "tier": None,
                "owner": None,
                "reason": "News workload unavailable — local news database could not be read.",
                "severity": "low",
                "task_type": "news_db_unavailable",
                "suggested_action": "Check news database path and ensure news has been collected.",
                "source": "system",
            })

        # Sort: high severity first, then medium, then low; within severity by tier then company name
        severity_order = {"high": 0, "medium": 1, "low": 2}
        tasks.sort(key=lambda t: (
            severity_order.get(t.get("severity", "low"), 2),
            t.get("tier") or "",
            t.get("company_name") or "",
        ))
        return tasks

    # --- Capacity Planning ---

    def get_capacity_data(self, universe_id: str) -> dict[str, Any]:
        """
        Returns capacity estimates for a universe.

        Complexity multiplier uses canonical GICS slugs (gics_sector_slug column).
        If gics_sector_slug is NULL or not in COMPLEX_GICS_SLUGS, no multiplier is applied
        and the company is flagged as gics_unknown=True — uncertainty is exposed, never hidden.

        Performance note: For ~500 companies this is 3 SQL queries + in-memory aggregation.
        Expect ~50-150ms on typical SQLite.
        """
        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            return {}

        assumptions = universe.get("assumptions", {})
        tier_hours = assumptions.get("tier_hours", DEFAULT_TIER_HOURS)

        # Single query: get all companies with tier, owner, and GICS slug
        company_query = """
            SELECT uc.cd_cvm, uc.tier, uc.owner_analyst,
                   c.company_name, c.ticker_b3, c.gics_sector_slug, c.gics_sector
            FROM universe_companies uc
            LEFT JOIN companies c ON uc.cd_cvm = c.cd_cvm
            WHERE uc.universe_id = :u_id
        """

        with self.engine.connect() as conn:
            comp_rows = conn.execute(text(company_query), {"u_id": universe_id}).fetchall()

            scen_row = conn.execute(
                text("SELECT available_hours, tier_weights_json FROM coverage_capacity_scenarios WHERE universe_id = :u_id AND is_active = 1"),
                {"u_id": universe_id}
            ).fetchone()

        available_hours = scen_row[0] if scen_row else 1600.0
        custom_tier_hours = json.loads(scen_row[1]) if scen_row else tier_hours

        total_hours = 0.0
        tier_counts: dict[str, int] = {}
        tier_hours_breakdown: dict[str, float] = {}
        gics_unknown_companies: list[dict[str, Any]] = []
        by_owner: dict[str, dict[str, Any]] = {}
        top_hour_consumers: list[dict[str, Any]] = []

        for row in comp_rows:
            cd_cvm = row[0]
            tier = row[1]
            owner = row[2] or "Unassigned"
            company_name = row[3] or f"CVM {cd_cvm}"
            ticker_b3 = _clean_b3_ticker(row[4]) or None
            gics_slug = row[5]  # canonical slug from DB — may be None
            gics_sector = row[6]

            base_hours = custom_tier_hours.get(tier, DEFAULT_TIER_HOURS.get(tier, 5.0))

            # Complexity: use GICS slug, never Portuguese strings
            is_complex = gics_slug in COMPLEX_GICS_SLUGS if gics_slug else False
            gics_known = bool(gics_slug) and gics_slug != "unknown"

            mult = 1.0
            if is_complex:
                mult *= 1.2
            if tier in ("must_cover", "core"):
                mult *= 1.1

            item_hours = base_hours * mult
            total_hours += item_hours

            # Tier aggregation
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            tier_hours_breakdown[tier] = tier_hours_breakdown.get(tier, 0.0) + item_hours

            # Unknown GICS flag
            if not gics_known:
                gics_unknown_companies.append({
                    "cd_cvm": cd_cvm,
                    "company_name": company_name,
                    "ticker_b3": ticker_b3,
                    "tier": tier,
                    "gics_sector_slug": gics_slug,
                })

            # Per-owner aggregation
            if owner not in by_owner:
                by_owner[owner] = {"company_count": 0, "required_hours": 0.0, "tier_counts": {}}
            by_owner[owner]["company_count"] += 1
            by_owner[owner]["required_hours"] = round(by_owner[owner]["required_hours"] + item_hours, 1)
            by_owner[owner]["tier_counts"][tier] = by_owner[owner]["tier_counts"].get(tier, 0) + 1

            top_hour_consumers.append({
                "cd_cvm": cd_cvm,
                "company_name": company_name,
                "ticker_b3": ticker_b3,
                "tier": tier,
                "estimated_hours": round(item_hours, 1),
                "complexity_multiplier": round(mult, 2),
                "gics_sector": gics_sector,
                "gics_sector_slug": gics_slug,
                "gics_unknown": not gics_known,
                "owner": owner,
            })

        # Sort top consumers desc
        top_hour_consumers.sort(key=lambda x: -x["estimated_hours"])

        # Capacity warnings
        utilization_pct = round((total_hours / available_hours) * 100.0, 1) if available_hours > 0 else 0.0
        warnings: list[str] = []
        if utilization_pct > 100:
            warnings.append(f"Over capacity: {utilization_pct}% utilization — reduce universe scope or increase available hours.")
        elif utilization_pct > 90:
            warnings.append(f"Near capacity: {utilization_pct}% utilization.")
        if gics_unknown_companies:
            warnings.append(
                f"{len(gics_unknown_companies)} company(ies) have unknown GICS sector — capacity estimate excludes their complexity multiplier."
            )
        unassigned_count = by_owner.get("Unassigned", {}).get("company_count", 0)
        if unassigned_count > 0:
            warnings.append(f"{unassigned_count} company(ies) have no assigned analyst owner.")

        return {
            "universe_id": universe_id,
            "available_hours": available_hours,
            "required_hours": round(total_hours, 1),
            "capacity_utilization_pct": utilization_pct,
            "tier_counts": tier_counts,
            "tier_hours": {k: round(v, 1) for k, v in tier_hours_breakdown.items()},
            "tier_hours_assumptions": custom_tier_hours,
            "by_owner": by_owner,
            "gics_unknown_companies": gics_unknown_companies,
            "top_hour_consumers": top_hour_consumers[:20],
            "warnings": warnings,
        }

    def save_capacity_scenario(self, universe_id: str, available_hours: float, tier_hours: dict[str, float]) -> None:
        self._ensure_schema()
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE coverage_capacity_scenarios
                    SET available_hours = :avail, tier_weights_json = :weights
                    WHERE universe_id = :u_id AND is_active = 1
                    """
                ),
                {"u_id": universe_id, "avail": available_hours, "weights": json.dumps(tier_hours)}
            )

    # --- Decision History & Overrides ---

    def get_decision_history(self, universe_id: str, cd_cvm: int | None = None) -> list[dict[str, Any]]:
        self._ensure_schema()
        params = {"u_id": universe_id}
        
        query = """
            SELECT dh.id, dh.event_type, dh.previous_value, dh.new_value, dh.rationale, dh.timestamp, dh.author,
                   c.company_name, c.ticker_b3, dh.cd_cvm
            FROM coverage_decision_history dh
            LEFT JOIN companies c ON dh.cd_cvm = c.cd_cvm
            WHERE dh.universe_id = :u_id
        """
        
        if cd_cvm is not None:
            query += " AND dh.cd_cvm = :cd_cvm"
            params["cd_cvm"] = cd_cvm
            
        query += " ORDER BY dh.timestamp DESC"
        
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
            results = []
            for row in rows:
                item = dict(row._mapping)
                if not item.get("company_name"):
                    item["company_name"] = f"CVM {item.get('cd_cvm') or ''}"
                if not item.get("ticker_b3"):
                    from src.companies.identity import CompanyIdentityResolver
                    cd = item.get('cd_cvm')
                    identity = CompanyIdentityResolver().resolve(cd) if cd else None
                    item["ticker_b3"] = _clean_b3_ticker(identity.ticker_b3 if identity else None)
                results.append(item)
            return results

    def export_coverage_universe_excel(self, universe_id: str) -> bytes:  # noqa: PLR0912,PLR0915
        """
        Exports a 7-sheet audit-grade Coverage workbook.

        Sheets: Summary, Priorities, Priority Factors, Work Queue, Capacity, Decision History, Methodology.
        Rules:
        - No merged cells.
        - Freeze panes (row 1) on all table sheets.
        - Autofilter on all table sheets.
        - Blocked scores: separate Score Status column with 'Blocked'; numeric score columns show '-'.
        - Partial scores: Score Status = 'Partial'; numeric columns remain numeric.
        - Missing values: displayed as '-' (not 0 or blank).
        - Negatives in parentheses where applicable.
        - Workbook opens with openpyxl and Excel without repair.

        Performance note: For ~500 companies this calls calculate_priority_scores once
        (~300-800ms), get_work_queue once (~200-400ms), get_capacity_data once (~50-150ms),
        get_decision_history once (~50ms), then writes all sheets. Total ~1-2s.
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        import io

        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            raise ValueError("Universe not found")

        # ---- Styles ----
        font_family = "Segoe UI"
        f_title   = Font(name=font_family, size=14, bold=True, color="1F3864")
        f_section = Font(name=font_family, size=11, bold=True, color="1F3864")
        f_header  = Font(name=font_family, size=9,  bold=True, color="FFFFFF")
        f_body    = Font(name=font_family, size=9)
        f_bold    = Font(name=font_family, size=9,  bold=True)
        f_warn    = Font(name=font_family, size=9,  bold=True, color="C0392B")
        f_note    = Font(name=font_family, size=9,  italic=True, color="7F8C8D")

        fill_header  = PatternFill(start_color="1F3864", end_color="1F3864", fill_type="solid")
        fill_zebra   = PatternFill(start_color="F5F7FA", end_color="F5F7FA", fill_type="solid")
        fill_warn    = PatternFill(start_color="FDEDED", end_color="FDEDED", fill_type="solid")
        fill_partial = PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid")

        border_thin = Border(
            left=Side(style="thin", color="D0D7DE"),
            right=Side(style="thin", color="D0D7DE"),
            top=Side(style="thin", color="D0D7DE"),
            bottom=Side(style="thin", color="D0D7DE"),
        )

        NUM_FMT_SCORE  = "0.0"
        NUM_FMT_PCT    = "0.0%"
        NUM_FMT_HOURS  = '#,##0.0'
        NUM_FMT_INT    = "#,##0"
        DASH = "-"

        def _set_header_row(ws, headers: list[str], col_widths: list[int] | None = None) -> None:
            """Write a frozen, autofiltered header row."""
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_idx, value=h)
                cell.font = f_header
                cell.fill = fill_header
                cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=False)
                cell.border = border_thin
            ws.row_dimensions[1].height = 22
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            if col_widths:
                for i, w in enumerate(col_widths, 1):
                    ws.column_dimensions[get_column_letter(i)].width = w

        def _auto_width(ws, min_w: int = 10, max_w: int = 50) -> None:
            for col in ws.columns:
                max_len = max((len(str(c.value or "")) for c in col), default=0)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, min_w), max_w)

        def _body_cell(ws, row_idx: int, col_idx: int, value, fmt: str | None = None,
                       bold: bool = False, warn: bool = False, zebra: bool = False,
                       fill_override=None) -> None:
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = f_bold if bold else (f_warn if warn else f_body)
            cell.border = border_thin
            cell.alignment = Alignment(horizontal="left", vertical="center")
            if fill_override:
                cell.fill = fill_override
            elif warn:
                cell.fill = fill_warn
            elif zebra:
                cell.fill = fill_zebra
            if fmt:
                cell.number_format = fmt

        # ---- Fetch data once ----
        scores   = self.calculate_priority_scores(universe_id)
        cap      = self.get_capacity_data(universe_id)
        wq       = self.get_work_queue(universe_id)
        history  = self.get_decision_history(universe_id)

        # ========================================================
        # Sheet 1 — Summary
        # ========================================================
        wb = openpyxl.Workbook()
        ws_sum = wb.active
        ws_sum.title = "Summary"
        ws_sum.column_dimensions["A"].width = 30
        ws_sum.column_dimensions["B"].width = 40

        ws_sum.cell(row=1, column=1, value=f"Coverage Universe: {universe['name']}").font = f_title
        ws_sum.cell(row=2, column=1, value=f"Exported: {now_iso_seconds()[:10]}").font = f_note

        universe_rows = [
            ("Universe Name",   universe["name"]),
            ("Purpose",         universe.get("purpose") or DASH),
            ("Analysis Type",   universe.get("analysis_type", DASH)),
            ("Benchmark",       universe.get("benchmark") or DASH),
            ("Status",          universe.get("status", "").upper()),
            ("Created",         universe.get("created_at", "")[:10]),
            ("Last Updated",    universe.get("updated_at", "")[:10]),
        ]
        r = 4
        ws_sum.cell(row=r, column=1, value="Universe Details").font = f_section
        r += 1
        for k, v in universe_rows:
            ws_sum.cell(row=r, column=1, value=k).font = f_bold
            ws_sum.cell(row=r, column=2, value=v).font = f_body
            r += 1

        r += 1
        ws_sum.cell(row=r, column=1, value="Coverage Summary").font = f_section
        r += 1
        total_co = len(scores)
        blocked_co = sum(1 for s in scores if s.get("score_status") == "blocked")
        partial_co = sum(1 for s in scores if s.get("score_status") == "partial")
        scored_co  = sum(1 for s in scores if s.get("score_status") == "complete")
        summary_rows = [
            ("Total Companies",          total_co),
            ("Scored (Complete)",         scored_co),
            ("Scored (Partial)",          partial_co),
            ("Blocked (Insufficient Data)", blocked_co),
        ]
        for k, v in summary_rows:
            ws_sum.cell(row=r, column=1, value=k).font = f_bold
            ws_sum.cell(row=r, column=2, value=v).font = f_body
            r += 1

        r += 1
        ws_sum.cell(row=r, column=1, value="Capacity Summary").font = f_section
        r += 1
        cap_rows = [
            ("Available Analyst Hours (BRL)",   cap.get("available_hours", 0)),
            ("Required Workload Hours",           cap.get("required_hours", 0)),
            ("Capacity Utilization",              f"{cap.get('capacity_utilization_pct', 0):.1f}%"),
            ("GICS-Unknown Companies",            len(cap.get("gics_unknown_companies", []))),
        ]
        for k, v in cap_rows:
            ws_sum.cell(row=r, column=1, value=k).font = f_bold
            ws_sum.cell(row=r, column=2, value=v).font = f_body
            r += 1

        if cap.get("warnings"):
            r += 1
            ws_sum.cell(row=r, column=1, value="Capacity Warnings").font = f_section
            r += 1
            for w_text in cap["warnings"]:
                ws_sum.cell(row=r, column=1, value=w_text).font = f_warn
                ws_sum.cell(row=r, column=1).fill = fill_warn
                r += 1

        # ========================================================
        # Sheet 2 — Priorities
        # Numeric score columns stay numeric OR DASH. Score Status is a SEPARATE column.
        # Blocked/Partial appear only in the Score Status column.
        # ========================================================
        ws_prio = wb.create_sheet(title="Priorities")
        prio_headers = [
            "Ticker", "CVM Code", "Company Name", "GICS Sector", "Tier",
            "Owner", "Holding %",
            "Score Status",          # Blocked / Partial / Complete
            "Calculated Score",       # numeric or DASH (never 'Blocked')
            "Manual Override",        # numeric or DASH
            "Final Score",            # numeric or DASH
            "Checklist Done", "Checklist Total",
            "Missing Factors",
        ]
        _set_header_row(ws_prio, prio_headers)

        for row_idx, s in enumerate(scores, 2):
            status = s.get("score_status", "blocked")
            is_blocked = (status == "blocked")
            is_partial = (status == "partial")
            zebra = (row_idx % 2 == 0)
            fill_ov = fill_warn if is_blocked else (fill_partial if is_partial else None)

            # Numeric score values — NEVER 'Blocked' or 'Partial' in these cells
            calc_val   = s.get("calculated_score")  # None when blocked
            manual_val = s.get("manual_score_override")
            final_val  = s.get("final_score")       # None when blocked

            vals = [
                s.get("ticker_b3") or DASH,
                s.get("cd_cvm"),
                s.get("company_name") or DASH,
                s.get("gics_sector") or DASH,
                (s.get("tier") or "").upper(),
                s.get("owner_analyst") or "Unassigned",
                (s.get("holding_pct") or 0.0) / 100.0,  # stored as pct, display as fraction
                status.title(),                           # Score Status — textual label here
                calc_val,   # numeric or None → DASH below
                manual_val, # numeric or None
                final_val,  # numeric or None
                s.get("completed_checklist_count", 0),
                s.get("total_checklist_count", 0),
                ", ".join(s.get("missing_factors", [])) or DASH,
            ]
            fmts = [
                None, None, None, None, None, None,
                NUM_FMT_PCT,
                None,
                NUM_FMT_SCORE, NUM_FMT_SCORE, NUM_FMT_SCORE,
                NUM_FMT_INT, NUM_FMT_INT,
                None,
            ]

            for col_idx, (v, fmt) in enumerate(zip(vals, fmts), 1):
                # Replace None numeric score with DASH string
                display_v = v
                if v is None and col_idx in (9, 10, 11):  # score columns
                    display_v = DASH
                    fmt = None
                _body_cell(ws_prio, row_idx, col_idx, display_v, fmt=fmt,
                           bold=(col_idx == 1), zebra=zebra, fill_override=fill_ov)

        _auto_width(ws_prio)

        # ========================================================
        # Sheet 3 — Priority Factors
        # One row per company × factor. No blocked/partial in score cols.
        # ========================================================
        ws_fac = wb.create_sheet(title="Priority Factors")
        fac_headers = [
            "Ticker", "CVM Code", "Company Name", "Tier",
            "Factor", "Original Weight", "Effective Weight",
            "Raw Value", "Factor Score", "Contribution",
            "Missing", "Disabled",
        ]
        _set_header_row(ws_fac, fac_headers)

        fac_row = 2
        FACTOR_ORDER = ["market_cap", "volume", "holding_pct", "sector_complexity"]
        for s in scores:
            details = s.get("factor_details", {})
            for factor_key in FACTOR_ORDER:
                fd = details.get(factor_key)
                if fd is None:
                    continue
                zebra = (fac_row % 2 == 0)
                raw_v = fd.get("raw_value")
                score_v = fd.get("score")  # numeric or None
                fac_vals = [
                    s.get("ticker_b3") or DASH,
                    s.get("cd_cvm"),
                    s.get("company_name") or DASH,
                    (s.get("tier") or "").upper(),
                    fd.get("name", factor_key),
                    fd.get("original_weight"),
                    fd.get("effective_weight"),
                    str(round(raw_v, 2)) if isinstance(raw_v, float) else (str(raw_v) if raw_v is not None else DASH),
                    score_v,
                    fd.get("contribution"),
                    "Yes" if fd.get("missing") else "No",
                    "Yes" if fd.get("original_weight", 1) == 0 else "No",
                ]
                fac_fmts = [
                    None, None, None, None, None,
                    "0.00", "0.00",  # weights
                    None,            # raw value (string)
                    NUM_FMT_SCORE,   # factor score
                    NUM_FMT_SCORE,   # contribution
                    None, None,
                ]
                for col_idx, (v, fmt) in enumerate(zip(fac_vals, fac_fmts), 1):
                    display_v = DASH if (v is None and col_idx in (9, 10)) else v
                    fmt_use = fmt if display_v != DASH else None
                    _body_cell(ws_fac, fac_row, col_idx, display_v, fmt=fmt_use, zebra=zebra)
                fac_row += 1

        _auto_width(ws_fac)

        # ========================================================
        # Sheet 4 — Work Queue
        # ========================================================
        ws_wq = wb.create_sheet(title="Work Queue")
        wq_headers = [
            "Severity", "Task Type", "Ticker", "CVM Code", "Company Name",
            "Tier", "Owner", "Reason", "Suggested Action", "Source",
        ]
        _set_header_row(ws_wq, wq_headers)

        SEV_FILL = {"high": fill_warn, "medium": fill_partial, "low": None}
        for row_idx, task in enumerate(wq, 2):
            sev = task.get("severity", "low")
            zebra = (row_idx % 2 == 0)
            fill_ov = SEV_FILL.get(sev)
            wq_vals = [
                (sev or "").title(),
                task.get("task_type") or DASH,
                task.get("ticker_b3") or DASH,
                task.get("cd_cvm") or DASH,
                task.get("company_name") or DASH,
                (task.get("tier") or "").upper() or DASH,
                task.get("owner") or "Unassigned",
                task.get("reason") or DASH,
                task.get("suggested_action") or DASH,
                task.get("source") or DASH,
            ]
            for col_idx, v in enumerate(wq_vals, 1):
                _body_cell(ws_wq, row_idx, col_idx, v, bold=(col_idx == 1),
                           zebra=zebra, fill_override=fill_ov)

        _auto_width(ws_wq)

        # ========================================================
        # Sheet 5 — Capacity
        # ========================================================
        ws_cap = wb.create_sheet(title="Capacity")
        ws_cap.column_dimensions["A"].width = 28
        ws_cap.column_dimensions["B"].width = 20

        ws_cap.cell(row=1, column=1, value="Capacity Planning").font = f_title
        r = 3
        ws_cap.cell(row=r, column=1, value="Scenario Summary").font = f_section
        r += 1
        cap_meta = [
            ("Available Analyst Hours",  cap.get("available_hours")),
            ("Required Workload Hours",   cap.get("required_hours")),
            ("Capacity Utilization (%)",  cap.get("capacity_utilization_pct")),
        ]
        for k, v in cap_meta:
            ws_cap.cell(row=r, column=1, value=k).font = f_bold
            c = ws_cap.cell(row=r, column=2, value=v)
            c.font = f_body
            c.number_format = NUM_FMT_HOURS
            r += 1

        r += 1
        ws_cap.cell(row=r, column=1, value="By Tier").font = f_section
        r += 1
        ws_cap.cell(row=r, column=1, value="Tier").font = f_bold
        ws_cap.cell(row=r, column=2, value="# Companies").font = f_bold
        ws_cap.cell(row=r, column=3, value="Est. Hours").font = f_bold
        ws_cap.cell(row=r, column=4, value="Hours / Company Assumption").font = f_bold
        r += 1
        tier_assumptions = cap.get("tier_hours_assumptions", {})
        for tier, count in sorted(cap.get("tier_counts", {}).items()):
            ws_cap.cell(row=r, column=1, value=tier.upper()).font = f_body
            ws_cap.cell(row=r, column=2, value=count).font = f_body
            hrs = cap.get("tier_hours", {}).get(tier, 0)
            ws_cap.cell(row=r, column=3, value=hrs).font = f_body
            ws_cap.cell(row=r, column=3).number_format = NUM_FMT_HOURS
            ws_cap.cell(row=r, column=4, value=tier_assumptions.get(tier, DASH)).font = f_body
            r += 1

        r += 1
        ws_cap.cell(row=r, column=1, value="By Owner").font = f_section
        r += 1
        ws_cap.cell(row=r, column=1, value="Owner").font = f_bold
        ws_cap.cell(row=r, column=2, value="# Companies").font = f_bold
        ws_cap.cell(row=r, column=3, value="Est. Hours").font = f_bold
        r += 1
        for owner_name, od in sorted(cap.get("by_owner", {}).items()):
            ws_cap.cell(row=r, column=1, value=owner_name).font = f_body
            ws_cap.cell(row=r, column=2, value=od["company_count"]).font = f_body
            ws_cap.cell(row=r, column=3, value=od["required_hours"]).font = f_body
            ws_cap.cell(row=r, column=3).number_format = NUM_FMT_HOURS
            r += 1

        gics_unknown = cap.get("gics_unknown_companies", [])
        if gics_unknown:
            r += 1
            ws_cap.cell(row=r, column=1, value=f"GICS Unknown ({len(gics_unknown)} co.)").font = f_warn
            r += 1
            ws_cap.cell(row=r, column=1, value="Ticker").font = f_bold
            ws_cap.cell(row=r, column=2, value="Company").font = f_bold
            ws_cap.cell(row=r, column=3, value="Tier").font = f_bold
            r += 1
            for gc in gics_unknown[:30]:
                ws_cap.cell(row=r, column=1, value=gc.get("ticker_b3") or DASH).font = f_body
                ws_cap.cell(row=r, column=2, value=gc.get("company_name") or DASH).font = f_body
                ws_cap.cell(row=r, column=3, value=(gc.get("tier") or "").upper()).font = f_body
                r += 1

        for cap_warning in cap.get("warnings", []):
            r += 1
            c = ws_cap.cell(row=r, column=1, value=f"⚠ {cap_warning}")
            c.font = f_warn
            c.fill = fill_warn

        # ========================================================
        # Sheet 6 — Decision History
        # ========================================================
        ws_log = wb.create_sheet(title="Decision History")
        log_headers = [
            "Timestamp (UTC)", "Ticker", "CVM Code", "Company Name",
            "Event Type", "Previous Value", "New Value", "Rationale",
        ]
        _set_header_row(ws_log, log_headers)

        for row_idx, h in enumerate(history, 2):
            ts_raw = h.get("timestamp") or ""
            ts_display = ts_raw[:16].replace("T", " ") if ts_raw else DASH
            log_vals = [
                ts_display,
                h.get("ticker_b3") or DASH,
                h.get("cd_cvm"),
                h.get("company_name") or DASH,
                (h.get("event_type") or "").upper(),
                str(h.get("previous_value") or DASH),
                str(h.get("new_value") or DASH),
                h.get("rationale") or DASH,
            ]
            zebra = (row_idx % 2 == 0)
            for col_idx, v in enumerate(log_vals, 1):
                _body_cell(ws_log, row_idx, col_idx, v, bold=(col_idx in (2, 5)), zebra=zebra)

        _auto_width(ws_log)

        # ========================================================
        # Sheet 7 — Methodology
        # Plain text reference; no tables/autofilter needed.
        # ========================================================
        ws_meth = wb.create_sheet(title="Methodology")
        ws_meth.column_dimensions["A"].width = 100

        meth_lines = [
            ("Coverage Universe — Methodology & Caveats", f_title),
            ("", f_body),
            ("SCORING", f_section),
            ("Priority scores are computed per company using a weighted factor model (0–100 scale).", f_body),
            ("Default weights: Market Cap 30%, Volume 30%, Holdings 20%, Sector Complexity 20%.", f_body),
            ("Weights are customizable per universe. Disabled factors (weight=0) are excluded from the denominator.", f_body),
            ("Market Cap score: log10(cap_brl) normalized between 10M and 50B BRL.", f_body),
            ("Volume score: log10(avg_daily_traded_brl) normalized between 10k and 100M BRL (last 30 days).", f_body),
            ("Holdings score: raw portfolio weight (0–100%), capped at 100.", f_body),
            ("Sector Complexity score: 100 if GICS slug is utilities/financials/energy, else 50.", f_body),
            ("", f_body),
            ("BLOCKED STATUS", f_section),
            ("A company is Blocked when: total active weight is 0, OR available factor weight < 50%, OR", f_body),
            ("only sector_complexity is available. Blocked companies appear in this workbook with Score Status = 'Blocked'", f_body),
            ("and no numeric score in calculated/final columns. Blocked scores are NOT exported as 0.0.", f_body),
            ("", f_body),
            ("PARTIAL STATUS", f_section),
            ("A company is Partial when it has enough factors to score but at least one factor is missing.", f_body),
            ("Partial scores are numeric. The missing factor(s) are listed in the Missing Factors column.", f_body),
            ("", f_body),
            ("CAPACITY", f_section),
            ("Capacity is estimated as: SUM(base_tier_hours * complexity_mult * priority_mult) per company.", f_body),
            ("Complexity multiplier (1.2×) applies ONLY when gics_sector_slug is 'utilities', 'financials', or 'energy'.", f_body),
            ("If GICS slug is unknown/missing, NO multiplier is applied and company is flagged as GICS-Unknown.", f_body),
            ("Priority multiplier (1.1×) applies for must_cover and core tiers.", f_body),
            ("Capacity is a planning estimate, not a billing or contractual figure.", f_body),
            ("", f_body),
            ("MARKET CAP SOURCE PRIORITY", f_section),
            ("official_b3 > official_cvm > imported_official > yahoo_finance > imported_user_data > unknown", f_body),
            ("Market cap conflicts (same source+date, different values) are exposed as missing — not silently resolved.", f_body),
            ("", f_body),
            ("NEWS WORKLOAD", f_section),
            ("News workload is derived from local cached news only. No live network calls are made.", f_body),
            ("Source: news_article_companies table in news.db, joined to news_articles.published_at.", f_body),
            ("If news database is unavailable or company-to-article mapping is absent, this is shown explicitly.", f_body),
            ("", f_body),
            ("DATA CAVEATS", f_section),
            ("Market cap from Yahoo Finance is unofficial and may lag or differ from B3 official data.", f_body),
            ("Volume/liquidity data depends on market_history table being populated via refresh.", f_body),
            ("GICS classification is manually curated where automatic detection fails.", f_body),
            ("", f_body),
            ("PLANNED (NOT YET IMPLEMENTED)", f_section),
            ("- Stock correlation matrix", f_note),
            ("- Peers / value-chain graph", f_note),
            ("- Supplier-customer network", f_note),
            ("- ONS/ANEEL/CCEE operational integration", f_note),
            ("- Full analyst user management / authentication", f_note),
        ]
        for mrow, (line, font) in enumerate(meth_lines, 1):
            c = ws_meth.cell(row=mrow, column=1, value=line)
            c.font = font
            c.alignment = Alignment(wrap_text=False)

        # ---- Final: save ----
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
