# MMGD Managed Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move MMGD distributed-generation project detail out of the main Energy SQLite database while preserving auditability, aggregate reads, and local/offline operation.

**Architecture:** SQLite keeps distribution metadata, import logs, and compact MMGD aggregate marts. MMGD detail rows are stored in managed Parquet partitions under the app data root with a manifest and catalog entry. Ingestion updates the managed store and SQLite marts; legacy SQLite detail tables remain supported for existing tests and fallback reads.

**Tech Stack:** Python, SQLite, SQLAlchemy connections, Polars Parquet writer, existing `ManagedDatasetContract`, pytest.

---

### Task 1: Durable Database Contract

**Files:**
- Create: `docs/decisions/0008-database-alignment-before-app-development.md`
- Create: `docs/plans/2026-06-30-mmgd-managed-storage.md`

- [x] **Step 1: Record that all future app database work must use explicit data layers.**

Expected: the ADR states that large facts cannot silently return to the main SQLite databases.

### Task 2: MMGD Managed Store Tests

**Files:**
- Create: `tests/energy_kpi/test_mmgd_managed_store.py`
- Modify: `tests/energy_kpi/test_distribution_ingest.py`

- [x] **Step 1: Add failing tests for MMGD manifest/catalog and managed ingestion.**

Expected failures before implementation:

```text
ModuleNotFoundError: No module named 'src.energy_kpi.distribution.mmgd_store'
```

- [x] **Step 2: Add a failing aggregate test proving `distribution_mmgd_monthly_mart` is used when legacy detail tables are empty.**

Expected failure before implementation:

```text
sqlite3.OperationalError: no such table: distribution_mmgd_monthly_mart
```

### Task 3: MMGD Managed Store Implementation

**Files:**
- Create: `src/energy_kpi/distribution/mmgd_store.py`
- Modify: `src/energy_kpi/schema.py`
- Modify: `src/energy_kpi/distribution/ingest.py`
- Modify: `src/energy_kpi/distribution/aggregates.py`
- Modify: `desktop/bridge_api/distribution.py`

- [x] **Step 1: Add an MMGD `ManagedDatasetContract`.**

Expected: contract validates and manifests include a `contract` block.

- [x] **Step 2: Add `managed_dataset_catalog` and `distribution_mmgd_monthly_mart`.**

Expected: schema creation remains additive and existing DBs upgrade in place.

- [x] **Step 3: Persist MMGD detail to partitioned Parquet and update the compact monthly mart.**

Expected: managed ingestion leaves `distribution_mmgd_project_snapshots` empty for managed paths.

- [x] **Step 4: Route desktop MMGD refresh through the managed path.**

Expected: future UI-triggered MMGD refresh does not grow SQLite detail tables.

### Task 4: Migration Tooling

**Files:**
- Create: `scripts/data/compact_energy_db_without_mmgd.py`
- Create: `tests/test_compact_energy_db_without_mmgd.py`

- [x] **Step 1: Add fixture tests for compacting an Energy DB by externalizing MMGD detail.**

Expected: candidate DB has empty MMGD detail tables, a populated MMGD mart, catalog rows, and a valid manifest.

- [x] **Step 2: Implement a dry-run-safe compaction script.**

Expected: no live DB replacement happens unless an explicit apply/swap command is used.

### Task 5: Validation

**Files:**
- Modify as needed only when tests identify a real gap.

- [x] **Step 1: Run targeted tests.**

```powershell
pytest tests\energy_kpi\test_mmgd_managed_store.py tests\energy_kpi\test_distribution_ingest.py tests\test_compact_energy_db_without_mmgd.py -q
```

- [x] **Step 2: Run release-relevant storage validation.**

```powershell
python scripts\data\check_storage_budget.py
python -m compileall desktop scripts\data src\energy_kpi src\platform tests
```

- [x] **Step 3: Only after safe validation, decide whether to run the live MMGD compaction and swap.**

Expected: live compaction requires a new rollback backup and a before/after reconciliation report.

Result: live MMGD compaction and swap were run on the Documents data root after
candidate validation. The rollback backup was retained under the user data root.
