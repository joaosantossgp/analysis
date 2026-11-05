# Research provenance: multi-window local storage

Research date: 2026-11-04.
Artifact: [research brief](local-multi-window-storage.md).
Baseline: `4b2b73cb448c234f3eb234e8300b287a2df26d52` plus pre-existing local skill installation changes.

## Method

- Applied the repository's `.agents/skills/research/SKILL.md`: fresh-context background investigation using primary sources, with findings consolidated into a repository Markdown brief.
- Inspected current source and active contracts before making recommendations. The background researcher independently examined engine, concurrency, backup and deployment documentation.
- Used a separate reviewer for an adversarial check of the brief and its key source/code claims, following the reviewer role described by the installed `research-review` skill.
- Read the installed `deep-research` skill. Its `/deepresearch` command expansion was not exposed by an available tool; this record does not claim that hidden workflow was executed. The actual workflow was repository inspection, delegated primary-source research, synthesis, independent review and document validation.
- No application edits, dependency installation, runtime database access, ingestion, performance experiments or external publishing were performed.

## Evidence classification

| Evidence | Treatment |
|---|---|
| Active source files listed in the brief | Verified in this checkout; not proof of packaged runtime behavior |
| ADR 0007 size/row measurements | Historical recorded evidence, not remeasured |
| Official vendor/project documentation | Read during this research; sources linked beside supported claims |
| Proposed coordinator/publication/backup design | Architectural inference and recommendation |
| Capacity arithmetic | Synthetic assumptions, not provider volumes or benchmark results |
| Latency goals and adoption gates | Proposed acceptance criteria; require product confirmation and experiments |

## Primary-source register

All sources below were consulted on the research date. Documentation is mutable; pin and recheck actual engine/extension versions before implementation.

| Source | Supports |
|---|---|
| [SQLite WAL](https://www.sqlite.org/wal.html) | Writer serialization, checkpoints, same-host requirement, attached-database atomicity and WAL-reset fix |
| [SQLite PRAGMAs](https://www.sqlite.org/pragma.html#pragma_synchronous) | Durability modes |
| [SQLite backup API](https://www.sqlite.org/backup.html) | Supported database snapshot backup |
| [SQLite floating point](https://www.sqlite.org/floatingpoint.html) | Exact integer versus approximate REAL representation |
| [DuckDB 2.0 concurrency](https://duckdb.org/docs/2.0/connect/concurrency) | Embedded ownership and distinct Quack topology |
| [DuckDB workload tuning](https://duckdb.org/docs/2.0/guides/performance/how_to_tune_workloads) | Spill, resource control and small-query caveats |
| [DuckDB Parquet tuning](https://duckdb.org/docs/2.0/data/parquet/tips) | File/row-group layout tradeoffs |
| [DuckDB numeric types](https://duckdb.org/docs/2.0/sql/data_types/numeric) | Fixed-point types and division semantics |
| [DuckDB extensions](https://duckdb.org/docs/2.0/extensions/overview) | Installation and offline packaging concern |
| [DuckLake catalog choice](https://ducklake.select/docs/stable/duckdb/usage/choosing_a_catalog_database) | Local SQLite and server catalog alternatives |
| [DuckLake maintenance](https://ducklake.select/docs/stable/duckdb/maintenance/recommended_maintenance) | Snapshot/file lifecycle cost |
| [DuckLake snapshots](https://ducklake.select/docs/stable/duckdb/usage/snapshots) | Managed table revisions |
| [Polars optimizations](https://docs.pola.rs/user-guide/lazy/optimizations/) | Existing lazy-reader baseline |
| [PostgreSQL architecture](https://www.postgresql.org/docs/current/tutorial-arch.html) | Local server process model |
| [PostgreSQL upgrades](https://www.postgresql.org/docs/current/upgrading.html) | Cluster lifecycle responsibilities |
| [Arrow IPC](https://arrow.apache.org/docs/python/ipc.html) | Batch transport, streaming and files |
| [pywebview API](https://pywebview.flowrl.com/api/) | Multiple windows and bridge return representation |
| [QuestDB WAL](https://questdb.com/docs/concepts/write-ahead-log/) | Conditional time-series candidate |
| [QuestDB backup](https://questdb.com/docs/operations/backup/) | Edition and operational differences |

Search snippets were not treated as authoritative when the opened official page differed. In particular, current DuckDB pages resolved to 2.0 documentation and described Quack differently from older indexed snippets. The brief explicitly distinguishes direct embedded access from client/server access.

## Remaining validation

Packaged SQLite/pywebview versions; effective PRAGMAs per connection; current user data sizes; current query plans and timings; Windows crash/power-loss behavior; cross-store snapshot recovery; offline extension availability; cold/warm multi-window benchmarks; fresh-root backup restore. No engine has been selected by measured performance in this research.

## Publication review (2026-11-05)

The publication review rechecked central active-code references and the primary
SQLite WAL, DuckDB concurrency and DuckLake catalog pages linked above. Local
Markdown links resolve. This was a targeted review, not a repeat of every source
check or an experimental validation. The original research date and method
above remain the historical record.

[Initial publication #465](https://github.com/joaosantossgp/analysis/issues/465)
can close when the documents merge. [Goal #464](https://github.com/joaosantossgp/analysis/issues/464)
and [planning/validation #466](https://github.com/joaosantossgp/analysis/issues/466)
remain open. The latter owns unresolved product choices, benchmark and recovery
evidence, architecture approval and creation of scoped implementation issues.

## Review disposition

The independent reviewer identified three material improvements, all incorporated after checking active source or official documentation:

1. Include mutable hot SQLite and current cold-directory replacement in snapshot/backup coordination; test rollover and revision restoration.
2. Select DuckLake's catalog from process ownership, not window count: native DuckDB for one owning process versus SQLite for independent local clients.
3. Make decision priorities explicit and keep existing Polars/storage as the baseline until measured workload and lifecycle requirements justify additions.
