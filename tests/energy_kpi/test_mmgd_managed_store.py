from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from sqlalchemy import text

from src.energy_kpi.distribution import seed_distribution_static_data
from src.energy_kpi.distribution.ingest import upsert_mmgd_facts


def _mmgd_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "normalized_cnpj": ["33050196000188", "33050196000188"],
            "raw_name": ["CPFL PAULISTA S.A.", "CPFL PAULISTA S.A."],
            "project_id": ["GD-1", "GD-2"],
            "municipality": ["Campinas", "Campinas"],
            "uf": ["SP", "SP"],
            "consumer_class": ["Residencial", "Comercial"],
            "tariff_subgroup": ["B1", "B3"],
            "project_modality": ["Geracao junto a carga", "Geracao remota"],
            "enabled_modality": ["Autoconsumo", "Autoconsumo"],
            "generation_type": ["Solar", "Solar"],
            "generation_source": ["Radiacao solar", "Radiacao solar"],
            "size_category": ["Microgeracao", "Minigeracao"],
            "latitude": [-22.9, -22.8],
            "longitude": [-47.06, -47.05],
            "connection_date": ["2025-01-15", "2025-01-20"],
            "reference_month": ["2026-06", "2026-06"],
            "installed_capacity_kw": [10.5, 75.0],
            "beneficiary_units_count": [1, 3],
            "source_row_hash": ["hash-1", "hash-2"],
        }
    )


def test_mmgd_managed_ingestion_writes_manifest_mart_and_no_sqlite_detail(tmp_path: Path, db_conn):
    seed_distribution_static_data(db_conn)

    result = upsert_mmgd_facts(
        db_conn,
        _mmgd_frame(),
        "snap-mmgd-managed",
        managed_data_dir=tmp_path,
    )

    assert int(result) == 2
    assert result.stats["managed_store"]["row_count"] == 2
    assert db_conn.execute(text("SELECT COUNT(*) FROM distribution_mmgd_projects")).scalar() == 0
    assert db_conn.execute(text("SELECT COUNT(*) FROM distribution_mmgd_project_snapshots")).scalar() == 0

    mart_rows = db_conn.execute(
        text(
            """
            SELECT distributor_id, reference_month, mmgd_projects_count, mmgd_capacity_kw
            FROM distribution_mmgd_monthly_mart
            """
        )
    ).fetchall()
    assert mart_rows == [("cpfl_paulista", "2026-06", 2, 85.5)]

    catalog = db_conn.execute(
        text(
            """
            SELECT dataset_id, manifest_path, row_count
            FROM managed_dataset_catalog
            WHERE dataset_id = 'distribution_mmgd_projects'
            """
        )
    ).fetchone()
    assert catalog is not None
    assert catalog.row_count == 2

    manifest_path = Path(catalog.manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["contract"]["dataset_id"] == "distribution_mmgd_projects"
    assert manifest["validation"]["ok"] is True
    assert manifest["partitions"][0]["reference_month"] == "2026-06"
    assert manifest["partitions"][0]["row_count"] == 2

    parquet_path = Path(manifest["partitions"][0]["path"])
    assert parquet_path.exists()
    stored = pl.read_parquet(parquet_path)
    assert stored.select("project_id").to_series().to_list() == ["GD-1", "GD-2"]
