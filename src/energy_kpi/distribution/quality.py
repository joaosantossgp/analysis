"""Data quality and validation utilities for the electricity distribution domain."""
from __future__ import annotations

import re
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def normalize_cnpj(raw_cnpj: str | None) -> str | None:
    """Normalize a CNPJ to a standard 14-digit numeric string with zero-padding.

    Returns None if input is empty or invalid.
    """
    if raw_cnpj is None:
        return None
    # Strip non-alphanumeric characters
    cleaned = re.sub(r"\D", "", str(raw_cnpj)).strip()
    if not cleaned:
        return None
    # Check length limits
    if len(cleaned) < 12 or len(cleaned) > 14:
        return None
    # Zero-pad if needed, up to 14 digits
    if len(cleaned) < 14:
        cleaned = cleaned.zfill(14)
    return cleaned


def check_ownership_overlaps(conn) -> list[dict]:
    """Check for overlapping ownership periods for the same distributor.

    Returns a list of conflict details.
    """
    query = """
        SELECT
            a.distributor_id,
            a.ownership_id as id_a,
            b.ownership_id as id_b,
            a.valid_from as from_a,
            a.valid_to as to_a,
            b.valid_from as from_b,
            b.valid_to as to_b,
            a.economic_group_id as group_a,
            b.economic_group_id as group_b
        FROM distribution_ownership_history a
        JOIN distribution_ownership_history b
          ON a.distributor_id = b.distributor_id
         AND a.ownership_id < b.ownership_id
         AND a.valid_from <= b.valid_to
         AND a.valid_to >= b.valid_from
    """
    result = conn.execute(text(query)).fetchall()
    conflicts = []
    for r in result:
        conflicts.append({
            "distributor_id": r[0],
            "id_a": r[1],
            "id_b": r[2],
            "from_a": r[3],
            "to_a": r[4],
            "from_b": r[5],
            "to_b": r[6],
            "group_a": r[7],
            "group_b": r[8]
        })
    return conflicts
