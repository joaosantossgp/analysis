# 0008 - Database Alignment Before App Development

- **Status:** accepted
- **Date:** 2026-06-30
- **Author:** human+ai

## Context

CVMAnalytics now has a local-first analytical storage pattern for large facts.
CCEE hourly generation already uses the managed hot/cold model, but other data
domains can still grow the main SQLite databases if ingestion code writes large
detail facts directly into app databases.

Future app development depends on predictable local storage. UI work should not
need to rediscover whether a table is raw data, normalized fact data, a mart, a
cache, or a managed analytical detail store.

## Decision

All databases and ingestion paths used by future app development must be aligned
with the local storage contract before new heavy screens or sector imports are
built on top of them.

Every data layer must be explicit:

- raw/source snapshot;
- metadata and audit catalog;
- managed detail fact store;
- normalized relational dimension;
- rebuildable mart;
- UI cache.

Large detail facts must not be inserted into a main SQLite app database by
default. New high-cardinality or high-frequency datasets must declare a managed
ingestion contract before import code is added.

SQLite remains the default for app metadata, import state, dimensions, small
relational data, and query marts. Parquet or another managed analytical store is
the default for large immutable or append-mostly detail facts. Detail reads must
be bounded by entity and period.

## Immediate Application

The next database finish slice is MMGD distributed-generation project detail in
the electricity distribution domain.

Current evidence:

- `energy_kpis.db` is about 4.97 GiB after the CCEE hourly migration.
- `distribution_mmgd_projects` has about 3.9M rows.
- `distribution_mmgd_project_snapshots` has about 3.9M rows.
- The raw MMGD source file is about 100 MB, but the SQLite representation expands
  into millions of rows.

The MMGD project detail layer should move to a managed analytical store while
SQLite keeps distribution dimensions, audit tables, and aggregate marts.

## Consequences

- New app features should read summary marts by default.
- Heavy drill-down views must use bounded managed-store reads.
- Release validation must continue to run the storage budget guardrail.
- Ingestion code should fail visibly if a large dataset lacks a valid managed
  storage contract.
- Existing foreign-key issues in distribution remain separate data-quality debt;
  they must not block storage alignment work unless a migration would worsen
  them.

