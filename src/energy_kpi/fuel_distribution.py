"""Managed storage pilot for ANP Fuel Distribution sales data."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import polars as pl
from sqlalchemy import text

from src.platform.managed_ingestion_contract import (
    managed_store_paths,
    validate_contract,
    validate_manifest_contract,
)
from src.platform.managed_ingestion_registry import FUEL_DISTRIBUTION_INTAKE_CONTRACT

DATASET_ID = "fuel_distribution_sector_intake"
DETAIL_DIR_NAME = "fuel_sales_detail"

_MONTHS = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}


@dataclass(frozen=True)
class FuelDistributionSourceFile:
    source_dataset_id: str
    label: str
    official_url: str
    path: Path
    grain: str
    value_unit: str
    frequency: str


def ensure_fuel_distribution_managed_tables(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS managed_dataset_catalog (
            dataset_id       TEXT PRIMARY KEY,
            domain           TEXT NOT NULL,
            manifest_path    TEXT NOT NULL,
            base_path        TEXT NOT NULL,
            row_count        INTEGER NOT NULL,
            partition_count  INTEGER NOT NULL,
            contract_json    TEXT NOT NULL,
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fuel_distribution_product_year_mart (
            source_dataset_id  TEXT NOT NULL,
            product            TEXT NOT NULL,
            year               INTEGER NOT NULL,
            unit               TEXT NOT NULL,
            total_value        REAL NOT NULL,
            source_row_count   INTEGER NOT NULL,
            updated_at         TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (source_dataset_id, product, year, unit)
        )
    """))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.lower()).strip("_")


def _header_key(value: str) -> str:
    return (
        str(value)
        .strip()
        .lstrip("\ufeff")
        .upper()
        .replace("Ê", "E")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ã", "A")
        .replace("Ç", "C")
    )


def _clean_text(value: Any) -> str | None:
    text_value = str(value or "").strip()
    return text_value or None


def _parse_decimal(value: Any) -> float | None:
    raw = str(value or "").strip().strip('"')
    if not raw:
        return None
    normalized = raw.replace(".", "").replace(",", ".")
    return float(normalized)


def _month_number(value: Any) -> int | None:
    raw = str(value or "").strip().upper()
    if raw in _MONTHS:
        return _MONTHS[raw]
    if raw.isdigit():
        month = int(raw)
        return month if 1 <= month <= 12 else None
    return None


def _read_source_rows(source: FuelDistributionSourceFile, *, content_hash: str, import_batch_id: str, parser_version: str) -> list[dict[str, Any]]:
    raw_text = Path(source.path).read_text(encoding="utf-8-sig")
    first_line = raw_text.splitlines()[0] if raw_text.splitlines() else ""
    delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
    reader = csv.DictReader(raw_text.splitlines(), delimiter=delimiter)
    output: list[dict[str, Any]] = []

    for row_number, raw_row in enumerate(reader, start=1):
        row = {_header_key(key): value for key, value in raw_row.items() if key is not None}
        year: int | None = None
        month: int | None = None
        if row.get("ANO"):
            year = int(str(row["ANO"]).strip())
            month = _month_number(row.get("MES"))
        elif row.get("MES/ANO"):
            month_raw, year_raw = str(row["MES/ANO"]).split("/", maxsplit=1)
            month = int(month_raw)
            year = int(year_raw)
        if year is None:
            continue

        base = {
            "source_dataset_id": source.source_dataset_id,
            "source_name": source.label,
            "source_url_or_path": source.official_url,
            "download_timestamp": _utc_now(),
            "import_batch_id": import_batch_id,
            "parser_version": parser_version,
            "content_hash": content_hash,
            "source_file_name": Path(source.path).name,
            "source_row_number": row_number,
            "year": year,
            "month": month,
            "reference_period": f"{year:04d}-{month:02d}" if month else f"{year:04d}",
            "frequency": source.frequency,
            "region": _clean_text(row.get("GRANDE REGIAO") or row.get("REGIAO") or row.get("REGIAO ORIGEM")),
            "state": _clean_text(row.get("UNIDADE DA FEDERACAO") or row.get("UF") or row.get("ESTADO")),
            "municipality_code": _clean_text(row.get("CODIGO IBGE")),
            "municipality": _clean_text(row.get("MUNICIPIO")),
            "segment": _clean_text(row.get("SEGMENTO")),
            "origin_region": _clean_text(row.get("REGIAO ORIGEM")),
            "destination_region": _clean_text(row.get("REGIAO DESTINO")),
            "grain": source.grain,
            "unit": source.value_unit,
        }

        value_fields: list[tuple[str | None, float | None]]
        if "P13" in row or "OUTROS" in row:
            value_fields = [("P13", _parse_decimal(row.get("P13"))), ("OUTROS", _parse_decimal(row.get("OUTROS")))]
            product = _clean_text(row.get("PRODUTO")) or "GLP"
        else:
            value_key = "VENDAS DE BIODIESEL" if "VENDAS DE BIODIESEL" in row else "VENDAS"
            value_fields = [(_clean_text(row.get("VASILHAME")), _parse_decimal(row.get(value_key)))]
            product = _clean_text(row.get("PRODUTO") or row.get("COMBUSTIVEL")) or "BIODIESEL B100"

        for vessel, value in value_fields:
            if value is None:
                continue
            fact = {
                **base,
                "product": product,
                "vessel": vessel,
                "value": value,
            }
            hash_payload = json.dumps(fact, sort_keys=True, ensure_ascii=False, default=str)
            fact["source_row_hash"] = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()
            output.append(fact)
    return output


def _copy_raw_snapshot(source: FuelDistributionSourceFile, *, paths, import_batch_id: str, content_hash: str) -> dict[str, Any]:
    raw_dir = paths.raw_dir / import_batch_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / Path(source.path).name
    shutil.copy2(source.path, target)
    return {
        "source_dataset_id": source.source_dataset_id,
        "label": source.label,
        "official_url": source.official_url,
        "path": str(target),
        "content_hash": content_hash,
        "bytes": target.stat().st_size,
    }


def _manifest_payload(
    *,
    base_dir: Path,
    import_batch_id: str,
    row_count: int,
    raw_snapshots: list[dict[str, Any]],
    partitions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "generated_at": _utc_now(),
        "contract": FUEL_DISTRIBUTION_INTAKE_CONTRACT.to_manifest_contract(),
        "storage": {
            "base_dir": str(base_dir),
            "format": "parquet",
            "partitioning": ["source_dataset_id", "year"],
        },
        "selection": {
            "import_batch_id": import_batch_id,
            "source_datasets": sorted({snapshot["source_dataset_id"] for snapshot in raw_snapshots}),
            "full_snapshot": True,
        },
        "validation": {
            "ok": True,
            "row_count": row_count,
        },
        "raw_snapshots": raw_snapshots,
        "partitions": partitions,
    }


def persist_fuel_distribution_sources_to_managed_store(
    *,
    data_dir: Path,
    conn,
    sources: Iterable[FuelDistributionSourceFile],
    import_batch_id: str,
    parser_version: str,
) -> dict[str, Any]:
    """Persist ANP fuel sales sources to raw snapshots, Parquet detail, and SQLite marts."""
    validate_contract(FUEL_DISTRIBUTION_INTAKE_CONTRACT)
    ensure_fuel_distribution_managed_tables(conn)

    paths = managed_store_paths(data_dir, domain=FUEL_DISTRIBUTION_INTAKE_CONTRACT.domain, dataset_id=DATASET_ID)
    rows: list[dict[str, Any]] = []
    raw_snapshots: list[dict[str, Any]] = []

    for source in sources:
        raw_bytes = Path(source.path).read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        raw_snapshots.append(
            _copy_raw_snapshot(source, paths=paths, import_batch_id=import_batch_id, content_hash=content_hash)
        )
        rows.extend(
            _read_source_rows(
                source,
                content_hash=content_hash,
                import_batch_id=import_batch_id,
                parser_version=parser_version,
            )
        )

    if not rows:
        return {"row_count": 0, "partitions": [], "raw_snapshots": raw_snapshots}

    frame = pl.DataFrame(rows, infer_schema_length=None).sort(
        ["source_dataset_id", "year", "reference_period", "product", "state", "municipality"]
    )
    detail_root = paths.cold_dir / DETAIL_DIR_NAME
    detail_root.mkdir(parents=True, exist_ok=True)

    partitions: list[dict[str, Any]] = []
    for partition_key in frame.select(["source_dataset_id", "year"]).unique().sort(["source_dataset_id", "year"]).to_dicts():
        source_dataset_id = str(partition_key["source_dataset_id"])
        year = int(partition_key["year"])
        part_frame = frame.filter((pl.col("source_dataset_id") == source_dataset_id) & (pl.col("year") == year))
        partition_dir = detail_root / f"source_dataset_id={_slug(source_dataset_id)}" / f"year={year}"
        if partition_dir.exists():
            shutil.rmtree(partition_dir)
        partition_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = partition_dir / f"part-{import_batch_id}.parquet"
        part_frame.write_parquet(parquet_path, compression="zstd")
        partitions.append(
            {
                "source_dataset_id": source_dataset_id,
                "year": year,
                "row_count": part_frame.height,
                "path": str(parquet_path),
                "bytes": parquet_path.stat().st_size,
            }
        )

    source_ids = sorted({str(row["source_dataset_id"]) for row in rows})
    for source_id in source_ids:
        conn.execute(
            text("DELETE FROM fuel_distribution_product_year_mart WHERE source_dataset_id = :source_dataset_id"),
            {"source_dataset_id": source_id},
        )
    mart_frame = (
        frame.group_by(["source_dataset_id", "product", "year", "unit"])
        .agg([
            pl.col("value").sum().alias("total_value"),
            pl.len().alias("source_row_count"),
        ])
        .sort(["product", "year", "source_dataset_id", "unit"])
    )
    conn.execute(
        text("""
            INSERT INTO fuel_distribution_product_year_mart (
                source_dataset_id, product, year, unit, total_value, source_row_count, updated_at
            )
            VALUES (
                :source_dataset_id, :product, :year, :unit, :total_value, :source_row_count, datetime('now')
            )
        """),
        [
            {
                "source_dataset_id": str(row["source_dataset_id"]),
                "product": str(row["product"]),
                "year": int(row["year"]),
                "unit": str(row["unit"]),
                "total_value": float(row["total_value"]),
                "source_row_count": int(row["source_row_count"]),
            }
            for row in mart_frame.to_dicts()
        ],
    )

    manifest = _manifest_payload(
        base_dir=paths.base_dir,
        import_batch_id=import_batch_id,
        row_count=frame.height,
        raw_snapshots=raw_snapshots,
        partitions=partitions,
    )
    validate_manifest_contract(manifest, FUEL_DISTRIBUTION_INTAKE_CONTRACT)
    paths.base_dir.mkdir(parents=True, exist_ok=True)
    paths.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    conn.execute(
        text("""
            INSERT INTO managed_dataset_catalog (
                dataset_id, domain, manifest_path, base_path, row_count,
                partition_count, contract_json, updated_at
            )
            VALUES (
                :dataset_id, :domain, :manifest_path, :base_path, :row_count,
                :partition_count, :contract_json, datetime('now')
            )
            ON CONFLICT(dataset_id) DO UPDATE SET
                domain = excluded.domain,
                manifest_path = excluded.manifest_path,
                base_path = excluded.base_path,
                row_count = excluded.row_count,
                partition_count = excluded.partition_count,
                contract_json = excluded.contract_json,
                updated_at = datetime('now')
        """),
        {
            "dataset_id": DATASET_ID,
            "domain": FUEL_DISTRIBUTION_INTAKE_CONTRACT.domain,
            "manifest_path": str(paths.manifest_path),
            "base_path": str(paths.base_dir),
            "row_count": int(frame.height),
            "partition_count": len(partitions),
            "contract_json": json.dumps(FUEL_DISTRIBUTION_INTAKE_CONTRACT.to_manifest_contract(), sort_keys=True),
        },
    )
    return {
        "base_dir": str(paths.base_dir),
        "manifest_path": str(paths.manifest_path),
        "row_count": int(frame.height),
        "raw_snapshots": raw_snapshots,
        "partitions": partitions,
    }


def _read_valid_manifest(data_dir: Path) -> dict[str, Any]:
    paths = managed_store_paths(data_dir, domain=FUEL_DISTRIBUTION_INTAKE_CONTRACT.domain, dataset_id=DATASET_ID)
    if not paths.manifest_path.exists():
        raise FileNotFoundError(f"Fuel Distribution managed manifest not found: {paths.manifest_path}")
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    validate_manifest_contract(manifest, FUEL_DISTRIBUTION_INTAKE_CONTRACT)
    if manifest.get("validation", {}).get("ok") is not True:
        raise ValueError("Fuel Distribution managed manifest validation is not ok")
    return manifest


def read_fuel_distribution_detail(
    *,
    data_dir: Path,
    source_dataset_id: str | None,
    product: str | None,
    year: int | None,
    region_or_state: str | None = None,
    limit: int | None = 500,
    offset: int | None = 0,
) -> dict[str, Any]:
    """Read bounded Fuel Distribution detail from managed Parquet partitions."""
    source_id = str(source_dataset_id or "").strip()
    product_value = str(product or "").strip()
    if not source_id or not product_value or year is None:
        raise ValueError("Fuel Distribution detail reads require source_dataset_id, product, and year")
    bounded_limit = max(1, min(int(limit or 500), 5_000))
    bounded_offset = max(0, int(offset or 0))
    manifest = _read_valid_manifest(Path(data_dir))
    partitions = [
        partition
        for partition in manifest.get("partitions", [])
        if isinstance(partition, dict)
        and str(partition.get("source_dataset_id")) == source_id
        and int(partition.get("year") or 0) == int(year)
        and partition.get("path")
        and Path(str(partition.get("path"))).exists()
    ]
    if not partitions:
        existing_paths: list[str] = []
    else:
        existing_paths = [str(partition["path"]) for partition in partitions]

    if not existing_paths:
        return {
            "source": "managed_parquet",
            "dataset_id": DATASET_ID,
            "source_dataset_id": source_id,
            "product": product_value,
            "year": int(year),
            "rows": [],
            "count": 0,
            "total_matching_rows": 0,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "truncated": False,
        }

    scan = pl.scan_parquet(existing_paths).filter(pl.col("product") == product_value)
    if region_or_state:
        target = str(region_or_state).strip()
        scan = scan.filter((pl.col("state") == target) | (pl.col("region") == target))
    total_matching = int(scan.select(pl.len()).collect().item())
    frame = scan.sort(["state", "municipality", "reference_period"]).slice(bounded_offset, bounded_limit).collect()
    rows = frame.to_dicts()
    return {
        "source": "managed_parquet",
        "dataset_id": DATASET_ID,
        "source_dataset_id": source_id,
        "product": product_value,
        "year": int(year),
        "rows": rows,
        "count": len(rows),
        "total_matching_rows": total_matching,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "truncated": bounded_offset + len(rows) < total_matching,
    }
