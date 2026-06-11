import pytest
from sqlalchemy import create_engine
from src.financials.resolver import ModelResolver
from src.financials.excel_mapping import ensure_excel_mapping_tables_for_connection, ModelMappingEntry


def test_resolver_tables_initialization():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    assert resolver.get_overrides(1234) == {}
    assert resolver.get_aliases() == []


def test_resolver_override_persistence():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    resolver.save_override(
        company_id=1234,
        target_id="DRE:3.01",
        period_label="2024",
        source_code="3.01.01",
        source_desc="Receita Bruta",
        sign=1
    )
    
    overrides = resolver.get_overrides(1234)
    assert "DRE:3.01" in overrides
    assert overrides["DRE:3.01"]["2024"]["source_code"] == "3.01.01"
    assert overrides["DRE:3.01"]["2024"]["source_desc"] == "Receita Bruta"
    assert overrides["DRE:3.01"]["2024"]["sign"] == 1

    resolver.delete_override(1234, "DRE:3.01", "2024")
    assert resolver.get_overrides(1234) == {}


def test_resolver_alias_and_exclusions():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    resolver.add_alias("COMP:DA", "depreciacao e amortizacao", "positive")
    resolver.add_alias("COMP:DA", "depreciacoes", "positive")
    resolver.add_alias("DRE:3.01", "receitas financeiras", "negative")
    
    aliases = resolver.get_aliases()
    assert len(aliases) == 3
    assert any(a["target_id"] == "DRE:3.01" and a["match_type"] == "negative" for a in aliases)


def test_resolver_scoring_rules():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    resolver.add_alias("DRE:3.01", "receita bruta de vendas", "positive")
    resolver.add_alias("DRE:3.01", "receita financeira", "negative")
    
    aliases = resolver.get_aliases()

    # Case 1: Exact code match
    cand1 = {"CD_CONTA": "3.01", "LINE_ID_BASE": "3.01", "DS_CONTA": "Receita Liquida"}
    score, evidence, warnings = resolver.score_candidate(cand1, "DRE:3.01", "Revenue", aliases)
    assert score == 95.0
    assert "Exact account code match" in evidence[0]

    # Case 2: Negative alias match (Exclusion)
    cand2 = {"CD_CONTA": "3.02", "LINE_ID_BASE": "3.02", "DS_CONTA": "Receita Financeira"}
    score, evidence, warnings = resolver.score_candidate(cand2, "DRE:3.01", "Revenue", aliases)
    assert score == 0.0
    assert "Rejected" in warnings[0]

    # Case 3: Positive alias exact match
    cand3 = {"CD_CONTA": "3.01.01", "LINE_ID_BASE": "3.01.01", "DS_CONTA": "Receita Bruta de Vendas"}
    score, evidence, warnings = resolver.score_candidate(cand3, "DRE:3.01", "Revenue", aliases)
    assert score == 85.0
    assert "Exact match on positive alias" in evidence[0]


def test_resolver_period_resolution():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    
    entry = ModelMappingEntry(
        target_id="DRE:3.01",
        target_label="Revenue",
        group="Income Statement",
        statement_type="DRE",
        display_order=1
    )
    
    raw_rows = [
        {"CD_CONTA": "3.01", "LINE_ID_BASE": "3.01", "DS_CONTA": "Receita Liquida", "2024": 150000.0, "2025": None},
        {"CD_CONTA": "3.01.01", "LINE_ID_BASE": "3.01.01", "DS_CONTA": "Receita Liquida de Servicos", "2024": None, "2025": 180000.0},
    ]
    
    # Resolve for 2024
    res_2024 = resolver.resolve_entry_for_period(
        company_id=1234,
        entry=entry,
        period="2024",
        raw_statement_rows=raw_rows,
        overrides={},
        aliases=[]
    )
    assert res_2024["selected_source_id"] == "DRE:3.01"
    assert res_2024["resolved_value"] == 150.0

    # Resolve for 2025
    res_2025 = resolver.resolve_entry_for_period(
        company_id=1234,
        entry=entry,
        period="2025",
        raw_statement_rows=raw_rows,
        overrides={},
        aliases=[]
    )
    assert res_2025["selected_source_id"] == "DRE:3.01.01"
    assert res_2025["resolved_value"] == 180.0


def test_resolver_restrict_to_sources():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    
    from src.financials.excel_mapping import ModelMappingSource
    
    entry = ModelMappingEntry(
        target_id="DRE:3.01",
        target_label="Revenue",
        group="Income Statement",
        statement_type="DRE",
        display_order=1,
        sources=(
            ModelMappingSource(
                statement_type="DRE",
                line_id_base="3.01",
                cd_conta="3.01",
                label_snapshot="Receita Liquida",
                sign=1,
                position=0,
            ),
        )
    )
    
    raw_rows = [
        {"CD_CONTA": "3.01", "LINE_ID_BASE": "3.01", "DS_CONTA": "Receita Liquida", "2024": 150000.0},
        {"CD_CONTA": "3.01.01", "LINE_ID_BASE": "3.01.01", "DS_CONTA": "Receita Liquida de Servicos", "2024": 180000.0},
    ]
    
    # 1. Without restrict_to_sources, 3.01.01 can be resolved (e.g. if we score it or check code matches)
    # 2. With restrict_to_sources, only 3.01 can be resolved.
    res_restricted = resolver.resolve_entry_for_period(
        company_id=1234,
        entry=entry,
        period="2024",
        raw_statement_rows=raw_rows,
        overrides={},
        aliases=[],
        restrict_to_sources=True
    )
    assert res_restricted["selected_source_id"] == "DRE:3.01"
    assert res_restricted["resolved_value"] == 150.0


def test_resolver_sum_operations():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    
    from src.financials.excel_mapping import ModelMappingSource
    
    entry = ModelMappingEntry(
        target_id="DRE:3.01",
        target_label="Revenue",
        group="Income Statement",
        statement_type="DRE",
        display_order=1,
        operation="sum_with_sign",
        sources=(
            ModelMappingSource(
                statement_type="DRE",
                line_id_base="3.01.01",
                cd_conta="3.01.01",
                label_snapshot="Gross Revenue",
                sign=1,
                position=0,
            ),
            ModelMappingSource(
                statement_type="DRE",
                line_id_base="3.01.02",
                cd_conta="3.01.02",
                label_snapshot="Deductions",
                sign=-1,
                position=1,
            ),
        )
    )
    
    raw_rows = [
        {"CD_CONTA": "3.01.01", "LINE_ID_BASE": "3.01.01", "DS_CONTA": "Gross Revenue", "2024": 100000.0},
        {"CD_CONTA": "3.01.02", "LINE_ID_BASE": "3.01.02", "DS_CONTA": "Deductions", "2024": 10000.0},
    ]
    
    res = resolver.resolve_entry_for_period(
        company_id=1234,
        entry=entry,
        period="2024",
        raw_statement_rows=raw_rows,
        overrides={},
        aliases=[],
        restrict_to_sources=True
    )
    assert res["selected_source_id"] == "sum(2)"
    # 100000 - 10000 = 90000 -> divided by 1000 = 90.0
    assert res["resolved_value"] == 90.0


def test_validate_excel_model_mapping_flags_issues():
    import pandas as pd
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        ensure_excel_mapping_tables_for_connection(conn)
    
    resolver = ModelResolver(engine)
    resolver.add_alias("DRE:3.01", "revenue", "positive")
    
    entry = ModelMappingEntry(
        target_id="DRE:3.01",
        target_label="Revenue",
        group="Income Statement",
        statement_type="DRE",
        display_order=1,
        required=True
    )
    
    from src.financials.excel_mapping import ModelMappingDefinition
    mapping = ModelMappingDefinition(
        preset_id="system:default",
        name="Default",
        description="",
        origin="system",
        default_mapping_version="model-mapping-v1",
        entries=(entry,)
    )
    
    statements = {
        "DRE": pd.DataFrame([
            {"CD_CONTA": "3.01.01", "LINE_ID_BASE": "3.01.01", "DS_CONTA": "Revenue", "STANDARD_NAME": "Revenue", "2024": 100000.0},
            {"CD_CONTA": "3.01.02", "LINE_ID_BASE": "3.01.02", "DS_CONTA": "Revenue", "STANDARD_NAME": "Revenue", "2024": 200000.0},
        ])
    }
    
    from src.financials.read_service_export import ReadServiceExportMixin
    class DummyExportService(ReadServiceExportMixin):
        def __init__(self, engine):
            self.engine = engine
            
    svc = DummyExportService(engine)
    issues = svc.validate_excel_model_mapping(mapping, statements, company_id=1234, engine=engine)
    
    assert len(issues) > 0
    assert any(issue.code == "ambiguous_mapping" for issue in issues)


