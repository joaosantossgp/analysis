from __future__ import annotations

import re
import unicodedata


def canonical_sector_name(setor_analitico: str | None, setor_cvm: str | None) -> str:
    for raw_value in (setor_analitico, setor_cvm):
        normalized = _normalize_label(raw_value)
        if normalized:
            return normalized
    return "Nao classificado"


def sector_slugify(sector_name: str | None) -> str:
    base = canonical_sector_name(sector_name, None)
    ascii_value = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug or "nao-classificado"


def canonical_sector_sql(table_alias: str | None = "c") -> str:
    prefix = f"{table_alias}." if table_alias else ""
    return f"""
COALESCE(
    NULLIF(TRIM({prefix}setor_analitico), ''),
    NULLIF(TRIM({prefix}setor_cvm), ''),
    'Nao classificado'
)
"""


def gics_sector_bucket_sql(
    company_columns: frozenset[str],
    *,
    table_alias: str | None = "c",
) -> str:
    base = canonical_sector_sql(table_alias)
    prefix = f"{table_alias}." if table_alias else ""
    if "gics_sector" in company_columns:
        return f"COALESCE(NULLIF(TRIM({prefix}gics_sector), ''), {base})"
    return base


def _normalize_label(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    collapsed = re.sub(r"\s+", " ", str(raw_value)).strip()
    return collapsed or None
