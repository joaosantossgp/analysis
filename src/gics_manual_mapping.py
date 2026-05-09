from __future__ import annotations

"""GICS hub resolution for the listed company universe (`GET /sectors`, filters, directory rows).

Pipeline:

1. Persisted ``companies.gics_sector`` when it equals one of the 11 English hub labels
   (matched case-insensitively).
2. Otherwise :func:`build_gics_classification` maps Portuguese/CVM-style strings via keyword rules.

**Coverage:** strings that match no rule produce no hub; those issuers are excluded from sector hub
cards (expected empty hub only when zero companies resolve to a GICS hub). Extend coverage by adding
rules to :func:`build_gics_classification` or by filling canonical GICS columns in ``companies``.

**Scope:** :func:`resolve_gics_classification` is shared across the read layer; behavior changes here
propagate to listings, filters, and sector routing—keep rules additive and conservative.
"""

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


@dataclass(frozen=True)
class ResolvedGicsClassification:
    gics_sector: str
    gics_sector_slug: str
    gics_industry_group: str | None = None
    gics_industry: str | None = None
    gics_sub_industry: str | None = None


def _canonical_gics_sector_label(label: str) -> str | None:
    """Return official GICS sector casing when `label` matches one of the 11 hubs."""
    label_cf = label.casefold()
    for official in GICS_11_SECTORS:
        if official.casefold() == label_cf:
            return official
    return None


def resolve_gics_classification(
    *,
    sector_name: str | None = None,
    setor_analitico: str | None = None,
    setor_cvm: str | None = None,
    gics_sector: str | None = None,
    gics_sector_slug: str | None = None,
    gics_industry_group: str | None = None,
    gics_industry: str | None = None,
    gics_sub_industry: str | None = None,
) -> ResolvedGicsClassification | None:
    """Resolve GICS access fields from persisted metadata or legacy sector labels.

    Persisted GICS fields win when they identify one of the 11 hub sectors (canonical
    English labels, matched case-insensitively). Legacy Portuguese or partial persisted
    labels fall through to manual mapping together with CVM/analytic sectors so the hub
    and directory stay aligned with the company universe.

    Missing hierarchy fields stay null instead of being invented when mapping cannot
    derive them; manual mapping fills known defaults where applicable.
    """
    persisted_sector = _clean_label(gics_sector)
    if persisted_sector:
        canon = _canonical_gics_sector_label(persisted_sector)
        if canon is not None:
            return ResolvedGicsClassification(
                gics_sector=canon,
                gics_sector_slug=_clean_label(gics_sector_slug) or sector_slugify(canon),
                gics_industry_group=_clean_label(gics_industry_group),
                gics_industry=_clean_label(gics_industry),
                gics_sub_industry=_clean_label(gics_sub_industry),
            )

    mapped = build_gics_classification(
        sector_name=sector_name or persisted_sector,
        setor_analitico=setor_analitico or persisted_sector,
        setor_cvm=setor_cvm or persisted_sector,
    )
    if mapped is None:
        return None
    return ResolvedGicsClassification(
        gics_sector=mapped.gics_sector,
        gics_sector_slug=mapped.gics_sector_slug,
        gics_industry_group=_clean_label(gics_industry_group) or mapped.gics_industry_group,
        gics_industry=_clean_label(gics_industry) or mapped.gics_industry,
        gics_sub_industry=_clean_label(gics_sub_industry) or mapped.gics_sub_industry,
    )


def resolve_gics_sector_name(
    *,
    sector_name: str | None = None,
    setor_analitico: str | None = None,
    setor_cvm: str | None = None,
    gics_sector: str | None = None,
) -> str | None:
    resolved = resolve_gics_classification(
        sector_name=sector_name,
        setor_analitico=setor_analitico,
        setor_cvm=setor_cvm,
        gics_sector=gics_sector,
    )
    if resolved and resolved.gics_sector in GICS_11_SECTORS:
        return resolved.gics_sector
    return None


def gics_sector_sort_key(sector_name: str) -> tuple[int, int | str]:
    if sector_name in GICS_11_SECTORS:
        return (0, GICS_11_SECTORS.index(sector_name))
    return (1, sector_name)


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


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text or None


def _mk(sector: str, group: str, industry: str, sub_industry: str) -> GicsClassification:
    return GicsClassification(
        gics_sector=sector,
        gics_sector_slug=sector_slugify(sector),
        gics_industry_group=group,
        gics_industry=industry,
        gics_sub_industry=sub_industry,
    )
