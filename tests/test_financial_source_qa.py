"""Conservative periodization against exact CVM rows and isolated persistence."""
import csv
from copy import deepcopy
import io
import json
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from src.financials.database import CVMDatabase
from src.financials.query_layer import CVMQueryLayer
from src.financials.scraper import CVMScraper
from src.financials.utils import normalize_account_names


@pytest.fixture
def scraper():
    # Pure transformation: constructor owns runtime directories and databases.
    result = CVMScraper.__new__(CVMScraper)
    result.report_type = "consolidated"
    result.source_cache = None
    result._coalesce_errors = []
    return result


def source_frame(rows):
    df = pd.DataFrame(rows)
    df["LINE_ID_BASE"] = df["CD_CONTA"]
    df["DS_CONTA_norm"] = normalize_account_names(df["DS_CONTA"])
    df["RAW_VL_CONTA"] = df["VL_CONTA"].astype(str)
    df["VL_CONTA"] = pd.to_numeric(df["VL_CONTA"])
    return df


def row(end, value, *, start="2024-01-01", code="6.01", description="Operating cash flow", **extra):
    return dict(CD_CVM=4170, CD_CONTA=code, DS_CONTA=description,
                DT_REFER=end, DT_INI_EXERC=start, DT_FIM_EXERC=end,
                VL_CONTA=value, MOEDA="REAL", ESCALA_MOEDA="MIL", VERSAO="1",
                PERIOD_TYPE="DFP" if end.endswith("12-31") else "ITR",
                SOURCE_FILE="fixture.csv", REPORT_TYPE="consolidated", **extra)


@pytest.fixture
def vale_sources():
    payload = json.loads((Path(__file__).parent / "fixtures/vale_2024_financial_qa.json").read_text(encoding="utf8"))
    df = source_frame(payload["rows"])
    df["PERIOD_TYPE"] = df["SOURCE_FILE"].str[:3].str.upper()
    df["STMT_TYPE_INTERNAL"] = df["SOURCE_FILE"].map(lambda x: "DRE" if "DRE" in x else "DFC")
    df["REPORT_TYPE"] = "consolidated"
    return df


@pytest.mark.parametrize("other_account_has_q2", [False, True])
def test_missing_predecessor_cell_or_column_never_becomes_zero(scraper, other_account_has_q2):
    rows = [row("2024-03-31", 100), row("2024-09-30", 420), row("2024-12-31", 600)]
    if other_account_has_q2:
        rows.append(row("2024-06-30", 50, code="6.02"))
    result = scraper.calculate_quarters(source_frame(rows), "DFC").set_index("CD_CONTA")
    assert pd.isna(result.loc["6.01", "3Q24"])
    assert result.loc["6.01", "4Q24"] == 180
    event = next(e for e in scraper._coalesce_errors if e["period"] == "3Q24" and e["cd_conta"] == "6.01")
    assert event["type"] == "MISSING_PREDECESSOR"
    assert event["missing_inputs"] == ["2Q24"]
    assert event["year"] == 2024
    assert event["unit"] == "BRL thousands"
    assert event["action"]


def test_annual_without_q3_does_not_derive_q4_from_q2(scraper):
    df = source_frame([row("2024-03-31", 100), row("2024-06-30", 250), row("2024-12-31", 600)])
    result = scraper.calculate_quarters(df, "DFC")
    assert pd.isna(result.loc[0, "4Q24"])
    assert result.loc[0, "2024"] == 600


def test_complete_additive_control_and_reported_standalone_preference(scraper):
    df = source_frame([row("2024-03-31", 100), row("2024-06-30", 250), row("2024-09-30", 420),
                       row("2024-12-31", 600), row("2024-09-30", 171, start="2024-07-01")])
    result = scraper.calculate_quarters(df, "DRE")
    assert result.loc[0, ["1Q24", "2Q24", "3Q24", "4Q24"]].tolist() == [100, 150, 171, 180]
    event = next(e for e in scraper._coalesce_errors if e["type"] == "DFC_VALIDATION_FAILED")
    assert event["diff"] == 1
    assert event["cd_conta"] == "6.01"
    assert event["expected"] == 600
    assert event["actual"] == 601


def test_reused_code_is_unavailable_without_name_mapping(scraper, vale_sources):
    result, qa = scraper.process_all_reports(vale_sources)
    dfc = result["DFC"].set_index("CD_CONTA")
    assert pd.isna(dfc.loc["6.01.03.09", "3Q24"])
    assert pd.isna(dfc.loc["6.02.11", "4Q24"])
    assert any(e["type"] == "ACCOUNT_IDENTITY_AMBIGUOUS" and e["cd_conta"] == "6.01.03.09" for e in qa)
    assert any(e["type"] == "ACCOUNT_IDENTITY_AMBIGUOUS" and e["cd_conta"] == "6.01.03.05" for e in qa)


def test_eps_uses_reported_duration_and_preserves_both_observations(scraper, vale_sources):
    reports, qa = scraper.process_all_reports(vale_sources)
    dre = reports["DRE"].set_index("CD_CONTA")
    assert dre.loc["3.99.01.02", "3Q24"] == pytest.approx(3.14)
    # This code is ON in Q2 and PNA elsewhere: its reported value survives in audit only.
    assert pd.isna(dre.loc["3.99.01.01", "2Q24"])
    assert pd.isna(dre.loc["3.99.01.02", "4Q24"])
    observations = reports["DRE"].attrs["source_observations"]
    q3 = [o for o in observations if o["CD_CONTA"] == "3.99.01.02" and o["DT_FIM_EXERC"] == "2024-09-30"]
    assert {o["RAW_VL_CONTA"] for o in q3} == {"8.4800000000", "3.1400000000"}
    assert {o["DT_INI_EXERC"] for o in q3} == {"2024-01-01", "2024-07-01"}
    event = next(e for e in qa if e["cd_conta"] == "3.99.01.02" and e["period"] == "4Q24")
    assert event["type"] == "NON_ADDITIVE_PERIOD"
    assert event["unit"] == "BRL/share"


def test_multiple_versions_are_retained_and_not_arbitrarily_selected(scraper):
    first = row("2024-03-31", 100)
    second = dict(first, VERSAO="2", VL_CONTA=101)
    report = scraper.calculate_quarters(source_frame([first, second]), "DFC")
    assert pd.isna(report.loc[0, "1Q24"])
    assert len(report.attrs["source_observations"]) == 2
    assert any(e["type"] == "SOURCE_OBSERVATION_AMBIGUOUS" for e in scraper._coalesce_errors)


def test_source_projection_keeps_version_currency_and_original_value(scraper, tmp_path):
    filename = "itr_cia_aberta_DRE_con_2024.csv"
    source = row("2024-03-31", "1.9300000000", code="3.99.01.02", description="ON")
    source.update(ORDEM_EXERC="\u00daLTIMO", ESCALA_MOEDA="UNIDADE")
    with (tmp_path / filename).open("w", encoding="latin1", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(source), delimiter=";")
        writer.writeheader()
        writer.writerow(source)
    scraper.processed_dir = str(tmp_path)
    scraper.suffix = "con"
    scraper._csv_cache = {}
    scraper.setores_map = {}
    raw = scraper.process_data(4170, [2024])
    assert raw.loc[0, "VERSAO"] == "1"
    assert raw.loc[0, "MOEDA"] == "REAL"
    assert raw.loc[0, "SOURCE_FILE"] == filename
    assert raw.loc[0, "RAW_VL_CONTA"] == "1.9300000000"
    assert raw.loc[0, "VL_CONTA"] == 1.93


def test_source_qa_roundtrip_partial_year_retry_and_rollback(scraper, vale_sources, tmp_path, monkeypatch):
    db = CVMDatabase(str(tmp_path / "financials.db"))
    reports, qa = scraper.process_all_reports(vale_sources)
    db.insert_company_data("VALE", 4170, "comercial", reports, qa)
    query = CVMQueryLayer(engine=db._engine)
    persisted = query.get_financial_qa(4170, [2024], "DRE")
    assert any(e["unit"] == "BRL/share" and e["year"] == 2024 and e["source_inputs"] for e in persisted)
    evidence = query.get_statement_provenance(4170, [2024], "DRE")
    assert evidence['source_observations'][0]['imported_at'].endswith('+00:00')
    with db._engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM financial_source_observations")).scalar()
        eps = conn.execute(text('SELECT "VL_CONTA" FROM financial_reports WHERE "CD_CONTA" = :code AND "PERIOD_LABEL" = :period'), {"code": "3.99.01.02", "period": "3Q24"}).scalar()
        assert eps == 3.14
    db.insert_company_data("VALE", 4170, "comercial", reports, qa)
    newer = source_frame([row("2025-03-31", 30, start="2025-01-01")])
    report25 = scraper.calculate_quarters(newer, "DFC")
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": report25}, [])
    assert query.get_financial_qa(4170, [2024], "DRE") == persisted
    with db._engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM financial_source_observations")).scalar() == count + 1
    original = db._to_sql_with_retry
    def fail_financial(table, frame, conn):
        if table == "financial_reports":
            raise RuntimeError("injected transaction failure")
        return original(table, frame, conn)
    monkeypatch.setattr(db, "_to_sql_with_retry", fail_financial)
    with pytest.raises(RuntimeError, match="injected transaction"):
        db.insert_company_data("VALE", 4170, "comercial", reports, qa)
    assert query.get_financial_qa(4170, [2024], "DRE") == persisted
    db._engine.dispose()


def test_reader_keeps_reported_zero_and_does_not_publish_unsafe_quarter(scraper, tmp_path):
    df = source_frame([row("2024-06-30", 250), row("2024-03-31", 0, code="6.02")])
    report = scraper.calculate_quarters(df, "DFC")
    db = CVMDatabase(str(tmp_path / "financials.db"))
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": report}, scraper._coalesce_errors)
    query = CVMQueryLayer(engine=db._engine)
    result = query.get_statement(4170, [2024], "DFC").set_index("CD_CONTA")
    assert result.loc["6.02", "1Q24"] == 0
    if "6.01" in result.index and "2Q24" in result.columns:
        assert pd.isna(result.loc["6.01", "2Q24"])
    assert any(e["cd_conta"] == "6.01" for e in query.get_financial_qa(4170, [2024], "DFC"))
    db._engine.dispose()


def test_reused_code_across_years_does_not_create_a_mislabeled_series(scraper):
    df = source_frame([row("2023-12-31", 100, start="2023-01-01", description="A"),
                       row("2024-12-31", 200, description="B")])
    result = scraper.calculate_quarters(df, "DFC")
    assert pd.isna(result.loc[0, "2024"])
    assert any(e["type"] == "ACCOUNT_IDENTITY_AMBIGUOUS" for e in scraper._coalesce_errors)


@pytest.mark.parametrize('statement', ['DFC', 'BPA', 'BPP'])
@pytest.mark.parametrize('currency,scale', [(None, 'MIL'), ('REAL', 'UNKNOWN'), (None, 'UNKNOWN')])
def test_unknown_unit_never_produces_an_unlabelled_derived_amount(scraper, statement, currency, scale):
    df = source_frame([row("2024-03-31", 100), row("2024-06-30", 250)])
    df["MOEDA"] = currency
    df["ESCALA_MOEDA"] = scale
    result = scraper.calculate_quarters(df, statement)
    assert pd.isna(result.loc[0, "2Q24"])
    assert any(e["type"] == "UNIT_UNAVAILABLE" for e in scraper._coalesce_errors)
    assert result.attrs['source_observations'][1]['RAW_VL_CONTA'] == '250'
    assert result.attrs['source_observations'][1]['MOEDA'] == currency
    assert result.attrs['source_observations'][1]['ESCALA_MOEDA'] == scale


def test_per_share_without_currency_is_unavailable(scraper):
    df = source_frame([row('2024-03-31', 3.14, code='3.99.01.01')]).drop(columns='MOEDA')
    result = scraper.calculate_quarters(df, 'DRE')
    assert pd.isna(result.loc[0, '1Q24'])
    assert scraper._coalesce_errors[0]['type'] == 'UNIT_UNAVAILABLE'
    assert result.attrs['source_observations'][0]['RAW_VL_CONTA'] == '3.14'


def test_public_matrix_exposes_qa_even_when_all_values_excluded(scraper, tmp_path):
    from src.financials.read_service import CVMReadService
    db = CVMDatabase(str(tmp_path / "financials.db"))
    report = scraper.calculate_quarters(source_frame([row("2024-06-30", 250)]), "DFC")
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": report}, scraper._coalesce_errors)
    svc = CVMReadService.__new__(CVMReadService)
    svc.query_layer = CVMQueryLayer(engine=db._engine)
    matrix = svc.get_statement_matrix(4170, [2024], "DFC").to_dict()
    assert matrix["qa_events"][0]["type"] == "MISSING_PREDECESSOR"
    assert matrix["quality_evidence"] == "available"
    assert matrix["table"]["rows"] == []
    db._engine.dispose()


def test_legacy_matrix_reads_without_schema_repair_and_marks_unknown(tmp_path):
    from sqlalchemy import create_engine, inspect
    from src.financials.read_service import CVMReadService
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    pd.DataFrame([dict(CD_CVM=4170, STATEMENT_TYPE="DFC", REPORT_YEAR=year,
                      PERIOD_LABEL=str(year), LINE_ID_BASE=code, CD_CONTA=code,
                      DS_CONTA="Cash", STANDARD_NAME="", QA_CONFLICT=False, VL_CONTA=10)
                  for year in (2022, 2023, 2024) for code in ("6.01", "6.02", "6.03")]).to_sql("financial_reports", engine, index=False)
    svc = CVMReadService.__new__(CVMReadService)
    svc.query_layer = CVMQueryLayer(engine=engine)
    result = svc.get_statement_matrix(4170, [2024], "DFC").to_dict()
    assert result["table"]["rows"][0]["2024"] == 10
    assert result["quality_evidence"] == "legacy_unknown"
    assert svc.get_statement_years(4170, 'DFC') == [2022, 2023, 2024]
    assert inspect(engine).get_table_names() == ["financial_reports"]
    engine.dispose()


def test_batched_observation_insert_keeps_one_row_per_id(tmp_path):
    db = CVMDatabase(str(tmp_path / "financials.db"))
    frame = pd.DataFrame([{"LINE_ID_BASE": "3.01", "CD_CONTA": "3.01", "DS_CONTA": "Receita", "2024": 1.0}])
    obs = {"observation_id": "same", "DT_FIM_EXERC": "2024-12-31", "VL_CONTA": 1.0}
    frame.attrs["source_observations"] = [obs, dict(obs)]
    frame.attrs["value_lineage"] = [dict(line_id_base="3.01", period="2024", year=2024, status="reported", source_ids=["same"])]
    db.insert_company_data("X", 1, "comercial", {"DRE": frame}, [])
    db.insert_company_data("X", 1, "comercial", {"DRE": frame}, [])
    with db._engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM financial_source_observations")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM financial_value_lineage")).scalar() == 1
    db._engine.dispose()


def test_qa_events_store_source_ids_and_reads_resolve_them(scraper, vale_sources, tmp_path):
    db = CVMDatabase(str(tmp_path / "financials.db"))
    reports, qa = scraper.process_all_reports(vale_sources)
    db.insert_company_data("VALE", 4170, "comercial", reports, qa)
    with db._engine.connect() as conn:
        stored = [json.loads(r[0]) for r in conn.execute(text('SELECT "DETAILS_JSON" FROM qa_logs'))]
        observations = {r[0]: json.loads(r[1]) for r in conn.execute(
            text("SELECT observation_id, payload_json FROM financial_source_observations"))}
    assert stored and all("source_inputs" not in e and e["source_ids"] for e in stored)

    events = CVMQueryLayer(engine=db._engine).get_financial_qa(4170, [2024], "DRE")
    assert events
    for event in events:
        assert event["source_inputs"] == [observations[i] for i in event["source_ids"]]
        assert all(source["SOURCE_FILE"] and source["RAW_VL_CONTA"] for source in event["source_inputs"])
    db._engine.dispose()


def test_qa_reads_keep_legacy_embedded_sources_and_flag_missing_ids(tmp_path):
    db = CVMDatabase(str(tmp_path / "financials.db"))
    legacy = dict(type="MISSING_OBSERVATION", statement="DRE", year=2024, period="2024",
                  source_inputs=[{"observation_id": "a", "SOURCE_FILE": "dfp.csv", "RAW_VL_CONTA": "1"}])
    slim = dict(type="MISSING_OBSERVATION", statement="DRE", year=2024, period="2024", source_ids=["gone"])
    with db._engine.begin() as conn:
        for event in (legacy, slim):
            conn.execute(text('INSERT INTO qa_logs ("CD_CVM", "STATEMENT_TYPE", "REPORT_YEAR", "DETAILS_JSON") '
                              "VALUES (4170, 'DRE', 2024, :details)"), {"details": json.dumps(event)})
    events = CVMQueryLayer(engine=db._engine).get_financial_qa(4170, [2024], "DRE")
    assert events[0] == legacy
    assert events[1]["source_inputs"] == [{"observation_id": "gone", "evidence_status": "missing"}]
    db._engine.dispose()


def test_workbook_keeps_qa_sources_and_per_share_units(scraper, vale_sources, tmp_path):
    from openpyxl import load_workbook
    from src.financials.excel_exporter import ExcelExporter
    db = CVMDatabase(str(tmp_path / "financials.db"))
    reports, qa = scraper.process_all_reports(vale_sources)
    db.insert_company_data("VALE", 4170, "comercial", reports, qa)
    query = CVMQueryLayer(engine=db._engine)
    evidence = query.get_statement_provenance(4170, [2024], "DRE")
    evidence["qa_events"] = query.get_financial_qa(4170, [2024], "DRE")
    exporter = ExcelExporter({"cd_cvm": 4170, "company_name": "VALE"},
                             {"DRE": query.get_statement(4170, [2024], "DRE")}, pd.DataFrame(),
                             financial_evidence=evidence)
    workbook = load_workbook(io.BytesIO(exporter.export(statement_type="DRE")), data_only=True)
    assert "financial_qa" in workbook.sheetnames
    assert "source_observations" in workbook.sheetnames
    qa_rows = list(workbook["financial_qa"].values)
    assert any("NON_ADDITIVE_PERIOD" in row for row in qa_rows)
    source_text = str(list(workbook["source_observations"].values))
    assert "3.1400000000" in source_text
    assert "BRL/share" in source_text
    raw = workbook['raw_DRE']
    headers = [cell.value for cell in raw[1]]
    eps_row = next(cells for cells in raw.iter_rows(min_row=2) if cells[headers.index('CD_CONTA')].value == '3.99.01.02')
    eps_cell = eps_row[headers.index('3Q24')]
    assert eps_cell.value == 3.14
    assert '.00' in eps_cell.number_format
    assert all(not sheet.merged_cells.ranges for sheet in workbook)
    db._engine.dispose()


def test_mixed_year_matrix_does_not_imply_legacy_year_has_evidence(scraper, tmp_path):
    from src.financials.read_service import CVMReadService
    db = CVMDatabase(str(tmp_path / "mixed.db"))
    legacy = pd.DataFrame([dict(LINE_ID_BASE="6.01", CD_CONTA="6.01", DS_CONTA="Cash", **{"2023": 10})])
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": legacy}, [])
    current = scraper.calculate_quarters(source_frame([row("2024-03-31", 10)]), "DFC")
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": current}, [])
    svc = CVMReadService.__new__(CVMReadService)
    svc.query_layer = CVMQueryLayer(engine=db._engine)
    assert svc.get_statement_matrix(4170, [2023, 2024], "DFC").quality_evidence == "partial"
    db._engine.dispose()


def test_missing_da_does_not_turn_ebit_into_ebitda():
    from src.financials.kpi_engine import compute_all_kpis
    accounts = pd.DataFrame([dict(REPORT_YEAR=2023, EBIT=50, Receita=100),
                             dict(REPORT_YEAR=2024, EBIT=50, Receita=100)])
    result = compute_all_kpis(accounts, pd.Series({2023: 0})).set_index("KPI_ID")
    assert result.loc["MG_EBITDA", 2023] == 0.5
    assert pd.isna(result.loc["MG_EBITDA", 2024])


def test_da_aggregation_never_sums_only_available_components(tmp_path):
    db = CVMDatabase(str(tmp_path / "da.db"))
    values = pd.DataFrame([dict(LINE_ID_BASE="6.01.01.01", CD_CONTA="6.01.01.01", DS_CONTA="Depreciacao", QA_CONFLICT=False, **{"2024": 10}),
                           dict(LINE_ID_BASE="6.01.01.02", CD_CONTA="6.01.01.02", DS_CONTA="Depreciacao adicional", QA_CONFLICT=True, **{"2024": 20})])
    db.insert_company_data("VALE", 4170, "comercial", {"DFC": values}, [])
    query = CVMQueryLayer(engine=db._engine)
    assert pd.isna(query.get_da_from_dfc(4170, [2024]).loc[2024])
    assert pd.isna(query.get_da_all_periods(4170, [2024]).iloc[0].da_value)
    db._engine.dispose()


def test_unavailable_statement_cannot_complete_a_period(scraper, tmp_path):
    db = CVMDatabase(str(tmp_path / "period.db"))
    safe = pd.DataFrame([dict(LINE_ID_BASE="1", CD_CONTA="1", DS_CONTA="Total", QA_CONFLICT=False, **{"2Q24": 100})])
    dfc = scraper.calculate_quarters(source_frame([row("2024-06-30", 250)]), "DFC")
    db.insert_company_data("VALE", 4170, "comercial", {"BPA": safe, "BPP": safe, "DRE": safe, "DFC": dfc}, scraper._coalesce_errors)
    assert CVMQueryLayer(engine=db._engine).get_company_complete_periods(4170) == []
    db._engine.dispose()


def test_refresh_persistence_writes_no_workbook(scraper, vale_sources, monkeypatch):
    """Refresh only persists; workbooks come from the on-demand export (#548)."""
    from unittest.mock import MagicMock

    def no_workbook(*args, **kwargs):
        raise AssertionError("refresh must not write a workbook")

    monkeypatch.setattr(pd, "ExcelWriter", no_workbook)
    monkeypatch.setattr(pd.DataFrame, "to_excel", no_workbook)
    monkeypatch.setattr("src.companies.identity.CompanyIdentityResolver.resolve", lambda *_: None)
    scraper.db = MagicMock()
    scraper.db.insert_company_data.return_value = 7
    scraper.setores_map = {}
    scraper.cnpjs_map = {}
    scraper.standardizer = None
    reports, qa = scraper.process_all_reports(vale_sources)
    assert scraper.persist_reports("VALE", 4170, reports, qa) == 7
    scraper.db.insert_company_data.assert_called_once()


class _TrackedAuditRecords(list):
    """Count recursive audit copies without changing the evidence being written."""

    def __init__(self, records, copies):
        super().__init__(records)
        self.copies = copies

    def __deepcopy__(self, memo):
        self.copies.append(len(self))
        result = _TrackedAuditRecords(deepcopy(list(self), memo), self.copies)
        memo[id(self)] = result
        return result


def _track_report_audit(reports):
    before = deepcopy(reports)
    copies = []
    for report in reports.values():
        for key in ('source_observations', 'value_lineage'):
            report.attrs[key] = _TrackedAuditRecords(report.attrs[key], copies)
    return before, copies


def _assert_reports_unchanged(reports, before):
    for statement, report in reports.items():
        pd.testing.assert_frame_equal(report, before[statement])
        assert report.attrs == before[statement].attrs


def _assert_persisted_audit(db, reports, qa):
    with db._engine.connect() as conn:
        for table, key in [('financial_source_observations', 'source_observations'),
                           ('financial_value_lineage', 'value_lineage')]:
            actual = [json.loads(row[0]) for row in conn.execute(text(f'SELECT payload_json FROM {table}'))]
            expected = [record for report in reports.values() for record in report.attrs[key]]
            assert sorted(json.dumps(row, sort_keys=True) for row in actual) == sorted(
                json.dumps(row, sort_keys=True) for row in expected)
        actual_qa = [json.loads(row[0]) for row in conn.execute(text('SELECT "DETAILS_JSON" FROM qa_logs'))]
        assert actual_qa == qa
        eps = conn.execute(text('SELECT "PERIOD_LABEL", "VL_CONTA", "QA_CONFLICT" '
                                'FROM financial_reports WHERE "CD_CONTA" = \'3.99.01.02\''))
        values = {period: (value, bool(conflict)) for period, value, conflict in eps}
        assert values['3Q24'] == (3.14, False)
        assert values['4Q24'] == (None, True)


@pytest.mark.parametrize('fail_write', [False, True])
def test_persistence_does_not_copy_or_mutate_report_audit(scraper, vale_sources, tmp_path, monkeypatch, fail_write):
    reports, qa = scraper.process_all_reports(vale_sources)
    before, copies = _track_report_audit(reports)
    qa_before = deepcopy(qa)
    db = CVMDatabase(str(tmp_path / 'financials.db'))
    write = db._to_sql_with_retry

    def fail_financial(table, frame, conn):
        if table == 'financial_reports':
            raise RuntimeError('injected financial write failure')
        return write(table, frame, conn)

    try:
        if fail_write:
            monkeypatch.setattr(db, '_to_sql_with_retry', fail_financial)
            with pytest.raises(RuntimeError, match='injected financial write failure'):
                db.insert_company_data('VALE', 4170, 'comercial', reports, qa)
            with db._engine.connect() as conn:
                for table in ('financial_reports', 'financial_source_observations', 'financial_value_lineage', 'qa_logs'):
                    assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar() == 0
        else:
            assert db.insert_company_data('VALE', 4170, 'comercial', reports, qa) > 0
            _assert_persisted_audit(db, reports, qa)
        operation_copies = list(copies)
        _assert_reports_unchanged(reports, before)
        assert qa == qa_before
        assert operation_copies == []
    finally:
        db._engine.dispose()


@pytest.mark.parametrize('standardize', [False, True])
@pytest.mark.parametrize('failure', [None, 'database'])
def test_ingestion_keeps_audit_without_tabular_deepcopies(scraper, vale_sources, tmp_path, monkeypatch, standardize, failure):
    from src.financials.standardizer import AccountStandardizer

    reports, qa = scraper.process_all_reports(vale_sources)
    before, copies = _track_report_audit(reports)
    qa_before = deepcopy(qa)
    scraper.db = CVMDatabase(str(tmp_path / 'financials.db'))
    scraper.setores_map = {}
    scraper.cnpjs_map = {}
    scraper.standardizer = AccountStandardizer(str(Path(__file__).parents[1] / 'data/import/canonical_accounts.csv')) if standardize else None
    # Identity resolution otherwise uses the default runtime database/catalog.
    monkeypatch.setattr('src.companies.identity.CompanyIdentityResolver.resolve', lambda *_: None)
    write = scraper.db._to_sql_with_retry

    def fail_financial(table, frame, conn):
        if table == 'financial_reports':
            raise RuntimeError('injected database failure')
        return write(table, frame, conn)

    try:
        if failure == 'database':
            monkeypatch.setattr(scraper.db, '_to_sql_with_retry', fail_financial)
        if failure:
            with pytest.raises(RuntimeError, match=f'injected {failure} failure'):
                scraper.persist_reports('VALE', 4170, reports, qa)
        else:
            assert scraper.persist_reports('VALE', 4170, reports, qa) > 0
        operation_copies = list(copies)
        _assert_reports_unchanged(reports, before)
        assert qa == qa_before
        if failure != 'database':
            _assert_persisted_audit(scraper.db, reports, qa)
        assert operation_copies == []
    finally:
        scraper.db._engine.dispose()


def partial_statement_service(scraper, tmp_path):
    from src.platform.settings import build_settings
    from src.financials.read_service import CVMReadService
    settings = build_settings(project_root=tmp_path)
    settings.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = CVMDatabase(str(settings.paths.db_path))
    reports = {}
    for statement, code in [('BPA', '1'), ('BPP', '2'), ('DRE', '3.01'), ('DFC', '6.01')]:
        start = '2024-04-01' if statement == 'DRE' else '2024-01-01'
        reports[statement] = scraper.calculate_quarters(source_frame([row('2024-06-30', 250, start=start, code=code)]), statement)
    db.insert_company_data('VALE', 4170, 'comercial', reports, scraper._coalesce_errors)
    return db, CVMReadService(settings=settings)


@pytest.mark.parametrize('statement_type', ['DFC', None])
def test_public_export_retains_partial_only_financial_evidence(scraper, tmp_path, statement_type):
    from openpyxl import load_workbook
    db, svc = partial_statement_service(scraper, tmp_path)
    try:
        assert svc.get_available_years(4170) == []
        assert svc.query_layer.get_company_complete_periods(4170) == []
        _, payload = svc.build_company_excel_export(4170, statement_type=statement_type, period_scope='full_history')
        workbook = load_workbook(io.BytesIO(payload), data_only=True)
        assert 'financial_qa' in workbook.sheetnames
        assert 'MISSING_PREDECESSOR' in str(list(workbook['financial_qa'].values))
        assert '2024' in str(list(workbook['source_observations'].values))
        scope = next(row[1].value for row in workbook['metadata'].iter_rows() if row[0].value == 'Export scope')
        assert 'partial evidence' in scope.lower()
        if statement_type is None:
            assert 'Model' not in workbook.sheetnames
            assert 'Financial evidence only' in workbook['README']['A1'].value
        assert svc.query_layer.get_company_complete_periods(4170) == []
    finally:
        svc.engine.dispose()
        db._engine.dispose()


@pytest.mark.parametrize('statement_type', ['DFC', None])
def test_public_export_includes_latest_partial_year_within_bounded_scope(scraper, tmp_path, statement_type):
    from openpyxl import load_workbook
    db, svc = partial_statement_service(scraper, tmp_path)
    for year in (2020, 2021, 2022, 2023):
        safe = pd.DataFrame([dict(LINE_ID_BASE='1', CD_CONTA='1', DS_CONTA='Total', QA_CONFLICT=False, **{str(year): 100})])
        db.insert_company_data('VALE', 4170, 'comercial', {statement: safe for statement in ('BPA', 'BPP', 'DRE', 'DFC')}, [])
    older = scraper.calculate_quarters(source_frame([row('2010-06-30', 25, start='2010-01-01')]), 'DFC')
    db.insert_company_data('VALE', 4170, 'comercial', {'DFC': older}, [event for event in scraper._coalesce_errors if event['year'] == 2010])
    try:
        _, payload = svc.build_company_excel_export(4170, statement_type=statement_type, period_scope='last_3_years')
        workbook = load_workbook(io.BytesIO(payload), data_only=True)
        qa = str(list(workbook['financial_qa'].values)) if 'financial_qa' in workbook.sheetnames else ''
        assert '2024' in qa
        assert '2010' not in str(list(workbook['value_lineage'].values))
        scope = next(row[1].value for row in workbook['metadata'].iter_rows() if row[0].value == 'Export scope')
        assert 'partial evidence' in scope.lower()
        if statement_type is None:
            # Package coverage does not supply the missing required model accounts.
            assert 'Model' not in workbook.sheetnames
            assert 'Financial evidence only' in workbook['README']['A1'].value
    finally:
        svc.engine.dispose()
        db._engine.dispose()


def test_partial_evidence_export_still_rejects_invalid_mapping(scraper, tmp_path, monkeypatch):
    from dataclasses import replace
    db, svc = partial_statement_service(scraper, tmp_path)
    try:
        mapping = svc.resolve_excel_model_mapping(4170)
        invalid = replace(mapping, entries=(replace(mapping.entries[0], operation='invalid'), *mapping.entries[1:]))
        monkeypatch.setattr(svc, 'resolve_excel_model_mapping', lambda *args: invalid)
        with pytest.raises(ValueError, match='Invalid Excel mapping'):
            svc.build_company_excel_export(4170, period_scope='full_history')
    finally:
        svc.engine.dispose()
        db._engine.dispose()


def test_statement_year_discovery_includes_qa_without_changing_annual_years(scraper, tmp_path):
    from desktop.bridge import CVMBridge
    db, svc = partial_statement_service(scraper, tmp_path)
    try:
        bridge = CVMBridge.__new__(CVMBridge)
        bridge._service = svc
        assert svc.get_available_years(4170) == []
        years = bridge.get_company_statement_years({'cd_cvm': 4170, 'stmt': 'DFC'})
        assert years == {'years': [2024]}
        result = bridge.get_company_statement({'cd_cvm': 4170, 'stmt': 'DFC', 'years': years['years']})
        assert result['qa_events'][0]['type'] == 'MISSING_PREDECESSOR'
        assert result['table']['rows'] == []
    finally:
        svc.engine.dispose()
        db._engine.dispose()
