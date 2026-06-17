# -*- coding: utf-8 -*-
"""
scripts/data/sync_identity.py — Sincroniza metadados unificados na tabela `companies`.

Busca dados do CVM live catalog, cruza com o `ticker_map.csv` e GICS, e atualiza a
tabela `companies` no banco de dados local com CNPJs, nomes, tickers e setores.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.platform.db import build_engine
from src.platform.settings import build_settings
from src.platform.startup import collect_startup_report, format_startup_report
from src.companies.catalog import CompanyCatalogService
from src.companies.identity import CompanyIdentityResolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    log.info("Iniciando sincronização unificada de identidade...")
    settings = build_settings(project_root=ROOT)
    
    # Valida o ambiente de inicialização do banco
    startup_report = collect_startup_report(
        settings,
        require_database=True,
    )
    if startup_report.issues:
        log.info(format_startup_report(startup_report))
        if startup_report.errors:
            raise SystemExit(1)

    engine = build_engine(settings)
    
    # 1. Carrega as empresas existentes no banco (de financial_reports e companies)
    log.info("Buscando empresas ativas no banco e catálogo...")
    with engine.connect() as conn:
        db_codes = {
            int(r[0]) for r in conn.execute(
                text('SELECT DISTINCT "CD_CVM" FROM financial_reports')
            ).fetchall()
        }
        try:
            comp_rows = {
                int(r[0]) for r in conn.execute(
                    text("SELECT cd_cvm FROM companies")
                ).fetchall()
            }
            db_codes.update(comp_rows)
        except Exception:
            pass

    # 2. Carrega catálogo da CVM para obter a lista mestra
    catalog_service = CompanyCatalogService(timeout=10)
    try:
        catalog_entries = catalog_service.list_entries()
        log.info(f"Carregadas {len(catalog_entries)} empresas do cadastro CVM.")
    except Exception as e:
        log.error(f"Não foi possível carregar catálogo CVM live: {e}")
        catalog_entries = []

    # Sincroniza todas as empresas que possuem relatórios financeiros ou já estão cadastradas
    codes_to_sync = set(db_codes)
    for entry in catalog_entries:
        if entry.is_active:
            codes_to_sync.add(entry.cd_cvm)

    log.info(f"Total de {len(codes_to_sync)} códigos de empresas para avaliar/atualizar.")
    
    resolver = CompanyIdentityResolver(skip_db=True)
    updated_at = datetime.utcnow().replace(microsecond=0).isoformat()
    
    inserted = 0
    updated = 0
    errors = 0

    with engine.begin() as conn:
        for idx, cd_cvm in enumerate(codes_to_sync, 1):
            try:
                identity = resolver.resolve(cd_cvm)
                if not identity:
                    continue

                # Prepara os valores
                params = {
                    "cd": identity.cd_cvm,
                    "name": identity.company_name,
                    "nome_comercial": identity.nome_comercial,
                    "cnpj": identity.cnpj,
                    "setor_cvm": identity.setor_cvm,
                    "gics_sector": identity.gics_sector,
                    "gics_sector_slug": identity.gics_sector_slug,
                    "gics_industry_group": identity.gics_industry_group,
                    "gics_industry": identity.gics_industry,
                    "gics_sub_industry": identity.gics_sub_industry,
                    "ticker": identity.ticker_b3,
                    "is_active": 1 if identity.is_active else 0,
                    "updated_at": updated_at,
                }

                # Executa o UPSERT dialético-safe
                row = conn.execute(
                    text("SELECT cd_cvm FROM companies WHERE cd_cvm = :cd"),
                    {"cd": identity.cd_cvm}
                ).fetchone()

                if not row:
                    conn.execute(text("""
                        INSERT INTO companies (
                            cd_cvm, company_name, nome_comercial, cnpj, setor_cvm,
                            gics_sector, gics_sector_slug, gics_industry_group,
                            gics_industry, gics_sub_industry, ticker_b3, is_active,
                            updated_at, company_type
                        ) VALUES (
                            :cd, :name, :nome_comercial, :cnpj, :setor_cvm,
                            :gics_sector, :gics_sector_slug, :gics_industry_group,
                            :gics_industry, :gics_sub_industry, :ticker, :is_active,
                            :updated_at, 'comercial'
                        )
                    """), params)
                    inserted += 1
                else:
                    # Preserva colunas manuais (setor_analitico, company_type, coverage_rank)
                    conn.execute(text("""
                        UPDATE companies
                        SET company_name = :name,
                            nome_comercial = COALESCE(:nome_comercial, nome_comercial),
                            cnpj = COALESCE(:cnpj, cnpj),
                            setor_cvm = COALESCE(:setor_cvm, setor_cvm),
                            gics_sector = COALESCE(:gics_sector, gics_sector),
                            gics_sector_slug = COALESCE(:gics_sector_slug, gics_sector_slug),
                            gics_industry_group = COALESCE(:gics_industry_group, gics_industry_group),
                            gics_industry = COALESCE(:gics_industry, gics_industry),
                            gics_sub_industry = COALESCE(:gics_sub_industry, gics_sub_industry),
                            ticker_b3 = :ticker,
                            is_active = :is_active,
                            updated_at = :updated_at
                        WHERE cd_cvm = :cd
                    """), params)
                    updated += 1

                if idx % 200 == 0:
                    log.info(f"Progresso: {idx}/{len(codes_to_sync)} avaliados...")

            except Exception as e:
                errors += 1
                log.debug(f"Erro ao processar cd_cvm {cd_cvm}: {e}")

    log.info("=" * 60)
    log.info("Relatório de Sincronização de Identidade:")
    log.info(f"  Inseridas no banco:  {inserted}")
    log.info(f"  Atualizadas no banco: {updated}")
    log.info(f"  Erros / Puladas:      {errors}")
    log.info("Sincronização concluída com sucesso!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
