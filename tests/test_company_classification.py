"""Canonical company classification: curated GICS layer loaded and read consistently (#518)."""
import csv
import sqlite3

import pytest

from desktop.bridge import CVMBridge
from src.companies.classification import (
    CURATED_PATH,
    STRUCTURE_PATH,
    CuratedClassificationError,
    load_gics_structure,
    sync_curated_classification,
)
from test_company_market_cap_sort import _company, _seed_db

FIELDS = ["cd_cvm", "company_name", "cnpj", "sub_industry_code", "unclassified_reason", "basis", "confidence",
          "rationale", "evidence_url", "review_status", "reviewer", "review_date", "proposed_by", "gics_version"]


def _write_curated(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"basis": "researched", "confidence": "high", "rationale": "r", "gics_version": "v", **row})
    return path


@pytest.fixture
def service(tmp_path):
    svc = _seed_db(tmp_path, [_company(10, "Oil Co"), _company(20, "Shell Co"), _company(30, "New Co")])
    with sqlite3.connect(svc.settings.paths.db_path) as conn:
        # Legacy CVM-derived label that the curated layer must replace.
        conn.execute("UPDATE companies SET gics_sector='Utilities', gics_sector_slug='utilities' WHERE cd_cvm=30")
    curated = _write_curated(tmp_path / "curated.csv", [
        {"cd_cvm": "10", "sub_industry_code": "10102010", "evidence_url": "https://ri.example"},
        {"cd_cvm": "20", "unclassified_reason": "pre-operational SPAC", "confidence": "medium"},
    ])
    sync_curated_classification(svc.engine, curated_path=curated)
    return svc, curated


def _company_row(svc, cd_cvm):
    with sqlite3.connect(svc.settings.paths.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM companies WHERE cd_cvm=?", (cd_cvm,)).fetchone())


def test_structure_has_every_current_gics_level():
    structure = load_gics_structure(STRUCTURE_PATH)
    assert len(structure) == 163
    levels = [{getattr(p, f) for p in structure.values()} for f in ("sector_code", "industry_group_code", "industry_code")]
    assert [len(level) for level in levels] == [11, 25, 74]
    assert structure["10102010"].industry == "Oil, Gas & Consumable Fuels"


def test_shipped_curated_dataset_is_valid():
    rows = list(csv.DictReader(CURATED_PATH.open(encoding="utf-8")))
    structure = load_gics_structure(STRUCTURE_PATH)
    assert rows and all(r["sub_industry_code"] in structure or r["unclassified_reason"] for r in rows)


def test_sync_materializes_curated_unclassified_and_pending(service):
    svc, _ = service
    oil, shell, new = (_company_row(svc, cd) for cd in (10, 20, 30))
    assert (oil["gics_sector"], oil["gics_industry"], oil["gics_sub_industry"], oil["gics_sub_industry_code"]) == (
        "Energy", "Oil, Gas & Consumable Fuels", "Integrated Oil & Gas", "10102010")
    assert oil["classification_origin"] == "curated"
    assert (shell["gics_sector"], shell["classification_origin"]) == (None, "unclassified")
    assert (new["gics_sector"], new["classification_origin"]) == (None, "pending")


def test_company_reads_show_the_same_canonical_classification(service):
    svc, _ = service
    info = svc.get_company_info(10)
    assert (info.gics_sector, info.gics_sub_industry) == ("Energy", "Integrated Oil & Gas")
    assert info.classification["origin"] == "curated"
    assert info.classification["official"] is False
    assert info.classification["evidence_url"] == "https://ri.example"
    assert svc.get_company_info(20).classification["unclassified_reason"] == "pre-operational SPAC"
    pending = svc.get_company_info(30)
    assert pending.gics_sector is None and pending.classification["origin"] == "pending"

    bridge = CVMBridge()
    bridge._service = svc
    items = {item["cd_cvm"]: item for item in bridge.get_companies({"page_size": 10})["items"]}
    assert (items[10]["gics_sector"], items[10]["classification_origin"]) == ("Energy", "curated")
    assert (items[30]["gics_sector"], items[30]["classification_origin"]) == (None, "pending")


def test_invalid_dataset_is_rejected_without_touching_previous_classification(service, tmp_path):
    svc, _ = service
    bad = _write_curated(tmp_path / "bad.csv", [
        {"cd_cvm": "10", "sub_industry_code": "99999999"},
        {"cd_cvm": "30"},
    ])
    with pytest.raises(CuratedClassificationError, match="2 invalid"):
        sync_curated_classification(svc.engine, curated_path=bad)
    assert _company_row(svc, 10)["classification_origin"] == "curated"


def test_sync_is_idempotent_and_new_companies_pick_up_curation(service):
    svc, curated = service
    sync_curated_classification(svc.engine, curated_path=curated)
    assert _company_row(svc, 10)["gics_sub_industry_code"] == "10102010"
    with svc.engine.begin() as conn:
        from src.companies.classification import materialize_company
        conn.exec_driver_sql("DELETE FROM companies WHERE cd_cvm=10")
        conn.exec_driver_sql("INSERT INTO companies (cd_cvm, company_name, updated_at) VALUES (10, 'Oil Co', '')")
        materialize_company(conn, 10)
    assert _company_row(svc, 10)["classification_origin"] == "curated"


def test_local_edit_wins_everywhere_and_survives_dataset_reload(service, tmp_path):
    svc, curated = service
    bridge = CVMBridge()
    bridge._service = svc
    result = bridge.set_company_classification({"cd_cvm": 10, "sub_industry_code": "10102020"})
    assert result["ok"] and result["classification"]["origin"] == "user"
    assert result["classification"]["user_edit"]["curated_sub_industry_code"] == "10102010"
    assert result["classification"]["user_edit"]["curated_changed_since_edit"] is False

    # A new shipped dataset changes the curated value: the edit stays and the change is flagged.
    newer = _write_curated(tmp_path / "newer.csv", [{"cd_cvm": "10", "sub_industry_code": "10102030"}])
    sync_curated_classification(svc.engine, curated_path=newer)
    info = svc.get_company_info(10)
    assert (info.gics_sub_industry, info.classification["origin"]) == ("Oil & Gas Exploration & Production", "user")
    assert info.classification["user_edit"]["curated_changed_since_edit"] is True
    items = {i["cd_cvm"]: i for i in bridge.get_companies({"page_size": 10})["items"]}
    assert items[10]["classification_origin"] == "user"

    reverted = bridge.clear_company_classification({"cd_cvm": 10})
    assert reverted["classification"]["origin"] == "curated"
    assert reverted["classification"]["gics_sub_industry_code"] == "10102030"


def test_local_edit_classifies_a_pending_company_and_rejects_unknown_codes(service):
    svc, _ = service
    bridge = CVMBridge()
    bridge._service = svc
    assert bridge.set_company_classification({"cd_cvm": 30, "sub_industry_code": "55101010"})["ok"]
    assert _company_row(svc, 30)["gics_sector"] == "Utilities"
    failed = bridge.set_company_classification({"cd_cvm": 30, "sub_industry_code": "12345678"})
    assert failed["ok"] is False and "Unknown GICS" in failed["error"]
    assert len(bridge.get_gics_structure()["items"]) == 163
