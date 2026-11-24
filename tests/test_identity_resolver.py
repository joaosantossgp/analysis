# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from src.companies.identity import CompanyIdentityResolver, CompanyIdentity


@pytest.fixture
def temp_db_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE companies (
                cd_cvm          INTEGER PRIMARY KEY,
                company_name    TEXT NOT NULL,
                nome_comercial  TEXT,
                cnpj            TEXT,
                setor_cvm       TEXT,
                gics_sector     TEXT,
                gics_sector_slug TEXT,
                gics_industry_group TEXT,
                gics_industry   TEXT,
                gics_sub_industry TEXT,
                company_type    TEXT NOT NULL DEFAULT 'comercial',
                ticker_b3       TEXT,
                coverage_rank   INTEGER,
                is_active       INTEGER NOT NULL DEFAULT 1,
                updated_at      TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO companies (
                cd_cvm, company_name, nome_comercial, cnpj, ticker_b3, is_active,
                setor_cvm, gics_sector, gics_sector_slug, updated_at
            ) VALUES (
                9512, 'PETROLEO BRASILEIRO S.A. PETROBRAS', 'PETROBRAS', '33000167000101', 'PETR4', 1,
                'Petróleo e Gás', 'Energy', 'energy', '2026-06-16T20:00:00'
            )
        """))
    return engine


def test_resolver_db_resolution(temp_db_engine):
    resolver = CompanyIdentityResolver(engine=temp_db_engine)
    identity = resolver.resolve(9512)
    
    assert identity is not None
    assert identity.cd_cvm == 9512
    assert identity.company_name == "PETROLEO BRASILEIRO S.A. PETROBRAS"
    assert identity.nome_comercial == "PETROBRAS"
    assert identity.cnpj == "33000167000101"
    assert identity.ticker_b3 == "PETR4.SA"  # Auto suffix appended
    assert identity.is_active is True
    assert identity.setor_cvm == "Petróleo e Gás"
    assert identity.gics_sector == "Energy"
    assert identity.source == "db"


def test_resolver_csv_fallback():
    # Uses real data/import/ticker_map.csv
    resolver = CompanyIdentityResolver()
    
    # 906 is BBDC4 in CSV
    identity = resolver.resolve(906)
    assert identity is not None
    assert identity.cd_cvm == 906
    assert identity.ticker_b3 == "BBDC4.SA"
    # It falls back to ticker_map because it's not in our empty temp DB
    assert identity.source in ("db", "catalog", "ticker_map")


@pytest.mark.parametrize(
    ("cd_cvm", "expected_ticker"),
    [
        (25690, "MATD3.SA"),
        (24295, "VBBR3.SA"),
    ],
)
def test_resolver_backfills_missing_db_ticker_from_csv(temp_db_engine, cd_cvm, expected_ticker):
    with temp_db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO companies (
                    cd_cvm, company_name, nome_comercial, cnpj, ticker_b3, is_active,
                    setor_cvm, gics_sector, gics_sector_slug, updated_at
                ) VALUES (
                    :cd_cvm, :company_name, NULL, NULL, NULL, 1,
                    NULL, NULL, NULL, '2026-06-18T12:00:00'
                )
                """
            ),
            {
                "cd_cvm": cd_cvm,
                "company_name": "HOSPITAL MATER DEI S.A." if cd_cvm == 25690 else "VIBRA ENERGIA S/A",
            },
        )

    resolver = CompanyIdentityResolver(engine=temp_db_engine)
    identity = resolver.resolve(cd_cvm)

    assert identity is not None
    assert identity.source == "db"
    assert identity.ticker_b3 == expected_ticker


def test_resolve_by_ticker(temp_db_engine):
    resolver = CompanyIdentityResolver(engine=temp_db_engine)
    
    # Resolves via DB ticker
    identity = resolver.resolve_by_ticker("PETR4")
    assert identity is not None
    assert identity.cd_cvm == 9512
    
    # Resolves via DB ticker with suffix
    identity_sa = resolver.resolve_by_ticker("PETR4.SA")
    assert identity_sa is not None
    assert identity_sa.cd_cvm == 9512
    
    # Resolves via CSV ticker fallback (906 -> BBDC4)
    identity_csv = resolver.resolve_by_ticker("BBDC4")
    assert identity_csv is not None
    assert identity_csv.cd_cvm == 906


def test_resolve_by_cnpj(temp_db_engine):
    resolver = CompanyIdentityResolver(engine=temp_db_engine)
    
    # Resolves via DB CNPJ
    identity = resolver.resolve_by_cnpj("33.000.167/0001-01")
    assert identity is not None
    assert identity.cd_cvm == 9512
    
    identity_raw = resolver.resolve_by_cnpj("33000167000101")
    assert identity_raw is not None
    assert identity_raw.cd_cvm == 9512


def test_resolve_batch(temp_db_engine):
    resolver = CompanyIdentityResolver(engine=temp_db_engine)
    res = resolver.resolve_batch([9512, 906, 99999])
    
    assert 9512 in res
    assert res[9512].ticker_b3 == "PETR4.SA"
    assert 906 in res
    assert 99999 not in res
