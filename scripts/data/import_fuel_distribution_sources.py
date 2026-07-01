#!/usr/bin/env python3
"""Import official ANP Fuel Distribution sales sources into managed storage."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.energy_kpi.fuel_distribution import (  # noqa: E402
    FuelDistributionSourceFile,
    persist_fuel_distribution_sources_to_managed_store,
)
from src.platform.settings import build_settings  # noqa: E402


@dataclass(frozen=True)
class OfficialFuelSource:
    source_dataset_id: str
    label: str
    official_url: str
    grain: str
    value_unit: str
    frequency: str


OFFICIAL_FUEL_SOURCES: tuple[OfficialFuelSource, ...] = (
    OfficialFuelSource(
        "anp_fuel_sales_state_month",
        "Vendas de derivados petroleo e etanol",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-derivados-petroleo-e-etanol/vendas-combustiveis-m3-1990-2025.csv",
        "state-product-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_fuel_sales_segment_state_month",
        "Vendas de combustiveis por segmento",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vcs/vendas-combustiveis-segmento-m3-2012-2025.csv",
        "state-product-segment-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_glp_vessel_state_month",
        "Vendas de GLP por tipo de vasilhame",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vct/vendas-glp-tipo-vasilhame-m3-2007-2025.csv",
        "state-vessel-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_diesel_type_state_month",
        "Vendas de oleo diesel por tipo",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vct/vendas-oleo-diesel-tipo-m3-2013-2025.csv",
        "state-product-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_diesel_producer_state_month",
        "Vendas de oleo diesel por produtor",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-por-produtor/vendas-oleo-diesel-produtores-m3-2025-2026.csv",
        "state-fuel-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_biodiesel_region_month",
        "Vendas de biodiesel",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vendas-de-biodiesel/vendas-biodiesel-b100-m3.csv",
        "origin-region-destination-region-month",
        "m3",
        "monthly",
    ),
    OfficialFuelSource(
        "anp_asphalt_municipality_year",
        "Vendas anuais de asfalto por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/asfalto/vendas-anuais-de-asfalto-por-municipio.csv",
        "municipality-product-year",
        "kg",
        "annual",
    ),
    OfficialFuelSource(
        "anp_ethanol_municipality_year",
        "Vendas anuais de etanol hidratado por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/etanol-hidratado/vendas-anuais-de-etanol-hidratado-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
    OfficialFuelSource(
        "anp_gasoline_c_municipality_year",
        "Vendas anuais de gasolina C por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/gasolina-c/vendas-anuais-de-gasolina-c-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
    OfficialFuelSource(
        "anp_aviation_gasoline_municipality_year",
        "Vendas anuais de gasolina de aviacao por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/gasolina-de-aviacao/vendas-anuais-de-gasolina-de-aviacao-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
    OfficialFuelSource(
        "anp_glp_municipality_year",
        "Vendas anuais de GLP por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/glp/vendas-anuais-de-glp-por-municipio.csv",
        "municipality-product-year",
        "kg",
        "annual",
    ),
    OfficialFuelSource(
        "anp_fuel_oil_municipality_year",
        "Vendas anuais de oleo combustivel por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/oleo-combustivel/vendas-anuais-de-oleo-combustivel-por-municipio.csv",
        "municipality-product-year",
        "kg",
        "annual",
    ),
    OfficialFuelSource(
        "anp_diesel_municipality_year",
        "Vendas anuais de oleo diesel por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/oleo-diesel/vendas-anuais-de-oleo-diesel-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
    OfficialFuelSource(
        "anp_jet_fuel_municipality_year",
        "Vendas anuais de querosene de aviacao por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/querosene-de-aviacao/vendas-anuais-de-querosene-de-aviacao-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
    OfficialFuelSource(
        "anp_kerosene_municipality_year",
        "Vendas anuais de querosene iluminante por municipio",
        "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/vdpb/vaehdpm/querosene-iluminante/vendas-anuais-de-querosene-iluminante-por-municipio.csv",
        "municipality-product-year",
        "liters",
        "annual",
    ),
)


def _utc_batch_id() -> str:
    return "fuel_distribution_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _prefer_documents_data_root() -> None:
    if os.environ.get("CVM_DATA_DIR"):
        return
    documents_root = Path.home() / "Documents" / "CVMAnalytics"
    if (documents_root / "db" / "energy_kpis.db").exists():
        os.environ["CVM_DATA_DIR"] = str(documents_root)


def _download(source: OfficialFuelSource, target_dir: Path) -> Path:
    target = target_dir / Path(source.official_url).name
    request = urllib.request.Request(
        source.official_url,
        headers={"User-Agent": "Mozilla/5.0 CVMAnalyticsFuelDistributionImporter/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return target


def _source_files(download_dir: Path, sources: Iterable[OfficialFuelSource]) -> tuple[FuelDistributionSourceFile, ...]:
    resolved = []
    for source in sources:
        path = _download(source, download_dir)
        resolved.append(
            FuelDistributionSourceFile(
                source_dataset_id=source.source_dataset_id,
                label=source.label,
                official_url=source.official_url,
                path=path,
                grain=source.grain,
                value_unit=source.value_unit,
                frequency=source.frequency,
            )
        )
    return tuple(resolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import official ANP Fuel Distribution sources.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Data root. Defaults to configured CVMAnalytics data dir.")
    parser.add_argument("--database", type=Path, default=None, help="Energy KPI SQLite database. Defaults to configured path.")
    parser.add_argument("--import-batch-id", default=None, help="Stable import batch id. Defaults to a UTC timestamp.")
    parser.add_argument("--parser-version", default="fuel_distribution_importer_v1", help="Parser version recorded in lineage.")
    parser.add_argument("--list-sources", action="store_true", help="Print configured source metadata without importing.")
    args = parser.parse_args(argv)

    if args.list_sources:
        print(json.dumps([source.__dict__ for source in OFFICIAL_FUEL_SOURCES], ensure_ascii=False, indent=2))
        return 0

    _prefer_documents_data_root()
    settings = build_settings(project_root=ROOT)
    data_dir = Path(args.data_dir or settings.paths.data_dir).expanduser().resolve()
    db_path = Path(args.database or settings.paths.energy_kpi_db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    import_batch_id = str(args.import_batch_id or _utc_batch_id())

    with tempfile.TemporaryDirectory(prefix="cvm_fuel_distribution_") as tmp:
        download_dir = Path(tmp)
        source_files = _source_files(download_dir, OFFICIAL_FUEL_SOURCES)
        engine = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False})
        with engine.begin() as conn:
            result = persist_fuel_distribution_sources_to_managed_store(
                data_dir=data_dir,
                conn=conn,
                sources=source_files,
                import_batch_id=import_batch_id,
                parser_version=str(args.parser_version),
            )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
