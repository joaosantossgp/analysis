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

MIN_LIQUIDITY_OBSERVATIONS = 5


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
                    raw_ticker = (identity.ticker_b3 if identity else None) or str(cd_cvm)
                    if raw_ticker.endswith(".SA"):
                        raw_ticker = raw_ticker[:-3]
                    comp_data["ticker_b3"] = raw_ticker
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
