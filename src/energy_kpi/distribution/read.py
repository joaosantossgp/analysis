"""Read service for the electricity distribution analytics domain."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import text

from src.energy_kpi.schema import get_energy_kpi_engine
from src.platform.settings import AppSettings

logger = logging.getLogger(__name__)


class DistributionReadService:
    """Read service for querying distribution analytics from SQLite."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def _engine(self):
        return get_energy_kpi_engine(self.settings)

    def get_distributors(
        self,
        *,
        search: str | None = None,
        economic_group_id: str | None = None,
        uf: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query the list of distributors with their current economic group details."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        query = """
            SELECT
                d.distributor_id,
                d.canonical_name,
                d.trade_name,
                d.normalized_cnpj,
                d.agent_code,
                d.concession_type,
                d.primary_uf,
                d.status,
                g.economic_group_id,
                g.group_name,
                c.cd_cvm,
                c.company_name,
                c.ticker_b3
            FROM distribution_distributors d
            LEFT JOIN distribution_ownership_history h
              ON d.distributor_id = h.distributor_id
             AND h.valid_from <= :today
             AND h.valid_to >= :today
             AND h.operational_consolidation_flag = 1
            LEFT JOIN distribution_economic_groups g
              ON h.economic_group_id = g.economic_group_id
            LEFT JOIN distribution_listed_companies c
              ON h.cd_cvm = c.cd_cvm
            WHERE 1=1
        """
        
        params: dict[str, Any] = {"today": today}
        
        if search:
            query += """ AND (
                d.canonical_name LIKE :search 
                OR d.trade_name LIKE :search 
                OR d.normalized_cnpj LIKE :search
            )"""
            params["search"] = f"%{search}%"
            
        if economic_group_id:
            if economic_group_id == "unmapped":
                query += " AND g.economic_group_id IS NULL"
            else:
                query += " AND g.economic_group_id = :group_id"
                params["group_id"] = economic_group_id
                
        if uf:
            query += " AND d.primary_uf = :uf"
            params["uf"] = uf

        query += " ORDER BY d.canonical_name"

        print("EXECUTING QUERY:", query)
        print("WITH PARAMS:", params)

        with self._engine().connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
            
        return [
            {
                "distributor_id": r[0],
                "canonical_name": r[1],
                "trade_name": r[2],
                "normalized_cnpj": r[3],
                "agent_code": r[4],
                "concession_type": r[5],
                "primary_uf": r[6],
                "status": r[7],
                "economic_group_id": r[8],
                "group_name": r[9],
                "cd_cvm": r[10],
                "company_name": r[11],
                "ticker_b3": r[12]
            }
            for r in rows
        ]

    def get_distributor_detail(self, distributor_id: str) -> dict[str, Any] | None:
        """Query single distributor metadata, current status, and full ownership history."""
        # 1. Base distributor record
        dist_query = """
            SELECT
                distributor_id, canonical_name, current_legal_name, trade_name,
                normalized_cnpj, agent_code, distributor_code, concession_type,
                primary_uf, service_area, status
            FROM distribution_distributors
            WHERE distributor_id = :id
        """
        with self._engine().connect() as conn:
            dist_row = conn.execute(text(dist_query), {"id": distributor_id}).fetchone()
            if not dist_row:
                return None
                
            # 2. Ownership history list
            history_query = """
                SELECT
                    h.ownership_id,
                    h.valid_from,
                    h.valid_to,
                    h.control_status,
                    h.ownership_percentage,
                    h.operational_consolidation_flag,
                    g.economic_group_id,
                    g.group_name,
                    c.cd_cvm,
                    c.company_name,
                    c.ticker_b3
                FROM distribution_ownership_history h
                LEFT JOIN distribution_economic_groups g
                  ON h.economic_group_id = g.economic_group_id
                LEFT JOIN distribution_listed_companies c
                  ON h.cd_cvm = c.cd_cvm
                WHERE h.distributor_id = :id
                ORDER BY h.valid_from DESC
            """
            history_rows = conn.execute(text(history_query), {"id": distributor_id}).fetchall()
            
            # 3. Available monthly periods
            period_query = """
                SELECT DISTINCT reference_month
                FROM distribution_market_facts
                WHERE distributor_id = :id
                ORDER BY reference_month DESC
            """
            periods = [p[0] for p in conn.execute(text(period_query), {"id": distributor_id}).fetchall()]

        history = [
            {
                "ownership_id": r[0],
                "valid_from": r[1],
                "valid_to": r[2],
                "control_status": r[3],
                "ownership_percentage": r[4],
                "operational_consolidation_flag": r[5],
                "economic_group_id": r[6],
                "group_name": r[7],
                "cd_cvm": r[8],
                "company_name": r[9],
                "ticker_b3": r[10]
            }
            for r in history_rows
        ]

        return {
            "identity": {
                "distributor_id": dist_row[0],
                "canonical_name": dist_row[1],
                "legal_name": dist_row[2],
                "trade_name": dist_row[3],
                "normalized_cnpj": dist_row[4],
                "agent_code": dist_row[5],
                "distributor_code": dist_row[6],
                "concession_type": dist_row[7],
                "primary_uf": dist_row[8],
                "service_area": dist_row[9],
                "status": dist_row[10]
            },
            "ownership_history": history,
            "available_periods": periods
        }

    def get_series(
        self,
        *,
        entity_type: str,
        entity_id: str,
        frequency: str = "monthly",
    ) -> list[dict[str, Any]]:
        """Retrieve precomputed time-series aggregates for a distributor or group.

        Returns a sorted list of aggregate dicts.
        """
        table = (
            "distribution_monthly_aggregates"
            if frequency == "monthly"
            else "distribution_annual_aggregates"
        )
        period_col = "reference_month" if frequency == "monthly" else "reference_year"

        if entity_type == "distributor":
            if frequency == "monthly":
                query = """
                    SELECT
                        m.reference_month, m.billed_energy_mwh, m.revenue_brl,
                        m.measured_energy_mwh, m.injected_energy_mwh, m.losses_mwh, m.losses_pct,
                        m.dec_actual, m.fec_actual, m.dec_limit, m.fec_limit,
                        m.compensation_count, m.compensation_value, m.delinquency_pct,
                        m.mmgd_projects_count, m.mmgd_capacity_kw,
                        (
                            SELECT t.te_value
                            FROM distribution_tariff_facts t
                            WHERE t.distributor_id = m.distributor_id
                              AND t.subgroup = 'B1'
                              AND t.consumer_class = 'Residencial'
                              AND t.unit = 'R$/MWh'
                              AND t.valid_from <= m.reference_month || '-01'
                              AND t.valid_to >= m.reference_month || '-01'
                            ORDER BY t.valid_from DESC LIMIT 1
                        ) AS te_homologated,
                        (
                            SELECT t.tusd_value
                            FROM distribution_tariff_facts t
                            WHERE t.distributor_id = m.distributor_id
                              AND t.subgroup = 'B1'
                              AND t.consumer_class = 'Residencial'
                              AND t.unit = 'R$/MWh'
                              AND t.valid_from <= m.reference_month || '-01'
                              AND t.valid_to >= m.reference_month || '-01'
                            ORDER BY t.valid_from DESC LIMIT 1
                        ) AS tusd_homologated
                    FROM distribution_monthly_aggregates m
                    WHERE m.distributor_id = :id
                    ORDER BY m.reference_month ASC
                """
            else:
                query = """
                    SELECT
                        reference_year, billed_energy_mwh, revenue_brl,
                        measured_energy_mwh, injected_energy_mwh, losses_mwh, losses_pct,
                        dec_actual, fec_actual, dec_limit, fec_limit,
                        compensation_count, compensation_value, delinquency_pct,
                        mmgd_projects_count, mmgd_capacity_kw,
                        NULL AS te_homologated,
                        NULL AS tusd_homologated
                    FROM distribution_annual_aggregates
                    WHERE distributor_id = :id
                    ORDER BY reference_year ASC
                """
            params = {"id": entity_id}
            
            with self._engine().connect() as conn:
                rows = conn.execute(text(query), params).fetchall()
                
            return [
                {
                    "period": str(r[0]),
                    "billed_energy_mwh": r[1],
                    "revenue_brl": r[2],
                    "measured_energy_mwh": r[3],
                    "injected_energy_mwh": r[4],
                    "losses_mwh": r[5],
                    "losses_pct": r[6],
                    "dec_actual": r[7],
                    "fec_actual": r[8],
                    "dec_limit": r[9],
                    "fec_limit": r[10],
                    "compensation_count": r[11],
                    "compensation_value": r[12],
                    "delinquency_pct": r[13],
                    "mmgd_projects_count": r[14],
                    "mmgd_capacity_kw": r[15],
                    "te_homologated": r[16],
                    "tusd_homologated": r[17]
                }
                for r in rows
            ]
            
        elif entity_type == "group":
            # For economic groups, we query the sum/weighted values of all historically controlled distributors.
            # This respects validity ranges of the ownership.
            if frequency == "monthly":
                group_query = """
                    SELECT
                        m.reference_month,
                        SUM(m.billed_energy_mwh) AS billed_energy_mwh,
                        SUM(m.revenue_brl) AS revenue_brl,
                        SUM(m.measured_energy_mwh) AS measured_energy_mwh,
                        SUM(m.injected_energy_mwh) AS injected_energy_mwh,
                        SUM(m.losses_mwh) AS losses_mwh,
                        CASE 
                            WHEN SUM(m.injected_energy_mwh) > 0 THEN SUM(m.losses_mwh) / SUM(m.injected_energy_mwh)
                            ELSE NULL 
                        END AS losses_pct,
                        SUM(m.dec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.dec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_actual,
                        SUM(m.fec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.fec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_actual,
                        SUM(m.dec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.dec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_limit,
                        SUM(m.fec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.fec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_limit,
                        SUM(m.compensation_count) AS compensation_count,
                        SUM(m.compensation_value) AS compensation_value,
                        CASE
                            WHEN SUM(m.revenue_brl) > 0 THEN SUM(m.delinquency_pct * m.revenue_brl) / SUM(m.revenue_brl)
                            ELSE NULL
                        END AS delinquency_pct,
                        SUM(m.mmgd_projects_count) AS mmgd_projects_count,
                        SUM(m.mmgd_capacity_kw) AS mmgd_capacity_kw
                    FROM distribution_monthly_aggregates m
                    JOIN distribution_ownership_history h
                      ON m.distributor_id = h.distributor_id
                     AND h.valid_from <= m.reference_month || '-28'
                     AND h.valid_to >= m.reference_month || '-01'
                     AND h.operational_consolidation_flag = 1
                    LEFT JOIN (
                        SELECT distributor_id, reference_month, SUM(actual_value) AS consumers
                        FROM distribution_continuity_facts
                        WHERE indicator_code = 'NumCon'
                        GROUP BY distributor_id, reference_month
                    ) w ON m.distributor_id = w.distributor_id AND m.reference_month = w.reference_month
                    WHERE h.economic_group_id = :group_id
                    GROUP BY m.reference_month
                    ORDER BY m.reference_month ASC
                """
            else:
                group_query = """
                    SELECT
                        m.reference_year,
                        SUM(m.billed_energy_mwh) AS billed_energy_mwh,
                        SUM(m.revenue_brl) AS revenue_brl,
                        SUM(m.measured_energy_mwh) AS measured_energy_mwh,
                        SUM(m.injected_energy_mwh) AS injected_energy_mwh,
                        SUM(m.losses_mwh) AS losses_mwh,
                        CASE 
                            WHEN SUM(m.injected_energy_mwh) > 0 THEN SUM(m.losses_mwh) / SUM(m.injected_energy_mwh)
                            ELSE NULL 
                        END AS losses_pct,
                        SUM(m.dec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.dec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_actual,
                        SUM(m.fec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.fec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_actual,
                        SUM(m.dec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.dec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_limit,
                        SUM(m.fec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN m.fec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_limit,
                        SUM(m.compensation_count) AS compensation_count,
                        SUM(m.compensation_value) AS compensation_value,
                        CASE
                            WHEN SUM(m.revenue_brl) > 0 THEN SUM(m.delinquency_pct * m.revenue_brl) / SUM(m.revenue_brl)
                            ELSE NULL
                        END AS delinquency_pct,
                        SUM(m.mmgd_projects_count) AS mmgd_projects_count,
                        SUM(m.mmgd_capacity_kw) AS mmgd_capacity_kw
                    FROM distribution_annual_aggregates m
                    JOIN distribution_ownership_history h
                      ON m.distributor_id = h.distributor_id
                     AND CAST(SUBSTR(h.valid_from, 1, 4) AS INTEGER) <= m.reference_year
                     AND CAST(SUBSTR(h.valid_to, 1, 4) AS INTEGER) >= m.reference_year
                     AND h.operational_consolidation_flag = 1
                    LEFT JOIN (
                        SELECT distributor_id, CAST(SUBSTR(reference_month, 1, 4) AS INTEGER) AS ref_year, AVG(consumers) AS consumers
                        FROM (
                            SELECT distributor_id, reference_month, SUM(actual_value) AS consumers
                            FROM distribution_continuity_facts
                            WHERE indicator_code = 'NumCon'
                            GROUP BY distributor_id, reference_month
                        )
                        GROUP BY distributor_id, ref_year
                    ) w ON m.distributor_id = w.distributor_id AND m.reference_year = w.ref_year
                    WHERE h.economic_group_id = :group_id
                    GROUP BY m.reference_year
                    ORDER BY m.reference_year ASC
                """
            params = {"group_id": entity_id}
            
            with self._engine().connect() as conn:
                rows = conn.execute(text(group_query), params).fetchall()
                
            return [
                {
                    "period": str(r[0]),
                    "billed_energy_mwh": r[1],
                    "revenue_brl": r[2],
                    "measured_energy_mwh": r[3],
                    "injected_energy_mwh": r[4],
                    "losses_mwh": r[5],
                    "losses_pct": r[6],
                    "dec_actual": r[7],
                    "fec_actual": r[8],
                    "dec_limit": r[9],
                    "fec_limit": r[10],
                    "compensation_count": r[11],
                    "compensation_value": r[12],
                    "delinquency_pct": r[13],
                    "mmgd_projects_count": r[14],
                    "mmgd_capacity_kw": r[15]
                }
                for r in rows
            ]
            
        return []

    def get_groups(self) -> list[dict[str, Any]]:
        """Query the list of economic groups with their linked listed company details."""
        query = """
            SELECT
                g.economic_group_id,
                g.group_name,
                c.cd_cvm,
                c.company_name,
                c.ticker_b3,
                (
                    SELECT COUNT(DISTINCT h.distributor_id)
                    FROM distribution_ownership_history h
                    WHERE h.economic_group_id = g.economic_group_id
                      AND h.operational_consolidation_flag = 1
                ) AS distributors_count
            FROM distribution_economic_groups g
            LEFT JOIN (
                SELECT DISTINCT economic_group_id, cd_cvm
                FROM distribution_ownership_history
                WHERE cd_cvm IS NOT NULL
            ) m ON g.economic_group_id = m.economic_group_id
            LEFT JOIN distribution_listed_companies c
              ON m.cd_cvm = c.cd_cvm
            ORDER BY g.group_name
        """
        with self._engine().connect() as conn:
            rows = conn.execute(text(query)).fetchall()
        
        groups = {}
        for r in rows:
            g_id = r[0]
            if g_id not in groups:
                groups[g_id] = {
                    "economic_group_id": r[0],
                    "group_name": r[1],
                    "cd_cvm": r[2],
                    "company_name": r[3],
                    "ticker_b3": r[4],
                    "distributors_count": r[5]
                }
        return list(groups.values())

    def get_group_detail(self, group_id: str) -> dict[str, Any] | None:
        """Query single economic group metadata, linked listed company, portfolio, and available periods."""
        # 1. Base group identity
        group_query = """
            SELECT g.economic_group_id, g.group_name, c.cd_cvm, c.company_name, c.ticker_b3
            FROM distribution_economic_groups g
            LEFT JOIN (
                SELECT DISTINCT economic_group_id, cd_cvm
                FROM distribution_ownership_history
                WHERE cd_cvm IS NOT NULL
            ) m ON g.economic_group_id = m.economic_group_id
            LEFT JOIN distribution_listed_companies c
              ON m.cd_cvm = c.cd_cvm
            WHERE g.economic_group_id = :group_id
            LIMIT 1
        """
        with self._engine().connect() as conn:
            group_row = conn.execute(text(group_query), {"group_id": group_id}).fetchone()
            if not group_row:
                return None
            
            # 2. Portfolio list
            portfolio_query = """
                SELECT
                    h.ownership_id,
                    h.distributor_id,
                    d.canonical_name,
                    d.trade_name,
                    h.valid_from,
                    h.valid_to,
                    h.control_status,
                    h.ownership_percentage,
                    h.operational_consolidation_flag
                FROM distribution_ownership_history h
                JOIN distribution_distributors d ON h.distributor_id = d.distributor_id
                WHERE h.economic_group_id = :group_id
                ORDER BY h.valid_from DESC, d.canonical_name ASC
            """
            portfolio_rows = conn.execute(text(portfolio_query), {"group_id": group_id}).fetchall()
            
            # 3. Available periods (based on the consolidated series)
            period_query = """
                SELECT DISTINCT m.reference_month
                FROM distribution_monthly_aggregates m
                JOIN distribution_ownership_history h
                  ON m.distributor_id = h.distributor_id
                 AND h.valid_from <= m.reference_month || '-28'
                 AND h.valid_to >= m.reference_month || '-01'
                 AND h.operational_consolidation_flag = 1
                WHERE h.economic_group_id = :group_id
                ORDER BY m.reference_month DESC
            """
            periods = [p[0] for p in conn.execute(text(period_query), {"group_id": group_id}).fetchall()]
            
        portfolio = [
            {
                "ownership_id": r[0],
                "distributor_id": r[1],
                "canonical_name": r[2],
                "trade_name": r[3],
                "valid_from": r[4],
                "valid_to": r[5],
                "control_status": r[6],
                "ownership_percentage": r[7],
                "operational_consolidation_flag": r[8]
            }
            for r in portfolio_rows
        ]
        
        return {
            "identity": {
                "economic_group_id": group_row[0],
                "group_name": group_row[1],
                "cd_cvm": group_row[2],
                "company_name": group_row[3],
                "ticker_b3": group_row[4]
            },
            "portfolio": portfolio,
            "available_periods": periods
        }

    def get_health(self) -> dict[str, Any]:
        """Query metadata about ingested datasets, record counts, and database sizes."""
        # 1. Row counts of facts
        query_counts = """
            SELECT
                (SELECT COUNT(*) FROM distribution_market_facts) AS market_rows,
                (SELECT COUNT(*) FROM distribution_energy_balance_facts) AS balance_rows,
                (SELECT COUNT(*) FROM distribution_continuity_facts) AS continuity_rows,
                (SELECT COUNT(*) FROM distribution_tariff_facts) AS tariff_rows,
                (SELECT COUNT(*) FROM distribution_delinquency_facts) AS delinquency_rows,
                (SELECT COUNT(*) FROM distribution_mmgd_projects) AS mmgd_rows
        """
        # 2. Ingested snapshots
        query_snapshots = """
            SELECT snapshot_id, source, fetched_at, sha256, row_count, status
            FROM source_snapshots
            ORDER BY fetched_at DESC
        """
        with self._engine().connect() as conn:
            counts = conn.execute(text(query_counts)).fetchone()
            snapshots = conn.execute(text(query_snapshots)).fetchall()
            
        return {
            "counts": {
                "market": counts[0] if counts else 0,
                "balance": counts[1] if counts else 0,
                "continuity": counts[2] if counts else 0,
                "tariffs": counts[3] if counts else 0,
                "delinquency": counts[4] if counts else 0,
                "mmgd": counts[5] if counts else 0,
            },
            "snapshots": [
                {
                    "snapshot_id": s[0],
                    "source": s[1],
                    "fetched_at": s[2],
                    "sha256": s[3],
                    "row_count": s[4],
                    "status": s[5],
                }
                for s in snapshots
            ]
        }


