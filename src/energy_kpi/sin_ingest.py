"""SIN subsystem KPI ingestion helpers.

Parsers are pure local CSV -> tidy dataframe. Network access is only used by
explicit refresh jobs that call the fetch helpers in this module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from sqlalchemy import text

from src.energy_kpi.sin_catalog import SIN_CATALOG_BY_ID, SIN_KPI_CATALOG, SIN_NS, SIN_SUBSYSTEMS
from src.settings import AppPaths

logger = logging.getLogger(__name__)

ONS_PACKAGE_API = "https://dados.ons.org.br/api/3/action/package_show?id={package_id}"
CCEE_PACKAGE_API = "https://dadosabertos.ccee.org.br/api/3/action/package_show?id=pld_horario"

ONS_DATASETS: dict[str, dict[str, str]] = {
    "balanco_energia_subsistema": {
        "package_id": "balanco-energia-subsistema",
        "resource_pattern": r"BALANCO_ENERGIA_SUBSISTEMA_(?P<year>\d{4})\.csv",
    },
    "ear_diario_subsistema": {
        "package_id": "ear-diario-por-subsistema",
        "resource_pattern": r"EAR_DIARIO_SUBSISTEMA_(?P<year>\d{4})\.csv",
    },
    "ena_diario_subsistema": {
        "package_id": "ena-diario-por-subsistema",
        "resource_pattern": r"ENA_DIARIO_SUBSISTEMA_(?P<year>\d{4})\.csv",
    },
    "cmo_semihorario": {
        "package_id": "cmo-semi-horario",
        "resource_pattern": r"CMO_SEMIHORARIO_(?P<year>\d{4})\.csv",
    },
}

_SUBSYSTEM_ALIAS: dict[str, str] = {}
for _code, _display, _aliases in SIN_SUBSYSTEMS:
    for _alias in _aliases:
        _SUBSYSTEM_ALIAS[_alias] = _code


@dataclass(frozen=True)
class SINSnapshotRecord:
    snapshot_id: str
    source: str
    source_dataset: str
    fetched_at: str
    file_path: Path
    sha256: str
    row_count: int
    source_url: str
    source_version_label: str
    status: str = "ok"


def normalize_subsystem_code(value: object) -> str | None:
    """Map ONS/CCEE subsystem labels to stable internal SIN codes."""
    if value is None:
        return None
    raw = str(value).strip().upper()
    if not raw:
        return None
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw)
    compact = raw.replace(" ", "").replace("-", "").replace("_", "")
    variants = {
        raw,
        compact,
        compact.replace("/", ""),
        raw.replace(" - ", "/"),
    }
    for candidate in variants:
        if candidate in _SUBSYSTEM_ALIAS:
            return _SUBSYSTEM_ALIAS[candidate]
    if compact in {"SECO", "SECOO", "SUDESTECENTROOESTE", "SUDESTECENTRO-OESTE"}:
        return "SE_CO"
    return None


def seed_subsystem_dimension(conn) -> None:
    rows = [
        {
            "code": code,
            "display_name": display,
            "aliases": ",".join(aliases),
            "sort_order": idx,
        }
        for idx, (code, display, aliases) in enumerate(SIN_SUBSYSTEMS, start=1)
    ]
    conn.execute(
        text("""
            INSERT OR REPLACE INTO subsystem_dimension
                (subsystem_code, display_name, source_aliases, sort_order)
            VALUES (:code, :display_name, :aliases, :sort_order)
        """),
        rows,
    )


def seed_sin_kpi_sources(conn) -> None:
    conn.execute(text("""
        INSERT OR IGNORE INTO kpi_sources
            (source, display_name, base_url, license, default_priority, cadence,
             retrieval_method, notes)
        VALUES
            ('ONS', 'Operador Nacional do Sistema Elétrico - Dados Abertos',
             'https://dados.ons.org.br', 'Dados abertos ONS', 1,
             'hourly/daily', 'CKAN package metadata + CSV resources',
             'SIN subsystem operating data: load, generation, EAR, ENA, CMO'),
            ('CCEE', 'CCEE Dados Abertos',
             'https://dadosabertos.ccee.org.br', 'Dados abertos CCEE', 2,
             'hourly', 'CKAN resource download or datastore API',
             'PLD hourly by submarket; direct download may be blocked in some environments'),
            ('EPE', 'Empresa de Pesquisa Energética - Dados Abertos',
             'https://www.epe.gov.br', 'planned', 3,
             'monthly', 'planned connector',
             'Future electricity consumption connector; not implemented in this MVP'),
            ('ANEEL', 'ANEEL Dados Abertos',
             'https://dadosabertos.aneel.gov.br', 'planned', 4,
             'monthly/annual', 'planned connector',
             'Future capacity, MMGD, DEC/FEC and tariff connectors; not implemented in this MVP')
    """))


def seed_sin_kpi_catalog(conn) -> None:
    conn.execute(
        text("""
            INSERT OR REPLACE INTO kpi_catalog
                (kpi_id, display_name, description, kpi_type, macro_category, subsector,
                 sector, geography_type, entity_type, unit, frequency, primary_source,
                 primary_source_field, calculation_method, v1_status, dashboard_priority,
                 excel_export_priority, source_verification_status, source_caveats,
                 audit_notes, owner_module, availability_status, updated_at)
            VALUES
                (:kpi_id, :display_name, :description, :kpi_type, :macro_category,
                 'SIN Subsystems', 'Energy Utilities', 'subsystem', 'subsystem',
                 :unit, :frequency, :source, :source_field, :calculation_method,
                 'v1_required', :dashboard_priority, :excel_export_priority,
                 :source_verification_status, :source_caveats, :audit_notes,
                 'energy_kpi.sin', 'available', datetime('now'))
        """),
        [
            {
                "kpi_id": entry.kpi_id,
                "display_name": entry.display_name,
                "description": entry.description,
                "kpi_type": entry.kpi_type,
                "macro_category": entry.macro_category,
                "unit": entry.unit,
                "frequency": entry.frequency,
                "source": entry.source,
                "source_field": entry.source_field,
                "calculation_method": entry.calculation_method,
                "dashboard_priority": entry.dashboard_priority,
                "excel_export_priority": entry.excel_export_priority,
                "source_verification_status": entry.source_verification_status,
                "source_caveats": entry.source_caveats,
                "audit_notes": entry.audit_notes,
            }
            for entry in SIN_KPI_CATALOG
        ],
    )


def fetch_ons_snapshot(paths: AppPaths, dataset: str, year: int, timeout: int = 120) -> SINSnapshotRecord:
    meta = ONS_DATASETS[dataset]
    package = requests.get(ONS_PACKAGE_API.format(package_id=meta["package_id"]), timeout=30)
    package.raise_for_status()
    package_json = package.json()
    resources = package_json.get("result", {}).get("resources", [])
    resource = _select_year_resource(resources, meta["resource_pattern"], year)
    if not resource:
        raise RuntimeError(f"ONS resource not found for dataset={dataset} year={year}")
    return fetch_csv_snapshot(
        paths=paths,
        source="ONS",
        source_dataset=dataset,
        url=str(resource["url"]),
        year=year,
        timeout=timeout,
    )


def fetch_ccee_pld_snapshot(paths: AppPaths, year: int, timeout: int = 120) -> SINSnapshotRecord:
    package = requests.get(
        CCEE_PACKAGE_API,
        timeout=30,
        headers={"User-Agent": "CVMAnalytics/energy-kpi"},
    )
    package.raise_for_status()
    package_json = package.json()
    resources = package_json.get("result", {}).get("resources", [])
    resource = _select_resource_by_year_or_csv(resources, year)
    if not resource:
        raise RuntimeError(f"CCEE PLD resource not found for year={year}")
    return fetch_csv_snapshot(
        paths=paths,
        source="CCEE",
        source_dataset="pld_horario",
        url=str(resource["url"]),
        year=year,
        timeout=timeout,
    )


def fetch_csv_snapshot(
    *,
    paths: AppPaths,
    source: str,
    source_dataset: str,
    url: str,
    year: int,
    timeout: int = 120,
) -> SINSnapshotRecord:
    snapshot_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snap_dir = paths.energy_kpi_raw_dir / source.lower() / source_dataset / str(year) / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    dest = snap_dir / f"{source_dataset}_{year}.csv"

    response = requests.get(
        url,
        timeout=timeout,
        stream=True,
        headers={"User-Agent": "CVMAnalytics/energy-kpi"},
    )
    response.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    sha = _sha256_file(dest)
    row_count = _count_data_rows(dest)
    return SINSnapshotRecord(
        snapshot_id=snapshot_id,
        source=source,
        source_dataset=source_dataset,
        fetched_at=fetched_at,
        file_path=dest,
        sha256=sha,
        row_count=row_count,
        source_url=url,
        source_version_label=f"{source_dataset}:{year}",
    )


def persist_sin_snapshot_record(conn, snapshot: SINSnapshotRecord) -> None:
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
            "source": snapshot.source,
            "fetched_at": snapshot.fetched_at,
            "file_path": str(snapshot.file_path),
            "sha256": snapshot.sha256,
            "row_count": snapshot.row_count,
            "source_version_label": snapshot.source_version_label,
            "status": snapshot.status,
        },
    )


def parse_ons_balanco(snapshot: SINSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path, sep=";")
    required = {
        "id_subsistema",
        "din_instante",
        "val_gerhidraulica",
        "val_gertermica",
        "val_gereolica",
        "val_gersolar",
        "val_carga",
        "val_intercambio",
    }
    _require_columns(df, required, snapshot.source_dataset)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        subsystem = normalize_subsystem_code(row.get("id_subsistema") or row.get("nom_subsistema"))
        ref = _parse_datetime(row.get("din_instante"))
        if not subsystem or not ref:
            continue
        hydro = _to_float(row.get("val_gerhidraulica"))
        thermal = _to_float(row.get("val_gertermica"))
        wind = _to_float(row.get("val_gereolica"))
        solar = _to_float(row.get("val_gersolar"))
        total = sum(v for v in (hydro, thermal, wind, solar) if v is not None)
        source_values = {
            "load_mwmed": (row.get("val_carga"), "val_carga"),
            "generation_hydro_mwmed": (hydro, "val_gerhidraulica"),
            "generation_thermal_mwmed": (thermal, "val_gertermica"),
            "generation_wind_mwmed": (wind, "val_gereolica"),
            "generation_solar_mwmed": (solar, "val_gersolar"),
            "generation_total_mwmed": (total, "derived_total_generation"),
            "net_interchange_mwmed": (row.get("val_intercambio"), "val_intercambio"),
        }
        if total > 0:
            source_values.update({
                "mix_hydro_pct": (None if hydro is None else hydro / total * 100, "val_gerhidraulica/derived_total_generation"),
                "mix_thermal_pct": (None if thermal is None else thermal / total * 100, "val_gertermica/derived_total_generation"),
                "mix_wind_pct": (None if wind is None else wind / total * 100, "val_gereolica/derived_total_generation"),
                "mix_solar_pct": (None if solar is None else solar / total * 100, "val_gersolar/derived_total_generation"),
            })
        for suffix, (value, source_field) in source_values.items():
            kpi_id = f"{SIN_NS}.{suffix}"
            rows.append(_make_observation(snapshot, kpi_id, subsystem, ref, value, source_field, row.to_dict()))
    return _observations_df(rows)


def parse_ons_ear(snapshot: SINSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path, sep=";")
    _require_columns(
        df,
        {"id_subsistema", "ear_data", "ear_verif_subsistema_mwmes", "ear_verif_subsistema_percentual"},
        snapshot.source_dataset,
    )
    return _parse_simple_ons_daily(
        df,
        snapshot,
        date_col="ear_data",
        mapping={
            "ear_stored_mwmes": "ear_verif_subsistema_mwmes",
            "ear_stored_pct": "ear_verif_subsistema_percentual",
        },
    )


def parse_ons_ena(snapshot: SINSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path, sep=";")
    _require_columns(
        df,
        {
            "id_subsistema",
            "ena_data",
            "ena_bruta_regiao_mwmed",
            "ena_bruta_regiao_percentualmlt",
            "ena_armazenavel_regiao_mwmed",
            "ena_armazenavel_regiao_percentualmlt",
        },
        snapshot.source_dataset,
    )
    return _parse_simple_ons_daily(
        df,
        snapshot,
        date_col="ena_data",
        mapping={
            "ena_gross_mwmed": "ena_bruta_regiao_mwmed",
            "ena_gross_pct_mlt": "ena_bruta_regiao_percentualmlt",
            "ena_storable_mwmed": "ena_armazenavel_regiao_mwmed",
            "ena_storable_pct_mlt": "ena_armazenavel_regiao_percentualmlt",
        },
    )


def parse_ons_cmo(snapshot: SINSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path, sep=";")
    _require_columns(df, {"id_subsistema", "din_instante", "val_cmo"}, snapshot.source_dataset)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        subsystem = normalize_subsystem_code(row.get("id_subsistema") or row.get("nom_subsistema"))
        ref = _parse_datetime(row.get("din_instante"))
        if not subsystem or not ref:
            continue
        rows.append(
            _make_observation(
                snapshot,
                f"{SIN_NS}.cmo_brl_mwh",
                subsystem,
                ref,
                row.get("val_cmo"),
                "val_cmo",
                row.to_dict(),
            )
        )
    return _observations_df(rows)


def parse_ccee_pld(snapshot: SINSnapshotRecord) -> pd.DataFrame:
    df = _read_csv(snapshot.file_path, sep=None)
    normalized_cols = {_normalize_col(c): c for c in df.columns}
    subsystem_col = _pick_col(normalized_cols, "SUBMERCADO", "submercado")
    value_col = _pick_col(normalized_cols, "PLD_HORA", "pld_hora", "PLD")
    if not subsystem_col or not value_col:
        raise RuntimeError("CCEE PLD CSV missing SUBMERCADO or PLD_HORA columns")
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        subsystem = normalize_subsystem_code(row.get(subsystem_col))
        ref = _parse_ccee_reference(row, normalized_cols)
        if not subsystem or not ref:
            continue
        rows.append(
            _make_observation(
                snapshot,
                f"{SIN_NS}.pld_brl_mwh",
                subsystem,
                ref,
                row.get(value_col),
                str(value_col),
                row.to_dict(),
            )
        )
    return _observations_df(rows)


def upsert_subsystem_kpi_values(conn, tidy_df: pd.DataFrame) -> int:
    if tidy_df.empty:
        return 0
    rows = tidy_df.to_dict(orient="records")
    conn.execute(
        text("""
            INSERT OR REPLACE INTO subsystem_kpi_values
                (kpi_id, subsystem_code, reference_datetime, source_value,
                 normalized_value, unit, source, source_dataset, source_field,
                 source_hash, snapshot_id, ingestion_batch_id, data_quality_status,
                 updated_at)
            VALUES
                (:kpi_id, :subsystem_code, :reference_datetime, :source_value,
                 :normalized_value, :unit, :source, :source_dataset, :source_field,
                 :source_hash, :snapshot_id, :ingestion_batch_id, :data_quality_status,
                 datetime('now'))
        """),
        rows,
    )
    return len(rows)


def _parse_simple_ons_daily(
    df: pd.DataFrame,
    snapshot: SINSnapshotRecord,
    *,
    date_col: str,
    mapping: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        subsystem = normalize_subsystem_code(row.get("id_subsistema") or row.get("nom_subsistema"))
        ref = _parse_datetime(row.get(date_col))
        if not subsystem or not ref:
            continue
        for suffix, source_field in mapping.items():
            rows.append(
                _make_observation(
                    snapshot,
                    f"{SIN_NS}.{suffix}",
                    subsystem,
                    ref,
                    row.get(source_field),
                    source_field,
                    row.to_dict(),
                )
            )
    return _observations_df(rows)


def _make_observation(
    snapshot: SINSnapshotRecord,
    kpi_id: str,
    subsystem_code: str,
    reference_datetime: str,
    value: object,
    source_field: str,
    raw_row: dict[str, Any],
) -> dict[str, Any]:
    normalized_value = _to_float(value)
    source_value = normalized_value
    catalog = SIN_CATALOG_BY_ID[kpi_id]
    hash_payload = {
        "source": snapshot.source,
        "source_dataset": snapshot.source_dataset,
        "snapshot_id": snapshot.snapshot_id,
        "kpi_id": kpi_id,
        "subsystem_code": subsystem_code,
        "reference_datetime": reference_datetime,
        "source_field": source_field,
        "value": normalized_value,
        "raw": _json_safe_row(raw_row),
    }
    return {
        "kpi_id": kpi_id,
        "subsystem_code": subsystem_code,
        "reference_datetime": reference_datetime,
        "source_value": source_value,
        "normalized_value": normalized_value,
        "unit": catalog.unit,
        "source": snapshot.source,
        "source_dataset": snapshot.source_dataset,
        "source_field": source_field,
        "source_hash": hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "snapshot_id": snapshot.snapshot_id,
        "ingestion_batch_id": snapshot.snapshot_id,
        "data_quality_status": "missing" if normalized_value is None else "ok",
    }


def _observations_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    cols = [
        "kpi_id",
        "subsystem_code",
        "reference_datetime",
        "source_value",
        "normalized_value",
        "unit",
        "source",
        "source_dataset",
        "source_field",
        "source_hash",
        "snapshot_id",
        "ingestion_batch_id",
        "data_quality_status",
    ]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).dropna(subset=["normalized_value"])


def _select_year_resource(resources: list[dict[str, Any]], pattern: str, year: int) -> dict[str, Any] | None:
    rx = re.compile(pattern, re.IGNORECASE)
    for resource in resources:
        url = str(resource.get("url") or "")
        name = str(resource.get("name") or "")
        match = rx.search(url) or rx.search(name)
        if match and int(match.group("year")) == int(year):
            return resource
    return None


def _select_resource_by_year_or_csv(resources: list[dict[str, Any]], year: int) -> dict[str, Any] | None:
    csv_resources = [
        r for r in resources
        if "csv" in str(r.get("format") or "").lower()
        or str(r.get("url") or "").lower().endswith(".csv")
    ]
    for resource in csv_resources:
        haystack = f"{resource.get('name') or ''} {resource.get('url') or ''}"
        if str(year) in haystack:
            return resource
    return csv_resources[0] if csv_resources else None


def _read_csv(path: Path, sep: str | None) -> pd.DataFrame:
    if sep is None:
        return pd.read_csv(path, sep=None, engine="python", decimal=",")
    return pd.read_csv(path, sep=sep, decimal=".")


def _require_columns(df: pd.DataFrame, required: set[str], dataset: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"{dataset} missing required columns: {sorted(missing)}")


def _parse_datetime(value: object) -> str | None:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime().replace(tzinfo=None).isoformat(timespec="seconds")


def _parse_ccee_reference(row, normalized_cols: dict[str, str]) -> str | None:
    date_col = _pick_col(normalized_cols, "DATA", "DATA_HORA", "DIN_INSTANTE")
    if date_col:
        return _parse_datetime(row.get(date_col))

    month_col = _pick_col(normalized_cols, "MES_REFERENCIA", "MES")
    day_col = _pick_col(normalized_cols, "DIA")
    hour_col = _pick_col(normalized_cols, "HORA")
    if not month_col or not day_col:
        return None
    month_value = str(row.get(month_col) or "").strip()
    day_value = str(row.get(day_col) or "").strip()
    hour_value = str(row.get(hour_col) or "0").strip() if hour_col else "0"

    year, month = _parse_year_month(month_value)
    if year is None or month is None:
        return None
    day = int(float(day_value))
    hour = _parse_hour(hour_value)
    try:
        return datetime(year, month, day, hour).isoformat(timespec="seconds")
    except ValueError:
        return None


def _parse_year_month(value: str) -> tuple[int | None, int | None]:
    digits = re.findall(r"\d+", value)
    if not digits:
        return None, None
    if len(digits) == 1 and len(digits[0]) == 6:
        return int(digits[0][:4]), int(digits[0][4:6])
    if len(digits) >= 2:
        a, b = int(digits[0]), int(digits[1])
        if a > 1900:
            return a, b
        return b, a
    return None, None


def _parse_hour(value: str) -> int:
    match = re.search(r"\d+", value)
    if not match:
        return 0
    hour = int(match.group(0))
    if 1 <= hour <= 24:
        return hour - 1
    return max(0, min(hour, 23))


def _normalize_col(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")


def _pick_col(normalized_cols: dict[str, str], *candidates: str) -> str | None:
    for candidate in candidates:
        found = normalized_cols.get(_normalize_col(candidate))
        if found:
            return found
    return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text_value = str(value).strip().replace("\xa0", "")
    if not text_value:
        return None
    if "," in text_value and "." not in text_value:
        text_value = text_value.replace(".", "").replace(",", ".")
    try:
        return float(text_value)
    except ValueError:
        return None


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, pd.Timestamp):
            out[str(key)] = value.isoformat()
        else:
            try:
                if pd.isna(value):
                    out[str(key)] = None
                else:
                    out[str(key)] = value
            except TypeError:
                out[str(key)] = value
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_data_rows(path: Path) -> int:
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)
