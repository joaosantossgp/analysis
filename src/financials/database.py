import os
import re
import time
import logging
import json
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy import create_engine, inspect, text, Engine
from sqlalchemy.exc import OperationalError

from src.companies.gics_manual_mapping import resolve_gics_classification
from src.companies.universe import ensure_company_universe_tables_for_connection
from src.companies.coverage import ensure_coverage_tables_for_connection
from src.financials.excel_mapping import ensure_excel_mapping_tables_for_connection
from src.financials.marts import ensure_financial_mart_tables_for_connection
from src.refresh.jobs import ensure_refresh_runtime_tables_for_connection
from src.energy_kpi.schema import get_energy_kpi_engine
from src.companies.market_history import ensure_market_history_tables_for_connection

logger = logging.getLogger(__name__)

SQLITE_WRITE_MAX_RETRIES = 3


def init_db_tables(engine: Engine) -> None:
    """Create all required tables if they do not exist.

    Safe to call multiple times (idempotent). Used by CVMDatabase on init
    and by the API lifespan to ensure tables exist on a fresh PostgreSQL
    instance before the healthcheck runs.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        pk = "INTEGER PRIMARY KEY AUTOINCREMENT"
        real = "REAL"
        with engine.connect() as pragma_conn:
            pragma_conn.execute(text("PRAGMA journal_mode = WAL"))
            pragma_conn.execute(text("PRAGMA synchronous = OFF"))
    else:
        pk = "SERIAL PRIMARY KEY"
        real = "DOUBLE PRECISION"

    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS financial_reports (
                id {pk},
                "COMPANY_NAME" TEXT,
                "CD_CVM" INTEGER,
                "COMPANY_TYPE" TEXT,
                "STATEMENT_TYPE" TEXT,
                "REPORT_YEAR" INTEGER,
                "PERIOD_LABEL" TEXT,
                "LINE_ID_BASE" TEXT,
                "CD_CONTA" TEXT,
                "DS_CONTA" TEXT,
                "STANDARD_NAME" TEXT,
                "QA_CONFLICT" BOOLEAN,
                "VL_CONTA" {real},
                UNIQUE("CD_CVM", "STATEMENT_TYPE", "PERIOD_LABEL", "LINE_ID_BASE")
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS qa_logs (
                id {pk},
                "COMPANY_NAME" TEXT,
                "CD_CVM" INTEGER,
                "ERROR_TYPE" TEXT,
                "STATEMENT_TYPE" TEXT,
                "PERIOD" TEXT,
                "LINE_ID_BASE" TEXT,
                "CD_CONTA" TEXT,
                "DESCRIPTION" TEXT,
                "ACTION" TEXT
            )
        """))
        inspector = inspect(conn, raiseerr=False)
        if inspector is not None:
            columns = {column['name'] for column in inspector.get_columns('qa_logs')}
            for name, datatype in {'REPORT_YEAR': 'INTEGER', 'DETAILS_JSON': 'TEXT'}.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE qa_logs ADD COLUMN "{name}" {datatype}'))
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS financial_source_observations (
                observation_id TEXT PRIMARY KEY,
                cd_cvm INTEGER NOT NULL,
                statement_type TEXT NOT NULL,
                report_year INTEGER,
                payload_json TEXT NOT NULL,
                imported_at TEXT NOT NULL
            )
        '''))
        conn.execute(text('''
            CREATE INDEX IF NOT EXISTS idx_financial_sources_company_year
            ON financial_source_observations(cd_cvm, report_year, statement_type)
        '''))
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS financial_value_lineage (
                cd_cvm INTEGER NOT NULL,
                statement_type TEXT NOT NULL,
                report_year INTEGER NOT NULL,
                period_label TEXT NOT NULL,
                line_id_base TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(cd_cvm, statement_type, period_label, line_id_base)
            )
        '''))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS companies (
                cd_cvm          INTEGER PRIMARY KEY,
                company_name    TEXT NOT NULL,
                nome_comercial  TEXT,
                cnpj            TEXT,
                setor_cvm       TEXT,
                gics_sector     TEXT,
                gics_sector_slug TEXT,
                gics_industry_group TEXT,
                gics_industry   TEXT,
                gics_sub_industry TEXT,
                company_type    TEXT NOT NULL DEFAULT 'comercial',
                ticker_b3       TEXT,
                coverage_rank   INTEGER,
                is_active       INTEGER NOT NULL DEFAULT 1,
                updated_at      TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS company_views (
                cd_cvm         INTEGER PRIMARY KEY REFERENCES companies(cd_cvm) ON DELETE CASCADE,
                view_count     INTEGER NOT NULL DEFAULT 0,
                last_viewed_at TEXT NOT NULL
            )
        """))
        ensure_refresh_runtime_tables_for_connection(conn)
        ensure_company_universe_tables_for_connection(conn)
        ensure_coverage_tables_for_connection(conn)
        ensure_excel_mapping_tables_for_connection(conn)
        ensure_market_history_tables_for_connection(conn)
        ensure_financial_mart_tables_for_connection(conn)
        _ensure_company_columns(conn)

    _index_ddl = [
        'CREATE INDEX {c}IF NOT EXISTS idx_company_views_count ON company_views(view_count DESC)',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cd_cvm ON financial_reports("CD_CVM")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cd_cvm_stmt_year ON financial_reports("CD_CVM", "STATEMENT_TYPE", "REPORT_YEAR")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cvm_year ON financial_reports("CD_CVM", "REPORT_YEAR", "PERIOD_LABEL")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cd_conta ON financial_reports("CD_CONTA")',
        "CREATE INDEX {c}IF NOT EXISTS idx_companies_ticker ON companies(ticker_b3)",
        # #582: each refresh deletes QA by this scope per statement-year; without it every delete scans qa_logs.
        'CREATE INDEX {c}IF NOT EXISTS idx_qa_logs_scope ON qa_logs("CD_CVM", "STATEMENT_TYPE", "REPORT_YEAR")',
        # Benchmarked 2026-04-20 (issue #134): EXPLAIN QUERY PLAN confirmed full SCAN of
        # financial_reports for any query filtered only by PERIOD_LABEL (sector_years_map,
        # available_years, sector_metric_rows). These composites let the planner eliminate
        # annual-vs-quarterly rows and the CD_CONTA IN filter without additional table scans.
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_year_period ON financial_reports("REPORT_YEAR", "PERIOD_LABEL")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_period_label ON financial_reports("PERIOD_LABEL")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cd_cvm_period_label ON financial_reports("CD_CVM", "PERIOD_LABEL")',
        'CREATE INDEX {c}IF NOT EXISTS idx_fr_cd_conta_period_label ON financial_reports("CD_CONTA", "PERIOD_LABEL")',
    ]
    if dialect == "postgresql":
        # CONCURRENTLY cannot run inside a transaction — requires AUTOCOMMIT
        with engine.connect() as idx_conn:
            idx_conn = idx_conn.execution_options(isolation_level="AUTOCOMMIT")
            for ddl in _index_ddl:
                idx_conn.execute(text(ddl.format(c="CONCURRENTLY ")))
    else:
        with engine.begin() as idx_conn:
            for ddl in _index_ddl:
                idx_conn.execute(text(ddl.format(c="")))

    logger.info("init_db_tables completed dialect=%s", dialect)
    _backfill_companies_metadata(engine)


def init_entity_registry_schema(engine: Engine) -> None:
    """Explicitly create the registry foundation for a fresh or sandbox database.

    This is intentionally not called by ordinary financial-database startup.
    Installed-database migration, legacy backfill, and cutover require the
    separately approved catalog/copy/swap runner.
    """
    from src.companies.entity_registry_schema import ensure_entity_registry_schema

    ensure_entity_registry_schema(engine)


def _backfill_companies_metadata(engine: Engine) -> None:
    """Idempotently backfills missing CNPJ or ticker_b3 values for existing companies in the database locally.

    Accepts a SQLAlchemy Engine or compatible connection object.
    """
    try:
        # Check if companies table exists and has rows with NULL cnpj or ticker_b3
        with engine.connect() as conn:
            inspector = inspect(conn)
            if not inspector.has_table("companies"):
                return
            
            rows = conn.execute(
                text("SELECT cd_cvm, cnpj, ticker_b3 FROM companies")
            ).fetchall()
            
        if not rows:
            return
            
        logger.info("Running automatic local metadata backfill for %d companies...", len(rows))
        from src.companies.identity import CompanyIdentityResolver
        from src.companies.cnpj import validate_cnpj
        
        resolver = CompanyIdentityResolver()
        updates_list = []
        
        for row in rows:
            cd_cvm = row[0]
            cnpj = row[1]
            ticker_b3 = row[2]
            
            updates = {}
            if cnpj:
                cleaned_cnpj = "".join(c for c in str(cnpj) if c.isdigit())
                if cleaned_cnpj != cnpj and validate_cnpj(cleaned_cnpj):
                    updates["cnpj"] = cleaned_cnpj
            else:
                identity = resolver.resolve(int(cd_cvm))
                if identity and identity.cnpj:
                    updates["cnpj"] = identity.cnpj

            if not ticker_b3:
                identity = resolver.resolve(int(cd_cvm))
                raw_ticker = identity.ticker_b3 if identity else None
                if raw_ticker:
                    clean_ticker = raw_ticker.strip().upper()
                    if clean_ticker.endswith(".SA"):
                        clean_ticker = clean_ticker[:-3]
                    updates["ticker_b3"] = clean_ticker
            
            if updates:
                updates_list.append((cd_cvm, updates))
        
        if updates_list:
            with engine.begin() as conn:
                for cd_cvm, updates in updates_list:
                    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                    updates["cd_cvm"] = cd_cvm
                    conn.execute(
                        text(f"UPDATE companies SET {set_clause} WHERE cd_cvm = :cd_cvm"),
                        updates
                    )
            logger.info("Local metadata backfill completed. Normalized/Updated %d companies.", len(updates_list))
    except Exception as exc:
        logger.debug("Bypassing local metadata backfill (inspection not supported or other database constraint): %s", exc)



def _ensure_company_columns(conn) -> None:
    inspector = inspect(conn, raiseerr=False)
    if inspector is None:
        return
    
    existing = {
        str(column.get("name") or "").lower()
        for column in inspector.get_columns("companies")
    }

    # Add missing columns dynamically to support smooth database migrations/upgrades
    columns_to_ensure = {
        "nome_comercial": "TEXT",
        "cnpj": "TEXT",
        "setor_cvm": "TEXT",
        "gics_sector": "TEXT",
        "gics_sector_slug": "TEXT",
        "gics_industry_group": "TEXT",
        "gics_industry": "TEXT",
        "gics_sub_industry": "TEXT",
        "gics_sub_industry_code": "TEXT",
        "classification_origin": "TEXT",
        "company_type": "TEXT NOT NULL DEFAULT 'comercial'",
        "ticker_b3": "TEXT",
        "coverage_rank": "INTEGER",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "updated_at": "TEXT NOT NULL DEFAULT ''"
    }

    for col_name, col_type in columns_to_ensure.items():
        if col_name.lower() not in existing:
            conn.execute(text(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}"))

    # #525: the legacy sector column was replaced by the canonical gics_* columns.
    # SQLite refuses DROP COLUMN on an indexed column, so drop its index first.
    if "setor_analitico" in existing:
        conn.execute(text("DROP INDEX IF EXISTS idx_companies_setor"))
        conn.execute(text("ALTER TABLE companies DROP COLUMN setor_analitico"))

SQLITE_WRITE_BACKOFF_SECONDS = 0.6
DEFAULT_TO_SQL_CHUNKSIZE = 2000
SQLITE_SAFE_MAX_VARIABLES = 900


class CVMDatabase:
    """Manages the database for CVM financial reports.

    Suporta SQLite (local) e PostgreSQL (Supabase/produção) via SQLAlchemy.
    A escolha do backend é feita por variável de ambiente DATABASE_URL:
      - Definida → PostgreSQL (Supabase)
      - Ausente   → SQLite local (fallback padrão)
    """

    def __init__(self, db_path="data/db/cvm_financials.db"):
        self._engine = self._build_engine(db_path)
        self._init_db()

    @staticmethod
    def _build_engine(db_path: str) -> Engine:
        url = os.getenv("DATABASE_URL", "")
        if url:
            return create_engine(
                url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=300,
            )
        abs_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        return create_engine(
            f"sqlite:///{abs_path}",
            connect_args={"check_same_thread": False},
        )

    def _init_db(self):
        """Creates the necessary tables if they don't exist."""
        init_db_tables(self._engine)

    def _upsert_company_metadata(self, conn, company_name: str, cvm_code: int,
                                 company_type: str, setor_cvm: str | None = None,
                                 ticker_b3: str | None = None,
                                 cnpj: str | None = None) -> None:
        """Persiste metadados na tabela companies (se existir). Idempotente."""
        updated_at = datetime.utcnow().replace(microsecond=0).isoformat()

        if ticker_b3 and ticker_b3.endswith(".SA"):
            ticker_b3 = ticker_b3[:-3]

        # Resolve ticker_b3 and cnpj if not provided
        if not ticker_b3 or not cnpj:
            from src.companies.identity import CompanyIdentityResolver
            resolver = CompanyIdentityResolver()
            identity = resolver.resolve(int(cvm_code))
            if identity:
                if not ticker_b3 and identity.ticker_b3:
                    ticker_b3 = identity.ticker_b3
                    if ticker_b3.endswith(".SA"):
                        ticker_b3 = ticker_b3[:-3]
                if not cnpj and identity.cnpj:
                    cnpj = identity.cnpj

        if cnpj:
            from src.companies.cnpj import validate_cnpj
            if validate_cnpj(cnpj):
                cnpj = "".join(c for c in str(cnpj) if c.isdigit())
            else:
                cnpj = None

        gics = resolve_gics_classification(
            sector_name=setor_cvm,
            setor_cvm=setor_cvm,
        )
        params = {
            "cd": int(cvm_code),
            "name": company_name,
            "ctype": company_type or "comercial",
            "setor": setor_cvm,
            "ticker": ticker_b3,
            "cnpj": cnpj,
            "updated_at": updated_at,
            "gics_sector": gics.gics_sector if gics else None,
            "gics_sector_slug": gics.gics_sector_slug if gics else None,
            "gics_industry_group": gics.gics_industry_group if gics else None,
            "gics_industry": gics.gics_industry if gics else None,
            "gics_sub_industry": gics.gics_sub_industry if gics else None,
        }

        conn.execute(text("""
            INSERT INTO companies
                (
                    cd_cvm, company_name, company_type, setor_cvm, ticker_b3, cnpj,
                    gics_sector, gics_sector_slug, gics_industry_group,
                    gics_industry, gics_sub_industry, updated_at
                )
            SELECT
                :cd, :name, :ctype, :setor, :ticker, :cnpj,
                :gics_sector, :gics_sector_slug, :gics_industry_group,
                :gics_industry, :gics_sub_industry, :updated_at
            WHERE NOT EXISTS (
                SELECT 1 FROM companies WHERE cd_cvm = :cd
            )
        """), params)
        conn.execute(text("""
            UPDATE companies
            SET company_name = :name,
                company_type = :ctype,
                setor_cvm    = COALESCE(:setor, setor_cvm),
                ticker_b3    = COALESCE(:ticker, ticker_b3),
                cnpj         = COALESCE(:cnpj, cnpj),
                gics_sector  = COALESCE(:gics_sector, gics_sector),
                gics_sector_slug = COALESCE(:gics_sector_slug, gics_sector_slug),
                gics_industry_group = COALESCE(:gics_industry_group, gics_industry_group),
                gics_industry = COALESCE(:gics_industry, gics_industry),
                gics_sub_industry = COALESCE(:gics_sub_industry, gics_sub_industry),
                updated_at   = :updated_at
            WHERE cd_cvm = :cd
        """), params)
        # The curated classification is canonical once loaded; it overrides any label written above.
        from src.companies.classification import materialize_company
        materialize_company(conn, int(cvm_code))

    def _to_sql_with_retry(self, table_name: str, df: pd.DataFrame, conn) -> None:
        """Retry writes for transient SQLite lock errors without masking final failures."""
        dialect = self._engine.dialect.name
        max_retries = SQLITE_WRITE_MAX_RETRIES if dialect == "sqlite" else 1
        chunksize = self._resolve_to_sql_chunksize(df)
        attempt = 0
        while True:
            attempt += 1
            try:
                df.to_sql(
                    table_name,
                    conn,
                    if_exists='append',
                    index=False,
                    method='multi',
                    chunksize=chunksize,
                )
                return
            except OperationalError as exc:
                if attempt >= max_retries:
                    raise
                sleep_s = SQLITE_WRITE_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Transient DB write failure for table=%s attempt=%s/%s error=%s",
                    table_name,
                    attempt,
                    max_retries,
                    exc,
                )
                time.sleep(sleep_s)

    def _resolve_to_sql_chunksize(self, df: pd.DataFrame) -> int:
        """Keep SQLite inserts below the engine parameter limit for multi-row writes."""
        if self._engine.dialect.name != "sqlite":
            return DEFAULT_TO_SQL_CHUNKSIZE

        column_count = max(1, len(getattr(df, "columns", [])))
        safe_chunksize = SQLITE_SAFE_MAX_VARIABLES // column_count
        return max(1, min(DEFAULT_TO_SQL_CHUNKSIZE, safe_chunksize))

    @staticmethod
    def _qa_year(period):
        label = str(period or '')
        if re.fullmatch(r'\d{4}', label):
            return int(label)
        if re.fullmatch(r'[1-4]Q\d{2}', label):
            return 2000 + int(label[2:])
        return None

    def insert_company_data(self, company_name: str, cvm_code: int, company_type: str,
                            processed_reports: dict, qa_logs: list,
                            setor_cvm: str | None = None,
                            ticker_b3: str | None = None,
                            cnpj: str | None = None):
        """
        Melts wide dataframes into long format and inserts them into the database.
        Replace only imported statement-years, preserving source observations.
        Financial rows, lineage and QA are committed in one transaction.
        """
        with self._engine.begin() as conn:
            # 0. Persistir metadados na tabela companies
            # Use nested transaction so metadata failures don't abort main data writes on PostgreSQL.
            try:
                with conn.begin_nested():
                    self._upsert_company_metadata(
                        conn, company_name, cvm_code, company_type, setor_cvm, ticker_b3, cnpj
                    )
            except Exception as exc:
                logger.warning(
                    "Non-fatal company metadata upsert failure "
                    "(table may not exist or schema may differ): cd_cvm=%s company_name=%r error_type=%s error=%s",
                    cvm_code,
                    company_name,
                    exc.__class__.__name__,
                    exc,
                )

            # Scope replacements to explicitly imported statement-years.
            scopes = set()
            for statement, frame in processed_reports.items():
                if frame is None:
                    continue
                for col in frame.columns:
                    label = str(col)
                    if re.fullmatch(r"\d{4}", label):
                        scopes.add((statement, int(label)))
                    elif re.fullmatch(r"[1-4]Q\d{2}", label):
                        scopes.add((statement, 2000 + int(label[2:])))
            for statement, year in scopes:
                params = {"cvm": int(cvm_code), "stmt": statement, "year": year}
                for table in ("financial_reports", "qa_logs"):
                    conn.execute(text(f'DELETE FROM {table} WHERE "CD_CVM" = :cvm '
                                      'AND "STATEMENT_TYPE" = :stmt AND "REPORT_YEAR" = :year'), params)
                conn.execute(text('DELETE FROM financial_value_lineage WHERE cd_cvm = :cvm '
                                  'AND statement_type = :stmt AND report_year = :year'), params)
            imported_at = datetime.now(timezone.utc).isoformat()
            observation_rows, lineage_rows = [], []
            for statement, frame in processed_reports.items():
                if frame is None:
                    continue
                for observation in frame.attrs.get('source_observations', []):
                    end = observation.get('DT_FIM_EXERC') or observation.get('DT_REFER') or ''
                    year = int(str(end)[:4]) if str(end)[:4].isdigit() else None
                    observation_rows.append(dict(
                        id=observation['observation_id'], cvm=int(cvm_code), stmt=statement, year=year,
                        payload=json.dumps(observation, ensure_ascii=False, default=str, allow_nan=False),
                        imported=imported_at))
                for cell in frame.attrs.get('value_lineage', []):
                    lineage_rows.append(dict(cvm=int(cvm_code), stmt=statement, year=cell['year'], period=cell['period'],
                                             line=cell['line_id_base'], payload=json.dumps(cell, ensure_ascii=False)))
            # One executemany per table instead of one statement per row (#585).
            if observation_rows:
                conn.execute(text('''
                    INSERT INTO financial_source_observations
                    (observation_id, cd_cvm, statement_type, report_year, payload_json, imported_at)
                    VALUES (:id, :cvm, :stmt, :year, :payload, :imported)
                    ON CONFLICT (observation_id) DO NOTHING
                '''), observation_rows)
            if lineage_rows:
                conn.execute(text('''
                    INSERT INTO financial_value_lineage
                    (cd_cvm, statement_type, report_year, period_label, line_id_base, payload_json)
                    VALUES (:cvm, :stmt, :year, :period, :line, :payload)
                '''), lineage_rows)

            # 2. Insert QA Logs
            if qa_logs:
                df_qa = pd.DataFrame(qa_logs)
                df_qa['COMPANY_NAME'] = company_name
                df_qa['CD_CVM'] = int(cvm_code)
                df_qa['REPORT_YEAR'] = [event.get('year') or self._qa_year(event.get('period')) for event in qa_logs]
                df_qa['DETAILS_JSON'] = [json.dumps(event, ensure_ascii=False, default=str, allow_nan=False) for event in qa_logs]

                col_map = {
                    'type': 'ERROR_TYPE',
                    'statement': 'STATEMENT_TYPE',
                    'period': 'PERIOD',
                    'line_id_base': 'LINE_ID_BASE',
                    'cd_conta': 'CD_CONTA',
                    'description': 'DESCRIPTION',
                    'action': 'ACTION',
                }

                db_cols = {k: v for k, v in col_map.items() if k in df_qa.columns}
                if db_cols:
                    df_qa = df_qa.rename(columns=db_cols)
                    db_schema_cols = [
                        'COMPANY_NAME', 'CD_CVM', 'ERROR_TYPE', 'STATEMENT_TYPE',
                        'PERIOD', 'LINE_ID_BASE', 'CD_CONTA', 'DESCRIPTION', 'ACTION', 'REPORT_YEAR', 'DETAILS_JSON',
                    ]
                    df_to_insert = df_qa[[c for c in db_schema_cols if c in df_qa.columns]]
                    self._to_sql_with_retry('qa_logs', df_to_insert, conn)

            # 3. Melt and Insert Financial Reports
            all_long_dfs = []

            for statement_type, df_wide in processed_reports.items():
                if df_wide.empty:
                    continue

                metadata_cols = [
                    'LINE_ID_BASE', 'CD_CONTA', 'DS_CONTA', 'DS_CONTA_norm',
                    'QA_CONFLICT', 'STANDARD_NAME', 'COMPANY_TYPE',
                ]
                id_vars    = [c for c in metadata_cols if c in df_wide.columns]
                value_vars = []
                for c in df_wide.columns:
                    if c in id_vars:
                        continue
                    col = str(c)
                    if col.isdigit() and len(col) == 4:
                        value_vars.append(c)
                        continue
                    if re.match(r'^\dQ(\d{2})$', col):
                        value_vars.append(c)

                if not value_vars:
                    continue

                # Audit attrs are persisted above; do not copy them through tabular reshaping.
                df_long = pd.DataFrame(df_wide, copy=True).melt(
                    id_vars=id_vars,
                    value_vars=value_vars,
                    var_name='PERIOD_LABEL',
                    value_name='VL_CONTA',
                )
                if not df_wide.attrs.get('value_lineage'):
                    df_long = df_long.dropna(subset=['VL_CONTA'])

                if df_long.empty:
                    continue

                df_long['COMPANY_NAME']   = company_name
                df_long['CD_CVM']         = int(cvm_code)
                df_long['COMPANY_TYPE']   = company_type
                df_long['STATEMENT_TYPE'] = statement_type

                                # Vectorized extract_year
                df_long['REPORT_YEAR'] = None
                labels = df_long['PERIOD_LABEL'].astype(str)
                # Annual: 2024
                mask_ann = labels.str.match(r'^\d{4}$')
                df_long.loc[mask_ann, 'REPORT_YEAR'] = labels[mask_ann].astype(int)
                # Quarterly: 1Q24
                mask_qtr = labels.str.match(r'^\dQ(\d{2})$')
                if mask_qtr.any():
                    yy = labels[mask_qtr].str.extract(r'\dQ(\d{2})')[0].astype(int)
                    df_long.loc[mask_qtr, 'REPORT_YEAR'] = 2000 + yy

                if 'CD_CONTA' not in df_long.columns:
                    df_long['CD_CONTA'] = None
                if 'STANDARD_NAME' not in df_long.columns:
                    df_long['STANDARD_NAME'] = None
                if 'QA_CONFLICT' not in df_long.columns:
                    df_long['QA_CONFLICT'] = False

                cells = {(cell['line_id_base'], cell['period']): cell for cell in df_wide.attrs.get('value_lineage', [])}
                if cells:
                    df_long['QA_CONFLICT'] = [cells.get((row.LINE_ID_BASE, row.PERIOD_LABEL), {}).get('status', 'unavailable') not in {'reported', 'calculated'} for row in df_long.itertuples()]
                    df_long['DS_CONTA'] = [cells.get((row.LINE_ID_BASE, row.PERIOD_LABEL), {}).get('description', row.DS_CONTA) for row in df_long.itertuples()]

                final_cols = [
                    'COMPANY_NAME', 'CD_CVM', 'COMPANY_TYPE', 'STATEMENT_TYPE',
                    'REPORT_YEAR', 'PERIOD_LABEL', 'LINE_ID_BASE', 'CD_CONTA',
                    'DS_CONTA', 'STANDARD_NAME', 'QA_CONFLICT', 'VL_CONTA',
                ]
                all_long_dfs.append(df_long[final_cols])

            if all_long_dfs:
                final_df = pd.concat(all_long_dfs, ignore_index=True)
                unique_key_cols = ["CD_CVM", "STATEMENT_TYPE", "PERIOD_LABEL", "LINE_ID_BASE"]
                before_dedupe = len(final_df)
                final_df = final_df.drop_duplicates(subset=unique_key_cols, keep="last").reset_index(drop=True)
                removed = before_dedupe - len(final_df)
                if removed > 0:
                    logger.warning(
                        "Deduplicated %s financial_reports rows before insert "
                        "for cd_cvm=%s company_name=%r",
                        removed,
                        cvm_code,
                        company_name,
                    )
                self._to_sql_with_retry('financial_reports', final_df, conn)
                return len(final_df)

            return 0


def init_energy_kpi_db(settings) -> None:
    """Ensure the energy KPI database and all its tables exist.

    Uses a separate SQLite file (energy_kpis.db) independent of
    cvm_financials.db so macro KPI data can be refreshed and shipped
    independently with zero migration risk.
    """
    get_energy_kpi_engine(settings)
