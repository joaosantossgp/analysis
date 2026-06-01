"""OWID Energy Dataset ingestion.

Fetch → immutable snapshot → normalize (wide→tidy) → return tidy DataFrame.
Never overwrites existing snapshots. Network only on explicit refresh trigger.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import requests

from src.energy_kpi.catalog import (
    CATALOG_BY_ID,
    OWID_FIELD_MAP,
    _ENERGY_CATALOG,
)
from src.settings import AppPaths

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

OWID_CSV_URL = "https://owid-public.owid.io/data/energy/owid-energy-data.csv"
OWID_CODEBOOK_URL = "https://owid-public.owid.io/data/energy/owid-energy-codebook.csv"

# v1 country scope — ISO alpha-3 codes
V1_ISO_CODES: frozenset[str] = frozenset({"BRA", "USA", "CHN", "OWEU", "CHL", "ARG"})

# OWID columns that map to v1 KPI fields (direct reads, not derived)
_DIRECT_SOURCE_FIELDS: frozenset[str] = frozenset(
    k.primary_source_field
    for k in _ENERGY_CATALOG
    if k.primary_source == "OWID" and k.primary_source_field and k.calculation_method == "direct"
)

# OWID fields needed for derived KPIs (same base field, computed locally)
_DERIVED_BASE_FIELDS: frozenset[str] = frozenset(
    k.primary_source_field
    for k in _ENERGY_CATALOG
    if k.primary_source == "OWID" and k.primary_source_field and k.calculation_method != "direct"
)

_ALL_OWID_FIELDS: frozenset[str] = _DIRECT_SOURCE_FIELDS | _DERIVED_BASE_FIELDS

# Columns always present in the raw CSV (join keys)
_ID_COLS = ("country", "iso_code", "year")


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    source: str
    fetched_at: str
    csv_path: Path
    codebook_path: Path
    sha256: str
    row_count: int
    source_version_label: str


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, timeout: int = 120) -> None:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)


def fetch_owid_snapshot(paths: AppPaths) -> SnapshotRecord:
    """Download OWID energy CSV + codebook to an immutable snapshot directory.

    Returns a SnapshotRecord describing what was fetched. Never overwrites
    an existing snapshot — each call creates a new snapshot_id directory.
    Caller is responsible for persisting the SnapshotRecord to source_snapshots.
    """
    snapshot_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap_dir = paths.energy_kpi_raw_dir / "owid" / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)

    csv_path = snap_dir / "owid-energy-data.csv"
    codebook_path = snap_dir / "owid-energy-codebook.csv"

    logger.info("Fetching OWID energy CSV → %s", csv_path)
    _download(OWID_CSV_URL, csv_path)

    logger.info("Fetching OWID codebook → %s", codebook_path)
    _download(OWID_CODEBOOK_URL, codebook_path)

    sha256 = _sha256_file(csv_path)

    # Quick row count without loading full CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1  # subtract header

    # Source version label: first available date column in codebook, else fetched_at date
    try:
        cb = pd.read_csv(codebook_path, nrows=5)
        version_label = cb.get("last_updated", pd.Series([])).dropna().iloc[0] if "last_updated" in cb.columns else fetched_at[:10]
    except Exception:
        version_label = fetched_at[:10]

    logger.info(
        "OWID snapshot %s: %d rows, sha256=%s…", snapshot_id, row_count, sha256[:12]
    )
    return SnapshotRecord(
        snapshot_id=snapshot_id,
        source="OWID",
        fetched_at=fetched_at,
        csv_path=csv_path,
        codebook_path=codebook_path,
        sha256=sha256,
        row_count=row_count,
        source_version_label=str(version_label),
    )


def normalize_owid(
    snapshot: SnapshotRecord,
    iso_filter: frozenset[str] = V1_ISO_CODES,
) -> pd.DataFrame:
    """Read snapshot CSV → filter → melt wide→tidy → return long DataFrame.

    Returns columns:
        kpi_id, iso_code, country_name, period (int), value (float),
        source_field (original OWID column), unit, source, source_priority,
        snapshot_id
    """
    # Load only needed columns to keep memory low
    needed_cols = list(_ID_COLS) + [f for f in _ALL_OWID_FIELDS if f]
    try:
        df = pd.read_csv(
            snapshot.csv_path,
            usecols=lambda c: c in set(needed_cols),
            dtype={"iso_code": str, "country": str, "year": "Int64"},
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to read OWID CSV at {snapshot.csv_path}: {exc}") from exc

    # Filter to v1 countries + drop world/continent aggregates (iso_code starts with OWID or is blank)
    df = df[df["iso_code"].isin(iso_filter)].copy()
    df = df.rename(columns={"country": "country_name", "year": "period"})

    # Keep only OWID fields that exist in the CSV (graceful — future-proof if field removed)
    present_owid_fields = [f for f in _ALL_OWID_FIELDS if f and f in df.columns]
    id_cols_present = [c for c in ("country_name", "iso_code", "period") if c in df.columns]

    if not present_owid_fields:
        logger.warning("No v1 KPI fields found in OWID CSV — check OWID_FIELD_MAP")
        return pd.DataFrame(columns=["kpi_id", "iso_code", "country_name", "period", "value",
                                     "source_field", "unit", "source", "source_priority", "snapshot_id"])

    # Melt wide → tidy
    tidy = df[id_cols_present + present_owid_fields].melt(
        id_vars=id_cols_present,
        value_vars=present_owid_fields,
        var_name="source_field",
        value_name="value",
    )

    # Map source_field → kpi_id (one source_field may produce multiple KPIs via derived)
    # Primary mapping: direct KPIs
    direct_map = {
        k.primary_source_field: k.kpi_id
        for k in _ENERGY_CATALOG
        if k.primary_source == "OWID" and k.primary_source_field and k.calculation_method == "direct"
    }
    tidy["kpi_id"] = tidy["source_field"].map(direct_map)
    tidy = tidy.dropna(subset=["kpi_id"])

    # Attach units from catalog
    unit_map = {k.kpi_id: k.unit for k in _ENERGY_CATALOG}
    tidy["unit"] = tidy["kpi_id"].map(unit_map)

    tidy["source"] = "OWID"
    tidy["source_priority"] = 1
    tidy["snapshot_id"] = snapshot.snapshot_id
    tidy["period"] = tidy["period"].astype("Int64").astype(object).where(tidy["period"].notna(), None)

    # Drop rows where period is null (some OWID rows have no year)
    tidy = tidy.dropna(subset=["period"])
    tidy["period"] = tidy["period"].astype(int)
    tidy["value"] = pd.to_numeric(tidy["value"], errors="coerce")

    logger.info(
        "OWID normalize: %d tidy rows for %d countries, %d KPI IDs",
        len(tidy),
        tidy["iso_code"].nunique(),
        tidy["kpi_id"].nunique(),
    )
    return tidy[["kpi_id", "iso_code", "country_name", "period", "value",
                 "source_field", "unit", "source", "source_priority", "snapshot_id"]]


def persist_snapshot_record(conn, snapshot: SnapshotRecord) -> None:
    """Insert a SnapshotRecord into source_snapshots table."""
    from sqlalchemy import text
    conn.execute(text("""
        INSERT OR REPLACE INTO source_snapshots
            (snapshot_id, source, fetched_at, file_path, sha256, row_count,
             source_version_label, status)
        VALUES
            (:sid, :src, :fat, :fp, :sha, :rc, :svl, 'ok')
    """), {
        "sid": snapshot.snapshot_id,
        "src": snapshot.source,
        "fat": snapshot.fetched_at,
        "fp": str(snapshot.csv_path),
        "sha": snapshot.sha256,
        "rc": snapshot.row_count,
        "svl": snapshot.source_version_label,
    })


def upsert_country_kpi_values(conn, tidy_df: pd.DataFrame) -> int:
    """Upsert tidy rows into country_kpi_values. Returns row count upserted."""
    from sqlalchemy import text
    if tidy_df.empty:
        return 0

    rows = tidy_df.to_dict(orient="records")
    conn.execute(text("""
        INSERT OR REPLACE INTO country_kpi_values
            (kpi_id, iso_code, period, value, value_owid, unit, source, source_priority,
             source_field, data_quality_status, source_conflict, fallback_used,
             last_updated, snapshot_id)
        VALUES
            (:kpi_id, :iso_code, :period, :value, :value,
             :unit, :source, :source_priority, :source_field,
             :data_quality_status, :source_conflict, :fallback_used,
             :last_updated, :snapshot_id)
    """), [
        {
            "kpi_id": r["kpi_id"],
            "iso_code": r["iso_code"],
            "period": r["period"],
            "value": r.get("value"),
            "unit": r.get("unit"),
            "source": r.get("source", "OWID"),
            "source_priority": r.get("source_priority", 1),
            "source_field": r.get("source_field", ""),
            "data_quality_status": r.get("data_quality_status", "ok"),
            "source_conflict": int(r.get("source_conflict", False)),
            "fallback_used": int(r.get("fallback_used", False)),
            "last_updated": r.get("last_updated", datetime.now(timezone.utc).isoformat(timespec="seconds")),
            "snapshot_id": r.get("snapshot_id", ""),
        }
        for r in rows
    ])
    return len(rows)


def seed_kpi_sources(conn) -> None:
    """Seed the kpi_sources table with known source metadata."""
    from sqlalchemy import text
    conn.execute(text("""
        INSERT OR IGNORE INTO kpi_sources
            (source, display_name, base_url, license, default_priority, cadence,
             retrieval_method, notes)
        VALUES
            ('OWID', 'Our World in Data — Energy Dataset',
             'https://ourworldindata.org/energy',
             'CC-BY', 1, 'annual',
             'HTTP CSV download',
             'Electricity matrix sourced from Ember Yearly Electricity Data; energy from Energy Institute + EIA'),
            ('EMBER', 'Ember Yearly Electricity Data',
             'https://ember-energy.org',
             'CC-BY', 2, 'annual+monthly',
             'API (key-gated)',
             'Direct Ember needed only for installed capacity and monthly granularity; v1 deferred')
    """))


def seed_country_dimension(conn) -> None:
    """Seed country_dimension with v1 scope countries."""
    from sqlalchemy import text
    countries = [
        ("BRA", "Brazil",         "South America",  1),
        ("USA", "United States",  "North America",  1),
        ("CHN", "China",          "Asia",           1),
        ("OWEU", "European Union (27)", "Europe",   1),
        ("CHL", "Chile",          "South America",  1),
        ("ARG", "Argentina",      "South America",  1),
    ]
    conn.execute(text("""
        INSERT OR IGNORE INTO country_dimension (iso_code, country_name, region, is_v1_scope)
        VALUES (:iso, :name, :region, :scope)
    """), [{"iso": c[0], "name": c[1], "region": c[2], "scope": c[3]} for c in countries])


def seed_kpi_catalog(conn) -> None:
    """Upsert all KPI definitions from _ENERGY_CATALOG into kpi_catalog table."""
    from sqlalchemy import text
    from src.energy_kpi.catalog import _ENERGY_CATALOG
    conn.execute(text("""
        INSERT OR REPLACE INTO kpi_catalog
            (kpi_id, display_name, description, kpi_type, macro_category, subsector,
             unit, primary_source, primary_source_field, fallback_source,
             fallback_source_field, calculation_method, v1_status, dashboard_priority,
             excel_export_priority, source_verification_status, higher_is_better,
             source_caveats, audit_notes, updated_at)
        VALUES
            (:kpi_id, :display_name, :description, :kpi_type, :macro_category, :subsector,
             :unit, :primary_source, :primary_source_field, :fallback_source,
             :fallback_source_field, :calculation_method, :v1_status, :dashboard_priority,
             :excel_export_priority, :source_verification_status, :higher_is_better,
             :source_caveats, :audit_notes, datetime('now'))
    """), [
        {
            "kpi_id": k.kpi_id,
            "display_name": k.display_name,
            "description": k.description,
            "kpi_type": k.kpi_type,
            "macro_category": k.macro_category,
            "subsector": k.subsector,
            "unit": k.unit,
            "primary_source": k.primary_source,
            "primary_source_field": k.primary_source_field,
            "fallback_source": k.fallback_source,
            "fallback_source_field": k.fallback_source_field,
            "calculation_method": k.calculation_method,
            "v1_status": k.v1_status,
            "dashboard_priority": k.dashboard_priority,
            "excel_export_priority": k.excel_export_priority,
            "source_verification_status": k.source_verification_status,
            "higher_is_better": None if k.higher_is_better is None else int(k.higher_is_better),
            "source_caveats": k.source_caveats,
            "audit_notes": k.audit_notes,
        }
        for k in _ENERGY_CATALOG
    ])
