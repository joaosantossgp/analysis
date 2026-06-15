"""Data ingestion, downloading, and normalization for the ANEEL distribution domain."""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
import requests
import polars as pl
from sqlalchemy import text

from src.platform.settings import AppPaths
from src.energy_kpi.distribution.catalog import ANEEL_RESOURCES

logger = logging.getLogger(__name__)

USER_AGENT = "CVMAnalytics/1.0 (electricity distribution connector)"
PARSER_VERSION = "distribution-ingest-v1"


class DistributionSchemaError(ValueError):
    """Raised when a Distribution source does not satisfy a parser schema contract."""


def _canonicalize_source_columns(
    df: pl.DataFrame,
    *,
    dataset_name: str,
    stage: str,
    file_path: Path,
    rename_map: dict[str, str],
    required_canonical: list[str],
) -> pl.DataFrame:
    """Map explicit source columns to parser-canonical names and validate them.

    The rename map is ordered by priority. If a canonical column is already
    present, later aliases for the same canonical field are left as extra source
    columns instead of creating duplicate names.
    """
    original_cols = list(df.columns)
    existing_cols = set(original_cols)
    rename_dict: dict[str, str] = {}
    claimed_targets = set(existing_cols)

    for source_col, canonical_col in rename_map.items():
        if source_col not in existing_cols:
            continue
        if source_col == canonical_col:
            claimed_targets.add(canonical_col)
            continue
        if canonical_col in claimed_targets:
            continue
        rename_dict[source_col] = canonical_col
        claimed_targets.add(canonical_col)

    if rename_dict:
        df = df.rename(rename_dict)

    missing = [col for col in required_canonical if col not in df.columns]
    if missing:
        matched_sources = sorted(rename_dict.keys())
        raise DistributionSchemaError(
            f"{dataset_name} parser canonicalization failed at {stage}: "
            f"missing canonical columns {missing}. "
            f"Mapped source columns: {matched_sources}. "
            f"Available columns: {original_cols}. "
            f"Resource: {file_path.name}. Parser: {PARSER_VERSION}."
        )

    return df


def _ensure_optional_columns(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    missing = [col for col in columns if col not in df.columns]
    if not missing:
        return df
    return df.with_columns([pl.lit(None).cast(pl.String).alias(col) for col in missing])


def _read_distribution_csv(file_path: Path, **kwargs) -> pl.DataFrame:
    """Read ANEEL CSVs with the encodings observed in official downloads."""
    last_exc: Exception | None = None
    for encoding in ("utf-8", "windows-1252", "latin1-lossy"):
        try:
            return pl.read_csv(file_path, separator=";", encoding=encoding, infer_schema_length=10000, **kwargs)
        except Exception as exc:
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _sha256_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _hash_columns(df: pl.DataFrame, columns: list[str], alias: str) -> pl.DataFrame:
    return df.with_columns(
        pl.concat_str([pl.col(col).fill_null("").cast(pl.String) for col in columns], separator="|")
        .map_elements(_sha256_text, return_dtype=pl.String)
        .alias(alias)
    )


def _unresolved_source_entity_id(prefix: str, raw_name: str | None, cnpj: str | None = None) -> str:
    raw_key = f"{cnpj or ''}|{raw_name or ''}".strip()
    return f"unresolved_{prefix}_{_sha256_text(raw_key)[:16]}"


def _reconcile_frame(df: pl.DataFrame, key_cols: list[str], value_cols: list[str] | None = None) -> dict:
    """Return compact row-flow counters for a normalized source frame."""
    value_cols = value_cols or []
    null_key_rows = (
        df.filter(pl.any_horizontal([pl.col(col).is_null() for col in key_cols])).height
        if key_cols
        else 0
    )
    distinct_keys = df.select(key_cols).unique().height if key_cols else df.height
    duplicate_groups = 0
    rows_in_duplicate_groups = 0
    conflicting_duplicate_groups = 0
    if key_cols:
        aggs = [pl.len().alias("rows")]
        aggs.extend(pl.col(col).n_unique().alias(f"{col}_distinct") for col in value_cols)
        dupes = df.group_by(key_cols).agg(aggs).filter(pl.col("rows") > 1)
        duplicate_groups = dupes.height
        rows_in_duplicate_groups = int(dupes["rows"].sum()) if dupes.height else 0
        if value_cols and dupes.height:
            conflict_expr = pl.any_horizontal([pl.col(f"{col}_distinct") > 1 for col in value_cols])
            conflicting_duplicate_groups = dupes.filter(conflict_expr).height
    return {
        "source_rows": df.height,
        "parsed_rows": df.height,
        "canonical_rows": df.height,
        "rows_missing_mandatory_keys": null_key_rows,
        "distinct_business_keys": distinct_keys,
        "duplicate_key_groups": duplicate_groups,
        "rows_in_duplicate_key_groups": rows_in_duplicate_groups,
        "conflicting_duplicate_key_groups": conflicting_duplicate_groups,
        "exact_duplicate_rows": df.height - df.unique().height,
    }


@dataclass(frozen=True)
class DistributionSnapshotRecord:
    snapshot_id: str
    source: str
    fetched_at: str
    file_path: Path
    sha256: str
    row_count: int
    source_version_label: str
    status: str = "ok"


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_distribution_resource(
    paths: AppPaths,
    conn,
    domain: str,
    resource_key: str | int | None = None,
    force: bool = False,
    timeout: int = 180,
) -> DistributionSnapshotRecord:
    """Download an ANEEL resource and register it in source_snapshots.

    Returns the DistributionSnapshotRecord.
    """
    # Resolve resource details from catalog
    if resource_key is not None:
        resource = ANEEL_RESOURCES.get(domain, {}).get(resource_key)
    else:
        resource = ANEEL_RESOURCES.get(domain)

    if not resource:
        raise ValueError(f"Resource not found in catalog for domain={domain}, key={resource_key}")

    url = resource["url"]
    file_name = resource["file_name"]
    fmt = resource["format"]
    resource_id = resource["resource_id"]

    version_label = f"ANEEL:{domain}"
    if resource_key is not None:
        version_label += f":{resource_key}"

    # Check if snapshot already exists in DB
    if not force:
        existing = conn.execute(
            text("""
                SELECT snapshot_id, file_path, sha256, row_count, fetched_at
                FROM source_snapshots
                WHERE source_version_label = :lbl AND status = 'ok'
                ORDER BY fetched_at DESC LIMIT 1
            """),
            {"lbl": version_label}
        ).fetchone()

        if existing:
            snap_id, fp_str, sha, r_count, fat = existing
            local_path = Path(fp_str)
            if local_path.exists():
                # Verify SHA matches
                current_sha = _sha256_file(local_path)
                if current_sha == sha:
                    logger.info("Reusing existing snapshot %s for %s", snap_id, version_label)
                    return DistributionSnapshotRecord(
                        snapshot_id=snap_id,
                        source="ANEEL",
                        fetched_at=fat,
                        file_path=local_path,
                        sha256=sha,
                        row_count=r_count,
                        source_version_label=version_label,
                    )

    # We need to download
    snapshot_id = str(uuid.uuid4())
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    
    # Target directory structure
    snap_dir = paths.energy_kpi_raw_dir / "distribution" / domain
    if resource_key is not None:
        snap_dir = snap_dir / str(resource_key)
    snap_dir = snap_dir / snapshot_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    
    dest = snap_dir / file_name

    logger.info("Downloading %s from %s to %s", version_label, url, dest)

    # Retry on transient server errors (5xx, 429, connection failures).
    # ANEEL's open-data portal returns occasional 502/503 under load.
    _RETRYABLE = {429, 500, 502, 503, 504}
    _MAX_ATTEMPTS = 3
    _BACKOFF_BASE = 5  # seconds; will be multiplied by 2^attempt

    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, stream=True)
            if resp.status_code in _RETRYABLE and attempt < _MAX_ATTEMPTS - 1:
                wait = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "ANEEL returned %s for %s (attempt %d/%d) — retrying in %ds",
                    resp.status_code, url, attempt + 1, _MAX_ATTEMPTS, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.ConnectionError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                wait = _BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    "Connection error downloading %s (attempt %d/%d) — retrying in %ds: %s",
                    url, attempt + 1, _MAX_ATTEMPTS, wait, exc,
                )
                time.sleep(wait)
            else:
                raise
    else:
        # All attempts used a retryable status code — raise the last response error
        resp.raise_for_status()

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=128 * 1024):
            if chunk:
                f.write(chunk)

    # Compute stats
    sha = _sha256_file(dest)
    
    # Read row count using Polars (very fast)
    row_count = 0
    try:
        if fmt == "parquet":
            # For parquet we can scan and collect the length without reading details
            row_count = pl.scan_parquet(dest).select(pl.len()).collect().item()
        elif fmt == "csv":
            # Count physical rows without parsing; parser-specific validation happens later.
            with open(dest, "rb") as f:
                row_count = max(sum(1 for _ in f) - 1, 0)
    except Exception as e:
        logger.warning("Failed to determine row count of %s: %s", dest.name, e)
        # Fallback to simple line count for CSV
        if fmt == "csv":
            try:
                with open(dest, "rb") as f:
                    row_count = sum(1 for _ in f) - 1  # subtract header
            except Exception:
                pass

    record = DistributionSnapshotRecord(
        snapshot_id=snapshot_id,
        source="ANEEL",
        fetched_at=fetched_at,
        file_path=dest,
        sha256=sha,
        row_count=row_count,
        source_version_label=version_label,
    )

    # Persist in DB
    conn.execute(
        text("""
            INSERT OR REPLACE INTO source_snapshots
                (snapshot_id, source, fetched_at, file_path, sha256, row_count,
                 source_version_label, status)
            VALUES
                (:sid, 'ANEEL', :fat, :fp, :sha, :rc, :lbl, 'ok')
        """),
        {
            "sid": record.snapshot_id,
            "fat": record.fetched_at,
            "fp": str(record.file_path),
            "sha": record.sha256,
            "rc": record.row_count,
            "lbl": record.source_version_label,
        }
    )

    return record


def parse_samp_mercado(file_path: Path, format_type: str = "parquet") -> pl.DataFrame:
    """Parse and normalize SAMP Mercado CSV/Parquet using Polars.

    Returns a normalized DataFrame with standardized fields.
    """
    logger.info("Parsing SAMP Mercado from %s", file_path)
    
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Standardize column mappings (ANEEL fields)
    rename_map = {
        "NumCNPJAgenteDistribuidora": "raw_cnpj",
        "NomAgenteDistribuidora": "raw_name",
        "SigAgenteDistribuidora": "raw_sigla",
        "NomTipoMercado": "market_type",
        "DscModalidadeTarifaria": "tariff_modality",
        "DscSubGrupoTarifario": "tariff_subgroup",
        "DscClasseConsumoMercado": "consumer_class",
        "DscSubClasseConsumidor": "consumer_subclass",
        "DscDetalheConsumidor": "consumer_detail",
        "DscPostoTarifario": "tariff_period",
        "DscOpcaoEnergia": "energy_option",
        "NumCNPJAgenteAcessante": "accessing_agent_cnpj",
        "NomAgenteAcessante": "accessing_agent_name",
        "DscDetalheMercado": "raw_metric",
        "DatCompetencia": "raw_date",
        "VlrMercado": "raw_value"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="SAMP Mercado",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=["raw_cnpj", "raw_name", "raw_date", "raw_value", "raw_metric"],
    )
    df = _ensure_optional_columns(
        df,
        [
            "raw_sigla",
            "market_type",
            "tariff_modality",
            "tariff_subgroup",
            "consumer_class",
            "consumer_subclass",
            "consumer_detail",
            "tariff_period",
            "energy_option",
            "accessing_agent_cnpj",
            "accessing_agent_name",
        ],
    )

    # Normalize values and types
    # Clean CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("raw_date").cast(pl.String).str.slice(0, 7).alias("reference_month")
    ])
    
    # Handle CNPJ padding
    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Cast raw value
    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0))

    # Standardize metrics
    # Receita Energia (R$), ICMS (R$), Consumo de Energia Elétrica (MWh), Número de Consumidores (Unidades)
    df = df.with_columns([
        pl.when(pl.col("raw_metric").str.contains("Receita"))
        .then(pl.lit("revenue"))
        .when(pl.col("raw_metric").str.contains("Consumo"))
        .then(pl.lit("billed_energy"))
        .when(pl.col("raw_metric").str.contains("Consumidores"))
        .then(pl.lit("consumer_count"))
        .when(pl.col("raw_metric").str.contains("ICMS"))
        .then(pl.lit("icms"))
        .otherwise(pl.lit("other"))
        .alias("metric_name"),

        pl.when(pl.col("raw_metric").str.contains("MWh"))
        .then(pl.lit("MWh"))
        .when(pl.col("raw_metric").str.contains("kWh"))
        .then(pl.lit("kWh"))
        .when(pl.col("raw_metric").str.contains(r"R\$"))
        .then(pl.lit("R$"))
        .otherwise(pl.lit("Unidades"))
        .alias("original_unit"),

        pl.when(pl.col("raw_metric").str.contains("MWh"))
        .then(pl.lit("MWh"))
        .when(pl.col("raw_metric").str.contains("kWh"))
        .then(pl.lit("MWh"))
        .when(pl.col("raw_metric").str.contains(r"R\$"))
        .then(pl.lit("BRL"))
        .otherwise(pl.lit("consumers"))
        .alias("normalized_unit")
    ])

    # Perform unit conversion
    df = df.with_columns(
        pl.when(pl.col("original_unit") == "kWh")
        .then(pl.col("raw_value") / 1000.0)
        .otherwise(pl.col("raw_value"))
        .alias("normalized_value")
    )

    # Accessing agent fields normalization
    if "accessing_agent_cnpj" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.String).alias("accessing_agent_cnpj"))
    else:
        df = df.with_columns(
            pl.col("accessing_agent_cnpj").cast(pl.String).str.replace_all(r"\D", "").str.zfill(14).fill_null("")
        )

    if "accessing_agent_name" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.String).alias("accessing_agent_name"))
    else:
        df = df.with_columns(pl.col("accessing_agent_name").cast(pl.String).fill_null(""))

    # Create row hash based on business keys
    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("reference_month"),
                pl.col("market_type").fill_null(""),
                pl.col("tariff_modality").fill_null(""),
                pl.col("tariff_subgroup").fill_null(""),
                pl.col("consumer_class").fill_null(""),
                pl.col("consumer_subclass").fill_null(""),
                pl.col("consumer_detail").fill_null(""),
                pl.col("tariff_period").fill_null(""),
                pl.col("energy_option").fill_null(""),
                pl.col("metric_name"),
                pl.col("accessing_agent_cnpj").fill_null("")
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "raw_sigla",
        "reference_month",
        "market_type",
        "tariff_modality",
        "tariff_subgroup",
        "consumer_class",
        "consumer_subclass",
        "consumer_detail",
        "tariff_period",
        "energy_option",
        "accessing_agent_cnpj",
        "accessing_agent_name",
        "metric_name",
        "raw_value",
        "normalized_value",
        "original_unit",
        "normalized_unit",
        "source_row_hash"
    ])


def upsert_samp_mercado_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed facts into distribution_market_facts, resolving distributor identities."""
    if df.height == 0:
        return 0

    # 1. Fetch existing CNPJ -> distributor_id mappings
    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    # 2. Identify and register new unmapped distributors dynamically
    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name", "raw_sigla"]).unique(subset=["normalized_cnpj"])
    
    new_dists = []
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = row["raw_sigla"] or f"CNPJ_{cnpj[:4]}"
            
            # Dynamic insert into distributors
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            new_dists.append(dist_id)
            logger.info("Dynamically registered unmapped distributor: %s (%s)", name, dist_id)

    # 3. Add distributor_id to DataFrame
    # Convert mapping to Polars join or replace
    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    # Filter rows with unresolved distributor_id
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        logger.warning("%d rows in market facts have unresolved distributor identities", unresolved_count)
        # Fallback to 'unresolved' distributor_id
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    # 4. Bulk insert into facts table
    records = df_with_dist.to_dicts()
    
    # Insert OR REPLACE in chunks to avoid SQLite variable limit
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_market_facts (
            fact_id, distributor_id, reference_month, market_type, tariff_modality,
            tariff_subgroup, consumer_class, consumer_subclass, consumer_detail,
            tariff_period, energy_option, accessing_agent_cnpj, accessing_agent_name,
            metric_name, raw_value, normalized_value, original_unit, normalized_unit,
            source_row_hash, snapshot_id
        )
        VALUES (
            :fact_id, :distributor_id, :reference_month, :market_type, :tariff_modality,
            :tariff_subgroup, :consumer_class, :consumer_subclass, :consumer_detail,
            :tariff_period, :energy_option, :accessing_agent_cnpj, :accessing_agent_name,
            :metric_name, :raw_value, :normalized_value, :original_unit, :normalized_unit,
            :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "fact_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "reference_month": r["reference_month"],
                "market_type": r.get("market_type"),
                "tariff_modality": r.get("tariff_modality"),
                "tariff_subgroup": r.get("tariff_subgroup"),
                "consumer_class": r.get("consumer_class"),
                "consumer_subclass": r.get("consumer_subclass"),
                "consumer_detail": r.get("consumer_detail"),
                "tariff_period": r.get("tariff_period"),
                "energy_option": r.get("energy_option"),
                "accessing_agent_cnpj": r.get("accessing_agent_cnpj"),
                "accessing_agent_name": r.get("accessing_agent_name"),
                "metric_name": r["metric_name"],
                "raw_value": r["raw_value"],
                "normalized_value": r["normalized_value"],
                "original_unit": r["original_unit"],
                "normalized_unit": r["normalized_unit"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d facts into distribution_market_facts", total_inserted)
    return total_inserted


def parse_samp_balanco(file_path: Path, format_type: str = "parquet") -> pl.DataFrame:
    """Parse and normalize ANEEL SAMP Balanco Parquet/CSV using Polars.

    Returns a normalized DataFrame with standardized fields.
    """
    logger.info("Parsing SAMP Balanco from %s", file_path)
    
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Standardize column mappings (ANEEL fields)
    rename_map = {
        "NumCPFCNPJ": "raw_cnpj",
        "NomAgente": "raw_name",
        "AnmCompetenciaBalanco": "raw_competence",
        "DscModalidadeBalanco": "balance_modality",
        "DscFluxoEnergia": "energy_flow",
        "DscCctBalanco": "balance_characteristic",
        "DscDetalheBalanco": "balance_detail",
        "VlrEnergia": "raw_value"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="SAMP Balanco",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=["raw_cnpj", "raw_name", "raw_competence", "raw_value"],
    )
    df = _ensure_optional_columns(
        df,
        ["balance_modality", "energy_flow", "balance_characteristic", "balance_detail"],
    )

    # Normalize values and types
    # Clean CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("raw_competence").cast(pl.String).alias("raw_competence_str")
    ])
    
    # reference_month from raw_competence_str (format YYYYMM -> YYYY-MM)
    df = df.with_columns(
        pl.concat_str([
            pl.col("raw_competence_str").str.slice(0, 4),
            pl.lit("-"),
            pl.col("raw_competence_str").str.slice(4, 2)
        ]).alias("reference_month")
    )
    
    # Handle CNPJ padding
    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Cast raw value
    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0))

    # Standardize units and values
    df = df.with_columns([
        pl.when(pl.col("balance_detail").str.contains("kWh"))
        .then(pl.lit("kWh"))
        .otherwise(pl.lit("MWh"))
        .alias("original_unit"),

        pl.lit("MWh").alias("normalized_unit")
    ])

    # Perform unit conversion
    df = df.with_columns(
        pl.when(pl.col("original_unit") == "kWh")
        .then(pl.col("raw_value") / 1000.0)
        .otherwise(pl.col("raw_value"))
        .alias("normalized_value")
    )

    # Create row hash based on business keys
    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("reference_month"),
                pl.col("balance_modality").fill_null(""),
                pl.col("energy_flow").fill_null(""),
                pl.col("balance_characteristic").fill_null(""),
                pl.col("balance_detail").fill_null(""),
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "reference_month",
        "balance_modality",
        "energy_flow",
        "balance_characteristic",
        "balance_detail",
        "raw_value",
        "normalized_value",
        "original_unit",
        "normalized_unit",
        "source_row_hash"
    ])


def upsert_samp_balanco_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed facts into distribution_energy_balance_facts, resolving distributor identities."""
    if df.height == 0:
        return 0

    # 1. Fetch existing CNPJ -> distributor_id mappings
    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    # 2. Identify and register new unmapped distributors dynamically
    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from balance facts: %s (%s)", name, dist_id)

    # 3. Add distributor_id to DataFrame
    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        logger.warning("%d rows in balance facts have unresolved distributor identities", unresolved_count)
        unresolved_entities = (
            df_with_dist.filter(pl.col("distributor_id").is_null())
            .select(["normalized_cnpj", "raw_name"])
            .unique()
            .to_dicts()
        )
        for entity in unresolved_entities:
            raw_name = entity.get("raw_name")
            cnpj = entity.get("normalized_cnpj")
            entity_id = _unresolved_source_entity_id("balance", raw_name, cnpj)
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'unresolved_source_entity')
                """),
                {
                    "id": entity_id,
                    "name": raw_name or f"Unresolved balance source {entity_id[-8:]}",
                    "trade": raw_name,
                    "cnpj": cnpj,
                },
            )
        df_with_dist = df_with_dist.with_columns(
            pl.when(pl.col("distributor_id").is_null())
            .then(
                pl.concat_str([
                    pl.lit("unresolved_balance_"),
                    pl.concat_str([
                        pl.col("normalized_cnpj").fill_null(""),
                        pl.lit("|"),
                        pl.col("raw_name").fill_null(""),
                    ]).map_elements(lambda value: _sha256_text(value)[:16], return_dtype=pl.String)
                ])
            )
            .otherwise(pl.col("distributor_id"))
            .alias("distributor_id")
        )

    # 4. Bulk insert into facts table
    chunk_size = 10000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_energy_balance_facts (
            fact_id, distributor_id, reference_month, balance_modality, energy_flow,
            balance_characteristic, balance_detail, raw_value, normalized_value,
            original_unit, normalized_unit, source_row_hash, snapshot_id
        )
        VALUES (
            :fact_id, :distributor_id, :reference_month, :balance_modality, :energy_flow,
            :balance_characteristic, :balance_detail, :raw_value, :normalized_value,
            :original_unit, :normalized_unit, :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, df_with_dist.height, chunk_size):
        chunk = df_with_dist.slice(i, chunk_size).to_dicts()
        payload = []
        for r in chunk:
            payload.append({
                "fact_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "reference_month": r["reference_month"],
                "balance_modality": r.get("balance_modality"),
                "energy_flow": r.get("energy_flow"),
                "balance_characteristic": r.get("balance_characteristic"),
                "balance_detail": r.get("balance_detail"),
                "raw_value": r["raw_value"],
                "normalized_value": r["normalized_value"],
                "original_unit": r["original_unit"],
                "normalized_unit": r["normalized_unit"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d facts into distribution_energy_balance_facts", total_inserted)
    return total_inserted


def parse_continuity_actuals(file_path: Path, format_type: str = "parquet") -> pl.DataFrame:
    """Parse and normalize ANEEL continuity actuals Parquet/CSV using Polars."""
    logger.info("Parsing continuity actuals from %s", file_path)
    # IdeConjUndConsumidoras sometimes contains values like '15,00' (BR decimal)
    # which Polars infers as i64 and then fails. Force it to String at read time.
    _CONTINUITY_SCHEMA: dict = {"IdeConjUndConsumidoras": pl.String}
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path, schema_overrides=_CONTINUITY_SCHEMA)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Standardize column mappings
    rename_map = {
        "NumCNPJ": "raw_cnpj",
        "SigAgente": "raw_name",
        "IdeConjUndConsumidoras": "set_id",
        "DscConjUndConsumidoras": "set_name",
        "SigIndicador": "indicator_code",
        "AnoIndice": "raw_year",
        "NumPeriodoIndice": "raw_month",
        "VlrIndiceEnviado": "raw_value"
    }
    
    df = _canonicalize_source_columns(
        df,
        dataset_name="Continuity actuals",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "set_id",
            "set_name",
            "indicator_code",
            "raw_year",
            "raw_month",
            "raw_value",
        ],
    )

    # Normalize CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("raw_year").cast(pl.String).alias("raw_year_str"),
        pl.col("raw_month").cast(pl.String).alias("raw_month_str")
    ])

    # reference_month from raw_year_str and raw_month_str (format YYYY-MM)
    df = df.with_columns(
        pl.concat_str([
            pl.col("raw_year_str"),
            pl.lit("-"),
            pl.col("raw_month_str").str.zfill(2)
        ]).alias("reference_month")
    )

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Cast value
    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("actual_value")
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0).alias("actual_value"))

    # Trim columns
    df = df.with_columns([
        pl.col("indicator_code").str.strip_chars().alias("indicator_code"),
        pl.col("set_id").cast(pl.String).alias("set_id"),
        pl.col("set_name").str.strip_chars().alias("set_name")
    ])

    # Filter to DEC, FEC, and NumCon (denominator)
    df = df.filter(pl.col("indicator_code").is_in(["DEC", "FEC", "NumCon"]))

    # Generate source row hash
    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("reference_month"),
                pl.col("set_id"),
                pl.col("indicator_code")
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "set_id",
        "set_name",
        "indicator_code",
        "reference_month",
        "actual_value",
        "source_row_hash"
    ])


def upsert_continuity_actuals_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed actuals into distribution_continuity_facts, resolving distributor identities."""
    if df.height == 0:
        return 0

    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from actuals facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_continuity_facts (
            fact_id, distributor_id, set_id, set_name, indicator_code,
            reference_month, actual_value, source_row_hash, snapshot_id
        )
        VALUES (
            :fact_id, :distributor_id, :set_id, :set_name, :indicator_code,
            :reference_month, :actual_value, :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "fact_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "set_id": r["set_id"],
                "set_name": r.get("set_name"),
                "indicator_code": r["indicator_code"],
                "reference_month": r["reference_month"],
                "actual_value": r["actual_value"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d facts into distribution_continuity_facts", total_inserted)
    return total_inserted


def parse_continuity_limits(file_path: Path, format_type: str = "csv") -> pl.DataFrame:
    """Parse and normalize ANEEL continuity limits CSV/Parquet using Polars."""
    logger.info("Parsing continuity limits from %s", file_path)
    # IdeConjUndConsumidoras sometimes contains values like '15,00' (BR decimal)
    # which Polars infers as i64 and then fails. Force it to String at read time.
    _CONTINUITY_SCHEMA: dict = {"IdeConjUndConsumidoras": pl.String}
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path, schema_overrides=_CONTINUITY_SCHEMA)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    rename_map = {
        "NumCNPJ": "raw_cnpj",
        "SigAgente": "raw_name",
        "IdeConjUndConsumidoras": "set_id",
        "DscConjUndConsumidoras": "set_name",
        "SigIndicador": "indicator_code",
        "AnoLimiteQualidade": "validity_year",
        "VlrLimite": "raw_value"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="Continuity limits",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "set_id",
            "set_name",
            "indicator_code",
            "validity_year",
            "raw_value",
        ],
    )

    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("validity_year").cast(pl.Int64).alias("validity_year")
    ])

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("limit_value")
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0).alias("limit_value"))

    df = df.with_columns([
        pl.col("indicator_code").str.strip_chars().alias("indicator_code"),
        pl.col("set_id").cast(pl.String).alias("set_id"),
        pl.col("set_name").str.strip_chars().alias("set_name")
    ])

    df = df.filter(pl.col("indicator_code").is_in(["DEC", "FEC"]))

    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("validity_year").cast(pl.String),
                pl.col("set_id"),
                pl.col("indicator_code")
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "set_id",
        "set_name",
        "indicator_code",
        "validity_year",
        "limit_value",
        "source_row_hash"
    ])


def upsert_continuity_limits_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed limits into distribution_continuity_limits, resolving distributor identities."""
    if df.height == 0:
        return 0

    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from limit facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_continuity_limits (
            limit_id, distributor_id, set_id, set_name, indicator_code,
            validity_year, limit_value, source_row_hash, snapshot_id
        )
        VALUES (
            :limit_id, :distributor_id, :set_id, :set_name, :indicator_code,
            :validity_year, :limit_value, :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "limit_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "set_id": r["set_id"],
                "set_name": r.get("set_name"),
                "indicator_code": r["indicator_code"],
                "validity_year": r["validity_year"],
                "limit_value": r["limit_value"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d limits into distribution_continuity_limits", total_inserted)
    return total_inserted


def parse_continuity_compensations(file_path: Path, format_type: str = "parquet") -> pl.DataFrame:
    """Parse and normalize ANEEL continuity compensations Parquet/CSV using Polars."""
    logger.info("Parsing continuity compensations from %s", file_path)
    _CONTINUITY_SCHEMA = {"IdeConjUndConsumidoras": pl.String}
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path, schema_overrides=_CONTINUITY_SCHEMA)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    rename_map = {
        "NumCNPJ": "raw_cnpj",
        "SigAgente": "raw_name",
        "IdeConjUndConsumidoras": "set_id",
        "DscConjUndConsumidoras": "set_name",
        "SigIndicador": "indicator_code",
        "AnoIndice": "raw_year",
        "NumPeriodoIndice": "raw_month",
        "VlrIndiceEnviado": "raw_value"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="Continuity compensations",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "set_id",
            "set_name",
            "indicator_code",
            "raw_year",
            "raw_month",
            "raw_value",
        ],
    )

    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("raw_year").cast(pl.String).alias("raw_year_str"),
        pl.col("raw_month").cast(pl.String).alias("raw_month_str")
    ])

    df = df.with_columns(
        pl.concat_str([
            pl.col("raw_year_str"),
            pl.lit("-"),
            pl.col("raw_month_str").str.zfill(2)
        ]).alias("reference_month")
    )

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("val")
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0).alias("val"))

    df = df.with_columns([
        pl.col("indicator_code").str.strip_chars().alias("indicator_code"),
        pl.col("set_id").cast(pl.String).alias("set_id"),
        pl.col("set_name").str.strip_chars().alias("set_name")
    ])

    # Aggregate by: normalized_cnpj, raw_name, set_id, set_name, reference_month
    agg_df = df.group_by(["normalized_cnpj", "raw_name", "set_id", "set_name", "reference_month"]).agg([
        pl.col("val").filter(pl.col("indicator_code").str.starts_with("QT")).sum().alias("compensation_count"),
        pl.col("val").filter(pl.col("indicator_code").str.starts_with("PG")).sum().alias("compensation_value")
    ])

    agg_df = agg_df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("reference_month"),
                pl.col("set_id")
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return agg_df.select([
        "normalized_cnpj",
        "raw_name",
        "set_id",
        "set_name",
        "reference_month",
        "compensation_count",
        "compensation_value",
        "source_row_hash"
    ])


def upsert_continuity_compensations_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed compensations into distribution_continuity_compensations, resolving distributor identities."""
    if df.height == 0:
        return 0

    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from compensation facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_continuity_compensations (
            compensation_id, distributor_id, set_id, set_name, reference_month,
            compensation_count, compensation_value, source_row_hash, snapshot_id
        )
        VALUES (
            :compensation_id, :distributor_id, :set_id, :set_name, :reference_month,
            :compensation_count, :compensation_value, :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "compensation_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "set_id": r["set_id"],
                "set_name": r.get("set_name"),
                "reference_month": r["reference_month"],
                "compensation_count": int(r["compensation_count"]) if r["compensation_count"] is not None else 0,
                "compensation_value": r["compensation_value"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d compensations into distribution_continuity_compensations", total_inserted)
    return total_inserted


def parse_tariffs(file_path: Path, format_type: str = "csv") -> pl.DataFrame:
    """Parse and normalize ANEEL homologated tariffs CSV/Parquet using Polars."""
    logger.info("Parsing tariffs from %s", file_path)
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Standardize column mappings
    rename_map = {
        "raw_cnpj": "raw_cnpj",
        "NumCNPJ": "raw_cnpj",
        "NumCNPJDistribuidora": "raw_cnpj",
        "raw_name": "raw_name",
        "NomAgenteRegulado": "raw_name",
        "SigAgente": "raw_name",
        "resolution_title": "resolution_title",
        "NumResolucao": "resolution_title",
        "DscREH": "resolution_title",
        "valid_from": "valid_from",
        "DatInicioVigencia": "valid_from",
        "valid_to": "valid_to",
        "DatFimVigencia": "valid_to",
        "tariff_base": "tariff_base",
        "DscBaseTarifaria": "tariff_base",
        "subgroup": "subgroup",
        "NomSubgrupo": "subgroup",
        "DscSubGrupo": "subgroup",
        "modality": "modality",
        "NomModalidade": "modality",
        "DscModalidadeTarifaria": "modality",
        "consumer_class": "consumer_class",
        "NomClasse": "consumer_class",
        "DscClasse": "consumer_class",
        "consumer_subclass": "consumer_subclass",
        "NomSubclasse": "consumer_subclass",
        "DscSubClasse": "consumer_subclass",
        "consumer_detail": "consumer_detail",
        "DscDetalhe": "consumer_detail",
        "tariff_period": "tariff_period",
        "NomPostoTarifario": "tariff_period",
        "accessing_agent": "accessing_agent",
        "SigAgenteAcessante": "accessing_agent",
        "unit": "unit",
        "NomUnidadeMedida": "unit",
        "DscUnidadeTerciaria": "unit",
        "tusd_raw": "tusd_raw",
        "VlrTUSD": "tusd_raw",
        "te_raw": "te_raw",
        "VlrTE": "te_raw"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="Tarifas de Aplicacao",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "resolution_title",
            "valid_from",
            "tariff_base",
            "subgroup",
            "modality",
            "consumer_class",
            "consumer_subclass",
            "tariff_period",
            "unit",
        ],
    )
    df = _ensure_optional_columns(df, ["valid_to", "consumer_detail", "tariff_period", "accessing_agent", "tusd_raw", "te_raw"])

    # Normalize CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj")
    ])

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Normalize Dates
    for col in ["valid_from", "valid_to"]:
        if col in df.columns:
            if df.schema[col] == pl.String:
                df = df.with_columns(
                    pl.when(pl.col(col).str.contains("/"))
                    .then(pl.col(col).str.strptime(pl.Date, format="%d/%m/%Y", strict=False).cast(pl.String))
                    .otherwise(pl.col(col).str.strptime(pl.Date, format="%Y-%m-%d", strict=False).cast(pl.String))
                    .alias(col)
                )

    # Cast TUSD and TE
    for col in ["tusd_raw", "te_raw"]:
        if col in df.columns:
            if df.schema[col] == pl.String:
                df = df.with_columns(
                    pl.col(col)
                    .str.replace_all(",", ".")
                    .cast(pl.Float64, strict=False)
                    .fill_null(0.0)
                    .alias(col.replace("_raw", "_value"))
                )
            else:
                df = df.with_columns(pl.col(col).cast(pl.Float64).fill_null(0.0).alias(col.replace("_raw", "_value")))
        else:
            df = df.with_columns(pl.lit(0.0).alias(col.replace("_raw", "_value")))

    # Trim text fields
    for col in ["subgroup", "modality", "consumer_class", "consumer_subclass", "consumer_detail", "tariff_period", "accessing_agent", "unit"]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.String).str.strip_chars())

    tariff_key_columns = [
        "normalized_cnpj",
        "resolution_title",
        "valid_from",
        "valid_to",
        "tariff_base",
        "subgroup",
        "modality",
        "consumer_class",
        "consumer_subclass",
        "consumer_detail",
        "tariff_period",
        "accessing_agent",
        "unit",
    ]
    df = _hash_columns(df, tariff_key_columns, "business_key_hash")
    df = _hash_columns(df, tariff_key_columns + ["tusd_value", "te_value"], "source_row_hash")

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "resolution_title",
        "valid_from",
        "valid_to",
        "tariff_base",
        "subgroup",
        "modality",
        "consumer_class",
        "consumer_subclass",
        "consumer_detail",
        "tariff_period",
        "accessing_agent",
        "unit",
        "tusd_value",
        "te_value",
        "business_key_hash",
        "source_row_hash"
    ])


def upsert_tariffs_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed tariff facts into distribution_tariff_facts, resolving distributor identities."""
    if df.height == 0:
        return 0

    if "business_key_hash" not in df.columns:
        raise DistributionSchemaError(
            "Tarifas de Aplicacao publication failed: missing business_key_hash. "
            f"Available columns: {df.columns}. Parser: {PARSER_VERSION}."
        )

    conflicts = (
        df.group_by("business_key_hash")
        .agg([
            pl.col("tusd_value").n_unique().alias("tusd_values"),
            pl.col("te_value").n_unique().alias("te_values"),
        ])
        .filter((pl.col("tusd_values") > 1) | (pl.col("te_values") > 1))
    )
    if conflicts.height:
        logger.warning(
            "Quarantining %d tariff logical keys with conflicting TE/TUSD values in snapshot %s",
            conflicts.height,
            snapshot_id,
        )
        conflict_rows = df.join(conflicts.select("business_key_hash"), on="business_key_hash", how="inner")
        conflict_query = """
            INSERT OR REPLACE INTO distribution_tariff_conflicts (
                conflict_row_id, business_key_hash, normalized_cnpj, raw_name,
                resolution_title, valid_from, valid_to, tariff_base, subgroup,
                modality, consumer_class, consumer_subclass, consumer_detail,
                tariff_period, accessing_agent, unit, tusd_value, te_value,
                source_row_hash, snapshot_id, conflict_reason
            )
            VALUES (
                :conflict_row_id, :business_key_hash, :normalized_cnpj, :raw_name,
                :resolution_title, :valid_from, :valid_to, :tariff_base, :subgroup,
                :modality, :consumer_class, :consumer_subclass, :consumer_detail,
                :tariff_period, :accessing_agent, :unit, :tusd_value, :te_value,
                :source_row_hash, :snapshot_id, :conflict_reason
            )
        """
        conn.execute(
            text(conflict_query),
            [
                {
                    **row,
                    "conflict_row_id": f"{row['business_key_hash']}_{row['source_row_hash']}_{snapshot_id}",
                    "snapshot_id": snapshot_id,
                    "conflict_reason": "same_business_key_different_tusd_or_te",
                }
                for row in conflict_rows.to_dicts()
            ],
        )
        df = df.join(conflicts.select("business_key_hash"), on="business_key_hash", how="anti")
        if df.height == 0:
            return 0

    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from tariff facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_tariff_facts (
            fact_id, distributor_id, resolution_title, valid_from, valid_to,
            tariff_base, subgroup, modality, consumer_class, consumer_subclass,
            consumer_detail, tariff_period, accessing_agent, unit, tusd_value, te_value,
            source_row_hash, snapshot_id
        )
        VALUES (
            :fact_id, :distributor_id, :resolution_title, :valid_from, :valid_to,
            :tariff_base, :subgroup, :modality, :consumer_class, :consumer_subclass,
            :consumer_detail, :tariff_period, :accessing_agent, :unit, :tusd_value, :te_value,
            :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "fact_id": f"{r['distributor_id']}_{r['business_key_hash']}",
                "distributor_id": r["distributor_id"],
                "resolution_title": r.get("resolution_title"),
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
                "tariff_base": r.get("tariff_base"),
                "subgroup": r.get("subgroup"),
                "modality": r.get("modality"),
                "consumer_class": r.get("consumer_class"),
                "consumer_subclass": r.get("consumer_subclass"),
                "consumer_detail": r.get("consumer_detail"),
                "tariff_period": r.get("tariff_period"),
                "accessing_agent": r.get("accessing_agent"),
                "unit": r["unit"],
                "tusd_value": r["tusd_value"],
                "te_value": r["te_value"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d facts into distribution_tariff_facts", total_inserted)
    return total_inserted


def parse_delinquency(file_path: Path, format_type: str = "csv") -> pl.DataFrame:
    """Parse and normalize ANEEL delinquency CSV/Parquet using Polars."""
    logger.info("Parsing delinquency from %s", file_path)
    if format_type == "parquet":
        df = pl.read_parquet(file_path)
    elif format_type == "csv":
        df = _read_distribution_csv(file_path)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Standardize column mappings
    rename_map = {
        "NumCNPJ": "raw_cnpj",
        "SigAgente": "raw_name",
        "SigIndicador": "indicator_code",
        "AnoIndice": "raw_year",
        "NumPeriodoIndice": "raw_month",
        "VlrIndiceEnviado": "raw_value"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="Inadimplencia",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "indicator_code",
            "raw_year",
            "raw_month",
            "raw_value",
        ],
    )

    # Normalize CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj"),
        pl.col("raw_year").cast(pl.String).alias("raw_year_str"),
        pl.col("raw_month").cast(pl.String).alias("raw_month_str")
    ])

    # reference_month (format YYYY-MM)
    df = df.with_columns(
        pl.concat_str([
            pl.col("raw_year_str"),
            pl.lit("-"),
            pl.col("raw_month_str").str.zfill(2)
        ]).alias("reference_month")
    )

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Cast value
    if df.schema["raw_value"] == pl.String:
        df = df.with_columns(
            pl.col("raw_value")
            .str.replace_all(",", ".")
            .cast(pl.Float64, strict=False)
            .fill_null(0.0)
            .alias("actual_value")
        )
    else:
        df = df.with_columns(pl.col("raw_value").cast(pl.Float64).fill_null(0.0).alias("actual_value"))

    df = df.with_columns(pl.col("indicator_code").str.strip_chars().alias("indicator_code"))

    # Generate source row hash
    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("reference_month"),
                pl.col("indicator_code"),
                pl.col("actual_value").cast(pl.String)
            ],
            separator="|"
        )
        .map_elements(_sha256_text, return_dtype=pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "reference_month",
        "indicator_code",
        "actual_value",
        "source_row_hash"
    ])


def upsert_delinquency_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed delinquency facts, validating indicator codes against registered dimension."""
    if df.height == 0:
        return 0

    # 1. Domain Constraint: every official source code must have explicit metadata.
    registered_codes = {
        r[0] for r in conn.execute(text("SELECT indicator_code FROM distribution_delinquency_indicators")).fetchall()
    }
    source_codes = set(df.select("indicator_code").unique().to_series().to_list())
    unknown_codes = sorted(source_codes - registered_codes)
    if unknown_codes:
        raise ValueError(
            "Blocking Ingestion: Delinquency indicator code(s) are not registered "
            f"in the database dimension: {unknown_codes}."
        )

    # 2. Resolve distributor_id
    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from delinquency facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        logger.warning("%d rows in delinquency facts have unresolved distributor identities", unresolved_count)
        unresolved_entities = (
            df_with_dist.filter(pl.col("distributor_id").is_null())
            .select(["normalized_cnpj", "raw_name"])
            .unique()
            .to_dicts()
        )
        for entity in unresolved_entities:
            raw_name = entity.get("raw_name")
            cnpj = entity.get("normalized_cnpj")
            entity_id = _unresolved_source_entity_id("delinquency", raw_name, cnpj)
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'unresolved_source_entity')
                """),
                {
                    "id": entity_id,
                    "name": raw_name or f"Unresolved delinquency source {entity_id[-8:]}",
                    "trade": raw_name,
                    "cnpj": cnpj,
                },
            )
        df_with_dist = df_with_dist.with_columns(
            pl.when(pl.col("distributor_id").is_null())
            .then(
                pl.concat_str([
                    pl.lit("unresolved_delinquency_"),
                    pl.concat_str([
                        pl.col("normalized_cnpj").fill_null(""),
                        pl.lit("|"),
                        pl.col("raw_name").fill_null(""),
                    ]).map_elements(lambda value: _sha256_text(value)[:16], return_dtype=pl.String),
                ])
            )
            .otherwise(pl.col("distributor_id"))
            .alias("distributor_id")
        )

    # 3. Bulk insert into facts table
    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0
    
    query = """
        INSERT OR REPLACE INTO distribution_delinquency_facts (
            fact_id, distributor_id, reference_month, indicator_code,
            actual_value, source_row_hash, snapshot_id
        )
        VALUES (
            :fact_id, :distributor_id, :reference_month, :indicator_code,
            :actual_value, :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        payload = []
        for r in chunk:
            payload.append({
                "fact_id": f"{r['distributor_id']}_{r['source_row_hash']}",
                "distributor_id": r["distributor_id"],
                "reference_month": r["reference_month"],
                "indicator_code": r["indicator_code"],
                "actual_value": r["actual_value"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        conn.execute(text(query), payload)
        total_inserted += len(chunk)

    logger.info("Upserted %d facts into distribution_delinquency_facts", total_inserted)
    return total_inserted


def parse_mmgd(file_path: Path, format_type: str = "parquet") -> pl.DataFrame:
    """Parse and normalize ANEEL MMGD Parquet/CSV using Polars, stripping personal data."""
    logger.info("Parsing MMGD from %s", file_path)
    mmgd_source_cols = [
        "NumCNPJDistribuidora",
        "SigAgente",
        "CodEmpreendimento",
        "NomMunicipio",
        "SigUF",
        "DscClasseConsumo",
        "DscSubGrupoTarifario",
        "SigModalidadeEmpreendimento",
        "DscModalidadeHabilitado",
        "SigTipoGeracao",
        "DscFonteGeracao",
        "DscPorte",
        "NumCoordNEmpreendimento",
        "NumCoordEEmpreendimento",
        "DthAtualizaCadastralEmpreend",
        "AnmPeriodoReferencia",
        "MdaPotenciaInstaladaKW",
        "QtdUCRecebeCredito",
    ]
    if format_type == "parquet":
        available_cols = pl.scan_parquet(file_path).collect_schema().names()
        df = pl.read_parquet(file_path, columns=[c for c in mmgd_source_cols if c in available_cols])
    elif format_type == "csv":
        df = _read_distribution_csv(file_path)
    else:
        raise ValueError(f"Unsupported format type: {format_type}")

    # Strip personal data columns immediately
    personal_cols = ["NumCPFCNPJ", "NomTitularEmpreendimento"]
    df = df.drop([c for c in personal_cols if c in df.columns])

    # Standardize column mappings
    rename_map = {
        "NumCNPJDistribuidora": "raw_cnpj",
        "SigAgente": "raw_name",
        "CodEmpreendimento": "project_id",
        "NomMunicipio": "municipality",
        "SigUF": "uf",
        "DscClasseConsumo": "consumer_class",
        "DscSubGrupoTarifario": "tariff_subgroup",
        "SigModalidadeEmpreendimento": "project_modality",
        "DscModalidadeHabilitado": "enabled_modality",
        "SigTipoGeracao": "generation_type",
        "DscFonteGeracao": "generation_source",
        "DscPorte": "size_category",
        "NumCoordNEmpreendimento": "latitude",
        "NumCoordEEmpreendimento": "longitude",
        "DthAtualizaCadastralEmpreend": "connection_date",
        "AnmPeriodoReferencia": "reference_period",
        "MdaPotenciaInstaladaKW": "installed_capacity_kw",
        "QtdUCRecebeCredito": "beneficiary_units_count"
    }

    df = _canonicalize_source_columns(
        df,
        dataset_name="MMGD projects",
        stage="raw-to-canonical",
        file_path=file_path,
        rename_map=rename_map,
        required_canonical=[
            "raw_cnpj",
            "raw_name",
            "project_id",
            "municipality",
            "uf",
            "generation_type",
            "generation_source",
            "size_category",
        ],
    )
    df = _ensure_optional_columns(
        df,
        ["consumer_class", "tariff_subgroup", "project_modality", "enabled_modality"],
    )
    df = _ensure_optional_columns(
        df,
        [
            "latitude",
            "longitude",
            "connection_date",
            "reference_period",
            "installed_capacity_kw",
            "beneficiary_units_count",
        ],
    )

    # Normalize CNPJ
    df = df.with_columns([
        pl.col("raw_cnpj").cast(pl.String).str.replace_all(r"\D", "").alias("clean_cnpj")
    ])

    df = df.with_columns(
        pl.when((pl.col("clean_cnpj").str.len_bytes() >= 12) & (pl.col("clean_cnpj").str.len_bytes() <= 14))
        .then(pl.col("clean_cnpj").str.zfill(14))
        .otherwise(pl.lit(None))
        .alias("normalized_cnpj")
    )

    # Normalize Dates
    if "connection_date" in df.columns:
        if df.schema["connection_date"] == pl.String:
            df = df.with_columns(
                pl.when(pl.col("connection_date").str.contains("/"))
                .then(pl.col("connection_date").str.strptime(pl.Date, format="%d/%m/%Y", strict=False).cast(pl.String))
                .otherwise(pl.col("connection_date").str.strptime(pl.Date, format="%Y-%m-%d", strict=False).cast(pl.String))
                .alias("connection_date")
            )
        else:
            df = df.with_columns(pl.col("connection_date").cast(pl.Date).cast(pl.String).alias("connection_date"))

    # reference_month (convert YYYYMM or YYYY-MM to YYYY-MM)
    if "reference_period" in df.columns:
        df = df.with_columns(
            pl.col("reference_period").cast(pl.String).alias("ref_str")
        )
        df = df.with_columns(
            pl.when(pl.col("ref_str").str.contains("/"))
            .then(
                pl.concat_str([
                    pl.col("ref_str").str.slice(3, 4),
                    pl.lit("-"),
                    pl.col("ref_str").str.slice(0, 2)
                ])
            )
            .when(pl.col("ref_str").str.contains("-"))
            .then(pl.col("ref_str").str.slice(0, 7))
            .otherwise(
                pl.concat_str([
                    pl.col("ref_str").str.slice(0, 4),
                    pl.lit("-"),
                    pl.col("ref_str").str.slice(4, 2)
                ])
            )
            .alias("reference_month")
        )
    else:
        df = df.with_columns(pl.lit(None).cast(pl.String).alias("reference_month"))

    # Convert coordinates and capacity
    for col in ["latitude", "longitude", "installed_capacity_kw"]:
        if col in df.columns:
            if df.schema[col] == pl.String:
                df = df.with_columns(
                    pl.col(col).str.replace_all(",", ".").cast(pl.Float64, strict=False).fill_null(0.0).alias(col)
                )
            else:
                df = df.with_columns(pl.col(col).cast(pl.Float64).fill_null(0.0).alias(col))
        else:
            df = df.with_columns(pl.lit(0.0).cast(pl.Float64).alias(col))

    # Convert beneficiary_units_count
    if "beneficiary_units_count" in df.columns:
        df = df.with_columns(pl.col("beneficiary_units_count").cast(pl.Int64).fill_null(0).alias("beneficiary_units_count"))
    else:
        df = df.with_columns(pl.lit(0).cast(pl.Int64).alias("beneficiary_units_count"))

    # Trim text fields
    for col in [
        "project_id",
        "municipality",
        "uf",
        "consumer_class",
        "tariff_subgroup",
        "project_modality",
        "enabled_modality",
        "generation_type",
        "generation_source",
        "size_category",
    ]:
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.String).str.strip_chars())

    # Generate source row hash
    df = df.with_columns(
        pl.concat_str(
            [
                pl.col("project_id").fill_null(""),
                pl.col("normalized_cnpj").fill_null(""),
                pl.col("municipality").fill_null(""),
                pl.col("uf").fill_null(""),
                pl.col("consumer_class").fill_null(""),
                pl.col("tariff_subgroup").fill_null(""),
                pl.col("project_modality").fill_null(""),
                pl.col("enabled_modality").fill_null(""),
                pl.col("generation_type").fill_null(""),
                pl.col("generation_source").fill_null(""),
                pl.col("size_category").fill_null(""),
                pl.col("latitude").cast(pl.String),
                pl.col("longitude").cast(pl.String),
                pl.col("connection_date").fill_null(""),
                pl.col("installed_capacity_kw").cast(pl.String),
                pl.col("beneficiary_units_count").cast(pl.String)
            ],
            separator="|"
        )
        .hash()
        .cast(pl.String)
        .alias("source_row_hash")
    )

    return df.select([
        "normalized_cnpj",
        "raw_name",
        "project_id",
        "municipality",
        "uf",
        "consumer_class",
        "tariff_subgroup",
        "project_modality",
        "enabled_modality",
        "generation_type",
        "generation_source",
        "size_category",
        "latitude",
        "longitude",
        "connection_date",
        "reference_month",
        "installed_capacity_kw",
        "beneficiary_units_count",
        "source_row_hash"
    ])


def upsert_mmgd_facts(conn, df: pl.DataFrame, snapshot_id: str) -> int:
    """Upsert parsed MMGD projects and snapshots, resolving distributor identities."""
    if df.height == 0:
        return 0

    # 1. Resolve distributor mapping
    dist_map = {}
    for r in conn.execute(text("SELECT distributor_id, normalized_cnpj FROM distribution_distributors")).fetchall():
        if r[1]:
            dist_map[r[1]] = r[0]
            
    for r in conn.execute(text("SELECT distributor_id, source_cnpj FROM distribution_distributor_aliases WHERE source_cnpj IS NOT NULL")).fetchall():
        dist_map[r[1]] = r[0]

    unique_agentes = df.filter(pl.col("normalized_cnpj").is_not_null()).select(["normalized_cnpj", "raw_name"]).unique(subset=["normalized_cnpj"])
    
    for row in unique_agentes.iter_rows(named=True):
        cnpj = row["normalized_cnpj"]
        if cnpj not in dist_map:
            dist_id = f"unmapped_{cnpj}"
            name = row["raw_name"] or f"Distribuidores CNPJ {cnpj}"
            sigla = f"CNPJ_{cnpj[:4]}"
            
            conn.execute(
                text("""
                    INSERT OR IGNORE INTO distribution_distributors
                        (distributor_id, canonical_name, trade_name, normalized_cnpj, status)
                    VALUES
                        (:id, :name, :trade, :cnpj, 'active')
                """),
                {"id": dist_id, "name": name, "trade": sigla, "cnpj": cnpj}
            )
            dist_map[cnpj] = dist_id
            logger.info("Dynamically registered unmapped distributor from MMGD facts: %s (%s)", name, dist_id)

    mapping_df = pl.DataFrame({
        "normalized_cnpj": list(dist_map.keys()),
        "distributor_id": list(dist_map.values())
    })
    
    df_with_dist = df.join(mapping_df, on="normalized_cnpj", how="left")
    
    unresolved_count = df_with_dist.filter(pl.col("distributor_id").is_null()).height
    if unresolved_count > 0:
        df_with_dist = df_with_dist.with_columns(
            pl.col("distributor_id").fill_null("unresolved")
        )

    records = df_with_dist.to_dicts()
    chunk_size = 5000
    total_inserted = 0

    # We do the upsert in two stages:
    # A. Upsert into distribution_mmgd_projects
    # B. Upsert into distribution_mmgd_project_snapshots

    # A. Projects
    projects_query = """
        INSERT OR REPLACE INTO distribution_mmgd_projects (
            project_id, distributor_id, municipality, uf,
            generation_type, generation_source, size_category,
            latitude, longitude, connection_date
        )
        VALUES (
            :project_id, :distributor_id, :municipality, :uf,
            :generation_type, :generation_source, :size_category,
            :latitude, :longitude, :connection_date
        )
    """

    # B. Snapshots
    snapshots_query = """
        INSERT OR REPLACE INTO distribution_mmgd_project_snapshots (
            snapshot_row_id, project_id, reference_month,
            installed_capacity_kw, beneficiary_units_count,
            source_row_hash, snapshot_id
        )
        VALUES (
            :snapshot_row_id, :project_id, :reference_month,
            :installed_capacity_kw, :beneficiary_units_count,
            :source_row_hash, :snapshot_id
        )
    """

    for i in range(0, len(records), chunk_size):
        chunk = records[i : i + chunk_size]
        
        # Deduplicate projects in the chunk
        unique_projects_chunk = {}
        for r in chunk:
            pid = r["project_id"]
            if not pid:
                continue
            unique_projects_chunk[pid] = {
                "project_id": pid,
                "distributor_id": r["distributor_id"],
                "municipality": r.get("municipality"),
                "uf": r.get("uf"),
                "generation_type": r.get("generation_type"),
                "generation_source": r.get("generation_source"),
                "size_category": r.get("size_category"),
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "connection_date": r.get("connection_date")
            }
        
        if unique_projects_chunk:
            conn.execute(text(projects_query), list(unique_projects_chunk.values()))

        # Snapshots
        snapshots_payload = []
        for r in chunk:
            if not r["project_id"] or not r["reference_month"]:
                continue
            snapshots_payload.append({
                "snapshot_row_id": f"{r['project_id']}_{r['source_row_hash']}",
                "project_id": r["project_id"],
                "reference_month": r["reference_month"],
                "installed_capacity_kw": r["installed_capacity_kw"],
                "beneficiary_units_count": r["beneficiary_units_count"],
                "source_row_hash": r["source_row_hash"],
                "snapshot_id": snapshot_id
            })
        
        if snapshots_payload:
            conn.execute(text(snapshots_query), snapshots_payload)
            total_inserted += len(snapshots_payload)

    logger.info("Upserted %d facts into distribution_mmgd_projects and snapshots", total_inserted)
    return total_inserted
