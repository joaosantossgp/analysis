from __future__ import annotations

"""GICS hub resolution for the listed company universe (`GET /sectors`, filters, directory rows).

Pipeline:

1. Persisted ``companies.gics_sector`` when it equals one of the 11 English hub labels
   (matched case-insensitively).
2. Missing or non-GICS labels return ``None``. CVM/B3/native labels are not treated as GICS.

**Coverage:** issuers without persisted GICS fields are excluded from real GICS hub cards and counted
as unclassified where the caller exposes that state. Extend coverage by filling canonical GICS columns
in ``companies``; do not infer GICS from CVM/B3/native labels.

**Scope:** :func:`resolve_gics_classification` is shared across the read layer; behavior changes here
propagate to listings, filters, and sector routing—keep rules additive and conservative.
"""

from dataclasses import dataclass

from src.companies.sector_taxonomy import sector_slugify

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
    gics_industry_group: str | None = None
    gics_industry: str | None = None
    gics_sub_industry: str | None = None


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
    """Resolve GICS access fields from persisted metadata only.

    Persisted GICS fields win when they identify one of the 11 hub sectors. Legacy
    Portuguese/CVM/B3/custom labels intentionally do not fall through to GICS.
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

    direct_sector = _clean_label(sector_name)
    if direct_sector:
        canon = _canonical_gics_sector_label(direct_sector)
        if canon is not None:
            return ResolvedGicsClassification(
                gics_sector=canon,
                gics_sector_slug=sector_slugify(canon),
                gics_industry_group=_clean_label(gics_industry_group),
                gics_industry=_clean_label(gics_industry),
                gics_sub_industry=_clean_label(gics_sub_industry),
            )

    return None


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
    """Legacy compatibility helper: resolve only explicit GICS 11 labels.

    It intentionally does not map Portuguese/CVM/B3 labels to GICS.
    """
    for raw in (sector_name, setor_analitico, setor_cvm):
        if raw is None:
            continue
        canon = _canonical_gics_sector_label(str(raw).strip())
        if canon is not None:
            return _mk(canon, canon, None, None)
    return None


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


def _mk(
    sector: str,
    group: str | None,
    industry: str | None,
    sub_industry: str | None,
) -> GicsClassification:
    return GicsClassification(
        gics_sector=sector,
        gics_sector_slug=sector_slugify(sector),
        gics_industry_group=group,
        gics_industry=industry,
        gics_sub_industry=sub_industry,
    )
