"""Canonical company classification: GICS sub-industry curated by CVMAnalytics.

One classification per company, resolved as: local user edit -> curated (shipped dataset) -> pending.
The curated dataset is loaded on startup into ``company_classification_curated`` and
materialized into the ``companies.gics_*`` columns that every read path already uses,
so all screens show the same value. Classifications are curated by CVMAnalytics and are
never presented as official MSCI/S&P assignments (see docs/reference/gics-import.md).
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoInspectionAvailable

from src.companies.sector_taxonomy import sector_slugify

DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"
STRUCTURE_PATH = DATA_ROOT / "reference" / "gics_structure.csv"
CURATED_PATH = DATA_ROOT / "curation" / "gics_curated.csv"

ORIGIN_USER = "user"
ORIGIN_CURATED = "curated"
ORIGIN_UNCLASSIFIED = "unclassified"
ORIGIN_PENDING = "pending"
CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
CURATED_FIELDS = (
    "sub_industry_code", "unclassified_reason", "basis", "confidence", "rationale",
    "evidence_url", "review_status", "reviewer", "review_date", "proposed_by", "gics_version",
)


class CuratedClassificationError(ValueError):
    """The curated dataset is invalid; nothing was loaded."""


@dataclass(frozen=True)
class GicsPath:
    sector_code: str
    sector: str
    industry_group_code: str
    industry_group: str
    industry_code: str
    industry: str
    sub_industry_code: str
    sub_industry: str
    gics_version: str

    def company_columns(self) -> dict[str, str]:
        return {
            "gics_sector": self.sector,
            "gics_sector_slug": sector_slugify(self.sector),
            "gics_industry_group": self.industry_group,
            "gics_industry": self.industry,
            "gics_sub_industry": self.sub_industry,
            "gics_sub_industry_code": self.sub_industry_code,
        }


@lru_cache(maxsize=4)
def load_gics_structure(path: Path = STRUCTURE_PATH) -> dict[str, GicsPath]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return {row["sub_industry_code"]: GicsPath(**row) for row in csv.DictReader(handle)}


def read_curated_dataset(path: Path, structure: dict[str, GicsPath]) -> list[dict[str, Any]]:
    """Parse and validate the curated CSV; raise listing every invalid row."""
    rows, errors, seen = [], [], set()
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for line, raw in enumerate(csv.DictReader(handle), start=2):
            try:
                cd_cvm = int(str(raw.get("cd_cvm") or "").strip())
            except ValueError:
                errors.append(f"line {line}: invalid cd_cvm {raw.get('cd_cvm')!r}")
                continue
            code = str(raw.get("sub_industry_code") or "").strip()
            reason = str(raw.get("unclassified_reason") or "").strip()
            if cd_cvm in seen:
                errors.append(f"line {line}: duplicate cd_cvm {cd_cvm}")
            elif code and code not in structure:
                errors.append(f"line {line}: unknown GICS sub-industry {code!r} for cd_cvm {cd_cvm}")
            elif not code and not reason:
                errors.append(f"line {line}: cd_cvm {cd_cvm} has no sub-industry and no unclassified reason")
            elif raw.get("confidence") not in CONFIDENCE_LEVELS:
                errors.append(f"line {line}: invalid confidence {raw.get('confidence')!r} for cd_cvm {cd_cvm}")
            seen.add(cd_cvm)
            rows.append({"cd_cvm": cd_cvm, **{f: str(raw.get(f) or "").strip() or None for f in CURATED_FIELDS}})
    if errors:
        raise CuratedClassificationError(f"{len(errors)} invalid curated classification rows: " + "; ".join(errors[:10]))
    return rows


def _ensure_curated_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_classification_curated (
            cd_cvm              INTEGER PRIMARY KEY,
            sub_industry_code   TEXT,
            unclassified_reason TEXT,
            basis               TEXT,
            confidence          TEXT,
            rationale           TEXT,
            evidence_url        TEXT,
            review_status       TEXT,
            reviewer            TEXT,
            review_date         TEXT,
            proposed_by         TEXT,
            gics_version        TEXT,
            dataset_sha256      TEXT NOT NULL,
            loaded_at           TEXT NOT NULL
        )
    """))


_EMPTY_COLUMNS = dict.fromkeys(
    ("gics_sector", "gics_sector_slug", "gics_industry_group", "gics_industry", "gics_sub_industry", "gics_sub_industry_code")
)


def _columns_for(
    row: dict[str, Any] | None,
    structure: dict[str, GicsPath],
    user_code: str | None = None,
) -> dict[str, Any]:
    if user_code and user_code in structure:
        return {**structure[user_code].company_columns(), "classification_origin": ORIGIN_USER}
    if row is None:
        return {**_EMPTY_COLUMNS, "classification_origin": ORIGIN_PENDING}
    code = row.get("sub_industry_code")
    if not code:
        return {**_EMPTY_COLUMNS, "classification_origin": ORIGIN_UNCLASSIFIED}
    return {**structure[code].company_columns(), "classification_origin": ORIGIN_CURATED}


def _ensure_user_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_classification_user (
            cd_cvm               INTEGER PRIMARY KEY,
            sub_industry_code    TEXT NOT NULL,
            curated_code_at_edit TEXT,
            edited_at            TEXT NOT NULL
        )
    """))


def _user_codes(conn) -> dict[int, dict[str, Any]]:
    if not inspect(conn).has_table("company_classification_user"):
        return {}
    rows = conn.execute(text("SELECT * FROM company_classification_user")).mappings().all()
    return {int(r["cd_cvm"]): dict(r) for r in rows}


_UPDATE_COMPANY = text("""
    UPDATE companies SET
        gics_sector = :gics_sector, gics_sector_slug = :gics_sector_slug,
        gics_industry_group = :gics_industry_group, gics_industry = :gics_industry,
        gics_sub_industry = :gics_sub_industry, gics_sub_industry_code = :gics_sub_industry_code,
        classification_origin = :classification_origin
    WHERE cd_cvm = :cd_cvm
""")


def sync_curated_classification(
    engine: Engine,
    curated_path: Path = CURATED_PATH,
    structure_path: Path = STRUCTURE_PATH,
) -> dict[str, int]:
    """Replace the curated layer from the shipped dataset and materialize it into companies.

    Validation happens before any write, so an invalid dataset leaves the previous
    classification untouched. Companies absent from the dataset become pending.
    Skips all work when the same dataset and structure are already loaded and every
    company row is materialized (companies written later materialize on insert).
    """
    # The structure is part of the digest: it alone can change what gets materialized.
    digest = hashlib.sha256(Path(curated_path).read_bytes() + Path(structure_path).read_bytes()).hexdigest()
    with engine.connect() as conn:
        if _already_synced(conn, digest):
            return {"skipped_unchanged": 1}
    structure = load_gics_structure(Path(structure_path))
    rows = read_curated_dataset(Path(curated_path), structure)
    loaded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    by_cd = {row["cd_cvm"]: row for row in rows}
    with engine.begin() as conn:
        _ensure_curated_table(conn)
        _ensure_user_table(conn)
        existing = {c["name"].lower() for c in inspect(conn).get_columns("companies")}
        for column in ("gics_sub_industry_code", "classification_origin"):
            if column not in existing:
                conn.execute(text(f"ALTER TABLE companies ADD COLUMN {column} TEXT"))
        conn.execute(text("DELETE FROM company_classification_curated"))
        if rows:
            columns = ("cd_cvm", *CURATED_FIELDS, "dataset_sha256", "loaded_at")
            conn.execute(
                text(f"INSERT INTO company_classification_curated ({', '.join(columns)}) "
                     f"VALUES ({', '.join(':' + c for c in columns)})"),
                [{**row, "dataset_sha256": digest, "loaded_at": loaded_at} for row in rows],
            )
        users = _user_codes(conn)
        company_ids = [int(r[0]) for r in conn.execute(text("SELECT cd_cvm FROM companies")).fetchall()]
        if company_ids:
            conn.execute(_UPDATE_COMPANY, [
                {"cd_cvm": cd, **_columns_for(by_cd.get(cd), structure, users.get(cd, {}).get("sub_industry_code"))}
                for cd in company_ids
            ])
    return {
        "curated_rows": len(rows),
        "companies": len(company_ids),
        "curated_companies": sum(1 for cd in company_ids if cd in by_cd and by_cd[cd]["sub_industry_code"]),
    }


def _already_synced(conn, digest: str) -> bool:
    if not has_curated_layer(conn):
        return False
    loaded = {r[0] for r in conn.execute(text("SELECT DISTINCT dataset_sha256 FROM company_classification_curated"))}
    if loaded != {digest}:
        return False
    unmaterialized = conn.execute(text("SELECT 1 FROM companies WHERE classification_origin IS NULL LIMIT 1"))
    return unmaterialized.first() is None


def has_curated_layer(conn) -> bool:
    try:
        inspector = inspect(conn)
    except NoInspectionAvailable:  # non-SQLAlchemy test doubles carry no schema
        return False
    return inspector.has_table("company_classification_curated")


def _curated_row(conn, cd_cvm: int) -> dict[str, Any] | None:
    if not has_curated_layer(conn):
        return None
    row = conn.execute(
        text("SELECT * FROM company_classification_curated WHERE cd_cvm = :cd"), {"cd": int(cd_cvm)}
    ).mappings().first()
    return dict(row) if row else None


def _user_row(conn, cd_cvm: int) -> dict[str, Any] | None:
    if not inspect(conn).has_table("company_classification_user"):
        return None
    row = conn.execute(
        text("SELECT * FROM company_classification_user WHERE cd_cvm = :cd"), {"cd": int(cd_cvm)}
    ).mappings().first()
    return dict(row) if row else None


def canonical_company_columns(conn, cd_cvm: int) -> dict[str, Any]:
    """Materialized classification columns for one company (used when a company row is written)."""
    row = _curated_row(conn, cd_cvm)
    user = _user_row(conn, cd_cvm)
    structure = load_gics_structure()
    if row and row.get("sub_industry_code") not in (None, "") and row["sub_industry_code"] not in structure:
        row = None  # shipped structure changed under an old curated table; treat as pending until next sync
    return _columns_for(row, structure, user["sub_industry_code"] if user else None)


def curated_company_columns(engine: Engine) -> dict[int, dict[str, Any]] | None:
    """Materialized columns for every curated company; None before the curated layer loads.

    Companies missing from the result are pending.
    """
    with engine.connect() as conn:
        if not has_curated_layer(conn):
            return None
        rows = conn.execute(text("SELECT cd_cvm, sub_industry_code FROM company_classification_curated")).fetchall()
        users = _user_codes(conn)
    structure = load_gics_structure()
    result = {
        int(cd): _columns_for({"sub_industry_code": code}, structure)
        for cd, code in rows
        if not code or code in structure
    }
    for cd, user in users.items():
        result[cd] = _columns_for(None, structure, user["sub_industry_code"])
    return result


def materialize_company(conn, cd_cvm: int) -> None:
    """Apply the canonical classification to one company row once the curated layer exists."""
    if has_curated_layer(conn):
        conn.execute(_UPDATE_COMPANY, {"cd_cvm": int(cd_cvm), **canonical_company_columns(conn, cd_cvm)})


def company_classification(conn, cd_cvm: int) -> dict[str, Any]:
    """Canonical classification with origin and curation evidence, for company reads."""
    row = _curated_row(conn, cd_cvm)
    user = _user_row(conn, cd_cvm)
    columns = canonical_company_columns(conn, cd_cvm)
    result: dict[str, Any] = {**columns, "origin": columns["classification_origin"], "official": False}
    del result["classification_origin"]
    structure = load_gics_structure()
    curated_code = (row or {}).get("sub_industry_code") or None
    if user:
        curated_path = structure.get(curated_code or "")
        result["user_edit"] = {
            "edited_at": user["edited_at"],
            "curated_sub_industry_code": curated_code,
            "curated_sub_industry": curated_path.sub_industry if curated_path else None,
            "curated_changed_since_edit": curated_code != (user.get("curated_code_at_edit") or None),
        }
    if row is None:
        return result
    path = structure.get(result.get("gics_sub_industry_code") or row.get("sub_industry_code") or "")
    result.update({
        "sector_code": path.sector_code if path else None,
        "industry_group_code": path.industry_group_code if path else None,
        "industry_code": path.industry_code if path else None,
        "unclassified_reason": row.get("unclassified_reason"),
        "confidence": row.get("confidence"),
        "rationale": row.get("rationale"),
        "evidence_url": row.get("evidence_url"),
        "review_status": row.get("review_status"),
        "gics_version": row.get("gics_version"),
    })
    return result


def set_user_classification(engine: Engine, cd_cvm: int, sub_industry_code: str) -> dict[str, Any]:
    """Save the analyst's local classification; it wins over curation and survives app updates."""
    code = str(sub_industry_code or "").strip()
    if code not in load_gics_structure():
        raise ValueError(f"Unknown GICS sub-industry code {code!r}")
    with engine.begin() as conn:
        _ensure_curated_table(conn)
        _ensure_user_table(conn)
        curated = _curated_row(conn, cd_cvm)
        conn.execute(text("DELETE FROM company_classification_user WHERE cd_cvm = :cd"), {"cd": int(cd_cvm)})
        conn.execute(
            text("INSERT INTO company_classification_user (cd_cvm, sub_industry_code, curated_code_at_edit, edited_at) "
                 "VALUES (:cd, :code, :curated, :at)"),
            {"cd": int(cd_cvm), "code": code, "curated": (curated or {}).get("sub_industry_code") or None,
             "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()},
        )
        materialize_company(conn, cd_cvm)
        return company_classification(conn, cd_cvm)


def clear_user_classification(engine: Engine, cd_cvm: int) -> dict[str, Any]:
    """Revert to the curated classification (or pending)."""
    with engine.begin() as conn:
        _ensure_curated_table(conn)
        _ensure_user_table(conn)
        conn.execute(text("DELETE FROM company_classification_user WHERE cd_cvm = :cd"), {"cd": int(cd_cvm)})
        materialize_company(conn, cd_cvm)
        return company_classification(conn, cd_cvm)


def gics_structure_rows() -> list[dict[str, str]]:
    """All current GICS sub-industries with their full path, for pickers."""
    return [vars(path) for path in load_gics_structure().values()]
