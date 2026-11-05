from __future__ import annotations

import io
import json
import logging
import tempfile
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from src.companies.ticker_map import TICKER_MAP
from src.platform.settings import get_settings

logger = logging.getLogger(__name__)

CVM_MASTER_URL = os.environ.get(
    "CVM_CATALOG_URL",
    "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
)
ACTIVE_STATUS_VALUES = {"ATIVO", "A"}
DEFAULT_CATALOG_TTL_SECONDS = 900


class CompanyCatalogUnavailableError(RuntimeError):
    """Raised when local catalog evidence or an explicit refresh is unavailable."""


def _normalize_display_ticker(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().upper()
    if normalized.endswith(".SA"):
        normalized = normalized[:-3]
    return normalized or None


@dataclass(frozen=True)
class CompanyCatalogEntry:
    cd_cvm: int
    company_name: str
    nome_comercial: str | None
    cnpj: str | None
    setor_cvm: str | None
    ticker_b3: str | None
    is_active: bool


@dataclass(frozen=True)
class CompanyCatalogSnapshot:
    entries: tuple[CompanyCatalogEntry, ...]
    by_cd_cvm: dict[int, CompanyCatalogEntry]


class CompanyCatalogService:
    def __init__(
        self,
        *,
        timeout: int,
        ttl_seconds: int = DEFAULT_CATALOG_TTL_SECONDS,
        snapshot_path: Path | None = None,
    ) -> None:
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else (
            get_settings().paths.metadata_dir / "cvm_company_catalog.json"
        )
        self.timeout = int(timeout)
        self.ttl_seconds = int(ttl_seconds)
        self._cache_lock = threading.Lock()
        self._cached_snapshot: CompanyCatalogSnapshot | None = None
        self._cached_at = 0.0

    def lookup_company(self, cd_cvm: int) -> CompanyCatalogEntry | None:
        snapshot = self._load_snapshot()
        return snapshot.by_cd_cvm.get(int(cd_cvm))

    def list_entries(self) -> tuple[CompanyCatalogEntry, ...]:
        snapshot = self._load_snapshot()
        return snapshot.entries

    def search_companies(
        self,
        *,
        q: str,
        limit: int,
        exclude_codes: set[int] | None = None,
    ) -> tuple[CompanyCatalogEntry, ...]:
        normalized_query = str(q or "").strip().lower()
        if not normalized_query or int(limit) <= 0:
            return ()

        excluded = exclude_codes or set()
        snapshot = self._load_snapshot()
        matches: list[tuple[tuple[int, int, str], CompanyCatalogEntry]] = []

        for entry in snapshot.entries:
            if entry.cd_cvm in excluded:
                continue

            company_name = entry.company_name.lower()
            trade_name = (entry.nome_comercial or "").lower()
            ticker = (entry.ticker_b3 or "").lower()
            code = str(entry.cd_cvm)

            names = [value for value in (company_name, trade_name) if value]
            rank: int | None = None

            if ticker == normalized_query or code == normalized_query:
                rank = 0
            elif any(value.startswith(normalized_query) for value in names):
                rank = 1
            elif ticker.startswith(normalized_query):
                rank = 2
            elif (
                any(normalized_query in value for value in names)
                or normalized_query in ticker
                or normalized_query in code
            ):
                rank = 3

            if rank is None:
                continue

            display_name = trade_name or company_name
            matches.append(
                (
                    (rank, 0 if entry.is_active else 1, display_name),
                    entry,
                )
            )

        matches.sort(key=lambda item: item[0])
        return tuple(entry for _, entry in matches[: int(limit)])

    def _load_snapshot(self) -> CompanyCatalogSnapshot:
        # TTL only controls local re-reading; it never authorizes a network request.
        with self._cache_lock:
            if self._cached_snapshot is not None and time.monotonic() - self._cached_at < self.ttl_seconds:
                return self._cached_snapshot
            try:
                payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                if payload["schema_version"] != 1 or not payload["source_url"] or not payload["downloaded_at"]:
                    raise ValueError("Missing catalog provenance")
                snapshot = self._parse_csv(payload["csv"].encode("latin1"))
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise CompanyCatalogUnavailableError(
                    "The local catalog is missing or invalid. Run setup or Update Data in Settings to download it."
                ) from exc
            self._cached_snapshot = snapshot
            self._cached_at = time.monotonic()
            return snapshot

    def refresh(self) -> CompanyCatalogSnapshot:
        """Explicit network operation; publish evidence only after validation succeeds."""
        logger.info("company_catalog_refresh_started source=%s", CVM_MASTER_URL)
        temporary_path = None
        try:
            response = requests.get(CVM_MASTER_URL, timeout=self.timeout)
            response.raise_for_status()
            snapshot = self._parse_csv(response.content)
            payload = {
                "schema_version": 1,
                "source_url": CVM_MASTER_URL,
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "csv": response.content.decode("latin1"),
            }
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.snapshot_path.parent,
                                             prefix=".catalog-", suffix=".tmp", delete=False) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=True)
                handle.flush()
                os.fsync(handle.fileno())
            with self._cache_lock:
                os.replace(temporary_path, self.snapshot_path)
                self._cached_snapshot = snapshot
                self._cached_at = time.monotonic()
            logger.info("company_catalog_refresh_completed entries=%d", len(snapshot.entries))
            return snapshot
        except Exception as exc:
            logger.warning("company_catalog_refresh_failed: %s", exc)
            raise CompanyCatalogUnavailableError(
                "Catalog refresh failed. The previous local snapshot has been preserved."
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @classmethod
    def _parse_csv(cls, content: bytes) -> CompanyCatalogSnapshot:
        raw_df = pd.read_csv(
            io.BytesIO(content), sep=";", encoding="latin1",
            usecols=["CD_CVM", "DENOM_SOCIAL", "DENOM_COMERC", "CNPJ_CIA", "SETOR_ATIV", "SIT"],
            dtype={"CD_CVM": str, "CNPJ_CIA": str},
        )
        snapshot = cls._build_snapshot(raw_df)
        if not snapshot.entries:
            raise ValueError("The CVM catalog contains no valid companies")
        return snapshot

    @staticmethod
    def _build_snapshot(raw_df: pd.DataFrame) -> CompanyCatalogSnapshot:
        df = raw_df.copy()
        df["CD_CVM"] = pd.to_numeric(df["CD_CVM"], errors="coerce")
        df = df.dropna(subset=["CD_CVM"]).copy()
        df["CD_CVM"] = df["CD_CVM"].astype(int)
        df["DENOM_SOCIAL"] = df["DENOM_SOCIAL"].fillna("").astype(str).str.strip()
        df["DENOM_COMERC"] = df["DENOM_COMERC"].fillna("").astype(str).str.strip()
        df["SETOR_ATIV"] = df["SETOR_ATIV"].fillna("").astype(str).str.strip()
        df["CNPJ_CIA"] = df["CNPJ_CIA"].fillna("").astype(str).str.strip()
        df["SIT"] = df["SIT"].fillna("").astype(str).str.strip().str.upper()
        df = df.drop_duplicates(subset="CD_CVM").sort_values("DENOM_SOCIAL")

        entries: list[CompanyCatalogEntry] = []
        by_cd_cvm: dict[int, CompanyCatalogEntry] = {}

        for _, row in df.iterrows():
            cd_cvm = int(row["CD_CVM"])
            company_name = str(row["DENOM_SOCIAL"]).strip() or f"CVM_{cd_cvm}"
            nome_comercial = str(row["DENOM_COMERC"]).strip() or None
            setor_cvm = str(row["SETOR_ATIV"]).strip() or None
            cnpj = str(row["CNPJ_CIA"]).strip() or None
            ticker_b3 = _normalize_display_ticker(TICKER_MAP.get(cd_cvm))
            entry = CompanyCatalogEntry(
                cd_cvm=cd_cvm,
                company_name=company_name,
                nome_comercial=nome_comercial,
                cnpj=cnpj,
                setor_cvm=setor_cvm,
                ticker_b3=ticker_b3,
                is_active=str(row["SIT"]).upper() in ACTIVE_STATUS_VALUES,
            )
            entries.append(entry)
            by_cd_cvm[cd_cvm] = entry

        return CompanyCatalogSnapshot(entries=tuple(entries), by_cd_cvm=by_cd_cvm)
