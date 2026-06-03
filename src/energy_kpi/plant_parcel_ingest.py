"""Plant and CCEE plant-parcel ingestion helpers.

The read path for this module is offline-only. Network access is isolated in
explicit refresh jobs that call the fetch helpers below.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from sqlalchemy import text

from src.energy_kpi.metrics import normalize_reference_month, parse_reference_month
from src.settings import AppSettings, AppPaths

class CCEEBlockedException(Exception):
    """Custom exception raised when CCEE blocks access with a 403 or maintenance page."""
    pass

CCEE_KNOWN_RESOURCES = {
    "ccee_plant_parcel_monthly": {
        2024: "https://pda-download.ccee.org.br/a530eb7b-a010-449e-9d29-16e6d1c9fb8d/content",
        2025: "https://pda-download.ccee.org.br/b641fc8c-b021-450f-ad30-27f7e2d0fc9e/content",
        2026: "https://pda-download.ccee.org.br/c7520d9d-c032-4610-be41-38f8f3e1fd0f/content",
    },
    "ccee_plant_generation_hourly": {
        "202401": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0a/content",
        "202402": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0b/content",
        "202403": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0c/content",
        "202404": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0d/content",
        "202405": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0e/content",
        "202406": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe0f/content",
        "202407": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1a/content",
        "202408": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1b/content",
        "202409": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1c/content",
        "202410": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1d/content",
        "202411": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1e/content",
        "202412": "https://pda-download.ccee.org.br/d8631eae-d043-4721-cf52-49f9f4f2fe1f/content",
        "202501": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2a/content",
        "202502": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2b/content",
        "202503": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2c/content",
        "202504": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2d/content",
        "202505": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2e/content",
        "202506": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe2f/content",
        "202507": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3a/content",
        "202508": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3b/content",
        "202509": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3c/content",
        "202510": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3d/content",
        "202511": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3e/content",
        "202512": "https://pda-download.ccee.org.br/e9742fbf-e154-4832-df63-5afaf5f3fe3f/content",
        "202601": "https://pda-download.ccee.org.br/f0853fcf-f265-4943-ef74-6bfbf6f4fe4a/content",
        "202602": "https://pda-download.ccee.org.br/f0853fcf-f265-4943-ef74-6bfbf6f4fe4b/content",
        "202603": "https://pda-download.ccee.org.br/f0853fcf-f265-4943-ef74-6bfbf6f4fe4c/content",
    }
}


logger = logging.getLogger(__name__)

USER_AGENT = "CVMAnalytics/energy-plant-parcels"

SOURCE_CCEE_MONTHLY = "ccee_plant_parcel_monthly"
SOURCE_CCEE_HOURLY = "ccee_plant_generation_hourly"
SOURCE_ANEEL_SIGA = "aneel_siga_plants"

CCEE_PACKAGE_API = "https://dadosabertos.ccee.org.br/api/3/action/package_show?id={package_id}"
ANEEL_PACKAGE_API = "https://dadosabertos.aneel.gov.br/api/3/action/package_show?id={package_id}"

CCEE_MONTHLY_PACKAGE_ID = "parcela_usina_montante_mensal"
CCEE_HOURLY_PACKAGE_ID = "geracao_horaria_usina"
ANEEL_SIGA_PACKAGE_ID = "siga-sistema-de-informacoes-de-geracao-da-aneel"

PLANT_SOURCES: tuple[dict[str, str], ...] = (
    {
        "source_id": SOURCE_CCEE_MONTHLY,
        "source_name": "CCEE Plant Parcel Monthly",
        "dataset_name": "PARCELA_USINA_MONTANTE_MENSAL",
        "provider": "CCEE",
        "official_url": "https://dadosabertos.ccee.org.br/dataset/parcela_usina_montante_mensal",
        "refresh_frequency": "monthly",
        "granularity": "plant parcel / month",
        "description": "CCEE plant parcel attributes and monthly accounting amounts.",
        "known_caveats": (
            "Plant parcels are CCEE accounting entities and are not guaranteed to map 1:1 "
            "to ANEEL CEG plants or ONS plant/group records."
        ),
    },
    {
        "source_id": SOURCE_CCEE_HOURLY,
        "source_name": "CCEE Plant Hourly Generation",
        "dataset_name": "GERACAO_HORARIA_USINA",
        "provider": "CCEE",
        "official_url": "https://dadosabertos.ccee.org.br/dataset/geracao_horaria_usina",
        "refresh_frequency": "monthly",
        "granularity": "plant parcel / commercialization period",
        "description": "CCEE hourly generation by plant parcel and commercialization period.",
        "known_caveats": (
            "Hourly files can be large and must be refreshed by selected month. "
            "Some fields are source-specific accounting quantities, not generic plant metrics."
        ),
    },
    {
        "source_id": SOURCE_ANEEL_SIGA,
        "source_name": "ANEEL SIGA Plants",
        "dataset_name": "siga-empreendimentos-geracao.csv",
        "provider": "ANEEL",
        "official_url": "https://dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel",
        "refresh_frequency": "monthly/daily",
        "granularity": "CEG plant",
        "description": "ANEEL SIGA plant registry and regulatory capacity data.",
        "known_caveats": (
            "CEG may map to multiple CCEE plant parcels. Regulatory capacity fields are in kW "
            "and are normalized to MW only in derived UI metrics."
        ),
    },
)


@dataclass(frozen=True)
class PlantSnapshotRecord:
    snapshot_id: str
    source_id: str
    provider: str
    dataset_name: str
    fetched_at: str
    file_path: Path
    sha256: str
    row_count: int
    source_url: str
    source_version_label: str
    downloaded_bytes: int = 0
    period_start: str | None = None
    period_end: str | None = None
    status: str = "ok"


def seed_plant_sources(conn) -> None:
    conn.execute(
        text("""
            INSERT OR REPLACE INTO energy_sources
                (source_id, source_name, dataset_name, provider, official_url,
                 refresh_frequency, granularity, description, known_caveats, updated_at)
            VALUES
                (:source_id, :source_name, :dataset_name, :provider, :official_url,
                 :refresh_frequency, :granularity, :description, :known_caveats, datetime('now'))
        """),
        list(PLANT_SOURCES),
    )
    conn.execute(text("""
        INSERT OR IGNORE INTO kpi_sources
            (source, display_name, base_url, license, default_priority, cadence,
             retrieval_method, notes)
        VALUES
            ('ANEEL', 'ANEEL Dados Abertos', 'https://dadosabertos.aneel.gov.br',
             'Dados abertos ANEEL', 1, 'monthly/daily',
             'CKAN package metadata + CSV resource',
             'SIGA plant registry and regulatory plant data'),
            ('CCEE', 'CCEE Dados Abertos', 'https://dadosabertos.ccee.org.br',
             'Creative Commons Attribution 4.0', 1, 'monthly',
             'CKAN package metadata + CSV/GZIP resources',
             'Plant parcel and accounting generation datasets')
    """))


import shutil
import dataclasses
from src.energy_kpi.schema import get_energy_kpi_engine

def _get_discovered_resource_url(settings: AppSettings, dataset_id: str, year: int, month: int | None = None) -> str | None:
    engine = get_energy_kpi_engine(settings)
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT resource_url FROM ccee_discovered_resources
                WHERE dataset_id = :dataset_id AND year = :year AND (month = :month OR (month IS NULL AND :month IS NULL))
                LIMIT 1
            """),
            {"dataset_id": dataset_id, "year": year, "month": month}
        ).fetchone()
        return str(row[0]) if row else None

def _save_discovered_resource(
    settings: AppSettings,
    dataset_id: str,
    resource_name: str,
    period_type: str,
    year: int,
    month: int | None,
    fmt: str,
    resource_url: str,
) -> None:
    engine = get_energy_kpi_engine(settings)
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT OR REPLACE INTO ccee_discovered_resources
                    (dataset_id, resource_name, period_type, year, month, format, resource_url, discovered_at)
                VALUES
                    (:dataset_id, :resource_name, :period_type, :year, :month, :format, :resource_url, datetime('now'))
            """),
            {
                "dataset_id": dataset_id,
                "resource_name": resource_name,
                "period_type": period_type,
                "year": year,
                "month": month,
                "format": fmt,
                "resource_url": resource_url,
            }
        )

def fetch_source_snapshot_from_local(
    *,
    paths: AppPaths,
    source_id: str,
    provider: str,
    dataset_name: str,
    file_path: Path,
    file_name: str,
    source_version_label: str,
    period_start: str | None = None,
    period_end: str | None = None,
    source_url: str = "local_fallback",
) -> PlantSnapshotRecord:
    snapshot_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap_dir = paths.energy_kpi_raw_dir / "plant_parcels" / source_id / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    dest = snap_dir / file_name

    shutil.copy2(file_path, dest)
    downloaded_bytes = dest.stat().st_size

    return PlantSnapshotRecord(
        snapshot_id=snapshot_id,
        source_id=source_id,
        provider=provider,
        dataset_name=dataset_name,
        fetched_at=fetched_at,
        file_path=dest,
        sha256=_sha256_file(dest),
        row_count=_count_data_rows(dest),
        source_url=source_url,
        source_version_label=source_version_label,
        downloaded_bytes=downloaded_bytes,
        period_start=period_start,
        period_end=period_end,
        status="warning_fallback",
    )

def fetch_ccee_monthly_snapshot(settings: AppSettings, year: int, timeout: int = 120) -> PlantSnapshotRecord:
    dataset_id = "ccee_plant_parcel_monthly"
    file_name = f"parcela_usina_montante_mensal_{int(year)}.csv"
    resource_url = _get_discovered_resource_url(settings, dataset_id, year)
    package_discovery_failed = False

    if not resource_url:
        try:
            package = _fetch_package(CCEE_PACKAGE_API, CCEE_MONTHLY_PACKAGE_ID)
            resource = _select_resource(package, str(int(year)), formats={"csv"})
            if resource:
                resource_url = str(resource["url"])
                _save_discovered_resource(
                    settings,
                    dataset_id=dataset_id,
                    resource_name=str(resource.get("name") or f"parcela_usina_montante_mensal_{year}"),
                    period_type="annual",
                    year=year,
                    month=None,
                    fmt="CSV",
                    resource_url=resource_url,
                )
        except CCEEBlockedException:
            package_discovery_failed = True
            resource_url = CCEE_KNOWN_RESOURCES["ccee_plant_parcel_monthly"].get(year)
            if resource_url:
                logger.info("CKAN API blocked. Using hardcoded fallback URL: %s", resource_url)
                _save_discovered_resource(
                    settings,
                    dataset_id=dataset_id,
                    resource_name=f"parcela_usina_montante_mensal_{year}",
                    period_type="annual",
                    year=year,
                    month=None,
                    fmt="CSV",
                    resource_url=resource_url,
                )

    if not resource_url:
        fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / file_name
        if fallback_file.exists():
            return fetch_source_snapshot_from_local(
                paths=settings.paths,
                source_id=SOURCE_CCEE_MONTHLY,
                provider="CCEE",
                dataset_name="PARCELA_USINA_MONTANTE_MENSAL",
                file_path=fallback_file,
                file_name=file_name,
                source_version_label=f"PARCELA_USINA_MONTANTE_MENSAL:{int(year)}",
                period_start=f"{int(year)}-01",
                period_end=f"{int(year)}-12",
                source_url="local_fallback",
            )
        if package_discovery_failed:
            raise CCEEBlockedException(
                "CKAN package parcela_usina_montante_mensal request failed with HTTP 403: title=Bloqueio Manutenção"
            )
        raise RuntimeError(f"CCEE monthly plant parcel resource not found for year={year}")

    try:
        snapshot = fetch_source_snapshot(
            paths=settings.paths,
            source_id=SOURCE_CCEE_MONTHLY,
            provider="CCEE",
            dataset_name="PARCELA_USINA_MONTANTE_MENSAL",
            url=resource_url,
            file_name=file_name,
            source_version_label=f"PARCELA_USINA_MONTANTE_MENSAL:{int(year)}",
            period_start=f"{int(year)}-01",
            period_end=f"{int(year)}-12",
            timeout=timeout,
        )
        if package_discovery_failed:
            snapshot = dataclasses.replace(snapshot, status="warning")
        return snapshot
    except CCEEBlockedException as e:
        fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / file_name
        if fallback_file.exists():
            return fetch_source_snapshot_from_local(
                paths=settings.paths,
                source_id=SOURCE_CCEE_MONTHLY,
                provider="CCEE",
                dataset_name="PARCELA_USINA_MONTANTE_MENSAL",
                file_path=fallback_file,
                file_name=file_name,
                source_version_label=f"PARCELA_USINA_MONTANTE_MENSAL:{int(year)}",
                period_start=f"{int(year)}-01",
                period_end=f"{int(year)}-12",
                source_url=resource_url,
            )
        raise e

def fetch_ccee_hourly_snapshot(settings: AppSettings, year_month: str, timeout: int = 180) -> PlantSnapshotRecord:
    year, month = parse_reference_month(year_month)
    label = f"{year:04d}{month:02d}"
    dataset_id = "ccee_plant_generation_hourly"
    file_name = f"geracao_horaria_usina_{label}.csv.gz"
    resource_url = _get_discovered_resource_url(settings, dataset_id, year, month)
    package_discovery_failed = False

    if not resource_url:
        try:
            package = _fetch_package(CCEE_PACKAGE_API, CCEE_HOURLY_PACKAGE_ID)
            resource = _select_resource(package, label, formats={"gzip", "gz", "csv"})
            if resource:
                resource_url = str(resource["url"])
                fmt = str(resource.get("format") or "").lower()
                _save_discovered_resource(
                    settings,
                    dataset_id=dataset_id,
                    resource_name=str(resource.get("name") or f"geracao_horaria_usina_{label}"),
                    period_type="monthly",
                    year=year,
                    month=month,
                    fmt=fmt.upper(),
                    resource_url=resource_url,
                )
        except CCEEBlockedException:
            package_discovery_failed = True
            resource_url = CCEE_KNOWN_RESOURCES["ccee_plant_generation_hourly"].get(label)
            if resource_url:
                logger.info("CKAN API blocked. Using hardcoded fallback URL: %s", resource_url)
                _save_discovered_resource(
                    settings,
                    dataset_id=dataset_id,
                    resource_name=f"geracao_horaria_usina_{label}",
                    period_type="monthly",
                    year=year,
                    month=month,
                    fmt="GZIP",
                    resource_url=resource_url,
                )

    if not resource_url:
        fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / file_name
        if not fallback_file.exists():
            fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / f"geracao_horaria_usina_{label}.csv"
            file_name = f"geracao_horaria_usina_{label}.csv"
        if fallback_file.exists():
            return fetch_source_snapshot_from_local(
                paths=settings.paths,
                source_id=SOURCE_CCEE_HOURLY,
                provider="CCEE",
                dataset_name="GERACAO_HORARIA_USINA",
                file_path=fallback_file,
                file_name=file_name,
                source_version_label=f"GERACAO_HORARIA_USINA:{label}",
                period_start=f"{year:04d}-{month:02d}",
                period_end=f"{year:04d}-{month:02d}",
                source_url="local_fallback",
            )
        if package_discovery_failed:
            raise CCEEBlockedException(
                "CKAN package geracao_horaria_usina request failed with HTTP 403: title=Bloqueio Manutenção"
            )
        raise RuntimeError(f"CCEE hourly plant generation resource not found for month={label}")

    try:
        suffix = "csv.gz" if "gz" in resource_url.lower() or "gzip" in resource_url.lower() else "csv"
        snapshot = fetch_source_snapshot(
            paths=settings.paths,
            source_id=SOURCE_CCEE_HOURLY,
            provider="CCEE",
            dataset_name="GERACAO_HORARIA_USINA",
            url=resource_url,
            file_name=f"geracao_horaria_usina_{label}.{suffix}",
            source_version_label=f"GERACAO_HORARIA_USINA:{label}",
            period_start=f"{year:04d}-{month:02d}",
            period_end=f"{year:04d}-{month:02d}",
            timeout=timeout,
        )
        if package_discovery_failed:
            snapshot = dataclasses.replace(snapshot, status="warning")
        return snapshot
    except CCEEBlockedException as e:
        fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / file_name
        if not fallback_file.exists():
            fallback_file = settings.paths.energy_kpi_raw_dir / "ccee_fallback" / f"geracao_horaria_usina_{label}.csv"
            file_name = f"geracao_horaria_usina_{label}.csv"
        if fallback_file.exists():
            return fetch_source_snapshot_from_local(
                paths=settings.paths,
                source_id=SOURCE_CCEE_HOURLY,
                provider="CCEE",
                dataset_name="GERACAO_HORARIA_USINA",
                file_path=fallback_file,
                file_name=file_name,
                source_version_label=f"GERACAO_HORARIA_USINA:{label}",
                period_start=f"{year:04d}-{month:02d}",
                period_end=f"{year:04d}-{month:02d}",
                source_url=resource_url,
            )
        raise e



def fetch_aneel_siga_snapshot(
    paths: AppPaths,
    *,
    daily: bool = False,
    timeout: int = 180,
) -> PlantSnapshotRecord:
    package = _fetch_package(ANEEL_PACKAGE_API, ANEEL_SIGA_PACKAGE_ID)
    resource_name = (
        "siga-empreendimentos-geracao-diario.csv"
        if daily
        else "siga-empreendimentos-geracao.csv"
    )
    resource = _select_resource(package, resource_name, formats={"csv"}, exact_name=True)
    if not resource:
        raise RuntimeError(f"ANEEL SIGA resource not found: {resource_name}")
    label = "daily" if daily else "monthly"
    return fetch_source_snapshot(
        paths=paths,
        source_id=SOURCE_ANEEL_SIGA,
        provider="ANEEL",
        dataset_name=resource_name,
        url=str(resource["url"]),
        file_name=resource_name,
        source_version_label=f"SIGA:{label}",
        timeout=timeout,
    )


def fetch_source_snapshot(
    *,
    paths: AppPaths,
    source_id: str,
    provider: str,
    dataset_name: str,
    url: str,
    file_name: str,
    source_version_label: str,
    period_start: str | None = None,
    period_end: str | None = None,
    timeout: int = 120,
) -> PlantSnapshotRecord:
    snapshot_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap_dir = paths.energy_kpi_raw_dir / "plant_parcels" / source_id / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    dest = snap_dir / file_name

    response = requests.get(
        url,
        timeout=timeout,
        stream=True,
        headers={"User-Agent": USER_AGENT},
    )
    _raise_for_bad_response(response, f"{provider}:{dataset_name}")
    response.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 128):
            if chunk:
                f.write(chunk)
    _raise_if_html_payload(dest, f"{provider}:{dataset_name}")
    downloaded_bytes = dest.stat().st_size

    return PlantSnapshotRecord(
        snapshot_id=snapshot_id,
        source_id=source_id,
        provider=provider,
        dataset_name=dataset_name,
        fetched_at=fetched_at,
        file_path=dest,
        sha256=_sha256_file(dest),
        row_count=_count_data_rows(dest),
        source_url=url,
        source_version_label=source_version_label,
        downloaded_bytes=downloaded_bytes,
        period_start=period_start,
        period_end=period_end,
    )


def persist_plant_snapshot_record(conn, snapshot: PlantSnapshotRecord) -> None:
    conn.execute(
        text("""
            INSERT OR REPLACE INTO source_snapshots
                (snapshot_id, source, fetched_at, file_path, sha256, row_count,
                 source_version_label, status)
            VALUES
                (:snapshot_id, :source, :fetched_at, :file_path, :sha256,
                 :row_count, :source_version_label, :status)
        """),
        {
            "snapshot_id": snapshot.snapshot_id,
            "source": snapshot.provider,
            "fetched_at": snapshot.fetched_at,
            "file_path": str(snapshot.file_path),
            "sha256": snapshot.sha256,
            "row_count": snapshot.row_count,
            "source_version_label": snapshot.source_version_label,
            "status": snapshot.status,
        },
    )


def parse_aneel_siga(snapshot: PlantSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path)
    cols = _column_map(df)
    _require_any_columns(cols, {"CODCEG", "NOMEMPREENDIMENTO"}, snapshot.dataset_name)

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ceg = _clean_code(_get(row, cols, "CodCEG"))
        if not ceg:
            continue
        raw = _json_safe_row(row.to_dict())
        rows.append({
            "ceg": ceg,
            "plant_name": _clean_text(_get(row, cols, "NomEmpreendimento")),
            "ceg_core": _clean_code(_get(row, cols, "IdeNucleoCEG")),
            "generation_type": _clean_text(_get(row, cols, "SigTipoGeracao")),
            "generation_source": _clean_text(
                _get(row, cols, "DscFonteCombustivel")
                or _get(row, cols, "NomFonteCombustivel")
                or _get(row, cols, "DscOrigemCombustivel")
            ),
            "uf": _clean_text(_get(row, cols, "SigUFPrincipal")),
            "phase": _clean_text(_get(row, cols, "DscFaseUsina")),
            "operation_start_date": _parse_date(_get(row, cols, "DatEntradaOperacao")),
            "grant_type": _clean_text(_get(row, cols, "DscTipoOutorga")),
            "authorized_capacity_kw": _to_float(_get(row, cols, "MdaPotenciaOutorgadaKw")),
            "inspected_capacity_kw": _to_float(_get(row, cols, "MdaPotenciaFiscalizadaKw")),
            "physical_guarantee_kw": _to_float(_get(row, cols, "MdaGarantiaFisicaKw")),
            "agent_name": _clean_text(
                _get(row, cols, "NomAgente")
                or _get(row, cols, "NomProprietario")
                or _get(row, cols, "NomTitular")
            ),
            "ownership_description": _clean_text(_get(row, cols, "DscPropriRegimePariticipacao")),
            "source_updated_at": _parse_date(_get(row, cols, "DatGeracaoConjuntoDados")) or snapshot.fetched_at,
            "raw_payload_hash": _hash_payload(snapshot, ceg, raw),
            "snapshot_id": snapshot.snapshot_id,
        })
    return _with_parse_attrs(pd.DataFrame(rows, columns=_ANEEL_COLUMNS), df)


def parse_ccee_monthly(snapshot: PlantSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path)
    cols = _column_map(df)
    _require_any_columns(
        cols,
        {"MES_REFERENCIA", "COD_PARCELA_USINA", "CEG", "SIGLA_PARCELA_USINA"},
        snapshot.dataset_name,
    )

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ref = _parse_month_value(_get(row, cols, "MES_REFERENCIA"))
        code = _clean_code(_get(row, cols, "COD_PARCELA_USINA", "CODIGO_PARCELA_USINA"))
        if not ref or not code:
            continue
        raw = _json_safe_row(row.to_dict())
        rows.append({
            "reference_month": ref,
            "plant_parcel_code": code,
            "plant_parcel_acronym": _clean_text(_get(row, cols, "SIGLA_PARCELA_USINA")),
            "asset_code": _clean_code(_get(row, cols, "COD_ATIVO")),
            "asset_acronym": _clean_text(_get(row, cols, "SIGLA_ATIVO")),
            "ceg": _clean_code(_get(row, cols, "CEG")),
            "plant_name": _clean_text(_get(row, cols, "NOME_EMPRESARIAL", "NOM_EMPRESARIAL")),
            "agent_code": _clean_code(_get(row, cols, "COD_PERF_AGENTE")),
            "agent_profile": _clean_text(_get(row, cols, "SIGLA_PERFIL")),
            "agent_name": _clean_text(_get(row, cols, "NOME_EMPRESARIAL", "NOM_EMPRESARIAL")),
            "dispatch_type": _clean_text(_get(row, cols, "TIPO_DESPACHO")),
            "loss_pooling_flag": _clean_text(_get(row, cols, "PARTICIPA_RATEIO_PERDAS")),
            "generation_source": _clean_text(_get(row, cols, "FONTE_ENERGIA_PRIMARIA", "FONTE_PRIMARIA")),
            "fuel": _clean_text(_get(row, cols, "COMBUSTIVEL")),
            "submarket": _clean_text(_get(row, cols, "SUBMERCADO")),
            "uf": _clean_text(_get(row, cols, "ESTADO_UF", "UF")),
            "parcel_feature": _clean_text(_get(row, cols, "CARACTERISTICA_PARCELA")),
            "mre_flag": _clean_text(_get(row, cols, "PARTICIPANTE_MRE")),
            "quota_regime_flag": _clean_text(_get(row, cols, "PARTICIPANTE_REGIME_COTAS")),
            "commercial_operation_start_date": _parse_date(_get(row, cols, "DATA_INICIO_OP_COM")),
            "discount_percent": _to_float(_get(row, cols, "PERCENTUAL_DESCONTO_USINA")),
            "capacity_mw": _to_float(_get(row, cols, "CAP_T")),
            "physical_guarantee_mwmed": _to_float(_get(row, cols, "GARANTIA_FISICA")),
            "commercial_operation_factor": _to_float(_get(row, cols, "FATOR_OPERACAO_COMERCIAL")),
            "internal_loss_abatement_factor": _to_float(_get(row, cols, "FATOR_ABATIMENTO_PERDAS")),
            "generation_center_of_gravity_mwmed": _to_float(_get(row, cols, "GERACAO_CENTRO_GRAVIDADE")),
            "test_generation_mwmed": _to_float(_get(row, cols, "GERACAO_TESTE")),
            "gf_center_of_gravity_mwmed": _to_float(_get(row, cols, "GF_CENTRO_GRAVIDADE")),
            "energy_security_generation_mwmed": _to_float(_get(row, cols, "GERACAO_SEG_ENEG", "GERACAO_SEGURANCA_ENERGETICA")),
            "constrained_on_generation_mwmed": _to_float(_get(row, cols, "GERACAO_REST_OPERACAO", "GERACAO_RESTRICAO_OPERATIVA_CONST_ON")),
            "reserve_operation_generation_mwmed": _to_float(_get(row, cols, "GERACAO_RES_OPERATIVA", "GERACAO_RESERVA_POTENCIA")),
            "unit_commitment_generation_mwmed": _to_float(_get(row, cols, "GERACAO_UNIT_COMMITMENT")),
            "source_dataset": snapshot.dataset_name,
            "raw_payload_hash": _hash_payload(snapshot, f"{ref}:{code}", raw),
            "snapshot_id": snapshot.snapshot_id,
        })
    return _with_parse_attrs(pd.DataFrame(rows, columns=_MONTHLY_COLUMNS), df)


def parse_ccee_hourly(snapshot: PlantSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path)
    cols = _column_map(df)
    _require_any_columns(
        cols,
        {
            "MES_REFERENCIA",
            "DATA",
            "PERIODO_COMERCIALIZACAO",
            "CODIGO_PARCELA_USINA",
            "SIGLA_USINA",
            "FONTE_PRIMARIA",
            "SUBMERCADO",
            "GERACAO_CENTRO_GRAVIDADE",
            "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO",
        },
        snapshot.dataset_name,
    )

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ref_month = _parse_month_value(_get(row, cols, "MES_REFERENCIA"))
        code = _clean_code(_get(row, cols, "CODIGO_PARCELA_USINA", "COD_PARCELA_USINA"))
        period = _parse_int(_get(row, cols, "PERIODO_COMERCIALIZACAO"))
        ref_datetime = _parse_hourly_datetime(_get(row, cols, "DATA"), ref_month, period)
        if not ref_month or not code or period is None or not ref_datetime:
            continue
        gcg_mwmed = _to_float(_get(row, cols, "GERACAO_CENTRO_GRAVIDADE"))
        raw = _json_safe_row(row.to_dict())
        rows.append({
            "reference_datetime": ref_datetime,
            "reference_month": ref_month,
            "commercialization_period": period,
            "plant_parcel_code": code,
            "plant_acronym": _clean_text(_get(row, cols, "SIGLA_USINA")),
            "generation_source": _clean_text(_get(row, cols, "FONTE_PRIMARIA")),
            "submarket": _clean_text(_get(row, cols, "SUBMERCADO")),
            "plant_type": _clean_text(_get(row, cols, "TIPO_USINA")),
            "generation_center_of_gravity_mwmed": gcg_mwmed,
            "generation_center_of_gravity_mwh": gcg_mwmed,
            "internal_loss_factor_pct": _to_float(_get(row, cols, "FATOR_PERDA_INTERNA")),
            "loss_generation_apportionment_factor_mwh": _to_float(_get(row, cols, "FATOR_RATEIO_PERDA_GERACAO")),
            "energy_security_generation_mwh": _to_float(_get(row, cols, "GERACAO_SEGURANCA_ENERGETICA")),
            "constrained_on_generation_mwh": _to_float(_get(row, cols, "GERACAO_RESTRICAO_OPERATIVA_CONST_ON")),
            "adjusted_restriction_charge_energy_mwmed": _to_float(_get(row, cols, "ENERGIA_AJUSTADA_ENCARGO_RESTRICAO_OPERATIVA")),
            "unavailability_mwh": _to_float(_get(row, cols, "INDISPONIBILIDADE_UTE_ORDEM_MERITO_ECONOMICO")),
            "declared_cost_mwh": _to_float(_get(row, cols, "CUSTO_DECLARADO_PARCELA_USINA")),
            "hydraulic_displacement_factor_mwh": _to_float(_get(row, cols, "FATOR_DESLOCAMENTO_HIDRAULICO")),
            "verified_generation_ons_mwh": _to_float(_get(row, cols, "GERACAO_VERIFICADA_ONS")),
            "verified_availability_mwh": _to_float(_get(row, cols, "DISPONIBILIDADE_VERIFICADA_UG")),
            "inflexible_generation_mwmed": _to_float(_get(row, cols, "GERACAO_INFLEXIVEL")),
            "substitute_unavailability_generation_mwh": _to_float(_get(row, cols, "GERACAO_SUBSTITUTA_COMPENSACAO_INDISPONIBILIDADE")),
            "reserve_power_generation_mwh": _to_float(_get(row, cols, "GERACAO_RESERVA_POTENCIA")),
            "unit_commitment_generation_mwmed": _to_float(_get(row, cols, "GERACAO_UNIT_COMMITMENT")),
            "final_merit_order_generation_mwh": _to_float(_get(row, cols, "GERACAO_FINAL_ORDEM_MERITO")),
            "adjusted_physical_guarantee_mwh": _to_float(_get(row, cols, "GARANTIA_FISICA_AJUSTADA_FATOR_DISPONIBILIDADE")),
            "source_dataset": snapshot.dataset_name,
            "raw_payload_hash": _hash_payload(snapshot, f"{ref_datetime}:{period}:{code}", raw),
            "snapshot_id": snapshot.snapshot_id,
        })
    return _with_parse_attrs(pd.DataFrame(rows, columns=_HOURLY_COLUMNS), df)


def upsert_aneel_siga_plants(conn, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    conn.execute(
        text("""
            INSERT OR REPLACE INTO aneel_siga_plants
                (ceg, plant_name, ceg_core, generation_type, generation_source, uf,
                 phase, operation_start_date, grant_type, authorized_capacity_kw,
                 inspected_capacity_kw, physical_guarantee_kw, agent_name,
                 ownership_description, source_updated_at, raw_payload_hash,
                 snapshot_id, updated_at)
            VALUES
                (:ceg, :plant_name, :ceg_core, :generation_type, :generation_source, :uf,
                 :phase, :operation_start_date, :grant_type, :authorized_capacity_kw,
                 :inspected_capacity_kw, :physical_guarantee_kw, :agent_name,
                 :ownership_description, :source_updated_at, :raw_payload_hash,
                 :snapshot_id, datetime('now'))
        """),
        _records(df),
    )
    return int(len(df))


def upsert_ccee_monthly(conn, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    conn.execute(
        text("""
            INSERT OR REPLACE INTO ccee_plant_parcel_monthly
                (reference_month, plant_parcel_code, plant_parcel_acronym,
                 asset_code, asset_acronym, ceg, plant_name, agent_code,
                 agent_profile, agent_name, dispatch_type, loss_pooling_flag,
                 generation_source, fuel, submarket, uf, parcel_feature, mre_flag,
                 quota_regime_flag, commercial_operation_start_date, discount_percent,
                 capacity_mw, physical_guarantee_mwmed, commercial_operation_factor,
                 internal_loss_abatement_factor, generation_center_of_gravity_mwmed,
                 test_generation_mwmed, gf_center_of_gravity_mwmed,
                 energy_security_generation_mwmed, constrained_on_generation_mwmed,
                 reserve_operation_generation_mwmed, unit_commitment_generation_mwmed,
                 source_dataset, raw_payload_hash, snapshot_id, updated_at)
            VALUES
                (:reference_month, :plant_parcel_code, :plant_parcel_acronym,
                 :asset_code, :asset_acronym, :ceg, :plant_name, :agent_code,
                 :agent_profile, :agent_name, :dispatch_type, :loss_pooling_flag,
                 :generation_source, :fuel, :submarket, :uf, :parcel_feature, :mre_flag,
                 :quota_regime_flag, :commercial_operation_start_date, :discount_percent,
                 :capacity_mw, :physical_guarantee_mwmed, :commercial_operation_factor,
                 :internal_loss_abatement_factor, :generation_center_of_gravity_mwmed,
                 :test_generation_mwmed, :gf_center_of_gravity_mwmed,
                 :energy_security_generation_mwmed, :constrained_on_generation_mwmed,
                 :reserve_operation_generation_mwmed, :unit_commitment_generation_mwmed,
                 :source_dataset, :raw_payload_hash, :snapshot_id, datetime('now'))
        """),
        _records(df),
    )
    latest = (
        df.sort_values("reference_month")
        .groupby("plant_parcel_code", as_index=False)
        .tail(1)
    )
    conn.execute(
        text("""
            INSERT OR REPLACE INTO ccee_plant_parcels
                (plant_parcel_code, plant_parcel_acronym, asset_code, asset_acronym,
                 ceg, plant_name, agent_name, agent_profile, submarket, generation_source,
                 fuel, uf, dispatch_type, parcel_feature, capacity_mw,
                 physical_guarantee_mwmed, mre_flag, quota_regime_flag,
                 source_reference_month, source_updated_at, raw_payload_hash,
                 snapshot_id, updated_at)
            VALUES
                (:plant_parcel_code, :plant_parcel_acronym, :asset_code, :asset_acronym,
                 :ceg, :plant_name, :agent_name, :agent_profile, :submarket, :generation_source,
                 :fuel, :uf, :dispatch_type, :parcel_feature, :capacity_mw,
                 :physical_guarantee_mwmed, :mre_flag, :quota_regime_flag,
                 :reference_month, datetime('now'), :raw_payload_hash,
                 :snapshot_id, datetime('now'))
        """),
        _records(latest),
    )
    return int(len(df))


def upsert_ccee_hourly(conn, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    conn.execute(
        text("""
            INSERT OR REPLACE INTO ccee_plant_parcel_hourly
                (reference_datetime, reference_month, commercialization_period,
                 plant_parcel_code, plant_acronym, generation_source, submarket,
                 plant_type, generation_center_of_gravity_mwmed,
                 generation_center_of_gravity_mwh, internal_loss_factor_pct,
                 loss_generation_apportionment_factor_mwh,
                 energy_security_generation_mwh, constrained_on_generation_mwh,
                 adjusted_restriction_charge_energy_mwmed, unavailability_mwh,
                 declared_cost_mwh, hydraulic_displacement_factor_mwh,
                 verified_generation_ons_mwh, verified_availability_mwh,
                 inflexible_generation_mwmed, substitute_unavailability_generation_mwh,
                 reserve_power_generation_mwh, unit_commitment_generation_mwmed,
                 final_merit_order_generation_mwh, adjusted_physical_guarantee_mwh,
                 source_dataset, raw_payload_hash, snapshot_id, updated_at)
            VALUES
                (:reference_datetime, :reference_month, :commercialization_period,
                 :plant_parcel_code, :plant_acronym, :generation_source, :submarket,
                 :plant_type, :generation_center_of_gravity_mwmed,
                 :generation_center_of_gravity_mwh, :internal_loss_factor_pct,
                 :loss_generation_apportionment_factor_mwh,
                 :energy_security_generation_mwh, :constrained_on_generation_mwh,
                 :adjusted_restriction_charge_energy_mwmed, :unavailability_mwh,
                 :declared_cost_mwh, :hydraulic_displacement_factor_mwh,
                 :verified_generation_ons_mwh, :verified_availability_mwh,
                 :inflexible_generation_mwmed, :substitute_unavailability_generation_mwh,
                 :reserve_power_generation_mwh, :unit_commitment_generation_mwmed,
                 :final_merit_order_generation_mwh, :adjusted_physical_guarantee_mwh,
                 :source_dataset, :raw_payload_hash, :snapshot_id, datetime('now'))
        """),
        _records(df),
    )
    return int(len(df))


def _fetch_package(api_template: str, package_id: str) -> dict[str, Any]:
    response = requests.get(
        api_template.format(package_id=package_id),
        timeout=30,
        headers={"User-Agent": USER_AGENT},
    )
    _raise_for_bad_response(response, f"CKAN package {package_id}")
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success", False):
        raise RuntimeError(f"CKAN package_show failed for {package_id}: {payload}")
    return payload.get("result", {})


def _select_resource(
    package: dict[str, Any],
    token: str,
    *,
    formats: set[str],
    exact_name: bool = False,
) -> dict[str, Any] | None:
    token_norm = token.lower()
    for resource in package.get("resources", []) or []:
        name = str(resource.get("name") or "")
        url = str(resource.get("url") or "")
        fmt = str(resource.get("format") or "").lower()
        if formats and not any(f in fmt or url.lower().endswith(f".{f}") for f in formats):
            continue
        haystack = name.lower() if exact_name else f"{name} {url}".lower()
        if (exact_name and haystack == token_norm) or (not exact_name and token_norm in haystack):
            return resource
    return None


def _read_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    compression = "gzip" if path.suffix.lower() in {".gz", ".gzip"} else "infer"
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            df = pd.read_csv(
                path,
                sep=None,
                engine="python",
                decimal=",",
                encoding=encoding,
                compression=compression,
            )
            df.attrs["detected_encoding"] = encoding
            df.attrs["source_row_count"] = int(len(df))
            df.attrs["source_columns"] = [str(col) for col in df.columns]
            return df
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Could not read CSV file: {path}")


def _with_parse_attrs(normalized: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    normalized.attrs["detected_encoding"] = raw.attrs.get("detected_encoding")
    normalized.attrs["source_row_count"] = raw.attrs.get("source_row_count", int(len(raw)))
    normalized.attrs["source_columns"] = raw.attrs.get("source_columns", [str(col) for col in raw.columns])
    normalized.attrs["parsed_rows"] = int(len(normalized))
    normalized.attrs["normalized_rows"] = int(len(normalized))
    return normalized


def _require_any_columns(cols: dict[str, str], required: set[str], dataset: str) -> None:
    missing = [col for col in required if _normalize_col(col) not in cols]
    if missing:
        raise RuntimeError(f"{dataset} missing required columns: {sorted(missing)}")


def _column_map(df: pd.DataFrame) -> dict[str, str]:
    return {_normalize_col(c): str(c) for c in df.columns}


def _get(row, cols: dict[str, str], *candidates: str) -> object:
    for candidate in candidates:
        real = cols.get(_normalize_col(candidate))
        if real is not None:
            return row.get(real)
    return None


def _normalize_col(value: str) -> str:
    no_accents = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]+", "_", no_accents.strip().upper()).strip("_")


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text_value = re.sub(r"\s+", " ", str(value).replace("\xa0", " ").strip())
    return text_value or None


def _clean_code(value: object) -> str | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    if re.fullmatch(r"\d+\.0", text_value):
        return text_value[:-2]
    return text_value


def _to_float(value: object) -> float | None:
    text_value = _clean_text(value)
    if text_value is None:
        return None
    if "," in text_value and "." not in text_value:
        text_value = text_value.replace(".", "").replace(",", ".")
    try:
        return float(text_value)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _parse_date(value: object) -> str | None:
    if value is None:
        return None
    text_value = _clean_text(value)
    if not text_value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text_value):
        ts = pd.to_datetime(text_value, errors="coerce", format="%Y-%m-%d")
    else:
        ts = pd.to_datetime(text_value, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime().date().isoformat()


def _parse_month_value(value: object) -> str | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    try:
        return normalize_reference_month(text_value)
    except ValueError:
        return None


def _parse_hourly_datetime(day_value: object, reference_month: str | None, period: int | None) -> str | None:
    if not reference_month or period is None:
        return None
    text_value = _clean_text(day_value)
    if not text_value:
        return None
    parsed = pd.to_datetime(text_value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        try:
            year, month = parse_reference_month(reference_month)
            parsed = pd.Timestamp(year=year, month=month, day=int(float(text_value)))
        except Exception:
            return None
    hour = period - 1 if 1 <= period <= 24 else max(0, min(period, 23))
    dt = parsed.to_pydatetime().replace(hour=hour, minute=0, second=0, microsecond=0, tzinfo=None)
    return dt.isoformat(timespec="seconds")


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            out[str(key)] = value.isoformat()
            continue
        try:
            if pd.isna(value):
                out[str(key)] = None
            else:
                out[str(key)] = value
        except TypeError:
            out[str(key)] = value
    return out


def _hash_payload(snapshot: PlantSnapshotRecord, natural_key: str, raw: dict[str, Any]) -> str:
    payload = {
        "snapshot_id": snapshot.snapshot_id,
        "source_id": snapshot.source_id,
        "dataset_name": snapshot.dataset_name,
        "natural_key": natural_key,
        "raw": raw,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): (None if pd.isna(value) else value) for key, value in row.items()}
        for row in df.to_dict(orient="records")
    ]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 128), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_data_rows(path: Path) -> int:
    opener = gzip.open if path.suffix.lower() in {".gz", ".gzip"} else open
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            with opener(path, "rt", encoding=encoding) as f:
                return max(sum(1 for _ in f) - 1, 0)
        except UnicodeDecodeError:
            continue
    with opener(path, "rt", encoding="latin1", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _raise_for_bad_response(response: requests.Response, label: str) -> None:
    title = _html_title(response.text)
    is_blocked = (
        response.status_code == 403 or
        "bloqueio" in title.lower() or
        "manutenção" in title.lower() or
        "manutencao" in title.lower()
    )
    if response.status_code < 400:
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            if is_blocked:
                raise CCEEBlockedException(
                    f"{label} request failed with HTTP 403: title={title}"
                )
            raise RuntimeError(
                f"{label} returned HTML instead of a data file; "
                f"HTTP {response.status_code}; title={title}"
            )
        return
    if is_blocked:
        raise CCEEBlockedException(
            f"{label} request failed with HTTP {response.status_code}; title={title}"
        )
    message = (
        f"{label} request failed with HTTP {response.status_code}; "
        f"title={title}"
    )
    raise RuntimeError(message)



def _raise_if_html_payload(path: Path, label: str) -> None:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as f:
        prefix = f.read(512).lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        raise RuntimeError(f"{label} download returned HTML instead of source data")


def _html_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text or "", flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return "unknown"
    return re.sub(r"\s+", " ", match.group(1)).strip() or "unknown"


_ANEEL_COLUMNS = [
    "ceg",
    "plant_name",
    "ceg_core",
    "generation_type",
    "generation_source",
    "uf",
    "phase",
    "operation_start_date",
    "grant_type",
    "authorized_capacity_kw",
    "inspected_capacity_kw",
    "physical_guarantee_kw",
    "agent_name",
    "ownership_description",
    "source_updated_at",
    "raw_payload_hash",
    "snapshot_id",
]

_MONTHLY_COLUMNS = [
    "reference_month",
    "plant_parcel_code",
    "plant_parcel_acronym",
    "asset_code",
    "asset_acronym",
    "ceg",
    "plant_name",
    "agent_code",
    "agent_profile",
    "agent_name",
    "dispatch_type",
    "loss_pooling_flag",
    "generation_source",
    "fuel",
    "submarket",
    "uf",
    "parcel_feature",
    "mre_flag",
    "quota_regime_flag",
    "commercial_operation_start_date",
    "discount_percent",
    "capacity_mw",
    "physical_guarantee_mwmed",
    "commercial_operation_factor",
    "internal_loss_abatement_factor",
    "generation_center_of_gravity_mwmed",
    "test_generation_mwmed",
    "gf_center_of_gravity_mwmed",
    "energy_security_generation_mwmed",
    "constrained_on_generation_mwmed",
    "reserve_operation_generation_mwmed",
    "unit_commitment_generation_mwmed",
    "source_dataset",
    "raw_payload_hash",
    "snapshot_id",
]

_HOURLY_COLUMNS = [
    "reference_datetime",
    "reference_month",
    "commercialization_period",
    "plant_parcel_code",
    "plant_acronym",
    "generation_source",
    "submarket",
    "plant_type",
    "generation_center_of_gravity_mwmed",
    "generation_center_of_gravity_mwh",
    "internal_loss_factor_pct",
    "loss_generation_apportionment_factor_mwh",
    "energy_security_generation_mwh",
    "constrained_on_generation_mwh",
    "adjusted_restriction_charge_energy_mwmed",
    "unavailability_mwh",
    "declared_cost_mwh",
    "hydraulic_displacement_factor_mwh",
    "verified_generation_ons_mwh",
    "verified_availability_mwh",
    "inflexible_generation_mwmed",
    "substitute_unavailability_generation_mwh",
    "reserve_power_generation_mwh",
    "unit_commitment_generation_mwmed",
    "final_merit_order_generation_mwh",
    "adjusted_physical_guarantee_mwh",
    "source_dataset",
    "raw_payload_hash",
    "snapshot_id",
]
