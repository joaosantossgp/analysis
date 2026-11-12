"""
CVM Financial Data Extractor
=============================

Extracts, processes, and generates Excel reports from CVM financial statements.
"""

# ============================================================================
# USER CONFIGURATION
# ============================================================================

# Company to process (name or CVM code)
COMPANY_NAME = "VALE"

# Year range (inclusive)
START_YEAR = 2020
END_YEAR = 2025

# Report type: "consolidated" or "individual"
REPORT_TYPE = "consolidated"

# Output directory
OUTPUT_DIR = "output/reports"

# Data directory
DATA_DIR = "data/input"

# Force re-download even if files exist
FORCE_REFRESH = False

# Maximum retries when output Excel file is locked by another process
MAX_EXCEL_LOCK_RETRIES = 10

# Network timeouts (seconds)
COMPANY_LIST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 60

# Additive statement reconciliation tolerance in normalized monetary units.
DFC_VALIDATION_TOLERANCE = 0.01

COMPANY_DB_MAX_RETRIES = 3
COMPANY_DB_RETRY_BACKOFF_SECONDS = 1.2

# Year interpretation: dois digitos < Y2K_PIVOT -> seculo 21, >= -> seculo 20
Y2K_PIVOT = 50

# ============================================================================
# IMPORTS
# ============================================================================

import sys
import os
import re
import time
import traceback
import requests
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import io
import json
import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Callable
from sqlalchemy.exc import OperationalError
from src.platform.contracts import RefreshProgressUpdate
from src.financials.utils import (
    normalize_account_name, generate_line_id_base, validate_line_ids,
    normalize_account_names, generate_line_id_bases,
)
from src.financials.standardizer import AccountStandardizer
from src.financials.database import CVMDatabase
from src.financials.periodization import build_statement, is_per_share
from src.financials.source_cache import AnnualSourceCache
from src.platform.settings import AppSettings, get_settings

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

_CSV_USECOLS = frozenset([
    "CD_CVM", "CD_CONTA", "DS_CONTA", "VL_CONTA", "DT_REFER",
    "DT_INI_EXERC", "DT_FIM_EXERC", "ORDEM_EXERC", "ESCALA_MOEDA",
    "VERSAO", "MOEDA", "GRUPO_DFP", "CNPJ_CIA", "ST_CONTA_FIXA",
])


@lru_cache(maxsize=1)
def _pd():
    import pandas as pd

    return pd


@lru_cache(maxsize=1)
def _pl():
    import polars as pl

    return pl


class CVMScraper:
    def __init__(
        self,
        output_dir="output/reports",
        data_dir="data/input",
        report_type="consolidated",
        max_workers=5,
        settings: AppSettings | None = None,
        source_cache: AnnualSourceCache | None = None,
    ):
        self.settings = settings or get_settings()
        self.output_dir = str(output_dir or self.settings.paths.reports_dir)
        self.data_dir = str(data_dir or self.settings.paths.input_dir)
        self.raw_dir = os.path.join(self.data_dir, "raw")
        self.processed_dir = os.path.join(self.data_dir, "processed")
        self.report_type = report_type or self.settings.default_report_type
        self.max_workers = max_workers
        self.base_url = self.settings.cvm_base_url
        self.company_list_timeout = self.settings.company_list_timeout
        self.download_timeout = self.settings.download_timeout
        self.max_excel_lock_retries = self.settings.max_excel_lock_retries
        self.company_db_max_retries = self.settings.company_db_max_retries
        self.company_db_retry_backoff_seconds = self.settings.company_db_retry_backoff_seconds
        self.force_refresh = os.getenv("CVM_FORCE_REFRESH", "0") == "1"
        self._print_lock = threading.Lock()
        self._http_state = threading.local()
        self._csv_cache: dict[str, "_pl().DataFrame"] = {}
        self.source_cache = source_cache
        if source_cache is not None:
            source_cache.configure(self.raw_dir, self.processed_dir, self.report_type, self.base_url)
            if self.force_refresh:
                source_cache.clear()

        if self.report_type == "consolidated":
            self.suffix = "con"
        else:
            self.suffix = "ind"
            
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.processed_dir, exist_ok=True)
        
        self.companies_map = {}
        self.setores_map = {}
        self.cnpjs_map = {}
        
        # Standardizer
        canonical_csv_path = str(self.settings.paths.canonical_accounts_path)
        self.standardizer = None
        if os.path.exists(canonical_csv_path):
            try:
                self.standardizer = AccountStandardizer(canonical_csv_path)
            except Exception as e:
                print(f"Aviso: Falha ao carregar padronizador: {e}")
                
        # Database
        db_path = str(self.settings.paths.db_path)
        self.db = CVMDatabase(db_path)

    def _http_session(self) -> requests.Session:
        session = getattr(self._http_state, "session", None)
        if session is None:
            session = requests.Session()
            self._http_state.session = session
        return session

    @staticmethod
    def _is_mocked_request(func) -> bool:
        return type(func).__module__.startswith("unittest.mock")

    def _http_get(self, *args, **kwargs):
        if self._is_mocked_request(requests.get):
            return requests.get(*args, **kwargs)
        return self._http_session().get(*args, **kwargs)

    def _http_head(self, *args, **kwargs):
        if self._is_mocked_request(requests.head):
            return requests.head(*args, **kwargs)
        return self._http_session().head(*args, **kwargs)

    def fetch_company_list(self):
        print("Fetching company list...")
        url = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
        try:
            response = self._http_get(url, timeout=self.company_list_timeout)
            response.raise_for_status()
            df = _pd().read_csv(io.BytesIO(response.content), sep=";", encoding="latin1")
            
            social = df[df['DENOM_SOCIAL'].notna()].set_index(df[df['DENOM_SOCIAL'].notna()]['DENOM_SOCIAL'].str.upper().str.strip())['CD_CVM']
            comerc = df[df['DENOM_COMERC'].notna()].set_index(df[df['DENOM_COMERC'].notna()]['DENOM_COMERC'].str.upper().str.strip())['CD_CVM']
            self.companies_map = {**social.to_dict(), **comerc.to_dict()}
            
            df['CD_CVM_STR'] = df['CD_CVM'].astype(str)
            self.setores_map = df[df['SETOR_ATIV'].notna()].set_index('CD_CVM_STR')['SETOR_ATIV'].to_dict()
            if 'CNPJ_CIA' in df.columns:
                self.cnpjs_map = df[df['CNPJ_CIA'].notna()].set_index('CD_CVM_STR')['CNPJ_CIA'].to_dict()
            else:
                self.cnpjs_map = {}
            return df
        except Exception as e:
            print(f"Error fetching company list: {e}")
            return None

    def resolve_company_codes(self, company_names):
        resolved = {}
        code_to_name = {v: k for k, v in self.companies_map.items()}
        for name in company_names:
            if str(name).isdigit():
                cvm_code = int(name)
                resolved[code_to_name.get(cvm_code, f"CVM_{cvm_code}")] = cvm_code
            else:
                name_upper = str(name).upper().strip()
                if name_upper in self.companies_map:
                    resolved[name] = self.companies_map[name_upper]
                else:
                    matches = [code for k, code in self.companies_map.items() if name_upper in k]
                    if matches: resolved[name] = matches[0]
        return resolved

    @staticmethod
    def _parse_http_datetime(raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None
        try:
            parsed = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _fetch_remote_zip_metadata(self, url: str) -> dict[str, object]:
        try:
            response = self._http_head(url, allow_redirects=True, timeout=self.download_timeout)
        except Exception as exc:
            print(f"  Warning: could not fetch remote metadata for {url}: {exc}")
            return {}

        if response.status_code != 200:
            print(
                f"  Warning: remote metadata unavailable for {url} "
                f"(status {response.status_code})"
            )
            return {}

        raw_length = response.headers.get("Content-Length")
        content_length = None
        if raw_length:
            try:
                content_length = int(raw_length)
            except (TypeError, ValueError):
                content_length = None

        return {
            "content_length": content_length,
            "last_modified": self._parse_http_datetime(response.headers.get("Last-Modified")),
        }

    def _should_refresh_local_zip(self, local_zip_path: str, url: str) -> tuple[bool, str]:
        if self.force_refresh:
            return True, "force_refresh"

        if not os.path.exists(local_zip_path):
            return True, "missing_local_zip"

        local_stat = os.stat(local_zip_path)
        if local_stat.st_size <= 0:
            return True, "empty_local_zip"

        remote_metadata = self._fetch_remote_zip_metadata(url)
        if not remote_metadata:
            return False, "remote_metadata_unavailable"

        remote_length = remote_metadata.get("content_length")
        remote_modified = remote_metadata.get("last_modified")
        local_modified = datetime.fromtimestamp(local_stat.st_mtime, tz=timezone.utc)

        reasons: list[str] = []
        if isinstance(remote_length, int) and remote_length > 0 and local_stat.st_size != remote_length:
            comparator = "<" if local_stat.st_size < remote_length else "!="
            reasons.append(f"size_mismatch ({local_stat.st_size} {comparator} {remote_length})")

        if isinstance(remote_modified, datetime):
            if local_modified.replace(microsecond=0) < remote_modified.replace(microsecond=0):
                reasons.append(
                    "remote_newer "
                    f"({local_modified.isoformat()} < {remote_modified.isoformat()})"
                )

        if reasons:
            return True, "; ".join(reasons)
        return False, "local_cache_fresh"

    def download_and_extract(self, year, doc_type) -> bool:
        filename = f"{doc_type.lower()}_cia_aberta_{year}.zip"
        url = f"{self.base_url}/{doc_type}/DADOS/{filename}"
        local_zip_path = os.path.join(self.raw_dir, filename)

        refresh_needed, refresh_reason = self._should_refresh_local_zip(local_zip_path, url)
        cache = self.source_cache
        if cache is not None and not refresh_needed and cache.prepared(local_zip_path):
            return True
        if cache is not None and refresh_needed:
            cache.prepared(local_zip_path)
        if not refresh_needed:
            with self._print_lock:
                print(f"  Using local zip: {filename} ({refresh_reason})")
        else:
            action = "Refreshing" if os.path.exists(local_zip_path) else "Downloading"
            with self._print_lock:
                print(f"{action} {doc_type} for {year}... ({refresh_reason})")
            tmp_zip_path = f"{local_zip_path}.download"
            downloaded = False
            for attempt in range(3):
                try:
                    response = self._http_get(url, stream=True, timeout=self.download_timeout)
                    if response.status_code != 200:
                        if cache is not None:
                            cache.clear()
                        return False
                    with open(tmp_zip_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    os.replace(tmp_zip_path, local_zip_path)
                    downloaded = True
                    break
                except requests.exceptions.RequestException as e:
                    if os.path.exists(tmp_zip_path):
                        os.remove(tmp_zip_path)
                    if attempt < 2:
                        sleep_s = 2 ** attempt  # 1s, 2s
                        with self._print_lock:
                            print(f"  Retry {attempt + 1}/3 for {doc_type}/{year} in {sleep_s}s: {e}")
                        time.sleep(sleep_s)
                    else:
                        with self._print_lock:
                            print(f"  Error downloading {doc_type}/{year} after 3 attempts: {e}")
                        if cache is not None:
                            cache.clear()
                        return False
            if not downloaded:
                return False

        try:
            zip_signature = AnnualSourceCache.signature(local_zip_path) if cache is not None else None
            extracted = []
            with zipfile.ZipFile(local_zip_path, 'r') as zip_ref:
                for file in zip_ref.namelist():
                    if any(f'_{self.suffix}_' in file and x in file for x in ['BPA', 'BPP', 'DRE', 'DFC', 'DVA', 'DMPL']):
                        extracted.append(zip_ref.extract(file, self.processed_dir))
            if cache is not None:
                cache.remember_prepared(local_zip_path, extracted, zip_signature)
            return True
        except Exception as e:
            if cache is not None:
                cache.clear()
            with self._print_lock:
                print(f"  Error extracting {doc_type}/{year}: {e}")
            return False

    def normalize_units(self, df):
        """Converts values to Thousands (R$ mil) based on ESCALA_MOEDA."""
        if 'VL_CONTA' in df.columns:
            if 'RAW_VL_CONTA' not in df.columns:
                df['RAW_VL_CONTA'] = df['VL_CONTA'].astype(str)
            df['VL_CONTA'] = _pd().to_numeric(df['VL_CONTA'], errors='coerce').astype(float)
        if 'ESCALA_MOEDA' not in df.columns or 'VL_CONTA' not in df.columns:
            return df
        per_share = df.get('CD_CONTA', _pd().Series('', index=df.index)).map(lambda code: is_per_share('DRE', code))
        mask_unidade = (df['ESCALA_MOEDA'].str.upper() == 'UNIDADE') & ~per_share
        mask_milhao = df['ESCALA_MOEDA'].str.upper().isin(['MILHÃO', 'MILHAO', 'MILLION']) & ~per_share
        df.loc[mask_unidade, 'VL_CONTA'] = df.loc[mask_unidade, 'VL_CONTA'] / 1000
        df.loc[mask_milhao, 'VL_CONTA'] = df.loc[mask_milhao, 'VL_CONTA'] * 1000
        return df

    def _read_csv_cached(self, filepath: str) -> "_pl().DataFrame":
        cache = self.source_cache
        if cache is not None:
            cached = cache.get(filepath)
            if cached is not None:
                return cached
        if filepath not in self._csv_cache:
            pl = None
            try:
                pl = _pl()
                df = pl.read_csv(
                    filepath,
                    separator=";",
                    encoding="latin1",
                    schema_overrides={"CD_CVM": pl.Int64, "CD_CONTA": pl.String,
                                      "VL_CONTA": pl.String, "VERSAO": pl.String},
                    infer_schema_length=1000,
                )
                wanted = [c for c in df.columns if c in _CSV_USECOLS]
                if wanted:
                    df = df.select(wanted)
            except Exception:
                df_pandas = _pd().read_csv(
                    filepath,
                    sep=";",
                    encoding="latin1",
                    dtype={"CD_CVM": "Int64", "CD_CONTA": str, "VL_CONTA": str, "VERSAO": str},
                    usecols=lambda column: column in _CSV_USECOLS,
                )
                if pl is not None:
                    try:
                        df = pl.from_pandas(df_pandas)
                    except Exception:
                        df = df_pandas
                else:
                    df = df_pandas
            if cache is not None:
                if hasattr(df, "is_empty"):
                    subset = df.filter(_pl().col('CD_CVM').is_in(cache.company_codes))
                    # to_pandas copies: a Polars slice can retain its full market buffers.
                    subset = self._polars_to_pandas(subset)
                else:
                    subset = df[df['CD_CVM'].isin(cache.company_codes)].copy(deep=True)
                return cache.retain(filepath, subset)
            self._csv_cache[filepath] = df
        return self._csv_cache[filepath]

    def _polars_to_pandas(self, df):
        try:
            return df.to_pandas()
        except Exception:
            records = df.to_dicts()
            if not records:
                return _pd().DataFrame({name: df[name].to_numpy().copy() for name in df.columns})
            return _pd().DataFrame(records)

    def process_data(self, cvm_code, years):
        all_data = []
        file_patterns = ['BPA', 'BPP', 'DRE', 'DFC_MD', 'DFC_MI', 'DVA', 'DMPL']
        for year in years:
            for doc_type in ['dfp', 'itr']:
                for pattern in file_patterns:
                    filename = f"{doc_type}_cia_aberta_{pattern}_{self.suffix}_{year}.csv"
                    filepath = os.path.join(self.processed_dir, filename)
                    if os.path.exists(filepath):
                        try:
                            df = self._read_csv_cached(filepath)
                            if hasattr(df, "filter") and hasattr(df, "is_empty"):
                                pl = _pl()
                                df_company_pl = df.filter(pl.col('CD_CVM') == int(cvm_code))
                                if 'ORDEM_EXERC' in df_company_pl.columns:
                                    df_company_pl = df_company_pl.filter(pl.col('ORDEM_EXERC') == 'ÚLTIMO')
                                if df_company_pl.is_empty():
                                    continue
                                df_company = self._polars_to_pandas(df_company_pl)
                            else:
                                df_company = df[df['CD_CVM'].astype('Int64') == int(cvm_code)].copy()
                                if 'ORDEM_EXERC' in df_company.columns:
                                    df_company = df_company[df_company['ORDEM_EXERC'] == 'ÚLTIMO'].copy()
                                if df_company.empty:
                                    continue
                            stmt_map = {'BPA':'BPA', 'BPP':'BPP', 'DRE':'DRE', 'DFC_MD':'DFC', 'DFC_MI':'DFC', 'DVA':'DVA', 'DMPL':'DMPL'}
                            stmt_type = stmt_map.get(pattern, 'OTHER')
                            df_company['DS_CONTA_norm'] = normalize_account_names(df_company['DS_CONTA'])
                            df_company['LINE_ID_BASE'] = generate_line_id_bases(df_company, stmt_type)
                            df_company = self.normalize_units(df_company)
                            df_company['PERIOD_TYPE'] = doc_type.upper()
                            df_company['STMT_TYPE_INTERNAL'] = stmt_type
                            df_company['REPORT_TYPE'] = self.report_type
                            df_company['SOURCE_FILE'] = filename
                            # Preserve COMPANY_TYPE for dashboard
                            setor = str(self.setores_map.get(str(cvm_code), '')).lower()
                            df_company['COMPANY_TYPE'] = 'financeira' if any(k in setor for k in ['banc', 'financ']) else 'comercial'
                            all_data.append(df_company)
                        except Exception as exc:
                            if self.source_cache is not None:
                                self.source_cache.clear()
                            with self._print_lock:
                                print(
                                    f"  Error processing {filename} for CVM {cvm_code}: {exc}"
                                )
                            continue
        return _pd().concat(all_data, ignore_index=True) if all_data else None

    def calculate_quarters(self, df, report_type):
        if df.empty:
            return _pd().DataFrame()
        result, errors = build_statement(df, report_type, DFC_VALIDATION_TOLERANCE)
        if not hasattr(self, '_coalesce_errors'):
            self._coalesce_errors = []
        self._coalesce_errors.extend(errors)
        metadata = ['LINE_ID_BASE', 'CD_CONTA', 'DS_CONTA', 'DS_CONTA_norm', 'QA_CONFLICT']
        if result.empty:
            return result
        periods = sorted([c for c in result.columns if c not in metadata], key=self._period_sort_key)
        return result[metadata + periods]

    def _create_period_label(self, row, report_type):
        if report_type in ['BPA', 'BPP']:
            dt = row.get('DT_REFER')
            if _pd().isna(dt): return None
            yy = str(dt.year)[2:]
            if dt.month == 3: return f'1Q{yy}'
            if dt.month == 6: return f'2Q{yy}'
            if dt.month == 9: return f'3Q{yy}'
            if dt.month == 12: return str(dt.year)
        else:
            dt_ini, dt_fim = row.get('DT_INI_EXERC'), row.get('DT_FIM_EXERC')
            if _pd().isna(dt_ini) or _pd().isna(dt_fim): return None
            yy = str(dt_fim.year)[2:]
            if dt_ini.month == 1 and dt_ini.day == 1:
                if dt_fim.month == 3: return f'1Q{yy}'
                if dt_fim.month == 6: return f'2Q{yy}'
                if dt_fim.month == 9: return f'3Q{yy}'
                if dt_fim.month == 12: return str(dt_fim.year)
            elif dt_ini.month == 4 and dt_fim.month == 6: return f'2Q{yy}'
            elif dt_ini.month == 7 and dt_fim.month == 9: return f'3Q{yy}'
            elif dt_ini.month == 10 and dt_fim.month == 12: return f'4Q{yy}'
        return None

    def _period_sort_key(self, label):
        if label.isdigit(): return (int(label), 5)
        if len(label) >= 4 and label[1] == 'Q':
            q = int(label[0])
            y = 2000 + int(label[2:]) if len(label[2:])==2 else int(label[2:])
            return (y, q)
        return (9999, 0)

    def coalesce_duplicate_line_ids(self, df, stmt):
        qa_errors = []
        p_cols = [c for c in df.columns if c not in ['LINE_ID_BASE', 'CD_CONTA', 'DS_CONTA', 'DS_CONTA_norm', 'QA_CONFLICT']]
        grouped = df.groupby('LINE_ID_BASE')
        final_rows = []
        for lid, group in grouped:
            if len(group) == 1:
                final_rows.append(group.iloc[0])
                continue
            merged = group.iloc[0].copy()
            has_conflict = False
            for col in p_cols:
                vals = group[col].dropna().unique()
                if len(vals) > 1:
                    has_conflict = True
                    qa_errors.append({'type': 'REAL_CONFLICT', 'statement': stmt, 'line_id_base': lid, 'period': col})
                if len(vals) >= 1: merged[col] = vals[0]
            merged['QA_CONFLICT'] = has_conflict
            final_rows.append(merged)
        return _pd().DataFrame(final_rows), [], qa_errors

    def _identify_period_years(self, df):
        import re
        years = set()
        for col in df.columns:
            if re.match(r'^\d{4}$', str(col)): years.add(int(col))
            m = re.match(r'^\dQ(\d{2})$', str(col))
            if m: years.add(2000 + int(m.group(1)))
        return sorted(years)

    def _compute_standalone_quarters(self, df, year, stmt):
        yy = str(year)[2:]; errors = []
        c1, c2, c3, c4, ca = f'1Q{yy}', f'2Q{yy}', f'3Q{yy}', f'4Q{yy}', str(year)
        h1, h2, h3, ha = c1 in df.columns, c2 in df.columns, c3 in df.columns, ca in df.columns
        if not any([h1, h2, h3, ha]): return df, []
        
        s1 = df[c1].copy() if h1 else _pd().Series(float('nan'), index=df.index)
        missing = _pd().Series(float('nan'), index=df.index)
        s2 = df[c2] - df[c1] if h2 and h1 else missing.copy()
        s3 = df[c3] - df[c2] if h3 and h2 else missing.copy()
        s4 = df[ca] - df[c3] if ha and h3 else missing.copy()
        for target, predecessor, current_present, previous_present in [
            (c2, c1, h2, h1), (c3, c2, h3, h2), (c4, c3, ha, h3)
        ]:
            current = ca if target == c4 else target
            if current_present:
                absent = df[current].notna() & (df[predecessor].isna() if previous_present else True)
                for idx in df.index[absent]:
                    errors.append({'type': 'MISSING_PREDECESSOR', 'statement': stmt, 'year': year,
                                   'period': target, 'line_id_base': df.loc[idx, 'LINE_ID_BASE'],
                                   'cd_conta': df.loc[idx, 'CD_CONTA'], 'missing_inputs': [predecessor],
                                   'action': 'Review the missing cumulative predecessor in the original filing.'})
        if h1: df[c1] = s1
        if h2: df[c2] = s2
        if h3: df[c3] = s3
        if ha: df[c4] = s4
        return df, errors, s1, s2, s3, s4, (df[ca] if ha else s1*0)

    def _validate_quarterly_sum(self, df, year, s1, s2, s3, s4, ann, stmt):
        ers = []
        diff = ((s1 + s2 + s3 + s4) - ann).abs()
        for idx in df.index:
            if not _pd().isna(ann.loc[idx]) and diff.loc[idx] > DFC_VALIDATION_TOLERANCE:
                ers.append({'type': 'DFC_VALIDATION_FAILED', 'statement': stmt, 'year': year, 'diff': float(diff.loc[idx])})
        return ers

    def convert_dfc_ytd_to_standalone(self, df, stmt):
        qa = []
        for y in self._identify_period_years(df):
            res = self._compute_standalone_quarters(df, y, stmt)
            if len(res) > 2:
                df, errs, s1, s2, s3, s4, ann = res
                qa.extend(errs)
                qa.extend(self._validate_quarterly_sum(df, y, s1, s2, s3, s4, ann, stmt))
        return df, qa

    def process_all_reports(self, raw_df):
        reports = {}
        self._coalesce_errors = []
        for stmt in ['BPA', 'BPP', 'DRE', 'DFC']:
            sub = raw_df[raw_df['STMT_TYPE_INTERNAL'] == stmt]
            df_stmt = self.calculate_quarters(sub, stmt)
            if not df_stmt.empty: reports[stmt] = df_stmt
        return reports, self._coalesce_errors

    def validate_line_id_uniqueness(self, reports):
        errs = []
        for name, df in reports.items():
            dups = df['LINE_ID_BASE'].value_counts()
            if dups.max() > 1: errs.append({'sheet': name, 'count': int(dups.max())})
        return len(errs)==0, errs

    def validate_final_output(self, reports):
        return True, [] # Simplified for restoration

    def generate_excel(self, name, cvm, reports, qas=None):
        import re
        safe = re.sub(r'[\\/*?:"<>|]', '_', name).replace(' ', '_')
        path = os.path.join(self.output_dir, f"{safe}_financials.xlsx")
        setor = str(self.setores_map.get(str(cvm), '')).lower()
        tipo = 'financeira' if any(k in setor for k in ['banc', 'financ']) else 'comercial'
        
        final = {}
        if self.standardizer:
            for s, df in reports.items():
                # Enrich only the table; restore the original audit evidence below.
                final[s] = self.standardizer.enrich(_pd().DataFrame(df, copy=True), s, tipo, (self.report_type=="consolidated"))
        else: final = reports
        
        for statement, report in final.items():
            report.attrs.update(reports[statement].attrs)

        from src.companies.identity import CompanyIdentityResolver
        identity = CompanyIdentityResolver().resolve(int(cvm))
        ticker_b3 = None
        if identity and identity.ticker_b3:
            ticker_b3 = identity.ticker_b3.strip().upper()
            if ticker_b3.endswith(".SA"):
                ticker_b3 = ticker_b3[:-3]

        rows_inserted = self.db.insert_company_data(
            name,
            int(cvm),
            tipo,
            final,
            qas,
            self.setores_map.get(str(cvm)),
            ticker_b3=ticker_b3,
            cnpj=self.cnpjs_map.get(str(cvm)),
        )
        
        for attempt in range(1, self.max_excel_lock_retries + 1):
            try:
                with _pd().ExcelWriter(path, engine='openpyxl') as writer:
                    for s, report in final.items():
                        # Keep audit attrs on the report for the explicit evidence sheets.
                        df = _pd().DataFrame(report, copy=True)
                        df.to_excel(writer, sheet_name=s, startrow=2, index=False)
                        ws = writer.sheets[s]
                        ws['A1'] = f"Type: {self.report_type}"
                        ws['A2'] = "Values in BRL thousands; DRE 3.99 per-share accounts in BRL/share. Review financial_qa."
                        if s == 'DRE' and 'CD_CONTA' in df.columns:
                            for row_index, code in enumerate(df['CD_CONTA'], start=4):
                                if is_per_share(s, code):
                                    for cell in ws[row_index]:
                                        if isinstance(cell.value, (int, float)):
                                            cell.number_format = '#,##0.00####;(#,##0.00####);-'
                    if qas:
                        audit = []
                        for event in qas:
                            item = {key: value for key, value in event.items() if key != 'source_inputs'}
                            item['source_ids'] = json.dumps([source.get('observation_id') for source in event.get('source_inputs', [])])
                            audit.append(item)
                        _pd().DataFrame(audit).to_excel(writer, sheet_name='financial_qa', index=False)
                    for key in ('source_observations', 'value_lineage'):
                        evidence = [record for df in final.values() for record in df.attrs.get(key, [])]
                        if evidence:
                            _pd().DataFrame(evidence).to_excel(writer, sheet_name=key, index=False)
                break
            except PermissionError:
                if attempt >= self.max_excel_lock_retries:
                    raise
                wait_s = min(2.0, 0.2 * attempt)
                print(
                    f"Excel file locked for {name} "
                    f"(attempt {attempt}/{self.max_excel_lock_retries}). Retrying in {wait_s:.1f}s..."
                )
                time.sleep(wait_s)
        print(f"Saved to {path}")
        return int(rows_inserted or 0)

    @staticmethod
    def _extract_years_processed(reports: dict, start_year: int, end_year: int) -> list[int]:
        years: set[int] = set()
        for _stmt, df_stmt in reports.items():
            if df_stmt is None or df_stmt.empty:
                continue
            for col in df_stmt.columns:
                label = str(col)
                if label.isdigit() and len(label) == 4:
                    years.add(int(label))
                    continue
                if re.match(r'^\dQ(\d{2})$', label):
                    years.add(2000 + int(label[2:]))
        bounded = [y for y in years if int(start_year) <= int(y) <= int(end_year)]
        return sorted(set(int(y) for y in bounded))

    def run(
        self,
        companies,
        start_year,
        end_year,
        company_year_overrides: dict[int, list[int]] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        stage_callback: Callable[[RefreshProgressUpdate], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ):
        def _emit_stage(stage: str, current: int, total: int, message: str) -> None:
            if stage_callback is None:
                return
            stage_callback(
                RefreshProgressUpdate(
                    stage=stage,
                    current=int(current),
                    total=max(1, int(total)),
                    message=str(message),
                )
            )

        self.fetch_company_list()
        resolved = self.resolve_company_codes(companies)

        download_years: set[int] = set()
        if company_year_overrides:
            for years in company_year_overrides.values():
                for year in years:
                    download_years.add(int(year))
        if not download_years:
            download_years = set(range(int(start_year), int(end_year) + 1))

        tasks = [
            (year, doc_type)
            for year in sorted(download_years)
            for doc_type in ('DFP', 'ITR')
        ]
        completed_downloads = 0
        _emit_stage(
            "download_extract",
            0,
            len(tasks) or 1,
            "Baixando e extraindo demonstracoes CVM.",
        )
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tasks)))) as pool:
            futures = {pool.submit(self.download_and_extract, year, dt): (year, dt)
                       for year, dt in tasks}
            for fut in as_completed(futures):
                year_done, dt_done = futures[fut]
                try:
                    fut.result()
                except Exception as exc:
                    if self.source_cache is not None:
                        self.source_cache.clear()
                    with self._print_lock:
                        print(f"  Unexpected error for {dt_done}/{year_done}: {exc}")
                completed_downloads += 1
                _emit_stage(
                    "download_extract",
                    completed_downloads,
                    len(tasks) or 1,
                    f"Download concluido para {dt_done}/{year_done}.",
                )
        
        company_items = list(resolved.items())
        total_companies = len(company_items)
        results = {}
        completed = 0
        default_years = list(range(int(start_year), int(end_year) + 1))
        for name, cvm in company_items:
            if progress_callback is not None:
                progress_callback(completed, total_companies, name)
            if should_cancel is not None and should_cancel():
                print("Execution cancelled before next company.")
                break

            years_requested = default_years
            if company_year_overrides:
                years_requested = company_year_overrides.get(int(cvm), default_years)
            years_requested = sorted(set(int(y) for y in years_requested))

            print(f"Processing {name}...")
            _emit_stage(
                "process_data",
                completed,
                total_companies or 1,
                f"Processando demonstracoes de {name}.",
            )
            payload = {
                "company_name": str(name),
                "cvm_code": int(cvm),
                "requested_years": years_requested,
                "years_processed": [],
                "rows_inserted": 0,
                "status": "error",
                "error": None,
                "traceback": None,
                "attempts": 0,
            }
            raw = self.process_data(cvm, years_requested)
            if raw is None:
                _emit_stage(
                    "process_data",
                    completed + 1,
                    total_companies or 1,
                    f"Nenhuma demonstracao encontrada para {name}.",
                )
                payload["status"] = "no_data"
                payload["error"] = "No financial rows found for selected years"
                results[str(int(cvm))] = payload
                completed += 1
                continue

            proc, qas = self.process_all_reports(raw)
            _emit_stage(
                "process_data",
                completed + 1,
                total_companies or 1,
                f"Processamento concluido para {name}.",
            )
            years_min = min(years_requested) if years_requested else int(start_year)
            years_max = max(years_requested) if years_requested else int(end_year)
            payload["years_processed"] = self._extract_years_processed(
                proc,
                years_min,
                years_max,
            )
            if not proc:
                payload["error"] = "No supported statements found after processing"
                results[str(int(cvm))] = payload
                completed += 1
                continue

            attempt = 0
            _emit_stage(
                "persist_reports",
                completed,
                total_companies or 1,
                f"Gravando relatorios e persistindo dados de {name}.",
            )
            while attempt < self.company_db_max_retries:
                attempt += 1
                payload["attempts"] = int(attempt)
                try:
                    rows_inserted = self.generate_excel(name, cvm, proc, qas)
                    payload["rows_inserted"] = int(rows_inserted or 0)
                    payload["status"] = "success"
                    payload["error"] = None
                    _emit_stage(
                        "persist_reports",
                        completed + 1,
                        total_companies or 1,
                        f"Persistencia concluida para {name}.",
                    )
                    break
                except OperationalError as exc:
                    if self.source_cache is not None:
                        self.source_cache.clear()
                    sql_code = getattr(exc, "code", None)
                    sql_text = f"[{sql_code}] {exc}" if sql_code else str(exc)
                    payload["status"] = "error"
                    payload["error"] = f"{exc.__class__.__name__}: {sql_text}"
                    payload["traceback"] = traceback.format_exc()
                    if attempt >= self.company_db_max_retries:
                        print(
                            f"OperationalError for {name} after {attempt} attempt(s): {sql_text}"
                        )
                        break
                    sleep_s = self.company_db_retry_backoff_seconds * attempt
                    print(
                        f"OperationalError for {name} on attempt {attempt}/{self.company_db_max_retries}. "
                        f"Retrying in {sleep_s:.1f}s... {sql_text}"
                    )
                    time.sleep(sleep_s)
                except Exception as exc:
                    payload["status"] = "error"
                    payload["error"] = f"{exc.__class__.__name__}: {exc}"
                    payload["traceback"] = traceback.format_exc()
                    print(f"Error processing {name}: {exc}")
                    break
            results[str(int(cvm))] = payload
            completed += 1
        self._csv_cache.clear()
        return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--company', default=COMPANY_NAME)
    parser.add_argument('--start-year', type=int, default=START_YEAR)
    parser.add_argument('--end-year', type=int, default=END_YEAR)
    args = parser.parse_args()
    scraper = CVMScraper()
    scraper.run([args.company], args.start_year, args.end_year)
