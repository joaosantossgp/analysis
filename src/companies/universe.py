from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import requests
from sqlalchemy import text

from src.platform.settings import AppSettings
from src.companies.identity import CompanyIdentityResolver
from src.companies.market_cap import MarketCapService


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
    "yahoo_finance",
    "local_snapshot",
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
        self.market_cap_service = MarketCapService(settings=settings, read_service=read_service)

    def source_status(self) -> dict[str, Any]:
        status = self.market_cap_service.get_status()
        return {
            "market_cap_source_available": status.get("available", False),
            "market_cap_source": status.get("source"),
            "market_cap_source_date": status.get("as_of_date"),
            "market_cap_snapshot_path": str(self.snapshot_path),
            "market_cap_ranked_companies": status.get("mapped_count", 0),
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
        _resolver = CompanyIdentityResolver()
        for item in getattr(page, "items", ()):
            cd_cvm = _coerce_int(_get(item, "cd_cvm"))
            if cd_cvm is None:
                continue
            identity = _resolver.resolve(cd_cvm)
            ticker = _clean_ticker(_get(item, "ticker_b3") or (identity.ticker_b3 if identity else None))
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
        _resolver = CompanyIdentityResolver()
        for entry in catalog_entries:
            cd_cvm = _coerce_int(getattr(entry, "cd_cvm", None))
            if cd_cvm is None:
                continue
            identity = _resolver.resolve(cd_cvm)
            entries.append(
                CompanyUniverseEntry(
                    cd_cvm=cd_cvm,
                    ticker=_clean_ticker(getattr(entry, "ticker_b3", None) or (identity.ticker_b3 if identity else None)),
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
        try:
            snapshot_entries = self.market_cap_service.read_snapshot()
        except FileNotFoundError as exc:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE) from exc
        except Exception as exc:
            raise CompanyUniverseUnavailableError(f"Error reading snapshot: {exc}") from exc

        rows: list[CompanyUniverseEntry] = []
        for entry in snapshot_entries:
            if entry.cd_cvm is None:
                continue
            rows.append(
                CompanyUniverseEntry(
                    cd_cvm=entry.cd_cvm,
                    ticker=entry.ticker,
                    company_name=entry.company_name,
                    market_cap=entry.market_cap_brl,
                    market_cap_rank=entry.rank,
                    source=entry.source,
                    source_date=entry.as_of_date,
                )
            )
        rows = _dedupe_ranked_rows(rows)
        if not rows:
            raise CompanyUniverseUnavailableError(self.REQUIRED_MARKET_CAP_MESSAGE)
        return rows


# Third-party market-cap provider via live network calls was removed.
# The provider chain now uses only the local snapshot (SnapshotCompanyUniverseProvider).


class CompanyUniverseProviderChain:
    def __init__(self, *, settings: AppSettings, read_service: Any) -> None:
        self.snapshot_provider = SnapshotCompanyUniverseProvider(
            settings=settings,
            read_service=read_service,
        )
        self.market_cap_providers = (
            self.snapshot_provider,
        )

    def source_status(self) -> dict[str, Any]:
        snapshot_raw = self.snapshot_provider.source_status()
        
        provider_name = self.snapshot_provider.settings.market_cap_provider
        # Normalize alias: 'yfinance' -> 'yahoo_finance'
        is_yahoo = provider_name in ("yahoo_finance", "yfinance")
        
        provider_status = []
        
        # Local snapshot entry
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
        provider_status.append(snapshot_status)
        
        # Yahoo Finance provider status entry
        yahoo_finance_status = {
            "provider": "yahoo_finance",
            "configured": is_yahoo,
            "available": is_yahoo,
            "source": "yahoo_finance" if is_yahoo else None,
            "source_date": snapshot_raw.get("market_cap_source_date") if is_yahoo else None,
            "ranked_companies": snapshot_raw.get("market_cap_ranked_companies", 0) if is_yahoo else 0,
            "message": "Yahoo Finance is configured as the main automatic free provider (unofficial)."
            if is_yahoo
            else "Configure CVM_MARKET_CAP_PROVIDER=yahoo_finance to enable automatic refresh.",
        }
        provider_status.append(yahoo_finance_status)
        
        # Fallback/All Companies
        all_status = {
            "provider": "all_companies",
            "configured": True,
            "available": True,
            "source": "cvm_company_catalog",
            "source_date": None,
            "ranked_companies": None,
            "message": "Manual fallback uses all companies from the CVM company catalog.",
        }
        provider_status.append(all_status)
        
        first_available = None
        if is_yahoo and snapshot_raw.get("market_cap_source_available"):
            first_available = yahoo_finance_status
        elif snapshot_raw.get("market_cap_source_available"):
            first_available = snapshot_status
            
        return {
            "market_cap_source_available": snapshot_raw.get("market_cap_source_available"),
            "market_cap_source": snapshot_raw.get("market_cap_source"),
            "market_cap_source_date": snapshot_raw.get("market_cap_source_date"),
            "market_cap_snapshot_path": snapshot_raw.get("market_cap_snapshot_path"),
            "market_cap_ranked_companies": snapshot_raw.get("market_cap_ranked_companies", 0),
            "company_universe_provider_order": ["yahoo_finance", "local_snapshot", "all_companies"] if is_yahoo else ["local_snapshot", "all_companies"],
            "company_universe_provider_status": provider_status,
            # Kept for backward compat: frontend types.ts still has this field
            "yfinance_universe_provider_enabled": is_yahoo,
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

    def get_company_universe_by_preset(
        self,
        preset: CompanyUniversePreset,
        *,
        refresh_catalog: bool = False,
    ) -> CompanyUniverseSelection:
        if refresh_catalog:
            if preset not in SUPPORTED_PRESETS:
                raise ValueError(f"Unsupported company universe preset: {preset}")
            self.read_service.company_catalog.refresh()
            self.read_service.invalidate_read_caches()
        return self.provider.get_company_universe_by_preset(preset)


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
        "Market cap ranking source is unavailable. "
        "Fetch market caps from Yahoo Finance (unofficial), "
        f"place a versioned local snapshot at {snapshot_path}, "
        "or choose All B3 companies."
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
