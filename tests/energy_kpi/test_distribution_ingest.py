"""Tests for Slice 2: Distribution Ingestion, Parsing, and Aggregation."""
from __future__ import annotations

from pathlib import Path
import zipfile
import pytest
import polars as pl
from sqlalchemy import text

from src.energy_kpi.distribution import (
    seed_distribution_static_data,
    parse_samp_mercado,
    parse_samp_balanco,
    upsert_samp_mercado_facts,
    upsert_samp_balanco_facts,
    rebuild_distribution_aggregates,
)


def test_parse_and_upsert_samp_mercado(tmp_path, db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Construct mock SAMP Mercado data
    # CPFL Paulista: 33050196000188
    # Neoenergia Coelba: 15139629000194
    mock_data = pl.DataFrame({
        "NumCNPJAgenteDistribuidora": ["33050196000188", "15139629000194", "15139629000194", "99999999000199"],
        "NomAgenteDistribuidora": [
            "CPFL PAULISTA S.A.",
            "COELBA DISTRIBUIDORA",
            "COELBA DISTRIBUIDORA",
            "UNMAPPED DISTRIBUTOR S.A."
        ],
        "SigAgenteDistribuidora": ["CPFL PAULISTA", "COELBA", "COELBA", "UNMAPPED"],
        "NomTipoMercado": ["Regular", "Regular", "Regular", "Regular"],
        "DscModalidadeTarifaria": ["Convencional", "Convencional", "Convencional", "Convencional"],
        "DscSubGrupoTarifario": ["B1", "B1", "B1", "B1"],
        "DscClasseConsumoMercado": ["Residencial", "Residencial", "Residencial", "Residencial"],
        "DscSubClasseConsumidor": ["Residencial", "Residencial", "Residencial", "Residencial"],
        "DscDetalheConsumidor": ["Não se aplica", "Não se aplica", "Não se aplica", "Não se aplica"],
        "NumCNPJAgenteAcessante": [None, None, None, None],
        "NomAgenteAcessante": [None, None, None, None],
        "DscPostoTarifario": ["Não se aplica", "Não se aplica", "Não se aplica", "Não se aplica"],
        "DscOpcaoEnergia": ["CATIVO", "CATIVO", "CATIVO", "CATIVO"],
        "DscDetalheMercado": [
            "Consumo de Energia Elétrica (MWh)",
            "Receita Energia (R$)",
            "Número de Consumidores (Unidades)",
            "Consumo de Energia Elétrica (kWh)" # Needs unit conversion (divide by 1000)
        ],
        "DatCompetencia": ["2025-01-01", "2025-01-01", "2025-01-01", "2025-02-01"],
        "VlrMercado": ["1200,50", "450000,00", "50000", "300000,00"]
    })

    mock_file = tmp_path / "mock_samp_mercado.parquet"
    mock_data.write_parquet(mock_file)

    # 3. Test parsing
    parsed_df = parse_samp_mercado(mock_file, format_type="parquet")
    assert parsed_df.height == 4
    
    # Check unit conversion (kWh to MWh)
    unmapped_row = parsed_df.filter(pl.col("normalized_cnpj") == "99999999000199").to_dicts()[0]
    assert unmapped_row["normalized_value"] == 300.0  # 300000 / 1000
    assert unmapped_row["metric_name"] == "billed_energy"
    assert unmapped_row["normalized_unit"] == "MWh"

    # Check mapping
    coelba_revenue_row = parsed_df.filter(
        (pl.col("normalized_cnpj") == "15139629000194") & (pl.col("metric_name") == "revenue")
    ).to_dicts()[0]
    assert coelba_revenue_row["normalized_value"] == 450000.0
    assert coelba_revenue_row["normalized_unit"] == "BRL"

    # 4. Test database upsert
    snapshot_id = "test-snap-123"
    inserted = upsert_samp_mercado_facts(db_conn, parsed_df, snapshot_id)
    assert inserted == 4

    # Verify facts in SQLite
    facts = db_conn.execute(text("""
        SELECT distributor_id, reference_month, metric_name, normalized_value, normalized_unit
        FROM distribution_market_facts
        ORDER BY distributor_id, metric_name
    """)).fetchall()
    
    # 4 facts inserted: 2 for coelba, 1 for cpfl_paulista, 1 for dynamically created unmapped distributor
    assert len(facts) == 4
    
    # Check dynamic registration of unmapped distributor
    unmapped_dist = db_conn.execute(
        text("SELECT canonical_name, status FROM distribution_distributors WHERE distributor_id = 'unmapped_99999999000199'")
    ).fetchone()
    assert unmapped_dist is not None
    assert unmapped_dist[0] == "UNMAPPED DISTRIBUTOR S.A."
    assert unmapped_dist[1] == "active"

    # 5. Test aggregates rebuild
    rebuild_distribution_aggregates(db_conn)

    # Verify monthly aggregates
    monthly = db_conn.execute(text("""
        SELECT distributor_id, reference_month, billed_energy_mwh, revenue_brl
        FROM distribution_monthly_aggregates
        ORDER BY distributor_id
    """)).fetchall()

    assert len(monthly) == 3  # coelba, cpfl_paulista, unmapped
    
    coelba_agg = [m for m in monthly if m[0] == "coelba"][0]
    assert coelba_agg[1] == "2025-01"
    # coelba had only revenue fact (450000.0) and consumer count fact (50000) -> billed_energy should be NULL
    assert coelba_agg[2] is None
    assert coelba_agg[3] == 450000.0

    cpfl_agg = [m for m in monthly if m[0] == "cpfl_paulista"][0]
    assert cpfl_agg[1] == "2025-01"
    assert cpfl_agg[2] == 1200.50
    assert cpfl_agg[3] is None

    unmapped_agg = [m for m in monthly if m[0] == "unmapped_99999999000199"][0]
    assert unmapped_agg[1] == "2025-02"
    assert unmapped_agg[2] == 300.0
    assert unmapped_agg[3] is None

    # Verify annual aggregates
    annual = db_conn.execute(text("""
        SELECT distributor_id, reference_year, billed_energy_mwh, revenue_brl
        FROM distribution_annual_aggregates
        ORDER BY distributor_id
    """)).fetchall()

    assert len(annual) == 3
    coelba_ann = [a for a in annual if a[0] == "coelba"][0]
    assert coelba_ann[1] == 2025
    assert coelba_ann[2] is None
    assert coelba_ann[3] == 450000.0

    # 6. Test Read Service
    from src.energy_kpi.distribution.read import DistributionReadService
    # Mock settings with settings object
    from unittest.mock import MagicMock
    mock_settings = MagicMock()
    
    # We patch _engine method of DistributionReadService to return a mock engine or connect directly.
    # Since db_conn is an active connection, we can subclass or patch get_energy_kpi_engine to return an engine that connects to our test DB.
    # But even simpler: patch the service's `_engine` method to return an engine mock that yields db_conn or is connected to the same in-memory DB.
    # Actually, in our tests, db_conn's engine can be obtained via db_conn.engine.
    read_service = DistributionReadService(mock_settings)
    
    # We mock _engine().connect() to yield db_conn (the active transaction connection)
    class MockConnContext:
        def __enter__(self):
            return db_conn
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = lambda: MockConnContext()
    read_service._engine = MagicMock(return_value=mock_engine)

    # Test get_distributors
    dists = read_service.get_distributors()
    print("ALL RETURNED DISTRIBUTORS:", dists)
    assert len(dists) > 0
    assert any(d["distributor_id"] == "coelba" for d in dists)
    # Check that current group is mapped (coelba is under neoenergia in seeded data)
    coelba_d = [d for d in dists if d["distributor_id"] == "coelba"][0]
    assert coelba_d["group_name"] == "Neoenergia"

    # Test get_distributors search
    print("COUNT ON db_conn:", db_conn.execute(text("SELECT count(*) FROM distribution_distributors")).scalar())
    with read_service._engine().connect() as c:
        print("COUNT ON read_service connection:", c.execute(text("SELECT count(*) FROM distribution_distributors")).scalar())
        print("SQL ON c:", c.execute(text("SELECT distributor_id, canonical_name FROM distribution_distributors WHERE canonical_name LIKE '%CPFL%'")).fetchall())
        
    cpfl_dists = read_service.get_distributors(search="CPFL")
    print("SERVICE SEARCH RETURNED:", cpfl_dists)
    assert len(cpfl_dists) > 0
    assert all("CPFL" in d["canonical_name"] or "CPFL" in d["trade_name"] for d in cpfl_dists)

    # Test get_distributor_detail
    detail = read_service.get_distributor_detail("coelba")
    assert detail is not None
    assert detail["identity"]["distributor_id"] == "coelba"
    assert len(detail["ownership_history"]) > 0
    # Available periods should include 2025-01
    assert "2025-01" in detail["available_periods"]

    # Test get_series
    series = read_service.get_series(entity_type="distributor", entity_id="coelba", frequency="monthly")
    assert len(series) == 1
    assert series[0]["period"] == "2025-01"
    assert series[0]["revenue_brl"] == 450000.0


def test_parse_and_upsert_samp_balanco(tmp_path, db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Construct mock SAMP Balanço data
    # Neoenergia Coelba: 15139629000194
    mock_data = pl.DataFrame({
        "NumCPFCNPJ": [15139629000194, 15139629000194],
        "NomAgente": ["COELBA DISTRIBUIDORA", "COELBA DISTRIBUIDORA"],
        "AnmCompetenciaBalanco": [202501, 202501],
        "DscModalidadeBalanco": ["Energia Injetada", "Perdas na Distribuição (valor medido)"],
        "DscFluxoEnergia": ["Disponibilidades", "Saldo"],
        "DscCctBalanco": ["Energia Injetada Total", "Perdas Totais"],
        "DscClassificacaoAgente": ["Concessionária", "Concessionária"],
        "AnoReferenciaBalanco": [2025, 2025],
        "MesReferenciaBalanco": [1, 1],
        "DscDetalheBalanco": ["Energia Medida (kWh)", "Energia Calculada (kWh)"],
        "VlrEnergia": [1000000, 150000]  # 1000 MWh injected, 150 MWh losses (15% loss)
    })

    mock_file = tmp_path / "mock_samp_balanco.parquet"
    mock_data.write_parquet(mock_file)

    # 3. Test parsing
    from src.energy_kpi.distribution.ingest import parse_samp_balanco, upsert_samp_balanco_facts
    parsed_df = parse_samp_balanco(mock_file, format_type="parquet")
    assert parsed_df.height == 2

    # Check unit conversion (1000000 kWh -> 1000 MWh)
    injected_row = parsed_df.filter(pl.col("balance_characteristic") == "Energia Injetada Total").to_dicts()[0]
    assert injected_row["normalized_value"] == 1000.0
    assert injected_row["normalized_unit"] == "MWh"

    losses_row = parsed_df.filter(pl.col("balance_characteristic") == "Perdas Totais").to_dicts()[0]
    assert losses_row["normalized_value"] == 150.0

    # 4. Test database upsert
    snapshot_id = "test-snap-balanco"
    inserted = upsert_samp_balanco_facts(db_conn, parsed_df, snapshot_id)
    assert inserted == 2

    # Verify facts in SQLite
    facts = db_conn.execute(text("""
        SELECT distributor_id, reference_month, balance_characteristic, normalized_value
        FROM distribution_energy_balance_facts
        ORDER BY balance_characteristic
    """)).fetchall()
    assert len(facts) == 2
    assert facts[0][0] == "coelba"
    assert facts[0][1] == "2025-01"
    assert facts[0][2] == "Energia Injetada Total"
    assert facts[0][3] == 1000.0

    # 5. Test aggregates rebuild
    rebuild_distribution_aggregates(db_conn)

    # Verify aggregates have balance metrics
    monthly = db_conn.execute(text("""
        SELECT distributor_id, reference_month, injected_energy_mwh, losses_mwh, measured_energy_mwh, losses_pct
        FROM distribution_monthly_aggregates
        WHERE distributor_id = 'coelba'
    """)).fetchone()

    assert monthly is not None
    assert monthly[2] == 1000.0
    assert monthly[3] == 150.0
    assert monthly[4] == 850.0  # 1000 - 150
    assert monthly[5] == 0.15   # 150 / 1000


def test_samp_balanco_unresolved_entities_get_stable_distinct_ids(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)

    path = tmp_path / "balanco-unresolved.csv"
    pl.DataFrame({
        "NumCPFCNPJ": ["", ""],
        "NomAgente": ["OLD DIST A", "OLD DIST B"],
        "AnmCompetenciaBalanco": [202501, 202501],
        "DscModalidadeBalanco": ["Energia Recebida", "Energia Recebida"],
        "DscFluxoEnergia": ["Disponibilidades", "Disponibilidades"],
        "DscCctBalanco": ["Compra/Repasse Itaipu/Importação", "Compra/Repasse Itaipu/Importação"],
        "DscDetalheBalanco": ["Energia Medida (kWh)", "Energia Medida (kWh)"],
        "VlrEnergia": [1000, 2000],
    }).write_csv(path, separator=";")

    parsed = parse_samp_balanco(path, "csv")
    inserted = upsert_samp_balanco_facts(db_conn, parsed, "snap-bal-unresolved")
    assert inserted == 2

    rows = db_conn.execute(text("""
        SELECT DISTINCT distributor_id
        FROM distribution_energy_balance_facts
        WHERE distributor_id LIKE 'unresolved_balance_%'
        ORDER BY distributor_id
    """)).fetchall()
    assert len(rows) == 2

    unresolved_master_rows = db_conn.execute(text("""
        SELECT count(*)
        FROM distribution_distributors
        WHERE status = 'unresolved_source_entity'
    """)).scalar()
    assert unresolved_master_rows == 2


def test_parse_and_upsert_continuity(tmp_path, db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Mock Continuity Actuals
    # CPFL Paulista: 33050196000188
    # 2 sets with different weights (NumCon) to test weighted average calculation
    actuals_data = pl.DataFrame({
        "NumCNPJ": [33050196000188, 33050196000188, 33050196000188, 33050196000188, 33050196000188, 33050196000188],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA"],
        "IdeConjUndConsumidoras": [1, 1, 1, 2, 2, 2],
        "DscConjUndConsumidoras": ["Set 1", "Set 1", "Set 1", "Set 2", "Set 2", "Set 2"],
        "SigIndicador": ["DEC", "FEC", "NumCon", "DEC", "FEC", "NumCon"],
        "AnoIndice": [2025, 2025, 2025, 2025, 2025, 2025],
        "NumPeriodoIndice": [1, 1, 1, 1, 1, 1],
        "VlrIndiceEnviado": ["10,0", "5,0", "1000", "20,0", "8,0", "3000"]  # Decimals as commas
    })
    actuals_file = tmp_path / "mock_actuals.parquet"
    actuals_data.write_parquet(actuals_file)

    # 3. Mock Continuity Limits
    limits_data = pl.DataFrame({
        "NumCNPJ": [33050196000188, 33050196000188, 33050196000188, 33050196000188],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA"],
        "IdeConjUndConsumidoras": [1, 1, 2, 2],
        "DscConjUndConsumidoras": ["Set 1", "Set 1", "Set 2", "Set 2"],
        "SigIndicador": ["DEC", "FEC", "DEC", "FEC"],
        "AnoLimiteQualidade": [2025, 2025, 2025, 2025],
        "VlrLimite": ["8,0", "4,0", "12,0", "6,0"]
    })
    limits_file = tmp_path / "mock_limits.csv"
    limits_data.write_csv(limits_file, separator=";")

    # 4. Mock Continuity Compensations
    compensations_data = pl.DataFrame({
        "NumCNPJ": [33050196000188, 33050196000188, 33050196000188, 33050196000188],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA", "CPFL PAULISTA"],
        "IdeConjUndConsumidoras": [1, 1, 2, 2],
        "DscConjUndConsumidoras": ["Set 1", "Set 1", "Set 2", "Set 2"],
        "SigIndicador": ["QTUCBTNU", "PGUCBTNU", "QTUGBTUA", "PGUGBTUA"],
        "AnoIndice": [2025, 2025, 2025, 2025],
        "NumPeriodoIndice": [1, 1, 1, 1],
        "VlrIndiceEnviado": [10.0, 150.00, 20.0, 450.00]
    })
    compensations_file = tmp_path / "mock_compensations.parquet"
    compensations_data.write_parquet(compensations_file)

    # 5. Ingest facts
    from src.energy_kpi.distribution import (
        parse_continuity_actuals,
        upsert_continuity_actuals_facts,
        parse_continuity_limits,
        upsert_continuity_limits_facts,
        parse_continuity_compensations,
        upsert_continuity_compensations_facts
    )
    
    parsed_act = parse_continuity_actuals(actuals_file, "parquet")
    assert parsed_act.height == 6  # 3 rows * 2 sets
    actuals_inserted = upsert_continuity_actuals_facts(db_conn, parsed_act, "snap-act")
    assert actuals_inserted == 6

    parsed_lim = parse_continuity_limits(limits_file, "csv")
    assert parsed_lim.height == 4
    limits_inserted = upsert_continuity_limits_facts(db_conn, parsed_lim, "snap-lim")
    assert limits_inserted == 4

    parsed_comp = parse_continuity_compensations(compensations_file, "parquet")
    # Groups by set/month: should produce 2 rows (one for set 1, one for set 2)
    assert parsed_comp.height == 2
    comp_inserted = upsert_continuity_compensations_facts(db_conn, parsed_comp, "snap-comp")
    assert comp_inserted == 2

    # Verify compensations count and values
    set1_comp = parsed_comp.filter(pl.col("set_id") == "1").to_dicts()[0]
    assert set1_comp["compensation_count"] == 10.0
    assert set1_comp["compensation_value"] == 150.0

    # 6. Rebuild aggregates
    rebuild_distribution_aggregates(db_conn)

    # Verify monthly weighted aggregates
    monthly = db_conn.execute(text("""
        SELECT distributor_id, reference_month, dec_actual, fec_actual, dec_limit, fec_limit, compensation_count, compensation_value
        FROM distribution_monthly_aggregates
        WHERE distributor_id = 'cpfl_paulista'
    """)).fetchone()

    assert monthly is not None
    # Weighted Actuals:
    # DEC: (10.0 * 1000 + 20.0 * 3000) / (1000 + 3000) = (10000 + 60000) / 4000 = 70000 / 4000 = 17.5
    # FEC: (5.0 * 1000 + 8.0 * 3000) / 4000 = (5000 + 24000) / 4000 = 29000 / 4000 = 7.25
    assert monthly[2] == 17.5
    assert monthly[3] == 7.25

    # Weighted Limits:
    # DEC Limit: (8.0 * 1000 + 12.0 * 3000) / 4000 = (8000 + 36000) / 4000 = 44000 / 4000 = 11.0
    # FEC Limit: (4.0 * 1000 + 6.0 * 3000) / 4000 = (4000 + 18000) / 4000 = 22000 / 4000 = 5.5
    assert monthly[4] == 11.0
    assert monthly[5] == 5.5

    # Compensations (sum of both sets):
    # Count: 10 + 20 = 30
    # Value: 150 + 450 = 600
    assert monthly[6] == 30
    assert monthly[7] == 600.0

    # Verify annual weighted aggregates
    annual = db_conn.execute(text("""
        SELECT distributor_id, reference_year, dec_actual, fec_actual, dec_limit, fec_limit, compensation_count, compensation_value
        FROM distribution_annual_aggregates
        WHERE distributor_id = 'cpfl_paulista'
    """)).fetchone()

    assert annual is not None
    assert annual[2] == 17.5
    assert annual[3] == 7.25
    assert annual[4] == 11.0
    assert annual[5] == 5.5
    assert annual[6] == 30
    assert annual[7] == 600.0


def test_parse_and_upsert_tariffs_delinquency(tmp_path, db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Construct mock Tariffs data
    # CPFL Paulista: 33050196000188
    # Neoenergia Coelba: 15139629000194
    tariffs_data = pl.DataFrame({
        "NumCNPJ": ["33050196000188", "15139629000194"],
        "NomAgenteRegulado": ["CPFL PAULISTA", "COELBA"],
        "NumResolucao": ["REH 3000/2025", "REH 3001/2025"],
        "DatInicioVigencia": ["2025-01-01", "01/02/2025"],
        "DatFimVigencia": ["2025-12-31", "31/12/2025"],
        "DscBaseTarifaria": ["Tarifa de Aplicação", "Tarifa de Aplicação"],
        "NomSubgrupo": ["B1", "B1"],
        "NomModalidade": ["Residencial", "Residencial"],
        "NomClasse": ["Residencial", "Residencial"],
        "NomSubclasse": ["Residencial", "Residencial"],
        "DscDetalhe": ["Não se aplica", "Não se aplica"],
        "NomPostoTarifario": ["Não se aplica", "Não se aplica"],
        "NomUnidadeMedida": ["R$/MWh", "R$/MWh"],
        "VlrTUSD": ["150,50", "180.00"],
        "VlrTE": ["120,40", "110.00"]
    })
    tariffs_file = tmp_path / "mock_tariffs.csv"
    tariffs_data.write_csv(tariffs_file, separator=";")

    # 3. Construct mock Delinquency data
    # CPFL Paulista: 33050196000188
    delinquency_data = pl.DataFrame({
        "NumCNPJ": ["33050196000188", "33050196000188"],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA"],
        "SigIndicador": ["ITot1", "ITot1"],
        "AnoIndice": [2025, 2025],
        "NumPeriodoIndice": [1, 2],
        "VlrIndiceEnviado": ["0,025", "0,035"]  # 2.5% and 3.5%
    })
    delinquency_file = tmp_path / "mock_delinquency.csv"
    delinquency_data.write_csv(delinquency_file, separator=";")

    # 4. Ingest and parse
    from src.energy_kpi.distribution import (
        parse_tariffs,
        upsert_tariffs_facts,
        parse_delinquency,
        upsert_delinquency_facts
    )

    parsed_tariffs = parse_tariffs(tariffs_file, "csv")
    assert parsed_tariffs.height == 2
    tariffs_inserted = upsert_tariffs_facts(db_conn, parsed_tariffs, "snap-tar")
    assert tariffs_inserted == 2

    parsed_delinquency = parse_delinquency(delinquency_file, "csv")
    assert parsed_delinquency.height == 2
    delinquency_inserted = upsert_delinquency_facts(db_conn, parsed_delinquency, "snap-del")
    assert delinquency_inserted == 2

    # Verify facts tables
    t_count = db_conn.execute(text("SELECT count(*) FROM distribution_tariff_facts")).scalar()
    assert t_count == 2
    d_count = db_conn.execute(text("SELECT count(*) FROM distribution_delinquency_facts")).scalar()
    assert d_count == 2

    # Add mock revenue to CPFL Paulista monthly aggregates to test delinquency weighting
    db_conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (aggregate_id, distributor_id, reference_month, revenue_brl)
        VALUES ('cpfl_paulista_2025-01', 'cpfl_paulista', '2025-01', 100000.0)
    """))
    db_conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (aggregate_id, distributor_id, reference_month, revenue_brl)
        VALUES ('cpfl_paulista_2025-02', 'cpfl_paulista', '2025-02', 200000.0)
        ON CONFLICT(aggregate_id) DO UPDATE SET revenue_brl = excluded.revenue_brl
    """))

    # 5. Rebuild aggregates
    rebuild_distribution_aggregates(db_conn)

    # Check monthly delinquency
    m_del = db_conn.execute(text("""
        SELECT reference_month, delinquency_pct FROM distribution_monthly_aggregates
        WHERE distributor_id = 'cpfl_paulista' ORDER BY reference_month
    """)).fetchall()
    assert len(m_del) == 2
    assert m_del[0][0] == "2025-01"
    assert m_del[0][1] == 0.025
    assert m_del[1][0] == "2025-02"
    assert m_del[1][1] == 0.035

    # Check annual delinquency (weighted by revenue)
    # (0.025 * 100000.0 + 0.035 * 200000.0) / (100000.0 + 200000.0)
    # = (2500 + 7000) / 300000 = 9500 / 300000 = 0.0316666...
    ann_del = db_conn.execute(text("""
        SELECT reference_year, delinquency_pct FROM distribution_annual_aggregates
        WHERE distributor_id = 'cpfl_paulista'
    """)).fetchone()
    assert ann_del is not None
    assert ann_del[0] == 2025
    assert abs(ann_del[1] - 0.0316666) < 1e-5

    # Test Domain Constraint (ValueError raised on unregistered target delinquency indicators)
    db_conn.execute(text("DELETE FROM distribution_delinquency_indicators WHERE indicator_code = 'ITot1'"))
    with pytest.raises(ValueError) as excinfo:
        upsert_delinquency_facts(db_conn, parsed_delinquency, "snap-del-err")
    assert "Blocking Ingestion" in str(excinfo.value)


def test_delinquency_publishes_registered_aging_total_and_support_codes(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_delinquency, upsert_delinquency_facts

    path = tmp_path / "delinquency-all-scope.csv"
    pl.DataFrame({
        "NumCNPJ": ["15139629000194", "15139629000194", "15139629000194", "15139629000194"],
        "SigAgente": ["COELBA", "COELBA", "COELBA", "COELBA"],
        "SigIndicador": ["ITot1", "ITot18", "ICom6", "ITotCrt"],
        "AnoIndice": [2025, 2025, 2025, 2025],
        "NumPeriodoIndice": [1, 1, 1, 1],
        "VlrIndiceEnviado": ["0,01", "0,18", "0,06", "10"],
    }).write_csv(path, separator=";")

    parsed = parse_delinquency(path, "csv")
    assert upsert_delinquency_facts(db_conn, parsed, "snap-del-all") == 4

    facts = db_conn.execute(text("""
        SELECT indicator_code, actual_value
        FROM distribution_delinquency_facts
        ORDER BY indicator_code
    """)).fetchall()
    assert [row[0] for row in facts] == ["ICom6", "ITot1", "ITot18", "ITotCrt"]

    lead_count = db_conn.execute(text("""
        SELECT count(*)
        FROM distribution_delinquency_indicators
        WHERE is_lead_kpi = 1 AND analytical_category = 'total_delinquency'
    """)).scalar()
    assert lead_count == 7


def test_delinquency_unknown_code_blocks_ingestion(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_delinquency, upsert_delinquency_facts

    path = tmp_path / "delinquency-unknown.csv"
    pl.DataFrame({
        "NumCNPJ": ["15139629000194"],
        "SigAgente": ["COELBA"],
        "SigIndicador": ["UNKNOWN_CODE"],
        "AnoIndice": [2025],
        "NumPeriodoIndice": [1],
        "VlrIndiceEnviado": ["0,01"],
    }).write_csv(path, separator=";")

    parsed = parse_delinquency(path, "csv")
    with pytest.raises(ValueError, match="UNKNOWN_CODE"):
        upsert_delinquency_facts(db_conn, parsed, "snap-del-unknown")


def _real_shape_tariff_frame(cnpjs: list[str | None]) -> pl.DataFrame:
    return pl.DataFrame({
        "DatGeracaoConjuntoDados": ["2026-01-01"] * len(cnpjs),
        "DscREH": [f"REH {3000 + i}/2026" for i in range(len(cnpjs))],
        "SigAgente": ["CPFL PAULISTA"] * len(cnpjs),
        "NumCNPJDistribuidora": cnpjs,
        "DatInicioVigencia": ["2026-01-01"] * len(cnpjs),
        "DatFimVigencia": ["2026-12-31"] * len(cnpjs),
        "tariff_base": ["Tarifa de Aplicação"] * len(cnpjs),
        "DscSubGrupo": ["B1"] * len(cnpjs),
        "DscModalidadeTarifaria": ["Convencional"] * len(cnpjs),
        "DscClasse": ["Residencial"] * len(cnpjs),
        "DscSubClasse": ["Residencial"] * len(cnpjs),
        "consumer_detail": ["Não se aplica"] * len(cnpjs),
        "tariff_period": ["Não se aplica"] * len(cnpjs),
        "DscUnidadeTerciaria": ["R$/MWh"] * len(cnpjs),
        "SigAgenteAcessante": [None] * len(cnpjs),
        "tusd_raw": ["150,50"] * len(cnpjs),
        "te_raw": ["120,40"] * len(cnpjs),
        "UnexpectedColumn": ["schema drift"] * len(cnpjs),
    })


def test_parse_tariffs_real_aneel_shape_maps_distributor_cnpj(tmp_path):
    from src.energy_kpi.distribution import parse_tariffs

    path = tmp_path / "tarifas-real-shape.csv"
    _real_shape_tariff_frame(["15.139.629/0001-94", "6272793000184", None, "12345"]).write_csv(
        path, separator=";"
    )

    parsed = parse_tariffs(path, "csv")

    assert parsed.height == 4
    assert parsed["normalized_cnpj"].to_list() == [
        "15139629000194",
        "06272793000184",
        None,
        None,
    ]
    assert parsed["raw_name"].to_list() == ["CPFL PAULISTA"] * 4
    assert parsed["subgroup"].to_list() == ["B1"] * 4
    assert parsed["tusd_value"].to_list() == [150.5] * 4
    assert "UnexpectedColumn" not in parsed.columns


def test_parse_tariffs_real_aneel_shape_parquet(tmp_path):
    from src.energy_kpi.distribution import parse_tariffs

    path = tmp_path / "tarifas-real-shape.parquet"
    _real_shape_tariff_frame(["33050196000188"]).write_parquet(path)

    parsed = parse_tariffs(path, "parquet")

    assert parsed.height == 1
    assert parsed.to_dicts()[0]["normalized_cnpj"] == "33050196000188"
    assert parsed.to_dicts()[0]["unit"] == "R$/MWh"


def test_parse_tariffs_accepts_canonical_input_contract(tmp_path):
    from src.energy_kpi.distribution import parse_tariffs

    path = tmp_path / "tarifas-canonical.csv"
    pl.DataFrame({
        "raw_cnpj": ["33050196000188"],
        "raw_name": ["CPFL PAULISTA"],
        "resolution_title": ["REH 3000/2026"],
        "valid_from": ["2026-01-01"],
        "valid_to": ["2026-12-31"],
        "tariff_base": ["Tarifa de Aplicação"],
        "subgroup": ["B1"],
        "modality": ["Convencional"],
        "consumer_class": ["Residencial"],
        "consumer_subclass": ["Residencial"],
        "consumer_detail": ["Não se aplica"],
        "tariff_period": ["Não se aplica"],
        "unit": ["R$/MWh"],
        "tusd_raw": ["150.50"],
        "te_raw": ["120.40"],
    }).write_csv(path, separator=";")

    parsed = parse_tariffs(path, "csv")

    assert parsed.height == 1
    assert parsed.to_dicts()[0]["normalized_cnpj"] == "33050196000188"


def test_parse_tariffs_missing_cnpj_alias_reports_schema_contract(tmp_path):
    from src.energy_kpi.distribution.ingest import DistributionSchemaError, parse_tariffs

    path = tmp_path / "tarifas-missing-cnpj.csv"
    df = _real_shape_tariff_frame(["33050196000188"]).drop("NumCNPJDistribuidora")
    df.write_csv(path, separator=";")

    with pytest.raises(DistributionSchemaError) as excinfo:
        parse_tariffs(path, "csv")

    message = str(excinfo.value)
    assert "Tarifas de Aplicacao parser canonicalization failed" in message
    assert "raw_cnpj" in message
    assert "Available columns" in message


def test_tariff_business_key_rejects_same_dimension_conflicting_values(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_tariffs, upsert_tariffs_facts

    path = tmp_path / "tariff-conflicting-values.csv"
    base = _real_shape_tariff_frame(["33050196000188", "33050196000188", "33050196000188"])
    base = base.with_columns([
        pl.Series("DscREH", ["REH 3000/2026", "REH 3000/2026", "REH 3000/2026"]),
        pl.Series("tusd_raw", ["1,00", "2,00", "2,00"]),
        pl.Series("te_raw", ["0,00", "0,00", "0,00"]),
    ])
    base.write_csv(path, separator=";")

    parsed = parse_tariffs(path, "csv")
    assert parsed.height == 3
    assert parsed.select("business_key_hash").unique().height == 1
    assert parsed.select("source_row_hash").unique().height == 2

    upsert_tariffs_facts(db_conn, parsed, "snap-tar-conflict")
    stored = db_conn.execute(text("SELECT count(*) FROM distribution_tariff_facts")).scalar()
    assert stored == 0
    quarantined = db_conn.execute(text("SELECT count(*) FROM distribution_tariff_conflicts")).scalar()
    assert quarantined == 2


def test_continuity_actuals_exact_duplicate_collapses_without_conflict(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_continuity_actuals, upsert_continuity_actuals_facts

    path = tmp_path / "continuity-duplicate.csv"
    pl.DataFrame({
        "NumCNPJ": ["33050196000188", "33050196000188"],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA"],
        "IdeConjUndConsumidoras": ["123", "123"],
        "DscConjUndConsumidoras": ["Set A", "Set A"],
        "SigIndicador": ["NumCon", "NumCon"],
        "AnoIndice": [2025, 2025],
        "NumPeriodoIndice": [6, 6],
        "VlrIndiceEnviado": ["100,0", "100,0"],
    }).write_csv(path, separator=";")

    parsed = parse_continuity_actuals(path, "csv")
    assert parsed.height == 2
    assert parsed.select(["normalized_cnpj", "set_id", "indicator_code", "reference_month"]).unique().height == 1

    upsert_continuity_actuals_facts(db_conn, parsed, "snap-cont-dupe")
    stored = db_conn.execute(text("SELECT count(*) FROM distribution_continuity_facts")).scalar()
    assert stored == 1


def test_parse_continuity_actuals_from_zip_wrapped_csv(tmp_path):
    from src.energy_kpi.distribution import parse_continuity_actuals

    csv_bytes = (
        '"DatGeracaoConjuntoDados";"IdeConjUndConsumidoras";"DscConjUndConsumidoras";'
        '"SigAgente";"NumCNPJ";"SigIndicador";"AnoIndice";"NumPeriodoIndice";"VlrIndiceEnviado"\r\n'
        '"2026-07-05";"12591";"Set A";"EAC";"04065033000170";"DEC";"2026";"4";"1,57"\r\n'
    ).encode("utf-8")
    path = tmp_path / "indicadores-continuidade-coletivos-2020-2029.csv"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("indicadores-continuidade-coletivos-2020-2029.csv", csv_bytes)

    parsed = parse_continuity_actuals(path, "csv")

    assert parsed.height == 1
    row = parsed.to_dicts()[0]
    assert row["normalized_cnpj"] == "04065033000170"
    assert row["indicator_code"] == "DEC"
    assert row["reference_month"] == "2026-04"
    assert row["actual_value"] == 1.57


def test_parse_and_upsert_mmgd(tmp_path, db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Construct mock MMGD data
    # CPFL Paulista: 33050196000188
    # Has personal data that needs to be stripped
    mmgd_data = pl.DataFrame({
        "NumCNPJDistribuidora": ["33050196000188", "33050196000188"],
        "SigAgente": ["CPFL PAULISTA", "CPFL PAULISTA"],
        "CodEmpreendimento": ["GD-1", "GD-2"],
        "NomMunicipio": ["Campinas", "Campinas"],
        "SigUF": ["SP", "SP"],
        "SigTipoGeracao": ["Solar", "Solar"],
        "DscFonteGeracao": ["Radiação solar", "Radiação solar"],
        "DscPorte": ["Microgeração", "Minigeração"],
        "NumCoordNEmpreendimento": [-22.9, -22.91],
        "NumCoordEEmpreendimento": [-47.06, -47.05],
        "DthAtualizaCadastralEmpreend": ["2025-01-15", "2025-02-10"],
        "AnmPeriodoReferencia": ["2025-01", "2025-02"],
        "MdaPotenciaInstaladaKW": ["10,5", "75.0"],
        "QtdUCRecebeCredito": [1, 5],
        "NumCPFCNPJ": ["12345678901", "98765432109"],
        "NomTitularEmpreendimento": ["Fulano de Tal", "Beltrano de Tal"]
    })
    mmgd_file = tmp_path / "mock_mmgd.csv"
    mmgd_data.write_csv(mmgd_file, separator=";")

    # 3. Parse MMGD
    from src.energy_kpi.distribution import parse_mmgd, upsert_mmgd_facts
    parsed_df = parse_mmgd(mmgd_file, format_type="csv")
    
    # Check that personal data is stripped
    assert "NumCPFCNPJ" not in parsed_df.columns
    assert "NomTitularEmpreendimento" not in parsed_df.columns
    
    # Verify dimensions are parsed
    assert parsed_df.height == 2
    row1 = parsed_df.filter(pl.col("project_id") == "GD-1").to_dicts()[0]
    assert row1["installed_capacity_kw"] == 10.5
    assert row1["beneficiary_units_count"] == 1
    assert row1["reference_month"] == "2025-01"

    # 4. Ingest to DB
    inserted = upsert_mmgd_facts(db_conn, parsed_df, "snap-mmgd")
    assert inserted == 2

    # Check project dimension table
    projs = db_conn.execute(text("SELECT project_id, distributor_id, size_category FROM distribution_mmgd_projects ORDER BY project_id")).fetchall()
    assert len(projs) == 2
    assert projs[0][0] == "GD-1"
    assert projs[0][1] == "cpfl_paulista"
    assert projs[0][2] == "Microgeração"

    # Check snapshots table
    snaps = db_conn.execute(text("SELECT project_id, reference_month, installed_capacity_kw FROM distribution_mmgd_project_snapshots ORDER BY project_id")).fetchall()
    assert len(snaps) == 2
    assert snaps[0][0] == "GD-1"
    assert snaps[0][1] == "2025-01"
    assert snaps[0][2] == 10.5

    # 5. Rebuild aggregates
    rebuild_distribution_aggregates(db_conn)

    # Check monthly aggregates
    # GD-1 is active in 2025-01 (capacity 10.5)
    # GD-2 is active in 2025-02 (capacity 75.0)
    m_agg = db_conn.execute(text("""
        SELECT reference_month, mmgd_projects_count, mmgd_capacity_kw FROM distribution_monthly_aggregates
        WHERE distributor_id = 'cpfl_paulista' ORDER BY reference_month
    """)).fetchall()
    
    # Filter only months with data (since cpfl_paulista has 2025-01 and 2025-02 from our delinquency test too)
    m_agg_filtered = [r for r in m_agg if r[1] is not None]
    assert len(m_agg_filtered) == 2
    assert m_agg_filtered[0][0] == "2025-01"
    assert m_agg_filtered[0][1] == 1
    assert m_agg_filtered[0][2] == 10.5
    
    assert m_agg_filtered[1][0] == "2025-02"
    assert m_agg_filtered[1][1] == 1
    assert m_agg_filtered[1][2] == 75.0

    # Check annual aggregates (end-of-period stock)
    # Stock in 2025 should be from the latest month (2025-02), which has 1 project and 75.0 capacity
    ann_agg = db_conn.execute(text("""
        SELECT reference_year, mmgd_projects_count, mmgd_capacity_kw FROM distribution_annual_aggregates
        WHERE distributor_id = 'cpfl_paulista'
    """)).fetchone()
    assert ann_agg is not None
    assert ann_agg[0] == 2025
    assert ann_agg[1] == 1
    assert ann_agg[2] == 75.0


def test_mmgd_unchanged_new_reference_month_does_not_duplicate_history(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_mmgd, upsert_mmgd_facts

    base = {
        "NumCNPJDistribuidora": ["33050196000188"],
        "SigAgente": ["CPFL PAULISTA"],
        "CodEmpreendimento": ["GD-1"],
        "NomMunicipio": ["Campinas"],
        "SigUF": ["SP"],
        "SigTipoGeracao": ["Solar"],
        "DscFonteGeracao": ["Radiação solar"],
        "DscPorte": ["Microgeração"],
        "NumCoordNEmpreendimento": [-22.9],
        "NumCoordEEmpreendimento": [-47.06],
        "DthAtualizaCadastralEmpreend": ["2025-01-15"],
        "MdaPotenciaInstaladaKW": ["10,5"],
        "QtdUCRecebeCredito": [1],
    }
    first = tmp_path / "mmgd-2025-01.csv"
    second = tmp_path / "mmgd-2025-02.csv"
    changed = tmp_path / "mmgd-2025-03.csv"
    pl.DataFrame({**base, "AnmPeriodoReferencia": ["2025-01"]}).write_csv(first, separator=";")
    pl.DataFrame({**base, "AnmPeriodoReferencia": ["2025-02"]}).write_csv(second, separator=";")
    pl.DataFrame({**base, "AnmPeriodoReferencia": ["2025-03"], "MdaPotenciaInstaladaKW": ["12,0"]}).write_csv(changed, separator=";")

    upsert_mmgd_facts(db_conn, parse_mmgd(first, "csv"), "snap-1")
    upsert_mmgd_facts(db_conn, parse_mmgd(second, "csv"), "snap-2")
    unchanged_count = db_conn.execute(text("SELECT count(*) FROM distribution_mmgd_project_snapshots")).scalar()
    assert unchanged_count == 1

    upsert_mmgd_facts(db_conn, parse_mmgd(changed, "csv"), "snap-3")
    changed_count = db_conn.execute(text("SELECT count(*) FROM distribution_mmgd_project_snapshots")).scalar()
    assert changed_count == 2


def test_distribution_aggregates_use_mmgd_monthly_mart_without_detail_tables(db_conn):
    db_conn.execute(
        text(
            """
            INSERT INTO distribution_mmgd_monthly_mart (
                distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw,
                source_snapshot_id, source_row_count
            )
            VALUES ('cpfl_paulista', '2026-06', 2, 85.5, 'snap-mmgd-managed', 2)
            """
        )
    )

    rebuild_distribution_aggregates(db_conn)

    monthly = db_conn.execute(
        text(
            """
            SELECT mmgd_projects_count, mmgd_capacity_kw
            FROM distribution_monthly_aggregates
            WHERE distributor_id = 'cpfl_paulista' AND reference_month = '2026-06'
            """
        )
    ).fetchone()
    assert monthly == (2, 85.5)

    annual = db_conn.execute(
        text(
            """
            SELECT mmgd_projects_count, mmgd_capacity_kw
            FROM distribution_annual_aggregates
            WHERE distributor_id = 'cpfl_paulista' AND reference_year = 2026
            """
        )
    ).fetchone()
    assert annual == (2, 85.5)


def test_distribution_aggregate_slices_refresh_only_requested_metrics(db_conn):
    from src.energy_kpi.distribution.aggregates import rebuild_distribution_aggregate_slices

    seed_distribution_static_data(db_conn)
    db_conn.execute(text("""
        INSERT INTO distribution_market_facts (
            fact_id, distributor_id, reference_month, metric_name, raw_value,
            normalized_value, original_unit, normalized_unit, source_row_hash, snapshot_id
        )
        VALUES (
            'market-cpfl-2026-06', 'cpfl_paulista', '2026-06', 'revenue',
            1000.0, 1000.0, 'R$', 'BRL', 'market-hash', 'snap-market'
        )
    """))
    db_conn.execute(text("""
        INSERT INTO distribution_mmgd_monthly_mart (
            distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw,
            source_snapshot_id, source_row_count
        )
        VALUES ('cpfl_paulista', '2026-06', 2, 85.5, 'snap-mmgd-managed', 2)
    """))

    rebuild_distribution_aggregate_slices(db_conn, ["mmgd"])

    monthly = db_conn.execute(text("""
        SELECT revenue_brl, mmgd_projects_count, mmgd_capacity_kw
        FROM distribution_monthly_aggregates
        WHERE distributor_id = 'cpfl_paulista' AND reference_month = '2026-06'
    """)).fetchone()
    assert monthly == (None, 2, 85.5)

    rebuild_distribution_aggregate_slices(db_conn, ["market"])

    monthly = db_conn.execute(text("""
        SELECT revenue_brl, mmgd_projects_count, mmgd_capacity_kw
        FROM distribution_monthly_aggregates
        WHERE distributor_id = 'cpfl_paulista' AND reference_month = '2026-06'
    """)).fetchone()
    assert monthly == (1000.0, 2, 85.5)


def test_group_series_consolidation(db_conn):
    # 1. Seed static master data
    seed_distribution_static_data(db_conn)

    # 2. Insert mock monthly aggregates for both CPFL Paulista and CPFL Piratininga
    db_conn.execute(text("""
        INSERT INTO distribution_monthly_aggregates (
            aggregate_id, distributor_id, reference_month, billed_energy_mwh, revenue_brl, dec_actual, fec_actual, dec_limit, fec_limit, delinquency_pct
        )
        VALUES 
            ('cpfl_paulista_2025-01', 'cpfl_paulista', '2025-01', 1000.0, 100000.0, 5.0, 3.0, 6.0, 4.0, 0.02),
            ('cpfl_piratininga_2025-01', 'cpfl_piratininga', '2025-01', 2000.0, 300000.0, 10.0, 6.0, 8.0, 5.0, 0.04)
    """))

    # 3. Insert mock continuity weights (NumCon) to test weighted average calculation
    db_conn.execute(text("""
        INSERT INTO distribution_continuity_facts (
            fact_id, distributor_id, set_id, reference_month, indicator_code, actual_value, source_row_hash, snapshot_id
        )
        VALUES
            ('weight_paulista', 'cpfl_paulista', 'set1', '2025-01', 'NumCon', 10000.0, 'h1', 's1'),
            ('weight_piratininga', 'cpfl_piratininga', 'set1', '2025-01', 'NumCon', 30000.0, 'h2', 's1')
    """))

    db_conn.execute(text("""
        INSERT INTO distribution_tariff_facts (
            fact_id, distributor_id, valid_from, valid_to, subgroup, consumer_class,
            unit, tusd_value, te_value, source_row_hash, snapshot_id
        )
        VALUES
            ('tariff_paulista', 'cpfl_paulista', '2025-01-01', '2025-12-31', 'B1', 'Residencial', 'MWh', 40.0, 10.0, 't1', 's1'),
            ('tariff_piratininga', 'cpfl_piratininga', '2025-01-01', '2025-12-31', 'B1', 'Residencial', 'MWh', 80.0, 30.0, 't2', 's1')
    """))

    # 4. Retrieve group series using DistributionReadService
    from src.energy_kpi.distribution.read import DistributionReadService
    from unittest.mock import MagicMock
    mock_settings = MagicMock()
    read_service = DistributionReadService(mock_settings)
    
    class MockConnContext:
        def __enter__(self):
            return db_conn
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = lambda: MockConnContext()
    read_service._engine = MagicMock(return_value=mock_engine)

    # Query group 'cpfl' series
    series = read_service.get_series(entity_type="group", entity_id="cpfl", frequency="monthly")
    assert len(series) == 1
    row = series[0]
    
    assert row["period"] == "2025-01"
    # Billed energy: 1000.0 + 2000.0 = 3000.0
    assert row["billed_energy_mwh"] == 3000.0
    # Revenue: 100000.0 + 300000.0 = 400000.0
    assert row["revenue_brl"] == 400000.0
    
    # DEC Actual (weighted by consumers: 10000 for paulista, 30000 for piratininga):
    # (5.0 * 10000 + 10.0 * 30000) / (10000 + 30000) = (50000 + 300000) / 40000 = 350000 / 40000 = 8.75
    assert row["dec_actual"] == 8.75
    # FEC Actual: (3.0 * 10000 + 6.0 * 30000) / 40000 = (30000 + 180000) / 40000 = 210000 / 40000 = 5.25
    assert row["fec_actual"] == 5.25
    
    # DEC Limit: (6.0 * 10000 + 8.0 * 30000) / 40000 = (60000 + 240000) / 40000 = 300000 / 40000 = 7.5
    assert row["dec_limit"] == 7.5
    # FEC Limit: (4.0 * 10000 + 5.0 * 30000) / 40000 = (40000 + 150000) / 40000 = 190000 / 40000 = 4.75
    assert row["fec_limit"] == 4.75

    # Delinquency Percentage (weighted by revenue: 100000.0 for paulista, 300000.0 for piratininga):
    # (0.02 * 100000.0 + 0.04 * 300000.0) / (100000.0 + 300000.0)
    # = (2000 + 12000) / 400000 = 14000 / 400000 = 0.035
    assert row["delinquency_pct"] == 0.035
    assert row["te_homologated"] == 20.0
    assert row["tusd_homologated"] == 60.0

    distributor_series = read_service.get_series(
        entity_type="distributor",
        entity_id="cpfl_paulista",
        frequency="monthly",
    )
    assert distributor_series[0]["te_homologated"] == 10.0
    assert distributor_series[0]["tusd_homologated"] == 40.0


def test_mmgd_incremental_and_removal_behaviors(tmp_path, db_conn):
    seed_distribution_static_data(db_conn)
    from src.energy_kpi.distribution import parse_mmgd, upsert_mmgd_facts

    base = {
        "NumCNPJDistribuidora": ["33050196000188"],
        "SigAgente": ["CPFL PAULISTA"],
        "CodEmpreendimento": ["GD-M1"],
        "NomMunicipio": ["Campinas"],
        "SigUF": ["SP"],
        "SigTipoGeracao": ["Solar"],
        "DscFonteGeracao": ["Radiação solar"],
        "DscPorte": ["Microgeração"],
        "NumCoordNEmpreendimento": [-22.9],
        "NumCoordEEmpreendimento": [-47.06],
        "DthAtualizaCadastralEmpreend": ["2025-01-15"],
        "MdaPotenciaInstaladaKW": ["10,5"],
        "QtdUCRecebeCredito": [1],
    }

    # 1. First snapshot: one active project GD-M1
    f1 = tmp_path / "mmgd-f1.csv"
    pl.DataFrame({**base, "AnmPeriodoReferencia": ["2025-01"]}).write_csv(f1, separator=";")
    res1 = upsert_mmgd_facts(db_conn, parse_mmgd(f1, "csv"), "snap-f1", is_full_snapshot=True)
    assert res1 == 1
    assert getattr(res1, "stats", {}).get("rows_inserted") == 1

    # Check database status
    p1 = db_conn.execute(text("SELECT status, deactivated_at_month FROM distribution_mmgd_projects WHERE project_id = 'GD-M1'")).fetchone()
    assert p1[0] == "active"
    assert p1[1] is None

    # 2. Second snapshot (partial): does NOT remove GD-M1 because is_full_snapshot=False
    f2 = tmp_path / "mmgd-f2.csv"
    pl.DataFrame({**base, "CodEmpreendimento": ["GD-M2"], "AnmPeriodoReferencia": ["2025-01"]}).write_csv(f2, separator=";")
    res2 = upsert_mmgd_facts(db_conn, parse_mmgd(f2, "csv"), "snap-f2", is_full_snapshot=False)
    assert res2 == 1

    # GD-M1 should still be active because the snapshot was partial
    p1 = db_conn.execute(text("SELECT status FROM distribution_mmgd_projects WHERE project_id = 'GD-M1'")).fetchone()
    assert p1[0] == "active"

    # 3. Third snapshot (full): GD-M1 is missing, so it should be deactivated
    f3 = tmp_path / "mmgd-f3.csv"
    pl.DataFrame({**base, "CodEmpreendimento": ["GD-M2"], "AnmPeriodoReferencia": ["2025-02"]}).write_csv(f3, separator=";")
    res3 = upsert_mmgd_facts(db_conn, parse_mmgd(f3, "csv"), "snap-f3", is_full_snapshot=True)
    
    # GD-M1 should now be inactive
    p1 = db_conn.execute(text("SELECT status, deactivated_at_month, deactivation_reason FROM distribution_mmgd_projects WHERE project_id = 'GD-M1'")).fetchone()
    assert p1[0] == "inactive"
    assert p1[1] == "2025-02"
    assert p1[2] == "removed_from_snapshot"

    # 4. Fourth snapshot (full): GD-M1 returns, so it should be reactivated
    res4 = upsert_mmgd_facts(db_conn, parse_mmgd(f1, "csv"), "snap-f4", is_full_snapshot=True)
    p1 = db_conn.execute(text("SELECT status, deactivated_at_month, deactivation_reason FROM distribution_mmgd_projects WHERE project_id = 'GD-M1'")).fetchone()
    assert p1[0] == "active"
    assert p1[1] is None
