from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.data.profile_local_storage import build_profile


def test_profile_local_storage_writes_json_and_markdown(tmp_path: Path):
    data_root = tmp_path / "CVMAnalytics"
    db_dir = data_root / "db"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "sample.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, label TEXT)")
        conn.executemany("INSERT INTO sample(label) VALUES (?)", [("a",), ("b",)])

    output_dir = data_root / "metadata" / "storage_profiles"
    profile = build_profile(
        data_root=data_root,
        output_dir=output_dir,
        top_n=5,
        include_dbstat=False,
        include_integrity=False,
        write=True,
    )

    assert profile["file_scan"]["total_bytes"] > 0
    assert profile["stores"][0]["type"] == "sqlite"
    assert profile["stores"][0]["tables"][0]["name"] == "sample"
    assert profile["stores"][0]["tables"][0]["row_count"] == 2
    assert Path(profile["outputs"]["json"]).exists()
    assert Path(profile["outputs"]["markdown"]).exists()
