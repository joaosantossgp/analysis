"""B3 sector classification (setor econômico / subsetor / segmento) per listed company.

Official source: B3's listed-companies service, which publishes each company's
industry classification by CVM code. Collected only on an explicit refresh, stored
locally with source and timestamp, and read offline afterwards. Shown as labelled
source metadata next to the CVM sector; it is never the canonical classification
(see docs/reference/gics-import.md). Labels are stored exactly as B3 publishes them.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import requests
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

DETAIL_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetDetail/{token}"
STALE_AFTER_DAYS = 90

Fetcher = Callable[[str], dict[str, Any]]


def detail_url(cd_cvm: int) -> str:
    token = base64.b64encode(json.dumps({"codeCVM": str(int(cd_cvm)), "language": "pt-br"}).encode()).decode()
    return DETAIL_URL.format(token=token)


def _http_fetch(url: str) -> dict[str, Any]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json() if response.content else {}


def parse_industry_classification(raw: str | None) -> tuple[str | None, str | None, str | None]:
    """Split B3's 'Setor / Subsetor / Segmento' string; missing levels stay None."""
    parts = [part.strip() or None for part in str(raw or "").split(" / ")] if raw else []
    parts += [None] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


def _ensure_tables(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS company_b3_classification (
            cd_cvm             INTEGER PRIMARY KEY,
            b3_sector          TEXT,
            b3_subsector       TEXT,
            b3_segment         TEXT,
            raw_classification TEXT,
            source_url         TEXT NOT NULL,
            fetched_at         TEXT NOT NULL
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS b3_classification_refresh_log (
            started_at  TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            requested   INTEGER NOT NULL,
            succeeded   INTEGER NOT NULL,
            not_listed  INTEGER NOT NULL,
            failed      INTEGER NOT NULL,
            errors      TEXT
        )
    """))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def refresh_b3_classification(
    engine: Engine,
    cd_cvm_codes: Iterable[int] | None = None,
    *,
    fetch: Fetcher = _http_fetch,
    delay_seconds: float = 0.2,
) -> dict[str, Any]:
    """Explicit refresh. A failed company keeps its previous row; every run is logged."""
    started_at = _now()
    with engine.begin() as conn:
        _ensure_tables(conn)
        if cd_cvm_codes is None:
            cd_cvm_codes = [int(r[0]) for r in conn.execute(text("SELECT cd_cvm FROM companies")).fetchall()]
    codes = sorted({int(cd) for cd in cd_cvm_codes})
    succeeded, not_listed, errors = 0, 0, []
    # shortcut: sequential, polite calls (one per company); move to a background job if the universe grows past ~1000.
    for index, cd in enumerate(codes):
        if index and delay_seconds:
            time.sleep(delay_seconds)
        url = detail_url(cd)
        try:
            payload = fetch(url)
        except Exception as exc:  # network, HTTP or JSON failure for this company only
            errors.append(f"{cd}: {exc}")
            continue
        raw = (payload or {}).get("industryClassification")
        if not raw:
            not_listed += 1
            continue
        sector, subsector, segment = parse_industry_classification(raw)
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM company_b3_classification WHERE cd_cvm = :cd"), {"cd": cd})
            conn.execute(
                text("INSERT INTO company_b3_classification VALUES (:cd, :s, :ss, :seg, :raw, :url, :at)"),
                {"cd": cd, "s": sector, "ss": subsector, "seg": segment, "raw": raw, "url": url, "at": _now()},
            )
        succeeded += 1
    summary = {
        "started_at": started_at,
        "finished_at": _now(),
        "requested": len(codes),
        "succeeded": succeeded,
        "not_listed": not_listed,
        "failed": len(errors),
        "errors": errors[:20],
    }
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO b3_classification_refresh_log VALUES (:started_at, :finished_at, :requested, "
                 ":succeeded, :not_listed, :failed, :errors)"),
            {**summary, "errors": "\n".join(errors[:20]) or None},
        )
    return summary


def _has_tables(conn) -> bool:
    return inspect(conn).has_table("company_b3_classification")


def b3_classification_for(conn, cd_cvm: int) -> dict[str, Any] | None:
    """Stored B3 classification for one company (offline read), or None if never fetched."""
    if not _has_tables(conn):
        return None
    row = conn.execute(
        text("SELECT * FROM company_b3_classification WHERE cd_cvm = :cd"), {"cd": int(cd_cvm)}
    ).mappings().first()
    if row is None:
        return None
    result = dict(row)
    result["stale"] = _age_days(result["fetched_at"]) > STALE_AFTER_DAYS
    return result


def _age_days(iso: str) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 86400
    except ValueError:
        return float("inf")


def b3_refresh_status(engine: Engine) -> dict[str, Any]:
    """Last refresh run and coverage, for the Sources screen."""
    with engine.connect() as conn:
        if not _has_tables(conn):
            return {"last_run": None, "stored_companies": 0, "stale": True, "stale_after_days": STALE_AFTER_DAYS}
        last = conn.execute(
            text("SELECT * FROM b3_classification_refresh_log ORDER BY finished_at DESC LIMIT 1")
        ).mappings().first()
        stored = conn.execute(text("SELECT COUNT(*) FROM company_b3_classification")).scalar() or 0
    last_run = dict(last) if last else None
    return {
        "last_run": last_run,
        "stored_companies": int(stored),
        "stale": last_run is None or _age_days(last_run["finished_at"]) > STALE_AFTER_DAYS,
        "stale_after_days": STALE_AFTER_DAYS,
    }
