# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text, Engine

from src.platform.settings import AppSettings
from src.financials.utils import now_iso_seconds

logger = logging.getLogger("src.companies.market_history")

YAHOO_TICKER_ALIASES: dict[str, str] = {
    # Eletrobras rebranded to AXIA Energia. B3 tickers changed on 2025-11-10.
    # Keep old DB/company mappings readable, but use active Yahoo symbols for
    # market-history downloads.
    "ELET3.SA": "AXIA3.SA",
    "ELET5.SA": "AXIA5.SA",
    "ELET6.SA": "AXIA6.SA",
}

YAHOO_TICKER_CANDIDATE_ALIASES: dict[str, list[str]] = {
    "ELET3.SA": ["AXIA3.SA", "AXIA5.SA", "AXIA6.SA", "AXIA7.SA"],
    "ELET5.SA": ["AXIA5.SA", "AXIA3.SA", "AXIA6.SA", "AXIA7.SA"],
    "ELET6.SA": ["AXIA6.SA", "AXIA3.SA", "AXIA5.SA", "AXIA7.SA"],
    "AXIA3.SA": ["AXIA3.SA", "AXIA5.SA", "AXIA6.SA", "AXIA7.SA"],
    "AXIA5.SA": ["AXIA5.SA", "AXIA3.SA", "AXIA6.SA", "AXIA7.SA"],
    "AXIA6.SA": ["AXIA6.SA", "AXIA3.SA", "AXIA5.SA", "AXIA7.SA"],
}


def _normalize_yahoo_ticker(ticker: str | None) -> str | None:
    if not ticker:
        return None
    normalized = str(ticker).strip().upper()
    if not normalized:
        return None
    if "." not in normalized:
        normalized = f"{normalized}.SA"
    return YAHOO_TICKER_ALIASES.get(normalized, normalized)


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric) or not math.isfinite(numeric):
        return None
    return numeric


def _positive_float(value: Any) -> float | None:
    numeric = _finite_float(value)
    if numeric is None or numeric <= 0:
        return None
    return numeric


@dataclass(frozen=True)
class MarketHistoryObservation:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: float | None
    dividend: float
    split_ratio: float
    price_return_index: float | None = None
    total_return_index: float | None = None
    ttm_dividend_yield: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketHistorySummary:
    initial_close: float | None
    final_close: float | None
    absolute_change: float | None
    price_return: float | None
    total_return: float | None
    annualized_total_return: float | None
    period_high: float | None
    period_low: float | None
    average_daily_volume: float | None
    dividends_per_share: float
    first_available_date: str | None
    last_available_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_market_history_tables_for_connection(conn: Any) -> None:
    """Creates the market_history table and its indices if they do not exist."""
    dialect_name = conn.dialect.name if hasattr(conn, "dialect") else "sqlite"
    pk = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect_name == "sqlite" else "SERIAL PRIMARY KEY"
    real = "REAL" if dialect_name == "sqlite" else "DOUBLE PRECISION"
    
    conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS market_history (
                id {pk},
                cd_cvm INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                open {real},
                high {real},
                low {real},
                close {real},
                adjusted_close {real},
                volume {real},
                dividend {real} DEFAULT 0.0,
                split_ratio {real} DEFAULT 1.0,
                source TEXT,
                provider_status TEXT,
                downloaded_at TEXT,
                UNIQUE(cd_cvm, ticker, date)
            )
            """
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_market_history_cd_cvm_date ON market_history(cd_cvm, date)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_market_history_ticker_date ON market_history(ticker, date)"
        )
    )


def resolve_ticker(cd_cvm: int | str, read_service: Any = None) -> str | None:
    """Resolves CVM code to a canonical Yahoo Finance symbol (ends with .SA if Brazilian)."""
    try:
        cd_cvm = int(cd_cvm)
    except (ValueError, TypeError):
        return None

    ticker = None
    if read_service:
        try:
            info = read_service.query_layer.get_company_info(cd_cvm)
            if info:
                ticker = info.get("ticker_b3")
        except Exception as exc:
            logger.debug("Error retrieving ticker from query_layer for cd_cvm=%s: %s", cd_cvm, exc)

    if not ticker:
        from src.companies.identity import CompanyIdentityResolver
        resolver = CompanyIdentityResolver()
        identity = resolver.resolve(cd_cvm)
        ticker = identity.ticker_b3 if identity else None

    if not ticker:
        return None

    return _normalize_yahoo_ticker(ticker)


def resolve_company_tickers(cd_cvm: int | str, read_service: Any = None) -> list[str]:
    """Resolves CVM code to a list of candidate Yahoo Finance symbols (e.g. PETR3.SA, PETR4.SA)."""
    try:
        cd_cvm = int(cd_cvm)
    except (ValueError, TypeError):
        return []

    primary = resolve_ticker(cd_cvm, read_service)
    if not primary:
        return []

    legacy_primary = None
    if read_service:
        try:
            info = read_service.query_layer.get_company_info(cd_cvm)
            if info and info.get("ticker_b3"):
                legacy_primary = _normalize_yahoo_ticker(str(info.get("ticker_b3")))
        except Exception:
            legacy_primary = None

    alias_candidates = YAHOO_TICKER_CANDIDATE_ALIASES.get(primary)
    if alias_candidates:
        return alias_candidates
    if legacy_primary and legacy_primary != primary:
        alias_candidates = YAHOO_TICKER_CANDIDATE_ALIASES.get(legacy_primary)
        if alias_candidates:
            return alias_candidates
    
    # Extract the base ticker (letters only, usually first 4 characters, e.g. PETR)
    import re
    m = re.match(r"^([A-Z]{4})\d+", primary)
    if not m:
        return [primary]
    
    base = m.group(1)
    suffixes = ["3", "4", "5", "6", "11"]
    candidates = [f"{base}{s}.SA" for s in suffixes]
    
    result = [primary]
    for c in candidates:
        if c not in result:
            result.append(c)
    return result


class MarketHistoryService:
    def __init__(self, *, settings: AppSettings, read_service: Any = None) -> None:
        self.settings = settings
        self.read_service = read_service
        self.engine = read_service.engine if read_service else None

    def get_market_history_status(self, cd_cvm: int, ticker: str | None = None) -> dict[str, Any]:
        """Returns the local cache availability, date ranges, and row counts."""
        available_tickers = resolve_company_tickers(cd_cvm, self.read_service)
        if not ticker:
            ticker = resolve_ticker(cd_cvm, self.read_service)
            
        if not ticker:
            return {
                "cd_cvm": cd_cvm,
                "ticker": None,
                "available_tickers": [],
                "has_local_data": False,
                "first_date": None,
                "last_date": None,
                "row_count": 0,
                "last_downloaded_at": None,
                "is_stale": True,
                "warnings": ["No ticker resolved for this CVM code."],
            }

        if not self.engine:
            return {
                "cd_cvm": cd_cvm,
                "ticker": ticker,
                "available_tickers": available_tickers,
                "has_local_data": False,
                "first_date": None,
                "last_date": None,
                "row_count": 0,
                "last_downloaded_at": None,
                "is_stale": True,
                "warnings": ["Database engine not initialized."],
            }

        try:
            with self.engine.begin() as conn:
                ensure_market_history_tables_for_connection(conn)
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT MIN(date), MAX(date), COUNT(*), MAX(downloaded_at)
                        FROM market_history
                        WHERE cd_cvm = :cd_cvm AND ticker = :ticker
                        """
                    ),
                    {"cd_cvm": cd_cvm, "ticker": ticker},
                ).fetchone()

            if result and result[2] > 0:
                first_date, last_date, count, last_downloaded = result
                
                # Check stale (stale if last downloaded more than 1 day ago)
                is_stale = True
                if last_downloaded:
                    try:
                        dt = datetime.fromisoformat(last_downloaded.replace("Z", "+00:00"))
                        # timezone naive vs aware comparison safety
                        now = datetime.now(dt.tzinfo)
                        if now - dt < timedelta(days=1):
                            is_stale = False
                    except Exception:
                        pass

                return {
                    "cd_cvm": cd_cvm,
                    "ticker": ticker,
                    "available_tickers": available_tickers,
                    "has_local_data": True,
                    "first_date": first_date,
                    "last_date": last_date,
                    "row_count": count,
                    "last_downloaded_at": last_downloaded,
                    "is_stale": is_stale,
                    "warnings": [],
                }
        except Exception as exc:
            logger.error("Error reading market history status for cd_cvm=%s: %s", cd_cvm, exc)

        return {
            "cd_cvm": cd_cvm,
            "ticker": ticker,
            "available_tickers": available_tickers,
            "has_local_data": False,
            "first_date": None,
            "last_date": None,
            "row_count": 0,
            "last_downloaded_at": None,
            "is_stale": True,
            "warnings": ["No local market history has been downloaded yet."],
        }

    def refresh_market_history(
        self,
        cd_cvm: int,
        ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Fetches historical prices from yfinance and performs transaction-safe, idempotent upserts."""
        if not ticker:
            ticker = resolve_ticker(cd_cvm, self.read_service)
        if not ticker:
            return {"ok": False, "error": "No ticker resolved for this CVM code.", "downloaded_rows": 0}

        t0 = time.perf_counter()
        status = self.get_market_history_status(cd_cvm, ticker=ticker)

        # Decide start/end date range
        if not start_date:
            if status["has_local_data"] and status["last_date"]:
                # 30 days overlap to catch restatements, stock splits, late dividend events
                latest_stored = datetime.strptime(status["last_date"], "%Y-%m-%d")
                start_date = (latest_stored - timedelta(days=30)).strftime("%Y-%m-%d")
            else:
                start_date = "2000-01-01"

        if not end_date:
            end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info("Refreshing market history for %s (CVM %s) from %s to %s", ticker, cd_cvm, start_date, end_date)

        try:
            import yfinance as yf
            ticker_client = yf.Ticker(ticker)
            df = ticker_client.history(
                start=start_date,
                end=end_date,
                auto_adjust=False,
                actions=True,
            )
        except Exception as exc:
            logger.error("yfinance query failed for ticker %s: %s", ticker, exc)
            return {
                "ok": False,
                "ticker": ticker,
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "downloaded_rows": 0,
                "inserted_rows": 0,
                "updated_rows": 0,
                "unchanged_rows": 0,
                "rejected_rows": 0,
                "provider_warnings": [f"yfinance failed: {exc}"],
                "completion_timestamp": now_iso_seconds(),
                "refresh_duration_seconds": round(time.perf_counter() - t0, 3),
                "error": str(exc),
            }

        if df.empty:
            logger.warning("yfinance returned no observations for ticker %s", ticker)
            return {
                "ok": True,
                "ticker": ticker,
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "provider_date_range": None,
                "downloaded_rows": 0,
                "inserted_rows": 0,
                "updated_rows": 0,
                "unchanged_rows": 0,
                "rejected_rows": 0,
                "provider_warnings": ["Provider returned empty dataset."],
                "completion_timestamp": now_iso_seconds(),
                "refresh_duration_seconds": round(time.perf_counter() - t0, 3),
            }

        # Normalize and validate rows
        observations = []
        rejected_count = 0
        
        for date_val, row in df.iterrows():
            date_str = date_val.strftime("%Y-%m-%d")
            
            open_val = _positive_float(row.get("Open"))
            high_val = _positive_float(row.get("High"))
            low_val = _positive_float(row.get("Low"))
            close_val = _finite_float(row.get("Close"))
            adj_close_val = _positive_float(row.get("Adj Close"))
            if adj_close_val is None and close_val is not None and close_val > 0:
                adj_close_val = close_val

            volume_val = _finite_float(row.get("Volume"))
            dividend_val = _finite_float(row.get("Dividends")) or 0.0
            split_ratio_val = _finite_float(row.get("Stock Splits")) or 1.0

            # Price must be positive or null. Reject provider placeholders.
            if close_val is not None and close_val <= 0:
                rejected_count += 1
                continue

            observations.append({
                "date": date_str,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "adjusted_close": adj_close_val,
                "volume": volume_val,
                "dividend": dividend_val,
                "split_ratio": split_ratio_val,
            })

        # Remove duplicate dates from response (should be unique in index, but verify)
        deduped = {}
        for obs in observations:
            deduped[obs["date"]] = obs
        observations = list(deduped.values())

        if not observations:
            return {
                "ok": True,
                "ticker": ticker,
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "downloaded_rows": len(df),
                "inserted_rows": 0,
                "updated_rows": 0,
                "unchanged_rows": 0,
                "rejected_rows": rejected_count,
                "provider_warnings": ["All downloaded observations were rejected/filtered."],
                "completion_timestamp": now_iso_seconds(),
                "refresh_duration_seconds": round(time.perf_counter() - t0, 3),
            }

        # Select existing records in the downloaded range to compare
        downloaded_dates = [obs["date"] for obs in observations]
        existing_data = {}
        try:
            with self.engine.connect() as conn:
                placeholders = ", ".join(f"'{d}'" for d in downloaded_dates)
                if placeholders:
                    query = text(
                        f"""
                        SELECT date, open, high, low, close, adjusted_close, volume, dividend, split_ratio
                        FROM market_history
                        WHERE cd_cvm = :cd_cvm AND ticker = :ticker AND date IN ({placeholders})
                        """
                    )
                    rows = conn.execute(query, {"cd_cvm": cd_cvm, "ticker": ticker}).fetchall()
                    for r in rows:
                        existing_data[r[0]] = {
                            "open": r[1],
                            "high": r[2],
                            "low": r[3],
                            "close": r[4],
                            "adjusted_close": r[5],
                            "volume": r[6],
                            "dividend": r[7],
                            "split_ratio": r[8],
                        }
        except Exception as exc:
            logger.warning("Could not pre-fetch existing rows for comparison: %s", exc)

        inserted_rows = 0
        updated_rows = 0
        unchanged_rows = 0

        # Run upserts inside transaction
        try:
            with self.engine.begin() as conn:
                for obs in observations:
                    dt_str = obs["date"]
                    exists = dt_str in existing_data
                    
                    if exists:
                        # Compare
                        prev = existing_data[dt_str]
                        is_same = (
                            prev["open"] == obs["open"]
                            and prev["high"] == obs["high"]
                            and prev["low"] == obs["low"]
                            and prev["close"] == obs["close"]
                            and prev["adjusted_close"] == obs["adjusted_close"]
                            and prev["volume"] == obs["volume"]
                            and prev["dividend"] == obs["dividend"]
                            and prev["split_ratio"] == obs["split_ratio"]
                        )
                        if is_same:
                            unchanged_rows += 1
                        else:
                            updated_rows += 1
                    else:
                        inserted_rows += 1

                    conn.execute(
                        text(
                            """
                            INSERT INTO market_history (
                                cd_cvm, ticker, date, open, high, low, close, adjusted_close,
                                volume, dividend, split_ratio, source, provider_status, downloaded_at
                            ) VALUES (
                                :cd_cvm, :ticker, :date, :open, :high, :low, :close, :adjusted_close,
                                :volume, :dividend, :split_ratio, :source, :provider_status, :downloaded_at
                            )
                            ON CONFLICT(cd_cvm, ticker, date) DO UPDATE SET
                                open = excluded.open,
                                high = excluded.high,
                                low = excluded.low,
                                close = excluded.close,
                                adjusted_close = excluded.adjusted_close,
                                volume = excluded.volume,
                                dividend = excluded.dividend,
                                split_ratio = excluded.split_ratio,
                                source = excluded.source,
                                provider_status = excluded.provider_status,
                                downloaded_at = excluded.downloaded_at
                            """
                        ),
                        {
                            "cd_cvm": cd_cvm,
                            "ticker": ticker,
                            "date": dt_str,
                            "open": obs["open"],
                            "high": obs["high"],
                            "low": obs["low"],
                            "close": obs["close"],
                            "adjusted_close": obs["adjusted_close"],
                            "volume": obs["volume"],
                            "dividend": obs["dividend"],
                            "split_ratio": obs["split_ratio"],
                            "source": "yahoo_finance",
                            "provider_status": "unofficial_free",
                            "downloaded_at": now_iso_seconds(),
                        }
                    )
        except Exception as exc:
            logger.error("Transaction failed during market_history refresh for cd_cvm=%s: %s", cd_cvm, exc)
            return {
                "ok": False,
                "ticker": ticker,
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "downloaded_rows": len(observations),
                "inserted_rows": 0,
                "updated_rows": 0,
                "unchanged_rows": 0,
                "rejected_rows": rejected_count,
                "provider_warnings": [f"Database write failure: {exc}"],
                "completion_timestamp": now_iso_seconds(),
                "refresh_duration_seconds": round(time.perf_counter() - t0, 3),
                "error": str(exc),
            }

        # Re-check status to get correct first/last dates
        new_status = self.get_market_history_status(cd_cvm)

        return {
            "ok": True,
            "ticker": ticker,
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "provider_date_range": f"{observations[0]['date']} to {observations[-1]['date']}",
            "downloaded_rows": len(observations),
            "inserted_rows": inserted_rows,
            "updated_rows": updated_rows,
            "unchanged_rows": unchanged_rows,
            "rejected_rows": rejected_count,
            "first_stored_date": new_status.get("first_date"),
            "last_stored_date": new_status.get("last_date"),
            "provider_warnings": [],
            "completion_timestamp": now_iso_seconds(),
            "refresh_duration_seconds": round(time.perf_counter() - t0, 3),
        }

    def get_market_history(
        self,
        cd_cvm: int,
        ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        period: str | None = None,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """Retrieves and calculates returns/TTM dividend yield for the company from local database."""
        if not ticker:
            ticker = resolve_ticker(cd_cvm, self.read_service)
        if not ticker:
            return {
                "cd_cvm": cd_cvm,
                "ticker": "",
                "source": "yahoo_finance",
                "provider_status": "unofficial_free",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "actual_start_date": None,
                "actual_end_date": None,
                "interval": interval,
                "last_downloaded_at": None,
                "is_stale": True,
                "has_local_data": False,
                "warnings": ["No ticker resolved for this CVM code."],
                "observations": [],
                "summary": None,
            }

        status = self.get_market_history_status(cd_cvm, ticker=ticker)
        if not status["has_local_data"]:
            return {
                "cd_cvm": cd_cvm,
                "ticker": ticker,
                "source": "yahoo_finance",
                "provider_status": "unofficial_free",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "actual_start_date": None,
                "actual_end_date": None,
                "interval": interval,
                "last_downloaded_at": None,
                "is_stale": True,
                "has_local_data": False,
                "warnings": ["No local market history has been downloaded yet."],
                "observations": [],
                "summary": None,
            }

        # Query all observations for this CVM code sorted by date
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT date, open, high, low, close, adjusted_close, volume, dividend, split_ratio
                        FROM market_history
                        WHERE cd_cvm = :cd_cvm AND ticker = :ticker
                        ORDER BY date ASC
                        """
                    ),
                    {"cd_cvm": cd_cvm, "ticker": ticker},
                ).fetchall()
        except Exception as exc:
            logger.error("Failed to query market history for cd_cvm=%s: %s", cd_cvm, exc)
            return {
                "cd_cvm": cd_cvm,
                "ticker": ticker,
                "source": "yahoo_finance",
                "provider_status": "unofficial_free",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "actual_start_date": None,
                "actual_end_date": None,
                "interval": interval,
                "last_downloaded_at": status.get("last_downloaded_at"),
                "is_stale": status.get("is_stale", True),
                "has_local_data": True,
                "warnings": [f"Error reading local data: {exc}"],
                "observations": [],
                "summary": None,
            }

        if not rows:
            return {
                "cd_cvm": cd_cvm,
                "ticker": ticker,
                "source": "yahoo_finance",
                "provider_status": "unofficial_free",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "actual_start_date": None,
                "actual_end_date": None,
                "interval": interval,
                "last_downloaded_at": status.get("last_downloaded_at"),
                "is_stale": status.get("is_stale", True),
                "has_local_data": True,
                "warnings": ["Local cache database has no rows for this company."],
                "observations": [],
                "summary": None,
            }

        # Map to raw observations list
        all_obs = []
        for r in rows:
            close_val = _positive_float(r[4])
            adjusted_close_val = _positive_float(r[5]) or close_val
            all_obs.append({
                "date": r[0],
                "open": _positive_float(r[1]),
                "high": _positive_float(r[2]),
                "low": _positive_float(r[3]),
                "close": close_val,
                "adjusted_close": adjusted_close_val,
                "volume": _finite_float(r[6]),
                "dividend": r[7] or 0.0,
                "split_ratio": r[8] or 1.0,
            })

        # Calculate TTM Dividend Yield for all dates first (needs full history)
        # We can optimize: group dividends by date, then query them.
        dividend_events = [(datetime.strptime(o["date"], "%Y-%m-%d"), o["dividend"]) for o in all_obs if o["dividend"] > 0]
        
        # Precompute TTM dividend for each date to avoid O(N*M) lookups
        # Since daily history is in order:
        dates_list = [datetime.strptime(o["date"], "%Y-%m-%d") for o in all_obs]
        
        ttm_dividends_by_date = []
        for d in dates_list:
            cutoff = d - timedelta(days=365)
            # Sum cash dividends paid in (d-365, d]
            tot = sum(div for div_date, div in dividend_events if cutoff < div_date <= d)
            ttm_dividends_by_date.append(tot)

        for obs, ttm_div in zip(all_obs, ttm_dividends_by_date):
            price = obs["close"]
            if price is not None and price > 0:
                obs["ttm_dividend_yield"] = ttm_div / price
            else:
                obs["ttm_dividend_yield"] = None

        # Determine start/end ranges based on Period / Date parameters
        latest_date_str = all_obs[-1]["date"]
        latest_dt = datetime.strptime(latest_date_str, "%Y-%m-%d")

        if period:
            period = period.strip().upper()
            if period == "1M":
                start_dt = latest_dt - timedelta(days=30)
            elif period == "3M":
                start_dt = latest_dt - timedelta(days=90)
            elif period == "6M":
                start_dt = latest_dt - timedelta(days=180)
            elif period == "YTD":
                start_dt = datetime(latest_dt.year, 1, 1)
            elif period == "1Y":
                start_dt = latest_dt - timedelta(days=365)
            elif period == "3Y":
                start_dt = latest_dt - timedelta(days=3 * 365)
            elif period == "5Y":
                start_dt = latest_dt - timedelta(days=5 * 365)
            elif period == "10Y":
                start_dt = latest_dt - timedelta(days=10 * 365)
            else:  # MAX or fallback
                start_dt = datetime(2000, 1, 1)
            
            start_date = start_dt.strftime("%Y-%m-%d")
            end_date = latest_date_str
        else:
            if not start_date:
                start_date = "2000-01-01"
            if not end_date:
                end_date = latest_date_str

        # Filter observations
        filtered_obs = [o for o in all_obs if start_date <= o["date"] <= end_date]

        if not filtered_obs:
            return {
                "cd_cvm": cd_cvm,
                "ticker": ticker,
                "source": "yahoo_finance",
                "provider_status": "unofficial_free",
                "requested_start_date": start_date,
                "requested_end_date": end_date,
                "actual_start_date": None,
                "actual_end_date": None,
                "interval": interval,
                "last_downloaded_at": status.get("last_downloaded_at"),
                "is_stale": status.get("is_stale", True),
                "has_local_data": True,
                "warnings": [f"Selected date range contains no trading sessions: {start_date} to {end_date}"],
                "observations": [],
                "summary": None,
            }

        # Aggregate by interval if needed
        # Supported: 1d, 1wk, 1mo
        if interval in ("1wk", "1mo"):
            aggregated = []
            
            df_temp = pd.DataFrame(filtered_obs)
            df_temp["dt"] = pd.to_datetime(df_temp["date"])
            
            if interval == "1wk":
                # Resample weekly. Note that yfinance/pandas week grouping typically groups Mon-Sun.
                # We can group by year and week number.
                df_temp["group_key"] = df_temp["dt"].dt.to_period("W").astype(str)
            else:
                # Group by calendar month
                df_temp["group_key"] = df_temp["dt"].dt.to_period("M").astype(str)

            grouped = df_temp.groupby("group_key")
            for _, grp in grouped:
                if grp.empty:
                    continue
                # Sort group by date
                grp = grp.sort_values("dt")
                
                # Take last row for close, adjusted_close, ttm_dividend_yield
                last_row = grp.iloc[-1]
                # First row for open
                first_row = grp.iloc[0]
                
                aggregated.append({
                    "date": last_row["date"],
                    "open": first_row["open"],
                    "high": grp["high"].max(),
                    "low": grp["low"].min(),
                    "close": last_row["close"],
                    "adjusted_close": last_row["adjusted_close"],
                    "volume": grp["volume"].sum(),
                    "dividend": grp["dividend"].sum(),
                    "split_ratio": last_row["split_ratio"], # last split ratio in group
                    "ttm_dividend_yield": last_row["ttm_dividend_yield"],
                })
            
            # Sort aggregated by date
            aggregated.sort(key=lambda o: o["date"])
            obs_to_calc = aggregated
        else:
            obs_to_calc = filtered_obs

        # Calculate returns relative to the baseline of this filtered period
        # Baseline = first element in our list (the oldest in the selected range)
        baseline = obs_to_calc[0]
        init_close = baseline["close"]
        init_adj = baseline["adjusted_close"]

        observations_final = []
        for o in obs_to_calc:
            close_val = o["close"]
            adj_val = o["adjusted_close"]

            price_return_idx = None
            if init_close is not None and init_close > 0 and close_val is not None:
                price_return_idx = close_val / init_close

            total_return_idx = None
            if init_adj is not None and init_adj > 0 and adj_val is not None:
                total_return_idx = adj_val / init_adj

            observations_final.append(
                MarketHistoryObservation(
                    date=o["date"],
                    open=o["open"],
                    high=o["high"],
                    low=o["low"],
                    close=o["close"],
                    adjusted_close=o["adjusted_close"],
                    volume=o["volume"],
                    dividend=o["dividend"],
                    split_ratio=o["split_ratio"],
                    price_return_index=price_return_idx,
                    total_return_index=total_return_idx,
                    ttm_dividend_yield=o["ttm_dividend_yield"],
                )
            )

        # Calculate period summary metrics
        first_date_val = datetime.strptime(observations_final[0].date, "%Y-%m-%d")
        last_date_val = datetime.strptime(observations_final[-1].date, "%Y-%m-%d")
        elapsed_calendar_days = (last_date_val - first_date_val).days

        final_close = observations_final[-1].close
        final_adj = observations_final[-1].adjusted_close

        price_return_val = None
        if init_close is not None and init_close > 0 and final_close is not None:
            price_return_val = (final_close / init_close) - 1.0

        total_return_val = None
        if init_adj is not None and init_adj > 0 and final_adj is not None:
            total_return_val = (final_adj / init_adj) - 1.0

        annualized_total_return_val = None
        if (
            elapsed_calendar_days >= 365
            and init_adj is not None
            and init_adj > 0
            and final_adj is not None
            and final_adj > 0
        ):
            annualized_total_return_val = (final_adj / init_adj) ** (365.0 / elapsed_calendar_days) - 1.0

        absolute_change_val = None
        if final_close is not None and init_close is not None:
            absolute_change_val = final_close - init_close

        highs = [o.high for o in observations_final if o.high is not None]
        lows = [o.low for o in observations_final if o.low is not None]
        vols = [o.volume for o in observations_final if o.volume is not None]

        period_high_val = max(highs) if highs else None
        period_low_val = min(lows) if lows else None
        average_daily_volume_val = sum(vols) / len(vols) if vols else None

        # sum dividends paid in period (sum the daily data in filtered range, not weekly aggregated ones to avoid double count/mismatch)
        dividends_sum = sum(o["dividend"] for o in filtered_obs)

        summary = MarketHistorySummary(
            initial_close=init_close,
            final_close=final_close,
            absolute_change=absolute_change_val,
            price_return=price_return_val,
            total_return=total_return_val,
            annualized_total_return=annualized_total_return_val,
            period_high=period_high_val,
            period_low=period_low_val,
            average_daily_volume=average_daily_volume_val,
            dividends_per_share=dividends_sum,
            first_available_date=observations_final[0].date,
            last_available_date=observations_final[-1].date,
        )

        return {
            "cd_cvm": cd_cvm,
            "ticker": ticker,
            "source": "yahoo_finance",
            "provider_status": "unofficial_free",
            "requested_start_date": start_date,
            "requested_end_date": end_date,
            "actual_start_date": observations_final[0].date,
            "actual_end_date": observations_final[-1].date,
            "interval": interval,
            "last_downloaded_at": status.get("last_downloaded_at"),
            "is_stale": status.get("is_stale", True),
            "has_local_data": True,
            "warnings": [],
            "observations": [o.to_dict() for o in observations_final],
            "summary": summary.to_dict(),
        }
