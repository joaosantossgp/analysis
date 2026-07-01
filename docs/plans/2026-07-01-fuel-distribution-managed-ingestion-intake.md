# Fuel Distribution Managed Ingestion Intake Plan

## Goal

Prepare the Energy / Fuel Distribution sector intake without writing
high-cardinality facts into the main app databases. This pilot proves the
source size, grain, lineage, and bounded read plan before UI integration.

## Non-Negotiable Storage Rule

No new heavy importer may write high-cardinality detail rows into
`cvm_financials.db`, `energy_kpis.db`, or `news.db` without:

- a `ManagedDatasetRegistration`;
- an explicit storage contract;
- lineage fields for source, timestamp, import batch, parser version, and hash;
- bounded detail reads;
- a compact SQLite mart for default app screens.

## Default Storage Shape

- `metadata_sqlite`: import catalog, source snapshot metadata, manifest pointer.
- `raw_snapshot`: immutable official source files under the user data root.
- `cold_parquet`: large immutable or append-mostly analytical facts.
- `mart_sqlite`: compact summaries for overview and company/asset screens.

## Implementation Order

1. Official source discovery and size profiling. Done:
   `docs/reference/fuel-distribution-source-intake.md`.
   - Capture source URL/path, access method, cadence, file sizes, expected row
     counts, keys, entity identifiers, date coverage, units, and licensing or
     use constraints.
2. Contract finalization. Done:
   `fuel_distribution_sector_intake` is implemented in
   `src/platform/managed_ingestion_registry.py`.
   - The source grain, lineage fields, partitions, and read bounds are known.
3. Parser and importer. Done:
   `src/energy_kpi/fuel_distribution.py` and
   `scripts/data/import_fuel_distribution_sources.py`.
   - Preserve raw snapshots, write managed detail storage, create a manifest,
     and avoid unbounded writes to the main SQLite databases.
4. Marts and app reads. Partially done.
   - `fuel_distribution_product_year_mart` exists for summary-first reads.
   - UI reads and richer state/month marts remain follow-up work.

## Acceptance Before Importer Work

- Source dossier exists with row-size and storage estimate.
- Managed contract passes
  `python scripts/data/check_managed_ingestion_contracts.py --require-manifests --scan-sqlite-large-tables`.
- Storage budget impact is estimated before ingestion.
- Default UI reads are planned against marts, not full detail scans.
- Rollback and rebuild behavior is documented.
