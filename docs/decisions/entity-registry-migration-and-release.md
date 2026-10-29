# Entity Registry Migration, Compatibility, Recovery, and v0.31.0 Release Plan

> **Withdrawn (2026-10-29).** The Canonical Entity Registry epic (#413) and its
> v0.31.0 release plan were closed as not planned during a backlog reset. This
> record is kept for reference only. It is not an active contract and does not
> authorize or require any work. See `docs/STATUS.md`.

Status: proposed — requires João's explicit approval in issue #416 before any migration code, DDL, version change, workflow edit, tag, package, or publication. This record implements no migration or release behavior.

Issue: #416. Depends on the approved #414 baseline and #415 entity-registry contract. It is the required decision gate before #417, #418, #419, #420, and #422. The #403 release-publication direction was separately approved, but its workflow implementation is not present at this source commit.

## Decision

Adopt a versioned, manifest-backed migration runner for the entity-registry cutover. Treat the current data layout as **`legacy_unversioned`** at discovery and target the logical migration version **`entity_registry/1`**. The runner is a future implementation authorized only after this ADR is approved; it is not the existing inline startup DDL.

For SQLite, create and fully validate a same-volume candidate copy before one short, recoverable live-database replacement. Prefer additive tables and indexes. Rebuild/copy/swap a table only when SQLite cannot express the required constraint or key change additively. For PostgreSQL, use a dedicated migration runner, an advisory lock, transactional migration units, and separately managed concurrent indexes; do not apply the SQLite file-swap procedure to PostgreSQL.

No migration changes install assets, removes raw files/source snapshots, or uses the updater's bundle rollback as a data rollback. Existing `CD_CVM`, CNPJ, and ticker consumers remain behind an explicit compatibility API until measured equivalence is demonstrated and João makes a later, separate removal decision.

The intended release train is `v0.31.0`: an immutable `v0.31.0-rc.N` candidate is produced and validated first, then stable `v0.31.0` is published only from the approved same SHA/checksum candidate. Approval gates are: this #416 decision before migration code; #440 before accepting an immutable RC candidate; and #441 before publication. Neither this ADR nor #403 authorizes a tag or a release.

## Evidence and constraints at the decision base

This proposal was reviewed at `f006a04d5391d54621a6dc6fa1d93987b260a347` (`docs: record approved canonical entity registry contract (#415)`).

| Verified source | Evidence | Consequence |
| --- | --- | --- |
| `docs/decisions/canonical-entity-registry-contract.md` | #415 approves append-only, bitemporal registry semantics but leaves physical DDL and cutover to later work. | This ADR fixes the operational envelope, not table definitions or mappings. |
| `docs/reference/entity-registry-baseline.md` | The #414 baseline finds no verified general migration runner/version table and requires copied-DB SQLite validation plus separately validated PostgreSQL behavior. | Discovery must tolerate unversioned databases; a new runner is not described as already present. |
| `src/financials/database.py:24-139,210-240` | Startup uses idempotent `CREATE ... IF NOT EXISTS`, dynamic `ALTER TABLE`, and separate index DDL; PostgreSQL concurrent indexes use autocommit. | Registry migration runs outside the existing initializer and tracks every migration explicitly. |
| `desktop/app.py:165-282` | The only verified legacy move copies a missing main DB into Documents with SQLite Backup API; it is target-existence idempotent and logs recovery. | Reuse its copy-first lesson, but do not call it a general schema migration or rollback mechanism. |
| `scripts/data/swap_energy_kpi_compact_db.py:104-260` | The energy utility validates a candidate, retains sidecars, uses same-volume `os.replace`, writes a backup report, and attempts restoration. | Use it only as a bounded SQLite swap pattern; add durable interruption markers and registry reconciliation. |
| `desktop/updater.py`, `desktop/update_helper.ps1`, `docs/build-release.md:91-116` | The updater validates packages, swaps only executable bundle entries, and snapshots install files in LocalAppData. Documents data is denied. | Package rollback and data migration rollback are separate. |
| `.github/workflows/release-desktop.yml` | The current tag/manual workflow builds, packages, hashes, and publishes in one job. | The #403 gate remains later implementation work. |
| Issue #403 comment `5120697487` | João approved exact-SHA `push/main` CI, immutable ZIP/checksum candidate, same-SHA/checksum manual evidence, and protected final publication approval. | Later workflow work MUST implement this direction without treating it as present today. |

The packaged user-data root is `%USERPROFILE%\\Documents\\CVMAnalytics`; its main DB is normally `db/cvm_financials.db`. The runtime also owns `{data_dir}/runtime.lock`. Release artifacts must exclude user data.

## Migration catalog, durable records, and discovery

The future runner MUST use a migration catalog committed with the code and a durable state record in the data root. A catalog entry is immutable by migration ID: applied content is never edited or reused. A run begins with discovery, not an assumed version.

| Record | Future location | Required fields |
| --- | --- | --- |
| Migration catalog entry | Reviewed application source | `migration_id`, ordered target version, immutable content checksum, source commit, dialect support, requires-rebuild flag, compatibility phase, and validation specification. |
| Migration state | Before copy: authoritative `{data_dir}/metadata/migrations/<run_id>.json`; after candidate creation: candidate control table plus that JSON mirror | `run_id`, migration ID/checksum, current and target version, source commit, dialect, started/updated UTC, state, attempt, host/app version, source/candidate/backup paths, and error/recovery details. |
| Preflight/backup manifest | `{data_dir}/backup/entity-registry/<run_id>/manifest.json` | Canonical absolute paths, source and backup hashes/sizes, SQLite sidecars, free-space measurement, copy method, row-count/index inventory, collision/orphan reports, and validation result. |
| Validation report | State record and backup-manifest directory | Schema assertions, source/candidate counts, referential/collision findings, index timings, read-smoke timings, and every failed check. |

Discovery MUST inspect the control record and physical schema before ordinary startup initialization. If there is no control record, it MUST classify the source as `legacy_unversioned`, inventory its schema, and select only the catalog path explicitly allowed from that shape. A mismatch among recorded version, catalog checksum, schema fingerprint, or source-commit history becomes `blocked_inconsistent_state`; generic startup DDL must not repair it.

Before candidate copy, the JSON record is the sole authoritative state and the legacy live DB is never opened for a migration write. The runner MUST write the JSON to a temporary file in the final directory, flush the file contents, atomically replace the prior JSON, and flush the containing directory where the platform supports it; if it cannot establish the required durable atomic-write condition, it MUST block before copy. Only inside the candidate migration transaction may the runner create/populate the control table with the same run ID, state, and catalog checksum. After a validated live swap, it MUST reconcile the control table against the JSON mirror and manifest hashes before setting `succeeded`. Any disagreement among the mirror, candidate/live control row, catalog checksum, or source/candidate hash blocks normal writes; before swap the legacy source remains authoritative, and after swap the runner must either prove the new live state from the manifest or restore the named snapshot.

`source_commit` identifies the commit that supplies the catalog/runner, not the historical database creator. The JSON transition is recorded before candidate work; the candidate control row is created in the candidate transaction; and neither becomes `succeeded` until post-swap validation and reconciliation pass.

## SQLite procedure

SQLite is the installed-user path. Every non-fresh execution MUST use a non-live test root until the rehearsal gate passes. A live execution is a separate explicit migration/maintenance action; ordinary browsing must not trigger it.

1. Acquire the runtime/migration lock before opening a write connection. Abort if another live PID owns `runtime.lock`, a migration lock cannot be acquired, or an app process has the data root open. A stale lock may follow the existing PID-liveness rule and must be recorded.
2. Preflight the exact source DB: resolve paths; prove read-only readability; inventory `-wal`, `-shm`, and journal sidecars; measure free disk on candidate/backup volume; and create row-count, index, foreign-key, identifier-collision, and orphan reports. Required free space is measured source size plus candidate/backup overhead and a documented margin. The numeric margin is **Needs validation** from rehearsals, not a guessed constant.
3. Write the authoritative `copying` JSON record using the durable atomic-write procedure above, then create a consistent candidate with SQLite Backup API on the same volume. Hash the candidate and source/sidecar inventory and retain the original live DB untouched. An incomplete copy is discarded only after its failure report is captured; it never replaces the source.
4. Apply the catalog only to the candidate and create/populate its control state in that same candidate transaction. Additive registry tables, columns, and indexes happen first. Where SQLite cannot add a required key/constraint, create a named replacement table, copy explicit columns in deterministic order, validate counts/constraints, then rename/swap tables in one candidate-database transaction. Original candidate tables remain until that transaction passes.
5. Validate before touching live data: `PRAGMA quick_check` (and `integrity_check` when rehearsals establish an acceptable window), foreign-key check, catalog/schema checksum, expected registry and preserved-table counts, collision/orphan report, required indexes/timings, and compatibility read/API smoke checks. Then perform and verify a full candidate checkpoint, close every candidate connection, and prove that no candidate `-wal`, `-shm`, or journal sidecar remains. Hash the closed candidate main file and record its sidecar-absence check in the manifest. A failed checkpoint, residual candidate sidecar, or failed validation becomes `validation_failed`; it cannot swap or be reported as partial success.
6. Create the timestamped backup directory and manifest, then set `ready_to_swap`. With the app quiesced and all paths on one volume, rename live DB and sidecars into backup, rename only the closed, sidecar-free validated candidate main file into live path, and record each completed step in the JSON mirror. Each file rename is atomic, but the sequence is not a multi-file transaction; the durable marker and reversible backup are required.
7. Reopen live data read-only and repeat validation. Only then set `succeeded`, retain backup/manifest, and allow normal startup. If post-swap validation fails, retain failed new DB in backup, restore named pre-swap snapshot plus sidecars, record `rollback_succeeded` or `rollback_failed`, and stop normal write startup.

Candidate, backup, state mirror, and live DB MUST share a volume. The runner MUST not use `VACUUM`, destructive cleanup, or a live-database benchmark as a substitute for a candidate rehearsal. It MUST preserve raw files, source snapshots, import manifests, and prior valid databases.

### SQLite interruption and rerun rules

The JSON mirror preserves recovery facts even if the database file is unavailable. A new attempt may reuse a *validated* candidate only when catalog checksum, source hash, and marker match; otherwise it makes a new candidate from the preserved source.

| State at restart | Required action | Automatic continuation? |
| --- | --- | --- |
| `discovered`, `preflight_failed`, `copy_failed`, `candidate_failed`, `validation_failed` | Preserve report, keep live DB authoritative, fix cause, start a new attempt. | No. |
| `candidate_validated` / `ready_to_swap`, live source present | Revalidate candidate/source hashes, candidate checkpoint result, and absence of every candidate sidecar; discard/rebuild candidate on mismatch or residual sidecar. | No. |
| Candidate checkpoint/close interrupted or a candidate `-wal`, `-shm`, or journal remains | Preserve the report; do not move live files or candidate main file. Close/rebuild candidate from source after the cause is fixed. | No. |
| `swap_source_moved`, candidate not live | Restore named backup to live; record recovery result. | Only bounded restore after operator-confirmed paths. |
| `swap_candidate_live`, post-swap unknown | Validate new live; restore named backup if it fails. | No normal startup until recorded. |
| `rollback_succeeded` | Keep failed candidate/evidence; allow a fresh later attempt. | No. |
| `rollback_failed` or marker/path/hash inconsistency | Preserve artifacts and block writes. | Never; operator recovery required. |
| JSON mirror and candidate/live control row disagree | Before swap, preserve evidence and block with legacy source authoritative. After swap, prove the live state from control row plus manifest hashes or restore the named snapshot; do not start normal writes while unresolved. | Never. |
| `succeeded` with matching catalog checksum | Expose version/validation result and no-op. | Yes. |

## PostgreSQL procedure and limits

PostgreSQL is optional and is not compatible with SQLite sidecars, file copy, `os.replace`, or Documents-path assumptions. Future implementation MUST:

- acquire a database-scoped advisory migration lock and reject concurrent runner/startup writes;
- use the same catalog IDs, checksums, state semantics, source commit, and validation contract, but store control/manifest references in PostgreSQL and an operator-controlled artifact path;
- rehearse against restored non-production PostgreSQL copies of every supported input shape; take an approved logical/physical snapshot or verify point-in-time recovery before a live attempt;
- run ordinary DDL/data migrations in a transaction. Run `CREATE INDEX CONCURRENTLY` outside it, with a separate marker and mandatory invalid-index inspection/recovery; current startup DDL already requires autocommit for concurrent indexes;
- on ordinary transaction failure, roll it back and keep compatibility reads active. Do not claim a committed concurrent index or external side effect can be transactionally undone; and
- restore fully only from the recorded approved snapshot/PITR point, not speculative inverse DDL. Downgrade support is limited to compatibility APIs and snapshot restoration.

Deployment topology, backup retention, credentials, extension set, downtime allowance, and PITR capability are **Needs validation**. No implementation may silently fall back from PostgreSQL to SQLite or represent a SQLite copy as PostgreSQL recovery.

## Compatibility and eventual legacy removal

During adoption, callers use a compatibility facade rather than direct registry assumptions. It accepts `CD_CVM`, CNPJ, and ticker and returns the legacy input, namespace/normalization version, effective/system-as-of inputs, selected `entity_id` when resolved, selected policy/version, and explicit status (`resolved`, `conflicted`, `ambiguous`, `unavailable`, or `blocked`). It preserves #415: ticker alone never creates identity and strong-ID conflicts remain reviewable rather than auto-merged.

Compatibility is additive: existing `companies.cd_cvm` and domain records remain authoritative for their current readers until each consumer is deliberately cut over. No compatibility read may trigger a remote lookup; downloaded data stays readable offline.

Legacy direct-read removal needs all measurable evidence below plus a later João approval:

1. inventory maps every active CD_CVM/CNPJ/ticker reader, bridge/API contract, export, and persisted reference to a facade or approved exception;
2. clean install plus both supported upgrade fixtures complete without a blocked/unresolved strong-ID collision hidden by cutover;
3. reconciliation has zero unexplained losses, duplicates, or orphaned required links for scoped records;
4. focused compatibility, offline, and packaged tests show equivalent scoped results, including ambiguity/error states; and
5. release evidence records migration/compatibility version, candidate SHA/checksum, and remaining approved exceptions.

The evidence—not a calendar duration—is the threshold. João alone approves removal; #416 does not.

## Rehearsal and recovery matrix

All rehearsal roots are isolated from `%USERPROFILE%\\Documents\\CVMAnalytics` and install assets. Each run records source snapshot identity, run ID, catalog/source commit, DB bytes before/after, free disk before/after, copy/migration/validation durations, table counts, collision/orphan counts, index build durations, representative read timings, and output hashes. No performance/storage target is accepted until measured.

| Scenario | Input and action | Required result/evidence |
| --- | --- | --- |
| Fresh install | Empty isolated root | Creates target schema/version once; rerun no-ops; empty/offline state is understandable. |
| Upgrade `0.29.2` | Captured, sanitized actual `0.29.2` root/DB | Discovery identifies `legacy_unversioned`; candidate succeeds or blocks with evidence; compatibility reads reconcile. |
| Upgrade `0.30.0-rc.1` | Captured, sanitized actual RC root/DB | Same, including runtime lock/data-root behavior. |
| Identifier collision | Duplicate/overlapping strong IDs and weak ticker ambiguity | Claims/reports preserved; affected canonical link blocks rather than chooses a winner. |
| Orphan/reference defect | Fixture per expected legacy relation defect | Exact report and policy-defined block/preserved unresolved state; no silent deletion. |
| Insufficient disk | Sandbox volume/quota below measured requirement | Fails before source write/swap, records measurement, leaves source valid. |
| Locked DB / active app | Live PID/runtime lock and SQLite-lock fixture | Refuses writes and presents retry-after-close; never force-kills. |
| Interrupted copy | Terminate candidate-copy fixture | Live DB unchanged; marker/report supports safe new attempt. |
| Interrupted swap | Fault injection after each rename | Recovery validates candidate or restores named backup; never masks unknown partial state. |
| Failed validation | Candidate count, checksum, FK, or compatibility-smoke defect | No swap; `validation_failed` contains all details. |
| Successful swap | Valid same-volume candidate | Pre-swap snapshot retained; post-swap validation passes; version advances once. |
| Rollback | Force post-swap validation failure | Failed new DB retained separately; named snapshot restores/verifies; downgrade limit documented. |
| Rerun | Repeat successes and recoveries | Completed matching migration no-ops; failure path remains deterministic/auditable. |
| PostgreSQL compatibility | Restored non-production copies of supported shapes | Advisory lock, transactional path, concurrent index, validation, and snapshot restore separately demonstrated. |

Fixture availability/representativeness for `0.29.2` and `0.30.0-rc.1` are **Needs validation**. A version label is insufficient: record source DB schema, sidecars, raw/metadata layout, and provenance before accepting a fixture.

## v0.31.0 candidate and publication plan

`v0.31.0` is a milestone target, not a current version edit. Later implementation MUST preserve stable/prerelease updater semantics and accepted tag grammar. It must embody approved #403 direction in separate stages:

1. **Resolve/preflight:** bind version, full candidate SHA, `main` ancestry, tag grammar, and conditional checks; require latest exact-SHA `push/main` CI success. Resolve the intended RC or stable tag's peeled target to a full commit SHA and fail unless it equals the candidate SHA. Persist the candidate SHA, tag name, tag-target SHA, and resolution method in immutable candidate evidence.
2. **Candidate build:** the Windows builder MUST check out the resolved full candidate SHA and fail unless observed `HEAD` equals it before packaging and remains equal when build provenance is captured. Build once; verify bundled runtime version/build provenance; create flat-root ZIP and SHA-256; and upload immutable candidate evidence that persists observed build SHA, tag-target SHA, immutable artifact identity, and ZIP checksum together. Testing consumes that artifact and publication neither rebuilds it nor retags it.
3. **Manual evidence:** bind local-data checks, migration rehearsal/upgrade evidence, packaged launch, Documents path, offline, Excel, updater, and clean-install/upgrade results to that SHA/checksum. Conditional API/managed-ingestion checks remain explicitly required/not-required with diff basis.
4. **Publish:** only after preceding stages and explicit protected approval, re-resolve the RC/stable tag target and fail unless it is the immutable candidate SHA recorded beside the ZIP checksum; verify observed build SHA, tag-target SHA, immutable artifact identity, and ZIP checksum all match the immutable evidence before consuming that artifact without rebuilding or retagging. Partial GitHub publication is not automatically reversible; destructive release-asset cleanup needs separate approval.

`v0.31.0-rc.N` remains prerelease and does not replace stable updates. Stable `v0.31.0` may come only from the accepted immutable RC SHA/checksum or a newly approved immutable candidate with equivalent evidence. This ADR intentionally does not fix the number of RC iterations.

## Approval gates and non-goals

| Gate | Required decision/evidence | Authority | Effect |
| --- | --- | --- | --- |
| #416 | Approve this ADR. | João | Authorizes migration-code planning/implementation, not live migration or release. |
| #440 | Review immutable `v0.31.0-rc.N` ZIP/checksum, same-SHA CI, rehearsal/manual evidence. | João | Accepts candidate for RC use; does not publish stable. |
| #441 | Review same-SHA/checksum stable publication record and protected-release evidence. | João | Authorizes publication only. |

This ADR does not authorize DDL, data backfill, live migration, user-data cleanup, legacy deletion, updater/workflow changes, version edits, tags, packages, GitHub Releases, or release-asset deletion.

## Alternatives considered

| Alternative | Rejected because |
| --- | --- |
| Keep implicit startup DDL and add registry changes there | No catalog/version/audit record; could hide partial upgrade; unsafe work couples to ordinary startup. |
| In-place SQLite change with only backup | Constraint changes can require rebuilds; backup alone neither validates nor gives deterministic interruption recovery. |
| Rebuild every table | Expands risk/performance cost without evidence additive staging is insufficient. |
| Treat PostgreSQL like copied SQLite | It needs database lock/transaction/snapshot handling; file replacement is invalid. |
| Remove legacy identifiers immediately | Breaks persisted/read contracts before reconciliation and compatibility evidence. |
| Publish directly from tag workflow | Current workflow immediately publishes and lacks approved #403 separation. |

## Remaining validation before implementation

- Physical registry tables, constraints, mappings, and consumer cutover order belong to #417/#418 and require reviewed plans.
- Repository-wide reader inventory and sanitized historical fixtures must be acquired without using a live user DB.
- SQLite free-space rule, integrity-check window, row/index baselines, and startup/performance thresholds need rehearsal evidence.
- PostgreSQL topology, backup/PITR, operational owner, and restore exercise remain Needs validation.
- The #403 gate still needs a reviewed workflow/recovery-runbook implementation; the current workflow is not evidence it is enforced.
