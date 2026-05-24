from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import requests
from sqlalchemy import inspect, text

from src.settings import AppSettings
from src.ticker_map import REVERSE_TICKER_MAP, TICKER_MAP
from src.utils import now_iso_seconds

try:
    import yfinance as yf

    _YF_AVAILABLE = True
except ImportError:
    yf = None
    _YF_AVAILABLE = False

CompanyUniversePreset = Literal["top_100", "top_200", "top_500", "all"]

SUPPORTED_PRESETS: tuple[CompanyUniversePreset, ...] = (
    "top_100",
    "top_200",
    "top_500",
    "all",
)

PRESET_LIMITS: dict[CompanyUniversePreset, int | None] = {
    "top_100": 100,
    "top_200": 200,
    "top_500": 500,
    "all": None,
}

MARKET_CAP_PROVIDER_ORDER: tuple[str, ...] = (
    "brapi",
    "local_snapshot",
    "yfinance_experimental",
    "all_companies",
)


class CompanyUniverseUnavailableError(RuntimeError):
    """Raised when a preset cannot be resolved from configured sources."""


@dataclass(frozen=True)
class CompanyUniverseEntry:
    cd_cvm: int
    ticker: str | None
    company_name: str
    market_cap: float | None
    market_cap_rank: int | None
    source: str
    source_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cd_cvm": int(self.cd_cvm),
            "ticker": self.ticker,
            "company_name": self.company_name,
            "market_cap": self.market_cap,
            "market_cap_rank": self.market_cap_rank,
            "source": self.source,
            "source_date": self.source_date,
        }


@dataclass(frozen=True)
class CompanyUniverseSelection:
    preset: CompanyUniversePreset
    entries: tuple[CompanyUniverseEntry, ...]
    source: str
    source_date: str | None
    warning: str | None = None

    @property
    def company_ids(self) -> tuple[int, ...]:
        return tuple(int(row.cd_cvm) for row in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "selected_count": len(self.entries),
            "company_ids": list(self.company_ids),
            "source": self.source,
            "source_date": self.source_date,
            "warning": self.warning,
            "companies": [row.to_dict() for row in self.entries],
        }


def ensure_company_universe_tables_for_connection(conn: Any) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS company_universe (
                cd_cvm INTEGER NOT NULL,
                ticker TEXT,
                company_name TEXT NOT NULL,
                market_cap REAL,
                market_cap_rank INTEGER,
                source TEXT NOT NULL,
                source_date TEXT,
                selected_preset TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (selected_preset, cd_cvm)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_company_universe_preset_rank
            ON company_universe(selected_preset, market_cap_rank)
            """
        )
    )


class SnapshotCompanyUniverseProvider:
    """Resolves B3 company universes from an explicit local market-cap snapshot."""

    REQUIRED_MARKET_CAP_MESSAGE = (
        "Market cap ranking source is unavailable. Add a versioned snapshot at "
        "data/metadata/b3_market_cap_universe_snapshot.csv or set "
        "CVM_COMPANY_UNIVERSE_SNAPSHOT_PATH."
    )

    def __init__(self, *, settings: AppSettings, read_service: Any) -> None:
        self.settings = settings
        self.read_service = read_service
        self.snapshot_path = Path(settings.paths.company_universe_snapshot_path)

    def source_status(self) -> dict[str, Any]:
        if not self.snapshot_path.exists():
            return {
                "market_cap_source_available": False,
                "market_cap_source": None,
                "market_cap_source_date": None,
                "market_cap_snapshot_path": str(self.snapshot_path),
            }
        try:
            rows = self._read_snapshot_rows()
        except CompanyUniverseUnavailableError:
            rows = []
        source = rows[0].source if rows else "local_snapshot"
        source_date = rows[0].source_date if rows else None
        return {
            "market_cap_source_available": bool(rows),
            "market_cap_source": source,
            "market_cap_source_date": source_date,
            "market_cap_snapshot_path": str(self.snapshot_path),
            "market_cap_ranked_companies": len(rows),
        }

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
    ) -> CompanyUniverseSelection:
        if preset not in SUPPORTED_PRESETS:
            raise ValueError(f"Unsupported company universe preset: {preset}")

        if preset == "all":
            entries = tuple(self.get_available_companies())
            if not entries:
                raise CompanyUniverseUnavailableError(
                    "No B3 companies are available from the local catalog or CVM company registry."
                )
            return CompanyUniverseSelection(
                preset=preset,
                entries=entries,
                source="cvm_company_catalog",
                source_date=None,
            )

        limit = PRESET_LIMITS[preset]
        assert limit is not None
        ranked_rows = self._read_snapshot_rows()
        resolved_rows = self.resolve_company_identifiers(ranked_rows)
        if not resolved_rows:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)

        selected = tuple(resolved_rows[:limit])
        warning = None
        if len(selected) < limit:
            warning = (
                f"Only {len(selected)} valid ranked companies are available; "
                f"selected all available companies for {preset}."
            )
        source = selected[0].source if selected else "local_snapshot"
        source_date = selected[0].source_date if selected else None
        return CompanyUniverseSelection(
            preset=preset,
            entries=selected,
            source=source,
            source_date=source_date,
            warning=warning,
        )

    def get_available_companies(self) -> list[CompanyUniverseEntry]:
        try:
            page = self.read_service.list_companies(
                search="",
                sector_slug=None,
                page=1,
                page_size=10_000,
            )
        except Exception:
            return self._get_available_companies_from_catalog()
        entries: list[CompanyUniverseEntry] = []
        for item in getattr(page, "items", ()):
            cd_cvm = _coerce_int(_get(item, "cd_cvm"))
            if cd_cvm is None:
                continue
            ticker = _clean_ticker(_get(item, "ticker_b3") or TICKER_MAP.get(cd_cvm))
            entries.append(
                CompanyUniverseEntry(
                    cd_cvm=cd_cvm,
                    ticker=ticker,
                    company_name=str(_get(item, "company_name") or f"CVM {cd_cvm}"),
                    market_cap=None,
                    market_cap_rank=None,
                    source="cvm_company_catalog",
                    source_date=None,
                )
            )
        return entries

    def _get_available_companies_from_catalog(self) -> list[CompanyUniverseEntry]:
        try:
            catalog = getattr(self.read_service, "company_catalog")
            catalog_entries = [entry for entry in catalog.list_entries() if entry.is_active]
        except Exception:
            return []

        entries: list[CompanyUniverseEntry] = []
        for entry in catalog_entries:
            cd_cvm = _coerce_int(getattr(entry, "cd_cvm", None))
            if cd_cvm is None:
                continue
            entries.append(
                CompanyUniverseEntry(
                    cd_cvm=cd_cvm,
                    ticker=_clean_ticker(getattr(entry, "ticker_b3", None) or TICKER_MAP.get(cd_cvm)),
                    company_name=str(getattr(entry, "company_name", None) or f"CVM {cd_cvm}"),
                    market_cap=None,
                    market_cap_rank=None,
                    source="cvm_company_catalog",
                    source_date=None,
                )
            )
        entries.sort(key=lambda row: row.company_name.upper())
        return entries

    def resolve_company_identifiers(
        self,
        rows: list[CompanyUniverseEntry],
    ) -> list[CompanyUniverseEntry]:
        available_by_code = {
            int(row.cd_cvm): row
            for row in self.get_available_companies()
        }
        resolved: list[CompanyUniverseEntry] = []
        seen: set[int] = set()
        for row in rows:
            available = available_by_code.get(int(row.cd_cvm))
            if available is None or int(row.cd_cvm) in seen:
                continue
            seen.add(int(row.cd_cvm))
            resolved.append(
                CompanyUniverseEntry(
                    cd_cvm=int(row.cd_cvm),
                    ticker=row.ticker or available.ticker,
                    company_name=available.company_name or row.company_name,
                    market_cap=row.market_cap,
                    market_cap_rank=row.market_cap_rank,
                    source=row.source,
                    source_date=row.source_date,
                )
            )
        resolved.sort(
            key=lambda row: (
                row.market_cap_rank is None,
                int(row.market_cap_rank or 999_999),
                -float(row.market_cap or 0.0),
                row.company_name.upper(),
            )
        )
        return resolved

    def _read_snapshot_rows(self) -> list[CompanyUniverseEntry]:
        if not self.snapshot_path.exists():
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)

        rows: list[CompanyUniverseEntry] = []
        with self.snapshot_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                normalized = {
                    str(key or "").strip().lower(): value
                    for key, value in dict(raw).items()
                }
                ticker = _clean_ticker(
                    _first(normalized, "ticker", "ticker_b3", "symbol", "codigo")
                )
                cd_cvm = _coerce_int(_first(normalized, "cd_cvm", "cvm_code", "codigo_cvm"))
                if cd_cvm is None and ticker:
                    cd_cvm = REVERSE_TICKER_MAP.get(ticker.replace(".SA", "").upper())
                if cd_cvm is None:
                    continue

                market_cap = _coerce_float(
                    _first(normalized, "market_cap", "mktcap", "valor_mercado")
                )
                rank = _coerce_int(
                    _first(normalized, "market_cap_rank", "rank", "ranking")
                )
                source = str(
                    _first(normalized, "source", "provider") or "local_market_cap_snapshot"
                ).strip()
                source_date = _clean_optional(
                    _first(normalized, "source_date", "snapshot_date", "as_of")
                )
                rows.append(
                    CompanyUniverseEntry(
                        cd_cvm=int(cd_cvm),
                        ticker=ticker or _clean_ticker(TICKER_MAP.get(int(cd_cvm))),
                        company_name=str(
                            _first(normalized, "company_name", "name", "nome") or f"CVM {cd_cvm}"
                        ),
                        market_cap=market_cap,
                        market_cap_rank=rank,
                        source=source,
                        source_date=source_date,
                    )
                )

        rows = _dedupe_ranked_rows(rows)
        if not rows:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)
        return rows


class BrapiCompanyUniverseProvider(SnapshotCompanyUniverseProvider):
    """Resolves B3 market-cap ranking through the documented brapi quote list API."""

    SOURCE_NAME = "brapi_quote_list"
    REQUIRED_MARKET_CAP_MESSAGE = (
        "brapi market cap ranking is unavailable. Set BRAPI_TOKEN or CVM_BRAPI_TOKEN, "
        "or provide a local market-cap snapshot fallback."
    )

    def source_status(self) -> dict[str, Any]:
        configured = bool(self.settings.brapi_token)
        return {
            "provider": "brapi",
            "configured": configured,
            "available": configured,
            "source": self.SOURCE_NAME if configured else None,
            "source_date": None,
            "message": None if configured else "Set BRAPI_TOKEN to enable brapi market-cap ranking.",
        }

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
    ) -> CompanyUniverseSelection:
        if preset == "all":
            return super().get_company_universe_by_preset(preset)
        if not self.settings.brapi_token:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)

        ranked_rows = self._read_brapi_rows()
        resolved_rows = self.resolve_company_identifiers(ranked_rows)
        if not resolved_rows:
            raise CompanyUniverseUnavailableError(
                "brapi did not return ranked companies that match the local CVM catalog."
            )
        return _selection_from_ranked_rows(
            preset=preset,
            resolved_rows=resolved_rows,
            source_fallback=self.SOURCE_NAME,
        )

    def _read_brapi_rows(self) -> list[CompanyUniverseEntry]:
        if not self.settings.brapi_token:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)

        base_url = str(self.settings.brapi_base_url or "https://brapi.dev/api").rstrip("/")
        url = f"{base_url}/quote/list"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.settings.brapi_token}",
        }
        params = {
            "sortBy": "market_cap_basic",
            "sortOrder": "desc",
            "type": "stock",
        }
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=int(self.settings.brapi_timeout),
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise CompanyUniverseUnavailableError(
                f"brapi market cap ranking is unavailable: {exc}"
            ) from exc

        if isinstance(payload, dict):
            stocks = payload.get("stocks")
        elif isinstance(payload, list):
            stocks = payload
        else:
            stocks = None
        if not isinstance(stocks, list):
            raise CompanyUniverseUnavailableError(
                "brapi market cap ranking response did not include a stocks list."
            )

        source_date = now_iso_seconds()[:10]
        rows: list[CompanyUniverseEntry] = []
        for raw in stocks:
            if not isinstance(raw, dict):
                continue
            normalized = {
                str(key or "").strip().lower(): value
                for key, value in raw.items()
            }
            ticker = _clean_ticker(
                _first(normalized, "stock", "ticker", "symbol", "code")
            )
            if not ticker:
                continue
            cd_cvm = REVERSE_TICKER_MAP.get(_ticker_lookup_key(ticker))
            if cd_cvm is None:
                continue
            market_cap = _coerce_float(
                _first(
                    normalized,
                    "market_cap_basic",
                    "marketcapbasic",
                    "market_cap",
                    "marketcap",
                    "market_capitalization",
                    "marketcapitalization",
                )
            )
            if market_cap is None or market_cap <= 0:
                continue
            rows.append(
                CompanyUniverseEntry(
                    cd_cvm=int(cd_cvm),
                    ticker=ticker,
                    company_name=str(
                        _first(
                            normalized,
                            "company_name",
                            "companyname",
                            "name",
                            "longname",
                            "shortname",
                        )
                        or f"CVM {cd_cvm}"
                    ),
                    market_cap=market_cap,
                    market_cap_rank=_coerce_int(
                        _first(normalized, "market_cap_rank", "rank", "ranking")
                    ),
                    source=self.SOURCE_NAME,
                    source_date=source_date,
                )
            )

        rows = _dedupe_ranked_rows(rows)
        if not rows:
            raise CompanyUniverseUnavailableError(
                "brapi market cap ranking did not include usable B3 companies."
            )
        return rows


class YFinanceCompanyUniverseProvider(SnapshotCompanyUniverseProvider):
    """Experimental market-cap fallback for personal/dev use."""

    SOURCE_NAME = "yfinance_experimental"
    REQUIRED_MARKET_CAP_MESSAGE = (
        "yfinance market cap fallback is disabled. Set "
        "CVM_ENABLE_YFINANCE_UNIVERSE_PROVIDER=true for personal/dev use."
    )

    def source_status(self) -> dict[str, Any]:
        cache_rows = self._cached_market_cap_count()
        enabled = bool(self.settings.enable_yfinance_universe_provider)
        return {
            "provider": self.SOURCE_NAME,
            "configured": enabled,
            "available": enabled and (_YF_AVAILABLE or cache_rows > 0),
            "source": self.SOURCE_NAME if enabled else None,
            "source_date": None,
            "ranked_companies": cache_rows,
            "message": None
            if enabled
            else "Enable only for personal/dev use with CVM_ENABLE_YFINANCE_UNIVERSE_PROVIDER.",
        }

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
    ) -> CompanyUniverseSelection:
        if preset == "all":
            return super().get_company_universe_by_preset(preset)
        if not self.settings.enable_yfinance_universe_provider:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)

        ranked_rows = self._read_yfinance_rows()
        resolved_rows = self.resolve_company_identifiers(ranked_rows)
        if not resolved_rows:
            raise CompanyUniverseUnavailableError(
                "yfinance fallback did not return market caps that match the local CVM catalog."
            )
        return _selection_from_ranked_rows(
            preset=preset,
            resolved_rows=resolved_rows,
            source_fallback=self.SOURCE_NAME,
        )

    def _read_yfinance_rows(self) -> list[CompanyUniverseEntry]:
        cache = self._load_market_cache()
        rows: list[CompanyUniverseEntry] = []
        fetch_budget = max(0, int(self.settings.yfinance_universe_fetch_limit))
        cache_updated = False

        for available in self.get_available_companies():
            ticker = _clean_ticker(available.ticker or TICKER_MAP.get(int(available.cd_cvm)))
            if not ticker:
                continue
            yahoo_ticker = _to_yfinance_ticker(ticker)
            snapshot = self._snapshot_from_cache(cache, yahoo_ticker)
            if snapshot is None:
                snapshot = self._snapshot_from_cache(cache, _ticker_lookup_key(ticker))

            if snapshot is None and fetch_budget > 0:
                snapshot = self._fetch_online_market_cap(yahoo_ticker)
                if snapshot is not None:
                    fetch_budget -= 1
                    cache_updated = True
                    previous = cache.get(yahoo_ticker)
                    if isinstance(previous, dict):
                        previous.update(snapshot)
                        cache[yahoo_ticker] = previous
                    else:
                        cache[yahoo_ticker] = snapshot

            market_cap = _coerce_float(_get(snapshot, "mktcap") if snapshot else None)
            if market_cap is None:
                market_cap = _coerce_float(_get(snapshot, "market_cap") if snapshot else None)
            if market_cap is None or market_cap <= 0:
                continue

            fetched_at = _clean_optional(_get(snapshot, "fetched_at") if snapshot else None)
            rows.append(
                CompanyUniverseEntry(
                    cd_cvm=int(available.cd_cvm),
                    ticker=ticker,
                    company_name=available.company_name,
                    market_cap=market_cap,
                    market_cap_rank=None,
                    source=self.SOURCE_NAME,
                    source_date=fetched_at[:10] if fetched_at else None,
                )
            )

        if cache_updated:
            self._save_market_cache(cache)

        rows = _dedupe_ranked_rows(rows)
        if not rows:
            raise CompanyUniverseUnavailableError(
                "yfinance fallback has no usable market cap data. Add cache data, allow a dev fetch, "
                "or use brapi/local snapshot instead."
            )
        return rows

    def _load_market_cache(self) -> dict[str, Any]:
        path = Path(self.settings.paths.yfinance_cache_path)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_market_cache(self, cache: dict[str, Any]) -> None:
        path = Path(self.settings.paths.yfinance_cache_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cache, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _snapshot_from_cache(
        self,
        cache: dict[str, Any],
        ticker: str,
    ) -> dict[str, Any] | None:
        entry = cache.get(ticker)
        if not isinstance(entry, dict):
            return None
        market_cap = _coerce_float(
            entry.get("mktcap")
            or entry.get("market_cap")
            or entry.get("marketCap")
        )
        if market_cap is None or market_cap <= 0:
            return None
        return {
            **entry,
            "mktcap": market_cap,
        }

    def _cached_market_cap_count(self) -> int:
        cache = self._load_market_cache()
        count = 0
        for value in cache.values():
            if not isinstance(value, dict):
                continue
            market_cap = _coerce_float(
                value.get("mktcap")
                or value.get("market_cap")
                or value.get("marketCap")
            )
            if market_cap is not None and market_cap > 0:
                count += 1
        return count

    def _fetch_online_market_cap(self, ticker: str) -> dict[str, Any] | None:
        if not _YF_AVAILABLE or yf is None:
            return None
        try:
            ticker_obj = yf.Ticker(ticker)
            fast_info = getattr(ticker_obj, "fast_info", None) or {}
            market_cap = _coerce_float(_get(fast_info, "market_cap"))
            if market_cap is None or market_cap <= 0:
                info = getattr(ticker_obj, "info", None) or {}
                market_cap = _coerce_float(
                    _get(info, "marketCap") or _get(info, "market_cap")
                )
            if market_cap is None or market_cap <= 0:
                return None
            return {
                "mktcap": market_cap,
                "fetched_at": now_iso_seconds(),
                "source": self.SOURCE_NAME,
            }
        except Exception:
            return None


class CompanyUniverseProviderChain:
    def __init__(self, *, settings: AppSettings, read_service: Any) -> None:
        self.brapi_provider = BrapiCompanyUniverseProvider(
            settings=settings,
            read_service=read_service,
        )
        self.snapshot_provider = SnapshotCompanyUniverseProvider(
            settings=settings,
            read_service=read_service,
        )
        self.yfinance_provider = YFinanceCompanyUniverseProvider(
            settings=settings,
            read_service=read_service,
        )
        self.market_cap_providers = (
            self.brapi_provider,
            self.snapshot_provider,
            self.yfinance_provider,
        )

    def source_status(self) -> dict[str, Any]:
        brapi_status = self.brapi_provider.source_status()
        snapshot_raw = self.snapshot_provider.source_status()
        yfinance_status = self.yfinance_provider.source_status()
        snapshot_status = {
            "provider": "local_snapshot",
            "configured": self.snapshot_provider.snapshot_path.exists(),
            "available": bool(snapshot_raw.get("market_cap_source_available")),
            "source": snapshot_raw.get("market_cap_source"),
            "source_date": snapshot_raw.get("market_cap_source_date"),
            "ranked_companies": snapshot_raw.get("market_cap_ranked_companies", 0),
            "message": None
            if snapshot_raw.get("market_cap_source_available")
            else "Add a local market-cap snapshot to enable offline Top N presets.",
        }
        all_status = {
            "provider": "all_companies",
            "configured": True,
            "available": True,
            "source": "cvm_company_catalog",
            "source_date": None,
            "ranked_companies": None,
            "message": "Manual fallback uses all companies from the CVM company catalog.",
        }
        provider_status = [
            brapi_status,
            snapshot_status,
            yfinance_status,
            all_status,
        ]
        first_available = next(
            (
                status
                for status in (brapi_status, snapshot_status, yfinance_status)
                if bool(status.get("available"))
            ),
            None,
        )
        return {
            "market_cap_source_available": first_available is not None,
            "market_cap_source": first_available.get("source") if first_available else None,
            "market_cap_source_date": first_available.get("source_date") if first_available else None,
            "market_cap_snapshot_path": snapshot_raw.get("market_cap_snapshot_path"),
            "market_cap_ranked_companies": first_available.get("ranked_companies")
            if first_available
            else 0,
            "company_universe_provider_order": list(MARKET_CAP_PROVIDER_ORDER),
            "company_universe_provider_status": provider_status,
            "brapi_configured": bool(brapi_status.get("configured")),
            "yfinance_universe_provider_enabled": bool(yfinance_status.get("configured")),
        }

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
    ) -> CompanyUniverseSelection:
        if preset not in SUPPORTED_PRESETS:
            raise ValueError(f"Unsupported company universe preset: {preset}")

        if preset == "all":
            return self.snapshot_provider.get_company_universe_by_preset(preset)

        provider_errors: list[str] = []
        for provider in self.market_cap_providers:
            try:
                return provider.get_company_universe_by_preset(preset)
            except CompanyUniverseUnavailableError as exc:
                provider_errors.append(f"{provider.__class__.__name__}: {exc}")
            except Exception as exc:
                provider_errors.append(f"{provider.__class__.__name__}: {exc}")

        raise CompanyUniverseUnavailableError(
            _market_cap_unavailable_message(
                snapshot_path=self.snapshot_provider.snapshot_path,
                provider_errors=provider_errors,
            )
        )

    def get_available_companies(self) -> list[CompanyUniverseEntry]:
        return self.snapshot_provider.get_available_companies()

    def resolve_company_identifiers(
        self,
        rows: list[CompanyUniverseEntry],
    ) -> list[CompanyUniverseEntry]:
        return self.snapshot_provider.resolve_company_identifiers(rows)


class CompanyUniverseService:
    def __init__(self, *, settings: AppSettings, read_service: Any) -> None:
        self.settings = settings
        self.read_service = read_service
        self.engine = read_service.engine
        self.provider = CompanyUniverseProviderChain(
            settings=settings,
            read_service=read_service,
        )
        self.state_path = Path(settings.paths.onboarding_state_path)

    def get_onboarding_state(self) -> dict[str, Any]:
        state = self._read_state()
        has_local_data = self._has_local_financial_data()
        source_status = self.provider.source_status()
        if not state:
            return {
                "first_run_completed": bool(has_local_data),
                "should_show": not has_local_data,
                "selected_company_universe": None,
                "company_universe_source": None,
                "company_universe_source_date": None,
                "setup_status": "existing_data" if has_local_data else "not_started",
                "selected_company_count": 0,
                "refresh_job_id": None,
                "warning": None,
                "has_local_financial_data": bool(has_local_data),
                **source_status,
            }

        first_run_completed = bool(state.get("first_run_completed"))
        return {
            "first_run_completed": first_run_completed,
            "should_show": not first_run_completed,
            "selected_company_universe": state.get("selected_company_universe"),
            "company_universe_source": state.get("company_universe_source"),
            "company_universe_source_date": state.get("company_universe_source_date"),
            "setup_status": state.get("setup_status") or "not_started",
            "selected_company_count": int(state.get("selected_company_count") or 0),
            "refresh_job_id": state.get("refresh_job_id"),
            "warning": state.get("warning"),
            "has_local_financial_data": bool(has_local_data),
            **source_status,
        }

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
    ) -> CompanyUniverseSelection:
        return self.provider.get_company_universe_by_preset(preset)

    def mark_setup_started(
        self,
        selection: CompanyUniverseSelection,
        *,
        refresh_job_id: str | None,
    ) -> None:
        self._persist_selection(selection)
        payload = {
            "first_run_completed": False,
            "selected_company_universe": selection.preset,
            "company_universe_source": selection.source,
            "company_universe_source_date": selection.source_date,
            "setup_status": "running",
            "selected_company_count": len(selection.entries),
            "refresh_job_id": refresh_job_id,
            "warning": selection.warning,
            "updated_at": now_iso_seconds(),
        }
        self._write_state(payload)
        self._write_app_settings(payload)

    def mark_setup_completed(self, *, status: str = "success") -> dict[str, Any]:
        state = self._read_state()
        state.update(
            {
                "first_run_completed": True,
                "setup_status": status,
                "completed_at": now_iso_seconds(),
                "updated_at": now_iso_seconds(),
            }
        )
        self._write_state(state)
        self._write_app_settings(state)
        return self.get_onboarding_state()

    def skip_setup(self) -> dict[str, Any]:
        payload = {
            "first_run_completed": True,
            "selected_company_universe": None,
            "company_universe_source": "configure_later",
            "company_universe_source_date": None,
            "setup_status": "skipped",
            "selected_company_count": 0,
            "refresh_job_id": None,
            "warning": None,
            "completed_at": now_iso_seconds(),
            "updated_at": now_iso_seconds(),
        }
        self._write_state(payload)
        self._write_app_settings(payload)
        return self.get_onboarding_state()

    def _persist_selection(self, selection: CompanyUniverseSelection) -> None:
        self._ensure_schema()
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM company_universe WHERE selected_preset = :preset"),
                {"preset": selection.preset},
            )
            for entry in selection.entries:
                conn.execute(
                    text(
                        """
                        INSERT INTO company_universe (
                            cd_cvm, ticker, company_name, market_cap, market_cap_rank,
                            source, source_date, selected_preset, created_at, updated_at
                        ) VALUES (
                            :cd_cvm, :ticker, :company_name, :market_cap, :market_cap_rank,
                            :source, :source_date, :selected_preset, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "cd_cvm": int(entry.cd_cvm),
                        "ticker": entry.ticker,
                        "company_name": entry.company_name,
                        "market_cap": entry.market_cap,
                        "market_cap_rank": entry.market_cap_rank,
                        "source": entry.source,
                        "source_date": entry.source_date,
                        "selected_preset": selection.preset,
                        "created_at": now,
                        "updated_at": now,
                    },
                )

    def _write_app_settings(self, payload: dict[str, Any]) -> None:
        self._ensure_schema()
        keys = {
            "first_run_completed": payload.get("first_run_completed"),
            "selected_company_universe": payload.get("selected_company_universe"),
            "company_universe_source": payload.get("company_universe_source"),
            "company_universe_source_date": payload.get("company_universe_source_date"),
            "download_status": payload.get("setup_status"),
            "refresh_job_id": payload.get("refresh_job_id"),
        }
        now = now_iso_seconds()
        with self.engine.begin() as conn:
            for key, value in keys.items():
                conn.execute(text("DELETE FROM app_settings WHERE key = :key"), {"key": key})
                conn.execute(
                    text(
                        """
                        INSERT INTO app_settings (key, value, updated_at)
                        VALUES (:key, :value, :updated_at)
                        """
                    ),
                    {
                        "key": key,
                        "value": json.dumps(value, ensure_ascii=True),
                        "updated_at": now,
                    },
                )

    def _ensure_schema(self) -> None:
        if not self.settings.database_url:
            Path(self.settings.paths.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.engine.begin() as conn:
            ensure_company_universe_tables_for_connection(conn)

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}

    def _write_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _has_local_financial_data(self) -> bool:
        if not self.settings.database_url and not Path(self.settings.paths.db_path).exists():
            return False
        try:
            inspector = inspect(self.engine)
            if not inspector.has_table("financial_reports"):
                return False
            with self.engine.connect() as conn:
                count = conn.execute(
                    text('SELECT COUNT(*) FROM "financial_reports"')
                ).scalar()
            return int(count or 0) > 0
        except Exception:
            return False


def _dedupe_ranked_rows(rows: list[CompanyUniverseEntry]) -> list[CompanyUniverseEntry]:
    if not rows:
        return []
    ranked = sorted(
        rows,
        key=lambda row: (
            row.market_cap_rank is None,
            int(row.market_cap_rank or 999_999),
            -float(row.market_cap or 0.0),
            row.company_name.upper(),
        ),
    )
    deduped: list[CompanyUniverseEntry] = []
    seen: set[int] = set()
    for idx, row in enumerate(ranked, start=1):
        if int(row.cd_cvm) in seen:
            continue
        seen.add(int(row.cd_cvm))
        rank = row.market_cap_rank if row.market_cap_rank is not None else idx
        deduped.append(
            CompanyUniverseEntry(
                cd_cvm=row.cd_cvm,
                ticker=row.ticker,
                company_name=row.company_name,
                market_cap=row.market_cap,
                market_cap_rank=rank,
                source=row.source,
                source_date=row.source_date,
            )
        )
    deduped.sort(key=lambda row: int(row.market_cap_rank or 999_999))
    return deduped


def _selection_from_ranked_rows(
    *,
    preset: CompanyUniversePreset,
    resolved_rows: list[CompanyUniverseEntry],
    source_fallback: str,
) -> CompanyUniverseSelection:
    limit = PRESET_LIMITS[preset]
    if limit is None:
        return CompanyUniverseSelection(
            preset=preset,
            entries=tuple(resolved_rows),
            source=source_fallback,
            source_date=None,
        )
    selected = tuple(resolved_rows[:limit])
    warning = None
    if len(selected) < limit:
        warning = (
            f"Only {len(selected)} valid ranked companies are available; "
            f"selected all available companies for {preset}."
        )
    source = selected[0].source if selected else source_fallback
    source_date = selected[0].source_date if selected else None
    return CompanyUniverseSelection(
        preset=preset,
        entries=selected,
        source=source,
        source_date=source_date,
        warning=warning,
    )


def _market_cap_unavailable_message(
    *,
    snapshot_path: Path,
    provider_errors: list[str],
) -> str:
    details = "; ".join(provider_errors[:3])
    suffix = f" Details: {details}" if details else ""
    return (
        "Market cap ranking source is unavailable. Configure BRAPI_TOKEN, add a "
        f"versioned local snapshot at {snapshot_path}, enable the yfinance fallback "
        "only for personal/dev use, or choose All B3 companies."
        f"{suffix}"
    )


def _get(item: Any, field: str) -> Any:
    if isinstance(item, dict):
        return item.get(field)
    getter = getattr(item, "get", None)
    if callable(getter):
        try:
            return getter(field)
        except Exception:
            pass
    return getattr(item, field, None)


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _clean_optional(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text_value = str(value).strip()
    return text_value or None


def _clean_ticker(value: Any) -> str | None:
    cleaned = _clean_optional(value)
    if cleaned is None:
        return None
    cleaned = cleaned.upper()
    if cleaned.startswith("BVMF:"):
        cleaned = cleaned.split(":", 1)[1]
    return cleaned


def _ticker_lookup_key(ticker: str) -> str:
    return ticker.replace(".SA", "").upper()


def _to_yfinance_ticker(ticker: str) -> str:
    cleaned = _clean_ticker(ticker) or ticker
    if "." in cleaned:
        return cleaned
    return f"{cleaned}.SA"


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    raw = str(value).strip().replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None
