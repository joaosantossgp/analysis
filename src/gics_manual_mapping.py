from __future__ import annotations

from dataclasses import dataclass

from src.sector_taxonomy import sector_slugify

GICS_11_SECTORS: tuple[str, ...] = (
    "Energy",
    "Materials",
    "Industrials",
    "Consumer Discretionary",
    "Consumer Staples",
    "Health Care",
    "Financials",
    "Information Technology",
    "Communication Services",
    "Utilities",
    "Real Estate",
)


@dataclass(frozen=True)
class GicsClassification:
    gics_sector: str
    gics_sector_slug: str
    gics_industry_group: str
    gics_industry: str
    gics_sub_industry: str


def build_gics_classification(
    *,
    sector_name: str | None,
    setor_analitico: str | None,
    setor_cvm: str | None,
) -> GicsClassification | None:
    # Persisted English GICS labels (and API-normalized names) must resolve directly.
    for raw in (sector_name, setor_analitico, setor_cvm):
        if raw is None:
            continue
        label = str(raw).strip()
        if label in GICS_11_SECTORS:
            return _mk(label, label, label, label)

    haystack = " ".join(
        str(part or "").strip().lower()
        for part in (sector_name, setor_analitico, setor_cvm)
    ).strip()
    if not haystack:
        return None

    # Priority rules tuned for Brazilian issuer labels.
    if _has_any(haystack, ("utilit", "saneamento", "energia eletrica", "eletric", "water", "gas distribu")):
        return _mk("Utilities", "Utilities", "Electric Utilities", "Electric Utilities")
    if _has_any(haystack, ("energia", "petro", "oil", "gas", "combust")):
        return _mk("Energy", "Energy", "Oil, Gas & Consumable Fuels", "Integrated Oil & Gas")
    if _has_any(haystack, ("material", "materiais", "basicos", "miner", "sider", "aco", "quimic", "papel", "celulose")):
        return _mk("Materials", "Materials", "Metals & Mining", "Diversified Metals & Mining")
    if _has_any(haystack, ("industrial", "logist", "transp", "infra", "aero", "rodov", "maquina")):
        return _mk("Industrials", "Industrials", "Industrial Conglomerates", "Industrial Conglomerates")
    if _has_any(haystack, ("varejo", "retail", "consumo discricionario", "ecommerce", "autos", "shopping")):
        return _mk("Consumer Discretionary", "Consumer Discretionary", "Broadline Retail", "Broadline Retail")
    if _has_any(haystack, ("alimento", "bebida", "food", "staples", "farmacia varejo")):
        return _mk("Consumer Staples", "Consumer Staples", "Consumer Staples Distribution & Retail", "Consumer Staples Merchandise Retail")
    if _has_any(haystack, ("saude", "health", "hospital", "farma", "medic")):
        return _mk("Health Care", "Health Care", "Health Care Providers & Services", "Health Care Services")
    if _has_any(haystack, ("banco", "finance", "segur", "credito", "holding financeira")):
        return _mk("Financials", "Financials", "Banks", "Diversified Banks")
    if _has_any(haystack, ("tecnologia", "software", "tech", "dados", "telecom equip")):
        return _mk("Information Technology", "Information Technology", "Software & Services", "Application Software")
    if _has_any(haystack, ("comunic", "media", "telecom", "internet", "conteudo")):
        return _mk("Communication Services", "Communication Services", "Telecommunication Services", "Integrated Telecommunication Services")
    if _has_any(haystack, ("imobili", "real estate", "propriedade", "laje corporativa")):
        return _mk("Real Estate", "Real Estate", "Real Estate Management & Development", "Real Estate Development")
    return None


def _has_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def _mk(sector: str, group: str, industry: str, sub_industry: str) -> GicsClassification:
    return GicsClassification(
        gics_sector=sector,
        gics_sector_slug=sector_slugify(sector),
        gics_industry_group=group,
        gics_industry=industry,
        gics_sub_industry=sub_industry,
    )
