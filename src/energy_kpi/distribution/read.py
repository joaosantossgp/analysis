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
                c.ticker_b3,
                m.cd_cvm AS mapped_cvm,
                m.custom_owner_name AS mapped_custom_owner,
                mc.company_name AS mapped_cvm_company_name,
                mc.ticker_b3 AS mapped_cvm_ticker,
                m.mapping_source
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
            LEFT JOIN conglomerate_asset_mappings m
              ON d.distributor_id = m.asset_id
             AND m.asset_type = 'distributor'
            LEFT JOIN distribution_listed_companies mc
              ON m.cd_cvm = mc.cd_cvm
            WHERE d.classification = 'distributor'
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

        with self._engine().connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
            
        results = []
        for r in rows:
            dist_id, name, trade_name, cnpj, agent_code, conc_type, uf, status, eg_id, eg_name, c_cvm, c_name, c_ticker, m_cvm, m_custom, mc_name, mc_ticker, m_source = r
            
            # Resolve owner override
            if m_cvm is not None:
                resolved_cvm = m_cvm
                resolved_owner = mc_name or c_name or f"CVM: {m_cvm}"
                resolved_ticker = mc_ticker or c_ticker
                resolved_is_custom = False
            elif m_custom is not None and m_custom.strip() != "":
                resolved_cvm = None
                resolved_owner = m_custom.strip()
                resolved_ticker = "Non-Listed"
                resolved_is_custom = True
            else:
                resolved_cvm = c_cvm
                resolved_owner = eg_name or c_name
                resolved_ticker = c_ticker
                resolved_is_custom = False
                
            results.append({
                "distributor_id": dist_id,
                "canonical_name": name,
                "trade_name": trade_name,
                "normalized_cnpj": cnpj,
                "agent_code": agent_code,
                "concession_type": conc_type,
                "primary_uf": uf,
                "status": status,
                "economic_group_id": eg_id,
                "group_name": eg_name,
                "cd_cvm": resolved_cvm,
                "company_name": resolved_owner,
                "ticker_b3": resolved_ticker,
                "is_custom_owner": resolved_is_custom,
                "mapping_source": m_source or "unmapped"
            })
        return results

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
                              AND t.unit = 'MWh'
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
                              AND t.unit = 'MWh'
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
                    WITH group_monthly AS (
                        SELECT m.*
                        FROM distribution_monthly_aggregates m
                        JOIN distribution_ownership_history h
                          ON m.distributor_id = h.distributor_id
                         AND h.valid_from <= m.reference_month || '-28'
                         AND h.valid_to >= m.reference_month || '-01'
                         AND h.operational_consolidation_flag = 1
                        WHERE h.economic_group_id = :group_id
                    ),
                    continuity_weights AS (
                        SELECT cf.distributor_id, cf.reference_month, SUM(cf.actual_value) AS consumers
                        FROM distribution_continuity_facts cf
                        JOIN (
                            SELECT DISTINCT distributor_id, reference_month
                            FROM group_monthly
                        ) gm
                          ON cf.distributor_id = gm.distributor_id
                         AND cf.reference_month = gm.reference_month
                        WHERE cf.indicator_code = 'NumCon'
                        GROUP BY cf.distributor_id, cf.reference_month
                    )
                    SELECT
                        gm.reference_month,
                        SUM(gm.billed_energy_mwh) AS billed_energy_mwh,
                        SUM(gm.revenue_brl) AS revenue_brl,
                        SUM(gm.measured_energy_mwh) AS measured_energy_mwh,
                        SUM(gm.injected_energy_mwh) AS injected_energy_mwh,
                        SUM(gm.losses_mwh) AS losses_mwh,
                        CASE 
                            WHEN SUM(gm.injected_energy_mwh) > 0 THEN SUM(gm.losses_mwh) / SUM(gm.injected_energy_mwh)
                            ELSE NULL 
                        END AS losses_pct,
                        SUM(gm.dec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN gm.dec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_actual,
                        SUM(gm.fec_actual * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN gm.fec_actual IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_actual,
                        SUM(gm.dec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN gm.dec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS dec_limit,
                        SUM(gm.fec_limit * COALESCE(w.consumers, 0)) / NULLIF(SUM(CASE WHEN gm.fec_limit IS NOT NULL THEN COALESCE(w.consumers, 0) ELSE 0 END), 0) AS fec_limit,
                        SUM(gm.compensation_count) AS compensation_count,
                        SUM(gm.compensation_value) AS compensation_value,
                        CASE
                            WHEN SUM(gm.revenue_brl) > 0 THEN SUM(gm.delinquency_pct * gm.revenue_brl) / SUM(gm.revenue_brl)
                            ELSE NULL
                        END AS delinquency_pct,
                        SUM(gm.mmgd_projects_count) AS mmgd_projects_count,
                        SUM(gm.mmgd_capacity_kw) AS mmgd_capacity_kw,
                        NULL AS te_homologated,
                        NULL AS tusd_homologated
                    FROM group_monthly gm
                    LEFT JOIN continuity_weights w
                      ON gm.distributor_id = w.distributor_id
                     AND gm.reference_month = w.reference_month
                    GROUP BY gm.reference_month
                    ORDER BY gm.reference_month ASC
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
                        SUM(m.mmgd_capacity_kw) AS mmgd_capacity_kw,
                        NULL AS te_homologated,
                        NULL AS tusd_homologated
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

            series = [
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
            if frequency == "monthly":
                self._apply_group_tariffs(entity_id, series)
            return series
            
        return []

    def _apply_group_tariffs(self, group_id: str, series: list[dict[str, Any]]) -> None:
        if not series:
            return

        periods = [row["period"] for row in series]
        min_date = f"{min(periods)}-01"
        max_date = f"{max(periods)}-28"
        query = """
            SELECT
                h.distributor_id,
                h.valid_from AS ownership_from,
                h.valid_to AS ownership_to,
                t.valid_from AS tariff_from,
                t.valid_to AS tariff_to,
                t.te_value,
                t.tusd_value
            FROM distribution_ownership_history h
            JOIN distribution_tariff_facts t
              ON t.distributor_id = h.distributor_id
             AND t.subgroup = 'B1'
             AND t.consumer_class = 'Residencial'
             AND t.unit = 'MWh'
             AND t.valid_to >= :min_date
             AND t.valid_from <= :max_date
            WHERE h.economic_group_id = :group_id
              AND h.operational_consolidation_flag = 1
              AND h.valid_to >= :min_date
              AND h.valid_from <= :max_date
            ORDER BY h.distributor_id, t.valid_from
        """
        with self._engine().connect() as conn:
            tariff_rows = conn.execute(
                text(query),
                {"group_id": group_id, "min_date": min_date, "max_date": max_date},
            ).fetchall()

        for point in series:
            period = point["period"]
            period_start = f"{period}-01"
            period_end = f"{period}-28"
            latest_by_distributor: dict[str, tuple[str, Any, Any]] = {}
            for row in tariff_rows:
                distributor_id = row[0]
                if row[1] > period_end or row[2] < period_start:
                    continue
                if row[3] > period_start or row[4] < period_start:
                    continue
                previous = latest_by_distributor.get(distributor_id)
                if previous is None or row[3] > previous[0]:
                    latest_by_distributor[distributor_id] = (row[3], row[5], row[6])

            te_values = [value[1] for value in latest_by_distributor.values() if value[1] is not None]
            tusd_values = [value[2] for value in latest_by_distributor.values() if value[2] is not None]
            point["te_homologated"] = sum(te_values) / len(te_values) if te_values else None
            point["tusd_homologated"] = sum(tusd_values) / len(tusd_values) if tusd_values else None

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
        # 3. Refresh logs
        query_logs = """
            SELECT
                refresh_id, source_id, dataset_name, started_at, finished_at, status,
                rows_inserted, rows_updated, rows_unchanged, error_message, warning_message,
                source_rows, parsed_rows, canonical_rows, final_published_rows,
                elapsed_download_ms, elapsed_parse_ms, elapsed_publish_ms, elapsed_aggregate_ms,
                elapsed_lock_wait_ms, peak_rss_mb, cpu_time_ms,
                unresolved_identity_rows, conflict_rows, rejected_rows, snapshot_id
            FROM energy_source_refresh_log
            ORDER BY started_at DESC
            LIMIT 50
        """
        with self._engine().connect() as conn:
            counts = conn.execute(text(query_counts)).fetchone()
            snapshots = conn.execute(text(query_snapshots)).fetchall()
            logs = conn.execute(text(query_logs)).fetchall()
            
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
            ],
            "refresh_logs": [
                {
                    "refresh_id": row[0],
                    "source_id": row[1],
                    "dataset_name": row[2],
                    "started_at": row[3],
                    "finished_at": row[4],
                    "status": row[5],
                    "rows_inserted": row[6],
                    "rows_updated": row[7],
                    "rows_unchanged": row[8],
                    "error_message": row[9],
                    "warning_message": row[10],
                    "source_rows": row[11],
                    "parsed_rows": row[12],
                    "canonical_rows": row[13],
                    "final_published_rows": row[14],
                    "elapsed_download_ms": row[15],
                    "elapsed_parse_ms": row[16],
                    "elapsed_publish_ms": row[17],
                    "elapsed_aggregate_ms": row[18],
                    "elapsed_lock_wait_ms": row[19],
                    "peak_rss_mb": row[20],
                    "cpu_time_ms": row[21],
                    "unresolved_identity_rows": row[22],
                    "conflict_rows": row[23],
                    "rejected_rows": row[24],
                    "snapshot_id": row[25],
                }
                for row in logs
            ]
        }
