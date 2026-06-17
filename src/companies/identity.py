# -*- coding: utf-8 -*-
"""unificação de identidade corporativa (ticker, nome, CNPJ e setores) via CSV e resolver central."""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Any

from sqlalchemy import text
from src.platform.db import get_engine
from src.companies.gics_manual_mapping import resolve_gics_classification

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompanyIdentity:
    cd_cvm: int
    company_name: str
    nome_comercial: str | None
    cnpj: str | None
    ticker_b3: str | None
    is_active: bool
    
    setor_cvm: str | None
    setor_analitico: str | None
    gics_sector: str | None
    gics_sector_slug: str | None
    gics_industry_group: str | None
    gics_industry: str | None
    gics_sub_industry: str | None
    
    source: str  # 'db' | 'catalog' | 'ticker_map' | 'fallback'

    def to_dict(self) -> dict[str, Any]:
        return {
            "cd_cvm": self.cd_cvm,
            "company_name": self.company_name,
            "nome_comercial": self.nome_comercial,
            "cnpj": self.cnpj,
            "ticker_b3": self.ticker_b3,
            "is_active": self.is_active,
            "setor_cvm": self.setor_cvm,
            "setor_analitico": self.setor_analitico,
            "gics_sector": self.gics_sector,
            "gics_sector_slug": self.gics_sector_slug,
            "gics_industry_group": self.gics_industry_group,
            "gics_industry": self.gics_industry,
            "gics_sub_industry": self.gics_sub_industry,
            "source": self.source,
        }


def _load_csv_ticker_map() -> dict[int, dict[str, Any]]:
    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "import" / "ticker_map.csv"
    res = {}
    if not csv_path.exists():
        return res
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cd_cvm = int(row["cd_cvm"])
                    res[cd_cvm] = {
                        "ticker_b3": row.get("ticker_b3", "").strip() or None,
                        "cnpj_hint": row.get("cnpj_hint", "").strip() or None,
                        "notes": row.get("notes", "").strip() or None,
                    }
                except (ValueError, KeyError):
                    continue
    except Exception as e:
        logger.warning(f"Error loading ticker_map.csv in resolver: {e}")
    return res


class CompanyIdentityResolver:
    """Single entry point para resolver cd_cvm -> CompanyIdentity.
    
    Busca de forma transparente na tabela local 'companies', no CompanyCatalogService
    (CVM live) e no arquivo local estático 'ticker_map.csv'.
    """

    def __init__(self, engine=None, skip_db: bool = False) -> None:
        self._engine = engine
        self.skip_db = skip_db
        self._cache: dict[int, CompanyIdentity] = {}
        self._ticker_map_cache = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        return get_engine()

    def _get_ticker_map(self) -> dict[int, dict[str, Any]]:
        if self._ticker_map_cache is None:
            self._ticker_map_cache = _load_csv_ticker_map()
        return self._ticker_map_cache

    def resolve(self, cd_cvm: int) -> CompanyIdentity | None:
        try:
            cd_cvm = int(cd_cvm)
        except (ValueError, TypeError):
            return None

        if cd_cvm in self._cache:
            return self._cache[cd_cvm]

        identity = self._resolve_uncached(cd_cvm)
        if identity:
            self._cache[cd_cvm] = identity
        return identity

    def _resolve_uncached(self, cd_cvm: int) -> CompanyIdentity | None:
        # 1. Query database if available and not skipped
        if not self.skip_db:
            try:
                engine = self._get_engine()
                with engine.connect() as conn:
                    row = conn.execute(text("""
                        SELECT cd_cvm, company_name, nome_comercial, cnpj, ticker_b3, is_active,
                               setor_cvm, setor_analitico, gics_sector, gics_sector_slug,
                               gics_industry_group, gics_industry, gics_sub_industry
                        FROM companies WHERE cd_cvm = :cd
                    """), {"cd": cd_cvm}).fetchone()
                    
                    if row:
                        cnpj_val = row[3]
                        if cnpj_val:
                            cnpj_val = "".join(c for c in str(cnpj_val) if c.isdigit())
                            if len(cnpj_val) != 14:
                                cnpj_val = None

                        ticker_val = row[4]
                        if ticker_val:
                            ticker_val = str(ticker_val).strip().upper()
                            if not ticker_val.endswith(".SA") and not ticker_val.isdigit() and len(ticker_val) > 0:
                                ticker_val = f"{ticker_val}.SA"

                        gics = resolve_gics_classification(
                            sector_name=row[6],
                            setor_analitico=row[7],
                            setor_cvm=row[6],
                            gics_sector=row[8],
                            gics_sector_slug=row[9],
                            gics_industry_group=row[10],
                            gics_industry=row[11],
                            gics_sub_industry=row[12],
                        )

                        return CompanyIdentity(
                            cd_cvm=int(row[0]),
                            company_name=str(row[1]).strip(),
                            nome_comercial=str(row[2]).strip() if row[2] else None,
                            cnpj=cnpj_val,
                            ticker_b3=ticker_val,
                            is_active=bool(row[5]),
                            setor_cvm=str(row[6]).strip() if row[6] else None,
                            setor_analitico=str(row[7]).strip() if row[7] else None,
                            gics_sector=gics.gics_sector if gics else None,
                            gics_sector_slug=gics.gics_sector_slug if gics else None,
                            gics_industry_group=gics.gics_industry_group if gics else None,
                            gics_industry=gics.gics_industry if gics else None,
                            gics_sub_industry=gics.gics_sub_industry if gics else None,
                            source="db"
                        )
            except Exception as e:
                logger.debug(f"Database resolution failed for cd_cvm={cd_cvm}: {e}")

        # 2. Try CVM Catalog Service
        catalog_entry = None
        try:
            from src.companies.catalog import CompanyCatalogService
            catalog = CompanyCatalogService(timeout=3, ttl_seconds=3600)
            catalog_entry = catalog.lookup_company(cd_cvm)
        except Exception as e:
            logger.debug(f"Catalog lookup failed for cd_cvm={cd_cvm}: {e}")

        tmap = self._get_ticker_map()
        tinfo = tmap.get(cd_cvm, {})

        if catalog_entry:
            cnpj_val = catalog_entry.cnpj
            if cnpj_val:
                cnpj_val = "".join(c for c in str(cnpj_val) if c.isdigit())
                if len(cnpj_val) != 14:
                    cnpj_val = None
            cnpj_val = cnpj_val or tinfo.get("cnpj_hint")

            ticker_val = catalog_entry.ticker_b3 or tinfo.get("ticker_b3")
            if ticker_val:
                ticker_val = str(ticker_val).strip().upper()
                if not ticker_val.endswith(".SA") and not ticker_val.isdigit() and len(ticker_val) > 0:
                    ticker_val = f"{ticker_val}.SA"

            gics = resolve_gics_classification(
                sector_name=catalog_entry.setor_cvm,
                setor_cvm=catalog_entry.setor_cvm,
            )

            return CompanyIdentity(
                cd_cvm=cd_cvm,
                company_name=catalog_entry.company_name,
                nome_comercial=catalog_entry.nome_comercial,
                cnpj=cnpj_val,
                ticker_b3=ticker_val,
                is_active=catalog_entry.is_active,
                setor_cvm=catalog_entry.setor_cvm,
                setor_analitico=None,
                gics_sector=gics.gics_sector if gics else None,
                gics_sector_slug=gics.gics_sector_slug if gics else None,
                gics_industry_group=gics.gics_industry_group if gics else None,
                gics_industry=gics.gics_industry if gics else None,
                gics_sub_industry=gics.gics_sub_industry if gics else None,
                source="catalog"
            )

        # 3. Fallback to local ticker map CSV
        if cd_cvm in tmap:
            cnpj_val = tinfo.get("cnpj_hint")
            ticker_val = tinfo.get("ticker_b3")
            if ticker_val:
                ticker_val = str(ticker_val).strip().upper()
                if not ticker_val.endswith(".SA") and not ticker_val.isdigit() and len(ticker_val) > 0:
                    ticker_val = f"{ticker_val}.SA"

            return CompanyIdentity(
                cd_cvm=cd_cvm,
                company_name=tinfo.get("notes") or f"CVM_{cd_cvm}",
                nome_comercial=None,
                cnpj=cnpj_val,
                ticker_b3=ticker_val,
                is_active=True,
                setor_cvm=None,
                setor_analitico=None,
                gics_sector=None,
                gics_sector_slug=None,
                gics_industry_group=None,
                gics_industry=None,
                gics_sub_industry=None,
                source="ticker_map"
            )

        return None

    def resolve_by_ticker(self, ticker: str) -> CompanyIdentity | None:
        if not ticker:
            return None
        clean_ticker = str(ticker).strip().upper()
        if clean_ticker.endswith(".SA"):
            clean_ticker = clean_ticker[:-3]
        
        # Try reverse map compatibility
        from src.companies.ticker_map import REVERSE_TICKER_MAP
        cd_cvm = REVERSE_TICKER_MAP.get(clean_ticker)
        if cd_cvm:
            return self.resolve(cd_cvm)
            
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT cd_cvm FROM companies 
                    WHERE UPPER(ticker_b3) = :t OR UPPER(ticker_b3) = :t_sa
                """), {"t": clean_ticker, "t_sa": f"{clean_ticker}.SA"}).fetchone()
                if row:
                    return self.resolve(int(row[0]))
        except Exception:
            pass
            
        return None

    def resolve_by_cnpj(self, cnpj: str) -> CompanyIdentity | None:
        if not cnpj:
            return None
        clean_cnpj = "".join(c for c in str(cnpj) if c.isdigit())
        if not clean_cnpj:
            return None
            
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT cd_cvm FROM companies 
                    WHERE REPLACE(REPLACE(REPLACE(cnpj, '.', ''), '/', ''), '-', '') = :cnpj
                """), {"cnpj": clean_cnpj}).fetchone()
                if row:
                    return self.resolve(int(row[0]))
        except Exception:
            pass
            
        try:
            from src.companies.catalog import CompanyCatalogService
            catalog = CompanyCatalogService(timeout=3, ttl_seconds=3600)
            for entry in catalog.list_entries():
                e_cnpj = "".join(c for c in str(entry.cnpj or "") if c.isdigit())
                if e_cnpj == clean_cnpj:
                    return self.resolve(entry.cd_cvm)
        except Exception:
            pass
            
        tmap = self._get_ticker_map()
        for cd_cvm, tinfo in tmap.items():
            if tinfo.get("cnpj_hint") == clean_cnpj:
                return self.resolve(cd_cvm)
                
        return None

    def resolve_batch(self, codes: Iterable[int]) -> dict[int, CompanyIdentity]:
        results = {}
        for code in codes:
            identity = self.resolve(code)
            if identity:
                results[identity.cd_cvm] = identity
        return results

    def get_all_configured_tickers(self) -> list[str]:
        tmap = self._get_ticker_map()
        tickers = []
        for info in tmap.values():
            t = info.get("ticker_b3")
            if t:
                # Standardize to end with .SA
                t_sa = t.upper().strip()
                if not t_sa.endswith(".SA") and not t_sa.isdigit() and len(t_sa) > 0:
                    t_sa = f"{t_sa}.SA"
                tickers.append(t_sa)
        return sorted(list(set(tickers)))
