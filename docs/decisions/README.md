# Architecture Decision Records

This directory holds the durable architectural decisions made on this project.

## How to read ADRs here

- ADRs are **historical decision records**. They capture the context, alternatives, and rationale that existed at the moment the decision was made.
- Some ADRs reference planning documents (e.g. `docs/STUDENT_PACK_PLAN.md`, `docs/WEBAPP_TRANSFORMATION_PLAN.md`, `docs/V2_PHASE1_BACKEND.md`, `docs/V2_PHASE2_WEB_SLICE.md`) that have since been **archived or removed** because they were point-in-time planning artifacts. The ADR itself is the canonical record of the decision — the planning docs were inputs to it.
- ADRs should **not** be interpreted as current operational instructions. For day-to-day rules, see [`../../AGENTS.md`](../../AGENTS.md). For active reference docs, see [`../reference/`](../reference/).
- Check each record's status and its link to the superseding authority. A newer ADR or an active repository contract can supersede a decision; the absence of a newer numbered ADR does not make an old workflow current.

## Index

| # | Title |
|---|---|
| [0001](0001-desktop-folder.md) | Desktop folder layout |
| [0002](0002-student-pack-v2-stack.md) | V2 stack with GitHub Student Pack (historical; frontend superseded by Vite desktop app) |
| [0003](0003-v2-selection-criteria.md) | V2 framework selection criteria (historical) |
| [0004](0004-first-remote-runtime-railway-vercel.md) | First remote runtime: Railway + Vercel (historical; desktop is active runtime) |
| [0005](0005-offline-governance-ledger.md) | Offline governance ledger pattern (historical, used once for LT-0001; superseded by the [AGENTS.md issue-driven workflow](../../AGENTS.md#5-workflow)) |
| [0006](0006-auth-desktop.md) | Authentication for the desktop app (historical; never implemented) |
| [0007](0007-local-analytical-storage.md) | Local analytical storage for large facts |
| [0008](0008-database-alignment-before-app-development.md) | Database alignment before app development |
| [0009](0009-curated-gics-classification.md) | Curated GICS classification |
| [0010](0010-shell-owned-data-updates.md) | Shell-owned data updates |
| [0011](0011-build-once-publications-and-update-channels.md) | Build-once publications and update channels (accepted; implemented) |
| [Energy/Utilities driver pilot](energy-utilities-driver-pilot-contract.md) | Energy/Utilities system-driver pilot contract |
| [Canonical entity registry](canonical-entity-registry-contract.md) | Canonical entity registry contract (withdrawn 2026-10-29) |
| [Entity registry migration](entity-registry-migration-and-release.md) | Entity registry migration and v0.31.0 release plan (withdrawn 2026-10-29) |
