"""Physical schema for the isolated canonical entity registry foundation.

The registry is deliberately created through an explicit API.  It is not part
of the legacy financial database startup initializer or a live migration.
"""
from __future__ import annotations

from sqlalchemy import Engine, inspect, text

from src.platform.db import configure_sqlite_foreign_keys


ENTITY_KINDS = (
    "organization",
    "economic_group",
    "security_class",
    "concession",
    "plant_or_asset",
    "market_parcel",
)
LIFECYCLE_STATUSES = ("active", "retired", "deprecated")
ORIGINS = ("source_ingestion", "user", "reviewer", "derived")
SOURCE_CLASSES = ("official_primary", "official_external", "external", "derived")
SOURCE_STATUSES = ("available", "unavailable", "failed", "unsupported")
IDENTIFIER_STRENGTHS = ("strong", "weak")
IDENTIFIER_CLAIM_STATUSES = ("accepted", "conflicted", "blocked")
ALIAS_TYPES = (
    "legal_name",
    "trade_name",
    "brand",
    "ticker_display",
    "former_name",
    "source_alias",
)
ORGANIZATION_FACETS = ("legal_entity", "issuer", "regulated_agent", "vehicle")
_REQUIRED_TABLES = {
    "entity_registry_entities",
    "entity_registry_evidence",
    "entity_registry_identifier_claims",
    "entity_registry_alias_claims",
    "entity_registry_organization_facets",
    "entity_registry_lifecycle_events",
    "entity_registry_identifier_guards",
}


def ensure_entity_registry_schema(engine: Engine) -> None:
    """Idempotently create registry tables in an explicit fresh/sandbox call.

    This function is intentionally separate from ``init_db_tables``.  The
    approved migration runner, backfill, and installed-database cutover remain
    future work.
    """
    dialect = engine.dialect.name
    configure_sqlite_foreign_keys(engine)
    if dialect == "sqlite":
        with engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_entities (
                entity_id TEXT PRIMARY KEY,
                entity_kind TEXT NOT NULL CHECK (entity_kind IN (
                    'organization', 'economic_group', 'security_class',
                    'concession', 'plant_or_asset', 'market_parcel'
                )),
                lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
                    'active', 'retired', 'deprecated'
                )),
                lifecycle_reason TEXT,
                created_origin TEXT NOT NULL CHECK (created_origin IN (
                    'source_ingestion', 'user', 'reviewer', 'derived'
                )),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_evidence (
                evidence_id TEXT PRIMARY KEY,
                source_class TEXT NOT NULL CHECK (source_class IN (
                    'official_primary', 'official_external', 'external', 'derived'
                )),
                source_status TEXT NOT NULL CHECK (source_status IN (
                    'available', 'unavailable', 'failed', 'unsupported'
                )),
                source_reference TEXT NOT NULL,
                source_snapshot_reference TEXT,
                raw_payload_reference TEXT,
                observed_at TEXT,
                retrieved_at TEXT,
                created_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_organization_facets (
                facet_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                facet TEXT NOT NULL CHECK (facet IN (
                    'legal_entity', 'issuer', 'regulated_agent', 'vehicle'
                )),
                eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('active', 'inactive')),
                origin TEXT NOT NULL CHECK (origin IN ('source_ingestion', 'user', 'reviewer', 'derived')),
                evidence_id TEXT REFERENCES entity_registry_evidence(evidence_id)
                    ON DELETE RESTRICT,
                evidence_status TEXT NOT NULL CHECK (evidence_status IN (
                    'available', 'none', 'unavailable', 'failed', 'unsupported'
                )),
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_lifecycle_events (
                lifecycle_event_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN (
                    'active', 'retired', 'deprecated'
                )),
                reason TEXT NOT NULL CHECK (length(reason) > 0),
                origin TEXT NOT NULL CHECK (origin IN ('source_ingestion', 'user', 'reviewer', 'derived')),
                evidence_id TEXT NOT NULL REFERENCES entity_registry_evidence(evidence_id)
                    ON DELETE RESTRICT,
                evidence_status TEXT NOT NULL CHECK (evidence_status IN (
                    'available', 'unavailable', 'failed', 'unsupported'
                )),
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_identifier_guards (
                guard_key TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_identifier_claims (
                claim_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                namespace TEXT NOT NULL,
                raw_value TEXT NOT NULL CHECK (length(raw_value) > 0),
                normalized_value TEXT NOT NULL CHECK (length(normalized_value) > 0),
                normalizer_version TEXT NOT NULL,
                scope_authority TEXT,
                scope_country TEXT,
                scope_context TEXT,
                identifier_strength TEXT NOT NULL CHECK (identifier_strength IN ('strong', 'weak')),
                claim_status TEXT NOT NULL CHECK (claim_status IN ('accepted', 'conflicted', 'blocked')),
                origin TEXT NOT NULL CHECK (origin IN ('source_ingestion', 'user', 'reviewer', 'derived')),
                evidence_id TEXT REFERENCES entity_registry_evidence(evidence_id)
                    ON DELETE RESTRICT,
                evidence_status TEXT NOT NULL CHECK (evidence_status IN (
                    'available', 'none', 'unavailable', 'failed', 'unsupported'
                )),
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_alias_claims (
                alias_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                alias_type TEXT NOT NULL CHECK (alias_type IN (
                    'legal_name', 'trade_name', 'brand', 'ticker_display',
                    'former_name', 'source_alias'
                )),
                raw_value TEXT NOT NULL CHECK (length(raw_value) > 0),
                locale TEXT,
                origin TEXT NOT NULL CHECK (origin IN ('source_ingestion', 'user', 'reviewer', 'derived')),
                evidence_id TEXT REFERENCES entity_registry_evidence(evidence_id)
                    ON DELETE RESTRICT,
                evidence_status TEXT NOT NULL CHECK (evidence_status IN (
                    'available', 'none', 'unavailable', 'failed', 'unsupported'
                )),
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))

        for ddl in (
            "CREATE INDEX IF NOT EXISTS idx_er_entities_kind ON entity_registry_entities(entity_kind, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_er_identifier_lookup ON entity_registry_identifier_claims("
            "namespace, normalized_value, scope_authority, claim_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_identifier_entity ON entity_registry_identifier_claims(entity_id, claim_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_alias_entity ON entity_registry_alias_claims(entity_id, alias_type)",
            "CREATE INDEX IF NOT EXISTS idx_er_facet_lookup ON entity_registry_organization_facets(entity_id, facet, eligibility_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_lifecycle_entity ON entity_registry_lifecycle_events(entity_id, system_from)",
        ):
            conn.execute(text(ddl))

        if dialect == "sqlite":
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS entity_registry_entities_no_id_update
                BEFORE UPDATE OF entity_id ON entity_registry_entities
                BEGIN
                    SELECT RAISE(ABORT, 'entity_id is immutable');
                END
            """))
        elif dialect == "postgresql":
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION entity_registry_prevent_entity_id_update()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.entity_id IS DISTINCT FROM OLD.entity_id THEN
                        RAISE EXCEPTION 'entity_id is immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$
            """))
            conn.execute(text("""
                DROP TRIGGER IF EXISTS entity_registry_entities_no_id_update
                ON entity_registry_entities
            """))
            conn.execute(text("""
                CREATE TRIGGER entity_registry_entities_no_id_update
                BEFORE UPDATE OF entity_id ON entity_registry_entities
                FOR EACH ROW EXECUTE FUNCTION entity_registry_prevent_entity_id_update()
            """))


def validate_entity_registry_schema(engine: Engine) -> None:
    """Validate an already-provisioned registry schema without emitting DDL."""
    configure_sqlite_foreign_keys(engine)
    tables = set(inspect(engine).get_table_names())
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise ValueError(f"entity registry schema is missing: {', '.join(missing)}")
