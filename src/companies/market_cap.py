from __future__ import annotations

import csv
import io
import json
import logging
import requests
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.platform.settings import AppSettings
from src.companies.identity import CompanyIdentityResolver
from src.financials.utils import now_iso_seconds

logger = logging.getLogger("src.companies.market_cap")


@dataclass(frozen=True)
class MarketCapEntry:
    as_of_date: str
    rank: int
    cd_cvm: int | None
    cnpj: str | None
    company_name: str
    ticker: str | None
    market_cap_brl: float
    source: str
    method: str
    source_url_or_id: str
    downloaded_at: str
    mapping_status: str
    mapping_confidence: float
    notes: str | None = None
    provider_status: str = "unofficial_free"
    dividend_yield: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    beta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketCapService:
    def __init__(self, *, settings: AppSettings, read_service: Any = None) -> None:
        self.settings = settings
        self.read_service = read_service
        self.snapshot_path = Path(settings.paths.company_universe_snapshot_path)

    def read_snapshot(self) -> list[MarketCapEntry]:
        """Read the local market cap snapshot/cache offline."""
        if not self.snapshot_path.exists():
            raise FileNotFoundError(
                f"No market-cap snapshot exists at {self.snapshot_path}"
            )

        entries: list[MarketCapEntry] = []
        with self.snapshot_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            # Schema validation: verify all required canonical fields exist
            required = {
                "as_of_date",
                "rank",
                "company_name",
                "market_cap_brl",
                "source",
                "method",
                "source_url_or_id",
                "downloaded_at",
                "mapping_status",
                "mapping_confidence",
            }
            if reader.fieldnames is None or not required.issubset(
                set(reader.fieldnames)
            ):
                missing = required - set(reader.fieldnames or [])
                raise ValueError(
                    f"Market cap snapshot is missing required columns: {sorted(missing)}"
                )

            for idx, raw in enumerate(reader, start=1):
                # Helper to grab values case-insensitively/stripped
                row = {str(k).strip().lower(): v for k, v in raw.items()}
                try:
                    rank_val = int(float(str(row.get("rank", "")).strip()))
                    mkt_cap_val = float(str(row.get("market_cap_brl", "")).strip())
                    confidence_val = float(
                        str(row.get("mapping_confidence", "0.0")).strip()
                    )
                except ValueError as exc:
                    raise ValueError(
                        f"Row {idx} contains invalid numeric value: {exc}"
                    ) from exc

                cd_cvm_val = None
                cd_cvm_str = str(row.get("cd_cvm", "")).strip()
                if cd_cvm_str not in ("", "None", "null"):
                    try:
                        cd_cvm_val = int(float(cd_cvm_str))
                    except ValueError:
                        pass

                def _parse_float_or_none(v: Any) -> float | None:
                    if v is None:
                        return None
                    v_str = str(v).strip()
                    if v_str in ("", "None", "null"):
                        return None
                    try:
                        return float(v_str)
                    except ValueError:
                        return None

                entries.append(
                    MarketCapEntry(
                        as_of_date=str(row.get("as_of_date", "")).strip(),
                        rank=rank_val,
                        cd_cvm=cd_cvm_val,
                        cnpj=_clean_cnpj(row.get("cnpj")),
                        company_name=str(row.get("company_name", "")).strip(),
                        ticker=_clean_ticker(row.get("ticker")),
                        market_cap_brl=mkt_cap_val,
                        source=str(row.get("source", "")).strip(),
                        method=str(row.get("method", "")).strip(),
                        source_url_or_id=str(row.get("source_url_or_id", "")).strip(),
                        downloaded_at=str(row.get("downloaded_at", "")).strip(),
                        mapping_status=str(row.get("mapping_status", "")).strip(),
                        mapping_confidence=confidence_val,
                        notes=str(row.get("notes", "")).strip() or None,
                        provider_status=str(row.get("provider_status", "unofficial_free")).strip(),
                        dividend_yield=_parse_float_or_none(row.get("dividend_yield")),
                        pe_ratio=_parse_float_or_none(row.get("pe_ratio")),
                        pb_ratio=_parse_float_or_none(row.get("pb_ratio")),
                        beta=_parse_float_or_none(row.get("beta")),
                    )
                )

        return entries

    def get_status(self) -> dict[str, Any]:
        """Expose freshness and statistics of the local cached market cap list."""
        if not self.snapshot_path.exists():
            return {
                "available": False,
                "row_count": 0,
                "as_of_date": None,
                "downloaded_at": None,
                "source": None,
                "provider_status": None,
                "warnings": ["No local market-cap snapshot is available."],
            }
        try:
            entries = self.read_snapshot()
            if not entries:
                return {
                    "available": False,
                    "row_count": 0,
                    "as_of_date": None,
                    "downloaded_at": None,
                    "source": None,
                    "provider_status": None,
                    "warnings": ["Local market-cap snapshot is empty."],
                }
            unmapped = [
                e.ticker or e.company_name
                for e in entries
                if e.mapping_status != "mapped"
            ]
            warnings = []
            if unmapped:
                warnings.append(
                    f"{len(unmapped)} companies could not be mapped to the CVM catalog."
                )
            return {
                "available": True,
                "row_count": len(entries),
                "as_of_date": entries[0].as_of_date,
                "downloaded_at": entries[0].downloaded_at,
                "source": entries[0].source,
                "provider_status": entries[0].provider_status,
                "method": entries[0].method,
                "source_url_or_id": entries[0].source_url_or_id,
                "mapped_count": sum(1 for e in entries if e.mapping_status == "mapped"),
                "unmapped_count": len(unmapped),
                "unmapped_identifiers": unmapped[:20],  # sample
                "warnings": warnings,
            }
        except Exception as exc:
            return {
                "available": False,
                "row_count": 0,
                "as_of_date": None,
                "downloaded_at": None,
                "source": None,
                "provider_status": None,
                "warnings": [f"Error reading market-cap snapshot: {exc}"],
            }

    def import_snapshot(
        self, csv_filepath_or_content: str | Path | io.StringIO
    ) -> dict[str, Any]:
        """Import, map, validate, and write a market cap CSV list atomically."""
        raw_rows = self._parse_and_validate_raw_csv(csv_filepath_or_content)
        mapped_entries = self._map_entries(raw_rows)
        self._write_snapshot(mapped_entries)
        return self.get_status()

    def _write_snapshot(self, mapped_entries: list[MarketCapEntry]) -> None:
        """Write canonical CSV snapshot atomically to disk."""
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.snapshot_path.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "as_of_date",
                        "rank",
                        "cd_cvm",
                        "cnpj",
                        "company_name",
                        "ticker",
                        "market_cap_brl",
                        "source",
                        "method",
                        "source_url_or_id",
                        "downloaded_at",
                        "mapping_status",
                        "mapping_confidence",
                        "notes",
                        "provider_status",
                        "dividend_yield",
                        "pe_ratio",
                        "pb_ratio",
                        "beta",
                    ],
                )
                writer.writeheader()
                for entry in mapped_entries:
                    writer.writerow(entry.to_dict())
            temp_path.replace(self.snapshot_path)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def fetch_from_yahoo_finance(self) -> dict[str, Any]:
        """Automatically query Yahoo Finance bulk quote API for mapped tickers and save snapshot."""
        # Accept both canonical 'yahoo_finance' and deprecated alias 'yfinance'
        if self.settings.market_cap_provider not in ("yahoo_finance", "yfinance"):
            raise RuntimeError(
                f"Yahoo Finance market-cap provider is not enabled. "
                "Configure CVM_MARKET_CAP_PROVIDER=yahoo_finance to enable."
            )
        # Get unique tickers from resolver
        resolver = CompanyIdentityResolver()
        tickers = resolver.get_all_configured_tickers()
        if not tickers:
            raise ValueError("No tickers found to fetch.")

        parsed_rows: list[dict[str, Any]] = []
        as_of_val = now_iso_seconds()[:10]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        seen_symbols: set[str] = set()

        session = requests.Session()
        session.headers.update(headers)

        # Pre-fetch cookie and crumb
        crumb = None
        try:
            session.get("https://fc.yahoo.com", timeout=10)
            crumb_resp = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
            crumb_resp.raise_for_status()
            crumb = crumb_resp.text.strip()
        except Exception as exc:
            logger.warning("Failed to retrieve Yahoo Finance crumb token: %s. Proceeding without crumb.", exc)

        # Query in batches of 100 tickers
        batch_size = 100
        for i in range(0, len(tickers), batch_size):
            chunk = tickers[i : i + batch_size]
            symbols_param = ",".join(chunk)
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_param}"
            if crumb:
                url += f"&crumb={crumb}"
            
            try:
                response = session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.error("Failed to query Yahoo Finance bulk quote: %s", exc)
                raise RuntimeError(f"Yahoo Finance API request failed: {exc}") from exc

            quote_response = data.get("quoteResponse", {})
            results = quote_response.get("result")
            if not results:
                logger.warning("Yahoo Finance response contains no results for symbol chunk.")
                continue

            for item in results:
                ticker = item.get("symbol")
                if not ticker or ticker in seen_symbols:
                    continue
                seen_symbols.add(ticker)
                market_cap = item.get("marketCap")
                if market_cap is None:
                    continue
                try:
                    market_cap_brl = float(market_cap)
                except (ValueError, TypeError):
                    continue

                if market_cap_brl <= 0.0:
                    continue

                company_name = item.get("longName") or item.get("shortName") or ticker

                # Fetch new metrics
                div_yield = item.get("trailingAnnualDividendYield") or item.get("dividendYield")
                pe_ratio = item.get("trailingPE") or item.get("forwardPE")
                pb_ratio = item.get("priceToBook")
                beta_val = item.get("beta")

                def _to_float(v: Any) -> float | None:
                    if v is None:
                        return None
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        return None

                parsed_rows.append(
                    {
                        "as_of_date": as_of_val,
                        "rank_raw": None,  # Assigned below
                        "cd_cvm_raw": None,  # Mapped in _map_entries
                        "cnpj_raw": None,
                        "company_name": str(company_name).strip(),
                        "ticker": ticker,
                        "market_cap_brl": market_cap_brl,
                        "source": "yahoo_finance",
                        "provider_status": "unofficial_free",
                        "method": "yahoo_finance_bulk_quote",
                        "source_url_or_id": "https://query1.finance.yahoo.com/v7/finance/quote",
                        "notes": None,
                        "dividend_yield": _to_float(div_yield),
                        "pe_ratio": _to_float(pe_ratio),
                        "pb_ratio": _to_float(pb_ratio),
                        "beta": _to_float(beta_val),
                    }
                )

        if not parsed_rows:
            raise RuntimeError("No valid market cap entries resolved from Yahoo Finance quotes.")

        # Sort descending by market cap and assign rank
        parsed_rows.sort(key=lambda r: -r["market_cap_brl"])
        for idx, r in enumerate(parsed_rows, start=1):
            r["rank"] = idx

        # Run catalog mapping
        mapped_entries = self._map_entries(parsed_rows)

        # Write to disk
        self._write_snapshot(mapped_entries)

        return self.get_status()

    def fetch_yahoo_price_history(self, ticker: str) -> dict[int, float]:
        """Fetch monthly price history from Yahoo Finance and return year -> end_of_year_price."""
        import math  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415
        
        # Ensure ticker has .SA if it is a pure Brazilian ticker (numeric ending) and no suffix
        ticker = ticker.strip()
        if ticker and "." not in ticker:
            ticker = f"{ticker}.SA"
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=10y&interval=1mo"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            result = data.get("chart", {}).get("result")
            if not result:
                return {}
            
            timestamps = result[0].get("timestamp", [])
            indicators = result[0].get("indicators", {})
            
            # Prefer adjusted close (adjclose) over close if available
            adjclose_list = indicators.get("adjclose", [{}])[0].get("adjclose", [])
            close_list = indicators.get("quote", [{}])[0].get("close", [])
            
            prices = adjclose_list if adjclose_list else close_list
            if not prices or len(prices) != len(timestamps):
                prices = close_list
                
            if not prices or len(prices) != len(timestamps):
                return {}
                
            # Group by year and take the last valid price
            year_prices: dict[int, float] = {}
            for ts, price in zip(timestamps, prices):
                if price is None or not math.isfinite(price):
                    continue
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                # We want the last available price for each year (e.g. December)
                year_prices[dt.year] = float(price)
                
            return year_prices
        except Exception as exc:
            logger.warning("Failed to fetch price history for %s: %s", ticker, exc)
            return {}

    def _parse_and_validate_raw_csv(
        self, csv_filepath_or_content: str | Path | io.StringIO
    ) -> list[dict[str, Any]]:
        """Parse raw CSV, validating headers and basic numeric types."""
        if isinstance(csv_filepath_or_content, io.StringIO):
            reader = csv.DictReader(csv_filepath_or_content)
        else:
            path = Path(csv_filepath_or_content)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            fh = path.open("r", encoding="utf-8-sig")
            reader = csv.DictReader(fh)

        # Normalize headers to lowercase/stripped
        if reader.fieldnames is None:
            raise ValueError("CSV file contains no headers.")

        fieldnames_normalized = [str(name).strip().lower() for name in reader.fieldnames]

        # Alias mapping helper
        def find_header(*aliases: str) -> str | None:
            for alias in aliases:
                if alias in fieldnames_normalized:
                    # Return the original fieldname (preserving case/etc for reader access)
                    idx = fieldnames_normalized.index(alias)
                    return reader.fieldnames[idx]
            return None

        # Resolve primary required columns
        col_mkt_cap = find_header(
            "market_cap_brl",
            "market_cap",
            "mkt_cap",
            "mktcap",
            "valor_mercado",
            "valor de mercado",
            "marketcapbasic",
            "market_cap_basic",
        )
        col_company_name = find_header(
            "company_name", "company", "name", "nome", "denom_social", "denom_comerc"
        )
        col_ticker = find_header(
            "ticker", "symbol", "code", "codigo", "ticker_b3", "stock"
        )

        if not col_mkt_cap:
            raise ValueError("CSV is missing a market cap column.")
        if not col_company_name and not col_ticker:
            raise ValueError(
                "CSV must contain at least a company name or ticker column."
            )

        # Optional helper columns
        col_as_of = find_header(
            "as_of_date", "as_of", "date", "data", "snapshot_date", "source_date"
        )
        col_rank = find_header("rank", "ranking", "posicao", "market_cap_rank")
        col_cd_cvm = find_header("cd_cvm", "cvm_code", "codigo_cvm", "codigo cvm")
        col_cnpj = find_header("cnpj", "cnpj_cia", "cnpj da empresa")
        col_source = find_header("source", "provider")
        col_method = find_header("method", "metodo")
        col_source_url = find_header("source_url_or_id", "source_url", "source_id")
        col_provider_status = find_header("provider_status", "status_provider", "providerstatus")
        col_notes = find_header("notes", "warnings", "note", "observacoes")
        col_div_yield = find_header("dividend_yield", "dividend_yield_pct", "dividend_yield_percent", "dy", "dividend_yield_ratio")
        col_pe = find_header("pe_ratio", "pe", "p_e", "price_earnings", "price_to_earnings", "p_l", "pl")
        col_pb = find_header("pb_ratio", "pb", "p_b", "price_book", "price_to_book", "p_vp", "pvp")
        col_beta = find_header("beta", "beta_coef", "beta_coefficient")

        parsed_rows: list[dict[str, Any]] = []
        for idx, raw in enumerate(reader, start=1):
            raw_mkt = str(raw.get(col_mkt_cap) or "").strip()
            if not raw_mkt:
                continue

            try:
                # Handle comma decimal separators if any
                cleaned_mkt = (
                    raw_mkt.replace(" ", "")
                    .replace(".", "")
                    .replace(",", ".")
                    if ("," in raw_mkt and "." in raw_mkt)
                    else raw_mkt.replace(",", ".")
                )
                mkt_cap_val = float(cleaned_mkt)
            except ValueError as exc:
                raise ValueError(
                    f"Row {idx}: Invalid market cap numeric format '{raw_mkt}': {exc}"
                ) from exc

            # Parse optional fields
            rank_val = None
            if col_rank and raw.get(col_rank):
                try:
                    rank_val = int(float(str(raw.get(col_rank)).strip()))
                except ValueError:
                    pass

            cd_cvm_val = None
            if col_cd_cvm and raw.get(col_cd_cvm):
                try:
                    cd_cvm_val = int(float(str(raw.get(col_cd_cvm)).strip()))
                except ValueError:
                    pass

            as_of_val = (
                str(raw.get(col_as_of)).strip()
                if col_as_of and raw.get(col_as_of)
                else now_iso_seconds()[:10]
            )

            def _parse_float_or_none(v: Any) -> float | None:
                if v is None:
                    return None
                v_str = str(v).strip()
                if v_str in ("", "None", "null"):
                    return None
                try:
                    return float(v_str)
                except ValueError:
                    return None

            parsed_rows.append(
                {
                    "as_of_date": as_of_val,
                    "rank_raw": rank_val,
                    "cd_cvm_raw": cd_cvm_val,
                    "cnpj_raw": _clean_cnpj(raw.get(col_cnpj)) if col_cnpj else None,
                    "company_name": str(
                        raw.get(col_company_name)
                        if col_company_name
                        else (raw.get(col_ticker) or "")
                    ).strip(),
                    "ticker": _clean_ticker(raw.get(col_ticker))
                    if col_ticker
                    else None,
                    "market_cap_brl": mkt_cap_val,
                    "source": str(
                        (col_source and raw.get(col_source))
                        or "imported_market_cap"
                    ).strip(),
                    "method": str(
                        (col_method and raw.get(col_method)) or "csv_import"
                    ).strip(),
                    "source_url_or_id": str(
                        (col_source_url and raw.get(col_source_url)) or ""
                    ).strip(),
                    "provider_status": str(
                        (col_provider_status and raw.get(col_provider_status))
                        or "unofficial_free"
                    ).strip(),
                    "notes": str((col_notes and raw.get(col_notes)) or "").strip()
                    or None,
                    "dividend_yield": _parse_float_or_none(raw.get(col_div_yield)) if col_div_yield else None,
                    "pe_ratio": _parse_float_or_none(raw.get(col_pe)) if col_pe else None,
                    "pb_ratio": _parse_float_or_none(raw.get(col_pb)) if col_pb else None,
                    "beta": _parse_float_or_none(raw.get(col_beta)) if col_beta else None,
                }
            )

        # Sort by market cap descending to compute implicit ranks if needed
        parsed_rows.sort(key=lambda r: -r["market_cap_brl"])
        for rank_idx, r in enumerate(parsed_rows, start=1):
            if r["rank_raw"] is None:
                r["rank"] = rank_idx
            else:
                r["rank"] = r["rank_raw"]

        return parsed_rows

    def _map_entries(self, raw_rows: list[dict[str, Any]]) -> list[MarketCapEntry]:
        """Perform explicit, audited mapping of raw inputs to CVM catalog identifiers."""
        # Load available CVM catalog companies
        catalog_companies = {}
        if self.read_service:
            try:
                catalog = self.read_service.company_catalog
                catalog_companies = {
                    c.cd_cvm: c for c in catalog.list_entries()
                }
            except Exception as exc:
                logger.warning(
                    "Could not load CVM company catalog for mapping: %s", exc
                )

        mapped_entries: list[MarketCapEntry] = []
        download_stamp = now_iso_seconds()

        # Dictionaries for catalog quick lookups
        catalog_by_ticker: dict[str, Any] = {}
        catalog_by_cnpj: dict[str, Any] = {}
        catalog_by_name: dict[str, Any] = {}

        for c in catalog_companies.values():
            if c.ticker_b3:
                catalog_by_ticker[_clean_ticker(c.ticker_b3)] = c
            if c.cnpj:
                catalog_by_cnpj[_clean_cnpj(c.cnpj)] = c
            name_key = c.company_name.strip().upper()
            if name_key:
                catalog_by_name[name_key] = c
            if c.nome_comercial:
                trade_key = c.nome_comercial.strip().upper()
                if trade_key:
                    catalog_by_name[trade_key] = c

        for row in raw_rows:
            cd_cvm: int | None = row.get("cd_cvm_raw")
            cnpj: str | None = row.get("cnpj_raw")
            ticker: str | None = row.get("ticker")
            company_name: str = row.get("company_name", "")
            notes: str | None = row.get("notes")

            mapping_status = "unmapped"
            mapping_confidence = 0.0

            # 1. Match by CVM code directly
            if cd_cvm and cd_cvm in catalog_companies:
                match = catalog_companies[cd_cvm]
                cd_cvm = match.cd_cvm
                cnpj = match.cnpj or cnpj
                ticker = ticker or match.ticker_b3
                mapping_status = "mapped"
                mapping_confidence = 1.0

            # 2. Match by ticker map
            if mapping_status == "unmapped" and ticker:
                resolver = CompanyIdentityResolver()
                identity = resolver.resolve_by_ticker(ticker)
                if identity and identity.cd_cvm in catalog_companies:
                    match = catalog_companies[identity.cd_cvm]
                    cd_cvm = match.cd_cvm
                    cnpj = match.cnpj or cnpj
                    ticker = ticker or match.ticker_b3
                    mapping_status = "mapped"
                    mapping_confidence = 1.0
                elif ticker in catalog_by_ticker:
                    match = catalog_by_ticker[ticker]
                    cd_cvm = match.cd_cvm
                    cnpj = match.cnpj or cnpj
                    ticker = ticker or match.ticker_b3
                    mapping_status = "mapped"
                    mapping_confidence = 0.95

            # 3. Match by CNPJ
            if mapping_status == "unmapped" and cnpj:
                cleaned_cnpj = _clean_cnpj(cnpj)
                if cleaned_cnpj in catalog_by_cnpj:
                    match = catalog_by_cnpj[cleaned_cnpj]
                    cd_cvm = match.cd_cvm
                    cnpj = match.cnpj or cnpj
                    ticker = ticker or match.ticker_b3
                    mapping_status = "mapped"
                    mapping_confidence = 0.9

            # 4. Match by exact Name
            if mapping_status == "unmapped" and company_name:
                name_key = company_name.strip().upper()
                if name_key in catalog_by_name:
                    match = catalog_by_name[name_key]
                    cd_cvm = match.cd_cvm
                    cnpj = match.cnpj or cnpj
                    ticker = ticker or match.ticker_b3
                    mapping_status = "mapped"
                    mapping_confidence = 0.8

            # Try mapping unmapped ticker using resolver fallback for fallback notes/ticker display
            if cd_cvm and not ticker:
                resolver = CompanyIdentityResolver()
                identity = resolver.resolve(cd_cvm)
                ticker = identity.ticker_b3 if identity else None

            if mapping_status == "unmapped":
                notes_extra = "Unmapped on import"
                notes = (
                    f"{notes} ({notes_extra})"
                    if notes
                    else notes_extra
                )

            mapped_entries.append(
                MarketCapEntry(
                    as_of_date=row["as_of_date"],
                    rank=row["rank"],
                    cd_cvm=cd_cvm,
                    cnpj=cnpj,
                    company_name=company_name,
                    ticker=ticker,
                    market_cap_brl=row["market_cap_brl"],
                    source=row["source"],
                    method=row["method"],
                    source_url_or_id=row["source_url_or_id"],
                    downloaded_at=download_stamp,
                    mapping_status=mapping_status,
                    mapping_confidence=mapping_confidence,
                    notes=notes,
                    provider_status=row.get("provider_status", "unofficial_free"),
                    dividend_yield=row.get("dividend_yield"),
                    pe_ratio=row.get("pe_ratio"),
                    pb_ratio=row.get("pb_ratio"),
                    beta=row.get("beta"),
                )
            )

        return mapped_entries


def _clean_cnpj(val: Any) -> str | None:
    if val in (None, ""):
        return None
    cleaned = "".join(char for char in str(val) if char.isdigit())
    return cleaned or None


def _clean_ticker(val: Any) -> str | None:
    if val in (None, ""):
        return None
    cleaned = str(val).strip().upper()
    if cleaned.startswith("BVMF:"):
        cleaned = cleaned.split(":", 1)[1]
    return cleaned or None
