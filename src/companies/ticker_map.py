"""Mapa canonico cd_cvm -> ticker B3 (Yahoo Finance).

Sem dependencias de framework UI.

STATIC SELECTION HEURISTIC (CONFIGURED PREFERRED TICKERS):
1. Purpose:
   Provide a mapping from a company's unique CVM code (cd_cvm) to its most relevant
   ticker on B3 for financial visualization (e.g. stock price chart, valuation ratios).
2. Selection Rules & Heuristics:
   - Configured Preferred Ticker: The primary ticker is chosen based on a static selection heuristic
     favoring the class historically known to have the highest B3 liquidity.
     - For companies with multiple share classes (e.g. ON, PN, Units), the preferred class
       is selected (e.g. PETR4 for Petrobras, ITUB4 for Itaú, rather than PETR3 or ITUB3).
     - For ON-only companies, the Common Share ticker (ending in 3) is selected (e.g. VALE3, WEGE3).
     - For Unit-centric companies, the Unit ticker (ending in 11) is selected (e.g. KLBN11, BPAC11).
   - Active-Ticker Fallback:
     - Active tickers are associated with companies whose registry status on CVM is active (SIT = "ATIVO").
     - Stale or historical delisted tickers (e.g. EDP Brasil 3697 -> ENBR3.SA) are preserved for historical
       auditing of archived financial statements but are displayed as "historical" in the UI.
     - If a company has no listed ticker or is a closely-held/non-ticker entity (e.g. AEGEA 23396),
       no ticker is mapped (returns None), and the UI displays the empty state gracefully.
3. Limitations:
   - Source: Manually compiled and maintained mapping from historical B3 records and Yahoo Finance listings.
   - Update Process: Requires manual edits to this map file when listings change or new companies are ingested.
   - Authoritative Date: Lacks an authoritative as-of date and does not dynamically query live volume or liquidity data.
"""
from __future__ import annotations
TICKER_MAP: dict[int, str] = {}
REVERSE_TICKER_MAP: dict[str, int] = {}

def load_ticker_map() -> None:
    import csv
    from pathlib import Path
    
    csv_path = Path(__file__).resolve().parent.parent.parent / "data" / "import" / "ticker_map.csv"
    if not csv_path.exists():
        return
        
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    cd_cvm = int(row["cd_cvm"])
                    ticker = row["ticker_b3"].strip()
                    if ticker:
                        TICKER_MAP[cd_cvm] = ticker
                        
                        clean_ticker = ticker.upper()
                        if clean_ticker.endswith(".SA"):
                            clean_ticker = clean_ticker[:-3]
                        REVERSE_TICKER_MAP[clean_ticker] = cd_cvm
                except (ValueError, KeyError):
                    continue
    except Exception:
        pass

load_ticker_map()
