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

COMPLEX_SECTORS = ["Utilidade Pública", "Intermediários Financeiros", "Energia Elétrica", "Petróleo, Gás e Biocombustíveis"]


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
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM coverage_universes WHERE id = :id"), {"id": universe_id})

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

    # --- Prioritization Scoring ---

    def calculate_priority_scores(self, universe_id: str) -> list[dict[str, Any]]:
        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            return []

        weights = universe.get("assumptions", {}).get("weights", DEFAULT_WEIGHTS)
        
        query = """
            SELECT uc.cd_cvm, uc.tier, uc.manual_score_override, uc.owner_analyst, uc.holding_pct,
                   c.company_name, c.ticker_b3, c.setor_analitico, c.gics_sector,
                   (SELECT COUNT(*) FROM coverage_checklists WHERE universe_id = uc.universe_id AND cd_cvm = uc.cd_cvm AND is_completed = 1) as completed_checklist_count,
                   (SELECT COUNT(*) FROM coverage_checklists WHERE universe_id = uc.universe_id AND cd_cvm = uc.cd_cvm) as total_checklist_count
            FROM universe_companies uc
            LEFT JOIN companies c ON uc.cd_cvm = c.cd_cvm
            WHERE uc.universe_id = :u_id
        """

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
                    raw_ticker = (identity.ticker_b3 if identity else None) or str(cd_cvm)
                    if raw_ticker.endswith(".SA"):
                        raw_ticker = raw_ticker[:-3]
                    comp_data["ticker_b3"] = raw_ticker
                if not comp_data.get("setor_analitico"):
                    comp_data["setor_analitico"] = "Unknown"
                if not comp_data.get("gics_sector"):
                    comp_data["gics_sector"] = "Unknown"

                # Retrieve volume and price history
                volume_query = """
                    SELECT AVG(volume) as avg_vol, MAX(adjusted_close) as last_close
                    FROM market_history
                    WHERE cd_cvm = :cd_cvm AND date >= date('now', '-30 days')
                """
                vol_row = conn.execute(text(volume_query), {"cd_cvm": cd_cvm}).fetchone()
                avg_vol = vol_row[0] if vol_row and vol_row[0] is not None else 0.0
                last_price = vol_row[1] if vol_row and vol_row[1] is not None else 0.0
                
                # Fetch market cap from database if available
                mkt_cap_query = "SELECT market_cap FROM company_universe WHERE cd_cvm = :cd_cvm LIMIT 1"
                mcap_row = conn.execute(text(mkt_cap_query), {"cd_cvm": cd_cvm}).fetchone()
                mkt_cap = mcap_row[0] if mcap_row and mcap_row[0] is not None else 0.0
                
                if mkt_cap == 0.0 and last_price > 0:
                    mkt_cap = last_price * 10_000_000 # Dummy fallback

                # Calculate individual scores
                cap_score = self._calc_log_score(mkt_cap, 7.0, 11.7) # 10M to 50B
                vol_score = self._calc_log_score(avg_vol, 4.0, 8.0) # 10k to 100M
                holding_score = min(max(comp_data["holding_pct"] or 0.0, 0.0), 100.0)
                
                # Sector relevance
                sector_score = 100.0 if comp_data["gics_sector"] in COMPLEX_SECTORS else 50.0

                w_cap = weights.get("market_cap_weight", 0.3)
                w_vol = weights.get("volume_weight", 0.3)
                w_hold = weights.get("holding_weight", 0.2)
                w_sect = weights.get("sector_weight", 0.2)

                calc_score = (
                    (cap_score * w_cap) +
                    (vol_score * w_vol) +
                    (holding_score * w_hold) +
                    (sector_score * w_sect)
                )

                override = comp_data["manual_score_override"] or 0.0
                final_score = round(min(max(calc_score + override, 0.0), 100.0), 1)

                # Lookup last snapshot score for delta calculation
                snapshot_row = conn.execute(
                    text(
                        """
                        SELECT new_value FROM coverage_decision_history
                        WHERE universe_id = :u_id AND cd_cvm = :cd_cvm AND event_type = 'score_snapshot'
                        ORDER BY timestamp DESC LIMIT 1
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm},
                ).fetchone()

                score_delta: float | None = None
                score_baseline: float | None = None
                if snapshot_row and snapshot_row[0] is not None:
                    try:
                        score_baseline = float(snapshot_row[0])
                        score_delta = round(final_score - score_baseline, 1)
                    except (TypeError, ValueError):
                        pass

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
                next_pending_item: str | None = next_action_row[0] if next_action_row else None

                comp_data.update({
                    "market_cap": mkt_cap,
                    "avg_volume": avg_vol,
                    "cap_score": round(cap_score, 1),
                    "vol_score": round(vol_score, 1),
                    "holding_score": round(holding_score, 1),
                    "sector_score": round(sector_score, 1),
                    "calculated_score": round(calc_score, 1),
                    "final_score": final_score,
                    "score_delta": score_delta,
                    "score_baseline": score_baseline,
                    "next_pending_item": next_pending_item,
                })
                results.append(comp_data)

            results.sort(key=lambda x: x["final_score"], reverse=True)
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

            # Snapshot the current calculated score so next load can show delta
            # We recalculate current final_score inline to avoid a recursive call
            uc_row = conn.execute(
                text("SELECT holding_pct, manual_score_override FROM universe_companies WHERE universe_id = :u_id AND cd_cvm = :cd_cvm"),
                {"u_id": universe_id, "cd_cvm": cd_cvm}
            ).fetchone()
            if uc_row:
                override_snap = float(override) if override is not None else 0.0
                conn.execute(
                    text(
                        """
                        INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                        VALUES (:u_id, :cd_cvm, 'score_snapshot', NULL, :score, 'auto_snapshot', :timestamp)
                        """
                    ),
                    {"u_id": universe_id, "cd_cvm": cd_cvm, "score": str(override_snap), "timestamp": now}
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

            # Score snapshot after checklist change so next load can compute delta
            conn.execute(
                text(
                    """
                    INSERT INTO coverage_decision_history (universe_id, cd_cvm, event_type, previous_value, new_value, rationale, timestamp)
                    VALUES (:u_id, :cd_cvm, 'score_snapshot', NULL, 'checklist_action', 'auto_snapshot', :timestamp)
                    """
                ),
                {"u_id": universe_id, "cd_cvm": cd_cvm, "timestamp": now}
            )

    def get_work_queue(self, universe_id: str) -> list[dict[str, Any]]:
        self._ensure_schema()
        query = """
            SELECT cc.cd_cvm, cc.item_key, cc.comments, uc.tier, c.company_name, c.ticker_b3
            FROM coverage_checklists cc
            JOIN universe_companies uc ON cc.universe_id = uc.universe_id AND cc.cd_cvm = uc.cd_cvm
            LEFT JOIN companies c ON cc.cd_cvm = c.cd_cvm
            WHERE cc.universe_id = :u_id AND cc.is_completed = 0
            ORDER BY uc.tier, c.company_name
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(query), {"u_id": universe_id}).fetchall()
            
            tasks = []
            for row in rows:
                item = dict(row._mapping)
                item_key = item["item_key"]
                
                if not item.get("company_name"):
                    item["company_name"] = f"CVM {item['cd_cvm']}"
                if not item.get("ticker_b3"):
                    from src.companies.identity import CompanyIdentityResolver
                    identity = CompanyIdentityResolver().resolve(item['cd_cvm'])
                    raw_t = (identity.ticker_b3 if identity else None) or str(item['cd_cvm'])
                    if raw_t.endswith(".SA"):
                        raw_t = raw_t[:-3]
                    item["ticker_b3"] = raw_t
                
                title = f"Complete required task: {item_key.replace('_', ' ').title()}"
                desc = f"Company {item['company_name']} ({item['ticker_b3']}) in tier '{item['tier']}' is missing: {item_key}."
                
                item.update({
                    "title": title,
                    "description": desc,
                })
                tasks.append(item)
            return tasks

    # --- Capacity Planning ---

    def get_capacity_data(self, universe_id: str) -> dict[str, Any]:
        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            return {}

        assumptions = universe.get("assumptions", {})
        tier_hours = assumptions.get("tier_hours", DEFAULT_TIER_HOURS)

        query = """
            SELECT tier, COUNT(*) as count
            FROM universe_companies
            WHERE universe_id = :u_id
            GROUP BY tier
        """
        
        complexity_query = """
            SELECT uc.tier, c.gics_sector
            FROM universe_companies uc
            LEFT JOIN companies c ON uc.cd_cvm = c.cd_cvm
            WHERE uc.universe_id = :u_id
        """

        with self.engine.connect() as conn:
            counts_rows = conn.execute(text(query), {"u_id": universe_id}).fetchall()
            counts = {row[0]: row[1] for row in counts_rows}
            
            comp_rows = conn.execute(text(complexity_query), {"u_id": universe_id}).fetchall()
            
            scen_row = conn.execute(
                text("SELECT available_hours, tier_weights_json FROM coverage_capacity_scenarios WHERE universe_id = :u_id AND is_active = 1"),
                {"u_id": universe_id}
            ).fetchone()
            
            available_hours = scen_row[0] if scen_row else 1600.0
            custom_tier_hours = json.loads(scen_row[1]) if scen_row else tier_hours

            total_hours = 0.0
            tier_hours_breakdown = {}
            for row in comp_rows:
                tier = row[0]
                sector = row[1]
                
                base_hours = custom_tier_hours.get(tier, DEFAULT_TIER_HOURS.get(tier, 5.0))
                
                mult = 1.0
                if sector in COMPLEX_SECTORS:
                    mult *= 1.2
                if tier in ("must_cover", "core"):
                    mult *= 1.1
                
                item_hours = base_hours * mult
                total_hours += item_hours
                
                tier_hours_breakdown[tier] = tier_hours_breakdown.get(tier, 0.0) + item_hours

            return {
                "universe_id": universe_id,
                "available_hours": available_hours,
                "required_hours": round(total_hours, 1),
                "capacity_utilization_pct": round((total_hours / available_hours) * 100.0, 1) if available_hours > 0 else 0,
                "tier_counts": counts,
                "tier_hours": tier_hours_breakdown,
                "tier_hours_assumptions": custom_tier_hours,
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
                    raw_t = (identity.ticker_b3 if identity else None) or str(cd or '')
                    if raw_t.endswith(".SA"):
                        raw_t = raw_t[:-3]
                    item["ticker_b3"] = raw_t
                results.append(item)
            return results

    def export_coverage_universe_excel(self, universe_id: str) -> bytes:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        import io

        self._ensure_schema()
        universe = self.get_universe(universe_id)
        if not universe:
            raise ValueError("Universe not found")

        wb = openpyxl.Workbook()
        
        # Style guidelines
        font_family = "Segoe UI"
        font_title = Font(name=font_family, size=16, bold=True, color="1F497D")
        font_section = Font(name=font_family, size=12, bold=True, color="1F497D")
        font_header = Font(name=font_family, size=10, bold=True, color="FFFFFF")
        font_body = Font(name=font_family, size=10)
        font_bold = Font(name=font_family, size=10, bold=True)
        
        fill_header = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        fill_zebra = PatternFill(start_color="F2F5F8", end_color="F2F5F8", fill_type="solid")
        
        border_thin = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )

        # 1. Summary Sheet
        ws_sum = wb.active
        ws_sum.title = "Summary"
        ws_sum.views.sheetView[0].showGridLines = True
        
        ws_sum.cell(row=1, column=1, value="COVERAGE UNIVERSE SUMMARY").font = font_title
        ws_sum.cell(row=3, column=1, value="Universe Details").font = font_section
        
        details = [
            ("Universe Name", universe["name"]),
            ("Purpose", universe["purpose"]),
            ("Analysis Type", universe["analysis_type"]),
            ("Benchmark", universe["benchmark"]),
            ("Status", universe["status"].upper()),
            ("Created Date", universe["created_at"][:10]),
            ("Last Review Date", universe["updated_at"][:10]),
        ]
        
        r = 5
        for k, v in details:
            cell_k = ws_sum.cell(row=r, column=1, value=k)
            cell_k.font = font_bold
            cell_k.border = border_thin
            cell_v = ws_sum.cell(row=r, column=2, value=v)
            cell_v.font = font_body
            cell_v.border = border_thin
            r += 1

        # Add Capacity Info
        r += 2
        ws_sum.cell(row=r, column=1, value="Capacity Summary").font = font_section
        r += 2
        cap = self.get_capacity_data(universe_id)
        cap_details = [
            ("Available Analyst Hours", cap.get("available_hours", 0)),
            ("Required Workload Hours", cap.get("required_hours", 0)),
            ("Capacity Utilization", f"{cap.get('capacity_utilization_pct', 0)}%"),
        ]
        for k, v in cap_details:
            cell_k = ws_sum.cell(row=r, column=1, value=k)
            cell_k.font = font_bold
            cell_k.border = border_thin
            cell_v = ws_sum.cell(row=r, column=2, value=v)
            cell_v.font = font_body
            cell_v.border = border_thin
            r += 1

        # 2. Priorities Sheet
        ws_prio = wb.create_sheet(title="Priorities & Rankings")
        ws_prio.views.sheetView[0].showGridLines = True
        
        headers = ["Ticker", "Company Name", "Sector", "Tier", "Holding %", "Calculated Score", "Manual Override", "Final Score", "Checklist Done", "Checklist Total"]
        for col_idx, h in enumerate(headers, 1):
            cell = ws_prio.cell(row=1, column=col_idx, value=h)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center" if col_idx > 4 else "left")
            ws_prio.row_dimensions[1].height = 25
            
        scores = self.calculate_priority_scores(universe_id)
        for row_idx, s in enumerate(scores, 2):
            ws_prio.cell(row=row_idx, column=1, value=s.get("ticker_b3") or f"CVM:{s['cd_cvm']}").font = font_bold
            ws_prio.cell(row=row_idx, column=2, value=s.get("company_name")).font = font_body
            ws_prio.cell(row=row_idx, column=3, value=s.get("gics_sector")).font = font_body
            ws_prio.cell(row=row_idx, column=4, value=s.get("tier").upper()).font = font_body
            ws_prio.cell(row=row_idx, column=5, value=s.get("holding_pct", 0.0) / 100.0).number_format = '0.0%'
            ws_prio.cell(row=row_idx, column=6, value=s.get("calculated_score", 0.0)).number_format = '0.0'
            ws_prio.cell(row=row_idx, column=7, value=s.get("manual_score_override")).number_format = '0.0'
            ws_prio.cell(row=row_idx, column=8, value=s.get("final_score", 0.0)).number_format = '0.0'
            ws_prio.cell(row=row_idx, column=9, value=s.get("completed_checklist_count", 0)).number_format = '#,##0'
            ws_prio.cell(row=row_idx, column=10, value=s.get("total_checklist_count", 0)).number_format = '#,##0'
            
            # Formatting and borders
            for col_idx in range(1, 11):
                c = ws_prio.cell(row=row_idx, column=col_idx)
                c.border = border_thin
                if row_idx % 2 == 0:
                    c.fill = fill_zebra
                if col_idx > 4:
                    c.alignment = Alignment(horizontal="right")
            ws_prio.row_dimensions[row_idx].height = 20

        # Auto-adjust column widths
        for ws in (ws_sum, ws_prio):
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # 3. Decision Log Sheet
        ws_log = wb.create_sheet(title="Decision History")
        ws_log.views.sheetView[0].showGridLines = True
        log_headers = ["Timestamp", "Ticker", "Company Name", "Event Type", "Prev Value", "New Value", "Rationale"]
        for col_idx, h in enumerate(log_headers, 1):
            cell = ws_log.cell(row=1, column=col_idx, value=h)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="left")
            
        history = self.get_decision_history(universe_id)
        for row_idx, h in enumerate(history, 2):
            ws_log.cell(row=row_idx, column=1, value=h.get("timestamp")[:16].replace("T", " ")).font = font_body
            ws_log.cell(row=row_idx, column=2, value=h.get("ticker_b3") or "N/A").font = font_bold
            ws_log.cell(row=row_idx, column=3, value=h.get("company_name")).font = font_body
            ws_log.cell(row=row_idx, column=4, value=h.get("event_type").upper()).font = font_body
            ws_log.cell(row=row_idx, column=5, value=str(h.get("previous_value") or '')).font = font_body
            ws_log.cell(row=row_idx, column=6, value=str(h.get("new_value") or '')).font = font_body
            ws_log.cell(row=row_idx, column=7, value=h.get("rationale")).font = font_body
            
            for col_idx in range(1, 8):
                c = ws_log.cell(row=row_idx, column=col_idx)
                c.border = border_thin
                if row_idx % 2 == 0:
                    c.fill = fill_zebra
            ws_log.row_dimensions[row_idx].height = 20

        # Auto-adjust column widths for log
        for col in ws_log.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws_log.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)

        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
