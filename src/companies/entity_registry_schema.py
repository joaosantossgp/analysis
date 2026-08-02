"""Physical schema for the isolated canonical entity registry foundation.

The registry is deliberately created through an explicit API.  It is not part
of the legacy financial database startup initializer or a live migration.
"""
from __future__ import annotations

import re

from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import NoInspectionAvailable

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
ASSERTION_STATES = (
    "draft", "submitted", "accepted", "rejected", "superseded", "withdrawn", "conflicted", "blocked",
)
RELATIONSHIP_DIMENSIONS = (
    "legal_ownership", "voting_interest", "economic_interest", "control",
    "accounting_treatment", "operational_role", "holder",
)
OPERATIONAL_ROLES = ("owner", "operator", "concession_holder", "service_provider")
REVIEW_STATUSES = ("pending", "accepted", "rejected", "needs_review")
RELATIONSHIP_STATUSES = ("accepted", "rejected", "superseded", "withdrawn", "conflicted", "blocked")
LINEAGE_STATUSES = RELATIONSHIP_STATUSES
LINEAGE_PREDICATES = (
    "legal_continuation", "merged_into", "split_from", "spun_off_from", "succeeded_by", "acquired_from",
)
_REQUIRED_TABLES = {
    "entity_registry_entities",
    "entity_registry_evidence",
    "entity_registry_identifier_claims",
    "entity_registry_alias_claims",
    "entity_registry_organization_facets",
    "entity_registry_lifecycle_events",
    "entity_registry_identifier_guards",
    "entity_registry_assertions",
    "entity_registry_relationships",
    "entity_registry_lineage",
    "entity_registry_resolution_policies",
    "entity_registry_resolution_overrides",
    "entity_registry_policy_activations",
    "entity_registry_conflicts",
}
_FOUNDATION_TABLES = _REQUIRED_TABLES - {
    "entity_registry_assertions", "entity_registry_relationships", "entity_registry_lineage",
    "entity_registry_resolution_policies", "entity_registry_resolution_overrides", "entity_registry_policy_activations", "entity_registry_conflicts",
}
_REQUIRED_FOREIGN_KEYS = {
    "entity_registry_identifier_claims": {
        ("entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("evidence_id",): ("entity_registry_evidence", ("evidence_id",)),
    },
    "entity_registry_alias_claims": {
        ("entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("evidence_id",): ("entity_registry_evidence", ("evidence_id",)),
    },
    "entity_registry_organization_facets": {
        ("entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("evidence_id",): ("entity_registry_evidence", ("evidence_id",)),
    },
    "entity_registry_lifecycle_events": {
        ("entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("evidence_id",): ("entity_registry_evidence", ("evidence_id",)),
    },
    "entity_registry_assertions": {
        ("subject_entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("evidence_id",): ("entity_registry_evidence", ("evidence_id",)),
        ("supersedes_assertion_id",): ("entity_registry_assertions", ("assertion_id",)),
    },
    "entity_registry_relationships": {
        ("subject_entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("object_entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("assertion_id",): ("entity_registry_assertions", ("assertion_id",)),
    },
    "entity_registry_lineage": {
        ("predecessor_entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("successor_entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("assertion_id",): ("entity_registry_assertions", ("assertion_id",)),
    },
    "entity_registry_resolution_overrides": {
        ("entity_id",): ("entity_registry_entities", ("entity_id",)),
        ("assertion_id",): ("entity_registry_assertions", ("assertion_id",)),
        ("policy_id", "policy_version"): ("entity_registry_resolution_policies", ("policy_id", "version")),
        ("reverses_override_id",): ("entity_registry_resolution_overrides", ("override_id",)),
    },
}
_REQUIRED_INDEXES = {
    "idx_er_entities_kind": ("entity_registry_entities", ("entity_kind", "entity_id"), False),
    "idx_er_identifier_lookup": (
        "entity_registry_identifier_claims",
        ("namespace", "normalized_value", "scope_authority", "scope_country", "scope_context", "claim_status"),
        False,
    ),
    "idx_er_identifier_entity": ("entity_registry_identifier_claims", ("entity_id", "claim_status"), False),
    "idx_er_alias_entity": ("entity_registry_alias_claims", ("entity_id", "alias_type"), False),
    "idx_er_facet_lookup": ("entity_registry_organization_facets", ("entity_id", "facet", "eligibility_status"), False),
    "idx_er_lifecycle_entity": ("entity_registry_lifecycle_events", ("entity_id", "system_from"), False),
    "idx_er_assertion_lookup": (
        "entity_registry_assertions",
        ("subject_entity_id", "domain", "attribute", "effective_from", "system_from"),
        False,
    ),
    "idx_er_relationship_subject": (
        "entity_registry_relationships",
        ("subject_entity_id", "dimension", "effective_from", "system_from"),
        False,
    ),
    "idx_er_relationship_object": (
        "entity_registry_relationships",
        ("object_entity_id", "dimension", "effective_from", "system_from"),
        False,
    ),
    "idx_er_lineage_predecessor": ("entity_registry_lineage", ("predecessor_entity_id", "effective_from"), False),
    "idx_er_lineage_successor": ("entity_registry_lineage", ("successor_entity_id", "effective_from"), False),
    "idx_er_policy_lookup": (
        "entity_registry_resolution_policies",
        ("domain", "attribute", "consumer_scope", "effective_from", "system_from"),
        False,
    ),
    "idx_er_policy_activation_lookup": (
        "entity_registry_policy_activations",
        ("domain", "attribute", "consumer_scope", "effective_from", "system_from"),
        False,
    ),
    "idx_er_override_lookup": (
        "entity_registry_resolution_overrides",
        ("entity_id", "policy_id", "policy_version", "effective_from", "system_from"),
        False,
    ),
}
_REQUIRED_CHECK_FRAGMENTS = {
    "entity_registry_entities": (
        "entity_kind in ('organization', 'economic_group', 'security_class', 'concession', 'plant_or_asset', 'market_parcel')",
        "lifecycle_status in ('active', 'retired', 'deprecated')",
        "created_origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
    ),
    "entity_registry_evidence": (
        "source_class in ('official_primary', 'official_external', 'external', 'derived')",
        "source_status in ('available', 'unavailable', 'failed', 'unsupported')",
    ),
    "entity_registry_identifier_claims": (
        "length(raw_value) > 0", "length(normalized_value) > 0",
        "identifier_strength in ('strong', 'weak')",
        "claim_status in ('accepted', 'conflicted', 'blocked')",
        "origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
        "evidence_status in ('available', 'none', 'unavailable', 'failed', 'unsupported')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_alias_claims": (
        "alias_type in ('legal_name', 'trade_name', 'brand', 'ticker_display', 'former_name', 'source_alias')",
        "length(raw_value) > 0", "origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
        "evidence_status in ('available', 'none', 'unavailable', 'failed', 'unsupported')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_organization_facets": (
        "facet in ('legal_entity', 'issuer', 'regulated_agent', 'vehicle')",
        "eligibility_status in ('active', 'inactive')",
        "origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
        "evidence_status in ('available', 'none', 'unavailable', 'failed', 'unsupported')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_lifecycle_events": (
        "lifecycle_status in ('active', 'retired', 'deprecated')", "length(reason) > 0",
        "origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
        "evidence_status in ('available', 'unavailable', 'failed', 'unsupported')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_assertions": (
        "assertion_state in ('draft', 'submitted', 'accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked')",
        "origin in ('source_ingestion', 'user', 'reviewer', 'derived')",
        "review_status in ('pending', 'accepted', 'rejected', 'needs_review')",
        "evidence_status in ('available', 'none', 'unavailable', 'failed', 'unsupported')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_relationships": (
        "dimension in ('legal_ownership', 'voting_interest', 'economic_interest', 'control', 'accounting_treatment', 'operational_role', 'holder')",
        "relationship_status in ('accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_lineage": (
        "predicate in ('legal_continuation', 'merged_into', 'split_from', 'spun_off_from', 'succeeded_by', 'acquired_from')",
        "lineage_status in ('accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked')",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_resolution_policies": (
        "length(domain) > 0", "length(attribute) > 0",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
    "entity_registry_resolution_overrides": (
        "length(reason) > 0", "length(actor_id) > 0",
        "effective_to is null or effective_from < effective_to",
        "system_to is null or system_from < system_to",
    ),
}


def ensure_entity_registry_schema(engine: Engine) -> None:
    """Idempotently create registry tables in an explicit fresh/sandbox call.

    This function is intentionally separate from ``init_db_tables``.  The
    approved migration runner, backfill, and installed-database cutover remain
    future work.
    """
    try:
        existing_tables = set(inspect(engine).get_table_names())
    except NoInspectionAvailable:
        # Portable DDL test doubles are intentionally execution-only. Real
        # SQLAlchemy engines remain fail-closed against partial registries.
        existing_tables = set()
    missing_tables = _REQUIRED_TABLES - existing_tables
    if existing_tables & _FOUNDATION_TABLES and missing_tables:
        raise ValueError("partial entity registry schema requires an approved migration")
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
                source_authority TEXT,
                qualified_namespace TEXT,
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
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_assertions (
                assertion_id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                domain TEXT NOT NULL CHECK (length(domain) > 0),
                attribute TEXT NOT NULL CHECK (length(attribute) > 0),
                value_json TEXT NOT NULL,
                assertion_state TEXT NOT NULL CHECK (assertion_state IN (
                    'draft', 'submitted', 'accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked'
                )),
                review_status TEXT NOT NULL CHECK (review_status IN ('pending', 'accepted', 'rejected', 'needs_review')),
                origin TEXT NOT NULL CHECK (origin IN ('source_ingestion', 'user', 'reviewer', 'derived')),
                actor_id TEXT NOT NULL CHECK (length(actor_id) > 0),
                evidence_id TEXT REFERENCES entity_registry_evidence(evidence_id) ON DELETE RESTRICT,
                evidence_status TEXT NOT NULL CHECK (evidence_status IN (
                    'available', 'none', 'unavailable', 'failed', 'unsupported'
                )),
                reason TEXT,
                supersedes_assertion_id TEXT REFERENCES entity_registry_assertions(assertion_id) ON DELETE RESTRICT,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_relationships (
                relationship_id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                object_entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                dimension TEXT NOT NULL CHECK (dimension IN (
                    'legal_ownership', 'voting_interest', 'economic_interest', 'control',
                    'accounting_treatment', 'operational_role', 'holder'
                )),
                operational_role TEXT,
                payload_json TEXT NOT NULL,
                assertion_id TEXT NOT NULL REFERENCES entity_registry_assertions(assertion_id)
                    ON DELETE RESTRICT,
                relationship_status TEXT NOT NULL CHECK (relationship_status IN (
                    'accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked'
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
            CREATE TABLE IF NOT EXISTS entity_registry_lineage (
                lineage_id TEXT PRIMARY KEY,
                predecessor_entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                successor_entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id)
                    ON DELETE RESTRICT,
                predicate TEXT NOT NULL CHECK (predicate IN (
                    'legal_continuation', 'merged_into', 'split_from', 'spun_off_from', 'succeeded_by', 'acquired_from'
                )),
                assertion_id TEXT NOT NULL REFERENCES entity_registry_assertions(assertion_id)
                    ON DELETE RESTRICT,
                lineage_status TEXT NOT NULL CHECK (lineage_status IN (
                    'accepted', 'rejected', 'superseded', 'withdrawn', 'conflicted', 'blocked'
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
            CREATE TABLE IF NOT EXISTS entity_registry_resolution_policies (
                policy_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                domain TEXT NOT NULL CHECK (length(domain) > 0),
                attribute TEXT NOT NULL CHECK (length(attribute) > 0),
                consumer_scope TEXT,
                eligible_assertion_states_json TEXT NOT NULL,
                eligible_origins_json TEXT NOT NULL,
                eligible_evidence_statuses_json TEXT NOT NULL,
                origin_precedence_json TEXT NOT NULL,
                allows_user_override INTEGER NOT NULL CHECK (allows_user_override IN (0, 1)),
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                PRIMARY KEY (policy_id, version),
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_resolution_overrides (
                override_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id) ON DELETE RESTRICT,
                domain TEXT NOT NULL,
                attribute TEXT NOT NULL,
                consumer_scope TEXT,
                policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                assertion_id TEXT NOT NULL REFERENCES entity_registry_assertions(assertion_id) ON DELETE RESTRICT,
                actor_id TEXT NOT NULL CHECK (length(actor_id) > 0),
                reason TEXT NOT NULL CHECK (length(reason) > 0),
                reverses_override_id TEXT REFERENCES entity_registry_resolution_overrides(override_id)
                    ON DELETE RESTRICT,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                FOREIGN KEY (policy_id, policy_version)
                    REFERENCES entity_registry_resolution_policies(policy_id, version) ON DELETE RESTRICT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_policy_activations (
                activation_id TEXT PRIMARY KEY,
                policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                domain TEXT NOT NULL,
                attribute TEXT NOT NULL,
                consumer_scope TEXT,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                supersedes_activation_id TEXT REFERENCES entity_registry_policy_activations(activation_id) ON DELETE RESTRICT,
                FOREIGN KEY (policy_id, policy_version) REFERENCES entity_registry_resolution_policies(policy_id, version) ON DELETE RESTRICT,
                CHECK (effective_to IS NULL OR effective_from < effective_to),
                CHECK (system_to IS NULL OR system_from < system_to)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_registry_conflicts (
                conflict_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL REFERENCES entity_registry_entities(entity_id) ON DELETE RESTRICT,
                domain TEXT NOT NULL,
                attribute TEXT NOT NULL,
                assertion_ids_json TEXT NOT NULL,
                dedup_key TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_version INTEGER NOT NULL,
                effective_from TEXT NOT NULL,
                effective_to TEXT,
                system_from TEXT NOT NULL,
                system_to TEXT,
                detected_at TEXT NOT NULL,
                detected_actor TEXT NOT NULL,
                detected_origin TEXT NOT NULL,
                queried_effective_as_of TEXT NOT NULL,
                queried_system_as_of TEXT NOT NULL,
                resolution_status TEXT NOT NULL CHECK (resolution_status IN ('unresolved', 'resolved', 'reversed')),
                resolved_at TEXT,
                resolved_actor TEXT,
                resolved_origin TEXT,
                resolution_reason TEXT,
                reversed_at TEXT,
                reversed_actor TEXT,
                reversed_origin TEXT,
                reversal_reason TEXT,
                CHECK (effective_to IS NULL OR effective_from < effective_to)
            )
        """))

        for ddl in (
            "CREATE INDEX IF NOT EXISTS idx_er_entities_kind ON entity_registry_entities(entity_kind, entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_er_identifier_lookup ON entity_registry_identifier_claims("
            "namespace, normalized_value, scope_authority, scope_country, scope_context, claim_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_identifier_entity ON entity_registry_identifier_claims(entity_id, claim_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_alias_entity ON entity_registry_alias_claims(entity_id, alias_type)",
            "CREATE INDEX IF NOT EXISTS idx_er_facet_lookup ON entity_registry_organization_facets(entity_id, facet, eligibility_status)",
            "CREATE INDEX IF NOT EXISTS idx_er_lifecycle_entity ON entity_registry_lifecycle_events(entity_id, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_assertion_lookup ON entity_registry_assertions(subject_entity_id, domain, attribute, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_relationship_subject ON entity_registry_relationships(subject_entity_id, dimension, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_relationship_object ON entity_registry_relationships(object_entity_id, dimension, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_lineage_predecessor ON entity_registry_lineage(predecessor_entity_id, effective_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_lineage_successor ON entity_registry_lineage(successor_entity_id, effective_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_policy_lookup ON entity_registry_resolution_policies(domain, attribute, consumer_scope, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_policy_activation_lookup ON entity_registry_policy_activations(domain, attribute, consumer_scope, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_override_lookup ON entity_registry_resolution_overrides(entity_id, policy_id, policy_version, effective_from, system_from)",
            "CREATE INDEX IF NOT EXISTS idx_er_conflict_lookup ON entity_registry_conflicts(entity_id, domain, attribute, resolution_status)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_er_conflict_unresolved_dedup ON entity_registry_conflicts(dedup_key) WHERE system_to IS NULL",
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
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = sorted(_REQUIRED_TABLES - tables)
    if missing:
        raise ValueError(f"entity registry schema is incomplete: missing {', '.join(missing)}")
    required_columns = {
        "entity_registry_entities": {"entity_id", "entity_kind", "lifecycle_status", "created_origin"},
        "entity_registry_evidence": {
            "evidence_id", "source_class", "source_status", "source_authority",
            "qualified_namespace", "source_reference",
        },
        "entity_registry_identifier_claims": {
            "claim_id", "entity_id", "namespace", "normalized_value", "scope_authority",
            "scope_country", "scope_context", "identifier_strength", "claim_status", "evidence_id",
            "effective_from", "system_from",
        },
        "entity_registry_alias_claims": {"alias_id", "entity_id", "alias_type", "effective_from"},
        "entity_registry_organization_facets": {"facet_id", "entity_id", "facet", "eligibility_status"},
        "entity_registry_lifecycle_events": {"lifecycle_event_id", "entity_id", "lifecycle_status", "evidence_id"},
        "entity_registry_identifier_guards": {"guard_key", "updated_at"},
        "entity_registry_assertions": {
            "assertion_id", "subject_entity_id", "domain", "attribute", "value_json", "assertion_state",
            "review_status", "origin", "actor_id", "evidence_id", "evidence_status", "supersedes_assertion_id",
            "reason", "effective_from", "system_from",
        },
        "entity_registry_relationships": {
            "relationship_id", "subject_entity_id", "object_entity_id", "dimension", "operational_role",
            "payload_json", "assertion_id", "relationship_status", "effective_from", "system_from",
        },
        "entity_registry_lineage": {
            "lineage_id", "predecessor_entity_id", "successor_entity_id", "predicate", "assertion_id",
            "lineage_status", "effective_from", "system_from",
        },
        "entity_registry_resolution_policies": {
            "policy_id", "version", "domain", "attribute", "consumer_scope", "eligible_assertion_states_json",
            "eligible_origins_json", "eligible_evidence_statuses_json", "origin_precedence_json",
            "allows_user_override", "effective_from", "system_from",
        },
        "entity_registry_resolution_overrides": {
            "override_id", "entity_id", "domain", "attribute", "consumer_scope", "policy_id", "policy_version",
            "assertion_id", "actor_id", "reason", "reverses_override_id", "effective_from", "system_from",
        },
        "entity_registry_policy_activations": {
            "activation_id", "policy_id", "policy_version", "domain", "attribute", "consumer_scope",
            "effective_from", "system_from", "supersedes_activation_id",
        },
        "entity_registry_conflicts": {
            "conflict_id", "entity_id", "domain", "attribute", "assertion_ids_json", "dedup_key", "policy_id",
            "policy_version", "effective_from", "system_from", "detected_at", "detected_actor", "detected_origin",
            "queried_effective_as_of", "queried_system_as_of", "resolution_status",
        },
    }
    for table_name, expected in required_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        if not expected.issubset(actual):
            raise ValueError(f"entity registry schema is incomplete: {table_name} columns")

    _validate_foreign_keys(engine, inspector)

    guard_pk = set(inspector.get_pk_constraint("entity_registry_identifier_guards")["constrained_columns"])
    if guard_pk != {"guard_key"}:
        raise ValueError("entity registry schema is incomplete: identifier guard key")
    _validate_indexes(inspector)
    _validate_check_constraints(inspector, engine.dialect.name)

    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            trigger = conn.execute(text("""
                SELECT sql FROM sqlite_master
                WHERE type = 'trigger' AND name = 'entity_registry_entities_no_id_update'
            """)).scalar_one_or_none()
        if trigger is None or "entity_id is immutable" not in trigger:
            raise ValueError("entity registry schema is incomplete: immutable entity trigger")
    elif engine.dialect.name == "postgresql":
        validate_postgresql_registry_safety(engine)


def _validate_foreign_keys(engine: Engine, inspector) -> None:
    for table_name, expected_keys in _REQUIRED_FOREIGN_KEYS.items():
        actual_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        for constrained_columns, (referred_table, referred_columns) in expected_keys.items():
            foreign_key = actual_keys.get(constrained_columns)
            if foreign_key is None or (
                foreign_key["referred_table"], tuple(foreign_key["referred_columns"])
            ) != (referred_table, referred_columns):
                raise ValueError(f"entity registry schema is incomplete: {table_name} foreign keys")
            ondelete = foreign_key.get("options", {}).get("ondelete")
            if engine.dialect.name != "sqlite" and str(ondelete).upper() != "RESTRICT":
                raise ValueError(f"entity registry schema is incomplete: {table_name} foreign keys")

    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            for table_name, expected_keys in _REQUIRED_FOREIGN_KEYS.items():
                grouped_keys: dict[int, list] = {}
                for row in conn.execute(text(f"PRAGMA foreign_key_list({table_name})")).mappings():
                    grouped_keys.setdefault(row["id"], []).append(row)
                actual_keys = {
                    tuple(item["from"] for item in sorted(rows, key=lambda item: item["seq"])): rows[0]
                    for rows in grouped_keys.values()
                }
                for constrained_columns, (referred_table, referred_columns) in expected_keys.items():
                    foreign_key = actual_keys.get(constrained_columns)
                    if foreign_key is None or (
                        foreign_key["table"], tuple(
                            item["to"] for item in sorted(
                                grouped_keys[foreign_key["id"]], key=lambda item: item["seq"]
                            )
                        ), str(foreign_key["on_delete"]).upper()
                    ) != (referred_table, referred_columns, "RESTRICT"):
                        raise ValueError(f"entity registry schema is incomplete: {table_name} foreign keys")


def _validate_indexes(inspector) -> None:
    for index_name, (table_name, columns, unique) in _REQUIRED_INDEXES.items():
        index = next(
            (candidate for candidate in inspector.get_indexes(table_name) if candidate["name"] == index_name),
            None,
        )
        if index is None or tuple(index["column_names"]) != columns or bool(index.get("unique")) != unique:
            raise ValueError("entity registry schema is incomplete: required indexes")


def _validate_check_constraints(inspector, dialect: str) -> None:
    for table_name, expected_fragments in _REQUIRED_CHECK_FRAGMENTS.items():
        actual = tuple(
            _normalize_sql(constraint.get("sqltext", ""))
            for constraint in inspector.get_check_constraints(table_name)
        )
        if any(
            not _has_required_check_expression(_normalize_sql(fragment), actual, dialect)
            for fragment in expected_fragments
        ):
            raise ValueError("entity registry schema is incomplete: check constraints")


def _normalize_sql(value: str) -> str:
    return " ".join(value.lower().split()).replace("( ", "(").replace(" )", ")")


def _has_required_check_expression(expected: str, actual: tuple[str, ...], dialect: str) -> bool:
    expected_expression = _canonicalize_check_expression(expected, dialect)
    return any(
        _canonicalize_check_expression(expression, dialect) == expected_expression
        for expression in actual
    )


def _canonicalize_check_expression(expression: str, dialect: str) -> str:
    normalized = _normalize_sql(expression)
    if normalized.startswith("check "):
        normalized = normalized[6:]
    normalized = _strip_outer_parentheses(normalized)
    if dialect == "postgresql":
        normalized = re.sub(r"::(?:text|character varying|varchar)(?:\[\])?", "", normalized)
        normalized = re.sub(r"= any \(array\[([^\]]+)\]\)", r"in (\1)", normalized)
    normalized = re.sub(r"\(([^()]+)\)", r"\1", normalized)
    return _normalize_sql(normalized)


def _strip_outer_parentheses(expression: str) -> str:
    while expression.startswith("(") and expression.endswith(")"):
        depth = 0
        encloses_all = True
        for index, character in enumerate(expression):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    encloses_all = False
                    break
        if not encloses_all or depth != 0:
            break
        expression = expression[1:-1].strip()
    return expression


def validate_postgresql_registry_safety(engine: Engine) -> None:
    """Validate PostgreSQL trigger/function safety when an operator supplies a live engine."""
    with engine.connect() as conn:
        trigger = conn.execute(text("""
            WITH expected_registry AS (
                SELECT registry_table.oid AS table_oid, registry_schema.nspname AS table_schema,
                       registry_function.oid AS function_oid,
                       function_schema.nspname AS function_schema
                FROM pg_class AS registry_table
                JOIN pg_namespace AS registry_schema ON registry_schema.oid = registry_table.relnamespace
                JOIN pg_proc AS registry_function
                  ON registry_function.proname = 'entity_registry_prevent_entity_id_update'
                 AND registry_function.pronamespace = registry_schema.oid
                 AND registry_function.proargtypes = ''::oidvector
                JOIN pg_namespace AS function_schema ON function_schema.oid = registry_function.pronamespace
                WHERE registry_table.oid = to_regclass('entity_registry_entities')
            )
            SELECT registry.table_oid, registry.table_schema, registry.function_oid, registry.function_schema,
                   trigger.tgenabled, trigger.tgtype,
                   EXISTS (
                       SELECT 1 FROM unnest(trigger.tgattr) AS attribute_number
                       JOIN pg_attribute AS attribute
                         ON attribute.attrelid = registry.table_oid
                        AND attribute.attnum = attribute_number
                       WHERE attribute.attname = 'entity_id'
                   ) AS updates_entity_id,
                   pg_get_triggerdef(trigger.oid) AS trigger_definition,
                   pg_get_functiondef(registry.function_oid) AS function_definition
            FROM expected_registry AS registry
            JOIN pg_trigger AS trigger
              ON trigger.tgrelid = registry.table_oid
             AND trigger.tgfoid = registry.function_oid
             AND trigger.tgname = 'entity_registry_entities_no_id_update'
             AND NOT trigger.tgisinternal
        """)).mappings().one_or_none()
    if trigger is None or trigger["tgenabled"] != "O" or not trigger["updates_entity_id"]:
        raise ValueError("entity registry schema is incomplete: PostgreSQL immutable entity trigger")
    trigger_definition = _normalize_sql(trigger["trigger_definition"])
    function_definition = _normalize_sql(trigger["function_definition"])
    if (
        "before update of entity_id" not in trigger_definition
        or "for each row" not in trigger_definition
        or "execute function" not in trigger_definition
        or _postgresql_function_body(function_definition)
        != "begin if new.entity_id is distinct from old.entity_id then raise exception 'entity_id is immutable'; end if; return new; end;"
    ):
        raise ValueError("entity registry schema is incomplete: PostgreSQL immutable entity trigger")


def _postgresql_function_body(function_definition: str) -> str | None:
    match = re.search(r"\bas\s+\$[a-z0-9_]*\$\s*(.*?)\s*\$[a-z0-9_]*\$", function_definition, re.DOTALL)
    return _normalize_sql(match.group(1)) if match else None
