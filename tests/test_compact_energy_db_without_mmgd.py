from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import polars as pl

from scripts.data.compact_energy_db_without_mmgd import create_compact_without_mmgd


def _write_source_db(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE distribution_mmgd_projects (
                project_id TEXT PRIMARY KEY,
                distributor_id TEXT NOT NULL,
                municipality TEXT,
                uf TEXT,
                generation_type TEXT,
                generation_source TEXT,
                size_category TEXT,
                latitude REAL,
                longitude REAL,
                connection_date TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                source_row_hash TEXT
            );
            CREATE TABLE distribution_mmgd_project_snapshots (
                snapshot_row_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                reference_month TEXT NOT NULL,
                installed_capacity_kw REAL,
                beneficiary_units_count INTEGER,
                source_row_hash TEXT NOT NULL,
                snapshot_id TEXT
            );
            INSERT INTO distribution_mmgd_projects (
                project_id, distributor_id, municipality, uf, generation_type,
                generation_source, size_category, latitude, longitude,
                connection_date, status, source_row_hash
            )
            VALUES
                ('GD-1', 'cpfl_paulista', 'Campinas', 'SP', 'Solar', 'Radiacao solar',
                 'Microgeracao', -22.9, -47.06, '2025-01-15', 'active', 'hash-1'),
                ('GD-2', 'cpfl_paulista', 'Campinas', 'SP', 'Solar', 'Radiacao solar',
                 'Minigeracao', -22.8, -47.05, '2025-01-20', 'active', 'hash-2');
            INSERT INTO distribution_mmgd_project_snapshots (
                snapshot_row_id, project_id, reference_month, installed_capacity_kw,
                beneficiary_units_count, source_row_hash, snapshot_id
            )
            VALUES
                ('GD-1_hash-1', 'GD-1', '2026-06', 10.5, 1, 'hash-1', 'snap-old'),
                ('GD-2_hash-2', 'GD-2', '2026-06', 75.0, 3, 'hash-2', 'snap-old');
            """
        )
        conn.commit()


def test_create_compact_without_mmgd_externalizes_detail_and_preserves_source(tmp_path: Path):
    source = tmp_path / "energy_kpis.db"
    output = tmp_path / "energy_kpis.without_mmgd.candidate.db"
    _write_source_db(source)

    report = create_compact_without_mmgd(
        source_db=source,
        output_db=output,
        data_dir=tmp_path,
    )

    assert report["ok"] is True
    assert report["source_mmgd_project_rows"] == 2
    assert report["output_mmgd_project_rows"] == 0
    assert report["managed_row_count"] == 2

    with sqlite3.connect(source) as conn:
        assert conn.execute("SELECT COUNT(*) FROM distribution_mmgd_projects").fetchone()[0] == 2

    with sqlite3.connect(output) as conn:
        assert conn.execute("SELECT COUNT(*) FROM distribution_mmgd_projects").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM distribution_mmgd_project_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT mmgd_projects_count, mmgd_capacity_kw FROM distribution_mmgd_monthly_mart").fetchone() == (2, 85.5)
        catalog = conn.execute(
            "SELECT manifest_path, row_count FROM managed_dataset_catalog WHERE dataset_id = 'distribution_mmgd_projects'"
        ).fetchone()

    manifest = json.loads(Path(catalog[0]).read_text(encoding="utf-8"))
    assert catalog[1] == 2
    assert manifest["validation"]["ok"] is True
    parquet_path = Path(manifest["partitions"][0]["path"])
    assert parquet_path.exists()
    assert pl.read_parquet(parquet_path).height == 2

